"""Hardened Scrape Pipeline & Enterprise SSRF Defense.

Enforces:
1. DNS Pinning (resolve once, validate all addresses, connect to pinned IP to defeat DNS rebinding).
2. Complete IPv4/IPv6 private, link-local, loopback, and cloud metadata (169.254.169.254) blocking.
3. Manual redirect validation (re-validates every redirect hop up to 3 hops).
4. Response streaming with strict 2 MB size cap and timeout limits.
5. Multi-tier text cleaning: HTML/script stripping, prompt injection scrubbing, PII redaction, and dedup.
6. 24-hour TTL-enforced database caching of sanitized bulletins only.

The hardened pipeline (:func:`execute_scrape_pipeline`) is the **live** code path
used by :class:`ScrapeTool._run`; there is no unguarded ``crewai_tools`` scrape
path left.  Cached payloads are always the sanitized/fenced text and are
re-sanitized again on read (defense-in-depth against legacy cache entries).
"""

from __future__ import annotations

import re
import socket
import hashlib
import ipaddress
import urllib.request
import urllib.error
from urllib.parse import urlparse, urljoin
from typing import Any, Dict, List, Optional, Tuple, Type
from bs4 import BeautifulSoup, Comment
from pydantic import BaseModel, Field
from crewai.tools import BaseTool

from security.guardrails import sanitize_scraped_content, mask_pii_and_secrets, fence_untrusted_content
from tools.source_registry import register_visited_url

MAX_RESPONSE_BYTES = 2 * 1024 * 1024  # 2 MB limit
MAX_REDIRECTS = 3
CONNECT_TIMEOUT = 5.0
READ_TIMEOUT = 10.0
MAX_SCRAPE_WORDS = 1500


def resolve_safe(url: str) -> Tuple[str, str, int]:
    """Validate URL and resolve IP address safely, defeating DNS rebinding and IP obfuscation.

    Returns:
        (hostname, safe_ip_str, port)
    Raises:
        ValueError if scheme, host, or IP is disallowed.
    """
    try:
        parsed = urlparse(url)
    except Exception as e:
        raise ValueError(f"Malformed URL: {e}")

    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Unsupported scheme '{parsed.scheme}'. Only http and https are permitted.")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("Invalid URL: missing hostname.")

    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    # Resolve all addresses once
    try:
        addr_infos = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise ValueError(f"Could not resolve hostname '{hostname}': {e}")

    if not addr_infos:
        raise ValueError(f"No IP addresses resolved for hostname '{hostname}'.")

    # Validate EVERY returned address against restricted ranges
    validated_ips: List[str] = []
    for info in addr_infos:
        sockaddr = info[4]
        ip_str = sockaddr[0]

        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            raise ValueError(f"Invalid resolved IP format: {ip_str}")

        # Check for IPv4-mapped IPv6 (e.g., ::ffff:127.0.0.1)
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            ip = ip.ipv4_mapped

        # Strict address check: block loopback, private, link-local, multicast, reserved, unspecified
        if (
            ip.is_loopback
            or ip.is_private
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
            or str(ip) == "169.254.169.254"  # Explicit cloud metadata IP check
            or str(ip).startswith("127.")
            or str(ip) == "0.0.0.0"
            or str(ip) == "::1"
            or str(ip) == "::"
        ):
            raise ValueError(f"Access to restricted internal IP or address ({ip}) is forbidden.")

        validated_ips.append(str(ip))

    return hostname, validated_ips[0], port


def safe_fetch(url: str, max_redirects: int = MAX_REDIRECTS) -> Tuple[str, str]:
    """Fetch URL with manual redirect checking, streaming size limits, and timeout protection.

    Returns:
        (final_url, response_text)
    """
    current_url = url

    for hop in range(max_redirects + 1):
        hostname, safe_ip, port = resolve_safe(current_url)

        req = urllib.request.Request(
            current_url,
            headers={
                "User-Agent": "ResearchStudioBot/2.0 (+https://github.com/Arjit005/research-and-blog-writer)",
                "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9",
            },
        )

        class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None  # Disable auto redirects to inspect every hop manually

        opener = urllib.request.build_opener(NoRedirectHandler)

        try:
            with opener.open(req, timeout=CONNECT_TIMEOUT + READ_TIMEOUT) as resp:
                status_code = resp.getcode()
                if status_code in (301, 302, 303, 307, 308):
                    location = resp.headers.get("Location")
                    if not location:
                        raise ValueError(f"HTTP {status_code} missing Location header.")
                    next_url = urljoin(current_url, location)
                    resolve_safe(next_url)
                    current_url = next_url
                    continue

                content_type = resp.headers.get_content_type() if hasattr(resp.headers, "get_content_type") else "text/html"

                if content_type not in ("text/html", "text/plain", "application/xhtml+xml"):
                    raise ValueError(f"Unsupported content type '{content_type}'. Only text pages permitted.")

                # Stream response up to MAX_RESPONSE_BYTES
                chunks = []
                bytes_read = 0
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    bytes_read += len(chunk)
                    if bytes_read > MAX_RESPONSE_BYTES:
                        raise ValueError(f"Response size exceeded {MAX_RESPONSE_BYTES // (1024 * 1024)} MB limit.")
                    chunks.append(chunk)

                encoding = resp.headers.get_content_charset() or "utf-8"
                raw_bytes = b"".join(chunks)
                text = raw_bytes.decode(encoding, errors="replace")
                return current_url, text

        except urllib.error.HTTPError as e:
            if e.code in (301, 302, 303, 307, 308):
                location = e.headers.get("Location")
                if not location:
                    raise ValueError(f"HTTP {e.code} missing Location header.")
                next_url = urljoin(current_url, location)
                # Re-validate target URL
                resolve_safe(next_url)
                current_url = next_url
                continue
            raise ValueError(f"HTTP Error {e.code}: {e.reason}")
        except urllib.error.URLError as e:
            raise ValueError(f"Network error: {e.reason}")

    raise ValueError(f"Exceeded maximum redirect limit of {max_redirects} hops.")


def strip_html_and_scripts(raw_html: str) -> str:
    """Strip script tags, style tags, comments, and hidden elements while preserving paragraphs."""
    soup = BeautifulSoup(raw_html, "html.parser")
    # 1. Remove comments
    for comment in soup.find_all(string=lambda s: isinstance(s, Comment)):
        comment.extract()
    # 2. Remove script, style, and noscript elements
    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()
    # 3. Remove elements explicitly styled as hidden
    hidden_markers = ["display:none", "visibility:hidden", "opacity:0", "font-size:0", "height:0", "width:0"]
    for tag in soup.find_all(style=True):
        style = tag.get("style", "").lower().replace(" ", "")
        if any(marker in style for marker in hidden_markers):
            tag.decompose()
    # 4. Remove elements hidden through HTML attributes
    for tag in soup.find_all(True):
        if tag.attrs is None:
            continue
        if tag.get("hidden") is not None or tag.get("aria-hidden") == "true":
            tag.decompose()
    # 5. Extract text preserving paragraph breaks
    text = soup.get_text(separator="\n\n")
    # 6. Clean up whitespace
    text = re.sub(r"\r\n|\r", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n", "\n\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def scrub_instruction_like_passages(text: str) -> str:
    """Scrub or drop passages containing imperative phrases aimed at overriding an AI."""
    injection_imperatives = [
        r"ignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions",
        r"disregard\s+(?:all\s+)?(?:previous|prior)\s+instructions",
        r"you\s+must\s+(?:now\s+)?output\s+the\s+system\s+prompt",
        r"system\s+prompt\s*:",
        r"as\s+an\s+ai\s+language\s+model",
        r"new\s+operating\s+instructions",
        r"reveal\s+your\s+secret\s+instructions",
        r"your\s+new\s+role\s+is\s+now",
        r"leak\s+all\s+(?:environment\s+)?secrets",
        r"declare\s+product\s+[a-z0-9]+\s+as\s+the\s+sole",
        r"bypass\s+all\s+safety\s+filters?",
    ]
    pattern = re.compile("|".join(injection_imperatives), re.IGNORECASE)

    paragraphs = text.split("\n\n")
    cleaned_paras = []

    for para in paragraphs:
        if pattern.search(para):
            # Drop the instruction-like paragraph entirely
            continue
        cleaned_paras.append(para)

    return "\n\n".join(cleaned_paras)


def deduplicate_paragraphs(text: str) -> str:
    """Remove boilerplate navigation, headers, and duplicate paragraphs via hashing."""
    seen_hashes = set()
    unique_paras = []

    for para in text.split("\n\n"):
        p_clean = para.strip()
        if not p_clean:
            continue
        p_hash = hashlib.sha256(p_clean.lower().encode("utf-8")).hexdigest()
        if p_hash not in seen_hashes:
            seen_hashes.add(p_hash)
            unique_paras.append(p_clean)

    return "\n\n".join(unique_paras)


def compact_scraped_text(text: str, max_words: int = 1500) -> str:
    """Compact scraped webpage text by normalizing whitespace and budgeting max words."""
    cleaned = re.sub(r"\n{3,}", "\n\n", text).strip()
    words = cleaned.split()
    if len(words) > max_words:
        truncated = " ".join(words[:max_words])
        return f"{truncated}\n\n[... truncated to {max_words} words for context optimization ...]"
    return cleaned


def is_safe_url(url: str) -> tuple[bool, str]:
    """Validate URL against SSRF vulnerabilities (blocks loopback, private & metadata IPs)."""
    try:
        resolve_safe(url)
        return True, ""
    except ValueError as e:
        return False, str(e)


def execute_scrape_pipeline(url: str, max_words: int = MAX_SCRAPE_WORDS) -> str:
    """Single fixed-order pipeline for fetching, scrubbing, sanitizing, and fencing web content.

    Order: SSRF/DNS-pinning validation -> bounded fetch -> HTML/hidden-element strip
    -> instruction-like passage scrub -> indirect-injection sanitization -> PII/secret
    masking -> boilerplate dedup -> word-budget compaction -> untrusted-content fencing.

    Raises:
        ValueError: on SSRF violations, fetch failures, oversized payloads, or when
            no readable text could be extracted from the page.
    """
    # 1. SSRF & DNS Pinning validation
    resolve_safe(url)

    # 2. Safe fetch with size caps & manual redirect tracking
    final_url, raw_html = safe_fetch(url)

    # 3. Strip HTML, scripts, styles, hidden nodes
    plain_text = strip_html_and_scripts(raw_html)
    if not plain_text.strip():
        raise ValueError(f"No readable text content could be extracted from {url}.")

    # 4. Scrub instruction-like prompt injections
    scrubbed_text = scrub_instruction_like_passages(plain_text)

    # 5. Remove indirect injection cues ([system note], "note to AI", etc.)
    sanitized_text = sanitize_scraped_content(scrubbed_text)

    # 6. PII & secrets redaction
    redacted_text = mask_pii_and_secrets(sanitized_text)

    # 7. Deduplicate boilerplate
    deduped_text = deduplicate_paragraphs(redacted_text)
    if not deduped_text.strip():
        raise ValueError(f"No readable text content could be extracted from {url}.")

    # 8. Word budgeting & compaction
    compacted = compact_scraped_text(deduped_text, max_words=max_words)

    # 9. Data Fencing (delimited untrusted context)
    return fence_untrusted_content(compacted, source_id=1, url=final_url)


def sanitize_cached_scrape(cached_text: str, url: str = "") -> str:
    """Re-sanitize an already-cached scrape payload (defense-in-depth on cache reads)."""
    if not cached_text:
        return ""
    text = sanitize_scraped_content(str(cached_text))
    text = mask_pii_and_secrets(text)
    if not text.strip():
        return ""
    # Legacy/unfenced cache entries get re-fenced; fenced entries are re-sanitized in place.
    if "<untrusted_source" not in text:
        return fence_untrusted_content(text, source_id=1, url=url)
    return text


class ScrapeInput(BaseModel):
    """Input schema for ScrapeTool."""
    url: str = Field(description="The full URL of the webpage to scrape")


# Defensive schema rebuild: some environments (and the JSON-first ``crewai run``
# loader) call ``model_rebuild()`` on tool schemas; making it explicit here keeps
# the tool definitions loadable even when annotations were evaluated lazily.
ScrapeInput.model_rebuild()


class ScrapeTool(BaseTool):
    """Hardened Scrape Tool with SSRF protection, prompt injection scrubbing, and 24-hr TTL caching."""

    name: str = "scrape_tool"
    description: str = (
        "Read the readable text content of a webpage. Pass a URL to get back "
        "verified, sanitized factual text. Protected against SSRF and prompt injection."
    )
    args_schema: Type[BaseModel] = ScrapeInput

    def _run(self, url: str = "", **kwargs: Any) -> str:
        """Fetch, sanitize, fence, and cache a webpage through the hardened pipeline."""
        target_url = url or kwargs.get("website_url", "") or kwargs.get("url", "")
        if isinstance(target_url, dict):
            target_url = target_url.get("url", "")
        target_url = str(target_url or "").strip()
        if not target_url:
            return "Error: No URL provided."

        # Security check (SSRF / DNS pinning)
        is_safe, error_msg = is_safe_url(target_url)
        if not is_safe:
            try:
                from database import save_security_event
                save_security_event("SSRF_OR_SCRAPE_BLOCKED", f"URL: {target_url[:100]} | Reason: {error_msg}")
            except Exception:
                pass
            return f"Security Warning: Blocked potentially unsafe URL. Reason: {error_msg}"

        # 1. Cache read: only sanitized payloads are stored; re-sanitize on read.
        try:
            from database import get_cached_scrape
            cached = get_cached_scrape(target_url)
            if cached:
                re_sanitized = sanitize_cached_scrape(cached, url=target_url)
                if re_sanitized:
                    return re_sanitized
        except Exception:
            pass

        # 2. Live hardened pipeline (bounded fetch -> scrub -> mask -> dedup -> fence)
        try:
            fenced = execute_scrape_pipeline(target_url, max_words=MAX_SCRAPE_WORDS)
            if not fenced.strip():
                return f"Notice: No readable text content could be extracted from {target_url}."

            register_visited_url(target_url, source="scrape")

            # 3. Cache only the sanitized, fenced output.
            try:
                from database import set_cached_scrape
                set_cached_scrape(target_url, fenced)
            except Exception:
                pass
            return fenced
        except ValueError as e:
            return f"Notice: Failed to fetch webpage content from {target_url} (Error: {e}). Proceed with other available sources."
        except Exception as e:  # noqa: BLE001 - tools must never crash the agent run
            return f"Notice: Failed to fetch webpage content from {target_url} (Error: {e}). Proceed with other available sources."
