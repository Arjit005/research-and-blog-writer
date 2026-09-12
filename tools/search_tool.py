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
        """Execute a web search and return the results."""
        search_query = query or kwargs.get("search_query", "") or kwargs.get("query", "")
        if not search_query or not search_query.strip():
            return "Error: No search query provided."

        if not os.getenv("SERPER_API_KEY"):
            return "Search unavailable: SERPER_API_KEY is missing from environment. Proceed using prior task context."

        try:
            serper = SerperDevTool()
            results = str(serper._run(search_query=search_query.strip()))
            if not results.strip():
                return f"Notice: No web search results found for query '{search_query}'. Try alternate keywords."
            return results
        except Exception as e:
            return f"Notice: Search request failed for '{search_query}' ({e}). Proceed with other available context."
