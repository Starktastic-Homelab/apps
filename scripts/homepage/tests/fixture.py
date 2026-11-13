"""Shared test helpers: build a throwaway repo tree for the generator."""
import copy
from pathlib import Path

import yaml

PAGES = {"household": "services/operations/homepage", "admin": "services/operations/homepage-admin"}

def _page():
    return {"tabs": [{"name": "Main", "groups": [{"name": "G", "items": ["a"]}]}]}
MIN_CATALOG = {
    "tiles": {"a": {"name": "A", "audience": "household", "href": "https://a.example"}},
    "pages": {"household": _page(), "admin": _page()},
    "bookmarks": {},
    "info": [],
}


def _dump(data) -> str:
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


CONFIGMAPS = {"household": "homepage-config", "admin": "homepage-admin-config"}
GENERATED = ("settings.yaml", "services.yaml", "bookmarks.yaml", "widgets.yaml", "kubernetes.yaml", "custom.js",
             "custom.css", "docker.yaml")


def default_mounts(keys=GENERATED) -> list:
    """globalMounts in the cut-over convention: config keys, the favicon, then images."""
    def path(key):
        if key == "favicon.svg":
            return "/app/public/icons/favicon.svg"
        return f"/app/config/{key}" if key in GENERATED + ("proxmox.yaml",) else f"/app/public/images/{key}"
    return [{"path": path(k), "subPath": k, "readOnly": True} for k in keys]


def make_repo(root: Path, catalog, apps=None, sealed=None, pages=None, shared=None, mounts=None) -> Path:
    apps, sealed, pages, mounts = apps or {}, sealed or {}, pages or {}, mounts or {}
    _write(root / "templates/globals.yaml", _dump(
        {"global": {"domains": {"public": "starktastic.net", "internal": "internal.starktastic.net", "media": "benplus.app"}}}))
    for rel, app in apps.items():
        _write(root / rel / "app.yaml", _dump(app))
    for page, appdir in PAGES.items():
        names = sealed.get(page, [])
        _write(root / appdir / "manifests/templates/secrets.yaml", _dump({
            "apiVersion": "bitnami.com/v1alpha1", "kind": "SealedSecret",
            "metadata": {"name": f"homepage-{page}-secrets", "namespace": "operations"},
            "spec": {"encryptedData": {n: "dummy" for n in names}},
        }))
    _write(root / "homepage/catalog.yaml", catalog if isinstance(catalog, str) else _dump(copy.deepcopy(catalog)))
    if shared is not None:
        _write(root / "homepage/pages/shared.css", shared)
    for page in PAGES:
        files = {"settings.yaml": "title: T\n", "custom.css": "", **pages.get(page, {})}
        for name, text in files.items():
            _write(root / "homepage/pages" / page / name, text)
        extra = [n for n in files if n == "proxmox.yaml"] + [n[len("files/"):] for n in files if n.startswith("files/")]
        _write(root / PAGES[page] / "values.yaml", _dump({"persistence": {CONFIGMAPS[page]: {
            "enabled": True, "type": "configMap", "name": CONFIGMAPS[page],
            "globalMounts": mounts.get(page, default_mounts(GENERATED + tuple(extra)))}}}))
    return root
