"""The render check's pure parts: no Docker, no browser."""
import copy
import sys
import unittest
from pathlib import Path
from unittest import mock

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "rendercheck"))
import render_check  # noqa: E402
from render_check import build_config, failures, mock_slug  # noqa: E402

ICAL = "http://sonarr.media:8989/feed/v3/calendar/Sonarr.ics?apikey={{HOMEPAGE_VAR_SONARR_KEY}}&pastDays=30"
PROM = "http://prom.monitoring:9090/api/v1/query?query=min(x%7Ba%3D%221%22%7D)"
DATA = {
    "proxmox.yaml": {"pve": {"url": "https://10.9.9.20:8006", "token": "{{HOMEPAGE_VAR_PROXMOX_USER}}",
                             "secret": "{{HOMEPAGE_VAR_PROXMOX_PASS}}"}},
    "favicon.svg": "<svg/>\n",
    "docker.yaml": "",
    "custom.js": "",
    "custom.css": ".service-card{}\n",
    "kubernetes.yaml": {"mode": "cluster"},
    "settings.yaml": {"title": "T", "hideErrors": True, "providers": {"finnhub": "{{HOMEPAGE_VAR_FINNHUB_KEY}}"},
                      "layout": {"G": {"tab": "Main"}}},
    "widgets.yaml": [{"customapi": {"url": PROM, "mappings": []}},
                     {"search": {"provider": "custom", "url": "https://search.example/search?q="}}],
    "services.yaml": [{"G": [
        {"T": {"id": "t", "href": "https://t.example", "siteMonitor": "http://t.media:80/ping",
               "namespace": "media", "app": "t", "podSelector": "x", "proxmoxNode": "pve", "proxmoxVMID": 1,
               "widgets": [{"type": "sonarr", "url": "http://sonarr.media:8989", "key": "{{HOMEPAGE_VAR_SONARR_KEY}}"},
                           {"type": "calendar", "integrations": [{"type": "ical", "name": "TV", "url": ICAL}]}]}},
        {"Sub": [{"U": {"id": "u", "widget": {"type": "x", "url": "https://10.9.9.20:8006"}}}]},
    ]}],
    "bookmarks.yaml": [{"L": [{"BM": [{"id": "bm", "href": "https://bm.example"}]}]}],
}

INV = {
    "tabs": [{"name": "A", "slug": "a"}, {"name": "B", "slug": "b"}],
    "groups": [{"name": "G", "tab": "A", "parents": []}, {"name": "H", "tab": "B", "parents": []},
               {"name": "L", "tab": "B", "parents": []}],
    "tiles": [{"id": "x", "name": "X", "group": "G", "href": None, "widgets": []},
              {"id": "y", "name": "Y", "group": "H", "href": None, "widgets": []}],
    "bookmarks": [{"id": "bm", "name": "BM", "group": "L", "href": "https://bm.example"}],
    "info": [],
}


def run(tab, ids, groups, **kw):
    return {"tab": tab, "viewport": "390x844", "scenario": "calm", "ok": True, "ids": ids, "groups": groups,
            "errors": 0, "missing": [], "small": [], "selectors": {}, **kw}


def good():
    return [run("A", ["x"], ["G"]), run("B", ["y", "bm"], ["H", "L"])]


class SlugTests(unittest.TestCase):
    def test_mock_slug(self):
        self.assertEqual(mock_slug("http://sonarr.media:8989/x"), "sonarr-media-8989")
        self.assertEqual(mock_slug("https://10.9.9.20:8006/api2"), "10-9-9-20-8006")
        self.assertEqual(mock_slug("https://api.github.com/search/issues?q=a"), "api-github-com")


class BuildConfigTests(unittest.TestCase):
    def test_build_config_rewrites(self):
        before = copy.deepcopy(DATA)
        out = build_config(DATA, set())
        self.assertEqual(DATA, before)  # the generator's data is not mutated
        self.assertEqual(set(out), set(DATA))
        self.assertTrue(all(isinstance(v, str) for v in out.values()))
        self.assertNotIn("HOMEPAGE_VAR", "".join(out.values()))
        group = yaml.safe_load(out["services.yaml"])[0]["G"]
        tile = group[0]["T"]
        self.assertEqual(tile["siteMonitor"], "http://mock:8080/up/t")
        self.assertEqual(tile["href"], "https://t.example")
        for key in ("namespace", "app", "podSelector", "proxmoxNode", "proxmoxVMID"):
            self.assertNotIn(key, tile)
        self.assertEqual(tile["widgets"][0], {"type": "sonarr", "url": "http://mock:8080/sonarr-media-8989",
                                              "key": "mock"})
        self.assertEqual(tile["widgets"][1]["integrations"][0]["url"],
                         "http://mock:8080/sonarr-media-8989/feed/v3/calendar/Sonarr.ics?apikey=mock&pastDays=30")
        self.assertEqual(group[1]["Sub"][0]["U"]["widget"]["url"], "http://mock:8080/10-9-9-20-8006")
        info = yaml.safe_load(out["widgets.yaml"])
        self.assertEqual(info[0]["customapi"]["url"],
                         "http://mock:8080/prom-monitoring-9090/api/v1/query?query=min(x%7Ba%3D%221%22%7D)")
        self.assertEqual(info[1]["search"]["url"], "https://search.example/search?q=")  # the browser's, not the pod's
        settings = yaml.safe_load(out["settings.yaml"])
        self.assertIs(settings["hideErrors"], False)
        self.assertIs(settings["disableUpdateCheck"], True)
        self.assertEqual(settings["providers"], {"finnhub": "mock"})
        self.assertEqual(settings["layout"], {"G": {"tab": "Main"}})
        self.assertEqual(yaml.safe_load(out["kubernetes.yaml"]), {"mode": "disabled"})
        self.assertEqual(yaml.safe_load(out["proxmox.yaml"]),
                         {"pve": {"url": "http://mock:8080/10-9-9-20-8006", "token": "mock", "secret": "mock"}})
        self.assertEqual(out["favicon.svg"], "<svg/>\n")
        self.assertEqual(out["custom.css"], ".service-card{}\n")
        self.assertEqual(yaml.safe_load(out["bookmarks.yaml"]), DATA["bookmarks.yaml"])

    def test_truenas_uses_the_rest_api(self):
        data = copy.deepcopy(DATA)
        tile = data["services.yaml"][0]["G"][0]["T"]
        tile["widgets"] = [{"type": "truenas", "version": 2, "url": "https://10.9.9.30", "enablePools": True},
                           {"type": "jellyfin", "version": 2, "url": "http://jellyfin-main.media:8096"}]
        widgets = yaml.safe_load(build_config(data, set())["services.yaml"])[0]["G"][0]["T"]["widgets"]
        self.assertEqual(widgets[0], {"type": "truenas", "url": "http://mock:8080/10-9-9-30", "enablePools": True})
        self.assertEqual(widgets[1]["version"], 2)  # only TrueNAS: its version 2 is a websocket the mock lacks

    def test_down_tiles(self):
        tile = yaml.safe_load(build_config(DATA, {"t"})["services.yaml"])[0]["G"][0]["T"]
        self.assertEqual(tile["siteMonitor"], "http://mock:8080/down/t")


class FailureTests(unittest.TestCase):
    def test_good_runs_pass(self):
        self.assertEqual(failures(INV, good(), "household"), [])

    def test_failures_missing_tile(self):
        lines = failures(INV, [run("A", [], ["G"]), good()[1]], "household")
        self.assertEqual(len(lines), 1)
        self.assertRegex(lines[0], r"household A 390x844 calm: .*\bx\b")

    def test_failures_missing_bookmark_and_group(self):
        lines = failures(INV, [good()[0], run("B", ["y"], ["H"])], "household")
        self.assertEqual(len(lines), 2)
        self.assertRegex("\n".join(lines), r"\bbm\b")
        self.assertRegex("\n".join(lines), r"group L")

    def test_failures_wrong_tab(self):
        lines = failures(INV, [run("A", [], ["G"]), run("B", ["x", "y", "bm"], ["H", "L"])], "household")
        self.assertRegex("\n".join(lines), r"household A .*\bx\b.* missing")
        self.assertRegex("\n".join(lines), r"household B .*\bx\b.* belongs to tab A")

    def test_failures_tab_never_rendered(self):
        self.assertRegex("\n".join(failures(INV, [good()[0]], "household")), r"tab B was never rendered")

    def test_failures_selector_union(self):
        runs = good() + [dict(run("A", ["x"], ["G"]), viewport="1440x900")]
        runs[0]["selectors"] = {".a": False, ".b": False, ".c": False}
        runs[2]["selectors"] = {".a": True, ".b": False, ".c": False}
        with mock.patch.dict(render_check.SELECTOR_ALLOW, {".c": "a state the mock cannot make"}):
            lines = failures(INV, runs, "household")
        self.assertEqual(len(lines), 1)
        self.assertRegex(lines[0], r"household: custom\.css selector matches nothing: \.b$")

    def test_failures_error_box(self):
        runs = good()
        runs[1].update(errors=1, scenario="alarm")
        lines = failures(INV, runs, "admin")
        self.assertEqual(len(lines), 1)
        self.assertRegex(lines[0], r"admin B 390x844 alarm: 1 widget error")

    def test_failures_missing_image(self):
        runs = good()
        runs[0]["missing"] = ["/images/aurora-still.svg"]
        self.assertRegex("\n".join(failures(INV, runs, "household")), r"/images/aurora-still\.svg")

    def test_failures_small_target(self):
        runs = good()
        runs[0]["small"] = ["a 30x30"]
        self.assertRegex("\n".join(failures(INV, runs, "household")), r"a 30x30")
        self.assertEqual(failures(INV, runs, "admin"), [])  # admin at 390 px is not a target
        runs[0]["viewport"] = "1440x900"
        self.assertEqual(failures(INV, runs, "household"), [])
        runs[0]["viewport"] = "390x844"
        with mock.patch.dict(render_check.SMALL_ALLOW, {"a 30x30": "Homepage's own control"}):
            self.assertEqual(failures(INV, runs, "household"), [])

    def test_failures_config_error_panel(self):
        runs = good()
        runs[0]["ok"] = False
        lines = failures(INV, runs, "household")
        self.assertEqual(len(lines), 1)  # nothing else is reported for a page that did not render
        self.assertRegex(lines[0], r"household A 390x844 calm: the dashboard did not render")


if __name__ == "__main__":
    unittest.main()
