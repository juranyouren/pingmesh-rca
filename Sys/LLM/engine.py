from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path


class ContextBudgetError(ValueError):
    pass


class EngineStats:
    """Inference accounting accumulated over the life of one engine.

    Counters are process-wide because the engine is shared. A caller that needs
    a per-incident view snapshots this before and after its own work.
    """

    _FIELDS = ("calls", "errors", "budget_rejections", "length_truncations",
               "wall_seconds", "generate_seconds", "prompt_tokens", "output_tokens")

    def __init__(self):
        self._values = dict.fromkeys(self._FIELDS, 0)
        self._lock = threading.Lock()

    def add(self, **deltas):
        with self._lock:
            for name, value in deltas.items():
                self._values[name] += value

    def snapshot(self):
        with self._lock:
            return dict(self._values)


def parse_json(text):
    # DeepSeek may emit reasoning before the final JSON.
    text = text.rsplit("</think>", 1)[-1].strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")
    return value


class NpuEngine:
    """One local vLLM/Ascend engine; imports occur only at server startup."""

    def __init__(self):
        model = os.environ.get("PINGMESH_MODEL_PATH", "/usr/share/large_language_models/DeepSeek-R1-Distill-Qwen-32B")
        if not Path(model).is_dir():
            raise ValueError(f"Local model directory does not exist: {model}")
        cards = os.environ.get("PINGMESH_NPU_CARDS", "0").split(",")
        cards = [c.strip() for c in cards if c.strip()]
        if not cards or len(set(cards)) != len(cards) or not all(c.isdigit() for c in cards):
            raise ValueError("PINGMESH_NPU_CARDS must contain distinct numeric card IDs")
        os.environ["ASCEND_RT_VISIBLE_DEVICES"] = ",".join(cards)
        from vllm import LLM, SamplingParams

        self.max_model_len = int(os.environ.get("PINGMESH_MAX_MODEL_LEN", "16384"))
        self.max_tokens = int(os.environ.get("PINGMESH_MAX_TOKENS", "4096"))
        if not 0 < self.max_tokens < self.max_model_len:
            raise ValueError("Require 0 < PINGMESH_MAX_TOKENS < PINGMESH_MAX_MODEL_LEN")
        self.model_path = model
        self.llm = LLM(model=model, tensor_parallel_size=len(cards),
                       max_model_len=self.max_model_len, trust_remote_code=True,
                       gpu_memory_utilization=float(os.environ.get("PINGMESH_LLM_MEMORY_UTILIZATION", "0.85")))
        self.tokenizer = self.llm.get_tokenizer()
        self.params = SamplingParams(temperature=0.0, max_tokens=self.max_tokens)
        self._lock = threading.Lock()
        self.stats = EngineStats()

    def _format(self, prompt):
        messages = [{"role": "user", "content": prompt}]
        if getattr(self.tokenizer, "chat_template", None):
            return self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        # Qwen2.5-0.5B is a base model, not necessarily an instruct model.
        return prompt + "\nJSON response:\n"

    def _output_tokens(self, output):
        """vLLM reports token ids; fall back to counting only if it does not."""
        try:
            token_ids = getattr(output, "token_ids", None)
            if token_ids:
                return len(token_ids)
            return len(self.tokenizer.encode(getattr(output, "text", "") or ""))
        except Exception:
            return 0

    def generate_json(self, prompt):
        started = time.perf_counter()
        self.stats.add(calls=1)
        try:
            formatted = self._format(prompt)
            prompt_tokens = len(self.tokenizer.encode(formatted))
            if prompt_tokens + self.max_tokens > self.max_model_len:
                self.stats.add(budget_rejections=1)
                raise ContextBudgetError("Prompt exceeds context budget; no records were truncated")
            generate_started = time.perf_counter()
            with self._lock:
                result = self.llm.generate([formatted], self.params, use_tqdm=False)
            generate_seconds = time.perf_counter() - generate_started
            if not result or not result[0].outputs:
                raise ValueError("Empty model response")
            output = result[0].outputs[0]
            self.stats.add(generate_seconds=generate_seconds, prompt_tokens=prompt_tokens,
                           output_tokens=self._output_tokens(output),
                           length_truncations=1 if getattr(output, "finish_reason", None) == "length" else 0)
            return parse_json(output.text)
        except ContextBudgetError:
            # A budget rejection is an expected routing decision, not an inference failure.
            raise
        except Exception:
            self.stats.add(errors=1)
            raise
        finally:
            self.stats.add(wall_seconds=time.perf_counter() - started)


_engine = None
_engine_lock = threading.Lock()


def get_shared_engine():
    """Initialize once per process; all agents should receive this same object."""
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = NpuEngine()
        return _engine
