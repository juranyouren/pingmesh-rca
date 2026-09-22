"""``logit_evidence_v1``: directional evidence accumulation for one device pair.

Three evidence families decide the two directions of a candidate pair:

* **semantic causality** - does the symptom on one device explain the symptom on
  the other, in this direction?
* **evidence attribution** - does this observation actually belong to *this*
  pair, or to some unresolved third party? Attribution is a gate, never a
  positive contribution of its own.
* **temporal direction** - does the ordering of the two onset *intervals* agree
  with the claimed direction, and are those timestamps trustworthy at all?

Each family contributes a likelihood ratio; the contributions accumulate in
log-odds space:

    z(direction) = logit(p0(edge_type)) + sum_i A_i (q_s,i log LR_s,i + q_t,i log LR_t,i)

The two directions are scored independently and are *not* renormalised against
each other. A pair may score low in both directions; forcing a choice between
them is exactly the early collapse the method is meant to avoid.

Design rules this module enforces:

* Attribution multiplies *inside* the bracket, so a fully unattributed
  observation adds ``log LR = 0`` - it is uninformative, not adverse.
* Only the strongest semantic pattern claims a given evidence pair. Three
  patterns reading the same two observations are three readings of one fact,
  and stacking their likelihood ratios would triple-count it.
* Temporal evidence compares intervals, never points, and is switched off
  whenever timestamp quality is insufficient.
* Topology is not an evidence family here. It decides which pairs enter the
  candidate graph and it supplies facts to the resolver; it does not add
  propagation strength.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple

from Sys.RootCauseAnalyze.propagation.resolution import peer_attribution

EVIDENCE_SCHEMA_VERSION = "edge-evidence-logit-v1"

DEFAULT_MODEL_RELATIVE_PATH = Path("configs") / "propagation" / "evidence_logit_v1.json"

# Event types grouped by fault layer. This taxonomy is the *weakest* semantic
# pattern; it is only consulted when no stronger pattern relates the pair.
_PHYSICAL_EVENT_TYPES = frozenset(
    {"physical_link_down", "physical_link_up", "interface_state_down"}
)
_DERIVATIVE_EVENT_TYPES = frozenset(
    {
        "bgp_session_down",
        "bgp_session_up",
        "bfd_session_down",
        "lldp_neighbor_change",
        "lldp_neighbor_recovery",
        "routing_change",
    }
)

# An observation with no stated parse quality is treated as a coin flip rather
# than as certainty.
_UNSTATED_MAPPING_CONFIDENCE = 0.5

_EXPLICIT_CAUSE_SOURCE = "explicit_log_semantics"


def default_model_path() -> Path:
    return Path(__file__).resolve().parents[3] / DEFAULT_MODEL_RELATIVE_PATH


@dataclass(frozen=True)
class EvidenceModel:
    """The configurable likelihood-ratio table and edge-type priors."""

    schema_version: str
    model_id: str
    prior_by_edge_type: Mapping[str, float]
    patterns: Mapping[str, Mapping[str, float]]
    pattern_priority: Tuple[str, ...]
    temporal: Mapping[str, float]
    cause_tokens: Mapping[str, Sequence[str]] = field(default_factory=dict)
    effect_tokens: Mapping[str, Sequence[str]] = field(default_factory=dict)

    def prior_for(self, edge_type: str) -> float:
        key = str(edge_type or "")
        if key in self.prior_by_edge_type:
            return float(self.prior_by_edge_type[key])
        return float(self.prior_by_edge_type.get("_default", 0.02))

    def pattern_lr(self, pattern: str, other: str) -> float:
        spec = self.patterns.get(pattern, {})
        return float(spec.get(f"{other}_lr", 1.0))


def _validate(payload: Mapping[str, Any], origin: str) -> EvidenceModel:
    if payload.get("schema_version") != EVIDENCE_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported evidence model schema in {origin}: "
            f"{payload.get('schema_version')!r}"
        )
    priors = payload.get("prior_by_edge_type")
    if not isinstance(priors, Mapping) or "_default" not in priors:
        raise ValueError(f"evidence model {origin} needs prior_by_edge_type with a _default")
    patterns = payload.get("patterns")
    if not isinstance(patterns, Mapping) or not patterns:
        raise ValueError(f"evidence model {origin} needs a non-empty patterns table")
    priority = payload.get("pattern_priority")
    if not isinstance(priority, Sequence) or isinstance(priority, (str, bytes)):
        raise ValueError(f"evidence model {origin} needs a pattern_priority list")
    unknown = [name for name in priority if name not in patterns]
    if unknown:
        raise ValueError(f"evidence model {origin} ranks unknown patterns: {unknown}")
    for name in patterns:
        for key in ("forward_lr", "reverse_lr"):
            value = patterns[name].get(key) if isinstance(patterns[name], Mapping) else None
            if not isinstance(value, (int, float)) or float(value) <= 0.0:
                raise ValueError(
                    f"evidence model {origin}: pattern {name!r} needs a positive {key}"
                )
    temporal = payload.get("temporal")
    if not isinstance(temporal, Mapping):
        raise ValueError(f"evidence model {origin} needs a temporal table")
    for key in ("forward_lr", "reverse_lr"):
        value = temporal.get(key)
        if not isinstance(value, (int, float)) or float(value) <= 0.0:
            raise ValueError(f"evidence model {origin}: temporal needs a positive {key}")
    return EvidenceModel(
        schema_version=EVIDENCE_SCHEMA_VERSION,
        model_id=str(payload.get("model_id", origin)),
        prior_by_edge_type={str(k): float(v) for k, v in priors.items()},
        patterns={
            str(name): {
                "forward_lr": float(spec.get("forward_lr", 1.0)),
                "reverse_lr": float(spec.get("reverse_lr", 1.0)),
            }
            for name, spec in patterns.items()
        },
        pattern_priority=tuple(str(name) for name in priority),
        temporal={
            "forward_lr": float(temporal["forward_lr"]),
            "reverse_lr": float(temporal["reverse_lr"]),
        },
        cause_tokens={
            str(k): tuple(str(token) for token in v)
            for k, v in (payload.get("cause_tokens") or {}).items()
        },
        effect_tokens={
            str(k): tuple(str(token) for token in v)
            for k, v in (payload.get("effect_tokens") or {}).items()
        },
    )


@lru_cache(maxsize=8)
def _load_model_cached(origin: str) -> EvidenceModel:
    with open(origin, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return _validate(payload, origin)


def load_evidence_model(path: str | Path | None = None) -> EvidenceModel:
    """Load the likelihood-ratio table. Defaults to the shipped, uncalibrated one."""

    target = Path(path) if path else default_model_path()
    return _load_model_cached(str(target))


# --------------------------------------------------------------------------
# Episode accessors
# --------------------------------------------------------------------------


def _clamp(value: Any, low: float = 0.0, high: float = 1.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return low
    return max(low, min(high, number))


def mapping_confidence(episode: Mapping[str, Any]) -> float:
    """How much we trust the *parse* of this episode (the ``q_s`` factor)."""

    canonical = episode.get("canonical_evidence")
    if isinstance(canonical, Mapping):
        quality = canonical.get("quality")
        if isinstance(quality, Mapping) and quality.get("mapping_confidence") is not None:
            return _clamp(quality.get("mapping_confidence"))
    quality = episode.get("quality")
    if isinstance(quality, Mapping):
        # ``description`` before ``core``: ``core`` is a composite that folds in
        # timestamp availability, and timestamp reliability is already carried
        # by the temporal axis. Reading it here would charge the same uncertainty
        # to the semantic axis twice.
        for key in ("description", "core"):
            if quality.get(key) is not None:
                return _clamp(quality.get(key))
    return _UNSTATED_MAPPING_CONFIDENCE


def _timestamp_quality(episodes: Sequence[Mapping[str, Any]]) -> float:
    values = [
        _clamp(episode.get("quality", {}).get("timestamp"))
        for episode in episodes
        if isinstance(episode.get("quality"), Mapping)
    ]
    return min(values) if values else 0.0


def _earliest_raised_interval(
    episodes: Sequence[Mapping[str, Any]],
) -> List[int] | None:
    """Earliest onset interval among non-clearing episodes, or ``None``."""

    intervals = [
        episode.get("onset_interval_ms")
        for episode in episodes
        if isinstance(episode.get("onset_interval_ms"), list)
        and len(episode.get("onset_interval_ms")) == 2
        and episode.get("lifecycle") != "clear"
    ]
    if not intervals:
        return None
    return list(min(intervals, key=lambda value: (value[0], value[1])))


def _layer_class(episode: Mapping[str, Any]) -> str:
    event_type = str(episode.get("event_type", "") or "")
    if event_type in _PHYSICAL_EVENT_TYPES:
        return "physical"
    if event_type in _DERIVATIVE_EVENT_TYPES:
        return "derivative"
    return ""


def _lookup_tokens(
    episode: Mapping[str, Any], table: Mapping[str, Sequence[str]]
) -> frozenset:
    """Look an episode up in a token table.

    The LLM path labels an episode with a canonical ``predicate``; the rule path
    only has an ``event_type``. Both name the same phenomenon, so both are
    tried before the episode is treated as semantically unknown.
    """

    for key in (
        str(episode.get("predicate", "") or ""),
        str(episode.get("event_type", "") or ""),
    ):
        if not key:
            continue
        tokens = table.get(key)
        if tokens:
            return frozenset(str(token) for token in tokens)
    return frozenset()


def _cause_tokens(episode: Mapping[str, Any], model: EvidenceModel) -> frozenset:
    """Semantic tokens this episode *produces* when read as the cause side."""

    declared = episode.get("possible_effects")
    if isinstance(declared, Sequence) and not isinstance(declared, (str, bytes)) and declared:
        return frozenset(str(token) for token in declared)
    return _lookup_tokens(episode, model.cause_tokens)


def _effect_tokens(episode: Mapping[str, Any], model: EvidenceModel) -> frozenset:
    """Semantic tokens this episode *manifests* when read as the effect side."""

    return _lookup_tokens(episode, model.effect_tokens)


def _evidence_id(episode: Mapping[str, Any]) -> str:
    return str(episode.get("evidence_id", "") or "")


def _explicit_cause_predicate(episode: Mapping[str, Any]) -> str:
    hint = episode.get("cause_hint")
    if not isinstance(hint, Mapping):
        return ""
    if str(hint.get("source", "") or "") != _EXPLICIT_CAUSE_SOURCE:
        return ""
    return str(hint.get("predicate", "") or "")


# --------------------------------------------------------------------------
# Pattern matching
# --------------------------------------------------------------------------


def _matches(
    pattern: str, cause: Mapping[str, Any], effect: Mapping[str, Any], model: EvidenceModel
) -> bool:
    if pattern == "explicit_cause":
        named = _explicit_cause_predicate(effect)
        return bool(named) and named == str(cause.get("predicate", "") or "")
    if pattern == "possible_effect":
        return bool(_cause_tokens(cause, model) & _effect_tokens(effect, model))
    if pattern == "physical_to_derivative":
        return _layer_class(cause) == "physical" and _layer_class(effect) == "derivative"
    if pattern == "derivative_to_physical":
        return _layer_class(cause) == "derivative" and _layer_class(effect) == "physical"
    return False


def _claim_pattern(
    a_episode: Mapping[str, Any],
    b_episode: Mapping[str, Any],
    model: EvidenceModel,
) -> Tuple[str, str] | None:
    """Return the strongest ``(pattern, cause_side)`` for one evidence pair.

    Only one pattern may claim a pair: the alternatives are different readings
    of the same two observations, so accumulating all of them would count one
    fact several times.
    """

    for pattern in model.pattern_priority:
        if pattern not in model.patterns:
            continue
        for cause_side, (cause, effect) in (
            ("a", (a_episode, b_episode)),
            ("b", (b_episode, a_episode)),
        ):
            if _matches(pattern, cause, effect, model):
                return pattern, cause_side
    return None


def _semantic_term(
    pattern: str,
    cause_side: str,
    a_episode: Mapping[str, Any],
    b_episode: Mapping[str, Any],
    endpoint_a: str,
    endpoint_b: str,
    model: EvidenceModel,
) -> Dict[str, Any]:
    if cause_side == "a":
        cause, effect = a_episode, b_episode
        forward = model.pattern_lr(pattern, "forward")
        reverse = model.pattern_lr(pattern, "reverse")
    else:
        cause, effect = b_episode, a_episode
        forward = model.pattern_lr(pattern, "reverse")
        reverse = model.pattern_lr(pattern, "forward")

    # Attribution gates the whole term. Each observation must be bindable to the
    # *other* device of the pair; an observation whose remote end stays
    # unresolved says nothing about this pair at all.
    attribution = min(
        peer_attribution(a_episode, endpoint_b),
        peer_attribution(b_episode, endpoint_a),
    )
    return {
        "pattern": pattern,
        "kind": "semantic",
        "cause_side": cause_side,
        "attribution": round(attribution, 6),
        "semantic_lr_a_to_b": forward,
        "semantic_lr_b_to_a": reverse,
        "semantic_quality": round(
            min(mapping_confidence(cause), mapping_confidence(effect)), 6
        ),
        "temporal_lr_a_to_b": 1.0,
        "temporal_lr_b_to_a": 1.0,
        "temporal_quality": 0.0,
        "evidence_ids": sorted(
            {item for item in (_evidence_id(cause), _evidence_id(effect)) if item}
        ),
        "reason": f"{pattern}_observed_on_{cause_side}_side",
    }


def _temporal_term(
    a_episodes: Sequence[Mapping[str, Any]],
    b_episodes: Sequence[Mapping[str, Any]],
    model: EvidenceModel,
) -> Dict[str, Any] | None:
    a_interval = _earliest_raised_interval(a_episodes)
    b_interval = _earliest_raised_interval(b_episodes)
    if a_interval is None or b_interval is None:
        return None

    quality = min(
        _timestamp_quality(a_episodes),
        _timestamp_quality(b_episodes),
    )
    forward_lr = float(model.temporal["forward_lr"])
    reverse_lr = float(model.temporal["reverse_lr"])
    if a_interval[1] < b_interval[0]:
        forward, reverse, reason = forward_lr, reverse_lr, "a_interval_precedes_b"
    elif b_interval[1] < a_interval[0]:
        forward, reverse, reason = reverse_lr, forward_lr, "b_interval_precedes_a"
    else:
        forward = reverse = 1.0
        reason = "interval_overlap_no_direction"

    return {
        "pattern": "temporal_order",
        "kind": "temporal",
        "cause_side": "",
        "attribution": 1.0,
        "semantic_lr_a_to_b": 1.0,
        "semantic_lr_b_to_a": 1.0,
        "semantic_quality": 0.0,
        "temporal_lr_a_to_b": forward,
        "temporal_lr_b_to_a": reverse,
        "temporal_quality": round(quality, 6),
        "interval_a_ms": list(a_interval),
        "interval_b_ms": list(b_interval),
        "evidence_ids": sorted(
            {
                _evidence_id(item)
                for item in [*a_episodes, *b_episodes]
                if item.get("onset_interval_ms") and item.get("lifecycle") != "clear"
            }
            - {""}
        ),
        "reason": reason,
    }


# --------------------------------------------------------------------------
# Pair-level evidence and directional scoring
# --------------------------------------------------------------------------


def build_pair_evidence(
    endpoint_a: str,
    endpoint_b: str,
    episodes_a: Sequence[Mapping[str, Any]],
    episodes_b: Sequence[Mapping[str, Any]],
    *,
    model: EvidenceModel,
    edge_type: str = "physical",
    timestamp_uncertainty_ms: int = 5_000,
) -> Dict[str, Any]:
    """Assemble the root-independent evidence terms for one candidate pair.

    This is evidence *extraction*: it records what was observed and how strong
    each observation is. Turning the terms into directional scores is the
    scoring method's job, so the same terms can be re-scored without re-parsing.
    """

    terms: List[Dict[str, Any]] = []
    for a_episode in episodes_a:
        if not isinstance(a_episode, Mapping):
            continue
        for b_episode in episodes_b:
            if not isinstance(b_episode, Mapping):
                continue
            claimed = _claim_pattern(a_episode, b_episode, model)
            if claimed is None:
                continue
            pattern, cause_side = claimed
            terms.append(
                _semantic_term(
                    pattern, cause_side, a_episode, b_episode,
                    str(endpoint_a), str(endpoint_b), model,
                )
            )

    temporal = _temporal_term(episodes_a, episodes_b, model)
    if temporal is not None:
        terms.append(temporal)

    peer_bearing = [
        episode
        for episode in [*episodes_a, *episodes_b]
        if isinstance(episode, Mapping) and str(episode.get("peer_raw", "") or "")
    ]
    attribution_available = all(
        str(episode.get("peer_resolution", {}).get("status", "") or "") == "resolved"
        for episode in peer_bearing
    ) if peer_bearing else True

    semantic_available = any(
        term["kind"] == "semantic" and float(term["attribution"]) > 0.0 for term in terms
    )
    temporal_available = temporal is not None

    return {
        "edge_type": str(edge_type or "physical"),
        "model_id": model.model_id,
        "timestamp_uncertainty_ms": int(timestamp_uncertainty_ms),
        "terms": terms,
        "diagnostics": {
            "semantic_available": semantic_available,
            "temporal_available": temporal_available,
            "attribution_available": attribution_available,
            "pattern_counts": _pattern_counts(terms),
        },
    }


def _pattern_counts(terms: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for term in terms:
        name = str(term.get("pattern", ""))
        counts[name] = counts.get(name, 0) + 1
    return dict(sorted(counts.items()))


def _sigmoid(value: float) -> float:
    if value >= 0.0:
        return 1.0 / (1.0 + math.exp(-value))
    exponential = math.exp(value)
    return exponential / (1.0 + exponential)


def _logit(probability: float) -> float:
    clipped = max(1e-9, min(1.0 - 1e-9, float(probability)))
    return math.log(clipped / (1.0 - clipped))


def _direction_contributions(
    terms: Sequence[Mapping[str, Any]], key: str
) -> List[Dict[str, Any]]:
    contributions: List[Dict[str, Any]] = []
    for term in terms:
        semantic_lr = float(term.get(f"semantic_lr_{key}", 1.0))
        temporal_lr = float(term.get(f"temporal_lr_{key}", 1.0))
        attribution = float(term.get("attribution", 1.0) or 0.0)
        semantic_quality = float(term.get("semantic_quality", 0.0) or 0.0)
        temporal_quality = float(term.get("temporal_quality", 0.0) or 0.0)
        log_contribution = attribution * (
            semantic_quality * math.log(semantic_lr)
            + temporal_quality * math.log(temporal_lr)
        )
        contributions.append(
            {
                "pattern": str(term.get("pattern", "")),
                "kind": str(term.get("kind", "")),
                "cause_side": str(term.get("cause_side", "")),
                "attribution": round(attribution, 6),
                "semantic_lr_a_to_b": float(term.get("semantic_lr_a_to_b", 1.0)),
                "semantic_lr_b_to_a": float(term.get("semantic_lr_b_to_a", 1.0)),
                "semantic_quality": round(semantic_quality, 6),
                "temporal_lr_a_to_b": float(term.get("temporal_lr_a_to_b", 1.0)),
                "temporal_lr_b_to_a": float(term.get("temporal_lr_b_to_a", 1.0)),
                "temporal_quality": round(temporal_quality, 6),
                "log_contribution": round(log_contribution, 9),
                "evidence_ids": list(term.get("evidence_ids", [])),
                "reason": str(term.get("reason", "")),
            }
        )
    return contributions


def directional_scores(
    pair_evidence: Mapping[str, Any],
    *,
    model: EvidenceModel,
    edge_type: str | None = None,
) -> Dict[str, Any]:
    """Accumulate the evidence terms into two independent directional scores."""

    terms = [
        term for term in pair_evidence.get("terms", []) if isinstance(term, Mapping)
    ]
    resolved_edge_type = str(edge_type or pair_evidence.get("edge_type", "physical"))
    prior = model.prior_for(resolved_edge_type)
    base = _logit(prior)

    a_to_b = _direction_contributions(terms, "a_to_b")
    b_to_a = _direction_contributions(terms, "b_to_a")
    logit_a = base + sum(item["log_contribution"] for item in a_to_b)
    logit_b = base + sum(item["log_contribution"] for item in b_to_a)
    score_a = _sigmoid(logit_a)
    score_b = _sigmoid(logit_b)
    # Neither direction accounting for the relation leaves the remainder:
    # this is a convenience mass for downstream gating, not a normalisation.
    no_direct = (1.0 - score_a) * (1.0 - score_b)

    diagnostics = pair_evidence.get("diagnostics", {})
    features = {
        "semantic_available": bool(diagnostics.get("semantic_available", False)),
        "temporal_available": bool(diagnostics.get("temporal_available", False)),
        "attribution_available": bool(diagnostics.get("attribution_available", True)),
    }

    def _counter(contributions: Sequence[Mapping[str, Any]]) -> List[str]:
        ids = {
            evidence_id
            for item in contributions
            if float(item["log_contribution"]) < 0.0
            for evidence_id in item["evidence_ids"]
        }
        return sorted(ids)

    return {
        "edge_type": resolved_edge_type,
        "model_id": str(pair_evidence.get("model_id", model.model_id)),
        "prior": round(prior, 9),
        "prior_logit": round(base, 9),
        "a_to_b_logit": round(logit_a, 9),
        "b_to_a_logit": round(logit_b, 9),
        "a_to_b_score": round(score_a, 9),
        "b_to_a_score": round(score_b, 9),
        "no_direct_score": round(no_direct, 9),
        "a_to_b_contributions": a_to_b,
        "b_to_a_contributions": b_to_a,
        "features": features,
        "evidence_ids": sorted(
            {evidence_id for item in [*a_to_b, *b_to_a] for evidence_id in item["evidence_ids"]}
        ),
        "counter_evidence_ids": sorted(
            set(_counter(a_to_b)) | set(_counter(b_to_a))
        ),
    }
