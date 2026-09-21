"""Synthetic failure cases; these are not production backup receipts."""
import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest
import os
from unittest.mock import patch
from maintenance_lock import acquire

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nfs_sync import inspect, apply_standard, reconcile

EXPECTED = dict(version='TrueNAS-25.10.7', pool='test', pool_guid='123',
                dataset='test/pv', dataset_guid='456', sync='STANDARD')


def backup():
    return dict(dataset_guid='456', captured_at=datetime.now(timezone.utc).isoformat(),
                coverage_reviewed_by='operator', critical_applications=['postgresql', 'sqlite-app'],
                archives=[dict(application=x, bytes=1024, sha256='a'*64, integrity='passed',
                               consistency='cold' if x != 'postgresql' else 'database-native',
                               restore='passed', evidence='private/restore-report.json')
                          for x in ['postgresql', 'sqlite-app']])


class FakeNAS:
    def __init__(self, **changes):
        self.guid='456'; self.pool_guid='123'; self.version=EXPECTED['version']
        self.sync='DISABLED'; self.source='LOCAL'; self.lose=False; self.stick=True
        self.fail_readback=False; self.calls=[]; self.updates=[]
        self.__dict__.update(changes)

    def call(self, method, *args):
        self.calls.append((method, args))
        if method == 'system.version': return self.version
        if method == 'pool.query': return [dict(name='test', guid=self.pool_guid, status='ONLINE')]
        if method == 'pool.dataset.query':
            if self.updates and self.fail_readback: raise TimeoutError('readback')
            return [dict(id='test/pv', guid=dict(value=self.guid),
                         sync=dict(value=self.sync, source=self.source), children=[])]
        if method == 'pool.dataset.update':
            self.updates.append(args)
            if self.stick: self.sync='STANDARD'
            if self.lose: raise TimeoutError('update')
            return {}
        raise AssertionError(method)


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.journal=Path(self.tmp.name)/'intent.jsonl'
        self.lock_root=Path(self.tmp.name)/'maintenance';self.lock_root.mkdir()
        (self.lock_root/'runner-instance').write_text('test-runner')
        env=patch.dict(os.environ,{'HOMELAB_RUNNER_INSTANCE':'test-runner','MAINTENANCE_OWNER':'tests/nfs'})
        env.start();self.addCleanup(env.stop)
        nonce=acquire(self.lock_root,'nfs-standard','tests/nfs')
        env2=patch.dict(os.environ,{'MAINTENANCE_NONCE':nonce});env2.start();self.addCleanup(env2.stop)
        # Redirect only the filesystem fixture; exercise the actual shared lock helper.
        root=patch('maintenance.Path',return_value=self.lock_root);root.start();self.addCleanup(root.stop)

    def test_missing_or_mismatched_ownership_never_updates(self):
        for variable,value in [('MAINTENANCE_NONCE','wrong'),('MAINTENANCE_OWNER','other'),('HOMELAB_RUNNER_INSTANCE','wrong')]:
            self.journal.unlink(missing_ok=True)
            nas=FakeNAS()
            with patch.dict(os.environ,{variable:value}),self.assertRaises((PermissionError,ValueError)):
                apply_standard(nas,EXPECTED,backup(),self.journal)
            self.assertFalse(nas.updates)
        self.journal.unlink(missing_ok=True)
        (self.lock_root/'operation.json').unlink()
        nas=FakeNAS()
        with self.assertRaises(FileNotFoundError):apply_standard(nas,EXPECTED,backup(),self.journal)
        self.assertFalse(nas.updates)

    def test_ownership_lost_after_intent_blocks_update(self):
        from nfs_sync import journal_event
        nas=FakeNAS()
        def lose(*args,**kwargs):
            journal_event(*args,**kwargs)
            if kwargs.get('create'):(self.lock_root/'operation.json').unlink()
        with patch('nfs_sync.journal_event',side_effect=lose),self.assertRaises(FileNotFoundError):
            apply_standard(nas,EXPECTED,backup(),self.journal)
        self.assertFalse(nas.updates)

    def test_inspect_never_mutates(self):
        nas=FakeNAS()
        self.assertEqual(inspect(nas, EXPECTED)['sync'], 'DISABLED')
        self.assertFalse(nas.updates)
        self.assertIn(('pool.dataset.query', ([['id', '=', 'test/pv']],
            {'extra': {'properties': ['guid', 'sync']}})), nas.calls)

    def test_wrong_identity_never_updates(self):
        for changes in [dict(guid='other'), dict(pool_guid='other'), dict(version='old')]:
            with self.subTest(changes=changes):
                nas=FakeNAS(**changes)
                with self.assertRaises(ValueError): apply_standard(nas, EXPECTED, backup(), self.journal)
                self.assertFalse(nas.updates)

    def test_success_readback_and_durable_intent(self):
        nas=FakeNAS()
        original=nas.call
        def check(method,*args):
            if method.endswith('.update'):
                self.assertEqual(json.loads(self.journal.read_text().splitlines()[0])['state'], 'intent')
                self.assertEqual(self.journal.stat().st_mode & 0o777, 0o600)
            return original(method,*args)
        nas.call=check
        result=apply_standard(nas,EXPECTED,backup(),self.journal)
        self.assertTrue(result['verified']); self.assertTrue(result['changed'])
        self.assertEqual(nas.updates, [('test/pv', {'sync':'STANDARD'})])
        self.assertEqual(json.loads(self.journal.read_text().splitlines()[-1])['state'],'verified')

    def test_already_standard_no_mutation_or_backup_needed(self):
        nas=FakeNAS(sync='STANDARD')
        self.assertFalse(apply_standard(nas,EXPECTED,{},self.journal)['changed'])
        self.assertFalse(nas.updates)

    def test_lost_reply_requires_explicit_reconciliation(self):
        nas=FakeNAS(lose=True)
        with self.assertRaises(TimeoutError): apply_standard(nas,EXPECTED,backup(),self.journal)
        with self.assertRaises(FileExistsError): apply_standard(nas,EXPECTED,backup(),self.journal)
        self.assertEqual(len(nas.updates),1)
        self.assertEqual(json.loads(self.journal.read_text().splitlines()[-1])['state'],'needs-reconciliation')
        self.assertTrue(reconcile(nas,EXPECTED,self.journal)['verified'])
        self.assertEqual(len(nas.updates),1)

    def test_reconcile_requires_matching_intent(self):
        self.journal.write_text(json.dumps(dict(state='intent', expected=dict(EXPECTED,dataset_guid='foreign')))+'\n')
        with self.assertRaises(ValueError): reconcile(FakeNAS(sync='STANDARD'),EXPECTED,self.journal)

    def test_reconcile_disabled_never_retries(self):
        nas=FakeNAS(stick=False,lose=True)
        with self.assertRaises(TimeoutError): apply_standard(nas,EXPECTED,backup(),self.journal)
        with self.assertRaises(RuntimeError): reconcile(nas,EXPECTED,self.journal)
        self.assertEqual(len(nas.updates),1)

    def test_failed_readback_has_no_success(self):
        for changes in [dict(stick=False),dict(fail_readback=True)]:
            self.journal.unlink(missing_ok=True)
            with self.subTest(changes=changes),self.assertRaises((RuntimeError,TimeoutError)):
                apply_standard(FakeNAS(**changes),EXPECTED,backup(),self.journal)
            self.assertNotIn('"state": "verified"',self.journal.read_text())

    def test_unexpected_or_inherited_policy_refused(self):
        for changes in [dict(sync='ALWAYS'),dict(source='INHERITED')]:
            nas=FakeNAS(**changes)
            with self.assertRaises(ValueError): apply_standard(nas,EXPECTED,backup(),self.journal)
            self.assertFalse(nas.updates)

    def test_backup_gate(self):
        cases=[{},dict(backup(),dataset_guid='other'),dict(backup(),archives=[]),
               dict(backup(),coverage_reviewed_by=''),dict(backup(),critical_applications=[]),
               dict(backup(),captured_at=(datetime.now(timezone.utc)-timedelta(days=2)).isoformat()),
               dict(backup(),captured_at=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat())]
        for key,value in [('restore','failed'),('integrity','failed'),('bytes',0),('sha256','bad'),
                          ('consistency','live-copy'),('evidence','')]:
            b=backup(); b['archives'][0][key]=value; cases.append(b)
        b=backup(); b['archives'].pop(); cases.append(b)
        for receipt in cases:
            with self.subTest(receipt=receipt):
                nas=FakeNAS()
                with self.assertRaises(ValueError): apply_standard(nas,EXPECTED,receipt,self.journal)
                self.assertFalse(nas.updates); self.assertFalse(self.journal.exists())

    def test_symlink_journal_refused(self):
        target=self.journal.with_suffix('.other');target.write_text('keep')
        self.journal.symlink_to(target)
        with self.assertRaises(FileExistsError): apply_standard(FakeNAS(),EXPECTED,backup(),self.journal)
        self.assertEqual(target.read_text(),'keep')


if __name__=='__main__': unittest.main()
