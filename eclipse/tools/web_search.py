#!/usr/bin/env python3
"""
web_search tool.

Backends: a search API you configured (Brave, Tavily or Serper, key in the vault) is tried
first. The keyless fallbacks read a results page: DuckDuckGo Lite, then Brave's web page,
then Bing. Scraping needs no account but can break when a site changes its page or blocks
an address, and Bing serves unrelated pages for some queries, so every backend's answer goes
through a relevance check and the result says which backend answered.

Settings: `search_backend` (auto | brave | tavily | serper; "auto" is the keyless chain) and
`search_api_key` (encrypted; never returned by the API).
"""

import asyncio
import base64
import logging
import re
import time
from collections import OrderedDict
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlsplit

import httpx

from . import Tool, ToolContext, ToolError, ToolResult, register

log = logging.getLogger("eclipse.tools.web_search")

BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
MAX_QUERY_CHARS = 400
SEARCH_TIMEOUT = 12.0
KEYED_BACKENDS = ("brave", "tavily", "serper")


# Keyless pages answer a burst of queries from one address with a bot check (DuckDuckGo: HTTP 202,
# Brave: 429), and an agent loop searches several times in a row. So keyless requests are spaced
# out, and an identical search within a few minutes is answered from memory.
KEYLESS_MIN_INTERVAL = 2.5
CACHE_TTL = 600.0
CACHE_MAX = 64
_last_request: Dict[str, float] = {}
_CACHE: "OrderedDict[tuple, tuple]" = OrderedDict()


class SearchBackendError(Exception):
    """One backend failed; the next one may still work."""


async def _space_out(backend_id: str) -> None:
    """Wait until this keyless backend may be asked again. Reserves the slot before sleeping."""
    if backend_id not in KEYLESS_CHAIN or KEYLESS_MIN_INTERVAL <= 0:
        return
    now = time.monotonic()
    slot = max(now, _last_request.get(backend_id, 0.0) + KEYLESS_MIN_INTERVAL)
    _last_request[backend_id] = slot
    if slot > now:
        await asyncio.sleep(slot - now)


# ---------------------------------------------------------------------------
# Bing results page (no key)
# ---------------------------------------------------------------------------

def decode_bing_url(href: str) -> str:
    """Bing wraps result links in /ck/a?...&u=a1<base64url of the real URL>."""
    parts = urlsplit(href)
    if parts.netloc.endswith("bing.com") and parts.path.startswith("/ck/a"):
        u = (parse_qs(parts.query).get("u") or [""])[0]
        if u.startswith("a1"):
            payload = u[2:]
            try:
                decoded = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)).decode("utf-8")
            except Exception:
                return ""
            return decoded if decoded.startswith(("http://", "https://")) else ""
        return ""
    return href if href.startswith(("http://", "https://")) else ""


class _BingParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: List[Dict[str, str]] = []
        self._item: Optional[Dict[str, Any]] = None
        self._in_h2 = False
        self._in_title_a = False
        self._in_caption = False
        self._in_snippet_p = False

    def _finish(self) -> None:
        item, self._item = self._item, None
        if item and item["href"] and item["title"].strip():
            url = decode_bing_url(item["href"])
            if url:
                self.results.append({
                    "title": " ".join(item["title"].split()),
                    "url": url,
                    "snippet": " ".join(item["snippet"].split()),
                })

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        classes = (a.get("class") or "").split()
        if tag == "li" and "b_algo" in classes:
            self._finish()
            self._item = {"href": "", "title": "", "snippet": ""}
            self._in_h2 = self._in_title_a = self._in_caption = self._in_snippet_p = False
            return
        if not self._item:
            return
        if tag == "h2" and not self._item["title"]:
            self._in_h2 = True
        elif tag == "a" and self._in_h2 and not self._item["href"]:
            self._item["href"] = a.get("href") or ""
            self._in_title_a = True
        elif tag == "div" and "b_caption" in classes:
            self._in_caption = True
        elif tag == "p" and self._in_caption and not self._item["snippet"]:
            self._in_snippet_p = True

    def handle_endtag(self, tag):
        if not self._item:
            return
        if tag == "a":
            self._in_title_a = False
        elif tag == "h2":
            self._in_h2 = False
        elif tag == "p":
            self._in_snippet_p = False

    def handle_data(self, data):
        if not self._item:
            return
        if self._in_title_a:
            self._item["title"] += data
        elif self._in_snippet_p:
            self._item["snippet"] += data

    def close(self):
        super().close()
        self._finish()


def parse_bing_results(html: str) -> List[Dict[str, str]]:
    parser = _BingParser()
    parser.feed(html)
    parser.close()
    return parser.results


async def _bing(client: httpx.AsyncClient, query: str, limit: int, key: str) -> List[Dict[str, str]]:
    try:
        r = await client.get(
            "https://www.bing.com/search",
            params={"q": query, "setlang": "en-US", "cc": "US", "count": str(min(limit + 4, 20))},
            headers={"User-Agent": BROWSER_UA, "Accept-Language": "en-US,en;q=0.9"},
        )
    except httpx.HTTPError as e:
        raise SearchBackendError(f"Bing request failed: {e.__class__.__name__}")
    if r.status_code != 200:
        raise SearchBackendError(f"Bing answered HTTP {r.status_code}")
    results = parse_bing_results(r.text)
    if not results:
        raise SearchBackendError("Bing returned no results we could read (blocked, or its page layout changed)")
    return results[:limit]


# ---------------------------------------------------------------------------
# DuckDuckGo Lite (no key)
# ---------------------------------------------------------------------------

def decode_ddg_url(href: str) -> str:
    """Lite wraps links as //duckduckgo.com/l/?uddg=<encoded URL>. Ads have no uddg and are dropped."""
    parts = urlsplit(href if not href.startswith("//") else "https:" + href)
    if parts.netloc.endswith("duckduckgo.com"):
        target = (parse_qs(parts.query).get("uddg") or [""])[0]
        return target if target.startswith(("http://", "https://")) else ""
    return href if href.startswith(("http://", "https://")) else ""


class _DdgParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: List[Dict[str, str]] = []
        self._item: Optional[Dict[str, str]] = None
        self._in_link = False
        self._in_snippet = False

    def _finish(self) -> None:
        item, self._item = self._item, None
        if item and item["href"]:
            url = decode_ddg_url(item["href"])
            title = " ".join(item["title"].split())
            if url and title:
                self.results.append({"title": title, "url": url, "snippet": " ".join(item["snippet"].split())})

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        classes = (a.get("class") or "").split()
        if tag == "a" and "result-link" in classes:
            self._finish()
            self._item = {"href": a.get("href") or "", "title": "", "snippet": ""}
            self._in_link = True
        elif tag == "td" and "result-snippet" in classes and self._item is not None:
            self._in_snippet = True

    def handle_endtag(self, tag):
        if tag == "a":
            self._in_link = False
        elif tag == "td":
            self._in_snippet = False

    def handle_data(self, data):
        if self._item is None:
            return
        if self._in_link:
            self._item["title"] += data
        elif self._in_snippet:
            self._item["snippet"] += data

    def close(self):
        super().close()
        self._finish()


def parse_ddg_results(html: str) -> List[Dict[str, str]]:
    parser = _DdgParser()
    parser.feed(html)
    parser.close()
    return parser.results


async def _duckduckgo(client: httpx.AsyncClient, query: str, limit: int, key: str) -> List[Dict[str, str]]:
    try:
        r = await client.get(
            "https://lite.duckduckgo.com/lite/",
            params={"q": query, "kl": "us-en"},
            headers={"User-Agent": BROWSER_UA, "Accept-Language": "en-US,en;q=0.9"},
        )
    except httpx.HTTPError as e:
        raise SearchBackendError(f"DuckDuckGo request failed: {e.__class__.__name__}")
    if r.status_code != 200:
        raise SearchBackendError(f"DuckDuckGo answered HTTP {r.status_code}")
    if "anomaly" in r.text[:5000]:
        raise SearchBackendError("DuckDuckGo asked for a bot check")
    results = parse_ddg_results(r.text)
    if not results:
        raise SearchBackendError("DuckDuckGo returned no results we could read")
    return results[:limit]


# ---------------------------------------------------------------------------
# Brave search page (no key)
# ---------------------------------------------------------------------------

class _BraveParser(HTMLParser):
    """Reads `div.snippet[data-type=web]` blocks from search.brave.com."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: List[Dict[str, str]] = []
        self._item: Optional[Dict[str, str]] = None
        self._cap: Optional[str] = None     # "title" | "snippet"
        self._cap_depth = 0
        self._in_generic = False

    def _finish(self) -> None:
        item, self._item = self._item, None
        self._cap = None
        if item and item["url"] and item["title"].strip():
            self.results.append({
                "title": " ".join(item["title"].split()),
                "url": item["url"],
                "snippet": " ".join(item["snippet"].split()),
            })

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        classes = (a.get("class") or "").split()
        if tag == "div" and "snippet" in classes and a.get("data-type") == "web":
            self._finish()
            self._item = {"url": "", "title": "", "snippet": ""}
            self._in_generic = False
            return
        if self._item is None:
            return
        if self._cap:
            if tag == "div":
                self._cap_depth += 1
            return
        if tag == "a" and not self._item["url"]:
            href = a.get("href") or ""
            if href.startswith(("http://", "https://")) and "brave.com" not in urlsplit(href).netloc:
                self._item["url"] = href
        elif tag == "div" and "title" in classes and not self._item["title"]:
            if a.get("title"):
                self._item["title"] = a["title"]
            else:
                self._cap, self._cap_depth = "title", 0
        elif tag == "div" and "generic-snippet" in classes:
            self._in_generic = True
        elif tag == "div" and self._in_generic and "content" in classes and not self._item["snippet"]:
            self._cap, self._cap_depth = "snippet", 0

    def handle_endtag(self, tag):
        if self._cap and tag == "div":
            if self._cap_depth == 0:
                self._cap = None
            else:
                self._cap_depth -= 1

    def handle_data(self, data):
        if self._item is not None and self._cap:
            self._item[self._cap] += data

    def close(self):
        super().close()
        self._finish()


def parse_brave_results(html: str) -> List[Dict[str, str]]:
    parser = _BraveParser()
    parser.feed(html)
    parser.close()
    return parser.results


async def _brave_web(client: httpx.AsyncClient, query: str, limit: int, key: str) -> List[Dict[str, str]]:
    try:
        r = await client.get(
            "https://search.brave.com/search",
            params={"q": query, "source": "web"},
            headers={"User-Agent": BROWSER_UA, "Accept-Language": "en-US,en;q=0.9"},
        )
    except httpx.HTTPError as e:
        raise SearchBackendError(f"Brave web search failed: {e.__class__.__name__}")
    if r.status_code != 200:
        raise SearchBackendError(f"Brave web search answered HTTP {r.status_code}")
    results = parse_brave_results(r.text)
    if not results:
        raise SearchBackendError("Brave web search returned no results we could read")
    return results[:limit]


# ---------------------------------------------------------------------------
# Keyed APIs
# ---------------------------------------------------------------------------

async def _brave(client: httpx.AsyncClient, query: str, limit: int, key: str) -> List[Dict[str, str]]:
    try:
        r = await client.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": str(limit)},
            headers={"X-Subscription-Token": key, "Accept": "application/json"},
        )
    except httpx.HTTPError as e:
        raise SearchBackendError(f"Brave request failed: {e.__class__.__name__}")
    if r.status_code != 200:
        raise SearchBackendError(f"Brave answered HTTP {r.status_code}")
    rows = ((r.json() or {}).get("web") or {}).get("results") or []
    return [
        {"title": x.get("title", ""), "url": x.get("url", ""), "snippet": x.get("description", "")}
        for x in rows if x.get("url")
    ][:limit]


async def _tavily(client: httpx.AsyncClient, query: str, limit: int, key: str) -> List[Dict[str, str]]:
    try:
        r = await client.post(
            "https://api.tavily.com/search",
            json={"query": query, "max_results": limit},
            headers={"Authorization": f"Bearer {key}"},
        )
    except httpx.HTTPError as e:
        raise SearchBackendError(f"Tavily request failed: {e.__class__.__name__}")
    if r.status_code != 200:
        raise SearchBackendError(f"Tavily answered HTTP {r.status_code}")
    rows = (r.json() or {}).get("results") or []
    return [
        {"title": x.get("title", ""), "url": x.get("url", ""), "snippet": x.get("content", "")}
        for x in rows if x.get("url")
    ][:limit]


async def _serper(client: httpx.AsyncClient, query: str, limit: int, key: str) -> List[Dict[str, str]]:
    try:
        r = await client.post(
            "https://google.serper.dev/search",
            json={"q": query, "num": limit},
            headers={"X-API-KEY": key},
        )
    except httpx.HTTPError as e:
        raise SearchBackendError(f"Serper request failed: {e.__class__.__name__}")
    if r.status_code != 200:
        raise SearchBackendError(f"Serper answered HTTP {r.status_code}")
    rows = (r.json() or {}).get("organic") or []
    return [
        {"title": x.get("title", ""), "url": x.get("link", ""), "snippet": x.get("snippet", "")}
        for x in rows if x.get("link")
    ][:limit]


BACKENDS = {
    "brave": ("Brave", _brave),
    "tavily": ("Tavily", _tavily),
    "serper": ("Serper", _serper),
    "duckduckgo": ("DuckDuckGo", _duckduckgo),
    "brave_web": ("Brave (web)", _brave_web),
    "bing": ("Bing", _bing),
}
KEYLESS_CHAIN = ["duckduckgo", "brave_web", "bing"]

_STOPWORDS = {
    "the", "and", "for", "what", "how", "does", "with", "from", "that", "this", "are", "you", "your", "who",
    "why", "when", "where", "which", "can", "latest", "new", "best", "about", "into", "have", "has", "was",
}


def backend_order(setting: Optional[str], key: Optional[str]) -> List[str]:
    """Backends to try, in order. A keyed backend without a key is skipped; the keyless chain is always last."""
    wanted = (setting or "auto").strip().lower()
    order: List[str] = []
    if wanted in KEYED_BACKENDS and (key or "").strip():
        order.append(wanted)
    return order + KEYLESS_CHAIN


def looks_relevant(query: str, results: List[Dict[str, str]]) -> bool:
    """False when the results have little to do with the query.

    Some engines answer a scraper with unrelated pages (Bing returned a bakery for a KaTeX
    query). A confident wrong answer is worse than none, so such a backend counts as failed.
    """
    tokens = [t for t in re.findall(r"[a-z0-9][a-z0-9.+#-]{2,}", query.lower()) if t not in _STOPWORDS]
    if not tokens or not results:
        return True
    scores = []
    for row in results:
        haystack = f"{row.get('title', '')} {row.get('snippet', '')} {row.get('url', '')}".lower()
        scores.append(sum(1 for t in tokens if t in haystack) / len(tokens))
    return max(scores) == 1.0 or sum(scores) / len(scores) >= 0.34


def active_backend(get_setting) -> Dict[str, Any]:
    """What the dashboard shows next to the Search toggle."""
    order = backend_order(get_setting("search_backend", "auto"), get_setting("search_api_key", ""))
    return {"name": BACKENDS[order[0]][0], "id": order[0], "keyed": order[0] in KEYED_BACKENDS}


class WebSearch(Tool):
    name = "web_search"
    description = "Search the web and return numbered results (title, URL, snippet)."
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "What to search for"},
            "max_results": {"type": "integer", "description": "1 to 8, default 5"},
        },
        "required": ["query"],
    }

    # Tests replace this to avoid the network.
    client_factory = staticmethod(lambda: httpx.AsyncClient(timeout=SEARCH_TIMEOUT, follow_redirects=True, trust_env=False))

    async def run(self, args: Dict[str, Any], ctx: ToolContext) -> ToolResult:
        query = args.get("query")
        if not isinstance(query, str) or not query.strip():
            raise ToolError('web_search needs a non-empty "query" string.')
        query = " ".join(query.split())[:MAX_QUERY_CHARS]
        limit = args.get("max_results", 5)
        limit = limit if isinstance(limit, int) and not isinstance(limit, bool) else 5
        limit = max(1, min(8, limit))

        key = ctx.get_setting("search_api_key", "") or ""
        order = backend_order(ctx.get_setting("search_backend", "auto"), key)
        notes: List[str] = []
        results: List[Dict[str, str]] = []
        used = ""
        from_cache = False
        cache_key = (query.lower(), limit, order[0])
        cached = _CACHE.get(cache_key)
        if cached and time.monotonic() - cached[0] < CACHE_TTL:
            from_cache = True
            _CACHE.move_to_end(cache_key)
            _, results, used = cached
            order = []
        async with self.client_factory() as client:
            for backend_id in order:
                label, fn = BACKENDS[backend_id]
                await _space_out(backend_id)
                try:
                    results = await fn(client, query, limit, key)
                except SearchBackendError as e:
                    log.warning("search backend %s failed: %s", backend_id, e)
                    notes.append(str(e))
                    continue
                except Exception as e:  # malformed JSON from an API, for example
                    log.warning("search backend %s crashed: %s", backend_id, e)
                    notes.append(f"{label} failed ({e.__class__.__name__})")
                    continue
                if results and not looks_relevant(query, results):
                    log.warning("search backend %s returned unrelated results for %r", backend_id, query)
                    notes.append(f"{label} returned results unrelated to the query")
                    results = []
                    continue
                if results:
                    used = label
                    break
        if not results:
            hint = "" if key else " (A search API key in Settings makes this reliable.)"
            raise ToolError("Search is unavailable right now: " + "; ".join(notes or ["no results"]) + "." + hint)
        _CACHE[cache_key] = (time.monotonic(), results, used)
        while len(_CACHE) > CACHE_MAX:
            _CACHE.popitem(last=False)

        lines = [f'Search results for "{query}" (via {used}):', ""]
        sources = []
        for row in results:
            src = ctx.add_source(row["title"], row["url"], row["snippet"])
            sources.append(src)
            lines.append(f"[{src['n']}] {src['title']} — {src['url']}")
            if src["snippet"]:
                lines.append(src["snippet"])
            lines.append("")
        if notes:
            lines.append("(Fallback used: " + "; ".join(notes) + ")")
        return ToolResult(
            text="\n".join(lines).strip(),
            summary=f"{len(sources)} result{'s' if len(sources) != 1 else ''}",
            sources=sources,
            meta={"backend": used, "query": query, "limit": limit, "tried": list(order), "cached": from_cache, "notes": notes},
        )


register(WebSearch())
