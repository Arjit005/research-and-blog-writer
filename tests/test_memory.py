"""Unit tests for Context and Memory Management architecture."""

import pytest
from unittest.mock import patch, MagicMock
from memory.chat_memory import ChatMemoryManager
from tools.scrape_tool import compact_scraped_text, ScrapeTool
import database as db


def test_compact_scraped_text_normal():
    """Verify whitespace cleanup and text preservation."""
    raw = "Line 1\n\n\n\n\nLine 2\n\n\nLine 3"
    compacted = compact_scraped_text(raw, max_words=50)
    assert "\n\n\n" not in compacted
    assert "Line 1\n\nLine 2\n\nLine 3" == compacted


def test_compact_scraped_text_budget_truncation():
    """Verify max word budget truncation."""
    words = ["word"] * 200
    long_text = " ".join(words)
    compacted = compact_scraped_text(long_text, max_words=50)
    assert len(compacted.split()) <= 65
    assert "truncated" in compacted


def test_chat_memory_select_article_context_full():
    """Verify that full transformations trigger full article injection."""
    mgr = ChatMemoryManager()
    article = "# Title\n\nSome deep technical details."
    assert mgr.select_article_context(article, "Rewrite the entire blog post") == article
    assert mgr.select_article_context(article, "3x LinkedIn Posts") == article


def test_chat_memory_select_article_context_compact():
    """Verify that specific questions inject compact outline rather than full article."""
    mgr = ChatMemoryManager()
    article = "# Title\n\n## Section 1\nDetails 1\n\n## Section 2\nDetails 2"
    ctx = mgr.select_article_context(article, "What is covered in Section 1?")
    assert "### Article Outline:" in ctx
    assert "### Relevant Section Detail:" in ctx


def test_chat_memory_sliding_window_and_summarization():
    """Verify sliding window bounds turns and compresses older ones."""
    mgr = ChatMemoryManager(max_turns=2)
    history = [
        {"role": "user", "content": "What is PagedAttention?"},
        {"role": "assistant", "content": "PagedAttention is a memory management algorithm..."},
        {"role": "user", "content": "How does it compare to vLLM?"},
        {"role": "assistant", "content": "vLLM implements PagedAttention..."},
        {"role": "user", "content": "Give me code sample."},
    ]
    messages = mgr.build_bounded_context(
        chat_history=history,
        current_report="# Report\nContent here",
        active_query="Give me code sample.",
        article_id=None,
        user_memories={"preferred_tone": "Formal", "prohibited_words": "delve"},
    )

    # 1 system message + 2 recent turns
    assert len(messages) == 3
    assert messages[0]["role"] == "system"
    assert "Prior Conversation Summary:" in messages[0]["content"]
    assert "PagedAttention" in messages[0]["content"]
    assert "Author Style & Editorial Guidelines:" in messages[0]["content"]


def test_database_research_cache_crud():
    """Verify research cache insertion, retrieval, and updates."""
    test_url = "https://example.com/research-paper-test"
    test_content = "Extracted verified technical specifications for testing."

    db.set_cached_scrape(test_url, test_content)
    cached = db.get_cached_scrape(test_url)
    assert cached == test_content

    # Overwrite cache
    updated_content = "Updated technical specifications."
    db.set_cached_scrape(test_url, updated_content)
    assert db.get_cached_scrape(test_url) == updated_content


def test_database_user_memory_crud():
    """Verify user preferences persistent storage."""
    db.set_user_memory("preferred_tone", "Deep Technical", memory_type="preference")
    db.set_user_memory("prohibited_words", "delve, tapestry", memory_type="preference")

    mems = db.get_user_memories()
    assert mems.get("preferred_tone") == "Deep Technical"
    assert mems.get("prohibited_words") == "delve, tapestry"

    db.delete_user_memory("preferred_tone")
    mems_after = db.get_user_memories()
    assert "preferred_tone" not in mems_after


def test_database_chat_sessions_crud():
    """Verify chat session running summary persistence."""
    test_article_id = db.save_article("Test Article for Memory", "# Test Content")
    db.save_chat_session(test_article_id, "Summary: Discussed PagedAttention and KV cache.", message_count=8)

    session = db.get_chat_session(test_article_id)
    assert session is not None
    assert "PagedAttention" in session["running_summary"]
    assert session["message_count"] == 8


def test_scrape_tool_uses_cache():
    """Verify ScrapeTool returns cached content immediately without calling external scraper."""
    test_url = "https://example.com/cached-page"
    db.set_cached_scrape(test_url, "Pre-cached compact content from database.")

    tool = ScrapeTool()
    with patch("tools.scrape_tool.ScrapeWebsiteTool") as mock_scrape:
        result = tool._run(url=test_url)
        assert result == "Pre-cached compact content from database."
        mock_scrape.assert_not_called()
