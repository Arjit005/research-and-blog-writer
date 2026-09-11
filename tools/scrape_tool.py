"""Custom scrape tool — wraps crewAI's ScrapeWebsiteTool for webpage scraping.

This tool lets an agent extract the full text content from any webpage.
Useful for the Content Analyst (to verify claims) and the Quality
Reviewer (to fact-check specific sources).

Requirements:
    - The ``crewai[tools]`` extra installed (included in pyproject.toml)
    - No API key needed — uses HTTP requests directly
"""

from typing import Any, Optional, Type
from pydantic import BaseModel, Field
from crewai.tools import BaseTool
from crewai_tools import ScrapeWebsiteTool


class ScrapeInput(BaseModel):
    """Input schema for ScrapeTool."""
    url: str = Field(description="The full URL of the webpage to scrape")


class ScrapeTool(BaseTool):
    """Scrape a webpage and extract its text content.

    Given a URL, this tool fetches the page and returns its readable
    text content (HTML tags stripped).
    """

    name: str = "scrape_tool"
    description: str = (
        "Read the full text content of a webpage. Pass a URL to get back "
        "the page's readable text content. Useful for verifying facts or "
        "extracting details from a specific source."
    )
    args_schema: Type[BaseModel] = ScrapeInput

    def _run(self, url: str = "", **kwargs: Any) -> str:
        """Fetch and extract text content from a webpage."""
        target_url = url or kwargs.get("website_url", "") or kwargs.get("url", "")
        if not target_url:
            return "Error: No URL provided."
        try:
            scraper = ScrapeWebsiteTool(website_url=target_url)
            return str(scraper._run(website_url=target_url))
        except Exception as e:
            return f"Scrape error: {e}"
