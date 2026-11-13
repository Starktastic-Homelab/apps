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

# ADR 0020 hook rule: what custom.css may select. Read in Homepage v2.7.0's source; re-read on a bump.
HOOK_IDS = {"layout-groups", "myTab", "tabs", "information-widgets", "information-widgets-right", "widgets-wrap",
            "background", "inner_wrapper", "footer"}
HOOK_CLASSES = {
    "service", "service-card", "service-title", "service-title-text", "service-name", "service-description",
    "service-icon", "service-tag", "service-site-monitor", "site-monitor-status", "service-container",
    "service-block", "service-block-value", "service-block-label", "services-group", "subgroup",
    "service-group-name", "service-group-icon",
    "bookmark", "bookmark-group-name", "bookmark-group-icon", "bookmark-icon", "bookmark-text", "bookmark-name",
    "bookmark-description",
}
HOOK_CLASS_PREFIX = "information-widget-"
HOOK_ATTRS = {"data-name", "data-highlight-level", "role", "aria-selected"}
NO_HOOK = re.compile(r"/\*\s*no-hook:start\s*\*/(.*?)/\*\s*no-hook:end\s*\*/", re.S)
POSITIONAL = re.compile(r":(?:nth-[a-z-]+|(?:first|last|only)-(?:child|of-type))\b")


def _blank(match):
    return " " * len(match.group())


WALKED_AT = {"media", "supports", "container", "layer"}  # at-rules that hold style rules: walked
OPAQUE_AT = {"keyframes", "font-face", "property"}  # at-rules that hold no selectors: skipped


def _selectors(css: str, where: str):
    """Yield (offset, selector text) for every style rule. Anything the walk cannot see into is an error."""
    i, n, start = 0, len(css), 0
    while i < n:
        ch = css[i]
        if ch in ";}":
            start = i + 1
        elif ch == "{":
            prelude = " ".join(css[start:i].split())
            at = re.match(r"@(?:-[a-z]+-)?([a-z-]+)", prelude)
            if at and at.group(1) in WALKED_AT:
                start = i + 1  # rules nested inside: keep scanning
            else:
                if at and at.group(1) not in OPAQUE_AT:
                    raise CatalogError(f"{where}: @{at.group(1)} is not checked by the hook lint; remove it (ADR 0020)")
                if not at:
                    yield i, prelude  # the brace's offset: always inside its no-hook span
                depth, i = 1, i + 1  # skip the block: declarations, @keyframes steps, @font-face
                while i < n and depth:
                    if css[i] == "{" and not at:
                        raise CatalogError(f"{where}: a rule nested in {prelude!r} is not checked by the hook lint; "
                                           "write it flat (ADR 0020)")
                    depth += {"{": 1, "}": -1}.get(css[i], 0)
                    i += 1
                start = i
                continue
        i += 1


def check_css(css: str, page: str, ids: set, tabs: list, where: str) -> None:
    """ADR 0020 rule 3: selectors use Homepage's hooks and tile ids; position only inside the no-hook block."""
    if len(re.findall(r"no-hook:start", css)) != len(NO_HOOK.findall(css)) or \
            len(re.findall(r"no-hook:end", css)) != len(NO_HOOK.findall(css)):
        raise CatalogError(f"{where}: unbalanced /* no-hook:start */ ... /* no-hook:end */ markers")
    spans = [m.span(1) for m in NO_HOOK.finditer(css)]
    # Same-length blanks keep offsets: comments, then strings and url() bodies (they may hold braces).
    text = re.sub(r"/\*.*?\*/", _blank, css, flags=re.S)
    text = re.sub(r"\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|url\([^)]*\)", _blank, text)
    known = HOOK_IDS | {f"{t}-tab" for t in tabs} | ids
    for offset, sel in _selectors(text, where):
        free = any(a <= offset < b for a, b in spans)
        for found in re.findall(r"#([A-Za-z_][\w-]*)", sel):
            if found not in known:
                raise CatalogError(f"{where}: #{found} is not a Homepage id, a tab or a tile on page {page}")
        for found in re.findall(r"\.([A-Za-z_-][\w-]*)", sel):
            if found not in HOOK_CLASSES and not found.startswith(HOOK_CLASS_PREFIX):
                raise CatalogError(f"{where}: .{found} is not a Homepage hook (ADR 0020)")
        if free:
            continue
        for found in re.findall(r"\[\s*([A-Za-z_][\w-]*)", sel):
            if found not in HOOK_ATTRS:
                raise CatalogError(f"{where}: [{found}] is not a Homepage hook (ADR 0020)")
        if POSITIONAL.search(sel) or re.search(r"[+~]", re.sub(r"\[[^\]]*\]", "", sel)):
            raise CatalogError(f"{where}: {sel!r} selects by position; restructure it or move it into the "
                               "no-hook block (ADR 0020)")


def mount_path(key: str) -> str:
    """Where the pod mounts a ConfigMap key; the render check places files the same way."""
    if key in OWN_KEYS:
        return f"/app/config/{key}"
    return "/app/public/icons/favicon.svg" if key == "favicon.svg" else f"/app/public/images/{key}"


def check_mounts(repo: Path, page: str, data: dict) -> None:
    """A cut-over page's values.yaml mounts exactly the ConfigMap's keys: a missing key stops the pod."""
    path = Path(repo) / PAGES[page]["dir"] / "values.yaml"
    where = f"pages.{page}: {path.relative_to(repo)}"
    try:
        values = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as err:
        raise CatalogError(f"{where}: {err}") from err
    cm = PAGES[page]["configmap"]
    try:
        mounts = {m["subPath"]: m["path"] for m in values["persistence"][cm]["globalMounts"]}
    except (KeyError, TypeError) as err:
        raise CatalogError(f"{where}: persistence.{cm}.globalMounts needs a path and subPath per entry") from err
    for key in sorted(set(mounts) - set(data)):
        raise CatalogError(f"{where}: mounts {key}, which is not a key of {cm}")
    for key in sorted(set(data) - set(mounts)):
        raise CatalogError(f"{where}: {key} is a key of {cm} but is not mounted at {mount_path(key)}")
    for key, got in sorted(mounts.items()):
        if got != mount_path(key):
            raise CatalogError(f"{where}: {key} is mounted at {got}, expected {mount_path(key)}")


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
    shared_path = Path(repo) / "homepage/pages/shared.css"
    shared = shared_path.read_text(encoding="utf-8") if shared_path.is_file() else ""
    placed = {i for _tab, g, _parents in walk_groups(pdata) for i in g.get("items") or [] if isinstance(i, str)}
    for text, where in ((shared, "homepage/pages/shared.css"), (css, f"{rel}/custom.css")):
        check_css(text, page, placed, tabs, where)
    if shared.strip():
        css = shared.rstrip("\n") + "\n" + css
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
