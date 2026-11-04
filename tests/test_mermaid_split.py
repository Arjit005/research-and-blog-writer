"""Unit tests for Mermaid markdown splitting, height estimation, and escaping."""

import pytest
import html
from ui.mermaid_renderer import (
    split_markdown_and_mermaid,
    estimate_mermaid_height,
    generate_mermaid_html,
)


def test_split_no_fences():
    """Content with zero mermaid fences should return a single prose segment."""
    content = "# Title\n\nThis is standard markdown with **bold text** and no diagrams."
    segments = split_markdown_and_mermaid(content)
    assert len(segments) == 1
    assert segments[0] == ("prose", content)


def test_split_single_fence():
    """Content with one middle fence splits into [prose, diagram, prose]."""
    content = (
        "# Overview\n\nHere is the architecture:\n\n"
        "```mermaid\nflowchart TD\n  A --> B\n```\n\n"
        "## Next Steps\nConclusion text."
    )
    segments = split_markdown_and_mermaid(content)
    assert len(segments) == 3
    assert segments[0][0] == "prose"
    assert "# Overview" in segments[0][1]
    assert segments[1][0] == "diagram"
    assert segments[1][1] == "flowchart TD\n  A --> B"
    assert segments[2][0] == "prose"
    assert "## Next Steps" in segments[2][1]


def test_split_multiple_fences():
    """Content with multiple diagrams splits correctly into alternating segments."""
    content = (
        "Intro\n\n"
        "```mermaid\ngraph LR\n  X --> Y\n```\n\n"
        "Middle narrative\n\n"
        "```mermaid\nsequenceDiagram\n  Alice->>Bob: Hello\n```\n\n"
        "Outro"
    )
    segments = split_markdown_and_mermaid(content)
    assert len(segments) == 5
    assert [k for k, _ in segments] == ["prose", "diagram", "prose", "diagram", "prose"]
    assert segments[1][1] == "graph LR\n  X --> Y"
    assert segments[3][1] == "sequenceDiagram\n  Alice->>Bob: Hello"


def test_split_fence_at_very_start_and_end():
    """Fences at the very beginning and very end should be parsed cleanly without empty ghost segments."""
    content = (
        "```mermaid\nflowchart TD\n  Start --> End\n```\n\n"
        "Some middle text.\n\n"
        "```mermaid\nstateDiagram-v2\n  s1 --> s2\n```"
    )
    segments = split_markdown_and_mermaid(content)
    assert len(segments) == 3
    assert segments[0][0] == "diagram"
    assert segments[1][0] == "prose"
    assert segments[2][0] == "diagram"


def test_split_unclosed_fence():
    """An unclosed mermaid fence at the end should be safely captured as a diagram attempt."""
    content = (
        "# Heading\n\nText before.\n\n"
        "```mermaid\nflowchart TD\n  A --> B"
    )
    segments = split_markdown_and_mermaid(content)
    assert len(segments) == 2
    assert segments[0][0] == "prose"
    assert segments[1][0] == "diagram"
    assert segments[1][1] == "flowchart TD\n  A --> B"


def test_empty_content():
    """Empty or whitespace content returns an empty segment list."""
    assert split_markdown_and_mermaid("") == []
    assert split_markdown_and_mermaid(None) == []


def test_estimate_height():
    """Height estimator scales with lines and honors min/max bounds."""
    short_diagram = "graph TD\n  A --> B"
    h_short = estimate_mermaid_height(short_diagram, min_height=320, max_height=850)
    assert h_short == 320

    long_diagram = "\n".join([f"  Node_{i} --> Node_{i+1}" for i in range(40)])
    h_long = estimate_mermaid_height(long_diagram, min_height=320, max_height=850)
    assert h_long == 850


def test_html_escaping_and_script_sanitization():
    """Test that malicious script injection in node labels is sanitized and escaped."""
    malicious_code = (
        'flowchart TD\n'
        '  A["<script>alert(\'pwned\')</script>"] --> B["Data & Analytics <tag>"]\n'
        '  B --> C[\'"quoted" & checked\']'
    )
    html_output = generate_mermaid_html(malicious_code, "test1234")

    # Raw unescaped <script> tag must NOT be present as a live HTML element
    assert "<script>alert('pwned')</script>" not in html_output
    assert html.escape("<script>alert('pwned')</script>") in html_output or "&lt;script&gt;" in html_output
    assert "securityLevel: 'strict'" in html_output
    assert "mermaid.render" in html_output
