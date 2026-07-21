"""Small-model semantic compression for per-device evidence.

Exact facts remain in deterministic JSON records. The small model receives one
target device at a time together with bounded alarms from directly adjacent
devices, and adds only a concise semantic description of the observed pattern.
"""

from __future__ import annotations

import gc
import inspect
import json
import os
import re
from typing import Any, Callable, Dict, List, Sequence


SUMMARY_PROMPT_VERSION = "device-neighbor-correlation-v4"
DEFAULT_SUMMARY_CONTEXT_MAX_CHARS = int(
    os.environ.get("PINGMESH_SUMMARY_CONTEXT_MAX_CHARS", "3500")
)

_REASONING_BLOCK = re.compile(
    r"<(?:think|analysis)\b[^>]*>.*?</(?:think|analysis)\s*>",
    re.IGNORECASE | re.DOTALL,
)
_UNCLOSED_REASONING_BLOCK = re.compile(
    r"<(?:think|analysis)\b[^>]*>.*\Z",
    re.IGNORECASE | re.DOTALL,
)


def strip_reasoning_content(text: str) -> str:
    """Remove hidden reasoning blocks from a summary-model response."""
    if not isinstance(text, str):
        return ""
    cleaned = _REASONING_BLOCK.sub("", text)
    cleaned = _UNCLOSED_REASONING_BLOCK.sub("", cleaned)
    return cleaned.strip()


def _parse_npu_cards(npu_spec: str) -> List[int]:
    if not isinstance(npu_spec, str) or not npu_spec.strip():
        return []
    return [int(part.strip()) for part in npu_spec.split(",") if part.strip().isdigit()]


def _cache_limit_kwargs(
    supported_engine_args: set[str],
    *,
    kv_cache_memory_bytes: int | None,
    num_gpu_blocks_override: int | None,
) -> dict:
    """Choose the KV-cache cap option supported by the installed vLLM."""
    if kv_cache_memory_bytes is not None and "kv_cache_memory_bytes" in supported_engine_args:
        return {"kv_cache_memory_bytes": kv_cache_memory_bytes}
    if num_gpu_blocks_override is not None and "num_gpu_blocks_override" in supported_engine_args:
        return {"num_gpu_blocks_override": num_gpu_blocks_override}
    if kv_cache_memory_bytes is not None or num_gpu_blocks_override is not None:
        raise RuntimeError(
            "Installed vLLM exposes neither kv_cache_memory_bytes nor "
            "num_gpu_blocks_override; cannot safely cap the summary KV cache."
        )
    return {}


_DEVICE_SUMMARY_PROMPT = (
    "你是网络告警事件摘要器，不是根因排序器。输入包含一个目标设备的告警，以及与它直接相邻设备的受限告警上下文。\n"
    "请结合目标告警和邻接告警之间可观察到的关联，概括目标设备周边发生了什么；必须区分目标设备自身告警与邻接设备告警。\n"
    "alarm weight 只是人工规则权重，用于控制上下文选择，不代表严重度或已确认因果。\n"
    "只能使用输入事实。不要判断根因、嫌疑排名、概率或置信度，不要把同时出现直接写成因果，不要给出处置建议。\n"
    "不要展示思考过程，不要输出 JSON 或列表。直接输出一句简洁中文；没有任何告警时输出“未观察到告警”。\n\n"
    "Target and adjacent alarm evidence:\n"
    "{device_json}\n"
)


def _summary_payload(device: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "target_device": {
            "ip": device.get("ip"),
            "alarms": list(device.get("alarms", []) or []),
            "alarm_events": list(device.get("alarm_events", []) or []),
            "high_weight_alarms": list(device.get("high_weight_alarms", []) or []),
        },
        "adjacent_alarm_context_policy": device.get(
            "adjacent_alarm_context_policy", {}
        ),
        "adjacent_alarm_context": list(device.get("adjacent_alarm_context", []) or []),
    }


def _render_prompt(payload: Dict[str, Any]) -> str:
    device_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return _DEVICE_SUMMARY_PROMPT.format(device_json=device_json)


def build_per_device_prompt(
    device: Dict,
    *,
    max_chars: int = DEFAULT_SUMMARY_CONTEXT_MAX_CHARS,
) -> str:
    """Build one bounded prompt containing target and adjacent alarm facts."""
    payload = _summary_payload(device)
    prompt = _render_prompt(payload)
    if max_chars <= 0 or len(prompt) <= max_chars:
        return prompt

    payload["context_truncated"] = True
    adjacent = payload["adjacent_alarm_context"]
    # The evidence builder orders neighbors by selected alarm weight, so tail
    # removal preserves the highest-priority context first.
    while adjacent and len(_render_prompt(payload)) > max_chars:
        adjacent.pop()

    target = payload["target_device"]
    while target["alarms"] and len(_render_prompt(payload)) > max_chars:
        target["alarms"].pop()
    while target["alarm_events"] and len(_render_prompt(payload)) > max_chars:
        target["alarm_events"].pop()
    while target["high_weight_alarms"] and len(_render_prompt(payload)) > max_chars:
        target["high_weight_alarms"].pop()
    return _render_prompt(payload)


def _hybrid_device_record(device: Dict, semantic_summary: str) -> Dict:
    """Retain exact facts deterministically and attach model semantics."""
    topology = device.get("topology", {})
    if not isinstance(topology, dict):
        topology = {}
    return {
        "ip": device.get("ip"),
        "role": device.get("role", "UNKNOWN"),
        "cross": device.get("cross", 0),
        "alarm_count": device.get("alarm_count", 0),
        "alarms_exact": device.get("alarms", []),
        "alarm_events_exact": device.get("alarm_events", []),
        "high_weight_alarms": device.get("high_weight_alarms", []),
        "upstream": topology.get("upstream", []),
        "downstream": topology.get("downstream", []),
        "adjacent_alarm_context_policy": device.get(
            "adjacent_alarm_context_policy", {}
        ),
        "adjacent_alarm_context": device.get("adjacent_alarm_context", []),
        "semantic_summary": semantic_summary or "(semantic summary unavailable)",
    }


def _format_hybrid_summary(
    tasks: Sequence[tuple[int, Dict, str]],
    outputs: Sequence[str],
) -> str:
    records = []
    for index, (_device_index, device, _prompt) in enumerate(tasks):
        text = strip_reasoning_content(outputs[index]) if index < len(outputs) else ""
        records.append(_hybrid_device_record(device, text))
    if not records:
        return ""
    lines = [json.dumps(record, ensure_ascii=False, separators=(",", ":")) for record in records]
    return "Device evidence records (lossless facts + semantic annotation):\n" + "\n".join(lines)


def summarize_devices(
    devices_json: str,
    *,
    summarize_batch: Callable[[Sequence[str]], Sequence[str]],
    max_prompt_chars: int = DEFAULT_SUMMARY_CONTEXT_MAX_CHARS,
) -> str:
    """Summarize all candidate devices independently in one model batch."""
    try:
        wrapper = json.loads(devices_json)
        devices = wrapper.get("devices", []) if isinstance(wrapper, dict) else []
    except (json.JSONDecodeError, TypeError):
        return devices_json

    if not isinstance(devices, list) or not devices:
        return devices_json
    tasks = [
        (index, device, build_per_device_prompt(device, max_chars=max_prompt_chars))
        for index, device in enumerate(devices)
        if isinstance(device, dict)
    ]
    if not tasks:
        return devices_json

    outputs = [
        strip_reasoning_content(str(item)) if item else ""
        for item in summarize_batch([task[2] for task in tasks])
    ]
    return _format_hybrid_summary(tasks, outputs) or devices_json


def summarize_nodes_with(
    candidate_detail: str,
    *,
    summarize_batch: Callable[[Sequence[str]], Sequence[str]],
    max_prompt_chars: int = DEFAULT_SUMMARY_CONTEXT_MAX_CHARS,
) -> str:
    return summarize_devices(
        candidate_detail,
        summarize_batch=summarize_batch,
        max_prompt_chars=max_prompt_chars,
    )


class VllmNodeSummarizer:
    """One-shot local-vLLM wrapper for the small evidence summarizer."""

    def __init__(
        self,
        *,
        model_path: str,
        npu_cards: str,
        max_tokens: int = 512,
        temperature: float = 0.1,
        max_model_len: int = 2048,
        max_num_seqs: int = 8,
        kv_cache_memory_bytes: int | None = None,
        num_gpu_blocks_override: int | None = None,
    ) -> None:
        self.model_path = model_path
        self.npu_cards = npu_cards
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.max_model_len = max_model_len
        if max_num_seqs <= 0:
            raise ValueError("max_num_seqs must be positive")
        self.max_num_seqs = int(max_num_seqs)
        self.kv_cache_memory_bytes = kv_cache_memory_bytes
        self.num_gpu_blocks_override = num_gpu_blocks_override
        self.llm = None
        self.sampling_params = None

    def __enter__(self) -> "VllmNodeSummarizer":
        os.environ["ASCEND_RT_VISIBLE_DEVICES"] = self.npu_cards
        from vllm import LLM, SamplingParams
        from vllm.engine.arg_utils import EngineArgs

        llm_kwargs = {
            "model": self.model_path,
            "tensor_parallel_size": 1,
            "gpu_memory_utilization": 0.35,
            "max_model_len": self.max_model_len,
            "max_num_seqs": self.max_num_seqs,
            "trust_remote_code": True,
        }
        llm_kwargs.update(
            _cache_limit_kwargs(
                set(inspect.signature(EngineArgs).parameters),
                kv_cache_memory_bytes=self.kv_cache_memory_bytes,
                num_gpu_blocks_override=self.num_gpu_blocks_override,
            )
        )
        self.llm = LLM(**llm_kwargs)
        self.sampling_params = SamplingParams(
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            repetition_penalty=1.02,
        )
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.llm = None
        self.sampling_params = None
        gc.collect()

    def summarize_batch(self, prompts: Sequence[str]) -> List[str]:
        if self.llm is None or self.sampling_params is None:
            raise RuntimeError("VllmNodeSummarizer must be used as a context manager")
        applied_prompts = [[{"role": "user", "content": prompt}] for prompt in prompts]
        outputs = self.llm.chat(applied_prompts, self.sampling_params)
        return [strip_reasoning_content(item.outputs[0].text) for item in outputs]


class MultiCardSummarizer:
    """Compatibility wrapper that safely runs one summary engine per process."""

    def __init__(
        self,
        *,
        model_path: str,
        npu_cards: str,
        max_tokens: int = 512,
        max_model_len: int = 2048,
        max_num_seqs: int = 8,
        kv_cache_memory_bytes: int | None = None,
        num_gpu_blocks_override: int | None = None,
    ) -> None:
        cards = [card.strip() for card in npu_cards.split(",") if card.strip()]
        if len(cards) != 1:
            raise ValueError(
                "Summary precomputation requires exactly one NPU card per process; "
                "use --npu-cards 0."
            )
        self._summarizer = VllmNodeSummarizer(
            model_path=model_path,
            npu_cards=cards[0],
            max_tokens=max_tokens,
            max_model_len=max_model_len,
            max_num_seqs=max_num_seqs,
            kv_cache_memory_bytes=kv_cache_memory_bytes,
            num_gpu_blocks_override=num_gpu_blocks_override,
        )

    def __enter__(self) -> "MultiCardSummarizer":
        self._summarizer.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._summarizer.__exit__(exc_type, exc, tb)

    def summarize_devices(self, devices_json: str) -> str:
        return summarize_devices(
            devices_json,
            summarize_batch=self._summarizer.summarize_batch,
        )
