import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cutover_guards import verify_target_hold, mark_possible_write
from render_storage import render
from test_render_storage import RECORD

class CutoverTests(unittest.TestCase):
    def test_reconciled_hold_and_exact_bindings_required(self):
        app={'status':{'sync':{'status':'Synced','revisions':['a'*40]}}}
        pv,pvc=render(RECORD)[:2];pv['status']={'phase':'Bound'};pvc['status']={'phase':'Bound'}
        pv['spec']['capacity']['storage']='64Gi';pvc['spec']['resources']['requests']['storage']='64Gi'
        verify_target_hold(RECORD,{'target-held':'a'*40},app,pv,pvc)
        wrong=copy.deepcopy(pv);wrong['spec']['csi']['volumeAttributes']['iqn']='foreign'
        with self.assertRaises(ValueError):verify_target_hold(RECORD,{'target-held':'a'*40},app,wrong,pvc)
        with self.assertRaises(ValueError):verify_target_hold(RECORD,{'target-held':'b'*40},app,pv,pvc)
        wrong=copy.deepcopy(pvc);wrong['spec']['resources']['requests']['storage']='1Gi'
        with self.assertRaises(ValueError):verify_target_hold(RECORD,{'target-held':'a'*40},app,pv,wrong)
    def test_first_release_latch_is_durable_and_cannot_change_identity(self):
        with tempfile.TemporaryDirectory() as d,patch('cutover_guards.require_maintenance'):
            path=Path(d)/'target-may-have-written.json'
            mark_possible_write(RECORD,path)
            first=path.read_bytes();mark_possible_write(RECORD,path);self.assertEqual(first,path.read_bytes())
            self.assertTrue(json.loads(first)['target_may_have_written'])
            with self.assertRaises(ValueError):mark_possible_write(dict(RECORD,marker='changed'),path)

if __name__=='__main__':unittest.main()
