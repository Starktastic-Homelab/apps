import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_storage_inspection import fixture, NOW
import reconciliation
import storage_inspection as inspection


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name); self.directory = fixture(self.root)
        for name in ('onboarding.jsonl', 'snapshot-intent.jsonl'):
            (self.directory/name).write_text('{"state":"intent"}\n')
        self.record = json.loads((self.directory/'record.json').read_text())

    def generate(self, native=None, snapshot=None):
        with patch('onboard.reconcile_onboarding', return_value=self.record if native is None else native), \
                patch('onboard.snapshot_policy', return_value={'verified':True,'id':2} if snapshot is None else snapshot):
            return reconciliation.generate(self.root, object(), now=NOW)

    def test_receipt_contains_only_verified_scope_and_hashes(self):
        before = {p:p.read_bytes() for p in self.directory.iterdir()}
        receipt = self.generate()
        self.assertEqual(receipt['scope'], 'historical-native-reconciliation')
        self.assertEqual(receipt['results'], {'onboarding':'verified','snapshot':'verified'})
        self.assertEqual(set(receipt['inputs']), {'record.json','onboarding.jsonl','snapshot-intent.jsonl'})
        self.assertEqual(before, {p:p.read_bytes() for p in self.directory.iterdir()})

    def test_conflicting_native_or_failed_snapshot_never_generates_receipt(self):
        native = dict(self.record, dataset='changed')
        with self.assertRaises(ValueError): self.generate(native=native)
        with self.assertRaises(ValueError): self.generate(snapshot={'verified':False})

    def test_input_change_during_observation_is_refused(self):
        def change(*args, **kwargs):
            (self.directory/'record.json').write_text('{}')
            return {'verified':True,'id':2}
        with patch('onboard.reconcile_onboarding', return_value=self.record), patch('onboard.snapshot_policy', side_effect=change):
            with self.assertRaises(ValueError): reconciliation.generate(self.root, object(), now=NOW)

    def test_copied_state_cannot_substitute_the_installed_execution_guard(self):
        import shutil
        copied = self.root/'copied'; shutil.copytree(self.directory.parent.parent, copied, ignore=shutil.ignore_patterns('copied'))
        data = {'state_root':str(self.root), 'runner_instance':'runner-1'}
        self.assertEqual(reconciliation.bind_state(data, self.root), self.root)
        with self.assertRaises(ValueError): reconciliation.bind_state(data, copied)
        (self.root/'runner-instance').write_text('other')
        with self.assertRaises(ValueError): reconciliation.bind_state(data, self.root)

    def test_rpc_mutation_never_reaches_transport(self):
        class NAS:
            def call(self, *args): raise AssertionError('transport called')
        with self.assertRaises(ValueError): reconciliation.ReadOnlyNAS(NAS()).call('pool.dataset.create', {})

    def test_writable_parent_cannot_host_trusted_receipt(self):
        # /tmp has a writable ancestor even if a leaf were root-owned and 0755.
        with self.assertRaises(ValueError):
            with reconciliation._protected_directory(self.directory): pass

    def test_atomic_publication_preserves_originals_and_refuses_overwrite(self):
        destination = self.root/'receipt-control'; destination.mkdir()
        before = {p:p.read_bytes() for p in self.directory.iterdir()}
        original = os.fstat
        def root_metadata(fd):
            info = original(fd); values = list(info); values[4] = 0
            return os.stat_result(values)
        # Simulate the privileged metadata profile; exercise actual atomic filesystem operations.
        with patch.object(inspection, 'RECONCILIATION_ROOT', destination), \
                patch('reconciliation._protected_directory', inspection._open_path), \
                patch('reconciliation.os.geteuid', return_value=0), \
                patch('reconciliation.os.fstat', side_effect=root_metadata), \
                patch('reconciliation.os.fchown'), \
                patch('onboard.reconcile_onboarding', return_value=self.record), \
                patch('onboard.snapshot_policy', return_value={'verified':True,'id':2}):
            receipt = reconciliation.publish(self.root, object(), now=NOW)
            path = destination/'jellyfin-reconciliation.json'; original_bytes = path.read_bytes()
            self.assertEqual(json.loads(original_bytes), receipt)
            self.assertEqual(path.stat().st_mode & 0o777, 0o640)
            self.assertEqual(path.stat().st_nlink, 1)
            with self.assertRaises(FileExistsError): reconciliation.publish(self.root, object(), now=NOW)
            self.assertEqual(path.read_bytes(), original_bytes)
        self.assertEqual(before, {p:p.read_bytes() for p in self.directory.iterdir()})

    def test_publication_requires_root_and_never_replaces_evidence(self):
        if os.geteuid() != 0:
            with self.assertRaises(PermissionError): reconciliation.publish(self.root, object(), now=NOW)
        self.assertFalse((self.directory/'reconciliation.json').exists())


if __name__ == '__main__': unittest.main()
