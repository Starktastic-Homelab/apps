import contextlib
import io
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import generate
from compare import diff, facts, parse_configmap
from generate import main, output_path, render_all
from test_output import Base

SETTINGS = "title: T\nlayout:\n  G:\n    tab: Main\n"
SERVICES = """- G:
    - A:
        id: x1
        href: https://a
        description: d
        widget:
          type: sonarr
          key: {{ "{{" }}HOMEPAGE_VAR_K{{ "}}" }}
    - Sub:
        - B:
            href: https://b
"""
BOOKMARKS = "- L:\n    - GH:\n        - abbr: GH\n          href: https://gh\n"
INFO = "- logo:\n    icon: x\n- search:\n    url: y\n"


def cm(services=SERVICES, settings=SETTINGS, bookmarks=BOOKMARKS, info=INFO):
    ind = lambda t: "".join("    " + l + "\n" for l in t.splitlines())
    return ("apiVersion: v1\nkind: ConfigMap\ndata:\n  settings.yaml: |\n" + ind(settings)
            + "  services.yaml: |\n" + ind(services) + "  bookmarks.yaml: |\n" + ind(bookmarks)
            + "  widgets.yaml: |\n" + ind(info))


def F(**kw):
    return facts(parse_configmap(cm(**kw)))


class TestCompare(unittest.TestCase):
    def test_equal_ignores_ids_quotes_anchors(self):
        base = SERVICES.replace("          key:", "          highlight: v\n          key:")
        other = base.replace("x1", "zz").replace("https://a", '"https://a"')
        other = "# c\n" + other.replace("highlight: v", "highlight: &q v").replace(
            "            href: https://b", "            href: https://b\n            description: *q")
        base = base.replace("            href: https://b", "            href: https://b\n            description: v")
        self.assertEqual(diff(F(services=base), F(services=other), "p"), [])

    def test_info_order_and_duplicate_names(self):
        swapped = "- search:\n    url: y\n- logo:\n    icon: x\n"
        self.assertEqual(len(diff(F(), F(info=swapped), "p")), 1)
        with self.assertRaisesRegex(Exception, "duplicate tile name 'A'"):
            F(services=SERVICES + "    - A:\n        href: z\n")

    def test_detects_each_fact(self):
        self.assertEqual(F()["tiles"]["B"]["group"], "Sub")
        self.assertEqual(F()["tiles"]["B"]["tab"], "Main")
        cases = {
            "tab": dict(settings=SETTINGS.replace("Main", "Other")),
            "group": dict(services=SERVICES.replace("- G:", "- H:")),
            "index": dict(services=SERVICES.replace("    - A:", "    - Z:\n        href: z\n    - A:")),
            "href": dict(services=SERVICES.replace("https://a", "https://c")),
            "siteMonitor": dict(services=SERVICES.replace("href: https://a", "href: https://a\n        siteMonitor: http://m")),
            "namespace": dict(services=SERVICES.replace("description: d", "description: d\n        namespace: n")),
            "app": dict(services=SERVICES.replace("description: d", "description: d\n        app: n")),
            "description": dict(services=SERVICES.replace("description: d", "description: e")),
            "widgets": dict(services=SERVICES.replace("type: sonarr", "type: radarr")),
            "placeholders": dict(services=SERVICES.replace("HOMEPAGE_VAR_K", "HOMEPAGE_VAR_J")),
        }
        for field, kw in cases.items():
            with self.subTest(field=field):
                out = diff(F(), F(**kw), "p")
                self.assertTrue(any(l.startswith("p: tile ") and f" {field}: live=" in l for l in out), out)
        self.assertEqual(diff(F(), F(services=SERVICES + "        - C:\n            href: c\n"), "p"),
                         ["p: tile C: only in staged"])
        self.assertEqual(diff(F(), F(bookmarks=BOOKMARKS.replace("https://gh", "https://x")), "p"),
                         ["p: bookmark GH: href: live=https://gh staged=https://x"])
        self.assertEqual(len(diff(F(), F(info=INFO.replace("search", "greeting")), "p")), 1)

    def test_duplicate_bookmark_and_missing_data(self):
        two = BOOKMARKS + "- M:\n    - GH:\n        - href: https://x\n"
        with self.assertRaisesRegex(Exception, "duplicate bookmark name 'GH'"):
            F(bookmarks=two)
        with self.assertRaisesRegex(Exception, "no data"):
            parse_configmap("apiVersion: v1\nkind: ConfigMap\n")

    def test_bad_yaml_names_key(self):
        with self.assertRaisesRegex(Exception, "services.yaml"):
            parse_configmap(cm(services="- a: [\n"))


class TestCli(Base):
    def test_cli_compare(self):
        repo = self.repo()
        for path, text in render_all(repo).items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(text.encode())
        for page in generate.STAGED:
            live = Path(repo) / f"{generate.PAGES[page]['dir']}/manifests/templates/configmap.yaml"
            live.write_bytes(output_path(repo, page).read_bytes())
        self.assertEqual(main(["--compare"], repo), 0)
        staged = output_path(repo, "household")
        staged.write_text(re.sub(r"(?m)^(\s+href: .*)$", r"\1x", staged.read_text()))
        err = io.StringIO()
        with contextlib.redirect_stdout(err):
            self.assertEqual(main(["--compare"], repo), 1)
        self.assertIn("household: tile A: href", err.getvalue())
        # strict: live-only edits beyond the facts, in data and in raw keys, fail
        live = Path(repo) / f"{generate.PAGES['admin']['dir']}/manifests/templates/configmap.yaml"
        good = live.read_text()
        for old, new, rx in (("      - A:\n          id: a\n", "      - A:\n          id: a\n          icon: x.png\n",
                              r"admin: services.yaml: differs"),
                             ("      G:\n", "      G:\n        columns: 9\n", r"admin: settings.yaml: differs"),
                             ('custom.css: ""', 'custom.css: "a{}"', r"admin: custom.css: live and staged differ")):
            with self.subTest(new=new):
                self.assertIn(old, good)
                live.write_text(good.replace(old, new, 1))
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    self.assertEqual(main(["--compare"], repo), 1)
                self.assertRegex(out.getvalue(), rx)
        live.write_text(good)
        output_path(repo, "household").unlink()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["--compare"], repo), 1)
        old = generate.STAGED
        generate.STAGED = set()
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["--compare"], repo), 0)
        finally:
            generate.STAGED = old
