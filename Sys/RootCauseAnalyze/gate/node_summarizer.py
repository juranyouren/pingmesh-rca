"""Device-state summarizer for evidence organization before LLM RCA.

Design (方案 A):
    Input is a single device dict (≈ 200–2000 chars), *not* the full devices list.
    The small model sees exactly one device at a time — no token overflow.
    Multiple VllmNodeSummarizer instances can be deployed in parallel across
    different NPU cards to process all devices in a case concurrently.
"""

from __future__ import annotations

import gc
import inspect
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Dict, List, Sequence


SUMMARY_PROMPT_VERSION = "device-state-summary-v2"

_REASONING_BLOCK = re.compile(
    r"<(?:think|analysis)\b[^>]*>.*?</(?:think|analysis)\s*>",
    re.IGNORECASE | re.DOTALL,
)
_UNCLOSED_REASONING_BLOCK = re.compile(
    r"<(?:think|analysis)\b[^>]*>.*\Z",
    re.IGNORECASE | re.DOTALL,
)


def strip_reasoning_content(text: str) -> str:
    """Remove hidden chain-of-thought blocks from a summary-model response.

    DeepSeek-style models may return ``<think>...</think>`` in ``text`` rather
    than a separate reasoning field.  Cache files and the main RCA prompt must
    contain only the final device-state summary.
    """
    if not isinstance(text, str):
        return ""
    cleaned = _REASONING_BLOCK.sub("", text)
    cleaned = _UNCLOSED_REASONING_BLOCK.sub("", cleaned)
    return cleaned.strip()


def _parse_npu_cards(npu_spec: str) -> list:
    """Parse ``"0,1"`` style NPU card strings into int list."""
    if not isinstance(npu_spec, str) or not npu_spec.strip():
        return []
    cards = []
    for part in npu_spec.split(","):
        part = part.strip()
        if part.isdigit():
            cards.append(int(part))
    return cards


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


# ── per-device prompt ─────────────────────────────────────────────────

_DEVICE_SUMMARY_PROMPT = (
    "你是网络设备状态证据压缩器，不是根因分析器。\n"
    "请仅根据输入字段，客观描述这一台设备的可观测状态。保留 IP，描述设备角色、"
    "cross 数、告警数量、告警名称、高权重告警和拓扑邻接；高权重仅表示规则权重，"
    "不表示已确认因果关系；字段缺失时不要补全。\n"
    "禁止判断该设备是否为根因、症状设备或可疑设备；禁止给出因果解释、排名、"
    "诊断结论、置信度或处置建议；禁止编造输入中不存在的事实。\n"
    "输出 1-3 句简洁中文事实描述。\n\n"
    "Device JSON:\n"
    "{device_json}\n"
)


def build_per_device_prompt(device: Dict) -> str:
    """Build a tiny prompt for ONE device. Expected input chars: 200–2000."""
    device_json = json.dumps(device, ensure_ascii=False, indent=2)
    return _DEVICE_SUMMARY_PROMPT.format(device_json=device_json)


# ── batch helpers ─────────────────────────────────────────────────────


def summarize_devices(
    devices_json: str,
    *,
    summarize_batch: Callable[[Sequence[str]], Sequence[str]],
) -> str:
    """Summarize all devices in *devices_json* one at a time.

    *devices_json* is the ``{"devices": [...]}`` string produced by
    ``build_fused_evidence``.  Each device is summarised independently,
    then results are concatenated.
    """
    try:
        wrapper = json.loads(devices_json)
        devices = wrapper.get("devices", []) if isinstance(wrapper, dict) else []
    except (json.JSONDecodeError, TypeError):
        return devices_json  # can't parse — pass through

    if not isinstance(devices, list) or not devices:
        return devices_json

    prompts = [build_per_device_prompt(d) for d in devices if isinstance(d, dict)]
    if not prompts:
        return devices_json

    outputs = [
        strip_reasoning_content(str(item)) if item else ""
        for item in summarize_batch(prompts)
    ]
    parts: List[str] = []
    for i, out in enumerate(outputs):
        ip = (
            devices[i].get("ip", f"device_{i}")
            if i < len(devices) and isinstance(devices[i], dict)
            else f"device_{i}"
        )
        text = strip_reasoning_content(str(out)) if out else ""
        if text:
            parts.append(f"- {ip}: {text}")
        else:
            parts.append(f"- {ip}: (summary unavailable)")

    if parts:
        return "Device state summaries:\n" + "\n".join(parts)
    return devices_json


def summarize_nodes_with(
    candidate_detail: str,
    *,
    summarize_batch: Callable[[Sequence[str]], Sequence[str]],
) -> str:
    """Entry point compatible with the existing call signature."""
    return summarize_devices(candidate_detail, summarize_batch=summarize_batch)


# ── vLLM wrapper ──────────────────────────────────────────────────────


class VllmNodeSummarizer:
    """One-shot vLLM wrapper for the small candidate-node summarizer model."""

    def __init__(
        self,
        *,
        model_path: str,
        npu_cards: str,
        max_tokens: int = 512,
        temperature: float = 0.1,
        max_model_len: int = 2048,
        kv_cache_memory_bytes: int | None = None,
        num_gpu_blocks_override: int | None = None,
    ) -> None:
        self.model_path = model_path
        self.npu_cards = npu_cards
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.max_model_len = max_model_len
        self.kv_cache_memory_bytes = kv_cache_memory_bytes
        self.num_gpu_blocks_override = num_gpu_blocks_override
        self.llm = None
        self.sampling_params = None

    def __enter__(self) -> "VllmNodeSummarizer":
        os.environ["ASCEND_RT_VISIBLE_DEVICES"] = self.npu_cards

        from vllm import LLM, SamplingParams
        from vllm.engine.arg_utils import EngineArgs

        llm_kwargs = dict(
            model=self.model_path,
            tensor_parallel_size=1,
            gpu_memory_utilization=0.35,
            max_model_len=self.max_model_len,
            max_num_seqs=1,
            trust_remote_code=True,
        )
        # Some vLLM-Ascend releases size the NPU KV cache too aggressively even
        # when gpu_memory_utilization is low. Use a byte cap when available, or
        # the older block-count cap for the one-device-at-a-time summarizer.
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
        applied_prompts = [[{"role": "user", "content": p}] for p in prompts]
        outputs = self.llm.chat(applied_prompts, self.sampling_params)
        return [strip_reasoning_content(item.outputs[0].text) for item in outputs]


# ── parallel pool ─────────────────────────────────────────────────────


class MultiCardSummarizer:
    """Run the summary model on one NPU in the current process.

    The historical multi-card implementation changed
    ``ASCEND_RT_VISIBLE_DEVICES`` after the NPU runtime had already initialized.
    vLLM engines must instead be isolated in separate processes. Until that
    process-level scheduler exists, fail fast on multi-card configurations.
    """

    def __init__(
        self,
        *,
        model_path: str,
        npu_cards: str,  # comma-separated, e.g. "4,5,6,7"
        max_tokens: int = 512,
        max_model_len: int = 2048,
        kv_cache_memory_bytes: int | None = None,
        num_gpu_blocks_override: int | None = None,
    ) -> None:
        self.model_path = model_path
        card_list = [c.strip() for c in npu_cards.split(",") if c.strip()]
        if len(card_list) != 1:
            raise ValueError(
                "Summary precomputation currently requires exactly one NPU card; "
                "use --npu-cards 0 (multi-card engines need process isolation)."
            )
        self.cards = card_list
        self.max_tokens = max_tokens
        self.max_model_len = max_model_len
        self.kv_cache_memory_bytes = kv_cache_memory_bytes
        self.num_gpu_blocks_override = num_gpu_blocks_override
        self._summarizers: List[VllmNodeSummarizer] = []

    def __enter__(self) -> "MultiCardSummarizer":
        for card in self.cards:
            s = VllmNodeSummarizer(
                model_path=self.model_path,
                npu_cards=card,
                max_tokens=self.max_tokens,
                max_model_len=self.max_model_len,
                kv_cache_memory_bytes=self.kv_cache_memory_bytes,
                num_gpu_blocks_override=self.num_gpu_blocks_override,
            )
            s.__enter__()
            self._summarizers.append(s)
        print(f"[MultiCardSummarizer] {len(self._summarizers)} instances on cards {self.cards}")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        for s in self._summarizers:
            try:
                s.__exit__(exc_type, exc, tb)
            except Exception:
                pass
        self._summarizers.clear()

    def summarize_devices(self, devices_json: str) -> str:
        """Summarize all devices, distributing prompts across cards."""
        try:
            wrapper = json.loads(devices_json)
            devices = wrapper.get("devices", []) if isinstance(wrapper, dict) else []
        except (json.JSONDecodeError, TypeError):
            return devices_json

        if not isinstance(devices, list) or not devices:
            return devices_json

        # Build (device_index, prompt) pairs
        tasks: List[tuple] = []
        for i, d in enumerate(devices):
            if isinstance(d, dict):
                tasks.append((i, d, build_per_device_prompt(d)))

        if not tasks:
            return devices_json

        # Distribute tasks round-robin across summarizers
        n = len(self._summarizers)
        if n <= 1:
            # Single card — batch all prompts at once
            prompts = [t[2] for t in tasks]
            outputs = list(self._summarizers[0].summarize_batch(prompts))
        else:
            # Multi-card — process in parallel via threads
            card_batches: List[List[tuple]] = [[] for _ in range(n)]
            for idx, task in enumerate(tasks):
                card_batches[idx % n].append(task)

            all_results: Dict[int, str] = {}

            def _run_card(card_idx: int, batch: List[tuple]) -> List[tuple]:
                if not batch:
                    return []
                prompts = [t[2] for t in batch]
                outputs = list(
                    self._summarizers[card_idx].summarize_batch(prompts)
                )
                return [(batch[j][0], str(outputs[j]).strip()) for j in range(len(batch))]

            with ThreadPoolExecutor(max_workers=n) as pool:
                futures = {
                    pool.submit(_run_card, ci, cb): ci
                    for ci, cb in enumerate(card_batches)
                    if cb
                }
                for fut in as_completed(futures):
                    for dev_idx, summary_text in fut.result():
                        all_results[dev_idx] = summary_text

            outputs = [
                all_results.get(t[0], "") for t in tasks
            ]

        # Build combined summary
        parts: List[str] = []
        for i, out in enumerate(outputs):
            ip = (
                devices[tasks[i][0]].get("ip", f"device_{i}")
                if tasks[i][0] < len(devices)
                else f"device_{i}"
            )
            text = strip_reasoning_content(out) if out else ""
            parts.append(f"- {ip}: {text}" if text else f"- {ip}: (summary unavailable)")

        return "Device state summaries:\n" + "\n".join(parts) if parts else devices_json
