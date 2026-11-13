import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fixture
from catalog import CatalogError, derive, resolve_tile

SONARR = {"name": "sonarr", "namespace": "media", "ingress": {"enabled": True, "host": "sonarr", "port": 8989}}
SRC = "services/media/sonarr"


class DeriveTests(unittest.TestCase):
    def repo(self, apps):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        return fixture.make_repo(Path(d.name), fixture.MIN_CATALOG, apps=apps)

    def test_rule03_derive_basic(self):
        got = derive(self.repo({SRC: SONARR}), SRC)
        self.assertEqual(got, {"href": "https://sonarr.internal.starktastic.net",
                               "siteMonitor": "http://sonarr.media:8989", "namespace": "media", "app": "sonarr"})

    def test_rule03_domain_and_service(self):
        app = {"name": "benplus", "namespace": "ns", "ingress": {"enabled": True, "domainType": "media", "serviceName": "web"}}
        got = derive(self.repo({"services/x/benplus": app}), "services/x/benplus")
        self.assertEqual(got["href"], "https://benplus.app")
        self.assertEqual(got["siteMonitor"], "http://web.ns:80")

    def test_rule03_variant_merge(self):
        ru = {"name": "sonarr-ru", "baseApp": SRC, "namespace": "media", "ingress": {"enabled": True, "host": "sonarr-ru"}}
        got = derive(self.repo({SRC: SONARR, "services/media/sonarr-ru": ru}), "services/media/sonarr-ru")
        self.assertEqual(got["siteMonitor"], "http://sonarr-ru.media:8989")
        self.assertEqual(got["app"], "sonarr-ru")

    def test_rule04_explicit_equal_fails(self):
        repo = self.repo({SRC: SONARR})
        with self.assertRaisesRegex(CatalogError, r"tiles\.s\.href:"):
            resolve_tile(repo, "s", {"name": "S", "source": SRC, "href": "https://sonarr.internal.starktastic.net"})

    def test_rule04_null_drops_and_explicit_wins(self):
        repo = self.repo({SRC: SONARR})
        t = resolve_tile(repo, "s", {"name": "S", "source": SRC, "siteMonitor": None, "app": "grafana"})
        self.assertNotIn("siteMonitor", t)
        self.assertEqual(t["app"], "grafana")
        self.assertEqual(t["source"], SRC)
        t = resolve_tile(repo, "s", {"name": "S", "source": SRC, "monitorPath": "/ping"})
        self.assertEqual(t["siteMonitor"], "http://sonarr.media:8989/ping")

    def test_rule04_no_ingress_fails(self):
        app = dict(SONARR, ingress={"enabled": False})
        with self.assertRaisesRegex(CatalogError, r"tiles\.s\.source:"):
            resolve_tile(self.repo({SRC: app}), "s", {"name": "S", "source": SRC})

    def test_variant_without_own_enabled_fails(self):
        ru = {"name": "sonarr-ru", "baseApp": SRC, "namespace": "media", "ingress": {"host": "sonarr-ru"}}
        repo = self.repo({SRC: SONARR, "services/media/sonarr-ru": ru})
        with self.assertRaisesRegex(CatalogError, "own app.yaml"):
            derive(repo, "services/media/sonarr-ru")

    def test_malformed_app_raises_catalog_error(self):
        bad = {"unk": dict(SONARR, ingress={"enabled": True, "domainType": "nope"}),
               "noname": {"namespace": "m", "ingress": {"enabled": True}},
               "nons": {"name": "n", "ingress": {"enabled": True}}}
        repo = self.repo({f"services/x/{k}": v for k, v in bad.items()})
        for k in bad:
            with self.subTest(k), self.assertRaises(CatalogError):
                derive(repo, f"services/x/{k}")
        (repo / "services/x/list").mkdir()
        (repo / "services/x/list/app.yaml").write_text("- a\n")
        with self.assertRaisesRegex(CatalogError, "not a mapping"):
            derive(repo, "services/x/list")

    def test_null_port_defaults(self):
        app = dict(SONARR, ingress={"enabled": True, "host": "s", "port": None})
        self.assertEqual(derive(self.repo({SRC: app}), SRC)["siteMonitor"], "http://sonarr.media:80")

    def test_missing_globals_domains(self):
        repo = self.repo({SRC: SONARR})
        (repo / "templates/globals.yaml").write_text("global: {}\n")
        with self.assertRaisesRegex(CatalogError, "global.domains"):
            derive(repo, SRC)

    def test_missing_source_fails(self):
        with self.assertRaisesRegex(CatalogError, r"tiles\.s\.source:"):
            resolve_tile(self.repo({}), "s", {"name": "S", "source": SRC})


if __name__ == "__main__":
    unittest.main()
