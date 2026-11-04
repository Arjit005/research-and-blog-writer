"""Export suite for generating slugified Markdown and standalone self-rendering HTML bundles."""

from __future__ import annotations

import re
import html
import unicodedata
from typing import Tuple
import markdown
from ui.mermaid_renderer import split_markdown_and_mermaid


def slugify(text: str, max_length: int = 50) -> str:
    """Convert text to a safe, clean URL/file slug."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    slug = re.sub(r"[-\s]+", "-", text)
    return slug[:max_length].rstrip("-") or "article"


def get_article_filename(title_or_topic: str, extension: str) -> str:
    """Generate a clean slugified filename with the given extension."""
    slug = slugify(title_or_topic)
    ext = extension.lstrip(".")
    return f"{slug}.{ext}"


def generate_standalone_html(title_or_topic: str, markdown_content: str) -> Tuple[str, str]:
    """Compile Markdown into a self-contained, standalone HTML document with embedded CSS and Mermaid JS."""
    filename = get_article_filename(title_or_topic, "html")

    # Segment content into prose and diagrams
    segments = split_markdown_and_mermaid(markdown_content)

    html_parts = []
    diagram_count = 0

    for kind, text in segments:
        if kind == "prose":
            rendered_prose = markdown.markdown(
                text,
                extensions=["tables", "fenced_code", "nl2br", "sane_lists"],
            )
            html_parts.append(rendered_prose)
        elif kind == "diagram":
            diagram_count += 1
            escaped_diagram = html.escape(text)
            html_parts.append(f"""
            <div class="diagram-wrapper">
              <pre class="mermaid">
{escaped_diagram}
              </pre>
            </div>
            """)

    article_body = "\n".join(html_parts)
    escaped_title = html.escape(title_or_topic)

    full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{escaped_title} | AI Research Studio</title>
  <style>
    :root {{
      --bg: #ffffff;
      --text: #0f172a;
      --muted: #475569;
      --border: #e2e8f0;
      --accent: #4f46e5;
      --card-bg: #f8fafc;
    }}
    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      line-height: 1.7;
      color: var(--text);
      background-color: var(--bg);
      padding: 32px 16px;
    }}
    .container {{
      max-width: 860px;
      margin: 0 auto;
      background: #ffffff;
    }}
    header {{
      border-bottom: 2px solid var(--border);
      padding-bottom: 20px;
      margin-bottom: 32px;
    }}
    header h1 {{
      font-size: 2.2rem;
      font-weight: 800;
      color: var(--text);
      line-height: 1.25;
      margin-bottom: 8px;
    }}
    .meta {{
      font-size: 0.9rem;
      color: var(--muted);
      display: flex;
      gap: 16px;
    }}
    h1, h2, h3, h4 {{
      color: var(--text);
      font-weight: 700;
      margin-top: 1.8em;
      margin-bottom: 0.6em;
      line-height: 1.3;
    }}
    h2 {{
      border-bottom: 1px solid var(--border);
      padding-bottom: 8px;
    }}
    p {{
      margin-bottom: 1.2em;
      font-size: 1.05rem;
    }}
    ul, ol {{
      margin-bottom: 1.2em;
      padding-left: 28px;
    }}
    li {{
      margin-bottom: 0.4em;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin: 1.5em 0;
      font-size: 0.95rem;
    }}
    th, td {{
      padding: 10px 14px;
      border: 1px solid var(--border);
      text-align: left;
    }}
    th {{
      background: var(--card-bg);
      font-weight: 700;
    }}
    code {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 0.9em;
      background: var(--card-bg);
      padding: 2px 6px;
      border-radius: 4px;
      border: 1px solid var(--border);
    }}
    pre code {{
      display: block;
      padding: 14px;
      overflow-x: auto;
      line-height: 1.5;
    }}
    blockquote {{
      border-left: 4px solid var(--accent);
      padding-left: 16px;
      margin: 1.5em 0;
      color: var(--muted);
      background: var(--card-bg);
      padding: 12px 16px;
      border-radius: 0 8px 8px 0;
    }}
    img {{
      max-width: 100%;
      height: auto;
      border-radius: 8px;
      margin: 1.5em 0;
    }}
    .diagram-wrapper {{
      background: #ffffff;
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 20px;
      margin: 2em 0;
      display: flex;
      justify-content: center;
      overflow-x: auto;
      box-shadow: 0 2px 6px rgba(0,0,0,0.03);
    }}
    .mermaid {{
      display: flex;
      justify-content: center;
      width: 100%;
    }}
    footer {{
      margin-top: 48px;
      padding-top: 20px;
      border-top: 1px solid var(--border);
      font-size: 0.85rem;
      color: var(--muted);
      text-align: center;
    }}

    /* Clean Print Stylesheet for PDF */
    @media print {{
      body {{
        padding: 0;
        font-size: 11pt;
      }}
      .container {{
        max-width: 100%;
      }}
      .diagram-wrapper {{
        box-shadow: none;
        border: 1px solid #ccc;
        page-break-inside: avoid;
      }}
      h1, h2, h3 {{
        page-break-after: avoid;
      }}
      a {{
        text-decoration: none;
        color: var(--text);
      }}
    }}
  </style>
  <script type="module">
    import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10.9.3/dist/mermaid.esm.min.mjs';
    mermaid.initialize({{
      startOnLoad: true,
      theme: 'neutral',
      securityLevel: 'strict'
    }});
  </script>
</head>
<body>
  <div class="container">
    <header>
      <h1>{escaped_title}</h1>
      <div class="meta">
        <span>Autonomous Technical Research</span>
        <span>•</span>
        <span>{diagram_count} Architecture Diagram{'s' if diagram_count != 1 else ''}</span>
      </div>
    </header>
    <main>
      {article_body}
    </main>
    <footer>
      Generated by Autonomous AI Research & Blog Studio
    </footer>
  </div>
</body>
</html>"""

    return filename, full_html
