"""Minimal BiAn Pipeline 1 reproduction with latency instrumentation.

Scope of this implementation:
  1. Monitor alert summary.
  2. Single-device anomaly analysis.
  3. Joint scoring and device ranking.

It intentionally excludes topology, timeline, Top-p filtering, early stop,
Rank of Ranks, prompt updating, fine-tuning, and multi-model evaluation.
One local 32B model is used for all three stages.

The inference path never reads label.json. Ground-truth evaluation is kept in
the separate Score_N path.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


METHOD_NAME = "BiAn-Pipeline1-32B"
DEFAULT_MODEL = "/usr/share/large_language_models/DeepSeek-R1-Distill-Qwen-32B"

ANOMALY_TYPES = (
    "Device Down",
    "Congestion",
    "Traffic Drop",
    "Flapping",
    "Network Changes",
    "Syslog Surge",
    "Alarm Count",
)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def save_json(data: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _node_ip(node: Mapping[str, Any], fallback: str = "") -> str:
    for key in ("mgmt_ip", "ip", "device_ip", "management_ip"):
        value = node.get(key)
        if value:
            return str(value)
    return fallback


def _timestamp(item: Any) -> Any:
    if not isinstance(item, Mapping):
        return None
    for key in ("alarm_time", "timestamp", "start_time", "time", "gmtCreate"):
        if item.get(key) is not None:
            return item.get(key)
    return None


def _count_alerts(node: Mapping[str, Any]) -> int:
    """Count alert records, not unique alert names."""
    return len(_as_list(node.get("alarms")))


def _count_logs(node: Mapping[str, Any]) -> int:
    return len(_as_list(node.get("logs")))


def _find_node_file(case_dir: Path) -> Optional[Path]:
    preferred: List[Path] = []
    for path in sorted(case_dir.glob("*.json")):
        name = path.name.lower()
        if name in {"info.json", "label.json", "label_v2.json", "nodes.json"}:
            continue
        if "全链路" in path.name or "full_link" in name or "full-link" in name:
            preferred.append(path)
    if preferred:
        return preferred[0]
    nodes_path = case_dir / "nodes.json"
    return nodes_path if nodes_path.exists() else None


def find_case_dirs(root: Path) -> List[Path]:
    cases: List[Path] = []
    for info_path in sorted(root.rglob("info.json")):
        case_dir = info_path.parent
        if _find_node_file(case_dir) is not None:
            cases.append(case_dir)
    return cases


def _normalise_nodes(data: Any) -> List[Dict[str, Any]]:
    values = list(data.values()) if isinstance(data, dict) else _as_list(data)
    nodes: List[Dict[str, Any]] = []
    for index, raw in enumerate(values):
        if not isinstance(raw, Mapping):
            continue
        node = dict(raw)
        ip = _node_ip(node, fallback=str(node.get("name", index)))
        if not ip:
            continue
        node["mgmt_ip"] = ip
        node["alarms"] = _as_list(node.get("alarms"))
        node["logs"] = _as_list(node.get("logs"))
        nodes.append(node)
    return nodes


def _explicit_candidate_ips(info: Mapping[str, Any]) -> List[str]:
    for key in ("candidate_devices", "candidates", "candidate_ips"):
        value = info.get(key)
        if value is None:
            continue
        values = value if isinstance(value, list) else [value]
        result: List[str] = []
        for item in values:
            if isinstance(item, Mapping):
                ip = _node_ip(item)
            else:
                ip = str(item)
            if ip and ip not in result:
                result.append(ip)
        if result:
            return result
    return []


def select_candidates(
    nodes: Sequence[Mapping[str, Any]],
    info: Mapping[str, Any],
    max_candidates: int = 6,
) -> List[Dict[str, Any]]:
    """Use an explicit candidate list when available, otherwise top alert nodes."""
    by_ip = {_node_ip(node): dict(node) for node in nodes if _node_ip(node)}
    explicit = _explicit_candidate_ips(info)
    if explicit:
        selected = [by_ip[ip] for ip in explicit if ip in by_ip]
        if selected:
            return selected[:max_candidates]

    ranked = [dict(node) for node in nodes if _node_ip(node)]
    ranked = [node for node in ranked if _count_alerts(node) or _count_logs(node)]
    ranked.sort(
        key=lambda node: (
            -_count_alerts(node),
            -_count_logs(node),
            str(_node_ip(node)),
        )
    )
    return ranked[:max_candidates]


def _compact_json(value: Any, max_chars: int = 12000) -> str:
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "...[truncated]"


def _safe_info(info: Mapping[str, Any]) -> Dict[str, Any]:
    """Remove label-like fields before any information reaches the model."""
    blocked = {
        "label",
        "labels",
        "ground_truth",
        "groud_truth",
        "rootcause_analysis",
        "root_cause",
        "abnormal_node",
    }
    return {key: value for key, value in info.items() if key not in blocked}


def build_summary_prompt(
    node: Mapping[str, Any], info: Mapping[str, Any], max_chars: int
) -> str:
    ip = _node_ip(node)
    alarms = _as_list(node.get("alarms"))
    logs = _as_list(node.get("logs"))
    return f"""TASK=ALERT_SUMMARY
你是生产级数据中心网络运维工程师。请只根据输入数据，提取设备告警摘要，不要判断根因。

DEVICE_IP={ip}
DEVICE_ROLE={node.get('role', '')}
ALARM_COUNT={len(alarms)}
CASE_INFO={_compact_json(_safe_info(info), 4000)}
ALARMS={_compact_json(alarms, max_chars)}
LOGS={_compact_json(logs, max_chars)}

只输出 JSON，不要 Markdown，不要输出 JSON 之外的内容：
{{
  "device": "{ip}",
  "summary": "简洁描述主要告警行为",
  "alarm_types": [],
  "critical_alarms": [],
  "first_alarm_time": null,
  "alarm_count": {len(alarms)},
  "evidence": []
}}"""


def build_anomaly_prompt(summary: Mapping[str, Any]) -> str:
    device = str(summary.get("device", ""))
    return f"""TASK=DEVICE_ANOMALY
你是网络故障分析工程师。请根据一个设备的告警摘要，按照 SOP 判断该设备出现了哪些异常，并给出可疑程度。

DEVICE_IP={device}
SUMMARY={_compact_json(summary, 10000)}

异常类型只能从以下列表选择：{json.dumps(ANOMALY_TYPES, ensure_ascii=False)}
判断原则：硬件/设备不可达和持续性严重告警优先级较高；告警数量多不等于一定是根因；没有证据时不要臆测。

只输出 JSON：
{{
  "device": "{device}",
  "anomalies": [{{"type": "Flapping", "severity": 0.0, "evidence": []}}],
  "overall_suspicion": 0.0,
  "reason": ""
}}"""


def build_joint_prompt(reports: Sequence[Mapping[str, Any]]) -> str:
    payload = [dict(report) for report in reports]
    return f"""TASK=JOINT_SCORING
你是网络故障根因定位工程师。请综合多个候选设备的单设备异常分析，判断最可能的根因设备。

REPORTS_JSON={_compact_json(payload, 30000)}

请遵守：
1. 所有候选设备都必须出现在 ranking 中；
2. score 为 0 到 1 的数字，所有 score 之和为 1；
3. 只能依据输入报告，不使用拓扑和时间线；
4. 输出从最可疑到最不疑的排序及简短解释。

只输出 JSON：
{{
  "ranking": [{{"device": "设备IP", "score": 0.5, "reason": ""}}],
  "root_cause": "设备IP"
}}"""


def extract_json(text: str) -> Dict[str, Any]:
    if not text:
        return {}
    candidates: List[str] = []
    candidates.extend(re.findall(r"```json\s*(.*?)\s*```", text, re.I | re.S))
    candidates.append(text.strip())
    for candidate in candidates:
        try:
            value = json.loads(candidate)
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            pass

    # Handle reasoning text around a JSON object.
    starts = [match.start() for match in re.finditer(r"\{", text)]
    for start in starts:
        try:
            value, _ = json.JSONDecoder().raw_decode(text[start:])
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            continue
    return {}


def _fallback_summary(node: Mapping[str, Any]) -> Dict[str, Any]:
    alarms = _as_list(node.get("alarms"))
    first = min(
        (value for value in (_timestamp(item) for item in alarms) if value is not None),
        default=None,
    )
    types: List[str] = []
    for alarm in alarms:
        if isinstance(alarm, Mapping):
            value = alarm.get("name") or alarm.get("alarm_name") or alarm.get("type")
            if value and str(value) not in types:
                types.append(str(value))
    return {
        "device": _node_ip(node),
        "summary": f"{len(alarms)} alert records",
        "alarm_types": types,
        "critical_alarms": [],
        "first_alarm_time": first,
        "alarm_count": len(alarms),
        "evidence": [],
    }


def _fallback_anomaly(summary: Mapping[str, Any]) -> Dict[str, Any]:
    count = int(summary.get("alarm_count", 0) or 0)
    suspicion = min(0.99, count / max(1.0, count + 3.0))
    anomalies = []
    if count:
        anomalies.append({"type": "Alarm Count", "severity": suspicion, "evidence": []})
    return {
        "device": summary.get("device", ""),
        "anomalies": anomalies,
        "overall_suspicion": suspicion,
        "reason": "Fallback score because the model response was not valid JSON.",
    }


def _normalise_ranking(
    result: Mapping[str, Any], reports: Sequence[Mapping[str, Any]]
) -> List[Dict[str, Any]]:
    by_ip = {
        str(report.get("device")): report
        for report in reports
        if report.get("device")
    }
    ranking: List[Dict[str, Any]] = []
    raw = result.get("ranking", [])
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, Mapping):
                continue
            device = str(item.get("device") or item.get("ip") or "")
            if device in by_ip and device not in {row["device"] for row in ranking}:
                try:
                    score = float(item.get("score", 0.0))
                except (TypeError, ValueError):
                    score = 0.0
                ranking.append(
                    {
                        "device": device,
                        "score": max(0.0, score),
                        "reason": str(item.get("reason", "")),
                    }
                )

    if len(ranking) != len(by_ip):
        ranking = [
            {
                "device": device,
                "score": float(report.get("overall_suspicion", 0.0) or 0.0),
                "reason": str(report.get("reason", "")),
            }
            for device, report in by_ip.items()
        ]
        ranking.sort(key=lambda row: (-row["score"], row["device"]))

    total = sum(row["score"] for row in ranking)
    if total > 0:
        for row in ranking:
            row["score"] = round(row["score"] / total, 6)
    elif ranking:
        uniform = round(1.0 / len(ranking), 6)
        for row in ranking:
            row["score"] = uniform
    return ranking


class VLLMBackend:
    def __init__(
        self,
        model_path: str,
        npu_cards: Sequence[str],
        temperature: float = 0.0,
        max_tokens: int = 2048,
        max_model_len: int = 16384,
    ) -> None:
        import vllm  # type: ignore

        self.model_path = model_path
        self.npu_cards = list(npu_cards)
        os.environ["ASCEND_RT_VISIBLE_DEVICES"] = ",".join(self.npu_cards)
        load_start = time.perf_counter()
        self.llm = vllm.LLM(
            model=model_path,
            tensor_parallel_size=max(1, len(self.npu_cards)),
            gpu_memory_utilization=0.85,
            max_model_len=max_model_len,
            trust_remote_code=True,
        )
        self.sampling_params = vllm.SamplingParams(
            temperature=temperature,
            top_p=1.0,
            max_tokens=max_tokens,
            repetition_penalty=1.05,
        )
        self.model_load_s = time.perf_counter() - load_start

    def generate(self, prompts: Sequence[str]) -> Tuple[List[str], float]:
        if not prompts:
            return [], 0.0
        messages = [[{"role": "user", "content": prompt}] for prompt in prompts]
        start = time.perf_counter()
        outputs = self.llm.chat(messages, self.sampling_params)
        elapsed = time.perf_counter() - start
        texts = [output.outputs[0].text.strip() for output in outputs]
        return texts, elapsed


class MockBackend:
    """Deterministic backend for parser/timing smoke tests without vLLM."""

    model_path = "mock"
    model_load_s = 0.0

    def generate(self, prompts: Sequence[str]) -> Tuple[List[str], float]:
        start = time.perf_counter()
        responses: List[str] = []
        for prompt in prompts:
            task = re.search(r"TASK=([^\n]+)", prompt)
            task_name = task.group(1).strip() if task else ""
            device_match = re.search(r"DEVICE_IP=([^\n]+)", prompt)
            device = device_match.group(1).strip() if device_match else ""
            count_match = re.search(r"ALARM_COUNT=(\d+)", prompt)
            count = int(count_match.group(1)) if count_match else 0
            if task_name == "ALERT_SUMMARY":
                responses.append(json.dumps(_fallback_summary({"mgmt_ip": device, "alarms": [{}] * count})))
            elif task_name == "DEVICE_ANOMALY":
                summary_match = re.search(r"SUMMARY=(.*?)(?:\n\n|$)", prompt, re.S)
                summary = json.loads(summary_match.group(1)) if summary_match else {}
                responses.append(json.dumps(_fallback_anomaly(summary)))
            elif task_name == "JOINT_SCORING":
                match = re.search(r"REPORTS_JSON=(.*?)(?:\n\n|$)", prompt, re.S)
                reports = json.loads(match.group(1)) if match else []
                rows = []
                for report in reports:
                    rows.append(
                        {
                            "device": report.get("device", ""),
                            "score": float(report.get("overall_suspicion", 0.0) or 0.0),
                            "reason": "mock",
                        }
                    )
                rows.sort(key=lambda row: (-row["score"], row["device"]))
                responses.append(json.dumps({"ranking": rows, "root_cause": rows[0]["device"] if rows else ""}))
            else:
                responses.append("{}")
        return responses, time.perf_counter() - start


class BiAnPipe1Analyzer:
    def __init__(
        self,
        backend: Any,
        max_candidates: int = 6,
        max_chars_per_device: int = 12000,
    ) -> None:
        self.backend = backend
        self.max_candidates = max_candidates
        self.max_chars_per_device = max_chars_per_device

    def _infer(self, prompts: Sequence[str]) -> Tuple[List[str], float]:
        return self.backend.generate(prompts)

    def process_one(self, case_dir: Path) -> Dict[str, Any]:
        case_start = time.perf_counter()
        load_start = time.perf_counter()
        info_path = case_dir / "info.json"
        node_path = _find_node_file(case_dir)
        info = load_json(info_path) if info_path.exists() else {}
        nodes_data = load_json(node_path) if node_path else {}
        nodes = _normalise_nodes(nodes_data)
        candidates = select_candidates(nodes, info, self.max_candidates)
        data_loading_s = time.perf_counter() - load_start

        timing = {
            "data_loading_s": data_loading_s,
            "stage1_alert_summary_s": 0.0,
            "stage2_device_anomaly_s": 0.0,
            "stage3_joint_scoring_s": 0.0,
            "llm_inference_s": 0.0,
            "end_to_end_s": 0.0,
            "num_candidates": len(candidates),
            "num_prompts": 0,
            "num_batches": 0,
        }

        if not candidates:
            result = {
                "ip": [],
                "ranking": [],
                "root_cause": "",
                "error": "No candidate device with alarms or logs was found.",
            }
            timing["end_to_end_s"] = time.perf_counter() - case_start
            return self._record(case_dir, result, {}, {}, timing)

        # Step 1: monitor alert summary.
        stage_start = time.perf_counter()
        summary_prompts = [
            build_summary_prompt(node, info, self.max_chars_per_device)
            for node in candidates
        ]
        summary_texts, summary_inference_s = self._infer(summary_prompts)
        summaries: List[Dict[str, Any]] = []
        for node, text in zip(candidates, summary_texts):
            parsed = extract_json(text)
            summaries.append(parsed if parsed.get("device") else _fallback_summary(node))
        timing["stage1_alert_summary_s"] = time.perf_counter() - stage_start
        timing["llm_inference_s"] += summary_inference_s
        timing["num_prompts"] += len(summary_prompts)
        timing["num_batches"] += 1

        # Step 2: single-device anomaly analysis.
        stage_start = time.perf_counter()
        anomaly_prompts = [build_anomaly_prompt(summary) for summary in summaries]
        anomaly_texts, anomaly_inference_s = self._infer(anomaly_prompts)
        analyses: List[Dict[str, Any]] = []
        for summary, text in zip(summaries, anomaly_texts):
            parsed = extract_json(text)
            analyses.append(parsed if parsed.get("device") else _fallback_anomaly(summary))
        timing["stage2_device_anomaly_s"] = time.perf_counter() - stage_start
        timing["llm_inference_s"] += anomaly_inference_s
        timing["num_prompts"] += len(anomaly_prompts)
        timing["num_batches"] += 1

        # Step 3: joint scoring.
        stage_start = time.perf_counter()
        joint_prompt = build_joint_prompt(analyses)
        joint_texts, joint_inference_s = self._infer([joint_prompt])
        joint_result = extract_json(joint_texts[0]) if joint_texts else {}
        ranking = _normalise_ranking(joint_result, analyses)
        timing["stage3_joint_scoring_s"] = time.perf_counter() - stage_start
        timing["llm_inference_s"] += joint_inference_s
        timing["num_prompts"] += 1
        timing["num_batches"] += 1

        result = {
            "ip": [row["device"] for row in ranking],
            "ranking": ranking,
            "root_cause": ranking[0]["device"] if ranking else "",
        }
        timing["end_to_end_s"] = time.perf_counter() - case_start
        return self._record(case_dir, result, summaries, analyses, timing)

    @staticmethod
    def _record(
        case_dir: Path,
        result: Mapping[str, Any],
        summaries: Any,
        analyses: Any,
        timing: Mapping[str, Any],
    ) -> Dict[str, Any]:
        response = "```json\n" + json.dumps(result, ensure_ascii=False, indent=2) + "\n```"
        return {
            "dir": str(case_dir),
            "method": METHOD_NAME,
            "prompt": METHOD_NAME,
            "response": response,
            "draft_response": response,
            "skill_ips": list(result.get("ip", [])),
            "stage1_alert_summaries": summaries,
            "stage2_device_analyses": analyses,
            "stage3_joint_scoring": result,
            "timing_s": dict(timing),
        }

    def process_cases(self, case_dirs: Sequence[Path]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        run_start = time.perf_counter()
        results = [self.process_one(case_dir) for case_dir in case_dirs]
        wall_clock_s = time.perf_counter() - run_start

        def mean(key: str) -> float:
            values = [float(item["timing_s"].get(key, 0.0)) for item in results]
            return sum(values) / len(values) if values else 0.0

        timing_summary = {
            "model_load_s": float(getattr(self.backend, "model_load_s", 0.0)),
            "wall_clock_s": wall_clock_s,
            "cases": len(results),
            "mean_data_loading_s": mean("data_loading_s"),
            "mean_stage1_alert_summary_s": mean("stage1_alert_summary_s"),
            "mean_stage2_device_anomaly_s": mean("stage2_device_anomaly_s"),
            "mean_stage3_joint_scoring_s": mean("stage3_joint_scoring_s"),
            "mean_llm_inference_s": mean("llm_inference_s"),
            "mean_end_to_end_s": mean("end_to_end_s"),
            "sum_end_to_end_s": sum(float(item["timing_s"].get("end_to_end_s", 0.0)) for item in results),
        }
        return results, timing_summary


def _parse_cards(value: str) -> List[str]:
    cards = [item.strip() for item in value.split(",") if item.strip()]
    return cards or ["0"]


def _build_backend(args: argparse.Namespace) -> Any:
    if args.mock:
        return MockBackend()
    return VLLMBackend(
        model_path=args.model,
        npu_cards=_parse_cards(args.npu),
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        max_model_len=args.max_model_len,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=METHOD_NAME)
    parser.add_argument(
        "data_root",
        nargs="?",
        default=os.environ.get("PINGMESH_DATA", "data/node/nodes_labeled"),
    )
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--model", default=os.environ.get("PINGMESH_MODEL_PATH", DEFAULT_MODEL))
    parser.add_argument("--npu", default=os.environ.get("PINGMESH_NPU_CARDS", "0"))
    parser.add_argument("--temperature", type=float, default=float(os.environ.get("PINGMESH_TEMPERATURE", "0.0")))
    parser.add_argument("--max-tokens", type=int, default=int(os.environ.get("PINGMESH_MAX_TOKENS", "2048")))
    parser.add_argument("--max-model-len", type=int, default=int(os.environ.get("PINGMESH_MAX_MODEL_LEN", "16384")))
    parser.add_argument("--max-candidates", type=int, default=6)
    parser.add_argument("--max-chars-per-device", type=int, default=12000)
    parser.add_argument("--mock", action="store_true", help="Run a deterministic smoke test without vLLM.")
    args = parser.parse_args(argv)

    root = Path(args.data_root).resolve()
    case_dirs = find_case_dirs(root)
    print(f"{METHOD_NAME}: {len(case_dirs)} cases found under {root}")
    backend = _build_backend(args)
    analyzer = BiAnPipe1Analyzer(
        backend=backend,
        max_candidates=args.max_candidates,
        max_chars_per_device=args.max_chars_per_device,
    )
    results, timing_summary = analyzer.process_cases(case_dirs)

    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        results_root = Path(os.environ.get("PINGMESH_RESULTS", "data/res"))
        output_dir = results_root / f"bian_pipe1_{time.strftime('%Y%m%d_%H%M%S')}"
    output_dir.mkdir(parents=True, exist_ok=True)
    save_json(results, output_dir / "res.json")
    save_json(timing_summary, output_dir / "timing.json")
    save_json(
        {
            "method": METHOD_NAME,
            "model": getattr(backend, "model_path", ""),
            "config": {
                "temperature": args.temperature,
                "max_tokens": args.max_tokens,
                "max_candidates": args.max_candidates,
            },
            "timing": timing_summary,
        },
        output_dir / "run_manifest.json",
    )
    print(json.dumps(timing_summary, ensure_ascii=False, indent=2))
    print(f"Saved to {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
