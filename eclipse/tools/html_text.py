#!/usr/bin/env python3
"""Reduce an HTML page to readable text for a model (standard library only)."""

import re
from html.parser import HTMLParser
from typing import List, Tuple
from urllib.parse import urljoin

_SKIP = {"script", "style", "noscript", "svg", "template", "iframe", "canvas", "nav", "footer", "aside", "form", "head"}
_VOID = {"br", "hr", "img", "input", "meta", "link", "source", "track", "wbr", "area", "base", "col", "embed", "param"}
_BLOCK = {
    "p", "div", "section", "article", "main", "ul", "ol", "li", "tr", "table", "blockquote",
    "h1", "h2", "h3", "h4", "h5", "h6", "pre", "figure", "figcaption", "dl", "dt", "dd", "header",
}
MAX_LINKS = 40
_NO_CLOSE_BREAK = {"li", "tr", "dt", "dd"}  # their start tag already begins a new line
NBSP = "\u00a0"


class _Extractor(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.title = ""
        self.parts: List[str] = []
        self._skip = 0
        self._in_title = False
        self._pre = 0
        self._href: List[str] = []        # stack of open links
        self._link_text: List[List[str]] = []
        self._links = 0

    def _emit(self, text: str) -> None:
        if self._link_text:
            self._link_text[-1].append(text)
        self.parts.append(text)

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self._in_title = True
            return
        if tag == "body":
            self._skip = 0  # a <head> that was never closed must not hide the page
        if tag in _SKIP:
            if tag not in _VOID:
                self._skip += 1
            return
        if self._skip:
            return
        if tag == "br":
            self.parts.append("\n")
        elif tag in _BLOCK:
            self.parts.append("\n")
            if tag.startswith("h") and len(tag) == 2 and tag[1].isdigit():
                self.parts.append("#" * int(tag[1]) + " ")
            elif tag == "li":
                self.parts.append("- ")
        if tag == "pre":
            self._pre += 1
        if tag == "a":
            href = dict(attrs).get("href") or ""
            self._href.append(href)
            self._link_text.append([])

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
            return
        if tag in _SKIP:
            if self._skip:
                self._skip -= 1
            return
        if self._skip:
            return
        if tag == "a" and self._href:
            href = self._href.pop()
            label = "".join(self._link_text.pop()).strip()
            if href and label and self._links < MAX_LINKS and not href.startswith(("#", "javascript:", "mailto:", "tel:")):
                url = urljoin(self.base_url, href)
                if url.startswith(("http://", "https://")):
                    self.parts.append(f" ({url})")
                    self._links += 1
        elif tag in _BLOCK and tag not in _NO_CLOSE_BREAK:
            self.parts.append("\n")
        if tag == "pre" and self._pre:
            self._pre -= 1

    def handle_data(self, data):
        if self._in_title:
            self.title += data
            return
        if self._skip:
            return
        if self._pre:
            # Indentation inside <pre> is kept: leading spaces become NBSP until the final cleanup.
            self._emit(re.sub(r"(?m)^ +", lambda m: NBSP * len(m.group(0)), data))
        else:
            self._emit(re.sub(r"\s+", " ", data))


def html_to_text(html: str, base_url: str = "") -> Tuple[str, str]:
    """Return (title, text)."""
    parser = _Extractor(base_url)
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        pass  # keep whatever was extracted before the parser gave up
    text = "".join(parser.parts)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return re.sub(r"\s+", " ", parser.title).strip(), text.strip().replace(NBSP, " ")
