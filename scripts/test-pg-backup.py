#!/usr/bin/env python3
"""Exercise the actual backup script with controlled producer failures."""
import gzip
import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "infrastructure/base-configs/templates/pg-backup/backup-script.yaml"
SCRIPT = textwrap.dedent(SOURCE.read_text().split("  backup.sh: |\n", 1)[1])
SQL = "-- PostgreSQL database cluster dump\nSELECT 1;\n-- PostgreSQL database cluster dump complete\n"


class BackupTests(unittest.TestCase):
    def run_backup(self, mode, compressor=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            backup = root / "backup"
            backup.mkdir()
            old = backup / "pg_dumpall_2000-01-01_000000.sql.gz"
            old.write_bytes(b"previous backup")
            os.utime(old, (1, 1))
            producer = root / "pg_dumpall"
            producer.write_text("#!/bin/sh\ncase \"$MODE\" in\n"
                                 "  fail) exit 23 ;;\n"
                                 "  partial) printf 'incomplete dump'; exit 23 ;;\n"
                                 "  empty) exit 0 ;;\n"
                                 "  incomplete) printf 'incomplete dump'; exit 0 ;;\n"
                                 "  *) printf '%s' \"$SQL\" ;;\nesac\n")
            producer.chmod(0o755)
            if compressor:
                binary = root / "gzip"
                binary.write_text("#!/bin/sh\n" + compressor)
                binary.chmod(0o755)
            script = root / "backup.sh"
            # Redirect the real script's fixed destination into this temporary directory.
            script.write_text(SCRIPT.replace("BACKUP_DIR=/backup", f"BACKUP_DIR={backup}"))
            result = subprocess.run(["/bin/sh", str(script)], capture_output=True, text=True,
                                    env=dict(os.environ, PATH=str(root) + ":" + os.environ["PATH"], MODE=mode, SQL=SQL))
            archives = [p for p in backup.glob("*.sql.gz") if p != old]
            if mode != "success" or compressor:
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertEqual(archives, [], "Failed dump was published")
                self.assertTrue(old.exists(), "Failure ran retention cleanup")
                self.assertNotIn("Backup complete", result.stdout)
            else:
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(len(archives), 1)
                self.assertEqual(archives[0].stat().st_mode & 0o777, 0o600)
                self.assertEqual(gzip.decompress(archives[0].read_bytes()).decode(), SQL)
                self.assertFalse(old.exists())
            self.assertFalse(list(backup.glob("*.tmp")), "Temporary dump leaked")

    def test_failed_empty_and_incomplete_dumps_are_never_published(self):
        for mode in ("fail", "partial", "empty", "incomplete"):
            with self.subTest(mode=mode):
                self.run_backup(mode)

    def test_compression_failure_preserves_old_backups(self):
        self.run_backup("success", "exit 9\n")

    def test_corrupt_compressor_output_is_rejected(self):
        self.run_backup("success", "if [ \"$1\" = -t ]; then exit 1; fi\nprintf corrupt\n")

    def test_success_publishes_complete_archive_then_applies_retention(self):
        self.run_backup("success")


if __name__ == "__main__":
    unittest.main()
