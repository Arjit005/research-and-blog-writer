"""Split Mermaid and D2 diagram fences from prose without GUI dependencies."""

from __future__ import annotations

import re
from typing import List, Tuple


MERMAID_FENCE_PATTERN = re.compile(r"```mermaid\s*([\s\S]*?)```", re.IGNORECASE)
DIAGRAM_FENCE_PATTERN = re.compile(r"```(mermaid|d2)\s*([\s\S]*?)```", re.IGNORECASE)


def split_markdown_and_mermaid(content: str) -> List[Tuple[str, str]]:
    """Split markdown text into an ordered list of (kind, text) segments.

    Kind is either 'prose' or 'diagram'.
    """
    if not content:
        return []

    segments: List[Tuple[str, str]] = []
    last_idx = 0

    for match in DIAGRAM_FENCE_PATTERN.finditer(content):
        start, end = match.span()
        if start > last_idx:
            prose = content[last_idx:start]
            if prose:
                segments.append(("prose", prose))

        diagram_format = match.group(1).lower()
        diagram_code = match.group(2).strip()
        if diagram_code:
            segments.append(("diagram" if diagram_format == "mermaid" else "d2diagram", diagram_code))

        last_idx = end

    if last_idx < len(content):
        trailing = content[last_idx:]
        unclosed_match = re.search(r"```(mermaid|d2)\s*([\s\S]*)$", trailing, re.IGNORECASE)
        if unclosed_match:
            unclosed_pre = trailing[:unclosed_match.start()]
            if unclosed_pre:
                segments.append(("prose", unclosed_pre))
            unclosed_code = unclosed_match.group(2).strip()
            if unclosed_code:
                segments.append(("diagram" if unclosed_match.group(1).lower() == "mermaid" else "d2diagram", unclosed_code))
        else:
            segments.append(("prose", trailing))

    return segments


def extract_mermaid(content: str) -> Tuple[str, str]:
    """Extract mermaid diagram from markdown content.

    Returns:
        (content, first_mermaid_diagram_code)
    """
    if not content:
        return "", ""

    match = MERMAID_FENCE_PATTERN.search(content)
    if match:
        diagram_code = match.group(1).strip()
        return content, diagram_code

    return content, ""
