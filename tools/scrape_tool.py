"""Custom scrape tool — wraps crewAI's ScrapeWebsiteTool for webpage scraping.

This tool lets an agent extract the full text content from any webpage.
Useful for the Content Analyst (to verify claims) and the Quality
Reviewer (to fact-check specific sources).

Requirements:
    - The ``crewai[tools]`` extra installed (included in pyproject.toml)
    - No API key needed — uses HTTP requests directly
"""

import ipaddress
import socket
import re
from typing import Any, Optional, Type
from urllib.parse import urlparse
from pydantic import BaseModel, Field
from crewai.tools import BaseTool
from crewai_tools import ScrapeWebsiteTool
from security.guardrails import sanitize_scraped_content


def compact_scraped_text(text: str, max_words: int = 1500) -> str:
    """Compact scraped webpage text by normalizing whitespace and budgeting max words."""
    cleaned = re.sub(r"\n{3,}", "\n\n", text).strip()
    words = cleaned.split()
    if len(words) > max_words:
        truncated = " ".join(words[:max_words])
        return f"{truncated}\n\n[... Content truncated to {max_words} words for context optimization ...]"
    return cleaned


def is_safe_url(url: str) -> tuple[bool, str]:
    """Validate URL against SSRF vulnerabilities (blocks loopback, private & metadata IPs)."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False, f"Unsupported scheme '{parsed.scheme}'. Only HTTP and HTTPS are permitted."

        hostname = parsed.hostname
        if not hostname:
            return False, "Invalid URL: missing hostname."

        # Quick check for known restricted hostnames
        if hostname.lower() in ("localhost", "127.0.0.1", "::1") or hostname.lower().endswith((".local", ".internal")):
            return False, "Access to localhost and internal domain names is forbidden."

        # Resolve hostname to check underlying IP addresses
        addr_info = socket.getaddrinfo(hostname, None)
        for entry in addr_info:
            ip_str = entry[4][0]
            ip = ipaddress.ip_address(ip_str)

            # Block loopback, private, link-local (169.254.x.x cloud metadata), and reserved ranges
            if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                return False, f"Access to restricted internal IP address ({ip_str}) is forbidden."

        return True, ""
    except socket.gaierror:
        return False, "Could not resolve hostname."
    except Exception as e:
        return False, f"URL validation error: {e}"


class ScrapeInput(BaseModel):
    """Input schema for ScrapeTool."""
    url: str = Field(description="The full URL of the webpage to scrape")


class ScrapeTool(BaseTool):
    """Scrape a webpage and extract its text content securely.

    Given a URL, this tool fetches the page and returns its readable
    text content (HTML tags stripped). Includes SSRF protection against
    internal network scanning and indirect prompt injection sanitization.
    """

    name: str = "scrape_tool"
    description: str = (
        "Read the full text content of a webpage. Pass a URL to get back "
        "the page's readable text content. Useful for verifying facts or "
        "extracting details from a specific source."
    )
    args_schema: Type[BaseModel] = ScrapeInput

    def _run(self, url: str = "", **kwargs: Any) -> str:
        """Fetch and extract text content from a webpage with SSRF and injection guards."""
        target_url = url or kwargs.get("website_url", "") or kwargs.get("url", "")
        if not target_url:
            return "Error: No URL provided."

        # Security check
        is_safe, error_msg = is_safe_url(target_url)
        if not is_safe:
            return f"Security Warning: Blocked potentially unsafe URL. Reason: {error_msg}"

        # Check database research cache for instant retrieval & zero redundant calls
        try:
            from database import get_cached_scrape, set_cached_scrape
            cached = get_cached_scrape(target_url)
            if cached:
                return cached
        except Exception:
            pass

        try:
            scraper = ScrapeWebsiteTool(website_url=target_url)
            content = str(scraper._run(website_url=target_url))
            if not content.strip():
                return f"Notice: No readable text content could be extracted from {target_url}."
            sanitized = sanitize_scraped_content(content)
            compacted = compact_scraped_text(sanitized, max_words=1500)
            try:
                set_cached_scrape(target_url, compacted)
            except Exception:
                pass
            return compacted
        except Exception as e:
            return f"Notice: Failed to fetch webpage content from {target_url} (Error: {e}). Proceed with other available sources."
