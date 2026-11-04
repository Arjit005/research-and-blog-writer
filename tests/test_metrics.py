"""Unit tests for prose cleaning and honest metric calculations."""

import pytest
from ui.metrics import clean_article_prose, count_citations_in_references, calculate_clean_metrics


def test_clean_article_prose_strips_code_and_references():
    """Verify that fenced code, diagrams, and references are removed from prose."""
    markdown_doc = (
        "# Title of Document\n\n"
        "Here is a paragraph explaining autonomous agents in detail.\n\n"
        "```python\ndef execute():\n    print('Hello World')\n```\n\n"
        "Another paragraph with an image ![Diagram](https://example.com/fig.png).\n\n"
        "```mermaid\nflowchart TD\n  A --> B\n```\n\n"
        "## 📚 References & Verified Sources\n"
        "1. [Research Paper](https://arxiv.org/abs/2309.06180)\n"
        "2. [Documentation](https://docs.vllm.ai/)\n"
    )

    cleaned = clean_article_prose(markdown_doc)

    assert "def execute():" not in cleaned
    assert "flowchart TD" not in cleaned
    assert "https://arxiv.org" not in cleaned
    assert "Title of Document" in cleaned
    assert "explaining autonomous agents in detail" in cleaned
    assert "Another paragraph" in cleaned


def test_empty_article_returns_zeros():
    """Empty or None text must return clean zeros without error."""
    metrics_empty = calculate_clean_metrics("")
    assert metrics_empty["word_count"] == 0
    assert metrics_empty["read_time_min"] == 0
    assert metrics_empty["citation_count"] == 0

    metrics_none = calculate_clean_metrics(None)
    assert metrics_none["word_count"] == 0


def test_citation_counting_variations():
    """Verify citation counting across different heading styles."""
    doc_1 = (
        "Some text.\n\n"
        "## References\n"
        "- https://github.com/vllm-project/vllm\n"
        "- https://arxiv.org/abs/2309.06180\n"
    )
    assert count_citations_in_references(doc_1) == 2

    doc_2 = (
        "Some text.\n\n"
        "### 📚 Verified Sources\n"
        "[1] https://tidbcloud.com\n"
        "[2] https://openrouter.ai\n"
        "[3] https://crewai.com\n"
    )
    assert count_citations_in_references(doc_2) == 3

    doc_no_refs = "Just text without any bibliography section."
    assert count_citations_in_references(doc_no_refs) == 0
