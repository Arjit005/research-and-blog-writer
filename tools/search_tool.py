"""Custom search tool — searches the web using DuckDuckGo (free, no API key required)
with optional Serper.dev fallback.

This tool lets an agent search the internet via DuckDuckGo.
It returns relevant search results (titles, snippets, URLs) that the
agent can use to gather information about a topic.

Failure behaviour is explicit: when every search backend fails or returns
nothing, the tool returns a clearly-labelled "degraded" notice instead of a
normal-looking empty result, so the agent (and the reviewer) can distinguish
"no matches" from "search is unavailable".  Results are de-duplicated by URL
because DDG frequently returns the same page through multiple trackers.

The Serper.dev API key may also be supplied per-run via
:func:`scoped_serper_key` (a ``contextvars`` scope) instead of mutating the
process-wide ``os.environ``.
"""

from __future__ import annotations

import contextvars
import os
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional, Type

from pydantic import BaseModel, Field
from crewai.tools import BaseTool
from crewai_tools import SerperDevTool

from tools.source_registry import register_visited_url

try:
    from ddgs import DDGS
except ImportError:
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        DDGS = None


_RUNTIME_SERPER_KEY: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "runtime_serper_key", default=None
)


def get_serper_key() -> str:
    """Return the Serper.dev API key, preferring a runtime-scoped key."""
    return _RUNTIME_SERPER_KEY.get() or os.getenv("SERPER_API_KEY") or ""


@contextmanager
def scoped_serper_key(serper_key: Optional[str] = None) -> Iterator[None]:
    """Temporarily expose a caller-supplied Serper key to the current context only."""
    token = _RUNTIME_SERPER_KEY.set(str(serper_key)) if serper_key else None
    try:
        yield
    finally:
        if token is not None:
            _RUNTIME_SERPER_KEY.reset(token)


class SearchInput(BaseModel):
    """Input schema for SearchTool."""
    query: str = Field(description="The search query to look up on the web")


# Defensive schema rebuild so tool definitions load in the JSON-first ``crewai run`` path.
SearchInput.model_rebuild()


class SearchTool(BaseTool):
    """Search the internet for information about a given query.

    Uses DuckDuckGo (free, no API key required) or Serper.dev
    to perform web searches and return structured results including
    titles, snippets, and URLs.
    """

    name: str = "search_tool"
    description: str = (
        "Search the internet for current, relevant information about any topic. "
        "Pass a search query string to get back search results with titles, "
        "snippets, and URLs."
    )
    args_schema: Type[BaseModel] = SearchInput

    @staticmethod
    def _dedupe_results(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """De-duplicate raw search results by normalized URL, preserving order."""
        seen = set()
        unique: List[Dict[str, Any]] = []
        for item in results:
            link = str(item.get("href") or item.get("link") or item.get("url") or "").strip()
            key = link.rstrip("/").lower()
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            unique.append(item)
        return unique

    def _run(self, query: str = "", **kwargs: Any) -> str:
        """Execute a web search and return the results."""
        search_query = query or kwargs.get("search_query", "") or kwargs.get("query", "")
        if not search_query or not str(search_query).strip():
            return "Error: No search query provided."

        query_str = str(search_query).strip()
        backend_errors: List[str] = []

        # 1. Primary: DuckDuckGo search (Free, no API key needed)
        if DDGS is not None:
            try:
                ddgs = DDGS()
                results = list(ddgs.text(query_str, max_results=5))
                results = self._dedupe_results(results)
                if results:
                    formatted = []
                    for item in results:
                        title = item.get("title", "")
                        link = item.get("href") or item.get("link", "")
                        snippet = item.get("body") or item.get("snippet", "")
                        if link:
                            register_visited_url(str(link), source="search")
                        formatted.append(f"Title: {title}\nURL: {link}\nSnippet: {snippet}\n---")
                    return "\n".join(formatted)
            except Exception as exc:  # noqa: BLE001 - fall through to Serper
                backend_errors.append(f"DuckDuckGo: {type(exc).__name__}: {exc}")
        else:
            backend_errors.append("DuckDuckGo: ddgs package not installed")

        # 2. Fallback to Serper if a SERPER_API_KEY is available
        serper_key = get_serper_key()
        if serper_key:
            try:
                serper = SerperDevTool()
                results = str(serper._run(search_query=query_str))
                if results and results.strip():
                    return results
                backend_errors.append("Serper: empty response")
            except Exception as exc:  # noqa: BLE001 - report degraded, never crash the agent
                backend_errors.append(f"Serper: {type(exc).__name__}: {exc}")
        else:
            backend_errors.append("Serper: SERPER_API_KEY not configured")

        degraded = "; ".join(backend_errors)
        return (
            f"⚠️ Search degraded: web search backends unavailable or empty ({degraded}). "
            f"Notice: No web search results found for query '{query_str}'. "
            "Treat related claims as unverified and proceed with other available sources."
        )
