"""Render the Homepage ConfigMaps from homepage/catalog.yaml. Run with no flags to write them."""
import argparse
import difflib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from catalog import CatalogError, load_catalog, slug, walk_groups  # noqa: E402
from render import PAGES, build_page, check_placeholders, dump_page, helm_escape  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
STAGED = {"household", "admin"}
COMMAND = "python3 scripts/homepage/generate.py"


def output_path(repo: Path, page: str) -> Path:
    rel = f"{PAGES[page]['dir']}/manifests/templates/configmap.yaml"
    return Path(repo) / ("homepage/staged/" + rel if page in STAGED else rel)


def render_all(repo: Path) -> dict[Path, str]:
    cat = load_catalog(repo)
    out = {}
    for page in PAGES:
        text = dump_page(page, build_page(repo, cat, page))
        check_placeholders(repo, page, text)
        out[output_path(repo, page)] = helm_escape(text)
    return out


def _widget_list(entry):
    return [entry["widget"]] if "widget" in entry else entry.get("widgets", [])


def _walk(items, group, tiles, bookmarks):
    for item in items:
        (name, val), = item.items()
        if isinstance(val, dict):
            ws = _widget_list(val)
            tiles.append({
                "id": val["id"], "name": name, "group": group, "href": val.get("href"),
                "widgets": [w["type"] for w in ws],
                "urls": [u for w in ws for u in [w.get("url")] + [i.get("url") for i in w.get("integrations", [])] if u],
                "highlight": [w.get("highlight") for w in ws],
                "refreshInterval": [w.get("refreshInterval") for w in ws],
            })
        elif val and isinstance(val[0], dict) and "id" in val[0]:
            bookmarks.append({"id": val[0]["id"], "name": name, "group": group, "href": val[0].get("href")})
        else:
            _walk(val, name, tiles, bookmarks)


def inventory(repo: Path) -> dict:
    cat = load_catalog(repo)
    out = {}
    for page in PAGES:
        data = build_page(repo, cat, page)
        pdata = cat["pages"][page]
        tiles, bookmarks = [], []
        for group in data["services.yaml"] + data["bookmarks.yaml"]:
            (name, items), = group.items()
            _walk(items, name, tiles, bookmarks)
        out[page] = {
            "tabs": [{"name": t["name"], "slug": slug(t["name"])} for t in pdata.get("tabs") or []],
            "groups": [{"name": g["name"], "tab": tab, "parents": parents} for tab, g, parents in walk_groups(pdata)],
            "tiles": tiles,
            "bookmarks": bookmarks,
            "info": [next(iter(e)) for e in data["widgets.yaml"]],
        }
    return out


def main(argv: list[str] | None = None, repo: Path = ROOT) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="fail if the committed output is stale")
    mode.add_argument("--inventory", action="store_true", help="print the pages' contents as JSON")
    mode.add_argument("--compare", action="store_true", help="compare staged pages with the live ones")
    args = parser.parse_args(argv)
    if args.compare:
        print("--compare: not implemented", file=sys.stderr)
        return 2
    try:
        if args.inventory:
            print(json.dumps(inventory(repo), indent=2, ensure_ascii=False))
            return 0
        rendered = render_all(repo)
    except CatalogError as err:
        print(err, file=sys.stderr)
        return 1
    stale = False
    for path, text in rendered.items():
        rel = path.relative_to(repo)
        if args.check:
            old = path.read_text(encoding="utf-8") if path.is_file() else ""
            if old.encode() == text.encode() and path.is_file():
                continue
            stale = True
            diff = list(difflib.unified_diff(old.splitlines(), text.splitlines(), f"a/{rel}", f"b/{rel}", lineterm=""))
            print(f"{rel}: out of date", *diff[:40], *(["..."] if len(diff) > 40 else []), sep="\n")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(text.encode())
            print(rel)
    if stale:
        print(f"run: {COMMAND}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
