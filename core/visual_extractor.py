"""Visual extraction, chart parsing, and figure-grounding utilities."""

from __future__ import annotations

import re
import json
import logging
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Patterns for Mermaid, Charts, and Markdown Figures/Images
MERMAID_PATTERN = re.compile(r"```mermaid\s*([\s\S]*?)```", re.IGNORECASE)
D2_PATTERN = re.compile(r"```d2\s*([\s\S]*?)```", re.IGNORECASE)
CHART_BLOCK_PATTERN = re.compile(r"```(?:chart|json:chart)\s*([\s\S]*?)```", re.IGNORECASE)
IMAGE_MARKDOWN_PATTERN = re.compile(r"!\[(.*?)\]\((https?:\/\/[^\s\)]+)(?:\s+\"(.*?)\")?\)", re.IGNORECASE)
REFERENCE_IMAGE_PATTERN = re.compile(r"!\[([^\]]*)\]\[([^\]]*)\]", re.IGNORECASE)
HTML_IMAGE_PATTERN = re.compile(
    r'<img\b(?=[^>]*\bsrc=["\'](https?:\/\/[^"\']+)["\'])'
    r'(?=[^>]*\balt=["\']([^"\']*)["\'])[^>]*>',
    re.IGNORECASE,
)
REFERENCE_LINK_PATTERN = re.compile(r"\[(\d+|[^\]]+)\]:\s*(https?:\/\/[^\s]+)(?:\s+\"(.*?)\")?", re.IGNORECASE)


def extract_visual_artifacts_from_markdown(
    content: str,
    article_id: Optional[int] = None,
    run_id: Optional[str] = None,
    user_id: int = 0,
) -> Dict[str, Any]:
    """Parse and extract all visual components (Mermaid, charts, images, sources) from markdown.

    Returns structured dictionaries ready for persistence into research_visuals and research_charts.
    """
    if not content:
        return {"visuals": [], "charts": [], "evidence_links": []}

    visuals: List[Dict[str, Any]] = []
    charts: List[Dict[str, Any]] = []
    evidence_links: List[Dict[str, Any]] = []

    # 1. Extract text-based architecture diagrams
    diagram_matches = [
        (match.start(), "mermaid", match)
        for match in MERMAID_PATTERN.finditer(content)
    ] + [
        (match.start(), "d2", match)
        for match in D2_PATTERN.finditer(content)
    ]
    diagram_matches.sort(key=lambda item: item[0])
    for idx, (_, diagram_format, match) in enumerate(diagram_matches, start=1):
        code = match.group(1).strip()
        if not code:
            continue
        # Extract title if present in diagram header or surrounding markdown
        title_match = re.search(r"title[:\s]+([^\n\r]+)", code, re.IGNORECASE)
        title = title_match.group(1).strip() if title_match else f"System Architecture Diagram #{idx}"
        
        # Determine diagram sub-type
        sub_type = "architecture_diagram"
        if "sequenceDiagram" in code:
            sub_type = "sequence_diagram"
        elif "classDiagram" in code:
            sub_type = "class_diagram"
        elif "stateDiagram" in code:
            sub_type = "state_diagram"
        elif "erDiagram" in code:
            sub_type = "er_diagram"
        elif "flowchart" in code or "graph" in code:
            sub_type = "flowchart"

        visuals.append({
            "user_id": user_id,
            "article_id": article_id,
            "run_id": run_id,
            "visual_type": "diagram",
            "origin_type": "system_diagram",
            "title": title,
            "caption": f"Figure {idx}: {title}",
            "description": f"Generated {diagram_format.upper()} {sub_type} illustrating the researched system topology.",
            "source_title": None,
            "license_information": None,
            "alt_text": f"{diagram_format.upper()} {sub_type} specification for {title}",
            "media_content": code,
            "file_format": diagram_format,
            "metadata_json": {
                "diagram_type": sub_type,
                "lines_count": len(code.splitlines()),
                "renderer": "D2 with TALA layout" if diagram_format == "d2" else "Mermaid 12.3.0",
            },
        })

    # 2. Extract Embedded Structured Charts (JSON/Table specs)
    chart_matches = list(CHART_BLOCK_PATTERN.finditer(content))
    for idx, match in enumerate(chart_matches, start=1):
        raw_json = match.group(1).strip()
        try:
            parsed = json.loads(raw_json)
            if isinstance(parsed, dict) and "data" in parsed:
                chart_type = str(parsed.get("type", "bar")).lower()
                c_title = str(parsed.get("title", f"Comparative Research Metric #{idx}"))
                c_desc = str(parsed.get("description", "Structured chart; verify its source and methodology before relying on the values."))
                c_units = str(parsed["units"]) if parsed.get("units") else None
                c_source = str(parsed["data_source"]) if parsed.get("data_source") else None
                c_method = str(parsed["methodology"]) if parsed.get("methodology") else "Methodology not provided; verify before relying on this chart."

                charts.append({
                    "user_id": user_id,
                    "article_id": article_id,
                    "title": c_title,
                    "description": c_desc,
                    "chart_type": chart_type,
                    "structured_data": parsed,
                    "data_source": c_source,
                    "units": c_units,
                    "methodology": c_method,
                })
        except Exception as e:
            logger.debug(f"Non-fatal chart parsing error: {e}")

    # 3. Extract Markdown, reference-style, and HTML images without asserting
    # that the URL is authoritative or that its license permits reuse.
    image_candidates: List[Tuple[int, str, str, Optional[str]]] = []
    for match in IMAGE_MARKDOWN_PATTERN.finditer(content):
        image_candidates.append((match.start(), match.group(1), match.group(2), match.group(3)))

    reference_urls = {
        match.group(1).strip().casefold(): (match.group(2).strip(), match.group(3))
        for match in REFERENCE_LINK_PATTERN.finditer(content)
    }
    for match in REFERENCE_IMAGE_PATTERN.finditer(content):
        label = (match.group(2).strip() or match.group(1).strip()).casefold()
        reference = reference_urls.get(label)
        if reference:
            image_candidates.append((match.start(), match.group(1), reference[0], reference[1]))

    for match in HTML_IMAGE_PATTERN.finditer(content):
        image_candidates.append((match.start(), match.group(2), match.group(1), None))

    seen_image_urls: set[str] = set()
    image_candidates.sort(key=lambda candidate: candidate[0])
    for idx, (_, raw_alt, raw_url, raw_title) in enumerate(image_candidates, start=1):
        url = raw_url.strip()
        if url in seen_image_urls:
            continue
        seen_image_urls.add(url)
        alt = raw_alt.strip() or f"Research Figure #{idx}"
        title_attr = raw_title.strip() if raw_title else alt
        visuals.append({
            "user_id": user_id,
            "article_id": article_id,
            "run_id": run_id,
            "visual_type": "figure",
            "origin_type": "retrieved_web",
            "title": title_attr,
            "caption": f"Figure {idx}: {title_attr}",
            "source_url": url,
            "source_title": None,
            "license_information": None,
            "usage_restrictions": "Image license has not been verified; check the original source before reuse.",
            "alt_text": alt,
            "thumbnail_url": url,
            "file_format": url.split(".")[-1].split("?")[0].lower() if "." in url else "png",
            "metadata_json": {"original_url": url, "caption_alt": alt},
        })
        evidence_links.append({
            "visual_index": len(visuals) - 1,
            "citation_url": url,
            "report_section": "Image source URL (unverified)",
            "evidence_status": "unverified",
        })

    return {
        "visuals": visuals,
        "charts": charts,
        "evidence_links": evidence_links,
    }
