import glob
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
GUARD = "infrastructure/base-configs/files/retained-startup/guard.py"
TEMPLATE = "infrastructure/base-configs/templates/retained-startup-guard.yaml"
CONFIGMAP = "retained-startup-guard"
PYTHON = re.compile(r"python@(sha256:[0-9a-f]{64})")
NAME = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
REFUSED = "Retained state refused; recovery acceptance is required."
UNSAFE = ("", "../x", "a/b", "A", "-x", "x-", "x" * 64, "a\n")


def run(args, timeout=60):
    return subprocess.run([sys.executable, "-I", "-B", str(ROOT / GUARD)] + [str(a) for a in args],
                          capture_output=True, text=True, env={"PATH": os.environ["PATH"]}, timeout=timeout)


def marker(app, kind="data", name=None):
    return {name or f".homelab-{app}-{kind}": f"homelab/{app}/{kind}/v1\n".encode()}


class GenericGuard(unittest.TestCase):
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
        return Path(d.name)

    def accepts(self, *args):
        r = run(args)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "Retained identity accepted.\n")

    def refuses(self, *args, timeout=60):
        r = run(args, timeout)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertEqual(r.stderr, REFUSED + "\n")  # one deliberate refusal line, not a crash

    def test_accepts_any_well_formed_name_and_kind(self):
        for app in ("sonarr", "radarr-ru", "a", "x" * 63, "new-app-2"):
            with self.subTest(app=app):
                self.accepts(app, self.tree(marker(app)))
                self.accepts(app, self.tree(marker(app)), "data")
                for kind in ("config", "cache", "state-2"):
                    self.accepts(app, self.tree(marker(app, kind)), kind)
        self.accepts("a", self.tree(marker("a", "x" * 63)), "x" * 63)  # a 63-character kind; app + kind must fit 128 bytes

    def test_accepts_an_explicit_marker_file(self):
        root = self.tree(marker("seerr-ru", "config", ".homelab-seerr-config"))
        self.accepts("seerr-ru", root, "config", ".homelab-seerr-config")
        self.refuses("seerr-ru", root, "config")  # the default name is not there
        # the file name is only a shape; the content still names this app and kind
        self.accepts("sonarr", self.tree(marker("sonarr", name=".homelab-sonarr-other")), "data", ".homelab-sonarr-other")

    def test_refuses_missing_wrong_empty_oversized_or_directory_marker(self):
        name, good = next(iter(marker("sonarr").items()))
        for files in ({"lost+found/": None}, {name: b"homelab/radarr/data/v1\n"}, {name: b"homelab/sonarr/config/v1\n"},
                      {name: good.rstrip()}, {name: b""}, {name: good + b"x" * 128}, {name + "/": None},
                      marker("radarr"), marker("sonarr", "config")):
            with self.subTest(files=files):
                self.refuses("sonarr", self.tree(files))

    def test_kind_and_marker_file_must_agree_with_content(self):
        self.refuses("seerr", self.tree(marker("seerr", "config")))  # default kind is data
        self.refuses("seerr", self.tree(marker("seerr")), "config")
        self.refuses("seerr-ru", self.tree(marker("seerr", "config", ".homelab-seerr-config")),
                     "config", ".homelab-seerr-config")

    def test_refuses_symlinked_marker_or_root(self):
        outside = self.tree(marker("sonarr")) / ".homelab-sonarr-data"
        root = self.tree({"lost+found/": None})
        os.symlink(outside, root / ".homelab-sonarr-data")
        self.refuses("sonarr", root)
        link = self.tree({}) / "root"
        os.symlink(outside.parent, link)
        self.refuses("sonarr", link)
        self.refuses("sonarr", "relative")
        self.refuses("sonarr", outside)  # a file, not a dir

    def test_refuses_fifo_marker_without_blocking(self):
        root = self.tree({"lost+found/": None})
        os.mkfifo(root / ".homelab-prometheus-data")
        self.refuses("prometheus", root, timeout=10)

    def test_refuses_unsafe_app_name(self):
        for app in UNSAFE:
            with self.subTest(app=app):
                files = {f".homelab-{app}-data": f"homelab/{app}/data/v1\n".encode()}  # "/" names plant nested markers
                self.refuses(app, self.tree(files))

    def test_refuses_bad_kind_or_marker_file(self):
        planted = {**marker("sonarr"), "sub/.homelab-sonarr-data": b"homelab/sonarr/data/v1\n",
                   ".homelab-sonarr-other": b"homelab/sonarr/data/v1\n", "x": b"homelab/sonarr/data/v1\n"}
        for kind in UNSAFE + ("Data", "data/", "other"):  # "other" is well formed, but its marker holds data
            with self.subTest(kind=kind):
                self.refuses("sonarr", self.tree(planted), kind)
                # a valid explicit file whose content names the bad kind, so only the kind pattern refuses
                files = {".homelab-sonarr-other": f"homelab/sonarr/{kind}/v1\n".encode()}
                if kind != "other":
                    self.refuses("sonarr", self.tree(files), kind, ".homelab-sonarr-other")
        for name in ("", "x", "sub/.homelab-sonarr-data", "../.homelab-sonarr-data", ".homelab-sonarr-",
                     ".homelab-Sonarr-data", ".homelab--data", ".homelab-sonarr-data\n", "/.homelab-sonarr-data",
                     ".homelab-sonarr-Data", ".homelab-sonarr-data-", ".homelab-" + "x" * 64 + "-data"):
            with self.subTest(name=name):
                files = dict(planted)
                if name and "/" not in name:  # plant the bad name itself, so only the name pattern refuses
                    files[name] = b"homelab/sonarr/data/v1\n"
                self.refuses("sonarr", self.tree(files), "data", name)

    def test_refuses_wrong_argument_count(self):
        root = self.tree(marker("sonarr"))
        self.refuses()
        self.refuses("sonarr")
        self.refuses("sonarr", root, "data", ".homelab-sonarr-data", "extra")

    def test_guard_and_template_name_no_app(self):
        names = {Path(p).parent.name for p in glob.glob(str(ROOT / "services/*/*/app.yaml"))
                 + glob.glob(str(ROOT / "infrastructure/**/app.yaml"), recursive=True)}
        names |= {c["command"][4] for _, _, _, c, _ in guards()}  # guarded names that are not app dirs
        self.assertIn("cleanuparr", names)
        for path in (GUARD, TEMPLATE):
            text = (ROOT / path).read_text()
            with self.subTest(file=path):
                self.assertEqual([n for n in names if re.search(rf"""['"]{re.escape(n)}['"]""", text)], [])
                self.assertEqual([n for n in names if re.search(rf"(?<![\w-]){re.escape(n)}(?![\w-])", text)], [])

    def test_template_serves_the_file(self):
        self.assertIn('guard.py: |{{ $.Files.Get "files/retained-startup/guard.py" | nindent 4 }}',
                      (ROOT / TEMPLATE).read_text())


def load(path):
    return yaml.safe_load(Path(path).read_text()) or {}


def merge(base, over):
    """Helm values layering: maps merge, everything else replaces."""
    if isinstance(base, dict) and isinstance(over, dict):
        return {**base, **{k: merge(base.get(k), v) for k, v in over.items()}}
    return over


def apps():
    """(app dir, namespace, merged values) for every app, layered as bootstrap/appsets/cluster-apps.yaml does."""
    for app_yaml in sorted(glob.glob(str(ROOT / "services/*/*/app.yaml"))
                           + glob.glob(str(ROOT / "infrastructure/**/app.yaml"), recursive=True)):
        d = Path(app_yaml).parent
        app = load(app_yaml)
        base = ROOT / app["baseApp"] if app.get("baseApp") else None
        layers = ([base / "values.yaml"] + ([d / "values.yaml"] if app.get("valuesOverride") else [])
                  if base else [d / "values.yaml"])
        values = {}
        for layer in layers:
            if layer.exists():
                values = merge(values, load(layer))
        yield d, app["namespace"], values


def walk(node, key=None):
    """Yield (key, node) for every mapping, parsing string-block init lists (pgadmin) too."""
    if isinstance(node, str) and key == "extraInitContainers":
        node = yaml.safe_load(node)
    if isinstance(node, dict):
        yield key, node
        for k, v in node.items():
            yield from walk(v, k)
    elif isinstance(node, list):
        for v in node:
            yield from walk(v, key)


def mounts(values, container, init):
    """(mount path, readOnly, volume source) for an init container, app-template or plain Kubernetes form."""
    if "volumeMounts" in container:
        volumes = {n["name"]: n for _, n in walk(values)
                   if "name" in n and {"configMap", "persistentVolumeClaim"} & set(n)}
        return [(m["mountPath"], m.get("readOnly"), volumes.get(m["name"], {})) for m in container["volumeMounts"]]
    found = []
    for entry in (values.get("persistence") or {}).values():
        for controller in (entry.get("advancedMounts") or {}).values():
            for m in controller.get(init) or []:
                found.append((m["path"], m.get("readOnly"), entry))
    return found


def guards():
    """(app dir, namespace, init name, container, mounts) for every init container that runs /retained-startup/."""
    for d, namespace, values in apps():
        for key, node in walk(values):
            command = node.get("command")
            if isinstance(command, list) and any("/retained-startup/" in str(c) for c in command):
                init = node.get("name", key)
                yield d, namespace, init, node, mounts(values, node, init)


def template_namespaces():
    return re.findall(r'"([a-z0-9-]+)"', re.search(r"range list ([^}]*)", (ROOT / TEMPLATE).read_text())[1])


class Wiring(unittest.TestCase):
    def test_every_guard_is_the_generic_guard(self):
        seen, digests = set(), set()
        for d, namespace, init, container, found in guards():
            command = container["command"]
            with self.subTest(app=d.name, init=init):
                self.assertEqual(command[:4], ["python3", "-I", "-B", "/retained-startup/guard.py"])
                app, root, *rest = command[4:]
                self.assertTrue(NAME.fullmatch(app), app)
                self.assertTrue(root.startswith("/"))
                self.assertLessEqual(len(rest), 2)  # optional kind and marker file
                self.assertNotIn(app, seen)
                seen.add(app)
                image = container["image"]
                ref = image if isinstance(image, str) else f"{image['repository']}@{image['digest']}"
                self.assertTrue(PYTHON.fullmatch(ref), ref)  # python pinned by digest; Renovate moves every pin together
                digests.add(PYTHON.fullmatch(ref)[1])
                self.assertNotIn("args", container)
                self.assertIn(namespace, template_namespaces())
                cm = [(ro, src) for path, ro, src in found if path == "/retained-startup"]
                self.assertEqual(len(cm), 1)
                ro, src = cm[0]
                self.assertTrue(ro)
                self.assertEqual((src.get("configMap") or src).get("name"), CONFIGMAP)
                self.assertEqual((src.get("configMap") or src).get("defaultMode"), 292)
                claim = [ro for path, ro, _ in found if path == root]
                self.assertEqual(claim, [True])  # the claim is mounted once, read-only, at the root
                security = container["securityContext"]
                self.assertIn("runAsUser", security)
                self.assertTrue(security["readOnlyRootFilesystem"])
                self.assertEqual(security["capabilities"]["drop"], ["ALL"])
        self.assertTrue(seen)
        self.assertEqual(len(digests), 1, digests)  # every guard on one python digest

    def test_template_namespaces_are_the_consumers(self):
        self.assertEqual(sorted(template_namespaces()), sorted({ns for _, ns, *_ in guards()}))

    def test_no_other_retained_configmap_is_mounted(self):
        for d, _, values in apps():
            for _, node in walk(values):
                source = node.get("configMap")
                name = source.get("name") if isinstance(source, dict) else (
                    node.get("name") if node.get("type") == "configMap" else None)
                if name and "retained" in name:
                    with self.subTest(app=d.name, configmap=name):
                        self.assertEqual(name, CONFIGMAP)


class NothingLeftBehind(unittest.TestCase):
    def test_no_retained_startup_dirs(self):
        self.assertEqual([p for p in glob.glob(str(ROOT / "**/retained-startup"), recursive=True)
                          if "/infrastructure/base-configs/files/" not in p], [])

    def test_no_other_guard_configmap(self):
        pattern = re.compile(r"[a-z0-9]-retained-(?:startup|database-guard)")
        hits = []
        for top in ("infrastructure", "services", "templates", "bootstrap", "scripts"):
            for path in (ROOT / top).rglob("*"):
                if path.is_file() and path.suffix in (".yaml", ".yml", ".py", ".sh", ".sql", ".json", ".tpl"):
                    if path != Path(__file__).resolve() and pattern.search(path.read_text(errors="replace")):
                        hits.append(str(path.relative_to(ROOT)))
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
