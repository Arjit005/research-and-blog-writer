"""LLMOps Telemetry, Latency Tracking & Evaluation Engine.

Provides:
- End-to-end execution latency measurement
- Token estimation & model usage accounting
- Fallback event monitoring
- Automated readability & content quality scoring
"""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional


def estimate_tokens(text: str) -> int:
    """Estimate token count based on common word/subword heuristic (~4 chars/token)."""
    if not text:
        return 0
    return max(1, int(len(text) / 4))


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
        self.fallback_events: List[Dict[str, Any]] = []
        self.security_events: List[Dict[str, Any]] = []
        self.stage_timings: Dict[str, float] = {}
        self._current_stage_start: Optional[float] = None

    def start_stage(self, stage_name: str) -> None:
        """Mark start of a pipeline stage."""
        self._current_stage_start = time.time()

    def end_stage(self, stage_name: str) -> None:
        """Record duration of a pipeline stage."""
        if self._current_stage_start:
            elapsed = time.time() - self._current_stage_start
            self.stage_timings[stage_name] = round(elapsed, 2)
            self._current_stage_start = None

    def record_model_usage(self, model_name: str) -> None:
        """Track which model successfully generated output."""
        if model_name not in self.models_used:
            self.models_used.append(model_name)

    def record_fallback(self, failed_model: str, error: str, next_model: str) -> None:
        """Record a model failover event."""
        self.fallback_events.append({
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "failed_model": failed_model,
            "error": str(error)[:200],
            "switched_to": next_model,
        })

    def record_security_event(self, event_type: str, details: str) -> None:
        """Record a detected or prevented security event."""
        self.security_events.append({
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "type": event_type,
            "details": details,
        })

    def finalize(self, report_text: str = "") -> Dict[str, Any]:
        """Finalize metrics calculation and return comprehensive telemetry payload."""
        self.end_time = time.time()
        duration_sec = round(self.end_time - self.start_time, 2)
        readability = calculate_readability(report_text)
        tokens = estimate_tokens(report_text) + estimate_tokens(self.topic) * 10

        return {
            "topic": self.topic,
            "duration_sec": duration_sec,
            "tokens_estimated": tokens,
            "models_used": self.models_used,
            "fallback_count": len(self.fallback_events),
            "fallback_events": self.fallback_events,
            "security_events": self.security_events,
            "stage_timings": self.stage_timings,
            "readability": readability,
        }
