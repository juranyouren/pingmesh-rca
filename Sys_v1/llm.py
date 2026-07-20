from __future__ import annotations

import json
import os
import re
from typing import Any, Sequence


_JSON_BLOCK = re.compile(r"```json\s*(\{.*?\})\s*```", re.IGNORECASE | re.DOTALL)


def parse_llm_ranking(text: str) -> tuple[list[str], dict[str, Any]]:
    if not isinstance(text, str) or not text.strip():
        return [], {"parse_success": False, "reason": "empty_response"}
    candidates = list(reversed(_JSON_BLOCK.findall(text)))
    if not candidates:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            candidates = [text[start : end + 1]]
    for raw in candidates:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        ips = payload.get("ip", []) if isinstance(payload, dict) else []
        if isinstance(ips, str):
            ips = [ips]
        if isinstance(ips, list):
            clean = list(dict.fromkeys(ip for ip in ips if isinstance(ip, str) and ip))
            return clean, {"parse_success": True, "payload": payload}
    return [], {"parse_success": False, "reason": "invalid_json_or_ip_field"}


class LocalVllmReviewer:
    """Lazy local-vLLM reviewer. No external API is used."""

    def __init__(
        self,
        *,
        model_path: str,
        npu_cards: str,
        temperature: float = 0.1,
        max_tokens: int = 2048,
        max_model_len: int = 16384,
        gpu_memory_utilization: float = 0.85,
    ) -> None:
        self.model_path = model_path
        self.npu_cards = npu_cards
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.max_model_len = max_model_len
        self.gpu_memory_utilization = gpu_memory_utilization
        self._llm = None
        self._sampling_params = None

    def _ensure_loaded(self) -> None:
        if self._llm is not None:
            return
        os.environ.setdefault("VLLM_WORKER_MULTIPROC_METHOD", "spawn")
        os.environ.setdefault("OMP_NUM_THREADS", "1")
        os.environ["ASCEND_RT_VISIBLE_DEVICES"] = self.npu_cards
        from vllm import LLM, SamplingParams

        cards = [item.strip() for item in self.npu_cards.split(",") if item.strip()]
        self._llm = LLM(
            model=self.model_path,
            tensor_parallel_size=max(len(cards), 1),
            distributed_executor_backend="mp",
            gpu_memory_utilization=self.gpu_memory_utilization,
            max_model_len=self.max_model_len,
            trust_remote_code=True,
        )
        self._sampling_params = SamplingParams(
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            repetition_penalty=1.05,
            top_p=0.95,
        )

    def review_batch(self, prompts: Sequence[str], *, batch_size: int = 8) -> list[str]:
        if not prompts:
            return []
        self._ensure_loaded()
        outputs: list[str] = []
        for start in range(0, len(prompts), batch_size):
            batch = prompts[start : start + batch_size]
            chats = [[{"role": "user", "content": prompt}] for prompt in batch]
            generated = self._llm.chat(chats, self._sampling_params)
            outputs.extend(item.outputs[0].text for item in generated)
        return outputs
