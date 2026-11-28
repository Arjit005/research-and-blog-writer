from __future__ import annotations

import re
import html
import json
import logging
import uuid
from typing import Callable, List, Tuple

logger = logging.getLogger(__name__)

MERMAID_FENCE_PATTERN = re.compile(r"```mermaid\s*([\s\S]*?)```", re.IGNORECASE)

_STYLE_LINE_RE = re.compile(
    r"^(\s*(?:classDef\s+\S+|style\s+\S+)\s+)(.+)$",
    re.IGNORECASE,
)
_FILL_RE = re.compile(r"\bfill\s*:\s*([^,\s;]+)", re.IGNORECASE)
_COLOR_RE = re.compile(r"(?:^|[,\s;])color\s*:", re.IGNORECASE)
_HEX_RE = re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_EDGE_PIPE_RE = re.compile(r"\|([^|\n]+)\|")
_EDGE_INLINE_RE = re.compile(r"--\s+([^-\n>]+?)\s+-->")
_NODE_ID_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_-]*)\s*(?:\[|\(|\{|>|$)")


def _hex_luminance(hex_color: str) -> float | None:
    """Return relative luminance [0.0, 1.0] for #RGB or #RRGGBB, else None."""
    m = _HEX_RE.match(hex_color.strip())
    if not m:
        return None
    h = m.group(1)
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0, int(h[4:6], 16) / 255.0
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def validate_mermaid_diagram(code: str) -> tuple[str, list[str]]:
    """Validate and auto-fix contrast on a Mermaid diagram. Pure function; never raises."""
    if not isinstance(code, str) or not code.strip():
        return code, []
    try:
        warnings: list[str] = []
        fixed_lines: list[str] = []
        distinct_fills: set[str] = set()
        node_ids: set[str] = set()

        for line in code.splitlines():
            stripped = line.strip()
            sm = _STYLE_LINE_RE.match(line)
            if sm:
                prefix, props = sm.group(1), sm.group(2)
                fm = _FILL_RE.search(props)
                if fm:
                    fill_val = fm.group(1).strip()
                    distinct_fills.add(fill_val.lower())
                    if not _COLOR_RE.search(props):
                        lum = _hex_luminance(fill_val)
                        if lum is None:
                            warnings.append(f"Non-hex fill '{fill_val}' has no text color")
                        else:
                            text_color = "#1a1a1a" if lum > 0.5 else "#ffffff"
                            sep = "" if props.rstrip().endswith(",") else ","
                            line = f"{prefix}{props.rstrip()}{sep}color:{text_color}"
                fixed_lines.append(line)
                continue

            # Check edge labels (> 4 words)
            for em in _EDGE_PIPE_RE.finditer(stripped):
                label = em.group(1).strip()
                if len(label.split()) > 4:
                    warnings.append(f"Edge label exceeds 4 words: '{label}'")
            for em in _EDGE_INLINE_RE.finditer(stripped):
                label = em.group(1).strip()
                if len(label.split()) > 4:
                    warnings.append(f"Edge label exceeds 4 words: '{label}'")

            # Count distinct node IDs (skip directives/subgraphs/end)
            if stripped and not re.match(
                r"^(?:flowchart|graph|sequenceDiagram|stateDiagram|classDiagram|erDiagram|journey|gantt|pie|gitGraph|mindmap|timeline|subgraph|end|direction|%%)\b",
                stripped,
                re.IGNORECASE,
            ):
                for part in re.split(r"--+>?|==+>?|-\.+->", stripped):
                    nm = _NODE_ID_RE.match(part.strip())
                    if nm:
                        node_ids.add(nm.group(1))

            fixed_lines.append(line)

        if len(node_ids) > 8:
            warnings.append(f"Diagram has {len(node_ids)} nodes (max 8 recommended)")
        if len(distinct_fills) > 3:
            warnings.append(f"Diagram uses {len(distinct_fills)} fill colours (max 3 recommended)")

        return "\n".join(fixed_lines), warnings
    except Exception as exc:
        return code, [f"Validator error: {exc}"]


def fix_mermaid_in_markdown(markdown: str) -> str:
    """Fix Mermaid blocks in-place within markdown, leaving all other text identical."""
    if not isinstance(markdown, str) or not markdown:
        return markdown
    try:
        block_idx = 0

        def _replace(match: re.Match[str]) -> str:
            nonlocal block_idx
            raw_block = match.group(1)
            stripped = raw_block.strip()
            if not stripped:
                return match.group(0)
            fixed_code, warnings = validate_mermaid_diagram(stripped)
            for w in warnings:
                logger.warning("Mermaid block %d: %s", block_idx, w)
            block_idx += 1
            return match.group(0).replace(stripped, fixed_code, 1)

        return MERMAID_FENCE_PATTERN.sub(_replace, markdown)
    except Exception:
        return markdown


def choose_better_diagram(
    original_code: str,
    retry_fn: Callable[[str, list[str]], str],
) -> tuple[str, list[str]]:
    """Validate original_code; if warnings exist, call retry_fn once and keep whichever has fewer warnings."""
    fixed_orig, orig_warnings = validate_mermaid_diagram(original_code)
    if not orig_warnings:
        return fixed_orig, []
    try:
        candidate = retry_fn(fixed_orig, orig_warnings)
        if not isinstance(candidate, str) or not candidate.strip():
            return fixed_orig, orig_warnings
        cand_stripped = candidate.strip()
        if not re.match(
            r"^(?:flowchart|graph|sequenceDiagram|stateDiagram(?:-v2)?|classDiagram|erDiagram|journey|gantt|pie|gitGraph|mindmap|timeline|quadrantChart|C4Context|xychart-beta)\b",
            cand_stripped,
            re.IGNORECASE,
        ):
            return fixed_orig, orig_warnings
        if (
            cand_stripped.count("[") != cand_stripped.count("]")
            or cand_stripped.count("(") != cand_stripped.count(")")
            or cand_stripped.count("{") != cand_stripped.count("}")
        ):
            return fixed_orig, orig_warnings
        fixed_retry, retry_warnings = validate_mermaid_diagram(cand_stripped)
        if len(retry_warnings) < len(orig_warnings):
            return fixed_retry, retry_warnings
        return fixed_orig, orig_warnings
    except Exception as exc:
        logger.warning("Mermaid retry failed, keeping original: %s", exc)
        return fixed_orig, orig_warnings


def split_markdown_and_mermaid(content: str) -> List[Tuple[str, str]]:
    """Split markdown text into an ordered list of (kind, text) segments.

    Kind is either 'prose' or 'diagram'.
    Handles unclosed fences, empty content, and multiple diagrams cleanly.
    """
    if not content:
        return []

    segments: List[Tuple[str, str]] = []
    last_idx = 0
    block_idx = 0

    for match in MERMAID_FENCE_PATTERN.finditer(content):
        start, end = match.span()

        # Leading prose before this mermaid fence
        if start > last_idx:
            prose = content[last_idx:start]
            if prose:
                segments.append(("prose", prose))

        # Extracted diagram code
        diagram_code = match.group(1).strip()
        if diagram_code:
            fixed_code, warnings = validate_mermaid_diagram(diagram_code)
            for w in warnings:
                logger.warning("Mermaid block %d: %s", block_idx, w)
            block_idx += 1
            segments.append(("diagram", fixed_code))

        last_idx = end

    # Trailing content after last closed fence
    if last_idx < len(content):
        trailing = content[last_idx:]
        # Check for unclosed mermaid fence at the end
        unclosed_match = re.search(r"```mermaid\s*([\s\S]*)$", trailing, re.IGNORECASE)
        if unclosed_match:
            unclosed_pre = trailing[:unclosed_match.start()]
            if unclosed_pre:
                segments.append(("prose", unclosed_pre))
            unclosed_code = unclosed_match.group(1).strip()
            if unclosed_code:
                # Treat unclosed fence as a diagram attempt
                segments.append(("diagram", unclosed_code))
        else:
            if trailing:
                segments.append(("prose", trailing))

    return segments


def estimate_mermaid_height(diagram_code: str, min_height: int = 320, max_height: int = 850) -> int:
    """Estimate a comfortable iframe height based on the number of lines and nodes."""
    if not diagram_code:
        return min_height

    lines = [line.strip() for line in diagram_code.strip().splitlines() if line.strip()]
    line_count = len(lines)

    # Heuristic: 26px per line + 100px padding for padding and controls
    estimated = (line_count * 26) + 100
    return max(min_height, min(max_height, estimated))


def generate_mermaid_html(diagram_code: str, diagram_id: str) -> str:
    """Generate self-contained HTML running Mermaid 10.x with strict security and error boundaries."""
    # Escape diagram text for HTML contexts (visible fallback <pre><code> block).
    escaped_code = html.escape(diagram_code)

    # JSON-encode the diagram source for the JS context. This defeats template
    # literal injection (backticks / `${...}`) and, by escaping `<`, `>` and `&`,
    # prevents `</script>` from terminating the inline module early.
    diagram_js_literal = (
        json.dumps(diagram_code)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background: transparent;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      min-height: 100%;
      padding: 12px;
    }}
    .diagram-card {{
      background: #ffffff;
      border: 1px solid #e2e8f0;
      border-radius: 12px;
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
      padding: 18px;
      width: 100%;
      max-width: 960px;
      display: flex;
      flex-direction: column;
      align-items: center;
      position: relative;
    }}
    .mermaid-container {{
      width: 100%;
      display: flex;
      justify-content: center;
      overflow-x: auto;
      padding: 8px 0;
    }}
    .mermaid-container svg {{
      max-width: 100% !important;
      height: auto !important;
    }}
    .toolbar {{
      display: flex;
      justify-content: flex-end;
      width: 100%;
      gap: 8px;
      margin-bottom: 8px;
    }}
    .action-btn {{
      background: #f1f5f9;
      border: 1px solid #cbd5e1;
      border-radius: 6px;
      padding: 4px 10px;
      font-size: 11px;
      font-weight: 600;
      color: #334155;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 4px;
      transition: all 0.15s ease;
    }}
    .action-btn:hover {{
      background: #e2e8f0;
      color: #0f172a;
    }}
    .error-card {{
      background: #fffbeb;
      border: 1px solid #fde68a;
      border-radius: 8px;
      padding: 14px;
      width: 100%;
      color: #92400e;
      font-size: 13px;
    }}
    .error-title {{
      font-weight: 700;
      margin-bottom: 6px;
      display: flex;
      align-items: center;
      gap: 6px;
    }}
    details {{
      margin-top: 8px;
    }}
    summary {{
      cursor: pointer;
      font-weight: 600;
      color: #b45309;
    }}
    pre.code-fallback {{
      background: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 6px;
      padding: 10px;
      margin-top: 6px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 12px;
      overflow-x: auto;
      color: #1e293b;
    }}
  </style>
  <script type="module">
    import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10.9.3/dist/mermaid.esm.min.mjs';

    // Strict security sandboxing
    mermaid.initialize({{
      startOnLoad: false,
      securityLevel: 'strict',
      theme: 'neutral',
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'
    }});

    const diagramText = {diagram_js_literal};
    const container = document.getElementById('diagram-target');
    const errorBox = document.getElementById('error-target');
    const toolbar = document.getElementById('toolbar-target');

    async function renderChart() {{
      try {{
        const id = 'svg-{diagram_id}';
        const {{ svg }} = await mermaid.render(id, diagramText);
        container.innerHTML = svg;
        toolbar.style.display = 'flex';
      }} catch (err) {{
        console.warn('Mermaid render error:', err);
        container.style.display = 'none';
        errorBox.style.display = 'block';
      }}
    }}

    window.downloadSVG = function() {{
      const svgEl = container.querySelector('svg');
      if (!svgEl) return;
      const svgData = new XMLSerializer().serializeToString(svgEl);
      const blob = new Blob([svgData], {{ type: 'image/svg+xml;charset=utf-8' }});
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'diagram-{diagram_id}.svg';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }};

    renderChart();
  </script>
</head>
<body>
  <div class="diagram-card">
    <div id="toolbar-target" class="toolbar" style="display:none;">
      <button class="action-btn" onclick="window.downloadSVG()">
        <span>⬇️ Download SVG</span>
      </button>
    </div>
    <div id="diagram-target" class="mermaid-container">
      <div style="color:#64748b; font-size:12px;">Rendering architecture diagram...</div>
    </div>
    <div id="error-target" class="error-card" style="display:none;">
      <div class="error-title">⚠️ Diagram Render Notice</div>
      <div>The generated diagram could not be parsed as valid Mermaid syntax. The underlying code is preserved below:</div>
      <details>
        <summary>View Diagram Source</summary>
        <pre class="code-fallback"><code>{escaped_code}</code></pre>
      </details>
    </div>
  </div>
</body>
</html>"""
