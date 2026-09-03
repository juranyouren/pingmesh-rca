from __future__ import annotations

import hashlib
import json
import math
import os
import random
from collections import Counter, defaultdict, deque
from dataclasses import asdict, dataclass, replace
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

from Sys.RootCauseAnalyze.stage1.alarm_topology_ranker import parse_endpoint_ips
from Sys.utils.alarm_utils import event_name, event_ts, load_alarm_weights
from Sys.utils.case_utils import find_full_link_file, get_device_ip, load_case_info, load_case_nodes
from Sys.utils.io_utils import load_json


NODE_DEVICE = 0
NODE_EVENT = 1
NODE_TYPE_COUNT = 2

REL_PHYSICAL_FORWARD = 0
REL_PHYSICAL_REVERSE = 1
REL_EVENT_TO_DEVICE = 2
REL_DEVICE_TO_EVENT = 3
REL_TEMPORAL_NEXT = 4
REL_TEMPORAL_PREVIOUS = 5
REL_NEIGHBOR_EARLIER_TO_LATER = 6
REL_NEIGHBOR_LATER_TO_EARLIER = 7
RELATION_COUNT = 8

NODE_FEATURE_DIM = 24
NODE_TYPE_FEATURE_DIM = 2
# The first two values retain the original temporal-lag contract.  The optional
# final three values are root-independent propagation state probabilities in
# the local edge orientation: source->target, target->source, and no-direct.
EDGE_FEATURE_DIM = 2
PROPAGATION_EDGE_FEATURE_DIM = 5


def edge_feature_dim(include_propagation_probabilities: bool) -> int:
    return (
        PROPAGATION_EDGE_FEATURE_DIM
        if include_propagation_probabilities
        else EDGE_FEATURE_DIM
    )


@dataclass(frozen=True)
class GraphBuildConfig:
    """Label-free settings for constructing one path-conditioned event graph."""

    event_window_ms: int = 1_800_000
    dedup_window_ms: int = 60_000
    max_events_per_device: int = 16
    max_events_total: int = 1_024
    max_neighbor_event_edges_per_link: int = 4
    max_neighbor_lag_ms: int = 600_000
    corridor_slack_hops: int = 2
    max_event_vocab: int = 256
    include_propagation_edge_probabilities: bool = False
    propagation_probability_method: str = "deterministic_evidence_v1"
    propagation_max_candidate_nodes: int = 80

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RawCase:
    dirpath: str
    nodes: List[Dict[str, Any]]
    info: Dict[str, Any]
    gt_ip: str | None = None


@dataclass
class PathConditionedGraph:
    dirpath: str
    node_features: List[List[float]]
    node_types: List[int]
    token_ids: List[int]
    edge_sources: List[int]
    edge_targets: List[int]
    edge_types: List[int]
    edge_features: List[List[float]]
    device_indices: List[int]
    device_ips: List[str]
    root_device_position: int | None
    diagnostics: Dict[str, Any]
    edge_feature_dim: int = EDGE_FEATURE_DIM


def condition_graph_on_propagation_dag(
    graph: PathConditionedGraph,
    selected_edges: Iterable[Tuple[str, str]],
    *,
    candidate_root: str | None = None,
) -> PathConditionedGraph:
    """Replace soft propagation probabilities with a candidate-specific hard DAG mask.

    A selected local direction is encoded as ``[1, 0, 0]`` and the reverse
    message-passing edge observes ``[0, 1, 0]``.  Unselected physical edges and
    all non-physical relations receive ``[0, 0, 0]``: this is an explicit mask,
    not a synthetic No-Direct label.
    """

    selected = {
        (str(source), str(target))
        for source, target in selected_edges
        if source and target and str(source) != str(target)
    }
    device_by_node = {
        int(node_index): str(ip)
        for node_index, ip in zip(graph.device_indices, graph.device_ips)
    }
    conditioned_features: List[List[float]] = []
    matched: set[Tuple[str, str]] = set()
    for source, target, relation, raw_features in zip(
        graph.edge_sources,
        graph.edge_targets,
        graph.edge_types,
        graph.edge_features,
    ):
        row = (list(raw_features) + [0.0] * PROPAGATION_EDGE_FEATURE_DIM)[
            :PROPAGATION_EDGE_FEATURE_DIM
        ]
        row[2:] = [0.0, 0.0, 0.0]
        source_ip = device_by_node.get(int(source))
        target_ip = device_by_node.get(int(target))
        if (
            relation in {REL_PHYSICAL_FORWARD, REL_PHYSICAL_REVERSE}
            and source_ip
            and target_ip
        ):
            if (source_ip, target_ip) in selected:
                row[2] = 1.0
                matched.add((source_ip, target_ip))
            elif (target_ip, source_ip) in selected:
                row[3] = 1.0
                matched.add((target_ip, source_ip))
        conditioned_features.append(row)

    diagnostics = {
        **dict(graph.diagnostics),
        "candidate_conditioned_propagation_graph": True,
        "candidate_root": candidate_root,
        "hard_selected_edge_count": len(selected),
        "hard_matched_edge_count": len(matched),
        "hard_unmatched_edge_count": len(selected - matched),
        "hard_no_direct_channel_policy": "zero_mask",
    }
    return replace(
        graph,
        edge_features=conditioned_features,
        diagnostics=diagnostics,
        edge_feature_dim=PROPAGATION_EDGE_FEATURE_DIM,
    )


class EventVocabulary:
    PAD = "<pad>"
    UNK = "<unk>"

    def __init__(self, values: Sequence[str] | None = None):
        ordered = list(values or [self.PAD, self.UNK])
        if not ordered or ordered[0] != self.PAD:
            ordered = [self.PAD, self.UNK, *ordered]
        elif len(ordered) < 2 or ordered[1] != self.UNK:
            ordered.insert(1, self.UNK)
        self.itos = ordered
        self.stoi = {value: index for index, value in enumerate(ordered)}

    @staticmethod
    def normalize(value: Any) -> str:
        return " ".join(str(value or "").strip().lower().split())

    @classmethod
    def fit(cls, cases: Sequence[RawCase], *, max_size: int = 256) -> "EventVocabulary":
        counts: Counter[str] = Counter()
        for case in cases:
            for node in case.nodes:
                for event in [*node.get("alarms", []), *node.get("logs", [])]:
                    name = cls.normalize(event_name(event))
                    if name:
                        counts[name] += 1
        values = [name for name, _count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))]
        return cls([cls.PAD, cls.UNK, *values[: max(0, int(max_size) - 2)]])

    def encode(self, value: Any) -> int:
        return self.stoi.get(self.normalize(value), 1)

    def to_dict(self) -> Dict[str, Any]:
        return {"itos": self.itos}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EventVocabulary":
        values = payload.get("itos", []) if isinstance(payload, Mapping) else []
        return cls([str(value) for value in values])


def discover_case_dirs(data_root: str, *, require_labels: bool = False) -> List[str]:
    result: List[str] = []
    for dirpath, _dirnames, filenames in os.walk(data_root):
        if "info.json" not in filenames or not find_full_link_file(dirpath, filenames):
            continue
        if require_labels and not ({"label.json", "label_v2.json"} & set(filenames)):
            continue
        result.append(os.path.normpath(dirpath))
    return sorted(result)


def _extract_ips(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, Mapping):
        for key in ("ip", "mgmt_ip", "device_ip"):
            if value.get(key):
                return [str(value[key])]
        return []
    if isinstance(value, list):
        result: List[str] = []
        for item in value:
            for ip in _extract_ips(item):
                if ip not in result:
                    result.append(ip)
        return result
    return []


def load_training_label(dirpath: str) -> str | None:
    """Read the single root only in the explicit training/evaluation path."""

    strict_path = os.path.join(dirpath, "label_v2.json")
    strict = load_json(strict_path, default=None)
    if isinstance(strict, Mapping):
        for key in ("primary_root_cause", "primary_root_causes", "secondary_root_causes", "root_causes"):
            values = _extract_ips(strict.get(key))
            if values:
                return values[0]

    legacy = load_json(os.path.join(dirpath, "label.json"), default=[])
    if not isinstance(legacy, list):
        return None
    for label in sorted(legacy, key=lambda item: item.get("ranking", 999)):
        for node in label.get("abnormal_node", []):
            ip = node.get("ip") if isinstance(node, Mapping) else None
            if ip:
                return str(ip)
    return None


def load_raw_cases(data_root: str, *, require_labels: bool) -> List[RawCase]:
    result: List[RawCase] = []
    for dirpath in discover_case_dirs(data_root, require_labels=require_labels):
        nodes = load_case_nodes(dirpath)
        info = load_case_info(dirpath)
        root = load_training_label(dirpath) if require_labels else None
        if nodes and info and (root is not None or not require_labels):
            result.append(RawCase(dirpath=dirpath, nodes=nodes, info=info, gt_ip=root))
    return result


def split_group_key(case: RawCase) -> str:
    """Group likely repeated endpoint incidents into the same CV fold."""

    source, sink = parse_endpoint_ips(case.info)
    payload = {
        "source": sorted(str(value) for value in source),
        "sink": sorted(str(value) for value in sink),
        "alarm_name": str(case.info.get("alarm_name", "")),
        "source_az": str(case.info.get("source_az", "")),
        "sink_az": str(case.info.get("sink_az", "")),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def grouped_kfold_indices(cases: Sequence[RawCase], folds: int, seed: int) -> List[List[int]]:
    if len(cases) < 2:
        raise ValueError("cross-validation requires at least two labeled cases")
    folds = max(2, min(int(folds), len(cases)))
    groups: Dict[str, List[int]] = defaultdict(list)
    for index, case in enumerate(cases):
        groups[split_group_key(case)].append(index)

    if len(groups) < 2:
        raise ValueError(
            "grouped cross-validation requires at least two distinct "
            "source/sink/alarm groups"
        )

    ordered = list(groups.items())
    random.Random(seed).shuffle(ordered)
    ordered.sort(key=lambda item: -len(item[1]))
    buckets: List[List[int]] = [[] for _ in range(min(folds, len(ordered)))]
    for _key, indices in ordered:
        target = min(range(len(buckets)), key=lambda idx: (len(buckets[idx]), idx))
        buckets[target].extend(indices)
    return [sorted(bucket) for bucket in buckets if bucket]


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalized_log(value: Any, cap: float = 8.0) -> float:
    return min(math.log1p(max(0.0, _safe_float(value))) / cap, 1.0)


def _severity(event: Any) -> float:
    if not isinstance(event, Mapping):
        return 0.0
    raw = event.get("alarm_level", event.get("severity", 0))
    return min(max(_safe_float(raw) / 4.0, 0.0), 1.0)


def _event_weight(event: Any, weights: Mapping[str, int]) -> float:
    if not isinstance(event, Mapping):
        return 0.0
    explicit = _safe_float(event.get("alarm_weight"), -1.0)
    if explicit >= 0.0:
        return min(explicit / 100.0, 1.0)
    return min(float(weights.get(EventVocabulary.normalize(event_name(event)), 0)) / 100.0, 1.0)


def _event_flags(event: Any) -> Tuple[float, float]:
    text = EventVocabulary.normalize(
        f"{event_name(event)} {event.get('description', '') if isinstance(event, Mapping) else ''}"
    )
    active = float(any(value in text for value in ("active", "occurred", "down", "fault")))
    clear = float(any(value in text for value in ("clear", "resume", "recovered", " up")))
    return active, clear


def _event_rows(
    node: Mapping[str, Any],
    ref_time: int | None,
    weights: Mapping[str, int],
    config: GraphBuildConfig,
) -> List[Dict[str, Any]]:
    raw_rows: List[Dict[str, Any]] = []
    for source_name, values in (("alarm", node.get("alarms", [])), ("log", node.get("logs", []))):
        for event in values if isinstance(values, list) else []:
            name = EventVocabulary.normalize(event_name(event))
            if not name:
                continue
            timestamp = event_ts(event)
            if ref_time is not None and timestamp is not None and abs(timestamp - ref_time) > config.event_window_ms:
                continue
            raw_rows.append(
                {
                    "name": name,
                    "timestamp": timestamp,
                    "source": source_name,
                    "severity": _severity(event),
                    "weight": _event_weight(event, weights),
                    "flags": _event_flags(event),
                }
            )

    raw_rows.sort(
        key=lambda row: (
            row["timestamp"] is None,
            row["timestamp"] if row["timestamp"] is not None else 0,
            row["name"],
            row["source"],
        )
    )
    deduped: List[Dict[str, Any]] = []
    last_by_key: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for row in raw_rows:
        key = (row["name"], row["source"])
        previous = last_by_key.get(key)
        if (
            previous is not None
            and row["timestamp"] is not None
            and previous["timestamp"] is not None
            and row["timestamp"] - previous["timestamp"] <= config.dedup_window_ms
        ):
            previous["duplicate_count"] += 1
            previous["severity"] = max(previous["severity"], row["severity"])
            previous["weight"] = max(previous["weight"], row["weight"])
            previous["flags"] = (
                max(previous["flags"][0], row["flags"][0]),
                max(previous["flags"][1], row["flags"][1]),
            )
            continue
        item = {**row, "duplicate_count": 1}
        deduped.append(item)
        last_by_key[key] = item

    def importance(row: Mapping[str, Any]) -> Tuple[float, float, float, str]:
        timestamp = row.get("timestamp")
        distance = abs(timestamp - ref_time) if timestamp is not None and ref_time is not None else config.event_window_ms * 2
        return (-float(row.get("weight", 0.0)), -float(row.get("severity", 0.0)), float(distance), str(row.get("name", "")))

    selected = sorted(deduped, key=importance)[: config.max_events_per_device]
    return sorted(
        selected,
        key=lambda row: (
            row["timestamp"] is None,
            row["timestamp"] if row["timestamp"] is not None else 0,
            row["name"],
        ),
    )


def _resolve_topology(nodes: Sequence[Mapping[str, Any]]) -> Tuple[List[str], Dict[str, Mapping[str, Any]], List[Tuple[str, str]]]:
    node_by_ip: Dict[str, Mapping[str, Any]] = {}
    aliases: Dict[str, str] = {}
    for node in nodes:
        ip = str(get_device_ip(dict(node)))
        if not ip or ip == "unknown":
            continue
        node_by_ip[ip] = node
        for alias in (ip, node.get("ip"), node.get("mgmt_ip"), node.get("name")):
            if alias:
                aliases[str(alias)] = ip

    edges = set()
    for ip, node in node_by_ip.items():
        for raw in node.get("linked_to", []) if isinstance(node.get("linked_to", []), list) else []:
            target = aliases.get(str(raw))
            if target and target != ip:
                edges.add((ip, target))
        for raw in node.get("linked_from", []) if isinstance(node.get("linked_from", []), list) else []:
            source = aliases.get(str(raw))
            if source and source != ip:
                edges.add((source, ip))
    return sorted(node_by_ip), node_by_ip, sorted(edges)


def _endpoint_anchors(
    endpoints: Iterable[str],
    node_by_ip: Mapping[str, Mapping[str, Any]],
    *,
    kind: str,
) -> List[str]:
    endpoint_set = {str(value) for value in endpoints}
    result = []
    for ip, node in node_by_ip.items():
        aliases = {ip, str(node.get("ip", "")), str(node.get("mgmt_ip", "")), str(node.get("name", ""))}
        neighbors = {
            str(value)
            for value in [
                *(node.get("linked_to", []) if isinstance(node.get("linked_to", []), list) else []),
                *(node.get("linked_from", []) if isinstance(node.get("linked_from", []), list) else []),
            ]
        }
        sign = EventVocabulary.normalize(node.get("node_sign", ""))
        accepted_signs = {"source", "src"} if kind == "source" else {"sink", "dst"}
        if endpoint_set & aliases or endpoint_set & neighbors or sign in accepted_signs:
            result.append(ip)
    return sorted(set(result))


def _distances(adjacency: Mapping[str, Sequence[str]], starts: Sequence[str]) -> Dict[str, int]:
    result: Dict[str, int] = {}
    queue: deque[str] = deque()
    for start in starts:
        if start in adjacency and start not in result:
            result[start] = 0
            queue.append(start)
    while queue:
        current = queue.popleft()
        for neighbor in adjacency.get(current, []):
            if neighbor not in result:
                result[neighbor] = result[current] + 1
                queue.append(neighbor)
    return result


def _distance_feature(distance: int | None) -> float:
    return 1.0 / (1.0 + distance) if distance is not None else 0.0


_PROPAGATION_PROBABILITY_CACHE: Dict[
    Tuple[str, str, int], Tuple[Dict[Tuple[str, str], List[float]], Dict[str, Any]]
] = {}


def _root_independent_edge_probabilities(
    case: RawCase,
    config: GraphBuildConfig,
) -> Tuple[Dict[Tuple[str, str], List[float]], Dict[str, Any]]:
    """Build orientation-aware M1 probabilities without consulting root labels."""

    method = str(config.propagation_probability_method or "deterministic_evidence_v1")
    if method not in {"deterministic_evidence_v1", "logit_softmax_v1"}:
        raise ValueError(
            "PC-STGR propagation edge features support deterministic_evidence_v1 "
            "or logit_softmax_v1; supervised edge models require an explicit "
            "fold-local model and are not accepted by this graph builder"
        )
    cache_key = (
        case_fingerprint(case),
        method,
        max(1, int(config.propagation_max_candidate_nodes)),
    )
    cached = _PROPAGATION_PROBABILITY_CACHE.get(cache_key)
    if cached is not None:
        probabilities, diagnostics = cached
        return dict(probabilities), dict(diagnostics)

    # Lazy imports keep the deterministic Stage-1 baseline independent from
    # the propagation package when the feature flag is disabled.
    from Sys.RootCauseAnalyze.propagation.m1 import reconstruct_hypothesis_graph
    from Sys.RootCauseAnalyze.propagation.schema import PropagationConfig
    from Sys.RootCauseAnalyze.propagation.topology_context import load_topology_context

    topology_context = load_topology_context(
        case.dirpath,
        node_list=case.nodes,
        info=case.info,
    )
    hypothesis_graph = reconstruct_hypothesis_graph(
        nodes=case.nodes,
        info=case.info,
        topology_context=topology_context,
        config=PropagationConfig(
            max_candidate_nodes=max(1, int(config.propagation_max_candidate_nodes)),
            edge_probability_method=method,
        ),
    )
    by_orientation: Dict[Tuple[str, str], List[float]] = {}
    for raw_pair in hypothesis_graph.get("edge_hypotheses", []):
        if not isinstance(raw_pair, Mapping):
            continue
        endpoint_a = str(raw_pair.get("endpoint_a", "") or "")
        endpoint_b = str(raw_pair.get("endpoint_b", "") or "")
        state = raw_pair.get("state_probabilities", {})
        if not endpoint_a or not endpoint_b or not isinstance(state, Mapping):
            continue
        forward = max(0.0, min(1.0, _safe_float(state.get("endpoint_a_to_b"))))
        reverse = max(0.0, min(1.0, _safe_float(state.get("endpoint_b_to_a"))))
        no_direct = max(
            0.0,
            min(1.0, _safe_float(state.get("no_direct_propagation"))),
        )
        by_orientation[(endpoint_a, endpoint_b)] = [forward, reverse, no_direct]
        by_orientation[(endpoint_b, endpoint_a)] = [reverse, forward, no_direct]

    summary = hypothesis_graph.get("summary", {})
    diagnostics = {
        "propagation_probability_method": method,
        "propagation_probability_pair_count": len(by_orientation) // 2,
        "propagation_probability_raw_topology_available": bool(
            summary.get("raw_topology_available", False)
        )
        if isinstance(summary, Mapping)
        else False,
    }
    _PROPAGATION_PROBABILITY_CACHE[cache_key] = (
        dict(by_orientation),
        dict(diagnostics),
    )
    return by_orientation, diagnostics


class PathConditionedGraphBuilder:
    def __init__(
        self,
        vocabulary: EventVocabulary,
        *,
        config: GraphBuildConfig | None = None,
        weight_path: str | None = None,
    ):
        self.vocabulary = vocabulary
        self.config = config or GraphBuildConfig()
        self.weights = load_alarm_weights(weight_path)

    def build(self, case: RawCase, *, include_labels: bool = False) -> PathConditionedGraph:
        device_ips, node_by_ip, physical_edges = _resolve_topology(case.nodes)
        if not device_ips:
            raise ValueError(f"case has no device nodes: {case.dirpath}")

        propagation_probabilities: Dict[Tuple[str, str], List[float]] = {}
        propagation_diagnostics: Dict[str, Any] = {
            "propagation_edge_probabilities_enabled": bool(
                self.config.include_propagation_edge_probabilities
            ),
            "propagation_probability_pair_count": 0,
        }
        if self.config.include_propagation_edge_probabilities:
            (
                propagation_probabilities,
                probability_diagnostics,
            ) = _root_independent_edge_probabilities(case, self.config)
            propagation_diagnostics.update(probability_diagnostics)
        current_edge_feature_dim = edge_feature_dim(
            self.config.include_propagation_edge_probabilities
        )

        ip_to_position = {ip: index for index, ip in enumerate(device_ips)}
        adjacency: Dict[str, List[str]] = {ip: [] for ip in device_ips}
        indegree: Counter[str] = Counter()
        outdegree: Counter[str] = Counter()
        for source, target in physical_edges:
            adjacency[source].append(target)
            adjacency[target].append(source)
            outdegree[source] += 1
            indegree[target] += 1

        source_ips, sink_ips = parse_endpoint_ips(case.info)
        source_anchors = _endpoint_anchors(source_ips, node_by_ip, kind="source")
        sink_anchors = _endpoint_anchors(sink_ips, node_by_ip, kind="sink")
        source_distance = _distances(adjacency, source_anchors)
        sink_distance = _distances(adjacency, sink_anchors)
        shortest = min(
            (source_distance[ip] + sink_distance[ip] for ip in device_ips if ip in source_distance and ip in sink_distance),
            default=None,
        )
        corridor = {
            ip
            for ip in device_ips
            if shortest is not None
            and ip in source_distance
            and ip in sink_distance
            and source_distance[ip] + sink_distance[ip] <= shortest + self.config.corridor_slack_hops
        }

        ref_raw = case.info.get("alarm_time")
        try:
            ref_time = int(ref_raw) if ref_raw is not None else None
        except (TypeError, ValueError):
            ref_time = None

        node_features: List[List[float]] = []
        node_types: List[int] = []
        token_ids: List[int] = []
        for ip in device_ips:
            node = node_by_ip[ip]
            role = EventVocabulary.normalize(node.get("role", ""))
            features = [0.0] * NODE_FEATURE_DIM
            features[9] = float(role == "leaf")
            features[10] = float(role == "spine")
            features[11] = float(role == "core")
            features[12] = float(role not in {"leaf", "spine", "core"})
            features[13] = _normalized_log(indegree[ip])
            features[14] = _normalized_log(outdegree[ip])
            features[15] = _normalized_log(node.get("cross", 0))
            features[16] = _normalized_log(len(node.get("alarms", [])))
            features[17] = _normalized_log(len(node.get("logs", [])))
            features[18] = float(ip in source_anchors)
            features[19] = float(ip in sink_anchors)
            features[20] = _distance_feature(source_distance.get(ip))
            features[21] = _distance_feature(sink_distance.get(ip))
            features[22] = float(ip in corridor)
            features[23] = float(ip in source_anchors or ip in sink_anchors)
            node_features.append(features)
            node_types.append(NODE_DEVICE)
            token_ids.append(0)

        event_rows_by_ip = {
            ip: _event_rows(node_by_ip[ip], ref_time, self.weights, self.config)
            for ip in device_ips
        }
        total_selected = sum(len(values) for values in event_rows_by_ip.values())
        if total_selected > self.config.max_events_total:
            flattened = []
            for ip, values in event_rows_by_ip.items():
                for row in values:
                    timestamp = row.get("timestamp")
                    distance = abs(timestamp - ref_time) if timestamp is not None and ref_time is not None else self.config.event_window_ms * 2
                    priority = (-float(row.get("weight", 0.0)), -float(row.get("severity", 0.0)), distance, ip, row["name"])
                    flattened.append((priority, ip, row))
            kept_ids = {id(row) for _priority, _ip, row in sorted(flattened)[: self.config.max_events_total]}
            event_rows_by_ip = {
                ip: [row for row in values if id(row) in kept_ids]
                for ip, values in event_rows_by_ip.items()
            }

        event_nodes_by_ip: Dict[str, List[Tuple[int, Dict[str, Any]]]] = defaultdict(list)
        for ip in device_ips:
            for row in event_rows_by_ip[ip]:
                features = [0.0] * NODE_FEATURE_DIM
                timestamp = row.get("timestamp")
                delta = (timestamp - ref_time) if timestamp is not None and ref_time is not None else 0
                features[0] = float(timestamp is not None)
                features[1] = math.tanh(delta / max(self.config.max_neighbor_lag_ms, 1))
                features[2] = min(abs(delta) / max(self.config.event_window_ms, 1), 1.0)
                features[3] = float(row.get("severity", 0.0))
                features[4] = float(row.get("source") == "alarm")
                features[5] = float(row.get("flags", (0.0, 0.0))[0])
                features[6] = float(row.get("flags", (0.0, 0.0))[1])
                features[7] = float(row.get("weight", 0.0))
                features[8] = _normalized_log(row.get("duplicate_count", 1))
                node_index = len(node_features)
                node_features.append(features)
                node_types.append(NODE_EVENT)
                token_ids.append(self.vocabulary.encode(row["name"]))
                event_nodes_by_ip[ip].append((node_index, row))

        edge_sources: List[int] = []
        edge_targets: List[int] = []
        edge_types: List[int] = []
        edge_features: List[List[float]] = []

        def add_edge(source: int, target: int, relation: int, features: Sequence[float] | None = None) -> None:
            edge_sources.append(source)
            edge_targets.append(target)
            edge_types.append(relation)
            row = list(features or [0.0] * current_edge_feature_dim)
            edge_features.append(
                (row + [0.0] * current_edge_feature_dim)[:current_edge_feature_dim]
            )

        for source_ip, target_ip in physical_edges:
            source = ip_to_position[source_ip]
            target = ip_to_position[target_ip]
            forward_features = [0.0] * EDGE_FEATURE_DIM
            reverse_features = [0.0] * EDGE_FEATURE_DIM
            if self.config.include_propagation_edge_probabilities:
                # A pair missing from the candidate hypothesis graph is unknown,
                # not a negative example. All-zero is the explicit feature mask;
                # an observed no-direct state is represented by its probability.
                forward_state = propagation_probabilities.get(
                    (source_ip, target_ip), [0.0, 0.0, 0.0]
                )
                reverse_state = propagation_probabilities.get(
                    (target_ip, source_ip), [0.0, 0.0, 0.0]
                )
                forward_features.extend(forward_state)
                reverse_features.extend(reverse_state)
            add_edge(source, target, REL_PHYSICAL_FORWARD, forward_features)
            add_edge(target, source, REL_PHYSICAL_REVERSE, reverse_features)

        for ip in device_ips:
            device_index = ip_to_position[ip]
            events = event_nodes_by_ip[ip]
            for event_index, _row in events:
                add_edge(event_index, device_index, REL_EVENT_TO_DEVICE)
                add_edge(device_index, event_index, REL_DEVICE_TO_EVENT)
            for (previous, previous_row), (current, current_row) in zip(events, events[1:]):
                previous_ts = previous_row.get("timestamp")
                current_ts = current_row.get("timestamp")
                lag = current_ts - previous_ts if previous_ts is not None and current_ts is not None else 0
                edge_row = [
                    math.tanh(lag / max(self.config.max_neighbor_lag_ms, 1)),
                    min(abs(lag) / max(self.config.max_neighbor_lag_ms, 1), 1.0),
                ]
                add_edge(previous, current, REL_TEMPORAL_NEXT, edge_row)
                add_edge(current, previous, REL_TEMPORAL_PREVIOUS, [-edge_row[0], *edge_row[1:]])

        undirected_links = {tuple(sorted((source, target))) for source, target in physical_edges}
        for left_ip, right_ip in sorted(undirected_links):
            candidates = []
            for left_index, left_row in event_nodes_by_ip[left_ip]:
                left_ts = left_row.get("timestamp")
                if left_ts is None:
                    continue
                for right_index, right_row in event_nodes_by_ip[right_ip]:
                    right_ts = right_row.get("timestamp")
                    if right_ts is None:
                        continue
                    lag = right_ts - left_ts
                    if abs(lag) <= self.config.max_neighbor_lag_ms:
                        candidates.append((abs(lag), lag, left_index, right_index))
            for _abs_lag, lag, left_index, right_index in sorted(candidates)[: self.config.max_neighbor_event_edges_per_link]:
                if lag >= 0:
                    earlier, later, positive_lag = left_index, right_index, lag
                else:
                    earlier, later, positive_lag = right_index, left_index, -lag
                edge_row = [
                    math.tanh(positive_lag / max(self.config.max_neighbor_lag_ms, 1)),
                    min(positive_lag / max(self.config.max_neighbor_lag_ms, 1), 1.0),
                ]
                add_edge(earlier, later, REL_NEIGHBOR_EARLIER_TO_LATER, edge_row)
                add_edge(later, earlier, REL_NEIGHBOR_LATER_TO_EARLIER, [-edge_row[0], *edge_row[1:]])

        root_position = (
            ip_to_position.get(case.gt_ip)
            if include_labels and case.gt_ip
            else None
        )
        return PathConditionedGraph(
            dirpath=case.dirpath,
            node_features=node_features,
            node_types=node_types,
            token_ids=token_ids,
            edge_sources=edge_sources,
            edge_targets=edge_targets,
            edge_types=edge_types,
            edge_features=edge_features,
            device_indices=list(range(len(device_ips))),
            device_ips=device_ips,
            root_device_position=root_position,
            diagnostics={
                "device_count": len(device_ips),
                "event_count": sum(len(values) for values in event_nodes_by_ip.values()),
                "edge_count": len(edge_sources),
                "source_anchor_count": len(source_anchors),
                "sink_anchor_count": len(sink_anchors),
                "corridor_device_count": len(corridor),
                "label_coverage": root_position is not None if include_labels else None,
                **propagation_diagnostics,
            },
            edge_feature_dim=current_edge_feature_dim,
        )


def case_fingerprint(case: RawCase) -> str:
    value = f"{os.path.normpath(case.dirpath)}|{case.info.get('alarm_time', '')}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
