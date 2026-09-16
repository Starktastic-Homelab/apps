#!/usr/bin/env python3
"""Check the disposable Jellyfin restore and rendered isolation; run from repo root."""

from contextlib import closing
import json
from pathlib import Path
import runpy
import shutil
import sqlite3
import subprocess
from tempfile import TemporaryDirectory
from unittest import TestCase

import yaml


directory = Path("services/media/jellyfin-rehearsal")
initializer = directory / "manifests/prepare.py"
assert initializer.is_file(), "The rehearsal initializer is missing"
helpers = runpy.run_path(str(initializer))
assert "require_ready" in helpers, "Pod startup must validate a preseeded copy without accessing the NAS snapshot"
prepare, require_ready = helpers["prepare"], helpers["require_ready"]
assert helpers["SNAPSHOT"] == Path(
    "/mnt/apps/pv/.zfs/snapshot/jellyfin-rehearsal-20260916-359cdcb9/media/jellyfin-config"
)
assert helpers["DESTINATION"] == Path("/mnt/apps/pv/media/jellyfin-rehearsal")
checks = TestCase()

with TemporaryDirectory() as temporary:
    root = Path(temporary)
    source, target = root / "snapshot", root / "clone"
    database = Path("data/data/jellyfin.db")
    (source / database.parent).mkdir(parents=True)
    old_plugin = source / "data/plugins/Example_1"
    old_plugin.mkdir(parents=True)
    (old_plugin / "Example.dll").write_bytes(b"old plugin")
    configurations = source / "data/plugins/configurations"
    configurations.mkdir()
    (configurations / "Example.xml").write_text("<setting>keep</setting>")
    (source / "system.xml").write_text("<configuration>keep</configuration>")
    (source / "cache").mkdir()
    (source / "cache/disposable").touch()
    litedb_files = {
        "kodisyncqueue.db": b"LiteDB data fixture",
        "kodisyncqueue-log.db": b"LiteDB transaction-log fixture",
    }
    for name, content in litedb_files.items():
        (source / "data/data" / name).write_bytes(content)

    # Keep the writer open so the copied data must include committed WAL frames.
    with closing(sqlite3.connect(source / database)) as original:
        original.execute("PRAGMA journal_mode=WAL")
        original.execute("CREATE TABLE example (value INTEGER)")
        original.execute("INSERT INTO example VALUES (1)")
        original.commit()
        try:
            prepare(source, target)
        except sqlite3.DatabaseError as error:
            raise AssertionError("Kodi's LiteDB data and log must not be treated as SQLite") from error
        require_ready(target)
        with closing(sqlite3.connect(target / database)) as restored:
            assert restored.execute("SELECT value FROM example").fetchall() == [(1,)]
            restored.execute("INSERT INTO example VALUES (2)")
            restored.commit()
        assert original.execute("SELECT value FROM example").fetchall() == [(1,)]

    assert (target / "system.xml").read_text() == "<configuration>keep</configuration>"
    assert not (target / "cache/disposable").exists()
    assert not list((target / "data/plugins").rglob("*.dll"))
    assert (target / "data/plugins/configurations/Example.xml").read_text() == "<setting>keep</setting>"
    assert (target / "data/plugins-before-12/Example_1/Example.dll").is_file()
    for name, content in litedb_files.items():
        assert (target / "data/data" / name).read_bytes() == content
    assert target.stat().st_uid == source.stat().st_uid
    assert target.stat().st_gid == source.stat().st_gid

    source.rename(root / "offline-snapshot")
    require_ready(target)
    (root / "offline-snapshot").rename(source)

    with checks.assertRaises(RuntimeError):
        require_ready(root / "empty")
    unready = root / "unready"
    shutil.copytree(target, unready)
    marker = unready / ".rehearsal-ready"
    ready_text = marker.read_text()
    marker.unlink()
    with checks.assertRaises(RuntimeError):
        require_ready(unready)
    marker.write_text("Incomplete restore\n")
    with checks.assertRaises(RuntimeError):
        require_ready(unready)
    marker.unlink()
    marker.symlink_to(target / marker.name)
    with checks.assertRaises(RuntimeError):
        require_ready(unready)
    marker.unlink()
    marker.write_text(ready_text)
    (unready / database).unlink()
    with checks.assertRaises(RuntimeError):
        require_ready(unready)
    (unready / database).symlink_to(target / database)
    with checks.assertRaises(RuntimeError):
        require_ready(unready)

    alias = root / "target-alias"
    alias.symlink_to(target)
    with checks.assertRaises(RuntimeError):
        prepare(source, alias)

    new_plugin = target / "data/plugins/Example_2"
    new_plugin.mkdir()
    (new_plugin / "Example.dll").write_bytes(b"new plugin")
    prepare(source, target)
    with closing(sqlite3.connect(target / database)) as restored:
        assert restored.execute("SELECT value FROM example").fetchall() == [(1,), (2,)]
    assert (new_plugin / "Example.dll").is_file(), "Restarts must preserve newly installed plugins"

    partial = root / "partial"
    partial.mkdir()
    (partial / "incomplete-copy").touch()
    try:
        prepare(source, partial)
    except RuntimeError:
        pass
    else:
        raise AssertionError("A partial destination must not be reused")

    broken = root / "broken"
    (broken / database.parent).mkdir(parents=True)
    (broken / database).write_bytes(b"not a SQLite database")
    rejected = root / "rejected"
    try:
        prepare(broken, rejected)
    except sqlite3.DatabaseError:
        pass
    else:
        raise AssertionError("A corrupt backup must not pass preparation")
    assert not (rejected / ".rehearsal-ready").exists()

    unknown = root / "unknown-format"
    (unknown / database.parent).mkdir(parents=True)
    shutil.copy2(source / database, unknown / database)
    (unknown / "data/data/unknown.db").write_bytes(b"not a recognized database")
    with checks.assertRaisesRegex(sqlite3.DatabaseError, "unknown.db"):
        prepare(unknown, root / "unknown-rejected")
    assert not (root / "unknown-rejected/.rehearsal-ready").exists()

    outside = root / "outside-clone"
    (source / ".rehearsal-ready").symlink_to(outside)
    try:
        prepare(source, root / "marker-clone")
    except RuntimeError:
        pass
    else:
        raise AssertionError("A source marker symlink must not be copied or followed")
    assert not outside.exists()

app = yaml.safe_load((directory / "app.yaml").read_text())
assert app["baseApp"] == "services/media/jellyfin" and app["valuesOverride"]
assert not app["ingress"]["enabled"]
chart = app["chart"]
assert chart == {"repo": "ghcr.io/bjw-s-labs/helm", "name": "app-template", "version": "5.1.0"}
rendered = subprocess.check_output(
    [
        "helm", "template", "jellyfin-rehearsal", f"oci://{chart['repo']}/{chart['name']}",
        "--version", chart["version"],
        "--namespace", "media",
        "-f", "templates/globals.yaml", "-f", "templates/common.yaml",
        "-f", "services/media/jellyfin/values.yaml", "-f", str(directory / "values.yaml"),
    ],
    text=True,
)
documents = [document for document in yaml.safe_load_all(rendered) if document]
deployment = next(document for document in documents if document["kind"] == "Deployment")
assert deployment["spec"]["replicas"] == 1
assert deployment["spec"]["strategy"]["type"] == "Recreate"
pod = deployment["spec"]["template"]["spec"]
assert pod["nodeSelector"]["kubernetes.io/hostname"] == "kube-worker-02"
assert pod["automountServiceAccountToken"] is False and not pod.get("hostNetwork", False)
main = next(container for container in pod["containers"] if container["name"] == "main")
assert main["image"] == (
    "lscr.io/linuxserver/jellyfin:12.1ubu2604-ls50@sha256:"
    "51252e7a416e703cdc3cd91e8a54673a2430cc80409be8a38abe511411577b95"
)
assert main["resources"]["limits"]["memory"] == "8Gi"
assert main["resources"]["limits"]["gpu.intel.com/i915"] == "1"
assert "exec" in main["readinessProbe"]
assert all(env.get("value") != "https://benplus.app" for env in main.get("env", []))

volumes = {volume["name"]: volume for volume in pod["volumes"]}
claims = {document["metadata"]["name"] for document in documents if document["kind"] == "PersistentVolumeClaim"}
assert claims == {"jellyfin-rehearsal"}, "The claim must match the fixed NAS restore destination"
assert volumes["config"]["persistentVolumeClaim"]["claimName"] in claims
assert not ({"jellyfin-config", "jellyfin-cache"} & {
    volume["persistentVolumeClaim"]["claimName"] for volume in volumes.values() if "persistentVolumeClaim" in volume
})
assert volumes["cache"]["emptyDir"]["sizeLimit"] == "10Gi"
assert "snapshot" not in volumes and not any("nfs" in volume for volume in volumes.values())
media_mount = next(mount for mount in main["volumeMounts"] if mount["mountPath"] == "/data")
assert media_mount["readOnly"] is True
assert volumes[media_mount["name"]]["persistentVolumeClaim"]["claimName"] == "media-library-pvc"
initial = next(container for container in pod["initContainers"] if container["name"] == "prepare")
assert initial["command"] == ["python", "/scripts/prepare.py"], "The pod must only check, never perform the NAS restore"
assert next(mount for mount in initial["volumeMounts"] if mount["name"] == "config")["mountPath"] == "/config"
assert not any(mount["name"] == media_mount["name"] for mount in initial["volumeMounts"])
services = [document for document in documents if document["kind"] == "Service"]
assert len(services) == 1 and services[0]["spec"]["type"] == "ClusterIP"
assert [port["port"] for port in services[0]["spec"]["ports"]] == [8096]
published = next(env["value"] for env in main["env"] if env["name"] == "JELLYFIN_PublishedServerUrl")
assert published == f"http://{services[0]['metadata']['name']}.media:8096"

rules = json.loads(Path("renovate.json").read_text())["packageRules"]
assert any(
    rule.get("matchFileNames") == ["services/media/jellyfin-rehearsal/**"] and rule.get("enabled") is False
    for rule in rules
), "The disposable rehearsal must not receive automated dependency changes"
print("Jellyfin rehearsal OK: NAS-local WAL restore, preseed gate, corruption/partial-copy gates, and isolation")
