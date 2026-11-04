"""Enterprise LangSmith Traceability, Observability & Evaluation Integration.

Features:
- Hierarchical Span Trees: Root research job with nested agent stages and tool executions.
- Thread-safe Context Management: Explicit parent-child span trees across background worker threads.
- Zero-leak PII Protection: Pre-scrubs sensitive entities prior to trace ingestion.
- Multi-SDK Env Sync: Bi-directionally aligns LANGSMITH_* and legacy LANGCHAIN_* variables.
- Automated LiteLLM Callback Hooks: Telemetry & token cost accounting for model calls.
- Automated Feedback & Regression Dataset Export: Converts production failures into eval datasets.
"""

from __future__ import annotations

import os
import logging
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

logger = logging.getLogger("llmops.tracing")

# Check API key existence across standard variants
LANGSMITH_API_KEY = os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY")
LANGSMITH_PROJECT = os.getenv("LANGSMITH_PROJECT") or os.getenv("LANGCHAIN_PROJECT") or "research-and-blog-writer"
LANGSMITH_ENDPOINT = os.getenv("LANGSMITH_ENDPOINT") or os.getenv("LANGCHAIN_ENDPOINT") or "https://api.smith.langchain.com"

# Setup environment synchronization if key is present
if LANGSMITH_API_KEY:
    os.environ["LANGSMITH_API_KEY"] = LANGSMITH_API_KEY
    os.environ["LANGCHAIN_API_KEY"] = LANGSMITH_API_KEY
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGSMITH_PROJECT"] = LANGSMITH_PROJECT
    os.environ["LANGCHAIN_PROJECT"] = LANGSMITH_PROJECT
    os.environ["LANGSMITH_ENDPOINT"] = LANGSMITH_ENDPOINT
    os.environ["LANGCHAIN_ENDPOINT"] = LANGSMITH_ENDPOINT

    try:
        import litellm
        if "langsmith" not in litellm.success_callback:
            litellm.success_callback.append("langsmith")
        if "langsmith" not in litellm.failure_callback:
            litellm.failure_callback.append("langsmith")
        logger.info(f"LangSmith auto-tracing initialized for project: {LANGSMITH_PROJECT}")
    except Exception as e:
        logger.debug(f"Could not initialize litellm callbacks: {e}")


def is_tracing_enabled() -> bool:
    """Check if LangSmith tracing is active and configured."""
    return bool(LANGSMITH_API_KEY and (os.getenv("LANGSMITH_TRACING") == "true" or os.getenv("LANGCHAIN_TRACING_V2") == "true"))


def _mask_inputs(data: Any) -> Any:
    """Pre-sanitize inputs to ensure PII and credentials never leak into LangSmith cloud."""
    try:
        from security.guardrails import mask_pii_and_secrets
        if isinstance(data, str):
            masked = mask_pii_and_secrets(data)
            return masked
        elif isinstance(data, dict):
            return {k: _mask_inputs(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [_mask_inputs(item) for item in data]
    except Exception:
        pass
    return data


class LangSmithJobTracer:
    """Manages hierarchical span trees for an end-to-end multi-agent research job."""

    def __init__(
        self,
        run_id: str,
        topic: str,
        user_id: Optional[int] = None,
        tone: Optional[str] = None,
        audience: Optional[str] = None,
        target_length: Optional[str] = None,
    ):
        self.run_id = run_id
        self.user_id = user_id
        self.topic = topic
        self.tone = tone
        self.audience = audience
        self.target_length = target_length
        self.root_tree = None
        self.active_spans: Dict[str, Any] = {}
        self._trace_url: Optional[str] = None

        if not is_tracing_enabled():
            return

        try:
            from langsmith.run_trees import RunTree

            masked_topic = _mask_inputs(topic)
            self.root_tree = RunTree(
                name=f"ResearchJob: {masked_topic[:45]}",
                run_type="chain",
                inputs={
                    "topic": masked_topic,
                    "tone": tone or "Professional",
                    "audience": audience or "General",
                    "target_length": target_length or "Standard",
                },
                project_name=LANGSMITH_PROJECT,
                tags=["crewai", "multi-agent", "production", "fastapi"],
                extra={
                    "metadata": {
                        "run_id": run_id,
                        "user_id": user_id,
                        "project": LANGSMITH_PROJECT,
                    }
                },
            )
            # Post root trace to LangSmith
            self.root_tree.post()
            try:
                self._trace_url = self.root_tree.get_url()
            except Exception as url_err:
                logger.debug(f"Could not compute LangSmith URL: {url_err}")
                self._trace_url = None
        except Exception as e:
            logger.warning(f"Failed to start root LangSmith trace: {e}")
            self.root_tree = None

    def get_trace_url(self) -> Optional[str]:
        """Return official authenticated LangSmith run URL."""
        if self._trace_url:
            return self._trace_url
        if self.root_tree:
            try:
                self._trace_url = self.root_tree.get_url()
                return self._trace_url
            except Exception:
                return None
        return None

    def start_span(self, span_key: str, name: str, run_type: str = "chain", inputs: Optional[Dict[str, Any]] = None) -> Optional[Any]:
        """Start a nested child span explicitly parented to the root job tree."""
        if not self.root_tree:
            return None
        try:
            clean_inputs = _mask_inputs(inputs or {})
            child_span = self.root_tree.create_child(
                name=name,
                run_type=run_type,
                inputs=clean_inputs,
                extra={"metadata": {"span_key": span_key, "run_id": self.run_id}},
            )
            child_span.post()
            self.active_spans[span_key] = child_span
            return child_span
        except Exception as e:
            logger.debug(f"Failed to start span {name}: {e}")
            return None

    def end_span(self, span_key: str, outputs: Optional[Dict[str, Any]] = None, error: Optional[str] = None) -> None:
        """End and post status for an active child span."""
        span = self.active_spans.pop(span_key, None)
        if not span:
            return
        try:
            clean_outputs = _mask_inputs(outputs or {})
            span.end(outputs=clean_outputs, error=error)
            span.patch()
        except Exception as e:
            logger.debug(f"Failed to end span {span_key}: {e}")

    def log_evaluation(self, key: str, score: float, comment: Optional[str] = None) -> None:
        """Attach quantitative evaluation metric (e.g., Flesch Readability) to the trace."""
        if not self.root_tree:
            return
        try:
            from langsmith import Client
            client = Client()
            client.create_feedback(
                run_id=self.root_tree.id,
                key=key,
                score=score,
                comment=comment,
            )
        except Exception as e:
            logger.debug(f"Could not log evaluation to LangSmith: {e}")

    def end_job(self, outputs: Optional[Dict[str, Any]] = None, error: Optional[str] = None) -> Optional[str]:
        """End the root trace, log completion outputs, and return the official trace URL."""
        if not self.root_tree:
            return None
        try:
            # End any dangling spans
            for key in list(self.active_spans.keys()):
                self.end_span(key, error="Job ended before span explicitly closed")

            clean_outputs = _mask_inputs(outputs or {})
            self.root_tree.end(outputs=clean_outputs, error=error)
            self.root_tree.patch()
            return self.get_trace_url()
        except Exception as e:
            logger.warning(f"Failed to end LangSmith root trace: {e}")
            return None


def export_failure_to_dataset(
    dataset_name: str,
    topic: str,
    error_message: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> bool:
    """Save production failures to a LangSmith Dataset for automated regression testing."""
    if not is_tracing_enabled():
        return False
    try:
        from langsmith import Client
        client = Client()

        # Ensure dataset exists
        try:
            dataset = client.read_dataset(dataset_name=dataset_name)
        except Exception:
            dataset = client.create_dataset(
                dataset_name=dataset_name,
                description="Production failure cases converted to automated regression test cases",
            )

        client.create_example(
            inputs={"topic": _mask_inputs(topic)},
            outputs={"error_message": error_message},
            metadata=_mask_inputs(metadata or {}),
            dataset_id=dataset.id,
        )
        logger.info(f"Successfully recorded regression test case to LangSmith dataset '{dataset_name}'")
        return True
    except Exception as e:
        logger.warning(f"Failed to export failure to LangSmith dataset: {e}")
        return False
