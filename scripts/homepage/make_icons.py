#!/usr/bin/env python3
"""Render each page's mark as the PNG icons phones need; run from the repo root after favicon.svg changes.

iOS takes no SVG for a tab icon or a home-screen icon, and falls back to Homepage's own. Phones also round the
corners themselves and paint transparency black, so the PNG is the mark on a full square of its background:
the rounded tile and its rim are left out. Needs Playwright (scripts/homepage/rendercheck/requirements.txt);
set HP_CHROME to a Chromium binary if Playwright has none of its own.
"""

import os
import re
import sys
from pathlib import Path

SIZE = 192  # a phone home-screen icon is 180 px; one file keeps the ConfigMap small
PAGES = ("household", "admin")


def full_bleed(svg: str) -> str:
    """The mark's SVG with its rounded tile widened to the whole square and its rim removed."""
    tile = re.search(r'<rect x="1" y="1" width="46" height="46" rx="14" fill="url\(#sq\)"/>', svg)
    rim = re.search(r'<rect x="1\.5" y="1\.5" width="45" height="45" rx="13\.5" fill="none" stroke="url\(#rim\)"/>', svg)
    if not tile or not rim:
        raise SystemExit("favicon.svg no longer has the tile and rim this script rewrites: update make_icons.py")
    svg = svg.replace(rim.group(0), "")
    return svg.replace(tile.group(0), '<rect width="48" height="48" fill="url(#sq)"/>')


def main(repo: Path) -> int:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.environ.get("HP_CHROME") or None)
        for page_name in PAGES:
            files = repo / "homepage/pages" / page_name / "files"
            svg = full_bleed((files / "favicon.svg").read_text(encoding="utf-8"))
            for size in (SIZE,):
                page = browser.new_page(viewport={"width": size, "height": size})
                page.set_content(f'<body style="margin:0">{svg}</body>')
                page.eval_on_selector("svg", f"e => {{ e.setAttribute('width', {size}); e.setAttribute('height', {size}); }}")
                out = files / f"icon-{size}.png"
                page.locator("svg").screenshot(path=str(out))
                page.close()
                print(out.relative_to(repo))
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()))
