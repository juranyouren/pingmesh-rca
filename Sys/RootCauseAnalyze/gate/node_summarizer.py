from __future__ import annotations

import gc
import os
from typing import Callable, List, Sequence


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


SUMMARY_SYSTEM_INSTRUCTION = """You are a network RCA evidence compressor.
Summarize candidate device evidence for a downstream root-cause LLM.
Keep all IP addresses, preserve discriminative alarms, topology proximity,
cross counts, and high-severity alarm hits. Do not invent devices or alarms.
Return concise Chinese bullet points grouped by device."""


def build_candidate_summary_prompt(candidate_detail: str) -> str:
    return (
        f"{SUMMARY_SYSTEM_INSTRUCTION}\n\n"
        "Input is JSON with candidate devices. For each device, summarize:\n"
        "- IP, role, cross\n"
        "- alarm_count, alarms, high_severity_alarms\n"
        "- upstream/downstream topology hints\n"
        "- why this device may be root cause or downstream symptom\n\n"
        "JSON:\n"
        f"{candidate_detail}\n"
    )


def summarize_nodes_with(
    candidate_detail: str,
    *,
    summarize_batch: Callable[[Sequence[str]], Sequence[str]],
) -> str:
    prompt = build_candidate_summary_prompt(candidate_detail)
    outputs = list(summarize_batch([prompt]))
    if not outputs:
        return candidate_detail
    summary = str(outputs[0]).strip()
    return summary or candidate_detail


class VllmNodeSummarizer:
    """One-shot vLLM wrapper for the small candidate-node summarizer model."""

    def __init__(
        self,
        *,
        model_path: str,
        npu_cards: str,
        max_tokens: int = 1024,
        temperature: float = 0.1,
        tensor_parallel_size: int = 1,
        max_model_len: int = 8192,
    ) -> None:
        self.model_path = model_path
        self.npu_cards = npu_cards
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.tensor_parallel_size = tensor_parallel_size
        self.max_model_len = max_model_len
        self.llm = None
        self.sampling_params = None

    def __enter__(self) -> "VllmNodeSummarizer":
        os.environ["ASCEND_RT_VISIBLE_DEVICES"] = self.npu_cards

        # The summary model is small (tensor_parallel_size=1), so we only
        # need a minimal amount of free memory.  Don't wait aggressively —
        # we expect it to share a card with the main RCA model.
        card_ids = _parse_npu_cards(self.npu_cards)
        if card_ids:
            from Sys.utils.npu_utils import wait_npu_memory
            wait_npu_memory(card_ids, required_free_ratio=0.05, timeout=60.0, poll_interval=5.0)

        from vllm import LLM, SamplingParams

        self.llm = LLM(
            model=self.model_path,
            tensor_parallel_size=self.tensor_parallel_size,
            gpu_memory_utilization=0.70,
            max_model_len=self.max_model_len,
            trust_remote_code=True,
        )
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
        return [item.outputs[0].text for item in outputs]
