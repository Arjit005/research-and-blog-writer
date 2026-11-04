"""Content metrics engine: text sanitization, word counting, readability, and citation audit."""

from __future__ import annotations

import re
from typing import Dict, Any
import textstat


def clean_article_prose(markdown_text: str) -> str:
    """Strip code blocks, Mermaid diagrams, images, and reference bibliographies to compute honest prose metrics."""
    if not markdown_text or not markdown_text.strip():
        return ""

    text = markdown_text

    # 1. Strip the references section at the end if present
    ref_match = re.search(r"\n#{1,3}\s*(?:📚\s*)?(?:References|Verified Sources|Sources|Further Reading)[\s\S]*$", text, re.IGNORECASE)
    if ref_match:
        text = text[:ref_match.start()]

    # 2. Strip fenced code blocks (including ```mermaid ... ``` and ```python ... ```)
    text = re.sub(r"```[\s\S]*?```", " ", text)

    # 3. Strip markdown image tags: ![Alt](url)
    text = re.sub(r"!\[.*?\]\(.*?\)", " ", text)

    # 4. Convert markdown links [text](url) to just text
    text = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", text)

    # 5. Strip raw URLs
    text = re.sub(r"https?://\S+", " ", text)

    # 6. Strip HTML tags
    text = re.sub(r"<[^>]+>", " ", text)

    # 7. Collapse whitespace
    clean = re.sub(r"\s+", " ", text).strip()
    return clean


def count_citations_in_references(markdown_text: str) -> int:
    """Count unique reference URLs or citations in the article references block."""
    if not markdown_text:
        return 0

    # Look for the references section
    ref_match = re.search(r"\n#{1,3}\s*(?:📚\s*)?(?:References|Verified Sources|Sources|Further Reading)[\s\S]*$", markdown_text, re.IGNORECASE)
    search_corpus = markdown_text[ref_match.start():] if ref_match else markdown_text

    # Extract all URLs in the references section
    urls = set(re.findall(r"https?://[^\s)\]\"'>]+", search_corpus))
    if urls:
        return len(urls)

    # Fallback: Count numbered citation markers like [1], [2], ...
    citation_markers = set(re.findall(r"\[(\d+)\]", search_corpus))
    return len(citation_markers)


def calculate_clean_metrics(markdown_text: str) -> Dict[str, Any]:
    """Calculate clean, honest metrics based strictly on natural language prose."""
    if not markdown_text or not markdown_text.strip():
        return {
            "word_count": 0,
            "read_time_min": 0,
            "flesch_score": 0.0,
            "flesch_grade": "N/A",
            "citation_count": 0,
            "complexity_label": "N/A",
        }

    clean_prose = clean_article_prose(markdown_text)
    words = len(clean_prose.split()) if clean_prose else 0
    read_time = max(1, round(words / 200)) if words > 0 else 0

    if words >= 20:
        flesch_score = round(textstat.flesch_reading_ease(clean_prose), 1)
        # Determine plain-language reading label
        if flesch_score >= 80:
            complexity = "Easy"
        elif flesch_score >= 60:
            complexity = "Standard"
        elif flesch_score >= 40:
            complexity = "Advanced"
        else:
            complexity = "Deep Technical"

        try:
            grade_level = textstat.text_standard(clean_prose, float_output=False)
        except Exception:
            grade_level = "College Level"
    else:
        flesch_score = 50.0
        complexity = "Standard"
        grade_level = "Standard"

    citations = count_citations_in_references(markdown_text)

    return {
        "word_count": words,
        "read_time_min": read_time,
        "flesch_score": flesch_score,
        "flesch_grade": grade_level,
        "citation_count": citations,
        "complexity_label": complexity,
    }
