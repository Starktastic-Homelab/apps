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


if __name__ == "__main__":
    unittest.main()
