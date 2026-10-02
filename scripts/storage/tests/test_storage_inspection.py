import copy
import hashlib
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from render_storage import record_hash
from test_render_storage import RECORD
import storage_inspection as inspection

NOW = datetime.now(timezone.utc) + timedelta(seconds=10)
SECRET = 'PRIVATE_SENTINEL_DO_NOT_PRINT'


def fixture(root):
    directory = root / 'operations/jellyfin'
    directory.mkdir(parents=True)
    (root / 'runner-instance').write_text('runner-1\n')
    operation = dict(schema=1, owner=SECRET, nonce=SECRET, operation='storage-hold',
                     stage='acquired', instance='runner-1', created_at='2026-09-01T00:00:00+00:00')
    (root / 'operation.json').write_text(json.dumps(operation))
    node = dict(hostname='worker-a', node_uid='node-a', smbios_uuid='vm-a', ssh_host='worker-a')
    records = {
        'record.json': copy.deepcopy(RECORD),
        'stages.json': {'target-held': 'a' * 40},
        'placement.json': dict(previous=node, next=node, old_writer_mode='clean-unmount'),
        'target-may-have-written.json': dict(target_may_have_written=True,
            record_hash=record_hash(RECORD), recorded_at='2026-09-01T00:00:00+00:00'),
    }
    for name, data in records.items():
        (directory / name).write_text(json.dumps(data))
    return directory


def checks(report):
    return {check['id']: check for check in report['checks']}


class InspectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.directory = fixture(self.root)
        self.receipt_root = self.root/'receipt-control'; self.receipt_root.mkdir()
        location = patch.object(inspection, 'RECONCILIATION_ROOT', self.receipt_root)
        location.start(); self.addCleanup(location.stop)
        # Synthetic receipt root: production protected-parent enforcement tested separately.
        safe = patch.object(inspection, '_protected_directory', inspection._open_path)
        safe.start(); self.addCleanup(safe.stop)

    def inspect(self):
        result = inspection.inspect_state(self.root, 'jellyfin', now=NOW)
        self.assertNotIn(SECRET, json.dumps(result))
        self.assertFalse(result['live_verified'])
        self.assertFalse(result['release_authorized'])
        return checks(result)

    def test_valid_state_is_unchanged_and_locally_consistent(self):
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        result = self.inspect()
        self.assertEqual(result['ownership']['status'], 'pass')
        self.assertEqual(result['ownership']['details']['stage'], 'acquired')
        self.assertEqual(result['first_write']['status'], 'pass')
        self.assertEqual(before, {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_missing_and_malformed_are_distinct(self):
        p = self.directory / 'record.json'
        p.unlink()
        self.assertEqual(self.inspect()['record']['status'], 'unknown')
        for text in ['{'+SECRET, '[]', 'null', '"'+SECRET+'"']:
            p.write_text(text)
            self.assertEqual(self.inspect()['record']['status'], 'fail')

    def test_missing_root_and_relative_or_traversal_paths(self):
        for root in [self.root/'absent', Path('relative'), self.root/'..'/self.root.name]:
            result = inspection.inspect_state(root, 'jellyfin', now=NOW)
            self.assertNotEqual(checks(result)['state_root']['status'], 'pass')

    def test_symlink_parent_and_file_are_refused(self):
        p = self.directory/'record.json'
        p.unlink(); p.symlink_to(self.root/'operation.json')
        self.assertEqual(self.inspect()['record']['status'], 'fail')
        alias = self.root/'alias'; alias.symlink_to(self.root, target_is_directory=True)
        result = inspection.inspect_state(alias, 'jellyfin', now=NOW)
        self.assertEqual(checks(result)['state_root']['status'], 'fail')
        p.unlink()
        self.directory.rename(self.root/'moved')
        self.directory.symlink_to(self.root/'moved', target_is_directory=True)
        self.assertEqual(self.inspect()['record']['status'], 'fail')

    def test_fifo_and_oversized_file_do_not_get_read(self):
        p = self.directory/'record.json'; p.unlink(); os.mkfifo(p)
        self.assertEqual(self.inspect()['record']['status'], 'fail')
        p.unlink(); p.write_bytes(b'x' * (1024**2 + 1))
        self.assertEqual(self.inspect()['record']['status'], 'fail')

    def test_identity_contradictions_fail(self):
        for filename, key, value, check in [
            ('record.json', 'service', 'other', 'record'),
            ('target-may-have-written.json', 'record_hash', '0'*64, 'first_write'),
            ('placement.json', 'old_writer_mode', 'guess', 'placement')]:
            path = self.directory/filename; original = path.read_text()
            data = json.loads(original); data[key] = value; path.write_text(json.dumps(data))
            self.assertEqual(self.inspect()[check]['status'], 'fail')
            path.write_text(original)
        path = self.root/'operation.json'; data = json.loads(path.read_text())
        data['instance'] = 'other'; path.write_text(json.dumps(data))
        self.assertEqual(self.inspect()['ownership']['status'], 'fail')

    def test_absent_first_write_never_means_safe_rollback(self):
        (self.directory/'target-may-have-written.json').unlink()
        self.assertEqual(self.inspect()['first_write']['status'], 'unknown')

    def test_secret_fields_are_not_echoed(self):
        for name in ['record.json', 'stages.json', 'placement.json']:
            p = self.directory/name; data = json.loads(p.read_text()); data[SECRET] = SECRET
            p.write_text(json.dumps(data))
        self.inspect()

    def test_journals_are_not_mistaken_for_completion(self):
        self.assertEqual(self.inspect()['onboarding_journal']['status'], 'not_checked')
        (self.directory/'onboarding.jsonl').write_text(SECRET)
        check = self.inspect()['onboarding_journal']
        self.assertEqual(check['status'], 'unknown')
        self.assertIn('file_age_seconds', check['details'])

    def receipt(self):
        for name in ('onboarding.jsonl', 'snapshot-intent.jsonl'):
            (self.directory/name).write_text('{"state":"intent"}\n')
        return dict(schema=1, service='jellyfin', runner_instance='runner-1',
                    observed_at=NOW.isoformat(), scope='historical-native-reconciliation',
                    inputs={n: hashlib.sha256((self.directory/n).read_bytes()).hexdigest()
                            for n in ('record.json', 'onboarding.jsonl', 'snapshot-intent.jsonl')},
                    results={'onboarding': 'verified', 'snapshot': 'verified'})

    def inspect_receipt(self, value):
        path = self.receipt_root/'jellyfin-reconciliation.json'; path.write_text(json.dumps(value)); path.chmod(0o640)
        original = inspection._Snapshot.read
        def read(snapshot, name, **kwargs):
            raw, info = original(snapshot, name, **kwargs)
            if name == 'jellyfin-reconciliation.json':
                values = list(info); values[4] = 0; info = os.stat_result(values)
            return raw, info
        with patch.object(inspection._Snapshot, 'read', read): return self.inspect()

    def test_root_receipt_resolves_only_matching_historical_journals(self):
        value = self.receipt(); result = self.inspect_receipt(value)
        for name in ('onboarding_journal', 'snapshot_journal'):
            self.assertEqual(result[name]['status'], 'pass')
            self.assertEqual(result[name]['details']['evidence_age_seconds'], 0)
        (self.directory/'onboarding.jsonl').write_text('{"state":"changed"}\n')
        result = self.inspect_receipt(value)
        self.assertEqual(result['onboarding_journal']['status'], 'unknown')
        self.assertEqual(result['snapshot_journal']['status'], 'unknown')

    def test_receipt_with_removed_journals_is_inconclusive(self):
        value = self.receipt(); self.inspect_receipt(value)
        for name in ('onboarding.jsonl', 'snapshot-intent.jsonl'):
            (self.directory/name).unlink()
        result = self.inspect_receipt(value)
        self.assertIn('unknown', [c['status'] for c in result.values()])
        self.assertEqual(result['reconciliation']['status'], 'unknown')

    def test_receipt_wrong_identity_record_timestamp_or_results_cannot_pass(self):
        value = self.receipt()
        cases = [('runner_instance', 'other'), ('service', 'other'), ('schema', True),
                 ('observed_at', (NOW+timedelta(seconds=1)).isoformat()),
                 ('observed_at', '2026-09-01T00:00:00'), ('results', {'onboarding':'verified'})]
        for key, bad in cases:
            with self.subTest(key=key):
                modified = dict(value); modified[key] = bad
                self.assertNotEqual(self.inspect_receipt(modified)['onboarding_journal']['status'], 'pass')
        (self.directory/'record.json').write_text('{}')
        self.assertNotEqual(self.inspect_receipt(value)['onboarding_journal']['status'], 'pass')

    def test_unprivileged_or_writable_receipt_is_not_trusted(self):
        value = self.receipt(); path = self.receipt_root/'jellyfin-reconciliation.json'
        path.write_text(json.dumps(value)); path.chmod(0o640)
        if os.getuid() != 0:
            self.assertEqual(self.inspect()['onboarding_journal']['status'], 'fail')
        path.chmod(0o666)
        self.assertEqual(self.inspect()['onboarding_journal']['status'], 'fail')
        path.unlink(); path.symlink_to(self.directory/'record.json')
        self.assertEqual(self.inspect()['onboarding_journal']['status'], 'fail')

    def test_future_or_naive_timestamps_are_not_fresh(self):
        p = self.directory/'target-may-have-written.json'; data = json.loads(p.read_text())
        for timestamp in [(NOW+timedelta(days=1)).isoformat(), '2026-09-01T00:00:00']:
            data['recorded_at'] = timestamp; p.write_text(json.dumps(data))
            self.assertEqual(self.inspect()['first_write']['status'], 'unknown')

    def test_changed_file_during_collection_is_inconclusive(self):
        original = inspection.record_hash
        def change(record):
            p = self.directory/'stages.json'
            p.write_text(json.dumps({'target-held': 'b'*40}))
            return original(record)
        with patch.object(inspection, 'record_hash', side_effect=change):
            self.assertEqual(self.inspect()['snapshot']['status'], 'unknown')

    def test_unsupported_service_is_fixed_error(self):
        result = inspection.inspect_state(self.root, SECRET, now=NOW)
        self.assertNotIn(SECRET, json.dumps(result))
        self.assertEqual(checks(result)['service']['status'], 'fail')


class PreflightTests(unittest.TestCase):
    setUp = InspectionTests.setUp

    def preflight(self):
        with patch('subprocess.run', side_effect=AssertionError('No subprocess allowed')), patch('socket.socket', side_effect=AssertionError('No network allowed')):
            result = inspection.preflight(self.root, 'jellyfin', now=NOW)
        self.assertNotIn(SECRET, json.dumps(result))
        self.assertEqual(result['command'], 'preflight')
        return checks(result)

    def test_missing_executables_are_reported_without_execution(self):
        with patch('shutil.which', return_value=None):
            result = self.preflight()
        for tool in ('ssh', 'kubectl', 'tar', 'systemctl'):
            self.assertEqual(result['tool_'+tool]['status'], 'fail')

    def test_transport_version_missing_wrong_and_matching(self):
        from importlib.metadata import PackageNotFoundError
        for value, expected in [('1.9.2', 'pass'), ('0.0.1', 'fail'), (SECRET, 'fail')]:
            with patch('importlib.metadata.version', return_value=value):
                self.assertEqual(self.preflight()['transport']['status'], expected)
        with patch('importlib.metadata.version', side_effect=PackageNotFoundError):
            self.assertEqual(self.preflight()['transport']['status'], 'fail')

    def test_helper_is_discovered_without_import(self):
        with patch('importlib.machinery.PathFinder.find_spec', return_value=None):
            self.assertEqual(self.preflight()['maintenance_helper']['status'], 'fail')

    def test_capacity_failure_and_success(self):
        result = self.preflight()
        self.assertGreaterEqual(result['state_capacity']['details']['available_bytes'], 0)
        with patch('os.fstatvfs', side_effect=OSError(SECRET)):
            self.assertEqual(self.preflight()['state_capacity']['status'], 'unknown')

    def test_private_files_never_read_and_state_unchanged(self):
        private = self.root/'private'; private.mkdir(); (private/'nas.credentials').write_text(SECRET)
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        original = os.open
        def checked_open(path, *args, **kwargs):
            self.assertNotIn('private', str(path))
            self.assertNotIn('credentials', str(path))
            return original(path, *args, **kwargs)
        with patch('os.open', side_effect=checked_open):
            self.preflight()
        self.assertEqual(before, {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()})


if __name__ == '__main__':
    unittest.main()
