import copy
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from catalog import CatalogError, load_catalog
from fixture import make_repo
from render import PAGES, build_page

CAT = {
    "tiles": {
        "cal": {"name": "Calendar", "audience": "household", "widgets": [
            {"audience": "household-only", "type": "calendar",
             "integrations": [{"type": "ical", "name": "TV", "url": "http://x"}]},
            {"type": "calendar", "integrations": [{"ref": "sonarr", "color": "blue"}]},
        ]},
        "jelly": {"name": "Jellyfin", "audience": "household", "href": "https://j.example",
                  "namespace": "media", "app": "jellyfin", "podSelector": "app=j", "proxmoxNode": "pve",
                  "widgets": [{"type": "jellyfin", "url": "http://a"},
                              {"audience": "household", "type": "jellyfin", "url": "http://b"}]},
        "seerr": {"name": "Seerr", "audience": "household",
                  "widgets": [{"audience": "household-only", "type": "seerr", "url": "http://s"}]},
        "sonarr": {"name": "Sonarr", "icon": "sonarr.png", "override": {"admin": {"name": "Sonarr TV"}},
                   "widgets": [{"type": "sonarr", "url": "http://so"}]},
        "plain": {"name": "Plain", "href": "https://p.example"},
    },
    "bookmarks": {
        "gh": {"name": "GitHub", "audience": "household", "abbr": "GH", "href": "https://github.com"},
        "mine": {"name": "My Account", "audience": "household-only", "abbr": "AC", "href": "https://auth"},
    },
    "info": [
        {"audience": "household-only", "greeting": {"text": "hi"}},
        {"datetime": {"text_size": "xl"}},
        {"audience": "household", "search": {"provider": "custom"}},
    ],
    "pages": {
        "household": {"tabs": [
            {"name": "Pulse", "groups": [{"name": "Coming Up", "style": "row", "columns": 1, "items": ["cal"]}]},
            {"name": "Play", "groups": [{"name": "Watch", "items": ["jelly", "seerr"]},
                                        {"name": "Links", "items": ["gh", "mine"]}]},
        ]},
        "admin": {"tabs": [
            {"name": "Pulse", "groups": [{"name": "Coming Up", "items": ["cal"]}]},
            {"name": "Run", "groups": [{"name": "Media", "style": "row", "items": [
                "jelly", "seerr", {"name": "Arr", "columns": 2, "items": ["sonarr", "plain"]}]}]},
            {"name": "Iron", "groups": [{"name": "Links", "items": ["gh"]}]},
        ]},
    },
}


def build(page, cat=CAT, pages=None, edit=None):
    c = copy.deepcopy(cat)
    if edit:
        edit(c)
    with tempfile.TemporaryDirectory() as d:
        repo = make_repo(Path(d), c, pages=pages)
        return build_page(repo, load_catalog(repo), page)


def tiles(data):
    """{tile name: config} across services.yaml, subgroups included."""
    out = {}

    def rec(entries):
        for entry in entries:
            (name, val), = entry.items()
            if isinstance(val, list):
                rec(val)
            else:
                out[name] = val
    for group in data["services.yaml"]:
        rec(next(iter(group.values())))
    return out


class RenderTests(unittest.TestCase):
    def test_pages_constants(self):
        self.assertEqual(PAGES["household"], {"configmap": "homepage-config", "dir": "services/operations/homepage"})
        self.assertEqual(PAGES["admin"], {"configmap": "homepage-admin-config", "dir": "services/operations/homepage-admin"})

    def test_rule07_widget_forms(self):
        h, a = tiles(build("household")), tiles(build("admin"))
        self.assertEqual(h["Jellyfin"]["widget"], {"type": "jellyfin", "url": "http://b"})
        self.assertNotIn("widgets", h["Jellyfin"])
        self.assertEqual([w["url"] for w in a["Jellyfin"]["widgets"]], ["http://a", "http://b"])
        self.assertNotIn("widget", a["Jellyfin"])
        self.assertNotIn("widget", a["Plain"])
        self.assertNotIn("widgets", a["Plain"])
        self.assertEqual(h["Seerr"]["widget"], {"type": "seerr", "url": "http://s"})
        self.assertNotIn("widget", a["Seerr"])

    def test_rule08_calendar_ref(self):
        a = tiles(build("admin"))
        self.assertEqual(a["Calendar"]["widget"]["integrations"],
                         [{"type": "sonarr", "service_group": "Arr", "service_name": "Sonarr TV", "color": "blue"}])
        h = tiles(build("household"))
        self.assertEqual(h["Calendar"]["widget"]["integrations"], [{"type": "ical", "name": "TV", "url": "http://x"}])

        def ref_to(target):
            return lambda c: c["tiles"]["cal"]["widgets"][1]["integrations"][0].update(ref=target)
        with self.assertRaisesRegex(CatalogError, r"tiles\.cal\.widgets\[1\]\.integrations\[0\]\.ref"):
            build("admin", edit=ref_to("nope"))
        with self.assertRaisesRegex(CatalogError, r"tiles\.cal\.widgets\[1\]\.integrations\[0\]\.ref"):
            build("admin", edit=ref_to("jelly"))  # two widgets on admin
        with self.assertRaisesRegex(CatalogError, r"tiles\.cal\.widgets\[1\]\.integrations\[0\]\.ref"):
            build("admin", edit=ref_to("plain"))  # no widget
        with self.assertRaisesRegex(CatalogError, r"tiles\.cal\.widgets\[0\]\.integrations\[0\]\.ref"):
            build("household", edit=lambda c: c["tiles"]["cal"]["widgets"][0].update(integrations=[{"ref": "sonarr"}]))
        with self.assertRaisesRegex(CatalogError, r"tiles\.cal\.widgets\[1\]\.integrations: not a list"):
            build("admin", edit=lambda c: c["tiles"]["cal"]["widgets"][1].update(integrations={"ref": "sonarr"}))

    def test_rule09_layout_and_pwa(self):
        pages = {"household": {"settings.yaml": "title: T\npwa:\n  icons:\n    - src: /i.png\n"}}
        h = build("household", pages=pages)["settings.yaml"]
        self.assertEqual(list(h["layout"]), ["Coming Up", "Watch", "Links"])
        self.assertEqual(h["layout"]["Coming Up"], {"tab": "Pulse", "style": "row", "columns": 1})
        self.assertEqual(h["layout"]["Watch"], {"tab": "Play"})
        self.assertEqual(h["pwa"], {"icons": [{"src": "/i.png"}],
                                    "shortcuts": [{"name": "Pulse", "url": "/#pulse"}, {"name": "Play", "url": "/#play"}]})
        self.assertEqual(list(h), ["title", "hideErrors", "pwa", "layout"])
        a = build("admin")["settings.yaml"]
        self.assertEqual(a["layout"]["Media"], {"tab": "Run", "style": "row", "Arr": {"columns": 2}})
        self.assertNotIn("Arr", a["layout"])
        self.assertEqual(a["pwa"], {"shortcuts": [{"name": n, "url": f"/#{n.lower()}"} for n in ("Pulse", "Run", "Iron")]})

        def no_none(v):
            if isinstance(v, dict):
                for x in v.values():
                    self.assertIsNotNone(x)
                    no_none(x)
        no_none(a["layout"])
        sub = build("admin", edit=lambda c: c["pages"]["admin"]["tabs"][1]["groups"][0]["items"][2].pop("columns"))
        self.assertEqual(sub["settings.yaml"]["layout"]["Media"]["Arr"], {})

    def test_rule10_css_data_name(self):
        with self.assertRaisesRegex(CatalogError, r"custom\.css.*Nope"):
            build("household", pages={"household": {"custom.css": 'li[data-name="Nope"] {}\n'}})
        with self.assertRaisesRegex(CatalogError, r"custom\.css.*Sonarr"):
            build("household", pages={"household": {"custom.css": 'li[data-name="Sonarr"] {}\n'}})
        css = 'li[data-name="Calendar"] {}\n'
        self.assertEqual(build("household", pages={"household": {"custom.css": css}})["custom.css"], css)

    def test_rule11_to_14_generator_owned(self):
        h, a = build("household"), build("admin")
        self.assertIs(h["settings.yaml"]["hideErrors"], True)
        self.assertIs(a["settings.yaml"]["hideErrors"], False)
        self.assertEqual(h["kubernetes.yaml"], {"mode": "disabled"})
        self.assertEqual(a["kubernetes.yaml"], {"mode": "cluster"})
        for d in (h, a):
            self.assertEqual(d["docker.yaml"], "")
            self.assertEqual(d["custom.js"], "")
        for text in ("hideErrors: true\n", "layout:\n  G:\n    tab: Main\n", "pwa:\n  shortcuts: []\n"):
            with self.assertRaisesRegex(CatalogError, r"settings\.yaml"):
                build("admin", pages={"admin": {"settings.yaml": text}})
        with self.assertRaisesRegex(CatalogError, r"custom\.js"):
            build("admin", pages={"admin": {"custom.js": ""}})

    def test_rule15_household_admin_keys(self):
        keys = ("namespace", "app", "podSelector", "proxmoxNode")
        a, h = tiles(build("admin"))["Jellyfin"], tiles(build("household"))["Jellyfin"]
        self.assertEqual({k: a[k] for k in keys},
                         {"namespace": "media", "app": "jellyfin", "podSelector": "app=j", "proxmoxNode": "pve"})
        self.assertFalse(set(keys) & set(h))

    def test_passthrough_files(self):
        svg = '<svg  xmlns="x">\n  <!-- keep -->\n</svg>\n'
        pages = {"household": {"files/favicon.svg": svg},
                 "admin": {"files/favicon.svg": svg, "proxmox.yaml": "# comment\npve:\n  url: https://pve\n"}}
        h, a = build("household", pages=pages), build("admin", pages=pages)
        self.assertEqual(h["favicon.svg"], svg)
        self.assertEqual(a["proxmox.yaml"], {"pve": {"url": "https://pve"}})
        self.assertNotIn("proxmox.yaml", h)
        self.assertEqual(list(a), ["proxmox.yaml", "favicon.svg", "docker.yaml", "custom.js", "custom.css",
                                   "kubernetes.yaml", "settings.yaml", "widgets.yaml", "services.yaml", "bookmarks.yaml"])
        self.assertEqual(list(h)[0], "favicon.svg")
        self.assertNotIn("proxmox.yaml", build("admin"))
        with self.assertRaisesRegex(CatalogError, r"proxmox\.yaml"):
            build("household", pages={"household": {"proxmox.yaml": "pve: {}\n"}})
        with self.assertRaisesRegex(CatalogError, r"files/settings\.yaml"):
            build("admin", pages={"admin": {"files/settings.yaml": "x"}})

        self.assertEqual(h["widgets.yaml"], [{"greeting": {"text": "hi"}}, {"search": {"provider": "custom"}}])
        self.assertEqual(a["widgets.yaml"], [{"datetime": {"text_size": "xl"}}, {"search": {"provider": "custom"}}])

        self.assertEqual(h["bookmarks.yaml"], [{"Links": [
            {"GitHub": [{"id": "gh", "abbr": "GH", "href": "https://github.com"}]},
            {"My Account": [{"id": "mine", "abbr": "AC", "href": "https://auth"}]},
        ]}])
        self.assertEqual(a["bookmarks.yaml"], [{"Links": [{"GitHub": [{"id": "gh", "abbr": "GH", "href": "https://github.com"}]}]}])

        self.assertEqual([list(g) for g in a["services.yaml"]], [["Coming Up"], ["Media"]])
        media = a["services.yaml"][1]["Media"]
        self.assertEqual([list(e)[0] for e in media], ["Jellyfin", "Seerr", "Arr"])
        self.assertEqual(media[2]["Arr"][0], {"Sonarr TV": {"id": "sonarr", "icon": "sonarr.png",
                                                            "widget": {"type": "sonarr", "url": "http://so"}}})
        jelly = media[0]["Jellyfin"]
        self.assertEqual(list(jelly)[0], "id")
        self.assertEqual(list(jelly)[-1], "widgets")

    def test_tile_has_no_inner_name(self):
        for page in ("household", "admin"):
            for name, t in tiles(build(page)).items():
                self.assertNotIn("name", t, name)

    def test_ref_integration_checks(self):
        def bad(integ, rx):
            with self.assertRaisesRegex(CatalogError, rx):
                build("admin", edit=lambda c: c["tiles"]["cal"]["widgets"][1].update(integrations=[integ]))
        for key in ("type", "service_group", "service_name"):
            bad({"ref": "sonarr", key: "x"}, rf"tiles\.cal\.widgets\[1\]\.integrations\[0\]: {key}")
        bad("sonarr", r"tiles\.cal\.widgets\[1\]\.integrations\[0\]: not a mapping")

    def test_page_dir_allowlist(self):
        for page, name in (("admin", "custom.js"), ("admin", "extra.yaml"), ("household", "docker.yaml"),
                           ("admin", "files/sub/x.svg")):
            with self.assertRaisesRegex(CatalogError, rf"homepage/pages/{page}/{name.split('/sub')[0]}"):
                build(page, pages={page: {name: ""}})
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d), copy.deepcopy(CAT))
            (repo / "homepage/pages/admin/files").write_text("x")  # files must be a directory
            with self.assertRaisesRegex(CatalogError, r"homepage/pages/admin/files: not an allowed"):
                build_page(repo, load_catalog(repo), "admin")
            (repo / "homepage/pages/admin/files").unlink()
            (repo / "homepage/pages/admin/custom.css").unlink()
            (repo / "homepage/pages/admin/custom.css").mkdir()  # custom.css must be a file
            with self.assertRaisesRegex(CatalogError, r"homepage/pages/admin/custom\.css: not an allowed"):
                build_page(repo, load_catalog(repo), "admin")

    def test_empty_proxmox_and_bad_pwa(self):
        for text in ("", "# only a comment\n", "- a\n"):
            with self.assertRaisesRegex(CatalogError, r"proxmox\.yaml: empty or not a mapping"):
                build("admin", pages={"admin": {"proxmox.yaml": text}})
        for text in ("pwa:\n", "pwa: x\n", "pwa:\n  - a\n"):
            with self.assertRaisesRegex(CatalogError, r"settings\.yaml\.pwa: not a mapping"):
                build("admin", pages={"admin": {"settings.yaml": text}})

    def test_missing_settings(self):
        c = copy.deepcopy(CAT)
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d), c)
            (repo / "homepage/pages/admin/settings.yaml").unlink()
            (repo / "homepage/pages/admin/custom.css").unlink()
            cat = load_catalog(repo)
            with self.assertRaisesRegex(CatalogError, r"settings\.yaml"):
                build_page(repo, cat, "admin")
            (repo / "homepage/pages/admin/settings.yaml").write_text("title: T\n")
            self.assertEqual(build_page(repo, cat, "admin")["custom.css"], "")

    def test_entry_shapes(self):
        def bad(edit, rx):
            with self.assertRaisesRegex(CatalogError, rx):
                build("admin", edit=edit)
        bad(lambda c: c["tiles"]["plain"].update(widgets=[5]), r"tiles\.plain\.widgets\[0\]: not a mapping")
        bad(lambda c: c["tiles"]["plain"].update(widgets=[{"url": "x"}]), r"tiles\.plain\.widgets\[0\]: .*type")
        bad(lambda c: c["info"].append(5), r"info\[3\]: not a mapping")
        bad(lambda c: c["info"].append({"a": {}, "b": {}}), r"info\[3\]: .*one")
        bad(lambda c: c["info"].append({"audience": "admin"}), r"info\[3\]: .*one")


if __name__ == "__main__":
    unittest.main()
