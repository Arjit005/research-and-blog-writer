from __future__ import annotations

import logging
import re

from core.mermaid import _hex_luminance

logger = logging.getLogger(__name__)

D2_FENCE_PATTERN = re.compile(r"```d2\s*([\s\S]*?)```", re.IGNORECASE)

_D2_FILL_RE = re.compile(r"style\.fill\s*:\s*[\"']?([^\"'\s;{}]+)[\"']?", re.IGNORECASE)
_D2_FONT_COLOR_RE = re.compile(r"style\.font-color\s*:", re.IGNORECASE)
_D2_CONN_LABEL_RE = re.compile(r"(?:->|<-|<->|--)\s*[^:\n]+:\s*([^\n{]+)")
_D2_SHAPE_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_.-]*)\s*(?::|\{|$)")


def validate_d2_diagram(code: str) -> tuple[str, list[str]]:
    """Validate and auto-fix contrast on a D2 diagram. Pure function; never raises."""
    if not isinstance(code, str) or not code.strip():
        return code, []
    try:
        warnings: list[str] = []
        lines = code.splitlines()
        fixed_lines: list[str] = []
        shape_ids: set[str] = set()

        # Track brace-delimited blocks for style.fill without style.font-color
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            # Connection label check (> 4 words)
            cm = _D2_CONN_LABEL_RE.search(stripped)
            if cm:
                label = cm.group(1).strip().strip("\"'")
                if len(label.split()) > 4:
                    warnings.append(f"D2 connection label exceeds 4 words: '{label}'")

            # Count top-level shapes (skip connections, comments, style lines)
            if (
                stripped
                and not stripped.startswith("#")
                and not stripped.startswith("style.")
                and not any(op in stripped for op in ("->", "<-", "<->", "--"))
            ):
                sm = _D2_SHAPE_RE.match(stripped)
                if sm:
                    shape_ids.add(sm.group(1).split(".")[0])

            # Inline style.fill on a single line (e.g. a.style.fill: "#EEEDFE")
            fm = _D2_FILL_RE.search(line)
            if fm and not _D2_FONT_COLOR_RE.search(line):
                # Check if next/prev lines in same block already have style.font-color
                block_has_font_color = False
                for j in range(max(0, i - 4), min(len(lines), i + 5)):
                    if j != i and _D2_FONT_COLOR_RE.search(lines[j]):
                        block_has_font_color = True
                        break
                if not block_has_font_color:
                    fill_val = fm.group(1).strip()
                    lum = _hex_luminance(fill_val)
                    if lum is not None:
                        text_color = "#1a1a1a" if lum > 0.5 else "#ffffff"
                        indent = line[: len(line) - len(line.lstrip())]
                        if "style.fill:" in line and "." in line.split("style.fill:")[0]:
                            prefix = line.split("style.fill:")[0]
                            fixed_lines.append(line)
                            fixed_lines.append(f'{prefix}style.font-color: "{text_color}"')
                            i += 1
                            continue
                        else:
                            fixed_lines.append(line)
                            fixed_lines.append(f'{indent}style.font-color: "{text_color}"')
                            i += 1
                            continue

            fixed_lines.append(line)
            i += 1

        if len(shape_ids) > 8:
            warnings.append(f"D2 diagram has {len(shape_ids)} shapes (max 8 recommended)")

        return "\n".join(fixed_lines), warnings
    except Exception as exc:
        return code, [f"D2 validator error: {exc}"]


def fix_d2_in_markdown(markdown: str) -> str:
    """Fix D2 blocks in-place within markdown, leaving all other text identical."""
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
            fixed_code, warnings = validate_d2_diagram(stripped)
            for w in warnings:
                logger.warning("D2 block %d: %s", block_idx, w)
            block_idx += 1
            return match.group(0).replace(stripped, fixed_code, 1)

        return D2_FENCE_PATTERN.sub(_replace, markdown)
    except Exception:
        return markdown
