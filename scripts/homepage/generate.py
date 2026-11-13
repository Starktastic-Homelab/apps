"""Render the Homepage ConfigMaps from homepage/catalog.yaml. Run with no flags to write them."""
import argparse
import difflib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compare  # noqa: E402
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


def _widget(w):
    urls = [w.get("url")] + [i.get("url") for i in w.get("integrations", [])]
    return {"type": w["type"], "urls": [u for u in urls if u],
            "highlight": w.get("highlight"), "refreshInterval": w.get("refreshInterval")}


def _tiles(items, group, out):
    for item in items:
        (name, val), = item.items()
        if isinstance(val, dict):
            ws = [val["widget"]] if "widget" in val else val.get("widgets", [])
            out.append({"id": val["id"], "name": name, "group": group, "href": val.get("href"),
                        "widgets": [_widget(w) for w in ws]})
        else:
            _tiles(val, name, out)


def inventory(repo: Path) -> dict:
    cat = load_catalog(repo)
    out = {}
    for page in PAGES:
        data = build_page(repo, cat, page)
        pdata = cat["pages"][page]
        tiles = []
        for group in data["services.yaml"]:
            (name, items), = group.items()
            _tiles(items, name, tiles)
        # Bookmark groups are flat (nested ones are rejected by build_page).
        bookmarks = [{"id": b[0]["id"], "name": bname, "group": gname, "href": b[0].get("href")}
                     for group in data["bookmarks.yaml"] for gname, items in group.items()
                     for item in items for bname, b in item.items()]
        out[page] = {
            "tabs": [{"name": t["name"], "slug": slug(t["name"])} for t in pdata.get("tabs") or []],
            "groups": [{"name": g["name"], "tab": tab, "parents": parents} for tab, g, parents in walk_groups(pdata)],
            "tiles": tiles,
            "bookmarks": bookmarks,
            "info": [next(iter(e)) for e in data["widgets.yaml"]],
        }
    return out


def run_compare(repo: Path) -> int:
    if not STAGED:
        print("nothing staged")
        return 0
    lines = []
    for page in sorted(STAGED):
        paths = [Path(repo) / f"{PAGES[page]['dir']}/manifests/templates/configmap.yaml", output_path(repo, page)]
        missing = [p for p in paths if not p.is_file()]
        if missing:
            lines += [f"{page}: missing {p.relative_to(repo)}" for p in missing]
            continue
        try:
            texts = [p.read_text(encoding="utf-8") for p in paths]
            parsed = [compare.parse_configmap(t) for t in texts]
            f = [compare.facts(d) for d in parsed]
            lines += compare.diff(f[0], f[1], page)
            lines += compare.strict_diff(*parsed, *[compare.raw_keys(t) for t in texts], page)
        except CatalogError as err:
            lines.append(f"{page}: {err}")
    if lines:
        print(*lines, sep="\n")
    return 1 if lines else 0


def main(argv: list[str] | None = None, repo: Path = ROOT) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="fail if the committed output is stale")
    mode.add_argument("--inventory", action="store_true", help="print the pages' contents as JSON")
    mode.add_argument("--compare", action="store_true", help="compare staged pages with the live ones")
    args = parser.parse_args(argv)
    if args.compare:
        return run_compare(repo)
    try:
        if args.inventory:
            print(json.dumps(inventory(repo), indent=2, ensure_ascii=False))
            return 0
        rendered = render_all(repo)
    except CatalogError as err:
        print(err, file=sys.stderr)
        return 1
    stale = False
    if args.check:
        staged_dir = Path(repo) / "homepage/staged"
        wanted = {p for p in rendered if p.is_relative_to(staged_dir)}
        for orphan in sorted(set(staged_dir.rglob("*.yaml")) - wanted) if staged_dir.is_dir() else []:
            stale = True
            print(f"{orphan.relative_to(repo)}: orphan staged file (page not in STAGED); delete it")
    for path, text in rendered.items():
        rel = path.relative_to(repo)
        if args.check:
            old = path.read_text(encoding="utf-8") if path.is_file() else ""
            if path.is_file() and old.encode() == text.encode():
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
