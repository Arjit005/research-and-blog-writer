"""Unit tests for Export Suite (slugification, Markdown and HTML bundle compilation)."""

import pytest
from ui.export import slugify, get_article_filename, generate_standalone_html


def test_slugify_variations():
    """Verify that slugify cleans special characters, emojis, and spaces correctly."""
    assert slugify("AI Agents in 2026: Architectures & Benchmarks!") == "ai-agents-in-2026-architectures-benchmarks"
    assert slugify("🚀 Next-Gen LLMOps") == "next-gen-llmops"
    assert slugify("   Multiple   Spaces   ") == "multiple-spaces"
    assert slugify("") == "article"


def test_get_article_filename():
    """Verify clean extensions and filenames."""
    assert get_article_filename("AI Topic", "md") == "ai-topic.md"
    assert get_article_filename("AI Topic", ".html") == "ai-topic.html"


def test_standalone_html_diagram_count_and_utf8():
    """Verify standalone HTML compilation embeds diagrams, tables, and UTF-8 charset."""
    topic = "LLMOps & Tokyo (東京) Architecture"
    content = (
        "# Introduction to Tokyo LLMOps\n\n"
        "Here is a table:\n\n"
        "| Framework | Latency |\n"
        "|---|---|\n"
        "| vLLM | 12ms |\n\n"
        "```mermaid\nflowchart LR\n  A[Tokyo Ingestion] --> B[TiDB Cloud]\n```\n\n"
        "Conclusion text with special characters: © 2026, café, & <safe tags>."
    )

    filename, html_bundle = generate_standalone_html(topic, content)

    assert filename == "llmops-tokyo-architecture.html"
    assert '<meta charset="UTF-8">' in html_bundle
    assert "Tokyo (東京) Architecture" in html_bundle
    assert '<pre class="mermaid">' in html_bundle
    assert "Tokyo Ingestion" in html_bundle
    assert "1 Architecture Diagram" in html_bundle
    assert "<table>" in html_bundle
    assert "vLLM" in html_bundle
    assert "mermaid.initialize" in html_bundle
    assert "securityLevel: 'strict'" in html_bundle


def test_standalone_html_escapes_malicious_diagram_source():
    """Diagram source containing </script> must not escape the <pre class="mermaid"> context."""
    malicious = 'flowchart TD\n  A["</script><script>alert(1)</script>"] --> B'
    _, html_bundle = generate_standalone_html("XSS Topic", f"Intro.\n\n```mermaid\n{malicious}\n```\n\nOutro.")
    # Only the single real module-closing </script> tag survives.
    assert html_bundle.count("</script>") == 1
    assert "&lt;/script&gt;" in html_bundle
