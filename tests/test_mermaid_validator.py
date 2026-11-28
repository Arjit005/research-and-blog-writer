from core.mermaid import (
    fix_mermaid_in_markdown,
    split_markdown_and_mermaid,
    validate_mermaid_diagram,
)


def test_classdef_light_fill_gets_dark_text():
    code = "flowchart LR\n  A:::light\n  classDef light fill:#EEEDFE,stroke:#534AB7"
    fixed, warnings = validate_mermaid_diagram(code)
    assert "color:#1a1a1a" in fixed
    assert warnings == []


def test_classdef_dark_fill_gets_light_text():
    code = "flowchart LR\n  A:::dark\n  classDef dark fill:#0f172a,stroke:#334155"
    fixed, warnings = validate_mermaid_diagram(code)
    assert "color:#ffffff" in fixed
    assert warnings == []


def test_classdef_with_existing_color_unchanged():
    code = "flowchart LR\n  A:::ok\n  classDef ok fill:#E1F5EE,stroke:#0F6E56,color:#04342C"
    fixed, warnings = validate_mermaid_diagram(code)
    assert fixed == code
    assert warnings == []


def test_style_line_without_color_fixed():
    code = "flowchart LR\n  A --> B\n  style A fill:#FCEBEB,stroke:#A32D2D"
    fixed, _ = validate_mermaid_diagram(code)
    assert "color:#1a1a1a" in fixed


def test_three_digit_hex_handled():
    code = "flowchart LR\n  classDef w fill:#fff,stroke:#ccc\n  classDef b fill:#000,stroke:#333"
    fixed, _ = validate_mermaid_diagram(code)
    assert "fill:#fff,stroke:#ccc,color:#1a1a1a" in fixed
    assert "fill:#000,stroke:#333,color:#ffffff" in fixed


def test_long_edge_label_warns_and_leaves_code_unchanged():
    code = "flowchart LR\n  A -->|this edge label has six words| B"
    fixed, warnings = validate_mermaid_diagram(code)
    assert fixed == code
    assert any("4 words" in w for w in warnings)


def test_more_than_8_nodes_warns():
    nodes = "\n".join(f"  N{i} --> N{i+1}" for i in range(1, 10))
    code = f"flowchart LR\n{nodes}"
    _, warnings = validate_mermaid_diagram(code)
    assert any("nodes" in w for w in warnings)


def test_malformed_input_returns_original_no_exception():
    for bad in ["", "   ", "not valid mermaid %%% {{{"]:
        fixed, _ = validate_mermaid_diagram(bad)
        assert fixed == bad


def test_idempotent():
    code = "flowchart LR\n  A:::w\n  classDef w fill:#FAEEDA,stroke:#854F0B"
    once, _ = validate_mermaid_diagram(code)
    twice, _ = validate_mermaid_diagram(once)
    assert once == twice


def test_split_markdown_and_mermaid_runs_validator():
    md = "Intro\n```mermaid\nflowchart LR\n  A:::w\n  classDef w fill:#FAEEDA,stroke:#854F0B\n```\nOutro"
    segs = split_markdown_and_mermaid(md)
    diagrams = [text for kind, text in segs if kind == "diagram"]
    assert len(diagrams) == 1
    assert "color:#1a1a1a" in diagrams[0]


def test_fix_mermaid_in_markdown_preserves_prose():
    md = "# Title\n\nSome prose.\n\n```mermaid\nflowchart LR\n  A:::w\n  classDef w fill:#FAEEDA,stroke:#854F0B\n```\n\nEnd prose."
    out = fix_mermaid_in_markdown(md)
    assert out.startswith("# Title\n\nSome prose.\n\n```mermaid\n")
    assert out.endswith("\n```\n\nEnd prose.")
    assert "color:#1a1a1a" in out


def test_fix_mermaid_in_markdown_no_mermaid_unchanged():
    md = "# Just Markdown\n\nNo diagrams here."
    assert fix_mermaid_in_markdown(md) == md


def test_fix_mermaid_in_markdown_two_blocks():
    md = (
        "```mermaid\nflowchart LR\n  classDef a fill:#fff,stroke:#ccc\n```\n"
        "mid\n"
        "```mermaid\nflowchart LR\n  classDef b fill:#000,stroke:#333\n```"
    )
    out = fix_mermaid_in_markdown(md)
    assert "color:#1a1a1a" in out
    assert "color:#ffffff" in out


def test_fix_mermaid_in_markdown_idempotent():
    md = "```mermaid\nflowchart LR\n  classDef a fill:#EEEDFE,stroke:#534AB7\n```"
    once = fix_mermaid_in_markdown(md)
    twice = fix_mermaid_in_markdown(once)
    assert once == twice


def test_fix_mermaid_in_markdown_malformed_fence_unchanged():
    md = "```mermaid\nflowchart LR\n  A --> B"
    assert fix_mermaid_in_markdown(md) == md
