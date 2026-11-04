"""Visited-source registry for citation verification.

The research crew's tools record every URL they actually searched/scraped into
this process-wide registry.  When the final report is produced, ``crew.py``
builds a :class:`security.guardrails.CitationGuard` from the registry and calls
``audit_report`` so fabricated links are flagged/stripped instead of being
persisted as if they were verified sources.

The registry is intentionally tiny and dependency-free (thread-safe, no I/O) so
that tools and the crew can import it without pulling in UI/Streamlit code.
"""

from __future__ import annotations

import threading
from typing import Dict, List, Set

_LOCK = threading.Lock()

# URL -> where it came from ("search" / "scrape" / "manual")
_VISITED: Dict[str, str] = {}


def _normalize_url(url: str) -> str:
    """Normalize a URL for stable de-duplication."""
    return (url or "").strip()


def register_visited_url(url: str, source: str = "unknown") -> bool:
    """Record a successfully visited/searched URL. Returns True if newly added."""
    clean = _normalize_url(url)
    if not clean:
        return False
    with _LOCK:
        if clean in _VISITED:
            return False
        _VISITED[clean] = source
        return True


def get_visited_urls() -> Set[str]:
    """Return a snapshot of all registered URLs."""
    with _LOCK:
        return set(_VISITED.keys())


def get_visited_sources() -> List[Dict[str, str]]:
    """Return a snapshot of the registry as ``[{url, source}, ...]``."""
    with _LOCK:
        return [{"url": url, "source": source} for url, source in _VISITED.items()]


def reset_visited_urls() -> None:
    """Clear the registry (call at the start of each research run)."""
    with _LOCK:
        _VISITED.clear()
