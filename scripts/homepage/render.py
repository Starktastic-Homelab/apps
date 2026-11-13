"""Build one Homepage page's ConfigMap data from the catalog and its pass-through files."""
import copy
import re
import textwrap
from pathlib import Path
from typing import Any

import yaml

from catalog import (GROUP_KEYS, TILE_EMIT, CatalogError, audience, load_yaml, page_tile, shown_on, slug,
                     walk_groups)

PAGES = {
    "household": {"configmap": "homepage-config", "dir": "services/operations/homepage"},
    "admin": {"configmap": "homepage-admin-config", "dir": "services/operations/homepage-admin"},
}
LAYOUT_KEYS = ("style", "columns", "icon", "header", "initiallyCollapsed", "useEqualHeights")  # ordered: output order
assert set(LAYOUT_KEYS) == GROUP_KEYS - {"name", "items"}
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
        if not isinstance(integ, dict):
            raise CatalogError(f"{path}[{j}]: not a mapping")
        if "ref" not in integ:
            ints.append(integ)
            continue
        filled = {"type", "service_group", "service_name"} & set(integ)
        if filled:
            raise CatalogError(f"{path}[{j}]: {', '.join(sorted(filled))} filled from ref; remove")
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
               if k in TILE_EMIT and k != "name" and not (page == "household" and k in ADMIN_ONLY))
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
    pwa = data.get("pwa", {})
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

    allowed = {"settings.yaml", "custom.css", "files"} | ({"proxmox.yaml"} if page == "admin" else set())
    for f in sorted(pdir.iterdir()) if pdir.is_dir() else []:
        if f.name == "proxmox.yaml" and page != "admin":
            raise CatalogError(f"{rel}/proxmox.yaml: only the admin page has Proxmox access")
        if f.name not in allowed or (f.is_dir() != (f.name == "files")):
            raise CatalogError(f"{rel}/{f.name}: not an allowed page input "
                               "(settings.yaml, custom.css, files/, admin proxmox.yaml)")
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
        prox = load_yaml(pdir / "proxmox.yaml")
        if not prox or not isinstance(prox, dict):
            raise CatalogError(f"{rel}/proxmox.yaml: empty or not a mapping")
        data["proxmox.yaml"] = prox
    fdir = pdir / "files"
    for f in sorted(fdir.iterdir()) if fdir.is_dir() else []:
        if f.name in OWN_KEYS:
            raise CatalogError(f"{rel}/files/{f.name}: clashes with a generated data key")
        if not f.is_file() or f.is_symlink():
            raise CatalogError(f"{rel}/files/{f.name}: not a regular file")
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


class NoAliasDumper(yaml.SafeDumper):
    def ignore_aliases(self, data):
        return True


HEADER = "# Generated by scripts/homepage/generate.py from homepage/catalog.yaml. Do not edit.\n"
PLACEHOLDER = re.compile(r"\{\{(HOMEPAGE_VAR_[A-Z0-9_]+)\}\}")


def dump_page(page: str, data: dict) -> str:
    """Rule 18: the unescaped ConfigMap text, wrapper built as text."""
    out = [HEADER, f"apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: {PAGES[page]['configmap']}\n"
                   "  namespace: operations\ndata:\n"]
    for key, val in data.items():
        if isinstance(val, str):
            body = val.rstrip("\n") + "\n" if val.strip() else ""
        else:
            body = yaml.dump(val, Dumper=NoAliasDumper, sort_keys=False, allow_unicode=True,
                             width=float("inf"), default_flow_style=False)
        if not body:
            out.append(f'  {key}: ""\n')
            continue
        if body.lstrip("\n")[:1] in (" ", "\t"):
            # `|` without an indentation indicator would take the first line's indent as the block's.
            raise CatalogError(f"pages.{page}: data key {key} starts with whitespace")
        out.append(f"  {key}: |\n" + textwrap.indent(body, "    ", lambda ln: ln.strip("\n") != ""))
    return "".join(out)


def sealed_names(repo: Path, page: str) -> set[str]:
    path = Path(repo) / PAGES[page]["dir"] / "manifests/templates/secrets.yaml"
    if not path.is_file():
        raise CatalogError(f"pages.{page}: {path.relative_to(repo)} missing")
    doc = load_yaml(path)
    spec = doc.get("spec") if isinstance(doc, dict) else None
    enc = spec.get("encryptedData") if isinstance(spec, dict) else None
    if not isinstance(enc, dict):
        raise CatalogError(f"pages.{page}: {path.relative_to(repo)} spec.encryptedData is not a mapping")
    return set(enc)


def check_placeholders(repo: Path, page: str, text: str) -> None:
    """Rules 16-17 on the unescaped text."""
    rest = PLACEHOLDER.sub("", text)
    for brace in ("{{", "}}"):
        if brace in rest:
            line = next(ln for ln in rest.splitlines() if brace in ln).strip()
            raise CatalogError(f"pages.{page}: {brace!r} outside a {{{{HOMEPAGE_VAR_...}}}} placeholder: {line}")
    used, sealed = set(PLACEHOLDER.findall(text)), sealed_names(repo, page)
    if used - sealed:
        raise CatalogError(f"pages.{page}: referenced but not sealed: {', '.join(sorted(used - sealed))}")
    if sealed - used:
        raise CatalogError(f"pages.{page}: sealed but not referenced: {', '.join(sorted(sealed - used))}")


def helm_escape(text: str) -> str:
    """Rule 19: today's Helm-escaped placeholder form."""
    return PLACEHOLDER.sub(r'{{ "{{" }}\1{{ "}}" }}', text)
