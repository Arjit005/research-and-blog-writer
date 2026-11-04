"""Native Mermaid.js Diagram Renderer for Streamlit.

Splits markdown text into prose and diagram segments, safely rendering
Mermaid code blocks as interactive SVGs inside isolated iframe components.
Includes strict security sandboxing, line-based height estimation, and
graceful error fallbacks for LLM-generated syntax flaws.
"""

from __future__ import annotations

import re
import html
import json
import uuid
from typing import List, Tuple, Optional
import streamlit as st
import streamlit.components.v1 as components


MERMAID_FENCE_PATTERN = re.compile(r"```mermaid\s*([\s\S]*?)```", re.IGNORECASE)


def split_markdown_and_mermaid(content: str) -> List[Tuple[str, str]]:
    """Split markdown text into an ordered list of (kind, text) segments.

    Kind is either 'prose' or 'diagram'.
    Handles unclosed fences, empty content, and multiple diagrams cleanly.
    """
    if not content:
        return []

    segments: List[Tuple[str, str]] = []
    last_idx = 0

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
            segments.append(("diagram", diagram_code))

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


def render_mermaid_diagram(diagram_code: str, height: Optional[int] = None) -> None:
    """Render a single Mermaid diagram securely in an isolated Streamlit iframe."""
    if not diagram_code.strip():
        return

    diagram_id = uuid.uuid4().hex[:8]
    iframe_height = height or estimate_mermaid_height(diagram_code)
    html_bundle = generate_mermaid_html(diagram_code, diagram_id)

    components.html(html_bundle, height=iframe_height, scrolling=False)


def render_article_markdown(content: str) -> None:
    """Render full article markdown, converting Mermaid code fences into native SVGs."""
    if not content:
        st.info("No content to display.")
        return

    segments = split_markdown_and_mermaid(content)
    if not segments:
        # LLM-generated prose is untrusted: render as plain markdown, never raw HTML.
        st.markdown(content)
        return

    for kind, text in segments:
        if kind == "prose":
            # Scraped/LLM prose must not be allowed to inject HTML/JS.
            st.markdown(text)
        elif kind == "diagram":
            render_mermaid_diagram(text)
