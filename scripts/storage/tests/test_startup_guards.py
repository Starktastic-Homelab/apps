import ast
import base64
import glob
import json
import os
import re
import sqlite3
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
GENERIC = "infrastructure/base-configs/files/retained-startup/guard.py"
TEMPLATES = "infrastructure/base-configs/templates/"
GENERIC_MESSAGE = "Retained state refused; recovery acceptance is required."
SQLITE = b"SQLite format 3\0" + b"\0" * 84
# apps the group guards serve today, plus two not yet wired (jellyfin, filebrowser) and an unlisted one
MARKER_ONLY = ("sonarr", "sonarr-ru", "radarr", "radarr-ru", "lidarr", "navidrome", "audiobookshelf", "shelfmark",
               "jellyfin", "alertmanager", "prometheus", "loki", "tempo", "karakeep", "karakeep-meilisearch",
               "bytestash", "convertx", "filebrowser", "home-assistant", "home-assistant-matter", "microbin",
               "lingarr", "newapp")
UNSAFE = ("", "../x", "a/b", "A", "-x", "x-", "x" * 64, "a\n")


def marker(app):
    return {f".homelab-{app}-data": f"homelab/{app}/data/v1\n".encode()}


def run_script(path, args, env=None):
    path = ROOT / path
    cmd = [sys.executable, "-I", "-B", str(path)] if path.suffix == ".py" else ["/bin/bash", str(path)]
    return subprocess.run(cmd + [str(a) for a in args], capture_output=True, text=True,
                          env=env if env is not None else {"PATH": os.environ["PATH"]})


class Base(unittest.TestCase):
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

    def ok(self, path, args, env=None):
        r = run_script(path, args, env)
        self.assertEqual(r.returncode, 0, r.stderr)

    def no(self, path, args, message, env=None):
        r = run_script(path, args, env)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(message, r.stderr)  # a deliberate refusal, not a crash


class GenericGuard(Base):
    """The one marker-only guard every group ConfigMap in base-configs serves (Ben, 2026-11-22)."""

    def accepts(self, app, root):
        self.ok(GENERIC, [app, root])

    def refuses(self, app, root):
        self.no(GENERIC, [app, root], GENERIC_MESSAGE)

    def test_accepts_marker_alone_for_any_name(self):
        for app in MARKER_ONLY:
            with self.subTest(app=app):
                self.accepts(app, self.tree(marker(app)))

    def test_refuses_missing_wrong_empty_or_oversized_marker(self):
        for app in MARKER_ONLY:
            with self.subTest(app=app):
                self.refuses(app, self.tree({"lost+found/": None}))
                self.refuses(app, self.tree({f".homelab-{app}-data": b"homelab/other/data/v1\n"}))
                self.refuses(app, self.tree({f".homelab-{app}-data": b""}))
                self.refuses(app, self.tree({f".homelab-{app}-data": marker(app)[f".homelab-{app}-data"] + b"x" * 128}))
                self.refuses(app, self.tree({f".homelab-{app}-data/": None}))

    def test_refuses_symlinked_marker_or_root(self):
        outside = Path(self.tree(marker("sonarr")), ".homelab-sonarr-data")
        root = Path(self.tree({"lost+found/": None}))
        os.symlink(outside, root / ".homelab-sonarr-data")
        self.refuses("sonarr", root)
        link = Path(self.tree({}), "root")
        os.symlink(outside.parent, link)
        self.refuses("sonarr", link)

    def test_other_apps_keep_their_marker(self):
        self.refuses("sonarr", self.tree(marker("radarr")))

    def test_refuses_unsafe_app_name(self):
        for app in UNSAFE:
            with self.subTest(app=app):
                files = {f".homelab-{app}-data": f"homelab/{app}/data/v1\n".encode()}  # "/" names plant nested markers
                self.refuses(app, self.tree(files))

    def test_refuses_wrong_argument_count(self):
        root = self.tree(marker("sonarr"))
        self.no(GENERIC, ["sonarr"], GENERIC_MESSAGE)
        self.no(GENERIC, ["sonarr", root, root], GENERIC_MESSAGE)

    def test_base_configs_guards_name_no_app(self):
        names = {Path(p).parent.name for p in glob.glob(str(ROOT / "services/*/*/app.yaml"))
                 + glob.glob(str(ROOT / "infrastructure/*/*/*/app.yaml"))}
        self.assertIn("cleanuparr", names)
        files = [ROOT / GENERIC] + sorted((ROOT / TEMPLATES).glob("*/guard*.yaml"))
        self.assertGreaterEqual(len(files), 7)
        for path in files:
            text = path.read_text()
            with self.subTest(file=str(path.relative_to(ROOT))):
                self.assertNotIn("LAYOUTS", text)
                self.assertEqual([n for n in names if re.search(rf"""['"]{re.escape(n)}['"]""", text)], [])
        for node in ast.walk(ast.parse((ROOT / GENERIC).read_text())):
            if isinstance(node, ast.Compare):
                self.assertNotIn("app", [getattr(n, "id", None) for n in [node.left, *node.comparators]])
            if isinstance(node, ast.Attribute) and node.attr in ("startswith", "endswith"):
                self.assertNotEqual(getattr(node.value, "id", None), "app")

    def test_group_templates_load_the_file(self):
        for path in sorted((ROOT / TEMPLATES).glob("*/guard*.yaml")):
            with self.subTest(file=path.name):
                self.assertIn('guard.py: |{{ .Files.Get "files/retained-startup/guard.py" | nindent 4 }}',
                              path.read_text())


# App-owned guards that check native content as well as the marker
MOSQUITTO = (b"\x00\xb5\x00mosquitto db" + b"\0" * 4 + (6).to_bytes(4, "big")
             + struct.pack("!II", 1, 16) + bytes(9) + b"\x08" + bytes(6))
QBIT = {"qBittorrent/qBittorrent.conf": b"[BitTorrent]\n", "qBittorrent/categories.json": b"{}"}
UTILITY = "verified recovery is required."
CLEANUPARR_ENV = {"PATH": os.environ["PATH"], "DATABASE_PROVIDER": "postgres",
                  "POSTGRES_HOST": "postgres-postgresql.databases", "POSTGRES_PORT": "5432",
                  "POSTGRES_USER": "cleanuparr", "POSTGRES_DB": "cleanuparr", "POSTGRES_PASS": "dummy"}
CONTENT = {  # app: (guard, refusal, argv apps, content files)
    "cleanuparr": ("services/media/cleanuparr/manifests/retained-startup/guard.py",
                   "recovery acceptance is required.", ("cleanuparr",),
                   {"DataProtection-Keys/key-1.xml": b"<key/>", "jwt-key.bin": bytes(32),
                    "plex-client-id.txt": b"id"}),
    "cineplete": ("services/media/cineplete/manifests/retained-startup/guard.py",
                  "recovery acceptance is required.", ("cineplete",),
                  {"config/config.yml": b"a: 1\n", "data/overrides.json": b"{}", "data/results.json": b"{}"}),
    "qbittorrent": ("services/media/qbittorrent/manifests/retained-startup/guard.py", UTILITY,
                    ("qbittorrent", "qbittorrent-ru"), QBIT),
    "changedetection": ("services/operations/changedetection/manifests/retained-startup/guard.py", UTILITY,
                        ("changedetection",), {"changedetection.json": b"{}", "secret.txt": b"s" * 64}),
    "stirling-pdf": ("services/operations/stirling-pdf/manifests/retained-startup/guard.py", UTILITY,
                     ("stirling-pdf",), {"stirling-pdf-DB-2.3.232.mv.db": b"H:2,block:0"}),
    "mosquitto": ("services/home-automation/mosquitto/manifests/retained-startup/guard.py", UTILITY,
                  ("mosquitto",), {"mosquitto.db": MOSQUITTO}),
    "zigbee2mqtt": ("services/home-automation/zigbee2mqtt/manifests/retained-startup/guard.py", UTILITY,
                    ("zigbee2mqtt",), {"database.db": b'{"id": 1}\n', "state.json": b"{}",
                                       "coordinator_backup.json": json.dumps({"metadata": {
                                           "format": "zigpy/open-coordinator-backup", "version": 1}}).encode()}),
}
# a variant mounts its base app's ConfigMap, so it must not mount a group guard either
CONTENT_MOUNTS = {**{app: app for app in CONTENT}, "qbittorrent-ru": "qbittorrent"}


class ContentGuards(Base):
    def each(self, fn):
        for app, (path, message, argv, files) in CONTENT.items():
            env = CLEANUPARR_ENV if app == "cleanuparr" else None
            for name in argv:
                with self.subTest(app=name):
                    fn(path, message, name, files, env)

    def test_marker_and_content_accepted(self):
        self.each(lambda p, m, a, f, e: self.ok(p, [a, self.tree({**marker(a), **f})], e))

    def test_marker_alone_refused(self):
        self.each(lambda p, m, a, f, e: self.no(p, [a, self.tree(marker(a))], m, e))

    def test_content_alone_refused(self):
        self.each(lambda p, m, a, f, e: self.no(p, [a, self.tree(f)], m, e))

    def test_each_content_file_required(self):
        def check(p, m, a, f, e):
            for name in f:
                self.no(p, [a, self.tree({**marker(a), **{k: v for k, v in f.items() if k != name}})], m, e)
        self.each(check)

    def test_foreign_app_refused_even_with_valid_state(self):
        for app, (path, message, argv, files) in CONTENT.items():
            env = CLEANUPARR_ENV if app == "cleanuparr" else None
            for other in ("sonarr", app + "-x", "qbittorrent-rux"):
                with self.subTest(app=app, other=other):
                    self.no(path, [other, self.tree({**marker(other), **files})], message, env)

    def test_refuses_unsafe_app_name(self):
        for app, (path, message, argv, files) in CONTENT.items():
            for name in UNSAFE:
                with self.subTest(app=app, name=name):
                    self.no(path, [name, self.tree({f".homelab-{name}-data": f"homelab/{name}/data/v1\n".encode(),
                                                    **files})], message)

    def test_cleanuparr_backend_and_fallback(self):
        path, message, _, files = CONTENT["cleanuparr"]
        good = {**marker("cleanuparr"), **files}
        self.no(path, ["cleanuparr", self.tree(good)], message, {**CLEANUPARR_ENV, "POSTGRES_HOST": "sqlite"})
        self.no(path, ["cleanuparr", self.tree(good)], message, {**CLEANUPARR_ENV, "POSTGRES_PASS": ""})
        self.no(path, ["cleanuparr", self.tree({**good, "events.db-wal": b"x"})], message, CLEANUPARR_ENV)
        self.no(path, ["cleanuparr", self.tree({**good, "jwt-key.bin": bytes(31)})], message, CLEANUPARR_ENV)

    def test_mosquitto_format(self):
        path, message, _, _ = CONTENT["mosquitto"]
        bad = MOSQUITTO[:19] + (5).to_bytes(4, "big") + MOSQUITTO[23:]
        self.no(path, ["mosquitto", self.tree({**marker("mosquitto"), "mosquitto.db": bad})], message)


# Per-app guards moved from inline ConfigMap keys to files, bytes unchanged
PER_APP = {  # script: refusal message
    "services/media/autobrr/manifests/retained-startup/guard.py":
        "Retained Autobrr state is missing or invalid; restore acceptance is required.",
    "services/media/calibre-web/manifests/retained-startup/guard.py":
        "Retained CWA identity/native state refused; recovery acceptance is required.",
    "services/operations/paperless-ngx/manifests/retained-startup/guard.py":
        "Retained Paperless data refused; recovery acceptance is required.",
    "infrastructure/controllers/databases/redis/manifests/retained-startup/guard.sh":
        "Retained Redis startup refused: identity/integrity check failed.",
    "infrastructure/controllers/databases/postgres/manifests/retained-startup/guard.sh":
        "Retained PostgreSQL startup refused: data identity validation failed.",
    "services/media/immich/manifests/retained-startup/guard.sh":
        "Retained Immich PostgreSQL startup refused: identity check failed.",
}


def retained_folders():
    return sorted(Path(p) for p in glob.glob(str(ROOT / "*/*/*/manifests/retained-startup"))
                  + glob.glob(str(ROOT / "*/*/*/*/manifests/retained-startup")))


class PerAppGuards(Base):
    def test_every_guard_file_parses(self):
        files = [p for d in retained_folders() for p in sorted(d.iterdir())]
        self.assertGreaterEqual(len(files), 25)
        for path in files:
            with self.subTest(file=str(path.relative_to(ROOT))):
                if path.suffix == ".py":
                    compile(path.read_text(), str(path), "exec")
                elif path.suffix == ".sh":
                    r = subprocess.run(["/bin/bash", "-n", str(path)], capture_output=True, text=True)
                    self.assertEqual(r.returncode, 0, r.stderr)

    def test_per_app_scripts_refuse_blank_tree(self):
        for path, message in PER_APP.items():
            with self.subTest(script=path):
                # bash guards read fixed in-container paths and tools: locally this only proves refusal
                self.no(path, [self.tree({"lost+found/": None})], message)

    def test_autobrr_content(self):
        path = next(p for p in PER_APP if "autobrr" in p)
        message = PER_APP[path]
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
        message = PER_APP[path]
        files = {**marker("calibre-web"), "config/.key": base64.urlsafe_b64encode(bytes(32))}
        self.ok(path, [self.tree(files)])
        self.no(path, [self.tree(marker("calibre-web"))], message)
        self.no(path, [self.tree({**files, "config/.key": b"x" * 44})], message)

    def test_paperless_content(self):
        path = next(p for p in PER_APP if "paperless" in p)
        message = PER_APP[path]
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


def load(path):
    return yaml.safe_load(Path(path).read_text()) or {}


def generated(manifests):
    """(namespace, name) -> source files of each ConfigMap a manifests dir's kustomization generates."""
    kust = load(manifests / "kustomization.yaml")
    return {(g.get("namespace", kust.get("namespace")), g["name"]): [f.split("=")[-1] for f in g.get("files", [])]
            for g in kust.get("configMapGenerator", [])}


class Wiring(unittest.TestCase):
    def test_kustomizations_are_complete(self):
        dirs = sorted(Path(p).parent for p in glob.glob(str(ROOT / "*/*/*/manifests/kustomization.yaml"))
                      + glob.glob(str(ROOT / "*/*/*/*/manifests/kustomization.yaml")))
        self.assertGreaterEqual(len(dirs), 22)
        for manifests in dirs:
            with self.subTest(dir=str(manifests.relative_to(ROOT))):
                kust = load(manifests / "kustomization.yaml")
                yamls = {p.name for p in manifests.glob("*.yaml")} - {"kustomization.yaml"}
                self.assertEqual(yamls, set(kust.get("resources", [])))  # an unlisted file is pruned live
                used = {f for files in generated(manifests).values() for f in files}
                guards = {f"retained-startup/{p.name}" for p in (manifests / "retained-startup").glob("*")}
                self.assertLessEqual(guards, used)

    def test_every_retained_startup_folder_is_generated(self):
        folders = retained_folders()
        self.assertGreaterEqual(len(folders), 19)
        for folder in folders:
            manifests = folder.parent
            with self.subTest(dir=str(manifests.relative_to(ROOT))):
                self.assertTrue((manifests / "kustomization.yaml").exists())
                self.assertNotIn("namespace", load(manifests / "kustomization.yaml"))  # set per generator
                self.assertTrue(generated(manifests))
                app = load(manifests.parent / "app.yaml")
                self.assertTrue(app.get("manifests"))
                self.assertNotIn("baseApp", app)  # a variant renders only its own dir: never define the guard twice

    def test_every_mount_resolves_in_its_namespace(self):
        group = set()
        for path in (ROOT / TEMPLATES).glob("*/guard*.yaml"):
            text = path.read_text()
            group.add((re.search(r"^  namespace: (\S+)$", text, re.M)[1], re.search(r"^  name: (\S+)$", text, re.M)[1]))
        self.assertEqual(len(group), 6)
        mounts = {}
        for app_yaml in sorted(glob.glob(str(ROOT / "services/*/*/app.yaml"))
                               + glob.glob(str(ROOT / "infrastructure/*/*/*/app.yaml"))):
            d = Path(app_yaml).parent
            app = load(app_yaml)
            base = ROOT / app["baseApp"] if app.get("baseApp") else None
            layers = ([base / "values.yaml"] + ([d / "values.yaml"] if app.get("valuesOverride") else [])
                      if base else [d / "values.yaml"])
            name = None
            for layer in layers:
                if layer.exists():
                    retained = ((load(layer).get("persistence") or {}).get("retained-startup") or {})
                    name = retained.get("name", name)
            if name is None:
                continue
            owned = {k for o in (d, base) if o and (o / "manifests/kustomization.yaml").exists()
                     for k in generated(o / "manifests")}
            key = (app["namespace"], name)
            mounts[d.name] = key
            with self.subTest(app=d.name, configmap=name):
                self.assertTrue(key in group or key in owned, key)
        self.assertGreaterEqual(len(mounts), 32)
        for app, base in CONTENT_MOUNTS.items():
            with self.subTest(content_app=app):
                self.assertNotIn(mounts[app], group)
                self.assertEqual(mounts[app][1], f"{base}-retained-startup-guard")


if __name__ == "__main__":
    unittest.main()
