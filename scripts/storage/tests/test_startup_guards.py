import os
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
LAYOUT = {"jellyfin": {"system.xml": b"<ServerConfiguration/>", "data/data/jellyfin.db": SQLITE},
          "filebrowser": {"database.sqlite": SQLITE}}
# an existing app of each guard, to pin that its marker is still required
OTHER = {"jellyfin": ("sonarr", {"sonarr.db": SQLITE, "logs.db": SQLITE, "config.xml": b"<Config/>"}),
         "filebrowser": ("bytestash", {"snippets.db": SQLITE})}
ROOT = Path(__file__).resolve().parents[3]


def marker(app):
    return {f".homelab-{app}-data": f"homelab/{app}/data/v1\n".encode()}


def run_guard(app, root) -> int:
    data = yaml.safe_load((ROOT / GUARDS[app.split(":")[0]]).read_text())["data"]
    with tempfile.TemporaryDirectory() as d:
        for name, text in data.items():
            Path(d, name).write_text(text)
        return subprocess.run([sys.executable, "-I", "-B", str(Path(d, "guard.py")), app.split(":")[-1], str(root)],
                              capture_output=True).returncode


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

    def guard(self, app, root, name=None):
        # run_guard keys the ConfigMap on the part before ':'; the app argument is the part after
        return run_guard(f"{app}:{name or app}", root)

    def test_accepts_native_layout(self):
        self.each(lambda a: self.assertEqual(self.guard(a, self.tree({**LAYOUT[a], **marker(a)})), 0))

    def test_refuses_missing_or_wrong_marker(self):
        def check(a):
            self.assertEqual(self.guard(a, self.tree(LAYOUT[a])), 1)
            self.assertEqual(self.guard(a, self.tree({**LAYOUT[a], f".homelab-{a}-data": b"homelab/other/data/v1\n"})), 1)
        self.each(check)

    def test_refuses_blank_filesystem(self):
        self.each(lambda a: self.assertEqual(self.guard(a, self.tree({"lost+found/": None})), 1))

    def test_refuses_each_missing_file(self):
        def check(a):
            for gone in LAYOUT[a]:
                files = {k: v for k, v in LAYOUT[a].items() if k != gone}
                self.assertEqual(self.guard(a, self.tree({**files, **marker(a)})), 1, gone)
        self.each(check)

    def test_refuses_wrong_sqlite_header(self):
        def check(a):
            db = next(k for k in LAYOUT[a] if k.endswith((".db", ".sqlite")))
            self.assertEqual(self.guard(a, self.tree({**LAYOUT[a], db: b"\0" * 100, **marker(a)})), 1)
        self.each(check)

    def test_refuses_symlinked_file(self):
        def check(a):
            db = next(k for k in LAYOUT[a] if k.endswith((".db", ".sqlite")))
            outside = Path(self.tree({"real": SQLITE}), "real")
            root = Path(self.tree({**{k: v for k, v in LAYOUT[a].items() if k != db}, **marker(a)}))
            (root / db).parent.mkdir(parents=True, exist_ok=True)
            os.symlink(outside, root / db)
            self.assertEqual(self.guard(a, root), 1)
        self.each(check)

    def test_other_apps_keep_their_marker(self):
        def check(a):
            other, files = OTHER[a]
            self.assertEqual(self.guard(a, self.tree(files), other), 1)
            self.assertEqual(self.guard(a, self.tree({**files, **marker(other)}), other), 0)
        self.each(check)


if __name__ == "__main__":
    unittest.main()
