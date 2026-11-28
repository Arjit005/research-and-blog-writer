from core.d2 import fix_d2_in_markdown, validate_d2_diagram


def test_d2_light_fill_gets_dark_font_color():
    code = 'a: Service {\n  style.fill: "#EEEDFE"\n}'
    fixed, warnings = validate_d2_diagram(code)
    assert 'style.font-color: "#1a1a1a"' in fixed
    assert warnings == []


def test_d2_dark_fill_gets_light_font_color():
    code = 'a: Service {\n  style.fill: "#0f172a"\n}'
    fixed, warnings = validate_d2_diagram(code)
    assert 'style.font-color: "#ffffff"' in fixed
    assert warnings == []


def test_d2_existing_font_color_unchanged():
    code = 'a: Service {\n  style.fill: "#EEEDFE"\n  style.font-color: "#3C3489"\n}'
    fixed, warnings = validate_d2_diagram(code)
    assert fixed == code
    assert warnings == []


def test_d2_idempotent():
    code = 'a: Service {\n  style.fill: "#FAEEDA"\n}'
    once, _ = validate_d2_diagram(code)
    twice, _ = validate_d2_diagram(once)
    assert once == twice


def test_d2_malformed_input_no_exception():
    for bad in ["", "   ", "a -> { broken"]:
        fixed, _ = validate_d2_diagram(bad)
        assert fixed == bad


def test_fix_d2_in_markdown_preserves_prose():
    md = '# Title\n\n```d2\na: Cache {\n  style.fill: "#FCEBEB"\n}\n```\n\nEnd.'
    out = fix_d2_in_markdown(md)
    assert out.startswith("# Title\n\n```d2\n")
    assert out.endswith("\n```\n\nEnd.")
    assert 'style.font-color: "#1a1a1a"' in out
