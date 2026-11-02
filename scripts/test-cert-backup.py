#!/usr/bin/env python3
"""Exercise the actual cert backup script against a fake Kubernetes API."""
import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "infrastructure/base-configs/templates/cert-backup/backup-script.yaml"
SCRIPT = textwrap.dedent(SOURCE.read_text().split("  backup.sh: |\n", 1)[1])
OLD = "previous backup\n"
WEB, ACME, GONE = "apps--web.yaml", "cert-manager--letsencrypt-prod-account-key.yaml", "apps--gone.yaml"
# The API holds apps/web (TLS) and the unlabelled cert-manager/letsencrypt-prod-account-key.
# FAIL picks which calls error out (namespaces, secrets, lookup, issuer, all) or empty-tls for an empty TLS list;
# GET picks how `-o yaml` misbehaves.
KUBECTL = r"""#!/bin/sh
[ "$FAIL" = all ] && { echo 'connection refused' >&2; exit 1; }
case "$FAIL:$*" in lookup:*--ignore-not-found*|issuer:*issuer-name*) echo 'Error from server (Forbidden)' >&2; exit 1 ;; esac
case "$1 $2" in
  "get namespaces") [ "$FAIL" = namespaces ] && exit 1; echo 'apps cert-manager'; exit ;;
  "get secrets") [ "$FAIL" = secrets ] && exit 1; case "$*" in *kubernetes.io/tls*) [ "$FAIL" = empty-tls ] || echo 'apps web' ;; esac; exit ;;
esac
case "$5/$3" in
  apps/web|cert-manager/letsencrypt-prod-account-key) ;;
  *) case "$*" in *--ignore-not-found*) exit 0 ;; esac
     echo "Error from server (NotFound): secrets \"$3\" not found" >&2; exit 1 ;;
esac
case "$*" in
  *"-o yaml"*) case "$GET" in fail) echo 'apiVersion: v1'; exit 1 ;; empty) exit 0 ;; esac
               printf 'apiVersion: v1\nkind: Secret\nmetadata:\n  name: %s\n  namespace: %s\n  uid: 1234\n' "$3" "$5" ;;
  *jsonpath*) printf letsencrypt-prod ;;
  *) echo "secret/$3" ;;
esac
"""


class CertBackupTests(unittest.TestCase):
    def run_backup(self, fail="", get=""):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            backup = root / "backup"
            backup.mkdir()
            for name in (WEB, ACME, GONE):
                (backup / name).write_text(OLD)
            kubectl = root / "kubectl"
            kubectl.write_text(KUBECTL)
            kubectl.chmod(0o755)
            script = root / "backup.sh"
            # Redirect the real script's fixed destination into this temporary directory.
            script.write_text(SCRIPT.replace("BACKUP_DIR=/backup", f"BACKUP_DIR={backup}"))
            result = subprocess.run(["/bin/sh", str(script)], capture_output=True, text=True, umask=0o022,
                                    env=dict(os.environ, PATH=f"{root}:{os.environ['PATH']}", FAIL=fail, GET=get))
            files = {p.name: (p.read_text(), p.stat().st_mode & 0o777) for p in backup.iterdir()}
        leaked = [name for name in files if name.startswith(".") or not name.endswith(".yaml")]
        self.assertEqual(leaked, [], "Temporary file leaked")
        return result, files

    def test_get_failure_keeps_existing_backup_and_exits_nonzero(self):
        result, files = self.run_backup(get="fail")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual(files[WEB][0], OLD)
        self.assertEqual(files[ACME][0], OLD)
        self.assertEqual(sorted(files), sorted([WEB, ACME, GONE]))

    def test_empty_get_output_does_not_overwrite(self):
        result, files = self.run_backup(get="empty")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual(files[WEB][0], OLD)
        self.assertEqual(files[ACME][0], OLD)
        self.assertEqual(sorted(files), sorted([WEB, ACME, GONE]))

    def test_list_failure_deletes_nothing(self):
        for fail in ("namespaces", "secrets", "lookup", "issuer", "empty-tls", "all"):
            with self.subTest(fail=fail):
                result, files = self.run_backup(fail=fail)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertEqual(sorted(files), sorted([WEB, ACME, GONE]))

    def test_secret_really_gone_is_removed(self):
        result, files = self.run_backup()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(GONE, files)

    def test_success_writes_0600_yaml_and_leaves_no_temp(self):
        result, files = self.run_backup()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sorted(files), sorted([WEB, ACME]))
        for name, (text, mode) in files.items():
            self.assertEqual(mode, 0o600, name)
            self.assertIn("kind: Secret", text)
            self.assertNotIn("uid:", text)


if __name__ == "__main__":
    unittest.main()
