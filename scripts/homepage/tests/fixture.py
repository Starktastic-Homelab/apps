"""Shared test helpers: build a throwaway repo tree for the generator."""
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


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_repo(root: Path, catalog, apps=None, sealed=None, pages=None) -> Path:
    apps, sealed, pages = apps or {}, sealed or {}, pages or {}
    _write(root / "templates/globals.yaml", yaml.safe_dump(
        {"domains": {"public": "starktastic.net", "internal": "internal.starktastic.net", "media": "benplus.app"}}))
    for rel, app in apps.items():
        _write(root / rel / "app.yaml", yaml.safe_dump(app))
    for page, appdir in PAGES.items():
        names = sealed.get(page, [])
        _write(root / appdir / "manifests/templates/secrets.yaml", yaml.safe_dump({
            "apiVersion": "bitnami.com/v1alpha1", "kind": "SealedSecret",
            "metadata": {"name": f"homepage-{page}-secrets", "namespace": "operations"},
            "spec": {"encryptedData": {n: "dummy" for n in names}},
        }))
    _write(root / "homepage/catalog.yaml", catalog if isinstance(catalog, str) else yaml.safe_dump(catalog))
    for page in PAGES:
        files = {"settings.yaml": "title: T\n", "custom.css": "", **pages.get(page, {})}
        for name, text in files.items():
            _write(root / "homepage/pages" / page / name, text)
    return root
