import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backup_reader import reader_pod, delete_reader

class ReaderTests(unittest.TestCase):
    def test_reader_mount_is_readonly_and_has_no_service_token(self):
        pod=reader_pod('owned', 'owner')
        self.assertTrue(pod['spec']['volumes'][0]['persistentVolumeClaim']['readOnly'])
        self.assertTrue(pod['spec']['containers'][0]['volumeMounts'][0]['readOnly'])
        self.assertFalse(pod['spec']['automountServiceAccountToken'])
        self.assertIn('@sha256:',pod['spec']['containers'][0]['image'])
    def test_wrong_uid_never_deleted(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'reader.json';path.write_text(json.dumps(dict(name='owned',uid='first')))
            calls=[]
            def api(*args,**kwargs):calls.append((args,kwargs));return dict(metadata=dict(name='owned',uid='replacement'))
            with patch('backup_reader.require_maintenance'),self.assertRaises(ValueError):delete_reader(api,path)
            self.assertEqual(len(calls),1)
    def test_delete_has_uid_precondition(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'reader.json';path.write_text(json.dumps(dict(name='owned',uid='first')))
            calls=[]
            def api(*args,**kwargs):calls.append((args,kwargs));return dict(metadata=dict(name='owned',uid='first'))
            with patch('backup_reader.require_maintenance'):delete_reader(api,path)
            self.assertEqual(calls[-1][1]['data']['preconditions']['uid'],'first')

if __name__=='__main__':unittest.main()
