#!/usr/bin/env python3
"""
The JanitorAI userscript
========================
`build(base_url)` returns the finished userscript: the metadata header, the markdown parser and the HTML
sanitizer (both vendored in static/vendor/, wrapped so they stay private to the script), and the
script itself (static/userscript/eclipse-regex.src.js). One file, nothing loaded from outside, so a
userscript manager can install it from the gateway's own address:

    GET /userscripts/eclipse-regex.user.js
"""

import json
from pathlib import Path

STATIC = Path(__file__).resolve().parent / "static"
SOURCE = STATIC / "userscript" / "eclipse-regex.src.js"
MARKED = STATIC / "vendor" / "marked.umd.js"
PURIFY = STATIC / "vendor" / "purify.min.js"
SCRIPT_PATH = "/userscripts/eclipse-regex.user.js"
VERSION = "1.0.1"

MATCHES = ("*://janitorai.com/*", "*://*.janitorai.com/*", "*://janitor.ai/*", "*://*.janitor.ai/*")
CONNECTS = (
    "localhost", "127.0.0.1",
    "ngrok-free.app", "*.ngrok-free.app",
    "ngrok.app", "*.ngrok.app",
    "ngrok.io", "*.ngrok.io",
    "ngrok.dev", "*.ngrok.dev",
    "*"
)
GRANTS = ("GM_xmlhttpRequest", "GM_getValue", "GM_setValue", "GM_registerMenuCommand")


def header(base_url: str) -> str:
    url = f"{base_url.rstrip('/')}{SCRIPT_PATH}"
    lines = [
        "// ==UserScript==",
        "// @name         Eclipse: JanitorAI regex display",
        "// @namespace    eclipse",
        f"// @version      {VERSION}",
        "// @description  Restyles JanitorAI replies with the display regex scripts of your Eclipse preset.",
        *[f"// @match        {m}" for m in MATCHES],
        "// @run-at       document-idle",
        "// @noframes",
        *[f"// @grant        {g}" for g in GRANTS],
        *[f"// @connect      {c}" for c in CONNECTS],
        f"// @downloadURL  {url}",
        f"// @updateURL    {url}",
        "// ==/UserScript==",
    ]
    return "\n".join(lines) + "\n"


def _private(name: str, code: str) -> str:
    """A UMD library run in a function of its own, so it exports to a local variable and not to the page."""
    return (
        f"const {name} = (function () {{\n"
        "  const module = { exports: {} };\n  const exports = module.exports;\n  const define = undefined;\n"
        f"{code}\n  return module.exports;\n}})();\n"
    )


def build(base_url: str = "http://localhost:5000", ngrok_url: str = "") -> str:
    source = SOURCE.read_text(encoding="utf-8")
    marked = _private("marked", MARKED.read_text(encoding="utf-8"))
    purify = _private("DOMPurify", PURIFY.read_text(encoding="utf-8"))
    init_vars = (
        f"const SG_EMBEDDED_BASE = {json.dumps(base_url.rstrip('/'))};\n"
        f"const SG_EMBEDDED_NGROK = {json.dumps(ngrok_url.rstrip('/'))};\n"
    )
    return f"{header(base_url)}(function () {{\n'use strict';\n{init_vars}{marked}{purify}{source}\n}})();\n"

