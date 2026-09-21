import copy
from pathlib import Path
import sys
import unittest
import yaml
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from jellyfin_stages import stage_values, validate_rollback
from test_render_storage import RECORD,NODE
ROOT=Path(__file__).resolve().parents[3]

class StageTests(unittest.TestCase):
    def setUp(self):self.values=yaml.safe_load((ROOT/'services/media/jellyfin/values.yaml').read_text())
    def test_source_hold_keeps_original_claim_and_image(self):
        held=stage_values(self.values,'source-held')
        self.assertEqual(held['controllers']['main']['replicas'],0)
        self.assertEqual(held['persistence'],self.values['persistence'])
        self.assertEqual(held['controllers']['main']['containers'],self.values['controllers']['main']['containers'])
    def test_target_refuses_incomplete_record(self):
        with self.assertRaises(ValueError):stage_values(self.values,'target-held',{},NODE)
    def test_target_preserves_app_and_uses_one_shared_disposable_budget(self):
        for stage,count in [('target-held',0),('target-released',1)]:
            target=stage_values(self.values,stage,RECORD,NODE)
            controller=target['controllers']['main'];main=controller['containers']['main']
            self.assertEqual(controller['replicas'],count);self.assertEqual(controller['strategy'],'Recreate')
            for key in ('image','probes'):self.assertEqual(main[key],self.values['controllers']['main']['containers']['main'][key])
            self.assertEqual(main['resources']['limits']['gpu.intel.com/i915'],'1')
            self.assertEqual(main['resources']['requests']['ephemeral-storage'],'12Gi')
            self.assertEqual(main['resources']['limits']['ephemeral-storage'],'12Gi')
            self.assertEqual(target['persistence']['jellyfin-config']['existingClaim'],RECORD['pvc'])
            self.assertFalse(target['persistence']['jellyfin-cache']['enabled'])
            self.assertEqual(target['persistence']['disposable']['sizeLimit'],'10Gi')
            self.assertEqual(target['persistence']['media'],self.values['persistence']['media'])
    def test_rollback_fails_closed_after_possible_first_write(self):
        with self.assertRaises(ValueError):validate_rollback(True,{'quiescent':True,'claim':'jellyfin-config'})
        with self.assertRaises(ValueError):validate_rollback(False,{'quiescent':False,'claim':'jellyfin-config'})
        validate_rollback(False,{'quiescent':True,'claim':'jellyfin-config'})
        validate_rollback(True,{'quiescent':True,'claim':'jellyfin-config-rollback-20260921',
                              'path':'/mnt/apps/pv/media/jellyfin-rollback-20260921','latest_target_restore_verified':True})

if __name__=='__main__':unittest.main()
