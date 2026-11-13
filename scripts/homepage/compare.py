"""Temporary check: do the staged ConfigMaps carry the same facts as the live ones?"""
import re
from typing import Any

import yaml

from catalog import loads_yaml

_VAR = re.compile(r"HOMEPAGE_VAR_[A-Z0-9_]+")
TILE_FIELDS = ("tab", "group", "index", "href", "siteMonitor", "namespace", "app", "description",
               "widgets", "placeholders")


def parse_configmap(text: str) -> dict[str, Any]:
    text = text.replace('{{ "{{" }}', "{{").replace('{{ "}}" }}', "}}")
    text = re.sub(r"\{\{(HOMEPAGE_VAR_[A-Z0-9_]+)\}\}", r"\1", text)
    cm = loads_yaml(text, "ConfigMap")
    out = {}
    for key, body in cm["data"].items():
        if key.endswith(".yaml"):
            out[key] = loads_yaml(body, key)
    return out


def _tiles(items, group, top, tab, out):
    for index, item in enumerate(items):
        (name, val), = item.items()
        if isinstance(val, dict):
            ws = [val["widget"]] if "widget" in val else val.get("widgets") or []
            out[name] = {
                "tab": tab, "group": group, "index": index,
                **{k: val.get(k) for k in ("href", "siteMonitor", "namespace", "app", "description")},
                "widgets": sorted(str(w.get("type")) for w in ws),
                "placeholders": sorted(sorted(set(_VAR.findall(yaml.safe_dump(w)))) for w in ws),
            }
        else:  # subgroup: keeps its top-level parent's tab
            _tiles(val, name, top, tab, out)


def facts(data: dict) -> dict:
    layout = (data.get("settings.yaml") or {}).get("layout") or {}
    tiles = {}
    for group in data.get("services.yaml") or []:
        (gname, items), = group.items()
        _tiles(items, gname, gname, (layout.get(gname) or {}).get("tab"), tiles)
    bookmarks = {name: b[0].get("href") for group in data.get("bookmarks.yaml") or []
                 for items in group.values() for item in items for name, b in item.items()}
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
