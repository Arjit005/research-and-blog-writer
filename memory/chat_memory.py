"""Chat memory management — sliding window, rolling summaries, and context compaction.

The window is bounded by **both** a turn count and a cheap token budget
(chars/4 heuristic, configurable via ``CHAT_MEMORY_MAX_TOKENS``).  Older turns
are folded into a rolling summary that *retains* the previously persisted
summary instead of dropping it once enough new turns accumulate.

All chat-session reads/writes are scoped by ``user_id`` (when supplied) so two
users can never read or overwrite each other's rolling conversation summary.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOKENS = 6000
DEFAULT_MAX_TURNS = 6
DEFAULT_MAX_SUMMARY_CHARS = 2000


def _env_int(name: str, default: int) -> int:
    """Read a positive int environment variable, ignoring malformed values."""
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        logger.warning("Ignoring invalid %s=%r (expected int)", name, raw)
        return default


def estimate_message_tokens(text: str) -> int:
    """Cheap token estimate (~4 chars/token) used for window budgeting."""
    if not text:
        return 0
    return max(1, int(len(str(text)) / 4))


class ChatMemoryManager:
    """Manages conversational context budgets for the interactive Copilot chat.

    Features:
    - Token-budgeted sliding window: keeps the most recent turns within a
      configurable token budget (and a hard turn cap).
    - Incremental rolling summary: distills older conversational turns into a
      concise running summary, merging (never discarding) the persisted summary.
    - Selective article injection: dynamically selects full report or compact
      outline based on query intent.
    - Injects persistent user memory (author guidelines, preferred style).
    - ``user_id``-scoped chat-session persistence.
    """

    def __init__(
        self,
        max_turns: int = DEFAULT_MAX_TURNS,
        max_tokens: Optional[int] = None,
        max_summary_chars: Optional[int] = None,
    ):
        self.max_turns = max(1, int(max_turns))
        self.max_tokens = int(max_tokens) if max_tokens is not None else _env_int(
            "CHAT_MEMORY_MAX_TOKENS", DEFAULT_MAX_TOKENS
        )
        self.max_summary_chars = int(max_summary_chars) if max_summary_chars is not None else _env_int(
            "CHAT_MEMORY_MAX_SUMMARY_CHARS", DEFAULT_MAX_SUMMARY_CHARS
        )

    def select_article_context(self, full_article: str, query: str) -> str:
        """Select full report or compact outline depending on user intent to save tokens."""
        if not full_article:
            return "No article context available."

        q_lower = query.lower()

        # Queries requiring the full text (re-writing, overall transformations, social threads)
        full_triggers = [
            "full", "entire", "whole", "rewrite", "translate", "linkedin",
            "twitter", "tweet", "summary", "executive", "all sections", "quiz"
        ]
        if any(trigger in q_lower for trigger in full_triggers):
            return full_article

        # For quick questions or specific sections, construct a compact outline + excerpt
        lines = full_article.splitlines()
        headings = [line for line in lines if line.startswith("#")]
        outline_str = "\n".join(headings[:15])

        # If user refers to a specific heading keyword, extract that section
        matching_section = []
        capture = False
        words = [w for w in re.findall(r"\w+", q_lower) if len(w) > 3]

        for line in lines:
            if line.startswith("#"):
                if any(w in line.lower() for w in words):
                    capture = True
                elif capture and line.startswith("## "):
                    capture = False
            if capture:
                matching_section.append(line)

        if matching_section:
            return f"### Article Outline:\n{outline_str}\n\n### Relevant Section Detail:\n" + "\n".join(matching_section[:50])

        # Default: Outline + First 800 words
        words_sample = " ".join(full_article.split()[:800])
        return f"### Article Outline:\n{outline_str}\n\n### Executive Overview & Initial Sections:\n{words_sample}..."

    def summarize_turns(self, turns: List[Dict[str, str]], existing_summary: str = "") -> str:
        """Condense older turns into a bulleted summary of key topics and decisions.

        The previously persisted summary is *retained* (never silently dropped):
        new bullets are appended until the summary character budget is reached,
        and the oldest new bullets are shed first.
        """
        if not turns and not existing_summary:
            return existing_summary

        new_bullets: List[str] = []
        for turn in turns:
            role = turn.get("role", "user")
            content = str(turn.get("content", "")).strip()
            first_line = content.splitlines()[0] if content else ""
            summary_snippet = first_line[:120] + ("..." if len(first_line) > 120 else "")
            if role == "user":
                new_bullets.append(f"- User requested: {summary_snippet}")
            else:
                new_bullets.append(f"- Assistant provided: {summary_snippet}")

        # Bound the number of freshly generated bullets and always keep the newest.
        new_bullets = new_bullets[-8:]

        existing = (existing_summary or "").strip()
        if len(existing) > self.max_summary_chars:
            existing = existing[: self.max_summary_chars].rstrip() + " …"

        sections: List[str] = [existing] if existing else []
        text = "\n".join(sections + new_bullets)
        while len(text) > self.max_summary_chars and new_bullets:
            new_bullets.pop(0)
            text = "\n".join(sections + new_bullets)
        if len(text) > self.max_summary_chars:
            text = text[: self.max_summary_chars].rstrip() + " …"
        return text

    def _select_window(self, chat_history: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Select the most recent turns fitting the token budget and turn cap."""
        recent_turns: List[Dict[str, str]] = []
        used_tokens = 0
        for turn in reversed(chat_history):
            role = str(turn.get("role", ""))
            content = str(turn.get("content", ""))
            cost = estimate_message_tokens(role) + estimate_message_tokens(content)
            if recent_turns and (
                len(recent_turns) >= self.max_turns or used_tokens + cost > self.max_tokens
            ):
                break
            recent_turns.append(turn)
            used_tokens += cost
        recent_turns.reverse()
        return recent_turns

    def build_bounded_context(
        self,
        chat_history: List[Dict[str, str]],
        current_report: str,
        active_query: str,
        article_id: Optional[int] = None,
        user_memories: Optional[Dict[str, str]] = None,
        user_id: Optional[int] = None,
    ) -> List[Dict[str, str]]:
        """Construct the prompt messages array fitting strictly within token boundaries."""
        running_summary = ""

        # Fetch prior rolling summary from database if article_id is given (user-scoped).
        if article_id:
            try:
                from database import get_chat_session

                session_data = get_chat_session(article_id, user_id=user_id)
                if session_data and session_data.get("running_summary"):
                    running_summary = session_data["running_summary"]
            except Exception as e:
                logger.debug(f"Could not load chat session summary: {e}")

        # Split history into older turns and the token/turn-bounded recent window.
        recent_turns = self._select_window(chat_history)
        older_turns = chat_history[: len(chat_history) - len(recent_turns)]
        if older_turns:
            running_summary = self.summarize_turns(older_turns, existing_summary=running_summary)

            # Persist updated summary back to database (user-scoped).
            if article_id:
                try:
                    from database import save_chat_session

                    save_chat_session(
                        article_id,
                        running_summary,
                        len(chat_history),
                        user_id=user_id,
                    )
                except Exception as e:
                    logger.debug(f"Could not save chat session summary: {e}")

        # Select optimized article context
        article_context = self.select_article_context(current_report, active_query)

        # Build persistent user memory guidance block
        mem_block = ""
        if user_memories:
            mem_lines = [f"- {k}: {v}" for k, v in user_memories.items() if v]
            if mem_lines:
                mem_block = "\n### 🧠 Author Style & Editorial Guidelines:\n" + "\n".join(mem_lines) + "\n"

        summary_block = ""
        if running_summary:
            summary_block = f"\n### 📝 Prior Conversation Summary:\n{running_summary}\n"

        system_prompt = (
            "You are the Senior Editorial Copilot for this multi-agent research team. "
            "You assist the user with high precision, authoritative technical prose, "
            "exact citations, and thoughtful revisions based on the report.\n"
            f"{mem_block}"
            f"{summary_block}\n"
            "=== GENERATED REPORT CONTEXT ===\n"
            f"{article_context}\n"
            "=================================\n"
        )

        messages = [{"role": "system", "content": system_prompt}]
        for turn in recent_turns:
            messages.append({"role": turn["role"], "content": turn["content"]})

        return messages
