"""Multi-model fallback manager for OpenRouter and Gemini.

Provides automated failover across top free models so that if one
model hits a rate limit (429), provider outage (503), or timeout,
the system transparently falls back to the next model in sequence
without user-facing errors.
"""

from __future__ import annotations

import os
import logging
import threading
from typing import Any, List, Optional

from crewai import LLM
from crewai.llms.base_llm import BaseLLM

logger = logging.getLogger(__name__)

def get_openrouter_key() -> str:
    """Retrieve OpenRouter API key supporting both naming conventions."""
    return os.getenv("OPENROUTER_API_KEY") or os.getenv("OPEN_ROUTER_API_KEY") or ""

def get_gemini_key() -> str:
    """Retrieve Gemini API key."""
    return os.getenv("GEMINI_API_KEY") or ""

# Curated list of high-capability free models on OpenRouter
OPENROUTER_FREE_MODELS = [
    "openrouter/nvidia/nemotron-3.5-lightning:free",       # 1M context, fast & reliable
    "openrouter/nvidia/nemotron-3-ultra-550b-a55b:free",    # 550B flagship, deep writing & analysis
    "openrouter/nvidia/nemotron-3.5-super-vl:free",         # 1M context, robust
    "openrouter/dots-studio/dots-3-note-preview:free",      # 512k context, great synthesis
    "openrouter/cohere/north-mini-code:free",               # 256k context, structured output
    "openrouter/nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free", # Fast reasoning
    "openrouter/google/gemma-4-31b-it:free",                # 262k context, Google Gemma 4 31B
]

# Verified Google Gemini models (1,500 requests/day free tier on Google AI Studio)
GEMINI_MODELS = [
    "gemini/gemini-3.5-flash",
    "gemini/gemini-3.5-flash-lite",
    "gemini/gemini-3.8-flash",
]

def get_available_model_sequence() -> List[str]:
    """Build the fallback sequence, prioritizing high-quota Gemini first, then OpenRouter."""
    seq: List[str] = []
    
    gemini_key = get_gemini_key()
    or_key = get_openrouter_key()

    # Prioritize Google Gemini first (1,500 req/day free vs OpenRouter 50 req/day)
    if gemini_key:
        os.environ["GEMINI_API_KEY"] = gemini_key
        seq.extend(GEMINI_MODELS)

    if or_key:
        os.environ["OPENROUTER_API_KEY"] = or_key
        os.environ["OPEN_ROUTER_API_KEY"] = or_key
        seq.extend(OPENROUTER_FREE_MODELS)

    if not seq:
        seq.extend(GEMINI_MODELS)
        seq.extend(OPENROUTER_FREE_MODELS)

    return seq


class FallbackLLM(BaseLLM):
    """CrewAI-compatible LLM with transparent multi-model failover."""

    models: List[str] = []

    def __init__(self, models: Optional[List[str]] = None, **kwargs: Any):
        model_list = models or get_available_model_sequence()
        if not model_list:
            raise ValueError("Model fallback list cannot be empty.")
        super().__init__(model=model_list[0], **kwargs)
        self.models = model_list
        self._llm_instances = {}
        self._lock = threading.Lock()

    def _get_instance(self, model_name: str) -> Any:
        with self._lock:
            if model_name not in self._llm_instances:
                self._llm_instances[model_name] = LLM(model=model_name)
            return self._llm_instances[model_name]

    def call(self, messages: Any, callbacks: Any = None, **kwargs: Any) -> str:
        """Call models sequentially until one succeeds, with deterministic hybrid caching."""
        raw_temp = kwargs.get("temperature")
        if raw_temp is None:
            raw_temp = getattr(self, "temperature", None)
        if raw_temp is None:
            raw_temp = 0.7
        temperature = float(raw_temp)
        bypass_cache = bool(kwargs.get("bypass_cache", False))
        user_id = kwargs.get("user_id")

        def _execute_network_call() -> str:
            last_error = None
            skip_openrouter = False
            for model_name in self.models:
                if skip_openrouter and model_name.startswith("openrouter/"):
                    continue
                try:
                    inst = self._get_instance(model_name)
                    result = inst.call(messages=messages, callbacks=callbacks, **kwargs)
                    return str(result)
                except Exception as e:
                    err_lower = str(e).lower()
                    print(
                        f"⚠️ [FallbackLLM] Model '{model_name}' failed ({e}). "
                        f"Automatically switching to next fallback..."
                    )
                    last_error = e
                    if model_name.startswith("openrouter/") and ("free-models-per-day" in err_lower or "rate limit exceeded" in err_lower):
                        skip_openrouter = True
                        print("⚠️ [FallbackLLM] OpenRouter account hit daily 50 request quota. Switching directly to Gemini models...")

            raise RuntimeError(
                f"All models in the fallback sequence failed. Last error: {last_error}"
            )

        # Only memoize deterministic calls (temperature <= 0.2)
        if temperature <= 0.2:
            try:
                from cache import HybridCacheManager, make_cache_key
                cache_key = make_cache_key(
                    "llm_eval",
                    self.models[0] if self.models else "default",
                    messages,
                    temperature,
                    user_id=user_id,
                )
                mgr = HybridCacheManager.get_instance()
                res, _ = mgr.fetch_or_compute(
                    key=cache_key,
                    namespace="llm_eval",
                    fetch_fn=_execute_network_call,
                    ttl_seconds=7 * 24 * 3600,
                    user_id=user_id,
                    bypass=bypass_cache,
                    allow_stale_on_error=True,
                )
                return res
            except Exception as e:
                logger.debug(f"LLM cache bypassed due to error: {e}")

        return _execute_network_call()

    def supports_stop_words(self) -> bool:
        return True

    def get_context_window_size(self) -> int:
        return 128000


def get_fallback_llm() -> FallbackLLM:
    """Convenience factory returning a configured FallbackLLM."""
    return FallbackLLM()
