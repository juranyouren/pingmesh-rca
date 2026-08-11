"""RCACopilot-style RCA for Pingmesh cases.

This module adapts the RCACopilot paper's two-stage workflow to the local
Pingmesh data format:

    parse case -> collect diagnostic text -> summarize -> FastText retrieval
    -> time-aware demonstrations -> local LLM prediction -> Top-K evaluation

Query evidence never includes label files. Ground-truth fields are kept on
``CaseRecord`` for offline evaluation and for annotating training-set
demonstrations, while the current query is always label-free.
The implementation has a stdlib-only hashing embedding fallback so that the
pipeline can be smoke-tested on a development machine. Server runs should
provide the ``fasttext`` and ``vllm`` packages for the paper-faithful path.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
import statistics
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


IP_RE = re.compile(r"(?<![\w])(?:\d{1,3}\.){3}\d{1,3}(?![\w])")
TOKEN_RE = re.compile(r"[A-Za-z0-9_:.\-/]+|[\u4e00-\u9fff]|[^\s]")


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, list) else [parsed]
        except json.JSONDecodeError:
            return [value]
    return [value]


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _first_nonempty(mapping: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, "", [], {}):
            return value
    return ""


def _dedupe(values: Iterable[str]) -> List[str]:
    result: List[str] = []
    seen = set()
    for value in values:
        value = str(value).strip()
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _extract_ip(value: Any) -> List[str]:
    """Extract IPs from a label field without assuming one exact schema."""
    if isinstance(value, str):
        return _dedupe(IP_RE.findall(value))
    if isinstance(value, Mapping):
        direct = [
            value.get("ip"),
            value.get("mgmt_ip"),
            value.get("root_cause_ip"),
            value.get("device_ip"),
        ]
        nested = []
        for key in ("abnormal_node", "root_causes", "primary_root_causes"):
            nested.extend(_extract_ip(value.get(key)))
        return _dedupe([str(item) for item in direct if item] + nested)
    if isinstance(value, list):
        result: List[str] = []
        for item in value:
            result.extend(_extract_ip(item))
        return _dedupe(result)
    return []


def _extract_ground_truth(value: Any) -> List[str]:
    if isinstance(value, list):
        ordered = sorted(
            value,
            key=lambda item: _as_int(item.get("ranking"), 999)
            if isinstance(item, Mapping)
            else 999,
        )
        result: List[str] = []
        for item in ordered:
            result.extend(_extract_ip(item))
        return _dedupe(result)
    return _extract_ip(value)


def _safe_json(value: Any, limit: int = 1000) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        text = str(value)
    return text if len(text) <= limit else text[:limit] + "...[truncated]"


def _event_text(event: Any, limit: int = 900) -> str:
    if isinstance(event, str):
        text = event
    elif isinstance(event, Mapping):
        name = _first_nonempty(event, ("name", "alarm_name", "event_name"))
        timestamp = _first_nonempty(event, ("alarm_time", "time", "timestamp"))
        description = _first_nonempty(
            event, ("description", "alarm_description", "message", "content")
        )
        if name or timestamp or description:
            text = f"name={name};time={timestamp};description={description}"
        else:
            text = _safe_json(event, limit)
    else:
        text = str(event)
    return text if len(text) <= limit else text[:limit] + "...[truncated]"


def _node_ip(node: Mapping[str, Any]) -> str:
    return str(
        _first_nonempty(node, ("mgmt_ip", "ip", "device_ip", "name")) or ""
    )


def _node_events(node: Mapping[str, Any]) -> List[Any]:
    result: List[Any] = []
    for key in ("alarms", "syslogs", "logs", "events", "alarm_list"):
        value = node.get(key)
        if isinstance(value, list):
            result.extend(value)
    return result


def _normalise_nodes(value: Any) -> List[Dict[str, Any]]:
    if isinstance(value, Mapping):
        if all(isinstance(item, Mapping) for item in value.values()):
            nodes = []
            for key, item in value.items():
                node = dict(item)
                node.setdefault("name", key)
                nodes.append(node)
            return nodes
        return []
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, Mapping)]
    return []


def _extract_topology_nodes(full_link: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Extract nodes from the raw Preprocessor task_topo.value shape."""
    task_topo = full_link.get("task_topo", {})
    value = task_topo.get("value") if isinstance(task_topo, Mapping) else None
    if not isinstance(value, list):
        return []

    node_map: Dict[str, Dict[str, Any]] = {}
    ip_to_key: Dict[str, str] = {}
    pending_links: List[Tuple[str, str]] = []

    for path in value:
        if not isinstance(path, list):
            continue
        for segment in path:
            if not isinstance(segment, Mapping):
                continue
            for raw_node in segment.get("nodes", []) or []:
                if not isinstance(raw_node, Mapping):
                    continue
                name = str(raw_node.get("name") or raw_node.get("mgmt_ip") or "")
                ip = str(raw_node.get("mgmt_ip") or raw_node.get("ip") or "")
                if not name:
                    continue
                node = node_map.setdefault(
                    name,
                    {
                        "name": name,
                        "mgmt_ip": ip,
                        "role": raw_node.get("role", ""),
                        "linked_from": [],
                        "linked_to": [],
                        "alarms": [],
                        "logs": [],
                        "cross": 0,
                    },
                )
                for key, field_name in (("role", "role"), ("devicetype", "devicetype")):
                    if raw_node.get(key) not in (None, ""):
                        node[field_name] = raw_node[key]
                if ip:
                    ip_to_key[ip] = name
            for raw_link in segment.get("links", []) or []:
                if not isinstance(raw_link, Mapping):
                    continue
                src = str(raw_link.get("src_ip") or raw_link.get("source_ip") or "")
                dst = str(raw_link.get("dst_ip") or raw_link.get("sink_ip") or "")
                if src and dst:
                    pending_links.append((src, dst))

    for src, dst in pending_links:
        src_key = ip_to_key.get(src, src)
        dst_key = ip_to_key.get(dst, dst)
        if src_key in node_map and dst not in node_map[src_key]["linked_to"]:
            node_map[src_key]["linked_to"].append(dst)
        if dst_key in node_map and src not in node_map[dst_key]["linked_from"]:
            node_map[dst_key]["linked_from"].append(src)

    return list(node_map.values())


def _attach_global_events(
    nodes: List[Dict[str, Any]], full_link: Mapping[str, Any]
) -> Tuple[List[Dict[str, Any]], List[Any]]:
    """Attach raw alarm/log lists and retain unassigned events as global data."""
    by_ip = {_node_ip(node): node for node in nodes if _node_ip(node)}
    global_events: List[Any] = []
    for key, target_key in (("alarm_list", "alarms"), ("log_list", "logs")):
        raw = full_link.get(key, [])
        if isinstance(raw, Mapping):
            raw = _first_nonempty(raw, ("list", "data", "items", "events"))
        for event in _as_list(raw):
            if not isinstance(event, Mapping):
                global_events.append(event)
                continue
            ip = str(
                _first_nonempty(event, ("alarm_ip_ad", "mgmt_ip", "device_ip", "ip"))
                or ""
            )
            node = by_ip.get(ip)
            if node is None:
                global_events.append(event)
            else:
                node.setdefault(target_key, []).append(dict(event))
    return nodes, global_events


def _case_text(
    info: Mapping[str, Any],
    nodes: Sequence[Mapping[str, Any]],
    full_link: Mapping[str, Any],
    max_chars: int,
) -> str:
    """Build diagnostic text without reading any ground-truth fields."""
    lines: List[str] = ["Incident metadata:"]
    for key in (
        "alarm_name",
        "alarm_type",
        "analysis_type",
        "task_type",
        "scenario_code",
        "alarm_time",
        "source_ip",
        "sink_ip",
        "alarm_description",
        "alarm_description_en",
    ):
        value = info.get(key)
        if value not in (None, "", [], {}):
            lines.append(f"{key}: {_event_text(value, 1800)}")

    lines.append("Device and topology evidence:")
    ordered_nodes = sorted(
        nodes,
        key=lambda node: (
            -len(_node_events(node)),
            -_as_int(node.get("cross"), 0),
            _node_ip(node),
        ),
    )
    for node in ordered_nodes:
        ip = _node_ip(node)
        if not ip:
            continue
        neighbours = _dedupe(
            [str(x) for x in _as_list(node.get("linked_from"))]
            + [str(x) for x in _as_list(node.get("linked_to"))]
        )
        lines.append(
            "device="
            + ip
            + f";role={node.get('role', '')};cross={node.get('cross', 0)}"
            + f";neighbors={','.join(neighbours[:16])}"
        )
        events = _node_events(node)
        for event in sorted(
            events,
            key=lambda item: _as_int(item.get("alarm_time"), 0)
            if isinstance(item, Mapping)
            else 0,
        )[:40]:
            lines.append(f"device_event[{ip}]: {_event_text(event)}")

    for trace in _as_list(full_link.get("task_trace"))[:40]:
        lines.append(f"trace: {_event_text(trace)}")

    # Some raw files keep events outside node records. Include them only when
    # they have not already been attached, and keep the input bounded.
    for key in ("alarm_list", "log_list"):
        raw = full_link.get(key)
        if isinstance(raw, Mapping):
            raw = _first_nonempty(raw, ("list", "data", "items", "events"))
        for event in _as_list(raw)[:60]:
            lines.append(f"global_{key}: {_event_text(event)}")

    text = "\n".join(lines)
    return text if len(text) <= max_chars else text[:max_chars] + "\n...[case text truncated]"


@dataclass
class CaseRecord:
    case_id: str
    alarm_time_ms: int
    info: Dict[str, Any]
    nodes: List[Dict[str, Any]]
    full_link: Dict[str, Any]
    ground_truth_ips: List[str] = field(default_factory=list)
    diagnostic_text: str = ""
    summary: str = ""

    @property
    def primary_root_cause(self) -> str:
        return self.ground_truth_ips[0] if self.ground_truth_ips else ""

    @property
    def candidate_ips(self) -> List[str]:
        return _dedupe(_node_ip(node) for node in self.nodes if _node_ip(node))


def _build_case(
    case_id: str,
    info: Mapping[str, Any],
    nodes: Sequence[Mapping[str, Any]],
    full_link: Mapping[str, Any],
    ground_truth_ips: Sequence[str],
    max_text_chars: int,
) -> CaseRecord:
    info_dict = dict(info)
    full_link_dict = dict(full_link)
    node_list = [dict(node) for node in nodes]
    node_list, global_events = _attach_global_events(node_list, full_link_dict)
    if global_events:
        full_link_dict = dict(full_link_dict)
        full_link_dict["_unassigned_events"] = global_events
    alarm_time = _as_int(
        _first_nonempty(info_dict, ("alarm_time", "create_time", "send_time")), 0
    )
    return CaseRecord(
        case_id=str(case_id),
        alarm_time_ms=alarm_time,
        info=info_dict,
        nodes=node_list,
        full_link=full_link_dict,
        ground_truth_ips=_dedupe(ground_truth_ips),
        diagnostic_text=_case_text(info_dict, node_list, full_link_dict, max_text_chars),
    )


def _raw_case_from_file(path: Path, max_text_chars: int) -> Optional[CaseRecord]:
    try:
        data = _load_json(path)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, Mapping) or not isinstance(data.get("full_link"), Mapping):
        return None
    full_link = dict(data["full_link"])
    info = full_link.get("task_info")
    if not isinstance(info, Mapping):
        info = data.get("info") if isinstance(data.get("info"), Mapping) else data
    topo_nodes = _extract_topology_nodes(full_link)
    nodes = _normalise_nodes(full_link.get("nodes"))
    if not nodes:
        nodes = topo_nodes
    if not nodes:
        nodes = _normalise_nodes(data.get("nodes"))
    gt = full_link.get("ground_truth")
    if gt in (None, [], {}):
        gt = full_link.get("groud_truth")
    if gt in (None, [], {}):
        gt = full_link.get("rootcause_analysis")
    filename_match = re.search(r"pingmesh[-_](\d+)", path.stem, flags=re.IGNORECASE)
    filename_csn = filename_match.group(1) if filename_match else ""
    case_id = str(
        _first_nonempty(info, ("csn", "case_id"))
        or filename_csn
        or full_link.get("csn")
        or info.get("id")
        or path.stem
    )
    return _build_case(case_id, info, nodes, full_link, _extract_ground_truth(gt), max_text_chars)


def _node_case_from_dir(case_dir: Path, max_text_chars: int) -> Optional[CaseRecord]:
    info_path = case_dir / "info.json"
    label_path = case_dir / "label.json"
    if not info_path.exists():
        return None
    try:
        info = _load_json(info_path)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(info, Mapping):
        return None
    labels = []
    if label_path.exists():
        try:
            labels = _load_json(label_path)
        except (OSError, json.JSONDecodeError):
            labels = []

    full_link: Dict[str, Any] = {}
    nodes: List[Dict[str, Any]] = []
    for path in sorted(case_dir.glob("*.json")):
        if path.name in {"info.json", "label.json", "label_v2.json"}:
            continue
        try:
            payload = _load_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, Mapping) and isinstance(payload.get("full_link"), Mapping):
            full_link = dict(payload["full_link"])
            break
        candidate_nodes = _normalise_nodes(payload)
        if candidate_nodes:
            nodes = candidate_nodes
            if "全链路" in path.name or "nodes" in path.name:
                break

    if isinstance(full_link.get("task_info"), Mapping):
        info = {**dict(full_link["task_info"]), **dict(info)}
    if not nodes:
        nodes = _extract_topology_nodes(full_link)
    if not nodes:
        nodes = _normalise_nodes(full_link.get("nodes"))
    case_id = str(info.get("csn") or case_dir.name)
    gt = _extract_ground_truth(labels)
    if not gt:
        gt = _extract_ground_truth(full_link.get("ground_truth"))
    return _build_case(case_id, info, nodes, full_link, gt, max_text_chars)


def discover_cases(data_root: str | Path, max_text_chars: int = 24000) -> List[CaseRecord]:
    """Discover either processed case directories or raw full_link JSON files."""
    root = Path(data_root)
    if not root.exists():
        raise FileNotFoundError(f"data root does not exist: {root}")

    candidates: Dict[str, CaseRecord] = {}
    for info_path in sorted(root.rglob("info.json")):
        case = _node_case_from_dir(info_path.parent, max_text_chars)
        if case is not None:
            old = candidates.get(case.case_id)
            if old is None or len(case.diagnostic_text) >= len(old.diagnostic_text):
                candidates[case.case_id] = case

    for json_path in sorted(root.rglob("*.json")):
        case = _raw_case_from_file(json_path, max_text_chars)
        if case is None:
            continue
        old = candidates.get(case.case_id)
        if old is None or len(case.diagnostic_text) > len(old.diagnostic_text):
            candidates[case.case_id] = case

    return sorted(
        candidates.values(),
        key=lambda case: (case.alarm_time_ms, case.case_id),
    )


class HashingEmbedder:
    """Deterministic fallback used only when the fasttext package is absent."""

    def __init__(self, dimension: int = 256):
        self.dimension = dimension

    def fit(self, texts: Sequence[str]) -> None:
        del texts

    def encode(self, text: str) -> List[float]:
        vector = [0.0] * self.dimension
        tokens = [token.lower() for token in TOKEN_RE.findall(text)]
        for token in tokens:
            features = [token]
            if len(token) >= 2:
                features.extend(token[index : index + 2] for index in range(len(token) - 1))
            if len(token) >= 3:
                features.extend(token[index : index + 3] for index in range(len(token) - 2))
            for feature in features:
                digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
                index = int.from_bytes(digest[:4], "little") % self.dimension
                sign = 1.0 if digest[4] & 1 else -1.0
                vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


class FastTextEmbedder:
    """FastText wrapper with a deterministic fallback for local tests."""

    def __init__(self, dimension: int = 128):
        self.dimension = dimension
        self.model = None
        self.fallback = HashingEmbedder(max(256, dimension * 2))
        self.backend = "hashing_fallback"

    def fit(self, texts: Sequence[str]) -> None:
        if not texts:
            return
        try:
            import fasttext  # type: ignore
        except ImportError:
            self.fallback.fit(texts)
            return

        temp_path = ""
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", suffix=".txt", delete=False
            ) as stream:
                temp_path = stream.name
                for text in texts:
                    stream.write(" ".join(text.split()) + "\n")
            self.model = fasttext.train_unsupervised(
                temp_path,
                model="skipgram",
                dim=self.dimension,
                minn=2,
                maxn=5,
                epoch=10,
                minCount=1,
                thread=4,
            )
            self.backend = "fasttext"
        except Exception:
            self.model = None
            self.backend = "hashing_fallback"
        finally:
            if temp_path:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass

    def encode(self, text: str) -> List[float]:
        if self.model is not None:
            return [float(value) for value in self.model.get_sentence_vector(text)]
        return self.fallback.encode(text)


def _euclidean(left: Sequence[float], right: Sequence[float]) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(left, right)))


def time_aware_similarity(
    distance: float, delta_days: float, alpha: float = 0.3
) -> float:
    return 1.0 / (1.0 + distance * math.exp(-alpha * abs(delta_days)))


def _strip_reasoning(text: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    if "</think>" in text:
        text = text.split("</think>", 1)[1]
    return text.strip()


def _simple_summary(text: str, max_words: int = 140) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text.strip()
    return " ".join(words[:max_words]).strip() + " ..."


class FallbackLLMClient:
    """No-network fallback for smoke tests; server runs should use vLLM."""

    name = "fallback"

    def summarize(self, text: str) -> str:
        return _simple_summary(text)

    def predict(self, prompt: str, candidate_ips: Sequence[str], fallback_ips: Sequence[str]) -> str:
        del prompt
        ips = _dedupe(fallback_ips) or _dedupe(candidate_ips)
        return json.dumps(
            {"root_cause_ips": ips[:5], "explanation": "fallback retrieval ranking"},
            ensure_ascii=False,
        )


class LocalVLLMClient:
    """Small vLLM adapter matching the project's local-only runtime policy."""

    name = "vllm"

    def __init__(
        self,
        model_path: str,
        npu_cards: str = "0",
        temperature: float = 0.3,
        max_tokens: int = 1024,
        max_model_len: int = 16384,
    ):
        if not model_path:
            raise ValueError("model_path is required for LocalVLLMClient")
        os.environ["ASCEND_RT_VISIBLE_DEVICES"] = npu_cards
        from vllm import LLM, SamplingParams  # type: ignore

        cards = [item for item in npu_cards.split(",") if item.strip()]
        self.llm = LLM(
            model=model_path,
            tensor_parallel_size=max(1, len(cards)),
            distributed_executor_backend="mp",
            gpu_memory_utilization=0.85,
            max_model_len=max_model_len,
            trust_remote_code=True,
        )
        self.sampling_params = SamplingParams(
            temperature=temperature,
            max_tokens=max_tokens,
            repetition_penalty=1.05,
        )

    def _generate(self, prompt: str) -> str:
        outputs = self.llm.chat([[{"role": "user", "content": prompt}]], self.sampling_params)
        if not outputs or not outputs[0].outputs:
            return ""
        return outputs[0].outputs[0].text.strip()

    def summarize(self, text: str) -> str:
        prompt = (
            "Please summarize the following network incident diagnostic information "
            "in at most 140 words. Keep concrete device, alarm, time and link facts. "
            "Do not infer a root cause and return only the summary.\n\n"
            + text
        )
        return _strip_reasoning(self._generate(prompt))

    def predict(self, prompt: str, candidate_ips: Sequence[str], fallback_ips: Sequence[str]) -> str:
        del candidate_ips, fallback_ips
        return self._generate(prompt)


@dataclass
class RCAcopilotConfig:
    top_k: int = 5
    alpha: float = 0.3
    test_ratio: float = 0.25
    seed: int = 42
    max_text_chars: int = 24000
    summary_max_words: int = 140
    model_path: str = ""
    npu_cards: str = "0"
    temperature: float = 0.3
    max_tokens: int = 1024
    max_model_len: int = 16384


def _summary_stats(values: Sequence[float]) -> Dict[str, float]:
    if not values:
        return {"mean": 0.0, "p50": 0.0, "p95": 0.0, "p99": 0.0}
    ordered = sorted(float(value) for value in values)

    def percentile(percent: float) -> float:
        index = min(len(ordered) - 1, max(0, math.ceil(percent * len(ordered)) - 1))
        return ordered[index]

    return {
        "mean": statistics.fmean(ordered),
        "p50": percentile(0.50),
        "p95": percentile(0.95),
        "p99": percentile(0.99),
    }


def evaluate_predictions(records: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    labeled = [record for record in records if record.get("ground_truth_ips")]
    metrics: Dict[str, Any] = {
        "total_cases": len(records),
        "evaluated_cases": len(labeled),
        "coverage": (len(labeled) / len(records)) if records else 0.0,
    }
    for k in (1, 3, 5):
        hits = 0
        for record in labeled:
            predicted = record.get("predicted_ips", [])[:k]
            truth = set(record.get("ground_truth_ips", []))
            hits += int(bool(set(predicted) & truth))
        metrics[f"top{k}"] = hits / len(labeled) if labeled else 0.0
    metrics["latency_seconds"] = _summary_stats(
        [record.get("latency_seconds", 0.0) for record in records]
    )
    for stage in ("summary_seconds", "retrieval_seconds", "llm_seconds"):
        metrics[stage] = _summary_stats(
            [record.get(stage, 0.0) for record in records]
        )
    metrics["total_wall_seconds"] = sum(
        float(record.get("latency_seconds", 0.0)) for record in records
    )
    return metrics


class RCAcopilotPipeline:
    def __init__(
        self,
        config: Optional[RCAcopilotConfig] = None,
        llm_client: Optional[Any] = None,
    ):
        self.config = config or RCAcopilotConfig()
        self.embedder = FastTextEmbedder()
        self.llm = llm_client or self._build_llm()
        self.train_cases: List[CaseRecord] = []
        self.train_vectors: Dict[str, List[float]] = {}
        self.summary_cache: Dict[str, str] = {}
        self.fit_seconds = 0.0
        self.summary_fit_seconds = 0.0

    def _build_llm(self) -> Any:
        if self.config.model_path:
            try:
                return LocalVLLMClient(
                    model_path=self.config.model_path,
                    npu_cards=self.config.npu_cards,
                    temperature=self.config.temperature,
                    max_tokens=self.config.max_tokens,
                    max_model_len=self.config.max_model_len,
                )
            except Exception as exc:
                print(f"[RCAcopilot] vLLM unavailable, using fallback: {exc}")
        return FallbackLLMClient()

    def _summarize(self, case: CaseRecord) -> Tuple[str, float]:
        if case.case_id in self.summary_cache:
            case.summary = self.summary_cache[case.case_id]
            return case.summary, 0.0
        started = time.perf_counter()
        summary = self.llm.summarize(case.diagnostic_text)
        summary = _strip_reasoning(summary) or _simple_summary(
            case.diagnostic_text, self.config.summary_max_words
        )
        case.summary = summary
        self.summary_cache[case.case_id] = summary
        return summary, time.perf_counter() - started

    def fit(self, train_cases: Sequence[CaseRecord]) -> None:
        started = time.perf_counter()
        self.train_cases = list(train_cases)
        self.embedder.fit([case.diagnostic_text for case in self.train_cases])
        self.train_vectors = {
            case.case_id: self.embedder.encode(case.diagnostic_text)
            for case in self.train_cases
        }
        for case in self.train_cases:
            _, elapsed = self._summarize(case)
            self.summary_fit_seconds += elapsed
        self.fit_seconds = time.perf_counter() - started

    def _retrieve(self, query: CaseRecord) -> Tuple[List[Dict[str, Any]], float]:
        started = time.perf_counter()
        query_vector = self.embedder.encode(query.diagnostic_text)
        query_days = query.alarm_time_ms / 86400000.0
        scored: List[Dict[str, Any]] = []
        for case in self.train_cases:
            distance = _euclidean(query_vector, self.train_vectors[case.case_id])
            case_days = case.alarm_time_ms / 86400000.0
            delta_days = abs(query_days - case_days)
            similarity = time_aware_similarity(distance, delta_days, self.config.alpha)
            scored.append(
                {
                    "case_id": case.case_id,
                    "distance": distance,
                    "delta_days": delta_days,
                    "similarity": similarity,
                    "root_cause_ip": case.primary_root_cause,
                    "summary": case.summary,
                }
            )
        scored.sort(key=lambda item: (-item["similarity"], item["case_id"]))

        # Prefer distinct root-cause devices, as the paper selects diverse
        # demonstrations from different categories.
        selected: List[Dict[str, Any]] = []
        seen_labels = set()
        for item in scored:
            label = item.get("root_cause_ip", "")
            if not label or label in seen_labels:
                continue
            selected.append(item)
            seen_labels.add(label)
            if len(selected) >= self.config.top_k:
                break
        if len(selected) < self.config.top_k:
            for item in scored:
                if item not in selected:
                    selected.append(item)
                if len(selected) >= self.config.top_k:
                    break
        return selected, time.perf_counter() - started

    @staticmethod
    def _fallback_candidates(case: CaseRecord) -> List[str]:
        scored = []
        for node in case.nodes:
            ip = _node_ip(node)
            if not ip:
                continue
            events = _node_events(node)
            alarm_weight = max(
                [_as_int(event.get("alarm_weight"), 0) for event in events if isinstance(event, Mapping)]
                or [0]
            )
            score = len(events) + 0.01 * _as_int(node.get("cross"), 0) + 0.001 * alarm_weight
            scored.append((score, ip))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [ip for _, ip in scored]

    def _prediction_prompt(
        self,
        query: CaseRecord,
        query_summary: str,
        demonstrations: Sequence[Mapping[str, Any]],
    ) -> str:
        candidates = query.candidate_ips
        candidate_text = "\n".join(
            f"- {ip}" for ip in candidates[: max(50, self.config.top_k * 10)]
        ) or "- No structured candidate list available; infer from the evidence."
        demo_text = []
        for index, demo in enumerate(demonstrations, start=1):
            demo_text.append(
                f"Example {index}:\n"
                f"Summary: {demo.get('summary', '')}\n"
                f"Root-cause device IP: {demo.get('root_cause_ip', '')}"
            )
        demos = "\n\n".join(demo_text) or "No historical example is available."
        return (
            "You are performing root-cause localization for a Pingmesh network incident. "
            "Choose and rank root-cause device IPs from the candidate list. "
            "Use the historical examples as demonstrations, but rely on concrete alarm, "
            "topology, time and trace evidence. Return only valid JSON with this schema:\n"
            '{"root_cause_ips":["ip1","ip2"],"explanation":"short evidence-based explanation"}\n\n'
            "Candidate device IPs:\n"
            + candidate_text
            + "\n\nHistorical demonstrations:\n"
            + demos
            + "\n\nCurrent incident summary:\n"
            + query_summary
        )

    @staticmethod
    def _parse_prediction(
        response: str,
        candidate_ips: Sequence[str],
        fallback_ips: Sequence[str],
        top_k: int,
    ) -> Tuple[List[str], str]:
        response = _strip_reasoning(response)
        parsed: Any = None
        blocks = re.findall(r"```(?:json)?\s*(.*?)\s*```", response, flags=re.DOTALL | re.IGNORECASE)
        for block in reversed(blocks):
            try:
                parsed = json.loads(block)
                break
            except json.JSONDecodeError:
                continue
        if parsed is None:
            try:
                parsed = json.loads(response)
            except json.JSONDecodeError:
                parsed = {}
        values = parsed.get("root_cause_ips", []) if isinstance(parsed, Mapping) else []
        raw_ips = _extract_ip(values)
        candidate_set = set(candidate_ips)
        ordered = [ip for ip in raw_ips if not candidate_set or ip in candidate_set]
        for ip in _dedupe(fallback_ips):
            if ip not in ordered and (not candidate_set or ip in candidate_set):
                ordered.append(ip)
        if not ordered:
            ordered = _dedupe(candidate_ips)
        return ordered[:top_k], response

    def predict_case(self, query: CaseRecord) -> Dict[str, Any]:
        started = time.perf_counter()
        query_summary, summary_seconds = self._summarize(query)
        demonstrations, retrieval_seconds = self._retrieve(query)
        fallback_ips = [item["root_cause_ip"] for item in demonstrations if item.get("root_cause_ip")]
        fallback_ips.extend(self._fallback_candidates(query))
        prompt = self._prediction_prompt(query, query_summary, demonstrations)
        llm_started = time.perf_counter()
        response = self.llm.predict(prompt, query.candidate_ips, fallback_ips)
        llm_seconds = time.perf_counter() - llm_started
        predicted_ips, clean_response = self._parse_prediction(
            response, query.candidate_ips, fallback_ips, self.config.top_k
        )
        return {
            "case_id": query.case_id,
            "ground_truth_ips": query.ground_truth_ips,
            "predicted_ips": predicted_ips,
            "retrieved_cases": demonstrations,
            "summary": query_summary,
            "llm_response": clean_response,
            "llm_backend": getattr(self.llm, "name", type(self.llm).__name__),
            "summary_seconds": summary_seconds,
            "retrieval_seconds": retrieval_seconds,
            "llm_seconds": llm_seconds,
            "latency_seconds": time.perf_counter() - started,
        }

    def run(
        self,
        cases: Sequence[CaseRecord],
        output_dir: Optional[str | Path] = None,
    ) -> Dict[str, Any]:
        eligible = [case for case in cases if case.ground_truth_ips]
        if len(eligible) < 2:
            raise ValueError("RCACopilot requires at least two labeled cases")
        shuffled = list(eligible)
        random.Random(self.config.seed).shuffle(shuffled)
        test_count = max(1, int(round(len(shuffled) * self.config.test_ratio)))
        test_cases = shuffled[:test_count]
        train_cases = shuffled[test_count:]
        if not train_cases:
            raise ValueError("test_ratio leaves no training cases")

        self.fit(train_cases)
        records = [self.predict_case(case) for case in test_cases]
        result = {
            "config": asdict(self.config),
            "split": {
                "seed": self.config.seed,
                "test_ratio": self.config.test_ratio,
                "train_cases": len(train_cases),
                "test_cases": len(test_cases),
                "train_case_ids": [case.case_id for case in train_cases],
                "test_case_ids": [case.case_id for case in test_cases],
            },
            "backend": getattr(self.llm, "name", type(self.llm).__name__),
            "embedding_backend": self.embedder.backend,
            "fit_seconds": self.fit_seconds,
            "summary_fit_seconds": self.summary_fit_seconds,
            "metrics": evaluate_predictions(records),
            "records": records,
        }
        if output_dir is not None:
            self.write_result(result, output_dir)
        return result

    @staticmethod
    def write_result(result: Mapping[str, Any], output_dir: str | Path) -> None:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        _write_json(out / "summary.json", {key: value for key, value in result.items() if key != "records"})
        _write_json(out / "records.json", result.get("records", []))
        _write_json(out / "run_config.json", result.get("config", {}))


def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the RCACopilot Pingmesh baseline")
    parser.add_argument("--data-root", required=True, help="Processed case root or raw full_link root")
    parser.add_argument("--output-dir", required=True, help="Output directory for summary and records")
    parser.add_argument("--model-path", default=os.environ.get("PINGMESH_MODEL_PATH", ""))
    parser.add_argument("--npu-cards", default=os.environ.get("PINGMESH_NPU_CARDS", "0"))
    parser.add_argument("--test-ratio", type=float, default=0.25)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--alpha", type=float, default=0.3)
    parser.add_argument("--max-text-chars", type=int, default=24000)
    parser.add_argument("--temperature", type=float, default=0.3)
    parser.add_argument("--max-tokens", type=int, default=1024)
    parser.add_argument("--max-model-len", type=int, default=16384)
    parser.add_argument("--print-summary", action="store_true")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse_args(argv)
    cases = discover_cases(args.data_root, max_text_chars=args.max_text_chars)
    labeled = [case for case in cases if case.ground_truth_ips]
    print(f"[RCAcopilot] discovered={len(cases)} labeled={len(labeled)}")
    if len(labeled) < 2:
        print("[RCAcopilot] need at least two labeled cases")
        return 2
    config = RCAcopilotConfig(
        top_k=args.top_k,
        alpha=args.alpha,
        test_ratio=args.test_ratio,
        seed=args.seed,
        max_text_chars=args.max_text_chars,
        model_path=args.model_path,
        npu_cards=args.npu_cards,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        max_model_len=args.max_model_len,
    )
    result = RCAcopilotPipeline(config).run(cases, args.output_dir)
    print(json.dumps(result["metrics"], ensure_ascii=False, indent=2))
    if args.print_summary:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
