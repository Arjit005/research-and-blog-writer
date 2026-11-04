import pytest
from llmops.telemetry import TelemetryTracker, calculate_readability, estimate_tokens
import database as db


def test_estimate_tokens():
    """Verify heuristic token estimation."""
    text = "Hello world, this is a test string."
    tokens = estimate_tokens(text)
    assert tokens > 0
    assert estimate_tokens("") == 0


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


def test_database_telemetry_persistence():
    """Verify saving and fetching telemetry from SQLite database."""
    telemetry_data = {
        "topic": "Quantum Testing",
        "duration_sec": 12.5,
        "tokens_estimated": 450,
        "models_used": ["model-x", "model-y"],
        "fallback_count": 1,
        "fallback_events": [{"failed": "model-x", "next": "model-y"}],
        "readability": {"score": 68.5, "grade": "Standard"},
    }

    run_id = db.save_telemetry_run(article_id=None, telemetry_data=telemetry_data)
    assert run_id is not None

    history = db.get_telemetry_history(limit=5)
    assert len(history) > 0
    latest = history[0]
    assert latest["topic"] == "Quantum Testing"
    assert latest["tokens_estimated"] == 450
