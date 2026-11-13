"""Homepage catalog loader and generator helpers."""
import re
import urllib.parse
from pathlib import Path
from typing import Any

import yaml


class CatalogError(Exception):
    pass


class UniqueLoader(yaml.SafeLoader):
    """SafeLoader that rejects duplicate keys (as js-yaml does) and unquoted yes/no/on/off."""

    def compose_node(self, parent, index):
        node = super().compose_node(parent, index)
        if (isinstance(node, yaml.ScalarNode) and node.style is None
                and node.tag == "tag:yaml.org,2002:bool"
                and node.value.lower() in ("yes", "no", "on", "off")):
            raise yaml.composer.ComposerError(
                None, None,
                f"unquoted {node.value!r} is a boolean in YAML 1.1; quote it or use true/false",
                node.start_mark,
            )
        return node

    def compose_mapping_node(self, anchor):
        node = super().compose_mapping_node(anchor)
        seen = set()
        # Checked before `<<` merges are expanded, so a key may still override a merged one.
        for key, _ in node.value:
            if not isinstance(key, yaml.ScalarNode) or key.tag == "tag:yaml.org,2002:merge":
                continue
            if key.value in seen:
                raise yaml.composer.ComposerError(
                    "while composing a mapping", node.start_mark,
                    f"found duplicate key {key.value!r}", key.start_mark,
                )
            seen.add(key.value)
        return node


def loads_yaml(text: str, where: str) -> Any:
    try:
        return yaml.load(text, Loader=UniqueLoader)
    except yaml.YAMLError as err:
        raise CatalogError(f"{where}: {err}") from err


def load_yaml(path: Path) -> Any:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as err:
        raise CatalogError(f"{path}: {err}") from err
    data = loads_yaml(text, str(path))
    return {} if data is None else data


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def _mapping(data, path) -> dict:
    if not isinstance(data, dict):
        raise CatalogError(f"{path}: not a mapping")
    return data


def derive(repo: Path, source: str) -> dict:
    """Mirror cluster-apps.yaml + ingress-chart: href, siteMonitor (no monitorPath), namespace, app."""
    path = Path(repo) / source / "app.yaml"
    if not path.is_file():
        raise CatalogError(f"{source}: no app.yaml")
    own = _mapping(load_yaml(path), path)
    # The AppSet gates the ingress chart on the variant's own app.yaml, before any baseApp merge.
    if not (isinstance(own.get("ingress"), dict) and own["ingress"].get("enabled")):
        raise CatalogError(f"{source}: ingress is not enabled in its own app.yaml")
    app = own
    if own.get("baseApp"):
        base = Path(repo) / own["baseApp"] / "app.yaml"
        app = _merge(_mapping(load_yaml(base), base), own)
    ing = app["ingress"]
    for key in ("name", "namespace"):
        if not app.get(key):
            raise CatalogError(f"{source}: app.yaml has no {key}")
    gpath = Path(repo) / "templates/globals.yaml"
    domains = (_mapping(load_yaml(gpath), gpath).get("global") or {}).get("domains")
    if not isinstance(domains, dict):
        raise CatalogError(f"{gpath}: no global.domains")
    dtype = ing.get("domainType") or "internal"
    if dtype not in domains:
        raise CatalogError(f"{source}: unknown ingress.domainType {dtype!r}")
    domain = domains[dtype]
    host = ing.get("host") or ""
    svc = ing.get("serviceName") or app["name"]
    return {
        "href": f"https://{domain if not host else f'{host}.{domain}'}",
        "siteMonitor": f"http://{svc}.{app['namespace']}:{ing.get('port') or 80}",
        "namespace": app["namespace"],
        "app": app["name"],
    }


def resolve_tile(repo: Path, tid: str, tile: dict) -> dict:
    """Apply derived keys: explicit wins, an explicit value equal to the derived one is an error, null drops."""
    out = dict(tile)
    if "source" not in tile:
        return out
    try:
        derived = derive(repo, tile["source"])
    except CatalogError as err:
        raise CatalogError(f"tiles.{tid}.source: {err}") from err
    for key, val in derived.items():
        if key not in tile:
            out[key] = val
        elif tile[key] is None:
            del out[key]
        elif tile[key] == val:
            raise CatalogError(f"tiles.{tid}.{key}: equals the value derived from source; remove it")
    if "monitorPath" in tile and "siteMonitor" in out and "siteMonitor" not in tile:
        out["siteMonitor"] += tile["monitorPath"]
    return out


PAGE_NAMES = ("household", "admin")
TILE_EMIT = ("name", "href", "icon", "description", "siteMonitor", "namespace", "app", "podSelector",
             "proxmoxNode", "proxmoxVMID")
TILE_KEYS = set(TILE_EMIT) | {"audience", "source", "monitorPath", "override", "widgets"}
BOOKMARK_KEYS = {"name", "abbr", "href", "icon", "description", "target", "audience"}
GROUP_KEYS = {"name", "items", "style", "columns", "icon", "header", "initiallyCollapsed", "useEqualHeights"}
AUDIENCES = ("household", "admin", "household-only")


def audience(entry: dict) -> str:
    return entry.get("audience", "admin")


def shown_on(aud: str, page: str) -> bool:
    return aud == "household" or aud == page or (aud == "household-only" and page == "household")


def slug(tab: str) -> str:
    return urllib.parse.quote(re.sub(r"\s+", "-", tab).lower(), safe="")


def page_tile(tile: dict, page: str) -> dict:
    out = dict(tile)
    for key, val in (tile.get("override") or {}).get(page, {}).items():
        if val is None:
            out.pop(key, None)
        else:
            out[key] = val
    return out


def walk_groups(page: dict):
    def rec(tab, group, parents):
        yield tab, group, parents
        for item in group.get("items", []):
            if isinstance(item, dict):
                yield from rec(tab, item, parents + [group.get("name")])
    for tab in page.get("tabs", []):
        for group in tab.get("groups", []):
            yield from rec(tab.get("name"), group, [])


def _list(val, path) -> list:
    if val is None:
        return []
    if not isinstance(val, list):
        raise CatalogError(f"{path}: not a list")
    return val


def _check_keys(path, entry, allowed):
    if not isinstance(entry, dict):
        raise CatalogError(f"{path}: not a mapping")
    for key in entry:
        if key not in allowed:
            raise CatalogError(f"{path}.{key}: unknown key")


def _check_aud(path, entry, allowed):
    if "audience" in entry and entry["audience"] not in allowed:
        raise CatalogError(f"{path}.audience: {entry['audience']!r} is not one of {', '.join(allowed)}")


def _check_tile(tid, tile):
    path = f"tiles.{tid}"
    _check_keys(path, tile, TILE_KEYS)
    _check_aud(path, tile, AUDIENCES[:2])
    over = tile.get("override") or {}
    _check_keys(f"{path}.override", over, PAGE_NAMES)
    for page, ov in over.items():
        _check_keys(f"{path}.override.{page}", ov, TILE_EMIT)
    widgets = tile.get("widgets") or []
    if not isinstance(widgets, list):
        raise CatalogError(f"{path}.widgets: not a list")
    for i, w in enumerate(widgets):
        _mapping(w, f"{path}.widgets[{i}]")
        if not w.get("type"):
            raise CatalogError(f"{path}.widgets[{i}]: widget has no type")
        _check_aud(f"{path}.widgets[{i}]", w, AUDIENCES)


def load_catalog(repo: Path) -> dict:
    cpath = Path(repo) / "homepage/catalog.yaml"
    raw = _mapping(load_yaml(cpath), cpath)
    tiles = {tid: _mapping(t, f"tiles.{tid}") for tid, t in _mapping({} if raw.get("tiles") is None else raw["tiles"], "tiles").items()}
    for tid, t in tiles.items():
        _check_tile(tid, t)
    tiles = {tid: resolve_tile(repo, tid, t) for tid, t in tiles.items()}
    bookmarks = _mapping({} if raw.get("bookmarks") is None else raw["bookmarks"], "bookmarks")
    for bid, b in bookmarks.items():
        _check_keys(f"bookmarks.{bid}", b, BOOKMARK_KEYS)
        _check_aud(f"bookmarks.{bid}", b, AUDIENCES)
        if bid in tiles:
            raise CatalogError(f"bookmarks.{bid}: id is also a tile id")
    info = _list(raw.get("info"), "info")
    for i, e in enumerate(info):
        _mapping(e, f"info[{i}]")
        _check_aud(f"info[{i}]", e, AUDIENCES)
        if len(set(e) - {"audience"}) != 1:
            raise CatalogError(f"info[{i}]: needs exactly one widget key besides audience")
    pages = raw.get("pages") or {}
    _check_keys("pages", pages, PAGE_NAMES)
    cat = {"tiles": tiles, "bookmarks": bookmarks, "info": info, "pages": pages}
    for page in PAGE_NAMES:
        _check_page(cat, page)
    return cat


def _check_page(cat, page):
    base = f"pages.{page}"
    tiles, bookmarks = cat["tiles"], cat["bookmarks"]
    data = _mapping(cat["pages"].get(page), base)
    placed = {"tiles": {}, "bookmarks": {}}
    group_names, tab_slugs = set(), set()

    def group(path, g, parents):
        _check_keys(path, g, GROUP_KEYS)
        name = g.get("name")
        if not isinstance(name, str) or not name:
            raise CatalogError(f"{path}: group has no name")
        if name in group_names:
            raise CatalogError(f"{path}.name: duplicate group name {name!r} on page {page}")
        group_names.add(name)
        kinds = set()
        for i, item in enumerate(_list(g.get("items"), f"{path}.items")):
            ipath = f"{path}.items[{i}]"
            if isinstance(item, dict):
                group(ipath, item, parents + [name])
            elif not isinstance(item, str):
                raise CatalogError(f"{ipath}: not a tile/bookmark id or a subgroup mapping")
            elif item in tiles:
                kinds.add("tiles")
                placed["tiles"][item] = placed["tiles"].get(item, 0) + 1
            elif item in bookmarks:
                kinds.add("bookmarks")
                placed["bookmarks"][item] = placed["bookmarks"].get(item, 0) + 1
            else:
                raise CatalogError(f"{ipath}: {item!r} is neither a tile nor a bookmark id")
        if len(kinds) > 1:
            raise CatalogError(f"{path}: group mixes tiles and bookmarks")

    for t, tab in enumerate(_list(data.get("tabs"), f"{base}.tabs")):
        tpath = f"{base}.tabs[{t}]"
        _check_keys(tpath, tab, {"name", "groups"})
        if not isinstance(tab.get("name"), str) or not re.fullmatch(r"[A-Za-z0-9 ]+", tab["name"]):
            raise CatalogError(f"{tpath}.name: must match [A-Za-z0-9 ]+")
        s = slug(tab["name"])
        if s in tab_slugs:
            raise CatalogError(f"{tpath}.name: duplicate tab slug {s!r} on page {page}")
        tab_slugs.add(s)
        for g, grp in enumerate(_list(tab.get("groups"), f"{tpath}.groups")):
            group(f"{tpath}.groups[{g}]", grp, [])

    for kind, entries in (("tiles", tiles), ("bookmarks", bookmarks)):
        names = {}
        for eid, entry in entries.items():
            want = shown_on(audience(entry), page)
            n = placed[kind].get(eid, 0)
            if n != int(want):
                raise CatalogError(f"{kind}.{eid}: audience {audience(entry)!r} needs {int(want)} placement(s) on page {page}, found {n}")
            if want:
                name = (page_tile(entry, page) if kind == "tiles" else entry).get("name")
                if not name:
                    raise CatalogError(f"{kind}.{eid}: no name on page {page}")
                if name in names:
                    raise CatalogError(f"{kind}.{eid}.name: {name!r} duplicates {names[name]} on page {page}")
                names[name] = eid
