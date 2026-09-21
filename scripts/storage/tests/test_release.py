import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from release import authorize, hold
from render_storage import record_hash
from test_render_storage import RECORD,NODE

def evidence():
    return dict(record_hash=record_hash(RECORD),namespace_uid='namespace-new',node=NODE,held=True,
                native_verified=True,filesystem_verified=True,filesystem_uuid=RECORD['filesystem_uuid'],marker=RECORD['marker'],
                chap_present=True,free_bytes=30*1024**3,eviction_checked=True,
                observed_at=datetime.now(timezone.utc).isoformat(),
                old_writer=dict(kind='clean-unmount',verified=True,mounts=0,sessions=0,
                                observed_at=datetime.now(timezone.utc).isoformat()))
class ReleaseTests(unittest.TestCase):
    def setUp(self):
        p=patch('release.require_maintenance');p.start();self.addCleanup(p.stop)
    def test_complete_fresh_verification_authorizes_exact_generation(self):
        cm=authorize(RECORD,evidence(),'namespace-new',NODE)
        self.assertEqual(cm['data']['nodeUID'],'node-a');self.assertEqual(cm['data']['released'],'true')
        self.assertEqual(cm['data']['namespaceUID'],'namespace-new')
    def test_missing_or_changed_evidence_keeps_closed(self):
        for key,value in [('held',False),('native_verified',False),('chap_present',False),('filesystem_uuid','foreign'),
                          ('namespace_uid','old'),('marker','wrong'),('free_bytes',1),('record_hash','other'),('node',dict(NODE,node_uid='old'))]:
            verification=evidence();verification[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):authorize(RECORD,verification,'namespace-new',NODE)
    def test_uncertain_or_stale_old_writer_refused(self):
        for old in [dict(kind='unknown'),dict(kind='clean-unmount',verified=True,mounts=0,sessions=1),
                    dict(kind='fenced',verified=True,current_status='running'),
                    dict(kind='fenced',verified=True,current_status='stopped',observed_at=(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat())]:
            v=evidence();v['old_writer']=old
            with self.assertRaises(ValueError):authorize(RECORD,v,'namespace-new',NODE)
    def test_current_matching_fence_can_replace_clean_unmount(self):
        v=evidence();v['old_writer']=dict(kind='fenced',verified=True,current_status='stopped',generation_matches=True,
            observed_at=datetime.now(timezone.utc).isoformat())
        self.assertEqual(authorize(RECORD,v,'namespace-new',NODE)['data']['released'],'true')
    def test_hold_is_always_closed(self):self.assertEqual(hold(RECORD)['data']['released'],'false')

if __name__=='__main__':unittest.main()
