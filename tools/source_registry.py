"""Visited-source registry for citation verification.

The research crew's tools record every URL they actually searched/scraped into
this process-wide registry.  When the final report is produced, ``crew.py``
builds a :class:`security.guardrails.CitationGuard` from the registry and calls
``audit_report`` so fabricated links are flagged/stripped instead of being
persisted as if they were verified sources.

The registry is intentionally tiny and dependency-free (thread-safe, no I/O) so
that tools and the crew can import it without pulling in presentation code.
"""

from __future__ import annotations

import threading
import json
import os
from pathlib import Path
from typing import Optional
from typing import Dict, List, Set

_LOCK = threading.Lock()

# URL -> where it came from ("search" / "scrape" / "manual")
_VISITED: Dict[str, str] = {}
_STORAGE_PATH: Optional[Path] = None


def configure_visited_url_storage(path: Optional[Path]) -> None:
    """Restore and persist the current run's source registry across worker restarts."""
    global _STORAGE_PATH
    with _LOCK:
        _STORAGE_PATH = path
        _VISITED.clear()
        if path is None:
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                _VISITED.update({str(url): str(source) for url, source in payload.items()})
        except FileNotFoundError:
            pass
        except Exception:
            # A corrupt sidecar must not prevent the research task from running.
            _VISITED.clear()


def disable_visited_url_storage() -> None:
    """Detach run-scoped storage before another job executes in this process."""
    global _STORAGE_PATH
    with _LOCK:
        _STORAGE_PATH = None
        _VISITED.clear()


def _persist_locked() -> None:
    if _STORAGE_PATH is None:
        return
    try:
        _STORAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
        temp_path = _STORAGE_PATH.with_suffix(_STORAGE_PATH.suffix + ".tmp")
        temp_path.write_text(json.dumps(_VISITED, ensure_ascii=False), encoding="utf-8")
        os.replace(temp_path, _STORAGE_PATH)
    except Exception:
        # Registry persistence is best-effort; CrewAI's own task checkpoints are
        # the authoritative resume state.
        pass


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
        _persist_locked()
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
        _persist_locked()
