#!/usr/bin/env python3
"""
fetch_url tool: read one web page as plain text.

The model chooses the URL, and the page text is untrusted, so the fetch is locked down:
  - http and https only, no credentials in the URL;
  - every address the host resolves to must be public (no loopback, private, link-local,
    carrier-grade NAT, cloud metadata or reserved ranges, and no IPv4 hidden in IPv6);
  - the connection goes to the address that was checked (the hostname is sent as Host and
    TLS server name), so a second DNS answer cannot redirect it;
  - redirects are followed by hand, at most 4, and each hop is checked again;
  - no cookies, no proxy settings from the environment;
  - 15 s timeout, 6 MB body (some news sites put 3 MB of script before the text), HTML / text / JSON only.
"""

import asyncio
import ipaddress
import re
import socket
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional
from urllib.parse import urljoin, urlsplit

import httpx

from . import Tool, ToolContext, ToolError, ToolResult, register
from .html_text import html_to_text

FETCH_TIMEOUT = 15.0
MAX_BYTES = 6_000_000
MAX_REDIRECTS = 4
DEFAULT_CHARS = 8000
MIN_CHARS, MAX_CHARS = 500, 20000

BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

_NAT64 = ipaddress.ip_network("64:ff9b::/96")
_TEXT_TYPES = re.compile(r"^(text/|application/(json|xml|xhtml\+xml|ld\+json|rss\+xml|atom\+xml)|[\w.+-]+/[\w.+-]*\+(json|xml))", re.I)

Resolver = Callable[[str, int], Awaitable[List[str]]]


def is_public_ip(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return False
    if ip.version == 6:
        if ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        elif ip in _NAT64:
            ip = ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
        elif ip.sixtofour:
            ip = ip.sixtofour
    return ip.is_global and not ip.is_multicast


async def default_resolver(host: str, port: int) -> List[str]:
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise ToolError(f"Could not resolve the host name {host!r}.")
    addresses: List[str] = []
    for info in infos:
        addr = info[4][0].split("%")[0]
        if addr not in addresses:
            addresses.append(addr)
    return addresses


@dataclass
class FetchedPage:
    url: str
    status: int
    content_type: str
    body: bytes
    truncated: bool


def _normalize(url: str) -> str:
    url = (url or "").strip()
    if not url:
        raise ToolError('fetch_url needs a "url".')
    if "://" not in url:
        url = "https://" + url
    return url


async def _check_target(url: str, resolver: Resolver):
    """Validate a URL and return (scheme, host, port, pinned_ip, host_header)."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise ToolError("Only http and https URLs can be fetched.")
    if not parts.hostname:
        raise ToolError("The URL has no host name.")
    if parts.username or parts.password:
        raise ToolError("URLs with a user name or password are not allowed.")
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError:
        raise ToolError("The URL has an invalid port.")
    host = parts.hostname
    try:
        ipaddress.ip_address(host)
        addresses = [host]
    except ValueError:
        addresses = await resolver(host, port)
    if not addresses:
        raise ToolError(f"Could not resolve the host name {host!r}.")
    blocked = [a for a in addresses if not is_public_ip(a)]
    if blocked:
        raise ToolError("That address is not on the public internet, so it is blocked.")
    default_port = 443 if parts.scheme == "https" else 80
    host_header = host if port == default_port else f"{host}:{port}"
    if ":" in host and not host_header.startswith("["):
        host_header = f"[{host}]" + (f":{port}" if port != default_port else "")
    return parts.scheme, host, port, addresses[0], host_header


async def safe_fetch(
    url: str,
    *,
    max_bytes: int = MAX_BYTES,
    timeout: float = FETCH_TIMEOUT,
    resolver: Optional[Resolver] = None,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> FetchedPage:
    resolver = resolver or default_resolver
    current = _normalize(url)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, trust_env=False, transport=transport) as client:
        for _ in range(MAX_REDIRECTS + 1):
            scheme, host, port, ip, host_header = await _check_target(current, resolver)
            parts = urlsplit(current)
            ip_netloc = f"[{ip}]" if ":" in ip else ip
            pinned = f"{scheme}://{ip_netloc}:{port}{parts.path or '/'}" + (f"?{parts.query}" if parts.query else "")
            headers = {
                "Host": host_header,
                "User-Agent": BROWSER_UA,
                "Accept": "text/html,application/xhtml+xml,text/plain,application/json;q=0.9,*/*;q=0.5",
                "Accept-Language": "en-US,en;q=0.9",
            }
            extensions = {"sni_hostname": host} if scheme == "https" else {}
            try:
                async with client.stream("GET", pinned, headers=headers, extensions=extensions) as resp:
                    if resp.status_code in (301, 302, 303, 307, 308) and resp.headers.get("location"):
                        current = urljoin(current, resp.headers["location"])
                        continue
                    content_type = resp.headers.get("content-type", "").split(";")[0].strip().lower()
                    chunks: List[bytes] = []
                    size = 0
                    truncated = False
                    if resp.status_code < 400 and content_type and not _TEXT_TYPES.match(content_type):
                        raise ToolError(f"Unsupported content type {content_type!r} (only HTML, text and JSON can be read).")
                    async for chunk in resp.aiter_bytes():
                        size += len(chunk)
                        if size > max_bytes:
                            chunks.append(chunk[: len(chunk) - (size - max_bytes)])
                            truncated = True
                            break
                        chunks.append(chunk)
                    return FetchedPage(
                        url=current,
                        status=resp.status_code,
                        content_type=content_type,
                        body=b"".join(chunks),
                        truncated=truncated,
                    )
            except httpx.TimeoutException:
                raise ToolError(f"The page did not answer within {timeout:.0f} seconds.")
            except httpx.HTTPError as e:
                raise ToolError(f"The request failed ({e.__class__.__name__}).")
    raise ToolError(f"Too many redirects (more than {MAX_REDIRECTS}).")


def _decode(body: bytes, content_type_header: str = "") -> str:
    head = body[:2048].decode("ascii", errors="ignore")
    m = re.search(r"charset=([\w-]+)", content_type_header or "", re.I) or re.search(r'<meta[^>]+charset=["\']?([\w-]+)', head, re.I)
    for enc in ([m.group(1)] if m else []) + ["utf-8"]:
        try:
            return body.decode(enc, errors="replace")
        except LookupError:
            continue
    return body.decode("utf-8", errors="replace")


class FetchUrl(Tool):
    name = "fetch_url"
    description = "Open a web page and read its text. Use a URL from a search result."
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "The page address (http or https)"},
            "max_chars": {"type": "integer", "description": "How much text to return, 500 to 20000, default 8000"},
        },
        "required": ["url"],
    }

    # Tests replace these to avoid the network.
    resolver: Optional[Resolver] = None
    transport: Optional[httpx.AsyncBaseTransport] = None

    async def run(self, args: Dict[str, Any], ctx: ToolContext) -> ToolResult:
        url = args.get("url")
        if not isinstance(url, str):
            raise ToolError('fetch_url needs a "url" string.')
        limit = args.get("max_chars", DEFAULT_CHARS)
        limit = limit if isinstance(limit, int) and not isinstance(limit, bool) else DEFAULT_CHARS
        limit = max(MIN_CHARS, min(MAX_CHARS, limit))

        page = await safe_fetch(url, resolver=self.resolver, transport=self.transport)
        if page.status >= 400:
            raise ToolError(f"The page answered HTTP {page.status}.")
        raw = _decode(page.body)
        if page.content_type in ("text/html", "application/xhtml+xml", "") and "<" in raw[:2000]:
            title, text = html_to_text(raw, page.url)
        else:
            title, text = "", raw.strip()
        if not text:
            if page.truncated:
                raise ToolError("The page is too large to read.")
            raise ToolError("The page has no readable text (it may need JavaScript).")

        shown = text[:limit]
        cut = len(text) > limit or page.truncated
        host = urlsplit(page.url).hostname or page.url
        src = ctx.add_source(title or host, page.url, text[:200].replace("\n", " "))
        header = f"[{src['n']}] {src['title']} — {page.url}"
        body = shown + ("\n\n[Text cut here. Ask for a larger max_chars, or fetch a more specific page.]" if cut else "")
        return ToolResult(
            text=f"{header}\n\n{body}",
            summary=f"{len(shown):,} characters" + (" (cut)" if cut else ""),
            sources=[src],
            meta={"host": host},
        )


register(FetchUrl())
