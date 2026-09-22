import base64
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import maintenance_cli
from jellyfin_stages import generate
from test_render_storage import RECORD,NODE

ROOT=Path(__file__).resolve().parents[3]
PREFIX='node-db.node.session.auth.'
class CsiChapTests(unittest.TestCase):
    def setUp(self):
        self.expected={'user':'test-user','secret':'test-password'}
        self.data={PREFIX+k:base64.b64encode(v.encode()).decode() for k,v in [('authmethod','CHAP'),('username','test-user'),('password','test-password')]}
    def test_recovered_credentials_match_driver_contract(self):
        maintenance_cli.verify_recovered_chap(self.data,self.expected)
    def test_legacy_missing_method_and_wrong_credentials_refused(self):
        for data in ({k.removeprefix('node-db.'):v for k,v in self.data.items()},
                     {k:v for k,v in self.data.items() if not k.endswith('authmethod')},
                     dict(self.data,**{PREFIX+'authmethod':base64.b64encode(b'None').decode()}),
                     dict(self.data,**{PREFIX+'password':base64.b64encode(b'wrong').decode()})):
            with self.subTest(keys=list(data)),self.assertRaises(ValueError):maintenance_cli.verify_recovered_chap(data,self.expected)
    def generate(self,keys):
        sealed={'kind':'SealedSecret','metadata':{'name':'retained-jellyfin-chap','namespace':'retained-iscsi'},'spec':{'encryptedData':{k:'ciphertext' for k in keys}}}
        passed={'files_verified':True,'sqlite_verified':True,'application_verified':True,'archive_sha256':'a'*64}
        with tempfile.TemporaryDirectory() as tmp:generate(ROOT,Path(tmp)/'stage','target-held',RECORD,NODE,passed,sealed)
    def test_generator_accepts_actual_csi_keys(self):self.generate(self.data)
    def test_generator_refuses_legacy_and_missing_method(self):
        for keys in ([k.removeprefix('node-db.') for k in self.data],[k for k in self.data if not k.endswith('authmethod')]):
            with self.subTest(keys=keys),self.assertRaises(ValueError):self.generate(keys)
