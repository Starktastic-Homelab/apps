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

    def test_subgroup_named_like_layout_key(self):
        for name in ("header", "tab", "columns"):
            self.bad(cat_with(lambda c: items(c, "household", [{"name": name, "items": ["a"]}])), "collides")

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
        self.bad(cat_with(f), "also a tile id")

    def test_audience_values_on_info_and_widgets(self):
        self.bad(cat_with(lambda c: c.update(info=[{"audience": "nope"}])), r"info\[0\]\.audience")
        self.bad(cat_with(lambda c: c["tiles"]["a"].update(widgets=[{"type": "x", "audience": "nope"}])),
                 r"widgets\[0\]\.audience")
        load(cat_with(lambda c: c["tiles"]["a"].update(widgets=[{"type": "x", "audience": "household-only"}])))

    def test_unknown_override_page_and_pages_key(self):
        self.bad(cat_with(lambda c: c["tiles"]["a"].update(override={"guest": {"name": "x"}})),
                 r"override\.guest")
        self.bad(cat_with(lambda c: c["pages"].update(guest={})), r"pages\.guest")

    def test_group_without_name(self):
        self.bad(cat_with(lambda c: c["pages"]["admin"]["tabs"][0]["groups"][0].pop("name")), "no name")
        self.bad(cat_with(lambda c: c["pages"]["admin"]["tabs"][0]["groups"][0].update(name=5)), "no name")

    def test_malformed_shapes(self):
        for rx, fn in (
            (r"items\[0\]", lambda c: items(c, "admin", [["a"]])),
            (r"admin\.tabs\[0\]\.groups\[0\]\.items: not a list", lambda c: items(c, "admin", "a")),
            ("^bookmarks: not a mapping", lambda c: c.update(bookmarks=[])),
            ("^tiles: not a mapping", lambda c: c.update(tiles=[])),
            ("^info: not a list", lambda c: c.update(info={})),
        ):
            with self.subTest(rx):
                self.bad(cat_with(fn), rx)

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

    def test_bookmark_groups_flat_and_unmixed_across_levels(self):
        def mk(top, sub):
            def fn(c):
                c["bookmarks"] = {"b": {"name": "B", "href": "https://b", "audience": "admin"}}
                items(c, "admin", top + [{"name": "S", "items": sub}])
            return cat_with(fn)
        self.bad(mk(["a"], ["b"]), r"pages\.admin\.tabs\[0\]\.groups\[0\]: group mixes")
        self.bad(mk(["b"], ["a"]), r"pages\.admin\.tabs\[0\]\.groups\[0\]: group mixes")
        self.bad(mk(["a"], [{"name": "S2", "items": ["b"]}]), r"groups\[0\]\.items\[1\]: a bookmark group cannot hold")
        self.bad(mk([], ["b", "a"]), r"groups\[0\]\.items\[0\]: group mixes")
        self.bad(mk([], ["b"]), r"pages\.admin\.tabs\[0\]\.groups\[0\]: a bookmark group cannot hold subgroups")
        self.bad(mk(["b"], []), r"pages\.admin\.tabs\[0\]\.groups\[0\]: a bookmark group cannot hold subgroups")
        load(cat_with(lambda c: items(c, "admin", [{"name": "S", "items": ["a"]}])))  # tile subgroups are fine

    def test_page_tile_and_walk(self):
        t = {"name": "N", "icon": "i", "override": {"admin": {"name": "M", "icon": None}}}
        self.assertEqual(page_tile(t, "admin")["name"], "M")
        self.assertNotIn("icon", page_tile(t, "admin"))
        self.assertEqual(page_tile(t, "household")["icon"], "i")
        page = {"tabs": [{"name": "T", "groups": [{"name": "P", "items": ["x", {"name": "S", "items": []}, ]}]}]}
        self.assertEqual([(t, g["name"], p) for t, g, p in walk_groups(page)], [("T", "P", []), ("T", "S", ["P"])])


if __name__ == "__main__":
    unittest.main()
