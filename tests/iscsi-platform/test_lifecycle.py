import copy
import pathlib
import sqlite3
import tempfile
import unittest
from lifecycle import export_pv, verify_database

PV={'metadata':{'name':'pv-a','uid':'old'},'spec':{'capacity':{'storage':'2Gi'},'accessModes':['ReadWriteOncePod'],'storageClassName':'iscsi-lab-retain','persistentVolumeReclaimPolicy':'Retain','claimRef':{'name':'service-a','namespace':'iscsi-fixture','uid':'old-claim'},'csi':{'driver':'org.democratic-csi.iscsi-lab','volumeHandle':'actual-native-handle','fsType':'ext4','volumeAttributes':{'iqn':'iqn.a','lun':'0','portal':'172.30.91.10:3260'},'nodeStageSecretRef':{'name':'iscsi-lab-chap','namespace':'iscsi-lab-system'}}}}
class LifecycleTests(unittest.TestCase):
 def test_export_strips_cluster_identity(self):
  p=export_pv(PV)
  self.assertNotIn('uid',p['metadata']);self.assertNotIn('uid',p['spec']['claimRef'])
  self.assertEqual(p['spec']['csi'],PV['spec']['csi'])
 def test_inline_secret_or_unexpected_attribute_rejected(self):
  for key in ('password','apiKey','unknown'):
   p=copy.deepcopy(PV);p['spec']['csi']['volumeAttributes'][key]='sensitive'
   with self.assertRaises(ValueError):export_pv(p)
 def test_wrong_driver_or_non_retained_rejected(self):
  p=copy.deepcopy(PV);p['spec']['csi']['driver']='foreign'
  with self.assertRaises(ValueError):export_pv(p)
  p=copy.deepcopy(PV);p['spec']['persistentVolumeReclaimPolicy']='Delete'
  with self.assertRaises(ValueError):export_pv(p)
 def test_missing_database_never_created(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d)/'db.sqlite'
   with self.assertRaises((ValueError,sqlite3.OperationalError)):verify_database(p,'a')
   self.assertFalse(p.exists())
 def test_wrong_marker_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d)/'db.sqlite'
   c=sqlite3.connect(p);c.execute('create table identity(marker text)');c.execute("insert into identity values('a')");c.commit();c.close()
   with self.assertRaises(ValueError):verify_database(p,'b')
   verify_database(p,'a')

class BackendIdentityTests(unittest.TestCase):
 def test_missing_or_redirected_backend_rejected(self):
  from lifecycle import verify_backend
  record={'backend':{'dataset':'pool/vol','guid':'7','extent_id':1,'serial':'serial','naa':'naa','target_id':2,'lun':0},'pv':{'spec':{'csi':{'volumeAttributes':{'iqn':'iqn.base:target','lun':'0'}}}}}
  ds=[{'id':'pool/vol','guid':{'value':'7'},'volsize':{'parsed':2147483648}}]
  extent={'id':1,'disk':'zvol/pool/vol','serial':'serial','naa':'naa'}
  targets=[{'id':2,'name':'target'}];mappings=[{'extent':1,'target':2,'lunid':0}]
  self.assertEqual(verify_backend(record,ds,[extent],targets,mappings,'iqn.base'),2147483648)
  with self.assertRaises(ValueError):verify_backend(record,[],[extent],targets,mappings,'iqn.base')
  with self.assertRaises(ValueError):verify_backend(record,ds,[{**extent,'disk':'zvol/foreign'}],targets,mappings,'iqn.base')
  with self.assertRaises(ValueError):verify_backend(record,[{**ds[0],'guid':{'value':'8'}}],[extent],targets,mappings,'iqn.base')
