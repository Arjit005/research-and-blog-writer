"""Revisions diff generator and revision utilities."""

from __future__ import annotations

import difflib
import html
from typing import Dict, List, Tuple


def calculate_diff_stats(old_text: str, new_text: str) -> Dict[str, int]:
    """Calculate the count of added, deleted, and unchanged lines."""
    old_lines = old_text.splitlines()
    new_lines = new_text.splitlines()

    matcher = difflib.SequenceMatcher(None, old_lines, new_lines)
    additions = 0
    deletions = 0

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "replace":
            deletions += (i2 - i1)
            additions += (j2 - j1)
        elif tag == "delete":
            deletions += (i2 - i1)
        elif tag == "insert":
            additions += (j2 - j1)

    return {
        "additions": additions,
        "deletions": deletions,
        "total_changes": additions + deletions,
    }


def generate_inline_diff_html(old_text: str, new_text: str) -> str:
    """Generate high-contrast, accessible HTML inline diff with + and - prefixes."""
    old_lines = old_text.splitlines()
    new_lines = new_text.splitlines()

    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile="Original Draft",
        tofile="Revised Draft",
        lineterm="",
    )

    lines_html = []
    has_changes = False

    for line in diff:
        has_changes = True
        escaped = html.escape(line)
        if line.startswith("+++") or line.startswith("---"):
            lines_html.append(f'<div class="diff-meta">{escaped}</div>')
        elif line.startswith("@@"):
            lines_html.append(f'<div class="diff-chunk">{escaped}</div>')
        elif line.startswith("+"):
            lines_html.append(f'<div class="diff-line diff-add">{escaped}</div>')
        elif line.startswith("-"):
            lines_html.append(f'<div class="diff-line diff-del">{escaped}</div>')
        else:
            lines_html.append(f'<div class="diff-line diff-ctx">{escaped}</div>')

    if not has_changes:
        return '<div class="diff-empty">✨ No differences found — both versions are identical.</div>'

    joined = "\n".join(lines_html)
    return f"""
    <style>
      .diff-container {{
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
        font-size: 12px;
        line-height: 1.5;
        border: 1px solid #cbd5e1;
        border-radius: 8px;
        background: #ffffff;
        padding: 12px;
        max-height: 480px;
        overflow-y: auto;
      }}
      .diff-line {{
        padding: 2px 6px;
        white-space: pre-wrap;
        word-break: break-all;
      }}
      .diff-meta {{
        color: #475569;
        font-weight: 700;
        padding: 2px 6px;
      }}
      .diff-chunk {{
        color: #2563eb;
        background: #eff6ff;
        font-weight: 600;
        padding: 2px 6px;
        margin: 4px 0;
      }}
      .diff-add {{
        background: #ecfdf5;
        color: #065f46;
        font-weight: 600;
      }}
      .diff-del {{
        background: #fef2f2;
        color: #991b1b;
        font-weight: 600;
      }}
      .diff-ctx {{
        color: #334155;
      }}
      .diff-empty {{
        padding: 14px;
        color: #059669;
        background: #ecfdf5;
        border-radius: 8px;
        font-size: 13px;
        font-weight: 600;
      }}
    </style>
    <div class="diff-container">
      {joined}
    </div>
    """
