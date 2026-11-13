"""Homepage catalog loader and generator helpers."""
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


def derive(repo: Path, source: str) -> dict:
    """Mirror cluster-apps.yaml + ingress-chart: href, siteMonitor (no monitorPath), namespace, app."""
    path = Path(repo) / source / "app.yaml"
    if not path.is_file():
        raise CatalogError(f"{source}: no app.yaml")
    app = load_yaml(path)
    if app.get("baseApp"):
        app = _merge(load_yaml(Path(repo) / app["baseApp"] / "app.yaml"), app)
    ing = app.get("ingress") or {}
    if not ing.get("enabled"):
        raise CatalogError(f"{source}: ingress is not enabled")
    domains = load_yaml(Path(repo) / "templates/globals.yaml")["global"]["domains"]
    domain = domains[ing.get("domainType") or "internal"]
    host = ing.get("host") or ""
    svc = ing.get("serviceName") or app["name"]
    return {
        "href": f"https://{domain if not host else f'{host}.{domain}'}",
        "siteMonitor": f"http://{svc}.{app['namespace']}:{ing.get('port', 80)}",
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
