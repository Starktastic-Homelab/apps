import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from test_storage_inspection import fixture

ADAPTER = Path(__file__).resolve().parents[1]/'supervised_readonly.py'


class AdapterTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name); fixture(self.root)

    def run_adapter(self, *args):
        return subprocess.run([sys.executable, '-B', '-S', str(ADAPTER), *map(str, args)],
                              env={'PATH': os.defpath}, capture_output=True, text=True, timeout=10)

    def test_readonly_json_and_exit_semantics_without_transport(self):
        for operation, code in [('status', 0), ('preflight', 1)]:
            result = self.run_adapter(operation, '--state-root', self.root, '--service', 'jellyfin')
            self.assertEqual(result.returncode, code, result.stderr)
            report = json.loads(result.stdout)
            self.assertFalse(report['release_authorized']); self.assertFalse(report['live_verified'])

    def test_managed_dependencies_and_helper_without_import_or_execution(self):
        helper = self.root/'helpers'; helper.mkdir()
        (helper/'maintenance_lock.py').write_text('raise AssertionError("must not import")')
        deps = self.root/'dependencies'; (deps/'bin').mkdir(parents=True)
        kubectl = deps/'bin/kubectl'
        kubectl.write_text('#!/bin/sh\nexit 99\n'); kubectl.chmod(0o755)
        (deps/'python').mkdir()
        wheel = deps/'python/websocket_client-1.9.2-py3-none-any.whl'
        with zipfile.ZipFile(wheel, 'w') as archive:
            archive.writestr('websocket_client-1.9.2.dist-info/METADATA',
                             'Metadata-Version: 2.1\nName: websocket-client\nVersion: 1.9.2\n')
        argv = [sys.executable, '-B', '-E', '-s', str(ADAPTER), 'preflight',
                '--state-root', str(self.root), '--service', 'jellyfin',
                '--helper-directory', str(helper), '--dependency-directory', str(deps)]
        result = subprocess.run(argv, env={'PATH': os.defpath}, capture_output=True, text=True, timeout=10)
        self.assertIn(result.returncode, (0, 1), result.stderr)
        report = json.loads(result.stdout); checks = {c['id']: c['status'] for c in report['checks']}
        for name in ('maintenance_helper', 'transport', 'tool_kubectl'):
            self.assertEqual(checks[name], 'pass', report)
        self.assertFalse(report['release_authorized']); self.assertFalse(report['live_verified'])
        kubectl.unlink()
        with zipfile.ZipFile(wheel, 'w') as archive:
            archive.writestr('websocket_client-1.9.2.dist-info/METADATA', 'Name: websocket-client\nVersion: 0.0.1\n')
        result = subprocess.run(argv, env={'PATH': os.defpath}, capture_output=True, text=True, timeout=10)
        checks = {c['id']: c['status'] for c in json.loads(result.stdout)['checks']}
        self.assertEqual(checks['tool_kubectl'], 'fail'); self.assertEqual(checks['transport'], 'fail')

    def test_mutations_and_unrecognized_input_refused(self):
        for operation in ['hold', 'release', 'verify', 'snapshot', 'onboard', 'sh', 'status --shell']:
            self.assertEqual(self.run_adapter(operation, '--state-root', self.root, '--service', 'jellyfin').returncode, 2)
        self.assertEqual(self.run_adapter('status').returncode, 2)

    def test_no_subprocess_or_network_or_state_mutations(self):
        import supervised_readonly
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        with patch('subprocess.Popen', side_effect=AssertionError('subprocess')), patch('socket.socket', side_effect=AssertionError('network')):
            for operation in ('status', 'preflight'):
                report = supervised_readonly.observe(operation, self.root, 'jellyfin')
                self.assertFalse(report['release_authorized'])
        self.assertEqual(before, {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()})


if __name__ == '__main__': unittest.main()
