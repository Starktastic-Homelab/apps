import copy
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from catalog import CatalogError, load_catalog, page_tile, slug, walk_groups
from fixture import MIN_CATALOG, make_repo


def load(cat):
    with tempfile.TemporaryDirectory() as d:
        return load_catalog(make_repo(Path(d), cat))


def cat_with(fn):
    c = copy.deepcopy(MIN_CATALOG)
    fn(c)
    return c


def items(c, page, ids, tab=0):
    c["pages"][page]["tabs"][tab]["groups"][0]["items"] = ids


class CatalogTests(unittest.TestCase):
    def bad(self, c, rx):
        with self.assertRaisesRegex(CatalogError, rx):
            load(c)

    def test_min_loads(self):
        self.assertEqual(list(load(MIN_CATALOG)["tiles"]), ["a"])

    def test_rule05_tile_placement(self):
        self.bad(cat_with(lambda c: items(c, "household", [])), r"tiles\.a")
        self.bad(cat_with(lambda c: items(c, "admin", ["a", "a"])), r"tiles\.a")
        self.bad(cat_with(lambda c: (c["tiles"]["a"].update(audience="admin"), items(c, "household", ["a"]))),
                 r"tiles\.a")

    def test_rule05_bookmark_audiences(self):
        def mk(aud, hh, ad):
            def f(c):
                c["bookmarks"] = {"b": {"name": "B", "href": "https://b", "audience": aud}}
                items(c, "household", ["a"] + [])
                c["pages"]["household"]["tabs"][0]["groups"].append({"name": "BG", "items": ["b"] * hh})
                c["pages"]["admin"]["tabs"][0]["groups"].append({"name": "BG", "items": ["b"] * ad})
            return cat_with(f)
        load(mk("household-only", 1, 0))
        self.bad(mk("household-only", 1, 1), r"bookmarks\.b")
        self.bad(mk("admin", 1, 1), r"bookmarks\.b")
        load(mk("admin", 0, 1))

    def test_rule05_tile_household_only_rejected(self):
        self.bad(cat_with(lambda c: c["tiles"]["a"].update(audience="household-only")), r"tiles\.a\.audience")

    def test_rule06_unique_names_after_override(self):
        def f(c):
            c["tiles"]["b"] = {"name": "B", "audience": "household", "href": "https://b",
                               "override": {"household": {"name": "A"}}}
            items(c, "household", ["a", "b"])
            items(c, "admin", ["a", "b"])
        self.bad(cat_with(f), r"tiles\.b\.name.*household")

    def test_rule06_unknown_id(self):
        self.bad(cat_with(lambda c: items(c, "admin", ["a", "zz"])), r"items\[1\].*zz")

    def test_rule06_ids_disjoint(self):
        def f(c):
            c["bookmarks"] = {"a": {"name": "x", "href": "https://x", "audience": "admin"}}
        self.bad(cat_with(f), r"bookmarks\.a")

    def test_case_sensitive_names(self):
        def f(c):
            c["tiles"]["t"] = {"name": "Apps", "audience": "admin", "href": "https://t"}
            c["bookmarks"] = {"b": {"name": "apps", "href": "https://b", "audience": "admin"}}
            items(c, "admin", ["a", "t"])
            c["pages"]["admin"]["tabs"][0]["groups"].append({"name": "BG", "items": ["b"]})
        load(cat_with(f))

    def test_rule06_tab_names_and_slug(self):
        self.assertEqual((slug("Pulse"), slug("Home Lab")), ("pulse", "home-lab"))
        self.bad(cat_with(lambda c: c["pages"]["admin"]["tabs"][0].update(name="Café")), r"tabs\[0\]\.name")
        self.bad(cat_with(lambda c: c["pages"]["admin"]["tabs"].append({"name": "main", "groups": []})), "slug")
        self.bad(cat_with(lambda c: c["pages"]["admin"]["tabs"][0]["groups"].append({"name": "G", "items": []})),
                 "duplicate group")
        self.bad(cat_with(lambda c: c["pages"]["admin"]["tabs"][0]["groups"][0]["items"].append(
            {"name": "G", "items": []})), "duplicate group")

    def test_allowlists(self):
        def tile(**kw):
            return cat_with(lambda c: c["tiles"]["a"].update(kw))
        self.bad(tile(bogus=1), r"tiles\.a\.bogus")
        self.bad(tile(override={"household": {"audience": "admin"}}), r"override\.household\.audience")
        self.bad(tile(override={"admin": {"widgets": []}}), r"override\.admin\.widgets")
        self.bad(cat_with(lambda c: c.update(bookmarks={"b": {"name": "B", "zz": 1}})), r"bookmarks\.b\.zz")
        self.bad(cat_with(lambda c: c["pages"]["admin"]["tabs"][0]["groups"][0].update(zz=1)), r"groups\[0\]\.zz")

        def mixed(c):
            c["bookmarks"] = {"b": {"name": "B", "href": "https://b", "audience": "admin"}}
            items(c, "admin", ["a", "b"])
        self.bad(cat_with(mixed), "mixes")

    def test_page_tile_and_walk(self):
        t = {"name": "N", "icon": "i", "override": {"admin": {"name": "M", "icon": None}}}
        self.assertEqual(page_tile(t, "admin")["name"], "M")
        self.assertNotIn("icon", page_tile(t, "admin"))
        self.assertEqual(page_tile(t, "household")["icon"], "i")
        page = {"tabs": [{"name": "T", "groups": [{"name": "P", "items": ["x", {"name": "S", "items": []}, ]}]}]}
        self.assertEqual([(t, g["name"], p) for t, g, p in walk_groups(page)], [("T", "P", []), ("T", "S", ["P"])])


if __name__ == "__main__":
    unittest.main()
