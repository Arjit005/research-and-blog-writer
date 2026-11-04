"""Custom search tool — searches the web using DuckDuckGo (free, no API key required)
with optional Serper.dev fallback.

This tool lets an agent search the internet via DuckDuckGo.
It returns relevant search results (titles, snippets, URLs) that the
agent can use to gather information about a topic.
"""

import os
from typing import Any, Optional, Type
from pydantic import BaseModel, Field
from crewai.tools import BaseTool
from crewai_tools import SerperDevTool

try:
    from ddgs import DDGS
except ImportError:
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        DDGS = None


class SearchInput(BaseModel):
    """Input schema for SearchTool."""
    query: str = Field(description="The search query to look up on the web")


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

    def _run(self, query: str = "", **kwargs: Any) -> str:
        """Execute a web search and return the results."""
        search_query = query or kwargs.get("search_query", "") or kwargs.get("query", "")
        if not search_query or not search_query.strip():
            return "Error: No search query provided."

        query_str = search_query.strip()

        # 1. Primary: DuckDuckGo search (Free, no API key needed)
        if DDGS is not None:
            try:
                ddgs = DDGS()
                results = list(ddgs.text(query_str, max_results=5))
                if results:
                    formatted = []
                    for item in results:
                        title = item.get("title", "")
                        link = item.get("href") or item.get("link", "")
                        snippet = item.get("body") or item.get("snippet", "")
                        formatted.append(f"Title: {title}\nURL: {link}\nSnippet: {snippet}\n---")
                    return "\n".join(formatted)
            except Exception:
                pass

        # 2. Fallback to Serper if SERPER_API_KEY is available
        if os.getenv("SERPER_API_KEY"):
            try:
                serper = SerperDevTool()
                results = str(serper._run(search_query=query_str))
                if results and results.strip():
                    return results
            except Exception:
                pass

        return f"Notice: No web search results found for query '{query_str}'. Try alternate keywords."
