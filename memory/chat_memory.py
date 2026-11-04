"""Chat memory management — sliding window, rolling summaries, and context compaction."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class ChatMemoryManager:
    """Manages conversational context budgets for the interactive Copilot chat.

    Features:
    - Token-budgeted sliding window: keeps the last K turns verbatim.
    - Incremental rolling summary: distills older conversational turns into a concise running summary.
    - Selective article injection: dynamically selects full report or compact outline based on query intent.
    - Injects persistent user memory (author guidelines, preferred style).
    """

    def __init__(self, max_turns: int = 6):
        self.max_turns = max_turns

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
        """Condense older turns into a bulleted summary of key topics and decisions."""
        if not turns:
            return existing_summary

        points = []
        if existing_summary.strip():
            points.append(existing_summary.strip())

        for turn in turns:
            role = turn.get("role", "user")
            content = turn.get("content", "").strip()
            # Truncate content line
            first_line = content.splitlines()[0] if content else ""
            summary_snippet = first_line[:120] + ("..." if len(first_line) > 120 else "")
            if role == "user":
                points.append(f"- User requested: {summary_snippet}")
            else:
                points.append(f"- Assistant provided: {summary_snippet}")

        # Keep summary bounded to ~8 key bullets
        return "\n".join(points[-8:])

    def build_bounded_context(
        self,
        chat_history: List[Dict[str, str]],
        current_report: str,
        active_query: str,
        article_id: Optional[int] = None,
        user_memories: Optional[Dict[str, str]] = None,
    ) -> List[Dict[str, str]]:
        """Construct the prompt messages array fitting strictly within token boundaries."""
        running_summary = ""

        # Fetch prior rolling summary from database if article_id is given
        if article_id:
            try:
                from database import get_chat_session, save_chat_session
                session_data = get_chat_session(article_id)
                if session_data and session_data.get("running_summary"):
                    running_summary = session_data["running_summary"]
            except Exception as e:
                logger.debug(f"Could not load chat session summary: {e}")

        # Split history into older turns and recent window
        if len(chat_history) > self.max_turns:
            older_turns = chat_history[:-self.max_turns]
            recent_turns = chat_history[-self.max_turns:]
            running_summary = self.summarize_turns(older_turns, existing_summary=running_summary)

            # Persist updated summary back to database
            if article_id:
                try:
                    from database import save_chat_session
                    save_chat_session(article_id, running_summary, len(chat_history))
                except Exception as e:
                    logger.debug(f"Could not save chat session summary: {e}")
        else:
            recent_turns = chat_history

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
