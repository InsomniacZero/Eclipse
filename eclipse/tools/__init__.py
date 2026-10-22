#!/usr/bin/env python3
"""
Eclipse Chat Tools
======================
Registry for the tools a model can call during a chat (see loop.py). A tool is one
file that builds a `Tool` subclass and calls `register()`. Nothing in the loop or the
dashboard knows about a specific tool: the dashboard renders any tool from the events
the loop emits.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


class ToolError(Exception):
    """A failure the model should be told about (bad arguments, blocked URL, backend down)."""


@dataclass
class ToolResult:
    text: str                                   # what the model reads
    summary: str = ""                           # one short line for the dashboard
    sources: List[Dict[str, Any]] = field(default_factory=list)   # sources this call produced
    meta: Dict[str, Any] = field(default_factory=dict)            # e.g. {"backend": "Bing"}


@dataclass
class ToolContext:
    """State shared by every call in one reply."""
    get_setting: Callable[[str, Optional[str]], Optional[str]] = lambda key, default=None: default
    sources: List[Dict[str, Any]] = field(default_factory=list)

    def add_source(self, title: str, url: str, snippet: str = "") -> Dict[str, Any]:
        """Register a source and return it. The same URL keeps its number across calls."""
        for existing in self.sources:
            if existing["url"] == url:
                return existing
        source = {
            "n": len(self.sources) + 1,
            "title": (title or url).strip()[:200],
            "url": url,
            "snippet": (snippet or "").strip()[:300],
        }
        self.sources.append(source)
        return source


class Tool:
    name: str = ""
    description: str = ""
    parameters: Dict[str, Any] = {"type": "object", "properties": {}}

    async def run(self, args: Dict[str, Any], ctx: ToolContext) -> ToolResult:
        raise NotImplementedError


_REGISTRY: Dict[str, Tool] = {}


def register(tool: Tool) -> Tool:
    _REGISTRY[tool.name] = tool
    return tool


def get(name: str) -> Optional[Tool]:
    return _REGISTRY.get(name)


def all_tools() -> List[Tool]:
    return list(_REGISTRY.values())


def describe() -> List[Dict[str, Any]]:
    """Public description of every registered tool (for GET /api/tools)."""
    return [
        {"name": t.name, "description": t.description, "parameters": t.parameters}
        for t in _REGISTRY.values()
    ]


# Importing the modules registers their tools.
from . import web_search  # noqa: E402,F401
from . import fetch_url  # noqa: E402,F401
