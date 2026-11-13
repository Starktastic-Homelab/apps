"""Build one Homepage page's ConfigMap data from the catalog and its pass-through files."""
import copy
import re
from pathlib import Path
from typing import Any

from catalog import (GROUP_KEYS, TILE_EMIT, CatalogError, audience, load_yaml, page_tile, shown_on, slug,
                     walk_groups)

PAGES = {
    "household": {"configmap": "homepage-config", "dir": "services/operations/homepage"},
    "admin": {"configmap": "homepage-admin-config", "dir": "services/operations/homepage-admin"},
}
LAYOUT_KEYS = [k for k in GROUP_KEYS if k not in ("name", "items")]
ADMIN_ONLY = {"namespace", "app", "podSelector", "proxmoxNode", "proxmoxVMID"}  # rule 15
OWN_KEYS = ("proxmox.yaml", "docker.yaml", "custom.js", "custom.css", "kubernetes.yaml", "settings.yaml",
            "widgets.yaml", "services.yaml", "bookmarks.yaml")


def _widgets(tile, page):
    return [(i, w) for i, w in enumerate(tile.get("widgets") or []) if shown_on(audience(w), page)]


def _emit_widget(cat, page, tid, i, w, group_of):
    out = {k: copy.deepcopy(v) for k, v in w.items() if k != "audience"}
    if "integrations" not in w:
        return out
    path = f"tiles.{tid}.widgets[{i}].integrations"
    if not isinstance(w["integrations"], list):
        raise CatalogError(f"{path}: not a list")
    ints = []
    for j, integ in enumerate(out["integrations"]):
        if not isinstance(integ, dict) or "ref" not in integ:
            ints.append(integ)
            continue
        ref, rest = integ["ref"], {k: v for k, v in integ.items() if k != "ref"}
        target = cat["tiles"].get(ref)
        if target is None or ref not in group_of:
            raise CatalogError(f"{path}[{j}].ref: {ref!r} is not a tile on page {page}")
        tw = _widgets(target, page)
        if len(tw) != 1:
            raise CatalogError(f"{path}[{j}].ref: {ref!r} has {len(tw)} widgets on page {page}, needs exactly 1")
        ints.append({"type": tw[0][1]["type"], "service_group": group_of[ref],
                     "service_name": page_tile(target, page)["name"], **rest})
    out["integrations"] = ints
    return out


def _emit_tile(cat, page, tid, group_of):
    tile = cat["tiles"][tid]
    pt = page_tile(tile, page)
    out = {"id": tid}
    out.update((k, v) for k, v in pt.items()
               if k in TILE_EMIT and not (page == "household" and k in ADMIN_ONLY))
    ws = [_emit_widget(cat, page, tid, i, w, group_of) for i, w in _widgets(tile, page)]
    if len(ws) == 1:
        out["widget"] = ws[0]
    elif ws:
        out["widgets"] = ws
    return {pt["name"]: out}


def _emit_items(cat, page, group, group_of):
    out = []
    for item in group.get("items") or []:
        if isinstance(item, dict):
            out.append({item["name"]: _emit_items(cat, page, item, group_of)})
        elif item in cat["tiles"]:
            out.append(_emit_tile(cat, page, item, group_of))
        else:
            b = cat["bookmarks"][item]
            out.append({b["name"]: [{"id": item, **{k: v for k, v in b.items() if k not in ("name", "audience")}}]})
    return out


def _has_bookmark(cat, group):
    return any(_has_bookmark(cat, i) if isinstance(i, dict) else i in cat["bookmarks"] for i in group.get("items") or [])


def _layout(group, tab):
    out = {"tab": tab} if tab else {}
    out.update((k, group[k]) for k in LAYOUT_KEYS if group.get(k) is not None)
    for item in group.get("items") or []:
        if isinstance(item, dict):
            out[item["name"]] = _layout(item, None)
    return out


def _settings(path, data, page, tabs, layout):
    for key in ("hideErrors", "layout"):
        if key in data:
            raise CatalogError(f"{path}.{key}: generator-owned; remove it")
    pwa = data.get("pwa") or {}
    if not isinstance(pwa, dict):
        raise CatalogError(f"{path}.pwa: not a mapping")
    if "shortcuts" in pwa:
        raise CatalogError(f"{path}.pwa.shortcuts: generator-owned; remove it")
    out = {k: v for k, v in data.items() if k != "pwa"}
    out["hideErrors"] = page == "household"
    out["pwa"] = {**pwa, "shortcuts": [{"name": t, "url": f"/#{slug(t)}"} for t in tabs]}
    out["layout"] = layout
    return out


def build_page(repo: Path, cat: dict, page: str) -> dict[str, Any]:
    pdir = Path(repo) / "homepage/pages" / page
    rel = f"homepage/pages/{page}"
    pdata = cat["pages"][page]
    tabs = [t["name"] for t in pdata.get("tabs") or []]

    group_of = {}
    for _tab, g, _parents in walk_groups(pdata):
        for item in g.get("items") or []:
            if isinstance(item, str):
                group_of[item] = g["name"]
    group_of = {k: v for k, v in group_of.items() if k in cat["tiles"]}

    services, bookmarks, layout = [], [], {}
    for tab in pdata.get("tabs") or []:
        for g in tab.get("groups") or []:
            layout[g["name"]] = _layout(g, tab["name"])
            target = bookmarks if _has_bookmark(cat, g) else services
            target.append({g["name"]: _emit_items(cat, page, g, group_of)})

    widgets = [{k: v for k, v in e.items() if k != "audience"} for e in cat["info"] if shown_on(audience(e), page)]

    if (pdir / "custom.js").exists():
        raise CatalogError(f"{rel}/custom.js: generator-owned (always empty); remove it")
    if not (pdir / "settings.yaml").is_file():
        raise CatalogError(f"{rel}/settings.yaml: missing")
    sdata = load_yaml(pdir / "settings.yaml")
    if not isinstance(sdata, dict):
        raise CatalogError(f"{rel}/settings.yaml: not a mapping")
    css_path = pdir / "custom.css"
    css = css_path.read_text(encoding="utf-8") if css_path.is_file() else ""
    names = {page_tile(t, page)["name"] for tid, t in cat["tiles"].items() if tid in group_of}
    for name in re.findall(r'data-name="([^"]*)"', css):
        if name not in names:
            raise CatalogError(f"{rel}/custom.css: data-name={name!r} is not a tile on page {page}")

    data = {}
    if (pdir / "proxmox.yaml").exists():
        if page != "admin":
            raise CatalogError(f"{rel}/proxmox.yaml: only the admin page has Proxmox access")
        data["proxmox.yaml"] = load_yaml(pdir / "proxmox.yaml")
    fdir = pdir / "files"
    for f in sorted(fdir.iterdir()) if fdir.is_dir() else []:
        if f.name in OWN_KEYS:
            raise CatalogError(f"{rel}/files/{f.name}: clashes with a generated data key")
        if f.is_file():
            data[f.name] = f.read_text(encoding="utf-8")
    data.update({
        "docker.yaml": "",
        "custom.js": "",
        "custom.css": css,
        "kubernetes.yaml": {"mode": "disabled" if page == "household" else "cluster"},
        "settings.yaml": _settings(f"{rel}/settings.yaml", sdata, page, tabs, layout),
        "widgets.yaml": widgets,
        "services.yaml": services,
        "bookmarks.yaml": bookmarks,
    })
    return data
