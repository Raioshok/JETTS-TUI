"""Built-in keyless web search + page extraction.

No API key, no optional package: search scrapes DuckDuckGo's HTML endpoints
over ``httpx`` (a core dependency) and extract fetches pages directly and
converts them to readable Markdown with :mod:`plugins.web.native.html_to_markdown`.

Redirects are followed by hand so every hop passes the same SSRF check the
``web_extract`` dispatcher applies to the requested URL.
"""

from __future__ import annotations

import asyncio
import logging
import re
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urljoin, urlparse

from agent.web_search_provider import WebSearchProvider
from plugins.web.native.html_to_markdown import html_to_markdown

logger = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)
_HEADERS = {
    "User-Agent": _USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,text/plain;q=0.8,*/*;q=0.5",
    "Accept-Language": "en-US,en;q=0.9",
}
_SEARCH_TIMEOUT = 15.0
_FETCH_TIMEOUT = 20.0
_MAX_REDIRECTS = 5
_MAX_BYTES = 8 * 1024 * 1024
_TEXT_TYPES = ("text/plain", "text/markdown", "text/csv", "application/json", "text/xml",
               "application/xml", "application/rss+xml", "application/atom+xml")


# =============================================================================
# DuckDuckGo result parsing
# =============================================================================

def _unwrap_ddg_href(href: str) -> str:
    """DDG wraps targets as ``//duckduckgo.com/l/?uddg=<url>``; unwrap them."""
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        return target
    return href


def _is_ad(href: str) -> bool:
    return "duckduckgo.com/y.js" in href or "ad_provider" in href or "ad_domain" in href


class _DDGParser(HTMLParser):
    """Collect results from html.duckduckgo.com or lite.duckduckgo.com."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: List[Dict[str, str]] = []
        self._field: Optional[str] = None
        self._buf: List[str] = []
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        classes = (a.get("class") or "").split()
        if self._field is not None:
            self._depth += 1
            return
        if tag == "a" and ("result__a" in classes or "result-link" in classes):
            href = a.get("href") or ""
            self.results.append({"title": "", "url": _unwrap_ddg_href(href), "description": "", "_ad": _is_ad(href)})
            self._field, self._buf, self._depth = "title", [], 0
        elif ("result__snippet" in classes or "result-snippet" in classes) and self.results:
            self._field, self._buf, self._depth = "description", [], 0

    def handle_endtag(self, tag):
        if self._field is None:
            return
        if self._depth > 0:
            self._depth -= 1
            return
        text = re.sub(r"\s+", " ", "".join(self._buf)).strip()
        if self.results and not self.results[-1][self._field]:
            self.results[-1][self._field] = text
        self._field = None

    def handle_data(self, data):
        if self._field is not None:
            self._buf.append(data)


def parse_ddg_results(html: str, limit: int) -> List[Dict[str, Any]]:
    parser = _DDGParser()
    parser.feed(html)
    out: List[Dict[str, Any]] = []
    seen = set()
    for r in parser.results:
        url = r["url"]
        if r["_ad"] or not url.startswith(("http://", "https://")) or url in seen:
            continue
        seen.add(url)
        out.append({"title": r["title"], "url": url, "description": r["description"], "position": len(out) + 1})
        if len(out) >= limit:
            break
    return out


# =============================================================================
# Fetching
# =============================================================================

def _sniff_charset(raw: bytes, header_charset: Optional[str]) -> str:
    if header_charset:
        return header_charset
    m = re.search(rb"<meta[^>]+charset=[\"']?([\w-]+)", raw[:4096], re.I)
    return m.group(1).decode("ascii", "ignore") if m else "utf-8"


async def _url_is_safe(url: str) -> bool:
    try:
        from tools.url_safety import is_safe_url
    except ImportError:  # pragma: no cover — url_safety ships in core
        return True
    return await asyncio.to_thread(is_safe_url, url)


async def _fetch(client, url: str) -> Tuple[str, str, bytes, Optional[str]]:
    """GET ``url`` following redirects safely → ``(final_url, content_type, body, charset)``."""
    current = url
    for _ in range(_MAX_REDIRECTS + 1):
        async with client.stream("GET", current) as resp:
            if resp.status_code in (301, 302, 303, 307, 308) and resp.headers.get("location"):
                nxt = urljoin(current, resp.headers["location"])
                if not await _url_is_safe(nxt):
                    raise ValueError("Blocked: redirect targets a private or internal network address")
                current = nxt
                continue
            if resp.status_code >= 400:
                raise ValueError(f"HTTP {resp.status_code} fetching {current}")
            chunks: List[bytes] = []
            size = 0
            async for chunk in resp.aiter_bytes():
                chunks.append(chunk)
                size += len(chunk)
                if size > _MAX_BYTES:
                    break
            ctype = resp.headers.get("content-type", "").split(";")[0].strip().lower()
            return str(resp.url), ctype, b"".join(chunks), resp.charset_encoding
    raise ValueError(f"Too many redirects fetching {url}")


async def _extract_one(client, url: str) -> Dict[str, Any]:
    try:
        final_url, ctype, raw, charset = await _fetch(client, url)
    except ValueError as exc:
        return {"url": url, "title": "", "content": "", "error": str(exc)}
    except Exception as exc:  # noqa: BLE001 — network errors become per-URL errors
        return {"url": url, "title": "", "content": "", "error": f"Fetch failed: {type(exc).__name__}: {exc}"}

    if ctype == "application/pdf" or raw[:5] == b"%PDF-":
        return {"url": final_url, "title": "", "content": "",
                "error": "PDF documents are not supported by the built-in extractor; "
                         "download the file and read it locally instead."}
    text = raw.decode(_sniff_charset(raw, charset), errors="replace")
    is_html = ctype in ("text/html", "application/xhtml+xml") or (
        not ctype and re.search(r"<html|<!doctype html", text[:1024], re.I)
    )
    if is_html:
        title, markdown = await asyncio.to_thread(html_to_markdown, text, final_url)
        if not markdown.strip():
            return {"url": final_url, "title": title, "content": "",
                    "error": "Page has no readable text (it may need JavaScript — try the browser tools)."}
        return {"url": final_url, "title": title, "content": markdown, "raw_content": markdown,
                "metadata": {"content_type": ctype or "text/html"}}
    if ctype.startswith("text/") or ctype in _TEXT_TYPES:
        return {"url": final_url, "title": "", "content": text, "raw_content": text,
                "metadata": {"content_type": ctype}}
    return {"url": final_url, "title": "", "content": "",
            "error": f"Unsupported content type '{ctype or 'unknown'}' for text extraction."}


# =============================================================================
# Provider
# =============================================================================

class NativeWebSearchProvider(WebSearchProvider):
    """Keyless search (DuckDuckGo HTML) + direct-fetch extraction."""

    @property
    def name(self) -> str:
        return "native"

    @property
    def display_name(self) -> str:
        return "Built-in (DuckDuckGo search + direct page fetch, no API key)"

    def is_available(self) -> bool:
        return True

    def supports_search(self) -> bool:
        return True

    def supports_extract(self) -> bool:
        return True

    def search(self, query: str, limit: int = 5) -> Dict[str, Any]:
        import httpx

        from tools.interrupt import is_interrupted

        limit = max(1, min(int(limit or 5), 25))
        endpoints = (
            ("https://html.duckduckgo.com/html/", {"q": query, "kl": "wt-wt"}),
            ("https://lite.duckduckgo.com/lite/", {"q": query, "kl": "wt-wt"}),
        )
        last_error = "no results"
        try:
            with httpx.Client(headers=_HEADERS, timeout=_SEARCH_TIMEOUT, follow_redirects=True) as client:
                for endpoint, form in endpoints:
                    if is_interrupted():
                        return {"success": False, "error": "Interrupted"}
                    try:
                        resp = client.post(endpoint, data=form)
                    except httpx.HTTPError as exc:
                        last_error = f"{type(exc).__name__}: {exc}"
                        continue
                    if resp.status_code != 200:
                        # 202 is DDG's bot-challenge page.
                        last_error = f"HTTP {resp.status_code} from {urlparse(endpoint).netloc}"
                        continue
                    results = parse_ddg_results(resp.text, limit)
                    if results:
                        return {"success": True, "data": {"web": results}}
                    if "No results" in resp.text or "No more results" in resp.text:
                        return {"success": True, "data": {"web": []}}
                    last_error = "no parseable results (DuckDuckGo may be rate limiting)"
        except Exception as exc:  # noqa: BLE001
            last_error = f"{type(exc).__name__}: {exc}"
        return {
            "success": False,
            "error": f"Built-in web search failed: {last_error}. "
                     "Configure another backend with `jettstui tools` if this persists.",
        }

    async def extract(self, urls: List[str], **kwargs: Any) -> List[Dict[str, Any]]:
        import httpx

        async with httpx.AsyncClient(headers=_HEADERS, timeout=_FETCH_TIMEOUT, follow_redirects=False) as client:
            return list(await asyncio.gather(*(_extract_one(client, u) for u in urls)))
