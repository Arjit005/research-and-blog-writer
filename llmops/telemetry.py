"""LLMOps Telemetry, Latency Tracking & Evaluation Engine.

Provides:
- End-to-end execution latency measurement
- Token estimation & model usage accounting (clearly labelled as estimates)
- Fallback event monitoring with the SAME key names consumers render
  (``failed_model`` / ``switched_to`` / ``error_type``)
- Automated readability & content quality scoring

The tracker is populated from two production sources:

* :func:`llm_fallback.get_usage_stats` (real model/fallback telemetry), wired
  through :meth:`TelemetryTracker.record_usage_stats`, and
* explicit per-stage timing / security events recorded by the runners.
"""

from __future__ import annotations

import re
import threading
import time
from typing import Any, Dict, List, Optional


# Fenced code blocks (```...```) and inline code spans (`...`) inflate a prose
# token estimate; they are excluded from token accounting by default.
_FENCED_CODE_RE = re.compile(r"```[\s\S]*?```")
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")


def estimate_tokens(text: str, ignore_code_blocks: bool = True) -> int:
    """Estimate token count (~4 chars/token) of natural-language text.

    This is a heuristic **estimate**, not a tokenizer count.  Fenced code
    blocks / Mermaid diagrams and inline code spans are ignored by default so
    prose estimates are not inflated by verbose diagram sources.
    """
    if not text:
        return 0
    sample = str(text)
    if ignore_code_blocks:
        sample = _FENCED_CODE_RE.sub(" ", sample)
        sample = _INLINE_CODE_RE.sub(" ", sample)
    sample = re.sub(r"\s+", " ", sample).strip()
    return max(1, int(len(sample) / 4)) if sample else 0


def count_syllables(word: str) -> int:
    """Heuristic syllable counter for readability scoring."""
    word = word.lower()
    if len(word) <= 3:
        return 1
    word = re.sub(r"(?:[^laeiouy]|ed|es|e)$", "", word)
    word = re.sub(r"^y", "", word)
    matches = re.findall(r"[aeiouy]{1,2}", word)
    return max(1, len(matches))


def calculate_readability(text: str) -> Dict[str, Any]:
    """Calculate Flesch Reading Ease score and content statistics.

    Score Range:
        90-100: Very Easy
        60-70: Standard / Conversational
        30-50: Difficult (College level)
        0-30: Very Confusing
    """
    if not text or not text.strip():
        return {
            "score": 0.0,
            "grade": "N/A",
            "word_count": 0,
            "sentence_count": 0,
            "avg_words_per_sentence": 0.0,
        }

    words = re.findall(r"\b[A-Za-z0-9'-]+\b", text)
    sentences = re.split(r"[.!?]+", text)
    sentences = [s.strip() for s in sentences if s.strip()]

    word_count = len(words)
    sentence_count = max(1, len(sentences))

    if word_count == 0:
        return {
            "score": 0.0,
            "grade": "N/A",
            "word_count": 0,
            "sentence_count": 0,
            "avg_words_per_sentence": 0.0,
        }

    total_syllables = sum(count_syllables(w) for w in words)
    words_per_sentence = word_count / sentence_count
    syllables_per_word = total_syllables / word_count

    # Flesch Reading Ease Formula
    score = 206.835 - (1.015 * words_per_sentence) - (84.6 * syllables_per_word)
    score = max(0.0, min(100.0, round(score, 1)))

    if score >= 80:
        grade = "Easy & Engaging"
    elif score >= 60:
        grade = "Standard (Optimal for Tech Blog)"
    elif score >= 40:
        grade = "Advanced & Technical"
    else:
        grade = "Dense / Academic"

    return {
        "score": score,
        "grade": grade,
        "word_count": word_count,
        "sentence_count": sentence_count,
        "avg_words_per_sentence": round(words_per_sentence, 1),
    }


class TelemetryTracker:
    """Manages telemetry, model failover logs, and metrics for an execution run."""

    def __init__(self, topic: str):
        self.topic = topic
        self.start_time = time.time()
        self.end_time: Optional[float] = None
        self.models_used: List[str] = []
        self.failed_models: List[str] = []
        self.fallback_events: List[Dict[str, Any]] = []
        self.security_events: List[Dict[str, Any]] = []
        self.stage_timings: Dict[str, float] = {}
        self.llm_call_count: int = 0
        self._current_stage_start: Optional[float] = None
        self._lock = threading.Lock()

    # -- stage timing ------------------------------------------------------
    def start_stage(self, stage_name: str) -> None:
        """Mark start of a pipeline stage."""
        self._current_stage_start = time.time()

    def end_stage(self, stage_name: str) -> None:
        """Record duration of a pipeline stage."""
        if self._current_stage_start:
            elapsed = time.time() - self._current_stage_start
            with self._lock:
                self.stage_timings[stage_name] = round(elapsed, 2)
            self._current_stage_start = None

    # -- model / fallback accounting --------------------------------------
    def record_model_usage(self, model_name: str) -> None:
        """Track which model successfully generated output."""
        if not model_name:
            return
        with self._lock:
            if model_name not in self.models_used:
                self.models_used.append(model_name)

    def record_fallback(
        self,
        failed_model: str,
        error: str = "",
        next_model: str = "",
        error_type: Optional[str] = None,
    ) -> None:
        """Record a model failover event.

        Writes the canonical keys consumed by the dashboard/API:
        ``failed_model``, ``switched_to``, ``error_type`` (plus the raw
        ``error`` string and a timestamp for debugging).
        """
        if error_type is None:
            try:
                from llm_fallback import classify_error

                error_type = classify_error(RuntimeError(str(error)))
            except Exception:
                error_type = "other"
        with self._lock:
            self.fallback_events.append({
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "failed_model": failed_model,
                "switched_to": next_model,
                "error_type": error_type,
                "error": str(error)[:200],
            })

    def record_usage_stats(self, usage_stats: Optional[Dict[str, Any]] = None) -> None:
        """Ingest a snapshot from :func:`llm_fallback.get_usage_stats`.

        This is the production wiring point that turns real FallbackLLM
        telemetry into persisted run telemetry (previously the tracker methods
        had no callers and dashboards showed invented data).
        """
        if usage_stats is None:
            try:
                from llm_fallback import get_usage_stats

                usage_stats = get_usage_stats()
            except Exception:
                return
        if not isinstance(usage_stats, dict):
            return

        with self._lock:
            for model_name in usage_stats.get("models_used", []) or []:
                if model_name and model_name not in self.models_used:
                    self.models_used.append(model_name)
            for model_name in usage_stats.get("failed_models", []) or []:
                if model_name and model_name not in self.failed_models:
                    self.failed_models.append(model_name)
            self.llm_call_count = int(usage_stats.get("call_count", self.llm_call_count) or 0)

        for event in usage_stats.get("fallback_events", []) or []:
            if not isinstance(event, dict):
                continue
            failed = event.get("failed_model", "")
            switched = event.get("switched_to", "")
            self.record_fallback(
                failed_model=failed,
                error=str(event.get("error", "")),
                next_model=switched,
                error_type=str(event.get("error_type", "other")),
            )

    def record_security_event(self, event_type: str, details: str) -> None:
        """Record a detected or prevented security event."""
        with self._lock:
            self.security_events.append({
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "type": event_type,
                "details": details,
            })

    # -- finalization ------------------------------------------------------
    def finalize(self, report_text: str = "") -> Dict[str, Any]:
        """Finalize metrics calculation and return comprehensive telemetry payload."""
        self.end_time = time.time()
        duration_sec = round(self.end_time - self.start_time, 2)
        readability = calculate_readability(report_text)
        # Honest estimate only: report prose tokens (code/Mermaid excluded).
        # No invented per-topic multiplier is added.
        tokens = estimate_tokens(report_text)

        with self._lock:
            fallback_events = [dict(event) for event in self.fallback_events]
            fallback_count = len(fallback_events)
            models_used = list(self.models_used)
            failed_models = list(self.failed_models)
            security_events = list(self.security_events)
            stage_timings = dict(self.stage_timings)
            llm_call_count = self.llm_call_count

        return {
            "topic": self.topic,
            "duration_sec": duration_sec,
            "tokens_estimated": tokens,
            "tokens_estimated_is_estimate": True,
            "models_used": models_used,
            "failed_models": failed_models,
            "fallback_count": fallback_count,
            "fallback_events": fallback_events,
            "security_events": security_events,
            "stage_timings": stage_timings,
            "llm_call_count": llm_call_count,
            "readability": readability,
        }
