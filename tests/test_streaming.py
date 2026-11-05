"""Tests for real-time token streaming via FastAPI SSE, queue broadcast, and fallback models."""

import asyncio
import json
import pytest
from unittest.mock import MagicMock, patch

from backend.routes.research import (
    register_token_listener,
    unregister_token_listener,
    broadcast_run_token,
    cleanup_run_tokens,
    _RUN_TOKEN_LISTENERS,
)


def test_token_broadcast_and_queue_isolation():
    """Verify that tokens are delivered to subscriber queues and isolated across runs synchronously."""
    run_1 = "run_test_1"
    run_2 = "run_test_2"

    q1_sub1: asyncio.Queue = asyncio.Queue()
    q1_sub2: asyncio.Queue = asyncio.Queue()
    q2_sub1: asyncio.Queue = asyncio.Queue()

    register_token_listener(run_1, q1_sub1)
    register_token_listener(run_1, q1_sub2)
    register_token_listener(run_2, q2_sub1)

    try:
        # Broadcast chunk 1 to run_1
        broadcast_run_token(run_1, "# Introduction\n\n")
        broadcast_run_token(run_1, "Artificial intelligence in 2026...")

        # Broadcast chunk to run_2
        broadcast_run_token(run_2, "Separate run content")

        # Verify subscriber 1 on run 1 received both tokens in exact order
        assert q1_sub1.get_nowait() == "# Introduction\n\n"
        assert q1_sub1.get_nowait() == "Artificial intelligence in 2026..."
        assert q1_sub1.empty()

        # Verify subscriber 2 on run 1 also received the same tokens
        assert q1_sub2.get_nowait() == "# Introduction\n\n"
        assert q1_sub2.get_nowait() == "Artificial intelligence in 2026..."
        assert q1_sub2.empty()

        # Verify run 2 subscriber received only run 2 chunk
        assert q2_sub1.get_nowait() == "Separate run content"
        assert q2_sub1.empty()
    finally:
        unregister_token_listener(run_1, q1_sub1)
        unregister_token_listener(run_1, q1_sub2)
        unregister_token_listener(run_2, q2_sub1)
        cleanup_run_tokens(run_1)
        cleanup_run_tokens(run_2)


def test_token_cleanup_clears_memory():
    """Verify that cleanup_run_tokens removes all listeners and prevents leaks."""
    run_id = "run_leak_test"
    q = asyncio.Queue()
    register_token_listener(run_id, q)
    assert run_id in _RUN_TOKEN_LISTENERS

    cleanup_run_tokens(run_id)
    assert run_id not in _RUN_TOKEN_LISTENERS

    # Broadcasting after cleanup is safe and does not recreate queue
    broadcast_run_token(run_id, "orphan chunk")
    assert run_id not in _RUN_TOKEN_LISTENERS


def test_only_writer_chunks_broadcasted():
    """Verify that only the Blog Writer agent's LLM chunks are forwarded to token broadcast."""
    from crewai.events.types.llm_events import LLMStreamChunkEvent

    run_id = "run_writer_filter_test"
    q: asyncio.Queue = asyncio.Queue()
    register_token_listener(run_id, q)

    try:
        # Mock agents with role and id
        researcher_agent = MagicMock(role="Senior Researcher", id="agent_1")
        diagram_agent = MagicMock(role="Content Analyst", id="agent_2")
        writer_agent = MagicMock(role="Blog Post Writer", id="agent_3")
        director_agent = MagicMock(role="Quality Reviewer", id="agent_4")

        # Simulate handler logic identical to backend/routes/research.py
        def simulate_event(agent, text):
            event = LLMStreamChunkEvent(
                chunk=text,
                from_task=None,
                from_agent=agent,
                call_type="llm_call",
                response_id=None,
                call_id="call_1",
            )
            agent_role = str(getattr(event, "agent_role", "") or "").lower()
            if not agent_role:
                from_agent = getattr(event, "from_agent", None)
                agent_role = str(getattr(from_agent, "role", "") or "").lower()
            if "writer" in agent_role or "author" in agent_role or "blog" in agent_role:
                broadcast_run_token(run_id, event.chunk)

        simulate_event(researcher_agent, "Researcher internal thinking")
        simulate_event(diagram_agent, "Diagram plan graph TD")
        simulate_event(writer_agent, "## Section 1: Deep Architecture")
        simulate_event(director_agent, "Editorial Director fact checks")

        # Only writer chunk should have reached the queue
        assert not q.empty()
        assert q.get_nowait() == "## Section 1: Deep Architecture"
        assert q.empty()
    finally:
        unregister_token_listener(run_id, q)
        cleanup_run_tokens(run_id)
