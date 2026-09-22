import base64
import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from jellyfin_backup import portable_entry

# Exact NFS attributes observed on the POSIX-backed source, not generated fixtures.
FILE644='00000003000000000000000000160187000000064f574e45524000000000000000000000001200810000000647524f55504000000000000000000000001200810000000945564552594f4e4540000000'
DIR755='000000030000000000000000001601e7000000064f574e45524000000000000000000000001200a10000000647524f55504000000000000000000000001200a10000000945564552594f4e4540000000'
class NFSModeACLTests(unittest.TestCase):
 def entry(self,hex_acl=FILE644,mode=0o644,kind='file'):
  return dict(type=kind,mode=mode,uid=1000,gid=1000,xattrs={'system.nfs4_acl':base64.b64encode(bytes.fromhex(hex_acl)).decode(),'user.keep':'eA=='})
 def test_exact_mode_acl_is_portable_without_changing_original(self):
  for acl,mode,kind in [(FILE644,0o644,'file'),(DIR755,0o755,'directory')]:
   original=self.entry(acl,mode,kind);saved=copy.deepcopy(original);result=portable_entry(original)
   self.assertEqual(result,dict(saved,xattrs={'user.keep':'eA=='}));self.assertEqual(original,saved)
 def test_acl_mismatch_named_flags_extra_entries_and_malformed_refused(self):
  for raw in [bytes.fromhex(FILE644)[:-1],bytes.fromhex(FILE644)+b'\0',bytes.fromhex(FILE644).replace(b'OWNER@',b'alice@'),bytes.fromhex(FILE644)[:11]+b'\1'+bytes.fromhex(FILE644)[12:]]:
   e=self.entry();e['xattrs']['system.nfs4_acl']=base64.b64encode(raw).decode()
   with self.subTest(raw=raw),self.assertRaises(ValueError):portable_entry(e)
  for mode in [0o600,0o640,0o4644]:
   with self.subTest(mode=mode),self.assertRaises(ValueError):portable_entry(self.entry(mode=mode))
 def test_unrelated_attributes_unchanged(self):
  e=self.entry();del e['xattrs']['system.nfs4_acl'];self.assertEqual(portable_entry(e),e)
if __name__=='__main__':unittest.main()
