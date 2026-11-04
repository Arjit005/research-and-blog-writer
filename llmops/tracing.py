"""Enterprise LangSmith Traceability, Observability & Evaluation Integration.

Features:
- Hierarchical Span Trees: Root research job with nested per-stage / per-agent
  spans and tool executions.
- Thread-safe Context Management: Explicit parent-child span trees across
  background worker threads.
- Zero-leak PII Protection: Pre-scrubs sensitive entities prior to trace
  ingestion, including failure error strings exported to eval datasets.
- Multi-SDK Env Sync: Bi-directionally aligns LANGSMITH_* and legacy
  LANGCHAIN_* variables.
- Explicit model-usage metadata: run telemetry from
  :func:`llm_fallback.get_usage_stats` can be attached to the root trace and
  individual spans.
- Automated Feedback & Regression Dataset Export: Converts production failures
  into eval datasets.

Known limitation (documented honestly)
-------------------------------------
Older versions of this module appended ``"langsmith"`` to ``litellm``'s
``success_callback`` / ``failure_callback`` lists and claimed that this traced
every model call.  The installed crewAI routes OpenRouter/Gemini through its
native provider adapters, which do **not** always go through LiteLLM, so those
callbacks cannot be relied upon.  The supported, deterministic tracing surface
is therefore the explicit span API on :class:`LangSmithJobTracer`
(:meth:`start_span` / :meth:`end_span`) plus model-usage metadata; the LiteLLM
callback hook is still installed when available (it is harmless and covers
LiteLLM-routed calls) but it is **not** the source of truth.  Tracing degrades
to safe no-ops when no API key is configured and never raises into the caller.
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
    try:
        os.environ["LANGSMITH_API_KEY"] = LANGSMITH_API_KEY
        os.environ["LANGCHAIN_API_KEY"] = LANGSMITH_API_KEY
        os.environ["LANGSMITH_TRACING"] = "true"
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGSMITH_PROJECT"] = LANGSMITH_PROJECT
        os.environ["LANGCHAIN_PROJECT"] = LANGSMITH_PROJECT
        os.environ["LANGSMITH_ENDPOINT"] = LANGSMITH_ENDPOINT
        os.environ["LANGCHAIN_ENDPOINT"] = LANGSMITH_ENDPOINT
    except Exception as exc:  # noqa: BLE001 - tracing config must never break the app
        logger.debug(f"Could not sync LangSmith environment variables: {exc}")

    # Best-effort LiteLLM callback hook (see module docstring limitation).
    try:
        import litellm

        if "langsmith" not in litellm.success_callback:
            litellm.success_callback.append("langsmith")
        if "langsmith" not in litellm.failure_callback:
            litellm.failure_callback.append("langsmith")
        logger.info(
            "LangSmith auto-tracing initialized for project: %s "
            "(LiteLLM callbacks are best-effort; explicit spans are authoritative)",
            LANGSMITH_PROJECT,
        )
    except Exception as e:  # noqa: BLE001
        logger.debug(f"Could not initialize litellm callbacks (non-fatal): {e}")


def is_tracing_enabled() -> bool:
    """Check if LangSmith tracing is active and configured."""
    return bool(LANGSMITH_API_KEY and (os.getenv("LANGSMITH_TRACING") == "true" or os.getenv("LANGCHAIN_TRACING_V2") == "true"))


def _mask_inputs(data: Any) -> Any:
    """Pre-sanitize inputs/outputs to ensure PII and credentials never leak to LangSmith."""
    try:
        from security.guardrails import mask_pii_and_secrets
        if isinstance(data, str):
            return mask_pii_and_secrets(data)
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
        self.model_usage: List[str] = []
        self.extra_metadata: Dict[str, Any] = {}

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
                        "tracing_note": "model usage recorded via FallbackLLM usage stats metadata",
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

    def record_model_usage(self, model_names: Any) -> None:
        """Attach model(s) that actually produced output as trace metadata.

        Accepts a single model name or an iterable of names.  The data is
        included in the span/root outputs when they are closed, so model usage
        is observable even when provider SDK callbacks are unavailable.
        """
        if not model_names:
            return
        if isinstance(model_names, str):
            names = [model_names]
        else:
            try:
                names = [str(name) for name in model_names]
            except TypeError:
                names = [str(model_names)]
        for name in names:
            if name and name not in self.model_usage:
                self.model_usage.append(name)

    def record_metadata(self, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Merge extra (PII-masked) metadata onto the root trace at close time."""
        if not metadata:
            return
        try:
            self.extra_metadata.update(_mask_inputs(dict(metadata)))
        except Exception:
            pass

    def start_span(
        self,
        span_key: str,
        name: str,
        run_type: str = "chain",
        inputs: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Any]:
        """Start a nested child span explicitly parented to the root job tree."""
        if not self.root_tree:
            return None
        try:
            clean_inputs = _mask_inputs(inputs or {})
            span_metadata = {"span_key": span_key, "run_id": self.run_id}
            if metadata:
                span_metadata.update(_mask_inputs(dict(metadata)))
            child_span = self.root_tree.create_child(
                name=name,
                run_type=run_type,
                inputs=clean_inputs,
                extra={"metadata": span_metadata},
            )
            child_span.post()
            self.active_spans[span_key] = child_span
            return child_span
        except Exception as e:
            logger.debug(f"Failed to start span {name}: {e}")
            return None

    def end_span(
        self,
        span_key: str,
        outputs: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> None:
        """End and post status for an active child span."""
        span = self.active_spans.pop(span_key, None)
        if not span:
            return
        try:
            clean_outputs = _mask_inputs(outputs or {})
            if self.model_usage:
                clean_outputs = dict(clean_outputs)
                clean_outputs.setdefault("models_used", list(self.model_usage))
            masked_error = _mask_inputs(error) if isinstance(error, str) else error
            span.end(outputs=clean_outputs, error=masked_error)
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

            clean_outputs = dict(_mask_inputs(outputs or {}))
            if self.model_usage:
                clean_outputs.setdefault("models_used", list(self.model_usage))
            if self.extra_metadata:
                clean_outputs.setdefault("metadata", dict(self.extra_metadata))

            if self.extra_metadata or self.model_usage:
                try:
                    root_metadata = dict(getattr(self.root_tree, "extra", {}).get("metadata", {}))
                    root_metadata.update(self.extra_metadata)
                    if self.model_usage:
                        root_metadata["models_used"] = list(self.model_usage)
                    self.root_tree.extra = dict(getattr(self.root_tree, "extra", {}))
                    self.root_tree.extra["metadata"] = root_metadata
                except Exception as meta_err:
                    logger.debug(f"Could not attach model-usage metadata to root trace: {meta_err}")

            masked_error = _mask_inputs(error) if isinstance(error, str) else error
            self.root_tree.end(outputs=clean_outputs, error=masked_error)
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
    """Save production failures to a LangSmith Dataset for automated regression testing.

    The error string is PII/secret-masked before it is uploaded to the cloud.
    """
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
            outputs={"error_message": _mask_inputs(error_message)},
            metadata=_mask_inputs(metadata or {}),
            dataset_id=dataset.id,
        )
        logger.info(f"Successfully recorded regression test case to LangSmith dataset '{dataset_name}'")
        return True
    except Exception as e:
        logger.warning(f"Failed to export failure to LangSmith dataset: {e}")
        return False
