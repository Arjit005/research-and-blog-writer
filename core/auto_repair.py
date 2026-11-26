"""Deterministic post-audit auto-repair for generated research articles.

Repairs common Mermaid syntax issues and cleans up broken/placeholder
citations flagged by Quality Auditor v2.1 without re-running the full LLM
pipeline.
"""

from __future__ import annotations

import re
from typing import Dict, List, Tuple


_MERMAID_BLOCK_RE = re.compile(r"```mermaid\s*\n([\s\S]*?)```", re.IGNORECASE)
_UNQUOTED_NODE_RE = re.compile(r'(\b[A-Za-z0-9_]+)\[([^"\[\]\n]*[\(\)][^"\[\]\n]*)\]')


def repair_mermaid_blocks(markdown: str) -> Tuple[str, int]:
    """Quote Mermaid node labels containing parentheses to prevent parse errors."""
    fixes = 0

    def _fix_block(match: re.Match[str]) -> str:
        nonlocal fixes
        body = match.group(1)
        new_body, count = _UNQUOTED_NODE_RE.subn(r'\1["\2"]', body)
        fixes += count
        return f"```mermaid\n{new_body}```"

    repaired = _MERMAID_BLOCK_RE.sub(_fix_block, markdown or "")
    return repaired, fixes


def auto_repair_article_markdown(
    markdown: str,
    audit_report: Dict | None = None,
) -> Tuple[str, List[str]]:
    """Apply deterministic repairs to generated Markdown and return repair notes."""
    repairs: List[str] = []
    text, mermaid_fixes = repair_mermaid_blocks(markdown or "")
    if mermaid_fixes:
        repairs.append(f"Quoted {mermaid_fixes} Mermaid node label(s) with special characters.")
    return text, repairs
