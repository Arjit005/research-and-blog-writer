"""Regression tests for the multi-model FallbackLLM.

All model calls are mocked; these tests never touch the network.
"""

import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import llm_fallback
from llm_fallback import (
    FallbackLLM,
    get_fallback_llm,
    get_usage_stats,
    reset_usage_stats,
    scoped_llm_keys,
    get_openrouter_key,
    get_gemini_key,
    get_beatapi_key,
    classify_error,
)

MODEL_NAMES = ["model-1", "model-2"]


@pytest.fixture(autouse=True)
def _offline_llm_env(monkeypatch):
    """Deterministic, offline defaults: no keys, no real backoff sleeps."""
    for var in ("OPENROUTER_API_KEY", "OPEN_ROUTER_API_KEY", "GEMINI_API_KEY", "BEATAPI_KEY", "BEAT_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("LLM_BACKOFF_BASE_SECONDS", "0")
    monkeypatch.setenv("LLM_BACKOFF_CAP_SECONDS", "10")
    reset_usage_stats()
    yield
    reset_usage_stats()


def _mock_llm(return_value=None, side_effect=None):
    mock = MagicMock()
    if side_effect is not None:
        mock.call.side_effect = side_effect
    else:
        mock.call.return_value = return_value
    return mock


def test_fallback_llm_success_first_try():
    """Verify that if the first model succeeds, its response is returned."""
    mock_llm_1 = _mock_llm("Response from model 1")

    with patch("llm_fallback.LLM", return_value=mock_llm_1):
        fallback = FallbackLLM(MODEL_NAMES)
        result = fallback.call([{"role": "user", "content": "hi"}])
        assert result == "Response from model 1"
        assert mock_llm_1.call.call_count == 1


def test_fallback_llm_failover():
    """Verify that when model 1 raises an error, model 2 is automatically called."""
    mock_llm_1 = _mock_llm(side_effect=Exception("HTTP 429 Rate Limited"))
    mock_llm_2 = _mock_llm("Response from fallback model 2")

    def side_effect(model, **kwargs):
        return mock_llm_1 if "model-1" in model else mock_llm_2

    with patch("llm_fallback.LLM", side_effect=side_effect):
        fallback = FallbackLLM(MODEL_NAMES)
        result = fallback.call([{"role": "user", "content": "hi"}])
        assert result == "Response from fallback model 2"
        mock_llm_1.call.assert_called_once()
        mock_llm_2.call.assert_called_once()


def test_fallback_llm_all_fail():
    """Verify that RuntimeError is raised only if all candidates fail."""
    mock_llm_fail = _mock_llm(side_effect=Exception("Outage 503"))

    with patch("llm_fallback.LLM", return_value=mock_llm_fail):
        fallback = FallbackLLM(MODEL_NAMES)
        with pytest.raises(RuntimeError, match="All models in the fallback sequence failed"):
            fallback.call([{"role": "user", "content": "hi"}])


# ---------------------------------------------------------------------------
# Usage telemetry contract consumed by the backend
# ---------------------------------------------------------------------------
def test_usage_stats_contract_success():
    """get_usage_stats returns exactly the documented keys with real values."""
    mock_llm = _mock_llm("ok output")
    with patch("llm_fallback.LLM", return_value=mock_llm):
        FallbackLLM(MODEL_NAMES).call([{"role": "user", "content": "hello"}])

    stats = get_usage_stats()
    assert set(stats.keys()) == {"models_used", "failed_models", "fallback_events", "call_count"}
    assert stats["models_used"] == ["model-1"]
    assert stats["failed_models"] == []
    assert stats["fallback_events"] == []
    assert stats["call_count"] == 1
    assert all(isinstance(event, dict) for event in stats["fallback_events"])


def test_usage_stats_records_fallback_event_and_error_type():
    """A failed model records a fallback event with failed_model/switched_to/error_type."""
    mock_llm_1 = _mock_llm(side_effect=Exception("HTTP 429 Rate Limited"))
    mock_llm_2 = _mock_llm("recovered")

    with patch("llm_fallback.LLM", side_effect=lambda model, **kw: mock_llm_1 if model == "model-1" else mock_llm_2):
        result = FallbackLLM(MODEL_NAMES).call([{"role": "user", "content": "hi"}])

    assert result == "recovered"
    stats = get_usage_stats()
    assert stats["models_used"] == ["model-2"]
    assert stats["failed_models"] == ["model-1"]
    assert stats["fallback_events"] == [
        {"failed_model": "model-1", "switched_to": "model-2", "error_type": "rate_limit"}
    ]
    assert stats["call_count"] == 2  # one attempt per candidate


def test_usage_stats_is_a_defensive_snapshot():
    mock_llm = _mock_llm("ok")
    with patch("llm_fallback.LLM", return_value=mock_llm):
        FallbackLLM(MODEL_NAMES).call([{"role": "user", "content": "hi"}])

    snapshot = get_usage_stats()
    snapshot["models_used"].append("tampered")
    snapshot["failed_models"].append("tampered")
    snapshot["call_count"] = 999
    assert "tampered" not in get_usage_stats()["models_used"]
    assert "tampered" not in get_usage_stats()["failed_models"]
    assert get_usage_stats()["call_count"] != 999


def test_failed_call_is_not_cached_and_not_recorded_as_model_used():
    """A failed deterministic call must not be cached nor recorded as success."""
    failing = _mock_llm(side_effect=Exception("503 provider outage"))
    with patch("llm_fallback.LLM", return_value=failing):
        with pytest.raises(RuntimeError):
            FallbackLLM(MODEL_NAMES).call(
                messages=[{"role": "user", "content": "unique-failure-probe"}],
                temperature=0.1,
            )
    assert get_usage_stats()["models_used"] == []

    working = _mock_llm("Fresh deterministic response")
    with patch("llm_fallback.LLM", return_value=working):
        result = FallbackLLM(MODEL_NAMES).call(
            messages=[{"role": "user", "content": "unique-failure-probe"}],
            temperature=0.1,
        )
    assert result == "Fresh deterministic response"
    assert working.call.call_count == 1  # network actually used, no stale/failed cache entry
    assert get_usage_stats()["models_used"] == ["model-1"]


# ---------------------------------------------------------------------------
# Fail-fast, classification, timeout, and backoff
# ---------------------------------------------------------------------------
def test_no_key_default_chain_fails_fast_without_network_calls():
    """The default chain raises a clear RuntimeError instead of 7 doomed calls."""
    with patch("llm_fallback.LLM") as mock_llm:
        fallback = FallbackLLM()
        with pytest.raises(RuntimeError, match="No LLM API key configured"):
            fallback.call([{"role": "user", "content": "hi"}])
        mock_llm.assert_not_called()
    assert get_usage_stats()["call_count"] == 0


def test_classify_error_categories():
    assert classify_error(Exception("HTTP 429 too many requests")) == "rate_limit"
    assert classify_error(TimeoutError("request timed out")) == "timeout"
    assert classify_error(Exception("401 Unauthorized: invalid api key")) == "auth"
    assert classify_error(Exception("404 model not found")) == "config"
    assert classify_error(Exception("some unexpected failure")) == "other"


def test_retry_after_header_honored_for_backoff(monkeypatch):
    """A provider Retry-After hint is honored (clamped by the configured cap)."""
    monkeypatch.setenv("LLM_BACKOFF_BASE_SECONDS", "1")
    monkeypatch.setenv("LLM_BACKOFF_CAP_SECONDS", "10")
    error = Exception("429 rate limited")
    error.response = SimpleNamespace(headers={"Retry-After": "3"})
    mock_bad = _mock_llm(side_effect=error)
    mock_good = _mock_llm("ok")

    with patch("llm_fallback.LLM", side_effect=lambda model, **kw: mock_bad if model == "model-1" else mock_good), \
         patch("llm_fallback.time.sleep") as mock_sleep:
        FallbackLLM(MODEL_NAMES).call([{"role": "user", "content": "hi"}])

    assert mock_sleep.call_count == 1
    assert mock_sleep.call_args[0][0] == pytest.approx(3.0)


def test_per_call_timeout_passed_to_underlying_llm():
    """LLM_CALL_TIMEOUT / explicit timeout is applied to underlying LLM instances."""
    mock_llm = _mock_llm("ok")
    with patch("llm_fallback.LLM", return_value=mock_llm) as llm_ctor:
        FallbackLLM(MODEL_NAMES, timeout=7).call([{"role": "user", "content": "hi"}])

    assert llm_ctor.call_count == 1
    assert llm_ctor.call_args.kwargs.get("timeout") == pytest.approx(7.0)


def test_scoped_llm_keys_do_not_mutate_process_environment():
    """Runtime-scoped keys are visible only inside the context manager."""
    env_openrouter = os.getenv("OPENROUTER_API_KEY")
    env_gemini = os.getenv("GEMINI_API_KEY")
    env_beatapi = os.getenv("BEATAPI_KEY")
    with scoped_llm_keys(openrouter_key="sk-or-runtime", gemini_key="AIza-runtime", beatapi_key="sk-beat-runtime"):
        assert get_openrouter_key() == "sk-or-runtime"
        assert get_gemini_key() == "AIza-runtime"
        assert get_beatapi_key() == "sk-beat-runtime"
        assert os.getenv("OPENROUTER_API_KEY") == env_openrouter
        assert os.getenv("GEMINI_API_KEY") == env_gemini
        assert os.getenv("BEATAPI_KEY") == env_beatapi
    assert os.getenv("OPENROUTER_API_KEY") == env_openrouter
    assert os.getenv("GEMINI_API_KEY") == env_gemini
    assert os.getenv("BEATAPI_KEY") == env_beatapi
    assert get_openrouter_key() == (env_openrouter or os.getenv("OPEN_ROUTER_API_KEY") or "")
    assert get_gemini_key() == (env_gemini or "")
    assert get_beatapi_key() == (env_beatapi or os.getenv("BEAT_API_KEY") or "")


def test_exported_helpers_are_import_safe():
    assert callable(llm_fallback.get_usage_stats)
    assert callable(llm_fallback.reset_usage_stats)
    assert callable(get_fallback_llm)


def test_beatapi_model_routing():
    """BeatAPI models are initialized with base_url and openai/ prefix."""
    mock_llm = _mock_llm("beatapi response")
    with patch("llm_fallback.LLM", return_value=mock_llm) as mock_ctor:
        with scoped_llm_keys(beatapi_key="test-beat-key"):
            fallback = FallbackLLM(["beatapi/glm-5.3-flash-free"])
            res = fallback.call([{"role": "user", "content": "hi"}])
            assert res == "beatapi response"
            assert mock_ctor.call_count == 1
            assert mock_ctor.call_args.kwargs.get("model") == "openai/glm-5.3-flash-free"
            assert mock_ctor.call_args.kwargs.get("base_url") == "https://api.beatapi.io/v1"
            assert mock_ctor.call_args.kwargs.get("api_key") == "test-beat-key"


def test_openrouter_daily_quota_skips_to_gemini():
    """Daily quota exhaustion (e.g. 50 req/day) skips remaining OpenRouter models directly to Gemini."""
    models = [
        "openrouter/model-a:free",
        "openrouter/model-b:free",
        "gemini/gemini-2.5-flash",
    ]
    mock_or_a = _mock_llm(side_effect=RuntimeError("Provider returned 429: Free model limit reached (50 requests per day)"))
    mock_or_b = _mock_llm(side_effect=RuntimeError("Should be skipped"))
    mock_gemini = _mock_llm("Gemini response after OpenRouter quota exhausted")

    def _llm_factory(model, **kwargs):
        if "model-a" in model:
            return mock_or_a
        if "model-b" in model:
            return mock_or_b
        return mock_gemini

    with patch("llm_fallback.LLM", side_effect=_llm_factory):
        with scoped_llm_keys(openrouter_key="test-or-key", gemini_key="test-gemini-key"):
            fallback = FallbackLLM(models)
            res = fallback.call([{"role": "user", "content": "hi"}])
            assert res == "Gemini response after OpenRouter quota exhausted"
            assert mock_or_a.call.call_count == 1
            assert mock_or_b.call.call_count == 0  # Crucial: skipped!
            assert mock_gemini.call.call_count == 1


def test_openrouter_temporary_429_retries_and_backs_off(monkeypatch):
    """Temporary 429 without daily quota indicators retries the next candidate with backoff."""
    monkeypatch.setenv("LLM_BACKOFF_BASE_SECONDS", "1.0")
    models = [
        "openrouter/model-a:free",
        "openrouter/model-b:free",
    ]
    mock_or_a = _mock_llm(side_effect=RuntimeError("429 Too Many Requests: concurrency limit 2"))
    mock_or_b = _mock_llm("Model B succeeded")

    def _llm_factory(model, **kwargs):
        if "model-a" in model:
            return mock_or_a
        return mock_or_b

    with patch("llm_fallback.LLM", side_effect=_llm_factory):
        with patch("llm_fallback.time.sleep") as mock_sleep:
            with scoped_llm_keys(openrouter_key="test-or-key"):
                fallback = FallbackLLM(models)
                res = fallback.call([{"role": "user", "content": "hi"}])
                assert res == "Model B succeeded"
                assert mock_or_a.call.call_count == 1
                assert mock_or_b.call.call_count == 1  # Not skipped!
                # Backoff was invoked for temporary rate limit
                assert mock_sleep.call_count >= 1
                assert mock_sleep.call_args[0][0] >= 1.0


def test_fallback_sequence_gemini_to_beatapi():
    """If Gemini fails, fallback proceeds to BeatAPI."""
    models = [
        "gemini/gemini-2.5-flash",
        "beatapi/glm-5.3-flash-free",
    ]
    mock_gemini = _mock_llm(side_effect=RuntimeError("Google Gemini 503 Service Unavailable"))
    mock_beatapi = _mock_llm("BeatAPI response")

    def _llm_factory(model, **kwargs):
        if "gemini" in model:
            return mock_gemini
        return mock_beatapi

    with patch("llm_fallback.LLM", side_effect=_llm_factory):
        with scoped_llm_keys(gemini_key="test-gemini-key", beatapi_key="test-beat-key"):
            fallback = FallbackLLM(models)
            res = fallback.call([{"role": "user", "content": "hi"}])
            assert res == "BeatAPI response"
            assert mock_gemini.call.call_count == 1
            assert mock_beatapi.call.call_count == 1


def test_no_keys_configured_fails_fast():
    """When no keys are configured, default fallback chain fails fast with informative error."""
    with patch("llm_fallback.get_openrouter_key", return_value=""):
        with patch("llm_fallback.get_gemini_key", return_value=""):
            with patch("llm_fallback.get_beatapi_key", return_value=""):
                fallback = FallbackLLM()
                with pytest.raises(RuntimeError, match="No LLM API key configured"):
                    fallback.call([{"role": "user", "content": "hi"}])


def test_secret_safe_logging(caplog):
    """Logs must never contain actual API keys or secret tokens."""
    import logging
    secret_or = "sk-or-v1-abcdef1234567890abcdef1234567890"
    secret_gemini = "AIzaSyD-Secret1234567890abcdef1234567"

    models = ["openrouter/model-a:free", "gemini/model-g"]
    mock_a = _mock_llm(side_effect=RuntimeError(f"OpenRouter 429 quota error: key {secret_or} exceeded free-models-per-day"))
    mock_g = _mock_llm("Success from Gemini")

    def _llm_factory(model, **kwargs):
        if "model-a" in model:
            return mock_a
        return mock_g

    with caplog.at_level(logging.WARNING):
        with patch("llm_fallback.LLM", side_effect=_llm_factory):
            with scoped_llm_keys(openrouter_key=secret_or, gemini_key=secret_gemini):
                fallback = FallbackLLM(models)
                res = fallback.call([{"role": "user", "content": "hi"}])
                assert res == "Success from Gemini"

    # Verify no log record contains the actual secret keys
    all_logs = " ".join([rec.message for rec in caplog.records])
    assert secret_or not in all_logs
    assert secret_gemini not in all_logs
    assert "[REDACTED_API_KEY]" in all_logs

