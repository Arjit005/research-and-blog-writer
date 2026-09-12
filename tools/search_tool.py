"""Custom search tool — wraps crewAI's SerperDevTool for web searching.

This tool lets an agent search the internet via the Serper.dev API.
It returns relevant search results (titles, snippets, URLs) that the
agent can use to gather information about a topic.

Requirements:
    - A valid SERPER_API_KEY in your .env file
    - The ``crewai[tools]`` extra installed (included in pyproject.toml)
"""

import os
from typing import Any, Optional, Type
from pydantic import BaseModel, Field
from crewai.tools import BaseTool
from crewai_tools import SerperDevTool


class SearchInput(BaseModel):
    """Input schema for SearchTool."""
    query: str = Field(description="The search query to look up on Google")


class SearchTool(BaseTool):
    """Search the internet for information about a given query.

    Uses the Serper.dev API to perform Google searches and return
    structured results including titles, snippets, and URLs.
    """

    name: str = "search_tool"
    description: str = (
        "Search the internet for current, relevant information about any topic. "
        "Pass a search query string to get back search results with titles, "
        "snippets, and URLs."
    )
    args_schema: Type[BaseModel] = SearchInput

    def _run(self, query: str = "", **kwargs: Any) -> str:
        """Execute a web search and return the results with automatic failover."""
        import os
        search_query = query or kwargs.get("search_query", "") or kwargs.get("query", "")
        if not search_query or not search_query.strip():
            return "Error: No search query provided."

        # 1. Try SerperDevTool if API key is provided
        if os.getenv("SERPER_API_KEY"):
            try:
                serper = SerperDevTool()
                res = str(serper._run(search_query=search_query.strip()))
                if res and "unauthorized" not in res.lower() and "invalid api key" not in res.lower() and res.strip():
                    return res
            except Exception as e:
                print(f"[WARNING] SerperDev search failed: {e}. Switching to DuckDuckGo fallback...")

        # 2. Resilient Fallback: DuckDuckGo Search (No API Key Required)
        try:
            from ddgs import DDGS
            results = list(DDGS().text(search_query.strip(), max_results=5))
            if results:
                formatted = []
                for item in results:
                    title = item.get("title", "No Title")
                    link = item.get("href", "")
                    body = item.get("body", "")
                    formatted.append(f"Title: {title}\nURL: {link}\nSnippet: {body}")
                return "\n\n---\n\n".join(formatted)
        except Exception as ddg_err:
            print(f"[WARNING] DuckDuckGo fallback failed: {ddg_err}")

        return f"Notice: No web search results could be retrieved for '{search_query}'. Proceed using prior task context."

