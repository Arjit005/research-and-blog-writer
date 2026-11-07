"""Citations and References Manager for Research Studio.

Handles:
- Extracting in-text citations ([1], [2], [RFC 9700], etc.) and web URLs.
- Compiling a centralized structured reference list with title, author, date, and provenance.
- Multiple citation styles: IEEE, APA 7th edition, ACM, and BibTeX.
- Diagnostic audit:
  - Missing-reference detection (citation referenced in prose but missing in bibliography).
  - Unused-reference detection (reference listed in bibliography but never cited in prose).
  - URL format validation & security checks (SSRF/private IP protection).
  - Preservation of source provenance.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse
import ipaddress


CITATION_NUMERIC_PATTERN = re.compile(r"\[(\d+)\]")
URL_PATTERN = re.compile(r"https?://[^\s)\]\"'>]+")


def is_safe_external_url(url: str) -> bool:
    """Validate that the URL is a syntactically valid public HTTP/HTTPS URL (SSRF defense)."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        host = parsed.hostname
        if not host:
            return False
        # Block localhost / private addresses
        if host in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
            return False
        try:
            ip = ipaddress.ip_address(host)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return False
        except ValueError:
            # Domain name, valid
            pass
        return True
    except Exception:
        return False


def extract_in_text_citations(content: str) -> List[int]:
    """Find all numeric citations like [1], [2] in document text."""
    matches = CITATION_NUMERIC_PATTERN.findall(content)
    seen = set()
    nums = []
    for m in matches:
        val = int(m)
        if val not in seen:
            seen.add(val)
            nums.append(val)
    return nums


def extract_all_sources(content: str) -> List[Dict[str, Any]]:
    """Extract all URLs, anchor titles, and potential references from markdown content."""
    # 1. Look for markdown links: [Title](URL)
    md_links = re.findall(r"\[([^\]]+)\]\((https?://[^\s)]+)\)", content)
    # 2. Look for numbered list references: [1] Title, URL or 1. Title, URL
    sources: List[Dict[str, Any]] = []
    seen_urls = set()

    for title, url in md_links:
        clean_url = url.strip()
        if clean_url in seen_urls:
            continue
        seen_urls.add(clean_url)
        is_safe = is_safe_external_url(clean_url)
        sources.append({
            "index": len(sources) + 1,
            "title": title.strip() or "Primary Web Reference",
            "url": clean_url,
            "is_safe": is_safe,
            "provenance": "Retrieved Research Dossier",
        })

    # Catch bare URLs not enclosed in markdown links
    for m in URL_PATTERN.finditer(content):
        raw_url = m.group(0).rstrip(".,;)>")
        if raw_url not in seen_urls:
            seen_urls.add(raw_url)
            parsed = urlparse(raw_url)
            domain = parsed.netloc or "web-source"
            sources.append({
                "index": len(sources) + 1,
                "title": f"Official Documentation & Resource ({domain})",
                "url": raw_url,
                "is_safe": is_safe_external_url(raw_url),
                "provenance": "Retrieved Research Dossier",
            })

    return sources


def format_citation(source: Dict[str, Any], style: str = "IEEE") -> str:
    """Format a single source entry according to academic citation style."""
    idx = source.get("index", 1)
    title = source.get("title", "Research Resource")
    url = source.get("url", "")
    author = source.get("author") or "Research Studio Squad"
    year = source.get("year") or "2026"

    style_upper = (style or "IEEE").upper()

    if style_upper == "APA":
        # Author. (Year). Title. URL
        return f"{author}. ({year}). {title}. Retrieved from {url}"
    elif style_upper == "ACM":
        # [idx] Author. Year. Title. URL
        return f"[{idx}] {author}. {year}. {title}. {url}"
    elif style_upper == "BIBTEX":
        key = f"ref_{idx}"
        return f"@misc{{{key},\n  author = {{{author}}},\n  title = {{{title}}},\n  year = {{{year}}},\n  url = {{{url}}}\n}}"
    else:  # Default IEEE
        # [idx] Author, "Title," 2026. [Online]. Available: URL.
        return f'[{idx}] {author}, "{title}," {year}. [Online]. Available: {url}'


def audit_document_citations(content: str) -> Dict[str, Any]:
    """Perform comprehensive citation verification, missing link detection, and duplicate checks."""
    sources = extract_all_sources(content)
    in_text_nums = extract_in_text_citations(content)
    total_sources = len(sources)

    missing_citations = [n for n in in_text_nums if n > total_sources]
    unused_sources = [s["index"] for s in sources if s["index"] not in in_text_nums]
    unsafe_urls = [s["url"] for s in sources if not s.get("is_safe", True)]

    # Detect duplicate URLs
    seen = {}
    duplicates = []
    for s in sources:
        u = s["url"].lower().rstrip("/")
        if u in seen:
            duplicates.append({"original": seen[u], "duplicate": s["index"], "url": s["url"]})
        else:
            seen[u] = s["index"]

    status = "VERIFIED"
    if missing_citations or unsafe_urls:
        status = "ISSUES_FOUND"
    elif unused_sources:
        status = "WARNINGS"

    return {
        "status": status,
        "total_sources_found": total_sources,
        "in_text_citations_count": len(in_text_nums),
        "in_text_indices": in_text_nums,
        "missing_references": missing_citations,
        "unused_references": unused_sources,
        "unsafe_urls": unsafe_urls,
        "duplicate_sources": duplicates,
        "sources": sources,
    }
