"""Temporary check: do the staged ConfigMaps carry the same facts as the live ones?"""
import re
from typing import Any

import yaml

from catalog import CatalogError, loads_yaml

_VAR = re.compile(r"HOMEPAGE_VAR_[A-Z0-9_]+")
TILE_FIELDS = ("tab", "group", "index", "href", "siteMonitor", "namespace", "app", "description",
               "widgets", "placeholders")


def _data(text: str) -> dict[str, str]:
    text = text.replace('{{ "{{" }}', "{{").replace('{{ "}}" }}', "}}")
    text = re.sub(r"\{\{(HOMEPAGE_VAR_[A-Z0-9_]+)\}\}", r"\1", text)
    cm = loads_yaml(text, "ConfigMap")
    if not isinstance(cm, dict) or not isinstance(cm.get("data"), dict):
        raise CatalogError("ConfigMap has no data mapping")
    return cm["data"]


def parse_configmap(text: str) -> dict[str, Any]:
    return {k: loads_yaml(b, k) for k, b in _data(text).items() if k.endswith(".yaml")}


def raw_keys(text: str) -> dict[str, str]:
    """Non-.yaml keys (CSS, favicon, ...), compared byte for byte."""
    return {k: b for k, b in _data(text).items() if not k.endswith(".yaml")}


def strip_ids(x: Any) -> Any:
    if isinstance(x, dict):
        return {k: strip_ids(v) for k, v in x.items() if k != "id"}
    return [strip_ids(v) for v in x] if isinstance(x, list) else x


def strict_diff(live: dict, staged: dict, live_raw: dict, staged_raw: dict, page: str) -> list[str]:
    """Everything beyond the compared facts: full parsed data without ids, plus the raw keys."""
    out = []
    for key in sorted(live.keys() | staged.keys()):
        if strip_ids(live.get(key)) != strip_ids(staged.get(key)):
            out.append(f"{page}: {key}: differs beyond the compared facts")
    for key in sorted(live_raw.keys() | staged_raw.keys()):
        if live_raw.get(key) != staged_raw.get(key):
            out.append(f"{page}: {key}: live and staged differ")
    return out


def _tiles(items, group, tab, out):
    for index, item in enumerate(items):
        (name, val), = item.items()
        if isinstance(val, dict):
            if name in out:
                raise CatalogError(f"duplicate tile name {name!r}")
            ws = [val["widget"]] if "widget" in val else val.get("widgets") or []
            out[name] = {
                "tab": tab, "group": group, "index": index,
                **{k: val.get(k) for k in ("href", "siteMonitor", "namespace", "app", "description")},
                "widgets": sorted(str(w.get("type")) for w in ws),
                "placeholders": sorted(sorted(set(_VAR.findall(yaml.safe_dump(w)))) for w in ws),
            }
        else:  # subgroup: keeps its top-level parent's tab
            _tiles(val, name, tab, out)


def facts(data: dict) -> dict:
    layout = (data.get("settings.yaml") or {}).get("layout") or {}
    tiles = {}
    for group in data.get("services.yaml") or []:
        (gname, items), = group.items()
        _tiles(items, gname, (layout.get(gname) or {}).get("tab"), tiles)
    bookmarks = {}
    for group in data.get("bookmarks.yaml") or []:
        for items in group.values():
            for item in items:
                for name, b in item.items():
                    if name in bookmarks:
                        raise CatalogError(f"duplicate bookmark name {name!r}")
                    bookmarks[name] = b[0].get("href")
    info = [next(iter(e)) for e in data.get("widgets.yaml") or []]
    return {"tiles": tiles, "bookmarks": bookmarks, "info": info}


def diff(live: dict, staged: dict, page: str = "page") -> list[str]:
    out = []
    for kind in ("tile", "bookmark"):
        a, b = live[kind + "s"], staged[kind + "s"]
        for name in sorted(a.keys() | b.keys()):
            if name not in b or name not in a:
                out.append(f"{page}: {kind} {name}: only in {'live' if name in a else 'staged'}")
            elif a[name] != b[name]:
                fields = TILE_FIELDS if kind == "tile" else (None,)
                for f in fields:
                    x, y = (a[name], b[name]) if f is None else (a[name][f], b[name][f])
                    if x != y:
                        out.append(f"{page}: {kind} {name}: {f or 'href'}: live={x} staged={y}")
    if live["info"] != staged["info"]:
        out.append(f"{page}: info: live={live['info']} staged={staged['info']}")
    return out
