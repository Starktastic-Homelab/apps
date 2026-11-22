import ast
import base64
import json
import os
import sqlite3
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

T = "infrastructure/base-configs/templates/"
GUARDS = {"jellyfin": T + "media-block-storage/guard-configmap.yaml",
          "filebrowser": T + "operations-home-block-storage/guard-operations.yaml"}
SQLITE = b"SQLite format 3\0" + b"\0" * 84
# an existing app of each guard, to pin that its marker is still required
OTHER = {"jellyfin": ("sonarr", {"sonarr.db": SQLITE, "logs.db": SQLITE, "config.xml": b"<Config/>"}),
         "filebrowser": ("bytestash", {"snippets.db": SQLITE})}
ROOT = Path(__file__).resolve().parents[3]


def marker(app):
    return {f".homelab-{app}-data": f"homelab/{app}/data/v1\n".encode()}


def run_guard(configmap, app, root):
    data = yaml.safe_load((ROOT / GUARDS[configmap]).read_text())["data"]
    with tempfile.TemporaryDirectory() as d:
        for name, text in data.items():
            Path(d, name).write_text(text)
        return subprocess.run([sys.executable, "-I", "-B", str(Path(d, "guard.py")), app, str(root)],
                              capture_output=True, text=True)


class Guards(unittest.TestCase):
    def tree(self, files):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        for rel, content in files.items():
            p = Path(d.name, rel)
            if content is None:
                p.mkdir(parents=True, exist_ok=True)
            else:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(content)
        return d.name

    def each(self, fn):
        for app in GUARDS:
            with self.subTest(app=app):
                fn(app)

    def accepts(self, configmap, root, app=None):
        r = run_guard(configmap, app or configmap, root)
        self.assertEqual(r.returncode, 0, r.stderr)

    def refuses(self, configmap, root, app=None):
        r = run_guard(configmap, app or configmap, root)
        self.assertEqual(r.returncode, 1)
        self.assertIn("refused; recovery acceptance is required.", r.stderr)  # a deliberate refusal, not a crash

    def test_accepts_marker_alone(self):
        # marker-only: no native files are required (Ben, 2026-11-22)
        self.each(lambda a: self.accepts(a, self.tree(marker(a))))

    def test_refuses_missing_or_wrong_marker(self):
        def check(a):
            self.refuses(a, self.tree({"data/": None}))
            self.refuses(a, self.tree({f".homelab-{a}-data": b"homelab/other/data/v1\n"}))
            self.refuses(a, self.tree({f".homelab-{a}-data": b""}))
        self.each(check)

    def test_refuses_blank_filesystem(self):
        self.each(lambda a: self.refuses(a, self.tree({"lost+found/": None})))

    def test_refuses_symlinked_marker(self):
        def check(a):
            outside = Path(self.tree(marker(a)), f".homelab-{a}-data")
            root = Path(self.tree({"lost+found/": None}))
            os.symlink(outside, root / f".homelab-{a}-data")
            self.refuses(a, root)
        self.each(check)

    def test_other_apps_keep_their_marker(self):
        def check(a):
            other, files = OTHER[a]
            self.refuses(a, self.tree(files), other)
            self.accepts(a, self.tree({**files, **marker(other)}), other)
        self.each(check)



# Retained block-volume guards after the marker-only decision (Ben, 2026-11-22):
# pure-layout apps need only the marker; content checks still bind.
UTILITY = "utility-home-block-storage/"
OPS = "operations-home-block-storage/"
SHARED = {  # script: (refusal message, marker-only apps, apps that need more than the marker)
    "media-block-storage/guard-configmap.yaml": (
        "Retained media state refused; recovery acceptance is required.",
        ("sonarr", "sonarr-ru", "radarr", "radarr-ru", "lidarr", "navidrome", "audiobookshelf",
         "shelfmark", "jellyfin"), ("cleanuparr", "cineplete")),
    "monitoring-block-storage/guard-configmap.yaml": (
        "Retained monitoring state refused; recovery acceptance is required.",
        ("alertmanager", "prometheus", "loki", "tempo"), ()),
    OPS + "guard-operations.yaml": (
        "Retained application state refused; recovery acceptance is required.",
        ("karakeep", "karakeep-meilisearch", "bytestash", "convertx", "filebrowser", "home-assistant",
         "home-assistant-matter"), ()),
    OPS + "guard-home-automation.yaml": (
        "Retained application state refused; recovery acceptance is required.",
        ("karakeep", "karakeep-meilisearch", "bytestash", "convertx", "home-assistant",
         "home-assistant-matter"), ()),
    **{UTILITY + name: (
        "Retained utility state refused; verified recovery is required.",
        ("microbin", "lingarr"),
        ("qbittorrent", "qbittorrent-ru", "stirling-pdf", "mosquitto", "zigbee2mqtt", "changedetection"))
       for name in ("guard-media.yaml", "guard-operations.yaml", "guard-home-automation.yaml")},
}
MOSQUITTO = (b"\x00\xb5\x00mosquitto db" + b"\0" * 4 + (6).to_bytes(4, "big")
             + struct.pack("!II", 1, 16) + bytes(9) + b"\x08" + bytes(6))
QBIT = {"qBittorrent/qBittorrent.conf": b"[BitTorrent]\n", "qBittorrent/categories.json": b"{}"}
# only the files the remaining content checks read
CONTENT = {
    "qbittorrent": QBIT, "qbittorrent-ru": QBIT,
    "stirling-pdf": {"stirling-pdf-DB-2.3.232.mv.db": b"H:2,block:0"},
    "mosquitto": {"mosquitto.db": MOSQUITTO},
    "zigbee2mqtt": {"database.db": b'{"id": 1}\n', "state.json": b"{}", "coordinator_backup.json": json.dumps(
        {"metadata": {"format": "zigpy/open-coordinator-backup", "version": 1}}).encode()},
}
PER_APP = {  # script: (key, refusal message)
    "services/media/autobrr/manifests/retained-startup-guard.yaml": (
        "guard.py", "Retained Autobrr state is missing or invalid; restore acceptance is required."),
    "services/media/calibre-web/manifests/retained-startup-guard.yaml": (
        "guard.py", "Retained CWA identity/native state refused; recovery acceptance is required."),
    "services/operations/paperless-ngx/manifests/retained-startup-guard.yaml": (
        "guard.py", "Retained Paperless data refused; recovery acceptance is required."),
    "infrastructure/controllers/databases/redis/manifests/retained-startup.yaml": (
        "guard.sh", "Retained Redis startup refused: identity/integrity check failed."),
    "infrastructure/controllers/databases/postgres/manifests/retained-startup-guard.yaml": (
        "guard.sh", "Retained PostgreSQL startup refused: data identity validation failed."),
    "services/media/immich/manifests/retained-startup.yaml": (
        "guard.sh", "Retained Immich PostgreSQL startup refused: identity check failed."),
}


def configmap_data(path):
    return yaml.safe_load((ROOT / path).read_text())["data"]


def run_script(path, args, env=None):
    data = configmap_data(path)
    with tempfile.TemporaryDirectory() as d:
        for name, text in data.items():
            Path(d, name).write_text(text)
        cmd = ([sys.executable, "-I", "-B", str(Path(d, "guard.py"))] if "guard.py" in data
               else ["/bin/bash", str(Path(d, "guard.sh"))])
        return subprocess.run(cmd + [str(a) for a in args], capture_output=True, text=True,
                              env=env if env is not None else {"PATH": os.environ["PATH"]})


class RetainedGuards(unittest.TestCase):
    tree = Guards.tree

    def ok(self, path, args):
        r = run_script(path, args)
        self.assertEqual(r.returncode, 0, r.stderr)

    def no(self, path, args, message):
        r = run_script(path, args)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(message, r.stderr)

    def test_shared_marker_only_apps(self):
        for path, (message, pure, _) in SHARED.items():
            for app in pure:
                with self.subTest(script=path, app=app):
                    self.ok(T + path, [app, self.tree(marker(app))])
                    self.no(T + path, [app, self.tree({"lost+found/": None})], message)
                    self.no(T + path, [app, self.tree({f".homelab-{app}-data": b"homelab/other/data/v1\n"})],
                            message)

    def test_shared_content_apps_need_more_than_marker(self):
        for path, (message, _, content) in SHARED.items():
            for app in content:
                with self.subTest(script=path, app=app):
                    self.no(T + path, [app, self.tree(marker(app))], message)

    def test_utility_content_checks_alone_suffice(self):
        for path, (message, _, content) in SHARED.items():
            for app in set(content) & set(CONTENT):
                with self.subTest(script=path, app=app):
                    self.ok(T + path, [app, self.tree({**marker(app), **CONTENT[app]})])
                    self.no(T + path, [app, self.tree(CONTENT[app])], message)

    def test_unlisted_marker_only_app_accepted(self):
        for path, (message, _, _) in SHARED.items():
            with self.subTest(script=path):
                self.ok(T + path, ["newapp", self.tree(marker("newapp"))])
                self.no(T + path, ["newapp", self.tree({"lost+found/": None})], message)
                self.no(T + path, ["newapp", self.tree({".homelab-newapp-data": b"homelab/other/data/v1\n"})],
                        message)

    def test_refuses_unsafe_app_name(self):
        for path, (message, _, _) in SHARED.items():
            for app in ("", "../x", "a/b", "A", "-x", "x-", "x" * 64, "a\n"):
                with self.subTest(script=path, app=app):
                    files = {} if "/" in app else {f".homelab-{app}-data": f"homelab/{app}/data/v1\n".encode()}
                    self.no(T + path, [app, self.tree(files)], message)

    def test_group_guards_list_only_apps_with_checks(self):
        def full(node):
            return isinstance(node, (tuple, list)) and any(full(i) if isinstance(i, (tuple, list)) else True for i in node)
        for path in SHARED:
            for name, source in configmap_data(T + path).items():
                if not name.endswith(".py"):
                    continue
                tree = ast.parse(source)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Assign) and any(
                            getattr(t, "id", getattr(t, "attr", None)) == "LAYOUTS" for t in node.targets):
                        with self.subTest(script=path, file=name):
                            self.assertTrue(all(full(v) for v in ast.literal_eval(node.value).values()))
                    if name == "base.py" and isinstance(node, ast.Compare):
                        self.assertNotIn("app", [getattr(n, "id", None) for n in [node.left, *node.comparators]],
                                         path)
                if name == "base.py":
                    self.assertNotIn("LAYOUTS", source, path)

    def test_per_app_scripts_parse_and_refuse_blank_tree(self):
        for path, (key, message) in PER_APP.items():
            with self.subTest(script=path):
                source = configmap_data(path)[key]
                if key == "guard.py":
                    compile(source, path, "exec")
                else:
                    r = subprocess.run(["/bin/bash", "-n"], input=source, capture_output=True, text=True)
                    self.assertEqual(r.returncode, 0, r.stderr)
                # bash guards read fixed in-container paths and tools: locally this only proves refusal
                self.no(path, [self.tree({"lost+found/": None})], message)

    def test_autobrr_content(self):
        path = next(p for p in PER_APP if "autobrr" in p)
        message = PER_APP[path][1]
        files = {".homelab-autobrr-config": b"homelab/autobrr/config/v1\n", "config.toml": b'sessionSecret = "s"\n'}
        self.no(path, [self.tree(files)], message)
        root = self.tree(files)
        with sqlite3.connect(Path(root, "autobrr.db")) as db:
            for table in ("indexer", "irc_network", "filter", "action", "client", "release_profile_duplicate"):
                db.execute(f"CREATE TABLE {table} (id INTEGER)")
        db.close()
        self.ok(path, [root])
        self.no(path, [self.tree({**files, "autobrr.db": SQLITE})], message)

    def test_calibre_web_content(self):
        path = next(p for p in PER_APP if "calibre" in p)
        message = PER_APP[path][1]
        files = {**marker("calibre-web"), "config/.key": base64.urlsafe_b64encode(bytes(32))}
        self.ok(path, [self.tree(files)])
        self.no(path, [self.tree(marker("calibre-web"))], message)
        self.no(path, [self.tree({**files, "config/.key": b"x" * 44})], message)

    def test_paperless_content(self):
        path = next(p for p in PER_APP if "paperless" in p)
        message = PER_APP[path][1]
        segment = "0123abcd-0000-0000-0000-0123456789ab"
        files = {
            ".homelab-paperless-data": b"homelab/paperless/data/v1\n", ".index_version": b"7\n",
            "index/.index_settings.json": json.dumps({"schema_version": 1, "language": "en"}).encode(),
            "index/meta.json": json.dumps({"schema": [{"name": "id"}, {"name": "content"}], "opstamp": 3,
                                           "segments": [{"segment_id": segment, "max_doc": 2}]}).encode()}
        self.ok(path, [self.tree(files)])
        self.no(path, [self.tree({".homelab-paperless-data": files[".homelab-paperless-data"]})], message)
        self.no(path, [self.tree({**files, ".index_version": b"0"})], message)
        bad = json.dumps({"schema": [], "opstamp": 3, "segments": []}).encode()
        self.no(path, [self.tree({**files, "index/meta.json": bad})], message)


if __name__ == "__main__":
    unittest.main()
