#!/usr/bin/env python3
"""Verify that every local image reference in tracked Markdown files resolves.

GitHub resolves relative image paths against the *directory of the Markdown file*
that contains them. A diagram committed at repo-root ``docs/diagrams/x.png`` but
referenced from ``profile/README.md`` as ``docs/diagrams/x.png`` therefore resolves
to ``profile/docs/diagrams/x.png`` and 404s on the rendered page.

This check mirrors that resolution: for each tracked Markdown file it collects the
local (non-URL) image paths from HTML ``src``/``srcset`` attributes and Markdown
``![alt](path)`` syntax, resolves them relative to the file's directory, and fails
if any target is missing. Run with no arguments from the repository root.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from urllib.parse import unquote, urlparse

ATTR_RE = re.compile(r'(?:src|srcset)\s*=\s*"([^"]+)"')
MD_IMG_RE = re.compile(r'!\[[^\]]*\]\(\s*<?([^)\s>]+)')


def tracked_markdown() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "*.md", "*.markdown"],
        capture_output=True, text=True, check=True,
    ).stdout
    return [line for line in out.splitlines() if line]


def candidate_paths(text: str) -> list[str]:
    paths: list[str] = []
    for match in ATTR_RE.finditer(text):
        # srcset may hold a comma-separated "url size, url size" list.
        for part in match.group(1).split(","):
            tokens = part.split()
            if tokens:
                paths.append(tokens[0])
    paths.extend(match.group(1) for match in MD_IMG_RE.finditer(text))
    return paths


def is_local(url: str) -> bool:
    if not url or url[0] in "#?":
        return False
    if url.startswith(("data:", "mailto:", "//")):
        return False
    parsed = urlparse(url)
    return parsed.scheme == "" and parsed.netloc == ""


def main() -> int:
    broken: list[tuple[str, str, str]] = []
    for md in tracked_markdown():
        base = os.path.dirname(md)
        with open(md, encoding="utf-8") as handle:
            text = handle.read()
        for url in candidate_paths(text):
            if not is_local(url):
                continue
            clean = unquote(url.split("#", 1)[0].split("?", 1)[0])
            if not clean:
                continue
            resolved = os.path.normpath(os.path.join(base, clean))
            if not os.path.isfile(resolved):
                broken.append((md, url, resolved))

    if broken:
        print("ERROR: broken local image references found:")
        for md, url, resolved in broken:
            print(f"  {md}: '{url}' -> '{resolved}' (missing)")
        return 1

    print("OK: all local image references resolve.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
