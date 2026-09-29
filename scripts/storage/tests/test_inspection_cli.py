from contextlib import ExitStack, redirect_stdout
from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_storage_inspection import fixture, SECRET

CLI = Path(__file__).resolve().parents[1]/'maintenance_cli.py'


class CLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.directory = fixture(self.root)

    def run_cli(self, *args):
        # -S removes optional site packages; environment has no credentials/helpers.
        return subprocess.run([sys.executable, '-B', '-S', str(CLI), *map(str, args)],
                              env={'PATH': os.defpath}, capture_output=True, text=True, timeout=10)

    def test_status_json_without_optional_dependencies_or_credentials(self):
        result = self.run_cli('status', '--service', 'jellyfin', '--state-root', self.root, '--json')
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report['scope'], 'local-only')
        self.assertFalse(report['release_authorized'])
        self.assertFalse(report['live_verified'])
        self.assertNotIn(SECRET, result.stdout+result.stderr)

    def test_text_reports_scope_and_no_authorization(self):
        result = self.run_cli('status', '--service', 'jellyfin', '--state-root', self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('local-only', result.stdout)
        self.assertIn('release_authorized: false', result.stdout)
        self.assertIn('live_verified: false', result.stdout)

    def test_help_does_not_load_transport(self):
        result = self.run_cli('--help')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('preflight', result.stdout)

    def test_missing_state_and_preflight_return_nonzero_json(self):
        for operation, root in [('status', self.root/'missing'), ('preflight', self.root)]:
            result = self.run_cli(operation, '--service', 'jellyfin', '--state-root', root, '--json')
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertFalse(json.loads(result.stdout)['release_authorized'])
            self.assertEqual(result.stderr, '')

    def test_invalid_options_are_usage_errors(self):
        for args in [('status',), ('preflight', '--service', 'jellyfin'),
                     ('status', '--state-root', self.root),
                     ('status', '--service', 'unknown', '--state-root', self.root),
                     ('render', '--json'), ('hold', '--state-root', self.root)]:
            result = self.run_cli(*args)
            self.assertEqual(result.returncode, 2, (args, result.stderr))
            self.assertNotIn('Traceback', result.stderr)

    def test_malformed_record_does_not_leak_input(self):
        (self.directory/'record.json').write_text('{'+SECRET)
        result = self.run_cli('status', '--service', 'jellyfin', '--state-root', self.root, '--json')
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertNotIn(SECRET, result.stdout+result.stderr)
        self.assertNotIn('Traceback', result.stdout+result.stderr)

    def test_in_process_dispatch_never_calls_maintenance_or_subprocess(self):
        import maintenance_cli
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        for operation in ('status', 'preflight'):
            with ExitStack() as stack:
                for name in ('require_maintenance', 'mutate_kube', 'probe_filesystem', 'observe_release'):
                    stack.enter_context(patch.object(maintenance_cli, name, side_effect=AssertionError('mutation')))
                stack.enter_context(patch('subprocess.run', side_effect=AssertionError('subprocess')))
                stack.enter_context(patch.dict(sys.modules, {'nas_rpc': None}))
                stack.enter_context(patch.object(sys, 'argv', [str(CLI), operation, '--service', 'jellyfin', '--state-root', str(self.root), '--json']))
                output = stack.enter_context(redirect_stdout(io.StringIO()))
                code = maintenance_cli.main()
                self.assertIn(code, (0, 1))
                self.assertFalse(json.loads(output.getvalue())['release_authorized'])
        self.assertEqual(before, {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()})


if __name__ == '__main__':
    unittest.main()
