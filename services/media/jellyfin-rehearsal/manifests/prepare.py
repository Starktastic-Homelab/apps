#!/usr/bin/env python3
"""Restore on the NAS with --restore; otherwise gate startup on the preseeded copy."""

import argparse
from contextlib import closing
import filecmp
from pathlib import Path
import shutil
import sqlite3
import subprocess


SNAPSHOT = Path("/mnt/apps/pv/.zfs/snapshot/jellyfin-rehearsal-20260916-359cdcb9/media/jellyfin-config")
DESTINATION = Path("/mnt/apps/pv/media/jellyfin-rehearsal")
DATABASE = Path("data/data/jellyfin.db")
READY_TEXT = f"Validated restore of {SNAPSHOT}\n"


def require_ready(target: Path):
    target = target.resolve()
    marker = target / ".rehearsal-ready"
    if marker.is_symlink() or not marker.is_file() or marker.read_text() != READY_TEXT:
        raise RuntimeError("Rehearsal is not prepared; run the tracked NAS restore before deployment")
    database = target / DATABASE
    if not database.is_file() or not database.resolve().is_relative_to(target):
        raise RuntimeError("Prepared rehearsal has lost its private database")
    print("Rehearsal already prepared; preserving data and plugins")


def prepare(source: Path, target: Path):
    if target.is_symlink():
        raise RuntimeError("Rehearsal destination must not be a symlink")
    source, target = source.resolve(strict=True), target.resolve()
    marker = target / ".rehearsal-ready"
    if source == target or source in target.parents or target in source.parents:
        raise RuntimeError("Snapshot and rehearsal paths must be separate")
    source_marker = source / marker.name
    database = source / DATABASE
    if (
        not database.is_file() or not database.resolve().is_relative_to(source)
        or source_marker.exists() or source_marker.is_symlink()
    ):
        raise RuntimeError("Source is not an original Jellyfin config snapshot")
    target.mkdir(parents=True, exist_ok=True)
    if marker.exists() or marker.is_symlink():
        require_ready(target)
        return
    if any(target.iterdir()):
        raise RuntimeError("Partial or unknown destination; do not overwrite it or touch production")

    for entry in source.iterdir():
        if entry.name != "cache":
            subprocess.run(["cp", "-a", str(entry), str(target)], check=True)
    shutil.copystat(source, target)
    shutil.chown(target, user=source.stat().st_uid, group=source.stat().st_gid)

    for path in sorted((target / "data/data").rglob("*.db")):
        relative = path.relative_to(target)
        if not path.resolve().is_relative_to(target):
            raise RuntimeError("Database path escapes the private rehearsal volume")
        # Kodi Sync Queue uses LiteDB; keep its data and transaction log together.
        if path.parent == target / "data/data" and path.name in ("kodisyncqueue.db", "kodisyncqueue-log.db"):
            if not filecmp.cmp(source / relative, path, shallow=False):
                raise RuntimeError(f"LiteDB copy differs from the snapshot: {relative}")
            print(f"LiteDB copy matches snapshot; native plugin check still required: {relative}")
            continue
        try:
            with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as connection:
                result = connection.execute("PRAGMA integrity_check").fetchall()
        except sqlite3.DatabaseError as error:
            raise sqlite3.DatabaseError(f"{relative}: {error}") from error
        if result != [("ok",)]:
            raise RuntimeError(f"SQLite integrity check failed: {relative}: {result}")
        print(f"SQLite integrity OK: {relative}")

    plugins = target / "data/plugins"
    if plugins.exists():
        archived = target / "data/plugins-before-12"
        if archived.exists():
            raise RuntimeError("Plugin archive already exists; refusing to overwrite it")
        plugins.rename(archived)
        plugins.mkdir()
        shutil.copystat(archived, plugins)
        shutil.chown(plugins, user=archived.stat().st_uid, group=archived.stat().st_gid)
        if (archived / "configurations").exists():
            subprocess.run(["cp", "-a", str(archived / "configurations"), str(plugins)], check=True)

    # ponytail: one snapshot per disposable PVC; never recopy over a migrated database.
    marker.write_text(READY_TEXT)
    print("Rehearsal config prepared; install compatible plugins after server migration")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--restore", action="store_true", help="Run on the NAS to restore the fixed private destination")
    if parser.parse_args().restore:
        prepare(SNAPSHOT, DESTINATION)
    else:
        require_ready(Path("/config"))
