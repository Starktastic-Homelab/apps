import copy
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from render_storage import render, record_hash, placement
from test_identity import R

RECORD=dict(R,marker='aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',filesystem_uuid='bbbbbbbb-cccc-dddd-eeee-ffffffffffff')
NODE=dict(hostname='worker-a',node_uid='node-a',smbios_uuid='vm-a')
class RenderTests(unittest.TestCase):
    def test_no_invented_ids(self):
        intent=json.loads((Path(__file__).resolve().parents[3]/'storage/services/jellyfin.json').read_text())
        with self.assertRaises(ValueError):render(intent)
    def test_retained_explicit_bindings_without_runtime_metadata(self):
        objects=render(RECORD);pv=next(o for o in objects if o['kind']=='PersistentVolume');pvc=next(o for o in objects if o['kind']=='PersistentVolumeClaim')
        self.assertEqual(pv['spec']['persistentVolumeReclaimPolicy'],'Retain')
        self.assertEqual(pv['spec']['accessModes'],['ReadWriteOncePod'])
        self.assertEqual(pv['spec']['csi']['fsType'],'ext4')
        self.assertEqual(pvc['spec']['volumeName'],pv['metadata']['name'])
        self.assertEqual(pvc['spec']['storageClassName'],'')
        for obj in [pv,pvc]:
            self.assertNotIn('uid',obj['metadata']);self.assertIn('Prune=false',obj['metadata']['annotations']['argocd.argoproj.io/sync-options'])
        self.assertNotIn('uid',pv['spec']['claimRef'])
        self.assertNotIn('secret',json.dumps(pv['spec']['csi']['volumeAttributes']))
        self.assertFalse(any(o['kind'] in ['StorageClass','ConfigMap','Secret'] for o in objects))
    def test_exact_one_worker_affinity(self):
        terms=placement(NODE)['nodeAffinity']['requiredDuringSchedulingIgnoredDuringExecution']['nodeSelectorTerms']
        self.assertEqual(len(terms),1)
        self.assertEqual(len(terms[0]['matchExpressions']),3)
    def test_record_hash_changes_with_identity(self):
        self.assertNotEqual(record_hash(RECORD),record_hash(dict(RECORD,naa='other')))

if __name__=='__main__':unittest.main()
