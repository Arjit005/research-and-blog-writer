"""Tests for LangSmith Observability and Tracing Engine."""

import os
from unittest.mock import patch, MagicMock
from llmops.tracing import LangSmithJobTracer, is_tracing_enabled, _mask_inputs, export_failure_to_dataset


def test_tracing_disabled_by_default_without_api_key(monkeypatch):
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")

    assert is_tracing_enabled() is False

    tracer = LangSmithJobTracer(
        run_id="run_test_123",
        topic="Architecture of Rust Microservices",
        user_id=1,
    )
    assert tracer.root_tree is None
    assert tracer.get_trace_url() is None

    # Operations should be safe no-ops
    span = tracer.start_span("stage_0", "Stage 0", run_type="chain")
    assert span is None
    tracer.end_span("stage_0", outputs={"result": "ok"})
    tracer.log_evaluation("flesch_reading_ease", 75.5)
    tracer.record_model_usage(["model-a", "model-b"])
    tracer.record_metadata({"fallback_count": 1})
    url = tracer.end_job(outputs={"article_id": 1})
    assert url is None


def test_pii_masking_before_tracing():
    topic_with_pii = "Contact me at alice@enterprise.com with token sk-or-v1-abcdef1234567890"
    masked = _mask_inputs(topic_with_pii)
    assert "alice@enterprise.com" not in masked
    assert "[REDACTED_EMAIL]" in masked or "[REDACTED" in masked


def test_tracer_with_mocked_run_tree(monkeypatch):
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2_pt_mock_test_key_12345")
    monkeypatch.setenv("LANGSMITH_TRACING", "true")

    mock_tree = MagicMock()
    mock_tree.id = "mock-tree-uuid-1"
    mock_tree.get_url.return_value = "https://smith.langchain.com/o/org/projects/p/proj/r/mock-tree-uuid-1"

    mock_child = MagicMock()
    mock_tree.create_child.return_value = mock_child

    with patch("llmops.tracing.is_tracing_enabled", return_value=True), \
         patch("langsmith.run_trees.RunTree", return_value=mock_tree):
        tracer = LangSmithJobTracer(
            run_id="run_mock_456",
            topic="Deep Learning Optimization",
            user_id=42,
        )

        assert tracer.root_tree is not None
        mock_tree.post.assert_called_once()
        assert tracer.get_trace_url() == "https://smith.langchain.com/o/org/projects/p/proj/r/mock-tree-uuid-1"

        # Test starting child span
        child = tracer.start_span("stage_0", "Researcher Agent", run_type="chain")
        assert child == mock_child
        mock_tree.create_child.assert_called_once()
        mock_child.post.assert_called_once()

        # Test ending child span
        tracer.end_span("stage_0", outputs={"findings": 5})
        mock_child.end.assert_called_once()
        mock_child.patch.assert_called_once()

        # Test ending job
        url = tracer.end_job(outputs={"status": "completed"})
        assert url == "https://smith.langchain.com/o/org/projects/p/proj/r/mock-tree-uuid-1"
        mock_tree.end.assert_called_once()
        mock_tree.patch.assert_called_once()


def test_model_usage_and_metadata_attached_to_spans_and_root(monkeypatch):
    """Model usage is recorded as span/root metadata (native-provider-friendly observability)."""
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2_pt_mock_test_key_12345")
    monkeypatch.setenv("LANGSMITH_TRACING", "true")

    mock_tree = MagicMock()
    mock_tree.id = "mock-tree-uuid-2"
    mock_tree.extra = {"metadata": {}}
    mock_tree.get_url.return_value = "https://example.invalid/run"
    mock_child = MagicMock()
    mock_tree.create_child.return_value = mock_child

    with patch("llmops.tracing.is_tracing_enabled", return_value=True), \
         patch("langsmith.run_trees.RunTree", return_value=mock_tree):
        tracer = LangSmithJobTracer(run_id="run_meta", topic="Meta")
        tracer.record_model_usage("model-a")
        tracer.record_model_usage(["model-a", "model-b"])
        tracer.record_metadata({"fallback_count": 2})

        tracer.start_span("stage_0", "Stage", metadata={"agent_role": "Senior Researcher"})
        create_kwargs = mock_tree.create_child.call_args.kwargs
        assert create_kwargs["extra"]["metadata"]["agent_role"] == "Senior Researcher"

        tracer.end_span("stage_0", outputs={"ok": True})
        span_outputs = mock_child.end.call_args.kwargs["outputs"]
        assert span_outputs["models_used"] == ["model-a", "model-b"]

        tracer.end_job(outputs={"status": "completed"})
        root_outputs = mock_tree.end.call_args.kwargs["outputs"]
        assert root_outputs["models_used"] == ["model-a", "model-b"]
        assert root_outputs["metadata"]["fallback_count"] == 2


def test_tracing_masks_error_strings():
    """Error strings attached to spans/jobs must be PII/secret-masked."""
    with patch("llmops.tracing.is_tracing_enabled", return_value=True), \
         patch("langsmith.run_trees.RunTree") as run_tree_cls:
        mock_tree = MagicMock()
        mock_tree.id = "id"
        mock_tree.extra = {"metadata": {}}
        mock_tree.get_url.return_value = None
        mock_child = MagicMock()
        mock_tree.create_child.return_value = mock_child
        run_tree_cls.return_value = mock_tree

        tracer = LangSmithJobTracer(run_id="run_mask", topic="Mask")
        tracer.start_span("stage_0", "Stage")
        tracer.end_span("stage_0", error="failed for alice@enterprise.com key sk-or-v1-abcdef1234567890")
        span_error = mock_child.end.call_args.kwargs["error"]
        assert "alice@enterprise.com" not in span_error
        assert "sk-or-v1-abcdef1234567890" not in span_error

        tracer.end_job(error="contact alice@enterprise.com")
        root_error = mock_tree.end.call_args.kwargs["error"]
        assert "alice@enterprise.com" not in root_error


def test_export_failure_to_dataset_masks_error_message(monkeypatch):
    """export_failure_to_dataset must mask the error string before uploading it."""
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2_pt_mock_test_key_12345")
    monkeypatch.setenv("LANGSMITH_TRACING", "true")

    created = {}

    class FakeClient:
        def read_dataset(self, dataset_name):
            raise RuntimeError("not found")

        def create_dataset(self, dataset_name, description=""):
            return MagicMock(id="dataset-1")

        def create_example(self, **kwargs):
            created.update(kwargs)

    with patch("llmops.tracing.is_tracing_enabled", return_value=True), \
         patch("langsmith.Client", return_value=FakeClient()):
        ok = export_failure_to_dataset(
            dataset_name="prod_failures",
            topic="Failing topic for alice@enterprise.com",
            error_message="401 Unauthorized for alice@enterprise.com with sk-or-v1-abcdef1234567890",
        )

    assert ok is True
    assert "alice@enterprise.com" not in created["outputs"]["error_message"]
    assert "sk-or-v1-abcdef1234567890" not in created["outputs"]["error_message"]
    assert "alice@enterprise.com" not in created["inputs"]["topic"]


def test_export_failure_to_dataset_disabled_when_no_key(monkeypatch):
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)
    monkeypatch.setenv("LANGSMITH_TRACING", "false")

    success = export_failure_to_dataset(
        dataset_name="prod_failures",
        topic="Failing Topic",
        error_message="Model timed out",
    )
    assert success is False
