#!/usr/bin/env python3
"""
Eclipse Universal Artifacts Engine
======================================
Protocol definitions, instruction injectors, and parsers for Eclipse
interactive Artifacts (<antArtifact>) across all supported AI models
(Gemini, Claude, DeepSeek, Kimi, Qwen, GLM, Antigravity, MiMo).
"""

import json
import re
from typing import Any, Dict, List, Optional

# Universal non-adversarial instructions teaching any model how to generate artifacts
ARTIFACTS_SYSTEM_PROMPT = """<artifacts_info>
The assistant can create and reference artifacts during conversations. Artifacts are for substantial, self-contained content that users might modify or reuse, displayed in a dedicated side-by-side workspace window for clarity.

# Good artifacts are:
- Substantial content (>15 lines)
- Content that the user is likely to modify, iterate on, or take ownership of
- Self-contained, complex content that can be understood on its own, without context from the conversation
- Interactive applications, React components, full HTML/CSS/JS websites, Mermaid diagrams, SVG art, or long documents

# Usage guidelines:
1. Immediately before creating an artifact, if appropriate, you can reflect briefly on whether the content is artifact-worthy in <antThinking> tags.
2. Wrap the content in opening and closing `<antArtifact>` tags.
3. Assign a descriptive `identifier` attribute using kebab-case (e.g., `identifier="mortgage-calculator"`).
   - CRITICAL: If modifying, improving, or updating an existing artifact, ALWAYS REUSE the prior `identifier` to maintain continuity and create a new version.
4. Include a human-readable `title` attribute (e.g., `title="Interactive Mortgage Calculator"`).
5. Add a `type` attribute specifying the format:
   - "application/vnd.ant.react": Use for interactive React components. Use Tailwind CSS utility classes for styling. Use default export (`export default function App()`). Components have access to React hooks, `lucide-react` icons, and `recharts`.
   - "text/html": Use for single-file HTML/CSS/JS web applications.
   - "image/svg+xml": Use for Scalable Vector Graphics. Specify viewBox attribute.
   - "application/vnd.ant.mermaid": Use for Mermaid flowcharts and diagrams. Do not wrap in markdown backticks inside the artifact.
   - "text/markdown": Use for standalone structured documents, reports, or guides.
   - "application/vnd.ant.code": Use for standalone code scripts in any programming language (include `language="..."` attribute).
6. Provide the complete and updated code/content inside the artifact tags without any truncation, placeholders, or "// rest of code remains the same".
7. Do not include raw `<antArtifact>` tags in normal conversation when just explaining concepts or answering simple questions.
</artifacts_info>"""


def inject_artifacts_prompt(messages: List[Dict[str, Any]], enabled: bool = True) -> List[Dict[str, Any]]:
    """
    Inject clean Artifacts guidelines into messages list if enabled and not already present.
    Works universally across all models without triggering safety or deception filters.
    """
    if not enabled or not messages:
        return messages

    new_msgs = [dict(m) for m in messages]
    
    # Check if artifacts instructions are already present in any system/developer message
    for i, m in enumerate(new_msgs):
        if m.get("role") in ("system", "developer"):
            content = m.get("content", "")
            if isinstance(content, str):
                if "<artifacts_info>" in content:
                    return new_msgs  # Already present
                # Prepend to existing system prompt
                new_msgs[i] = {
                    **m,
                    "content": f"{content}\n\n{ARTIFACTS_SYSTEM_PROMPT}".strip(),
                }
                return new_msgs

    # Otherwise prepend system message at the head
    return [{"role": "system", "content": ARTIFACTS_SYSTEM_PROMPT}] + new_msgs


def convert_genui_to_artifact(text: str) -> str:
    """
    Convert legacy GenUI app_block tags (※genui※{...}※) into standard
    Eclipse Artifact tags (<antArtifact ...>...</antArtifact>).
    """
    if not text or "※genui※" not in text:
        return text

    pattern = re.compile(r"※genui※(\{.*?)(?:※|$)", re.DOTALL)

    def replacer(m):
        raw_json = m.group(1).strip()
        data = None
        for suffix in ["", "}}", "\"}}", "\"]}}"]:
            try:
                data = json.loads(raw_json + suffix)
                break
            except Exception:
                pass

        if data:
            block = data.get("app_block") or data
            title = block.get("title") or "Interactive Application"
            content = block.get("content") or ""
        else:
            title_m = re.search(r"\"title\"\s*:\s*\"([^\"]+)\"", raw_json)
            title = title_m.group(1) if title_m else "Interactive Application"
            content_m = re.search(r"\"content\"\s*:\s*\"((?:[^\"\\]|\\.)*)", raw_json)
            if content_m:
                raw_c = content_m.group(1)
                try:
                    content = json.loads("\"" + raw_c + ("\"" if not raw_c.endswith("\"") else ""))
                except Exception:
                    content = raw_c.replace("\\n", "\n").replace("\\t", "\t").replace('\\"', '"').replace("\\\\", "\\")
            else:
                return m.group(0)

        identifier = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "genui-app"
        artifact_type = "text/html"
        if "export default" in content or "import React" in content:
            artifact_type = "application/vnd.ant.react"

        return (
            f"\n\n<antArtifact identifier=\"{identifier}\" type=\"{artifact_type}\" title=\"{title}\">\n"
            f"{content}\n"
            f"</antArtifact>\n"
        )

    return pattern.sub(replacer, text)


def extract_artifacts(text: str) -> List[Dict[str, Any]]:
    """
    Extract all <antArtifact ...>...</antArtifact> blocks from a completed text.
    Returns list of dicts with identifier, type, title, language, content.
    """
    text = convert_genui_to_artifact(text)
    pattern = re.compile(
        r'<antArtifact\s+([^>]+)>(.*?)</antArtifact>',
        re.DOTALL | re.IGNORECASE
    )
    attr_pattern = re.compile(r'([a-zA-Z0-9_\-]+)=["\']([^"\']+)["\']')

    results = []
    for match in pattern.finditer(text):
        raw_attrs = match.group(1)
        content = match.group(2)
        
        attrs = dict(attr_pattern.findall(raw_attrs))
        results.append({
            "identifier": attrs.get("identifier", "artifact"),
            "type": attrs.get("type", "text/markdown"),
            "title": attrs.get("title", "Artifact"),
            "language": attrs.get("language", ""),
            "content": content.strip(),
        })

    return results
