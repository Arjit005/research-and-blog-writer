"""Multi-model fallback manager for OpenRouter and Gemini.

Provides automated failover across top free models so that if one
model hits a rate limit (429), provider outage (503), or timeout,
the system transparently falls back to the next model in sequence
without user-facing errors.

Reliability features
--------------------
* Error classification (``rate_limit`` / ``timeout`` / ``auth`` /
  ``config`` / ``other``) so retry decisions are explicit rather than
  a single generic ``except``.
* Exponential backoff between failed candidates with a hard cap
  (``LLM_BACKOFF_BASE_SECONDS`` / ``LLM_BACKOFF_CAP_SECONDS``) that
  also honors an upstream ``Retry-After`` hint when one is exposed by
  the provider exception.
* Per-call timeout (``LLM_CALL_TIMEOUT``, default 120s) applied to the
  underlying ``crewai.LLM`` instances.
* Fail-fast when the *default* fallback chain is requested but no LLM
  API key is configured, instead of firing one doomed request per model.
* Thread-safe, module-level usage accounting exposed through
  :func:`reset_usage_stats` / :func:`get_usage_stats`.  The backend
  (``backend/routes/research.py``) consumes those two functions to
  record real model usage and fallback telemetry.

Runtime-scoped API keys
-----------------------
:func:`scoped_llm_keys` stores visitor-supplied keys in a
:mod:`contextvars` context instead of mutating process-wide
``os.environ``.  This lets the legacy Streamlit UI accept an optional
user key for a single run without leaking or overriding the operator's
server-side credentials for every other visitor.
"""

from __future__ import annotations

import contextvars
import logging
import os
import re
import socket
import threading
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional

from crewai import LLM
from crewai.llms.base_llm import BaseLLM
from pydantic import PrivateAttr

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration (all overridable through environment variables)
# ---------------------------------------------------------------------------
DEFAULT_CALL_TIMEOUT_SECONDS = 120.0
DEFAULT_BACKOFF_BASE_SECONDS = 1.0
DEFAULT_BACKOFF_CAP_SECONDS = 8.0


def _env_float(name: str, default: float) -> float:
    """Read a float environment variable, ignoring malformed values."""
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        logger.warning("Ignoring invalid %s=%r (expected a number)", name, raw)
        return default


# ---------------------------------------------------------------------------
# Runtime-scoped API keys (never mutate os.environ from request handlers)
# ---------------------------------------------------------------------------
_RUNTIME_OPENROUTER_KEY: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "runtime_openrouter_key", default=None
)
_RUNTIME_GEMINI_KEY: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "runtime_gemini_key", default=None
)
_RUNTIME_BEATAPI_KEY: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "runtime_beatapi_key", default=None
)


def get_openrouter_key() -> str:
    """Retrieve the OpenRouter API key, preferring a runtime-scoped key."""
    return (
        _RUNTIME_OPENROUTER_KEY.get()
        or os.getenv("OPENROUTER_API_KEY")
        or os.getenv("OPEN_ROUTER_API_KEY")
        or ""
    )


def get_gemini_key() -> str:
    """Retrieve the Gemini API key, preferring a runtime-scoped key."""
    return _RUNTIME_GEMINI_KEY.get() or os.getenv("GEMINI_API_KEY") or ""


def get_beatapi_key() -> str:
    """Retrieve the BeatAPI key, preferring a runtime-scoped key."""
    return (
        _RUNTIME_BEATAPI_KEY.get()
        or os.getenv("BEATAPI_KEY")
        or os.getenv("BEAT_API_KEY")
        or ""
    )


@contextmanager
def scoped_llm_keys(
    openrouter_key: Optional[str] = None,
    gemini_key: Optional[str] = None,
    beatapi_key: Optional[str] = None,
) -> Iterator[None]:
    """Temporarily expose caller-supplied LLM keys to the current context only.

    Unlike writing to ``os.environ`` this is thread-safe, isolated to the current
    asynchronous/thread context via ContextVars, and reset as soon as the ``with``
    block exits so multi-tenant requests cannot leak API keys.
    """
    tokens = []
    try:
        if openrouter_key:
            tokens.append((_RUNTIME_OPENROUTER_KEY, _RUNTIME_OPENROUTER_KEY.set(str(openrouter_key))))
        if gemini_key:
            tokens.append((_RUNTIME_GEMINI_KEY, _RUNTIME_GEMINI_KEY.set(str(gemini_key))))
        if beatapi_key:
            tokens.append((_RUNTIME_BEATAPI_KEY, _RUNTIME_BEATAPI_KEY.set(str(beatapi_key))))
        yield
    finally:
        for var, token in reversed(tokens):
            var.reset(token)


def has_llm_key() -> bool:
    """Return True when at least one supported LLM provider key is configured."""
    return bool(get_openrouter_key() or get_gemini_key() or get_beatapi_key())


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

# Verified Google Gemini models (1,500 requests/day free tier on Google AI Studio).
# Model names match the LiteLLM / CrewAI identifier format: "gemini/<model-id>".
# Ordered with verified active 2026 models first so the most capable available model is tried first.
GEMINI_MODELS = [
    "gemini/gemini-3.5-flash",       # Gemini 3.5 Flash — current primary fast flagship
    "gemini/gemini-3.5-flash-lite",  # Gemini 3.5 Flash-Lite — ultra-fast, high quota
    "gemini/gemini-3.8-flash",       # Gemini 3.8 Flash fallback
    "gemini/gemini-2.5-flash",       # Gemini 2.5 Flash fallback
    "gemini/gemini-2.5-flash-lite",  # Gemini 2.5 Flash-Lite fallback
]

# BeatAPI free models (OpenAI-compatible endpoints at https://api.beatapi.io/v1)
BEATAPI_FREE_MODELS = [
    "beatapi/glm-5.3-flash-free",         # High performance GLM free model
    "beatapi/deepseek-v4.1-flash-free",    # DeepSeek V4.1 free model
    "beatapi/hy4-free",                    # Tencent Hunyuan free model
]


def get_available_model_sequence() -> List[str]:
    """Build the fallback sequence, prioritizing Gemini first, then BeatAPI, then OpenRouter."""
    seq: List[str] = []

    gemini_key = get_gemini_key()
    beatapi_key = get_beatapi_key()
    or_key = get_openrouter_key()

    # 1. Prioritize Google Gemini first (1,500 req/day free vs OpenRouter 50 req/day)
    if gemini_key:
        seq.extend(GEMINI_MODELS)

    # 2. Next, BeatAPI free models
    if beatapi_key:
        seq.extend(BEATAPI_FREE_MODELS)

    # 3. Next, OpenRouter free models
    if or_key:
        seq.extend(OPENROUTER_FREE_MODELS)

    if not seq:
        # No key configured: keep the candidate list intact so the tool schema /
        # construction path still works, but ``FallbackLLM.call`` fails fast and
        # never fires a doomed request for each entry.
        seq.extend(GEMINI_MODELS)
        seq.extend(BEATAPI_FREE_MODELS)
        seq.extend(OPENROUTER_FREE_MODELS)

    return seq


# ---------------------------------------------------------------------------
# Per-run usage accounting via ContextVars (safe for multi-tenant concurrent runs)
#
# Previously a single module-level dict was shared across all threads, meaning
# reset_usage_stats() called for one user's run wiped stats for every concurrent
# run. Now each thread/context gets its own isolated stats bucket.
# ---------------------------------------------------------------------------

class _RunStats:
    """Isolated stats bucket for a single research run."""
    __slots__ = ("models_used", "failed_models", "fallback_events", "call_count", "_lock")

    def __init__(self) -> None:
        self.models_used: List[str] = []
        self.failed_models: List[str] = []
        self.fallback_events: List[Dict[str, Any]] = []
        self.call_count: int = 0
        self._lock = threading.Lock()

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "models_used": list(self.models_used),
                "failed_models": list(self.failed_models),
                "fallback_events": [dict(e) for e in self.fallback_events],
                "call_count": self.call_count,
            }


# ContextVar holds the stats bucket for the current thread/async context.
# The global fallback is used by code paths that have not called reset_usage_stats()
# (e.g. tests, the legacy Streamlit app) so they keep working unchanged.
_GLOBAL_STATS = _RunStats()
_CURRENT_RUN_STATS: contextvars.ContextVar[_RunStats] = contextvars.ContextVar(
    "current_run_stats", default=_GLOBAL_STATS
)


def _current_stats() -> _RunStats:
    return _CURRENT_RUN_STATS.get()


def reset_usage_stats() -> None:
    """Install a fresh, isolated stats bucket for the current context (thread-safe).

    Call this at the start of each research run. Each concurrent run gets its own
    bucket so stats from one run can never bleed into another.
    """
    _CURRENT_RUN_STATS.set(_RunStats())


def get_usage_stats() -> Dict[str, Any]:
    """Return a defensive snapshot of the current context's LLM usage counters.

    Returns:
        dict with exactly these keys::

            {
                "models_used": list[str],      # models that actually produced output
                "failed_models": list[str],    # models that raised an error
                "fallback_events": list[dict], # keys: failed_model, switched_to, error_type
                "call_count": int,             # underlying model invocation attempts
            }
    """
    return _current_stats().snapshot()


def _track_call_attempt() -> None:
    s = _current_stats()
    with s._lock:
        s.call_count += 1


def _track_model_success(model_name: str) -> None:
    s = _current_stats()
    with s._lock:
        if model_name not in s.models_used:
            s.models_used.append(model_name)


def _track_model_failure(model_name: str) -> None:
    s = _current_stats()
    with s._lock:
        if model_name not in s.failed_models:
            s.failed_models.append(model_name)


def _track_fallback(failed_model: str, switched_to: str, error_type: str) -> None:
    s = _current_stats()
    with s._lock:
        s.fallback_events.append({
            "failed_model": failed_model,
            "switched_to": switched_to,
            "error_type": error_type,
        })


# ---------------------------------------------------------------------------
# Error classification, Retry-After parsing, and backoff
# ---------------------------------------------------------------------------
_RATE_LIMIT_MARKERS = (
    "429",
    "rate limit",
    "rate-limit",
    "ratelimit",
    "too many requests",
    "free-models-per-day",
    "quota exceeded",
    "quota_exceeded",
    "resource_exhausted",
    "resource exhausted",
    "daily limit",
    "insufficient_quota",
)
_AUTH_MARKERS = (
    "401",
    "403",
    "unauthorized",
    "invalid api key",
    "invalid_api_key",
    "incorrect api key",
    "authentication",
    "api key not valid",
    "permission denied",
    "no auth credentials",
)
_TIMEOUT_MARKERS = (
    "timeout",
    "timed out",
    "time out",
    "deadline exceeded",
    "read timeout",
    "connect timeout",
)
_CONFIG_MARKERS = (
    "404",
    "model not found",
    "model_not_found",
    "not a valid model",
    "invalid model",
    "does not exist",
    "unsupported model",
    "no such model",
)


def _status_code(error: BaseException) -> Optional[int]:
    """Best-effort extraction of an HTTP status code from a provider exception."""
    for attr in ("status_code", "status", "http_status", "code"):
        value = getattr(error, attr, None)
        if isinstance(value, int):
            return value
    response = getattr(error, "response", None)
    if response is not None:
        value = getattr(response, "status_code", None)
        if isinstance(value, int):
            return value
    match = re.search(r"\b(4\d{2}|5\d{2})\b", str(error))
    return int(match.group(1)) if match else None


def classify_error(error: BaseException) -> str:
    """Classify a provider/network exception into a stable error category.

    Returns one of ``"rate_limit"``, ``"timeout"``, ``"auth"``, ``"config"``,
    or ``"other"``.  Categories are strings (never exception instances) so they
    can be logged, persisted, and returned to API clients safely.
    """
    if isinstance(error, (TimeoutError, socket.timeout)):
        return "timeout"

    status = _status_code(error)
    if status == 429:
        return "rate_limit"
    if status in (401, 403):
        return "auth"
    if status == 408:
        return "timeout"
    if status in (400, 404):
        return "config"

    text = f"{type(error).__name__}: {error}".lower()
    if any(marker in text for marker in _RATE_LIMIT_MARKERS):
        return "rate_limit"
    if any(marker in text for marker in _TIMEOUT_MARKERS):
        return "timeout"
    if any(marker in text for marker in _AUTH_MARKERS):
        return "auth"
    if any(marker in text for marker in _CONFIG_MARKERS):
        return "config"
    return "other"


def _retry_after_seconds(error: BaseException) -> Optional[float]:
    """Extract a ``Retry-After`` hint (seconds) from a provider exception if present."""
    candidates: List[str] = []

    response = getattr(error, "response", None)
    headers = getattr(response, "headers", None) or getattr(error, "headers", None)
    if headers is not None:
        try:
            value = headers.get("Retry-After") or headers.get("retry-after")
        except Exception:
            value = None
        if value is not None:
            candidates.append(str(value))

    for attr in ("retry_after", "retry_after_seconds"):
        value = getattr(error, attr, None)
        if value is not None:
            candidates.append(str(value))

    match = re.search(r"retry[\s_-]*after[\s:=]*([0-9]+(?:\.[0-9]+)?)", str(error), re.IGNORECASE)
    if match:
        candidates.append(match.group(1))

    for candidate in candidates:
        try:
            return max(0.0, float(candidate))
        except (TypeError, ValueError):
            # Some providers use an HTTP-date for Retry-After.
            try:
                import datetime
                from email.utils import parsedate_to_datetime

                retry_at = parsedate_to_datetime(candidate)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=datetime.timezone.utc)
                delta = retry_at - datetime.datetime.now(datetime.timezone.utc)
                return max(0.0, delta.total_seconds())
            except Exception:
                continue
    return None


def _backoff_delay(attempt_index: int, error: BaseException) -> float:
    """Compute exponential backoff for ``attempt_index`` (1-based), honoring Retry-After."""
    base = _env_float("LLM_BACKOFF_BASE_SECONDS", DEFAULT_BACKOFF_BASE_SECONDS)
    cap = _env_float("LLM_BACKOFF_CAP_SECONDS", DEFAULT_BACKOFF_CAP_SECONDS)
    if base <= 0:
        return 0.0

    delay = base * (2 ** max(0, attempt_index - 1))
    retry_after = _retry_after_seconds(error)
    if retry_after is not None:
        delay = max(delay, retry_after)
    if cap > 0:
        delay = min(delay, cap)
    return max(0.0, delay)


class AllModelsFailedError(RuntimeError):
    """Raised when every candidate in the fallback sequence has failed."""


class FallbackLLM(BaseLLM):
    """CrewAI-compatible LLM with transparent multi-model failover."""

    models: List[str] = []

    # ``BaseLLM`` is a pydantic model: private attributes must be declared as
    # ``PrivateAttr`` (and assigned AFTER ``super().__init__``) or the values are
    # silently dropped when pydantic initializes ``__pydantic_private__``.
    _uses_default_sequence: bool = PrivateAttr(default=False)
    _call_timeout: float = PrivateAttr(default=DEFAULT_CALL_TIMEOUT_SECONDS)
    _llm_instances: Dict[str, Any] = PrivateAttr(default_factory=dict)
    _lock: Any = PrivateAttr(default_factory=threading.Lock)

    def __init__(
        self,
        models: Optional[List[str]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        timeout: Optional[float] = None,
        **kwargs: Any,
    ):
        uses_default_sequence = models is None
        model_list = list(models) if models else get_available_model_sequence()
        if not model_list:
            raise ValueError("Model fallback list cannot be empty.")

        call_timeout = float(
            timeout if timeout is not None else _env_float("LLM_CALL_TIMEOUT", DEFAULT_CALL_TIMEOUT_SECONDS)
        )
        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

        super().__init__(model=model_list[0], **kwargs)

        # Private attributes must be assigned after pydantic's __init__ ran.
        self.models = model_list
        self._uses_default_sequence = uses_default_sequence
        self._call_timeout = call_timeout
        self._llm_instances = {}
        self._lock = threading.Lock()

    # -- internals ---------------------------------------------------------
    def _get_instance(self, model_name: str) -> Any:
        """Return (and lazily build) the underlying ``crewai.LLM`` for a model."""
        with self._lock:
            # Check direct name lookup first (for testing/mocking compatibility)
            if model_name in self._llm_instances:
                return self._llm_instances[model_name]

            if model_name.startswith("gemini/"):
                active_key = get_gemini_key()
                inst_model = model_name
                init_kwargs: Dict[str, Any] = {"timeout": self._call_timeout}
                if active_key:
                    init_kwargs["api_key"] = active_key
            elif model_name.startswith("beatapi/"):
                active_key = get_beatapi_key()
                raw_model = model_name[len("beatapi/"):]
                inst_model = f"openai/{raw_model}"
                init_kwargs = {
                    "timeout": self._call_timeout,
                    "base_url": "https://api.beatapi.io/v1",
                }
                if active_key:
                    init_kwargs["api_key"] = active_key
            else:
                active_key = get_openrouter_key()
                inst_model = model_name
                init_kwargs = {"timeout": self._call_timeout}
                if active_key:
                    init_kwargs["api_key"] = active_key

            cache_key = (model_name, active_key)
            if cache_key in self._llm_instances:
                return self._llm_instances[cache_key]

            temperature = getattr(self, "temperature", None)
            if temperature is not None:
                init_kwargs["temperature"] = temperature
            max_tokens = getattr(self, "max_tokens", None)
            if max_tokens is not None:
                init_kwargs["max_tokens"] = max_tokens
            try:
                inst = LLM(model=inst_model, **init_kwargs)
            except TypeError:
                # Older crewai versions do not accept timeout/temperature here.
                inst = LLM(model=inst_model)
            self._llm_instances[cache_key] = inst
            return inst

    @staticmethod
    def _is_openrouter_daily_quota(error: BaseException) -> bool:
        text = str(error).lower()
        return "free-models-per-day" in text or "per day" in text or "daily" in text

    @staticmethod
    def _next_attemptable(models: List[str], start_index: int, skip_openrouter: bool) -> Optional[str]:
        for candidate in models[start_index:]:
            if skip_openrouter and candidate.startswith("openrouter/"):
                continue
            return candidate
        return None

    @staticmethod
    def _call_kwargs(kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Filter call kwargs down to what ``crewai.LLM.call`` actually accepts."""
        allowed = {"tools", "available_functions", "from_task", "from_agent", "response_model"}
        return {key: value for key, value in kwargs.items() if key in allowed}

    def _call_model(
        self,
        model_name: str,
        messages: Any,
        callbacks: Any,
        **kwargs: Any,
    ) -> str:
        instance = self._get_instance(model_name)
        result = instance.call(
            messages=messages,
            callbacks=callbacks,
            **self._call_kwargs(kwargs),
        )
        text = "" if result is None else str(result)
        if not text.strip():
            raise AllModelsFailedError(
                f"Model '{model_name}' returned an empty response."
            )
        return text

    def _execute_network_call(self, messages: Any, callbacks: Any, **kwargs: Any) -> str:
        last_error: Optional[BaseException] = None
        skip_openrouter = False
        models = get_available_model_sequence() if self._uses_default_sequence else list(self.models)
        attempt_index = 0

        for index, model_name in enumerate(models):
            if skip_openrouter and model_name.startswith("openrouter/"):
                continue

            attempt_index += 1
            _track_call_attempt()
            try:
                output = self._call_model(model_name, messages, callbacks, **kwargs)
                _track_model_success(model_name)
                return output
            except Exception as error:  # noqa: BLE001 - failover must catch everything
                last_error = error
                error_type = classify_error(error)
                _track_model_failure(model_name)

                daily_quota = (
                    error_type == "rate_limit"
                    and model_name.startswith("openrouter/")
                    and self._is_openrouter_daily_quota(error)
                )
                if daily_quota:
                    skip_openrouter = True

                next_model = self._next_attemptable(models, index + 1, skip_openrouter)
                if next_model:
                    _track_fallback(model_name, next_model, error_type)

                logger.warning(
                    "[FallbackLLM] model '%s' failed (%s: %s). %s",
                    model_name,
                    error_type,
                    error,
                    f"Falling back to '{next_model}'..." if next_model else "No candidates remain.",
                )
                if daily_quota and next_model:
                    logger.warning(
                        "[FallbackLLM] OpenRouter daily free quota hit; skipping remaining "
                        "OpenRouter candidates."
                    )

                if next_model:
                    delay = 0.0 if daily_quota else _backoff_delay(attempt_index, error)
                    if delay > 0:
                        logger.warning("[FallbackLLM] backing off for %.2fs before next attempt", delay)
                        time.sleep(delay)
                else:
                    break

        if skip_openrouter and not get_gemini_key() and not get_beatapi_key():
            raise AllModelsFailedError(
                "OpenRouter free-tier daily rate limit reached (50 requests/day). "
                "Please configure a free Google Gemini API Key or BeatAPI Key in Settings "
                "to get additional free requests without daily limits."
            )

        raise AllModelsFailedError(
            f"All models in the fallback sequence failed. Last error: {last_error}"
        )

    # -- public API --------------------------------------------------------
    def call(self, messages: Any, callbacks: Any = None, **kwargs: Any) -> str:
        """Call models sequentially until one succeeds, with deterministic memoization."""
        raw_temp = kwargs.pop("temperature", None)
        if raw_temp is None:
            raw_temp = getattr(self, "temperature", None)
        if raw_temp is None:
            raw_temp = 0.7
        temperature = float(raw_temp)
        bypass_cache = bool(kwargs.pop("bypass_cache", False))
        user_id = kwargs.pop("user_id", None)

        # Fail fast instead of firing one doomed network request per candidate.
        if self._uses_default_sequence and not has_llm_key():
            disabled_hint = (
                " LLM_DISABLED is set and no provider key is configured."
                if os.getenv("LLM_DISABLED", "").strip().lower() in ("1", "true", "yes")
                else ""
            )
            raise RuntimeError(
                "No LLM API key configured: set OPENROUTER_API_KEY (or GEMINI_API_KEY) "
                "before calling the default fallback chain." + disabled_hint
            )

        # Only memoize deterministic calls (temperature <= 0.2). Failures are never
        # cached (allow_stale_on_error=False) so a failed evaluation cannot be
        # served from stale data later.
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
                cached_result, _ = mgr.fetch_or_compute(
                    key=cache_key,
                    namespace="llm_eval",
                    fetch_fn=lambda: self._execute_network_call(messages, callbacks, **kwargs),
                    ttl_seconds=7 * 24 * 3600,
                    user_id=user_id,
                    bypass=bypass_cache,
                    allow_stale_on_error=False,
                )
                return cached_result
            except AllModelsFailedError:
                # A genuine model failure: bubble it up rather than attempting the
                # whole fallback sequence a second time.
                raise
            except Exception as cache_error:  # noqa: BLE001 - cache must never break LLM calls
                logger.debug("LLM cache bypassed due to cache/infra error: %s", cache_error)

        return self._execute_network_call(messages, callbacks, **kwargs)

    def supports_stop_words(self) -> bool:
        return True

    def get_context_window_size(self) -> int:
        return 128000


def get_fallback_llm(**kwargs: Any) -> FallbackLLM:
    """Convenience factory returning a configured FallbackLLM."""
    return FallbackLLM(**kwargs)
