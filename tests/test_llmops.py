"""Tests for LLMOps telemetry: estimates, readability, fallback accounting."""

from unittest.mock import patch

import pytest

from llmops.telemetry import TelemetryTracker, calculate_readability, estimate_tokens
import database as db


def test_estimate_tokens():
    """Verify heuristic token estimation."""
    text = "Hello world, this is a test string."
    tokens = estimate_tokens(text)
    assert tokens > 0
    assert estimate_tokens("") == 0


def test_estimate_tokens_ignores_code_blocks_and_mermaid():
    """Fenced code/Mermaid must not inflate the prose token estimate."""
    prose = "Short prose about KV cache behaviour."
    fenced = prose + "\n\n```mermaid\n" + "\n".join(["flowchart TD"] * 200) + "\n```\n"
    assert estimate_tokens(fenced) == estimate_tokens(prose)
    assert estimate_tokens(fenced, ignore_code_blocks=False) > estimate_tokens(fenced)


def test_calculate_readability():
    """Verify Flesch Reading Ease calculation."""
    text = (
        "Artificial intelligence agents are computer systems that perceive their environment "
        "and take autonomous actions to achieve specific goals. They use language models "
        "and specialized tools to execute complex workflows."
    )
    metrics = calculate_readability(text)
    assert "score" in metrics
    assert "grade" in metrics
    assert metrics["word_count"] > 10
    assert 0 <= metrics["score"] <= 100


def test_telemetry_tracker_lifecycle():
    """Verify TelemetryTracker recording and finalization."""
    tracker = TelemetryTracker(topic="AI Agents")
    tracker.start_stage("research")
    tracker.record_model_usage("nvidia/nemotron-3.5-lightning:free")
    tracker.record_fallback("model-a", "429 Rate Limited", "model-b")
    tracker.record_security_event("SANITIZATION", "Indirect injection removed")
    tracker.end_stage("research")

    summary = tracker.finalize(report_text="Sample report content with multiple words.")
    assert summary["topic"] == "AI Agents"
    assert summary["fallback_count"] == 1
    assert "nvidia/nemotron-3.5-lightning:free" in summary["models_used"]
    assert "research" in summary["stage_timings"]
    assert len(summary["security_events"]) == 1


def test_record_fallback_writes_consumer_key_names():
    """record_fallback must write the canonical failed_model/switched_to/error_type keys."""
    tracker = TelemetryTracker(topic="Keys")
    tracker.record_fallback("model-a", "HTTP 429 Rate Limited", "model-b")

    summary = tracker.finalize(report_text="Report")
    event = summary["fallback_events"][0]
    assert event["failed_model"] == "model-a"
    assert event["switched_to"] == "model-b"
    assert event["error_type"] == "rate_limit"
    # Legacy dashboard key aliases must NOT be the only representation.
    assert "from_model" not in event and "to_model" not in event


def test_finalize_does_not_invent_token_estimates():
    """tokens_estimated must be the real (estimate) of the report, with no topic multiplier."""
    long_topic = "An extremely long research topic " * 50
    tracker = TelemetryTracker(topic=long_topic)
    report = "Report body with a handful of words."
    summary = tracker.finalize(report_text=report)
    assert summary["tokens_estimated"] == estimate_tokens(report)
    assert summary["tokens_estimated_is_estimate"] is True

    empty_summary = TelemetryTracker(topic=long_topic).finalize(report_text="")
    assert empty_summary["tokens_estimated"] == 0


def test_record_usage_stats_ingests_real_fallback_telemetry():
    """TelemetryTracker must consume llm_fallback.get_usage_stats() verbatim."""
    fake_stats = {
        "models_used": ["model-x"],
        "failed_models": ["model-y"],
        "fallback_events": [
            {"failed_model": "model-y", "switched_to": "model-x", "error_type": "timeout"}
        ],
        "call_count": 2,
    }
    tracker = TelemetryTracker(topic="Wiring")
    tracker.record_usage_stats(fake_stats)

    summary = tracker.finalize(report_text="Report")
    assert summary["models_used"] == ["model-x"]
    assert summary["failed_models"] == ["model-y"]
    assert summary["fallback_count"] == 1
    assert summary["fallback_events"][0]["failed_model"] == "model-y"
    assert summary["fallback_events"][0]["switched_to"] == "model-x"
    assert summary["fallback_events"][0]["error_type"] == "timeout"
    assert summary["llm_call_count"] == 2


def test_database_telemetry_persistence_roundtrip():
    """Verify saving and fetching telemetry (including canonical fallback keys) from SQLite."""
    telemetry_data = {
        "topic": "Quantum Testing",
        "duration_sec": 12.5,
        "tokens_estimated": 450,
        "models_used": ["model-x", "model-y"],
        "fallback_count": 1,
        "fallback_events": [
            {"failed_model": "model-x", "switched_to": "model-y", "error_type": "rate_limit"}
        ],
        "readability": {"score": 68.5, "grade": "Standard"},
    }

    run_id = db.save_telemetry_run(article_id=None, telemetry_data=telemetry_data)
    assert run_id is not None

    history = db.get_telemetry_history(limit=5)
    assert len(history) > 0
    latest = history[0]
    assert latest["topic"] == "Quantum Testing"
    assert latest["tokens_estimated"] == 450
    assert latest["fallback_events"][0]["failed_model"] == "model-x"
    assert latest["fallback_events"][0]["switched_to"] == "model-y"
