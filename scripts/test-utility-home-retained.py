#!/usr/bin/env python3
"""Retained native identities must refuse empty, corrupt or redirected stores."""
from pathlib import Path
import hashlib, importlib.util, json, os, tempfile, unittest, copy
import yaml
ROOT=Path(__file__).resolve().parents[1]
GUARD=ROOT/'scripts/utility-home-retained/guard.py'
LAYOUTS={
 'qbittorrent':{'qBittorrent/qBittorrent.conf':b'[BitTorrent]\nSession\\Port=56881\n','qBittorrent/categories.json':b'{}','qBittorrent/BT_backup/':None,'modcache/':None},
 'qbittorrent-ru':{'qBittorrent/qBittorrent.conf':b'[BitTorrent]\nSession\\Port=56882\n','qBittorrent/categories.json':b'{}','qBittorrent/BT_backup/':None,'modcache/':None},
 'changedetection':{'changedetection.json':b'{"watching":{},"settings":{}}','secret.txt':b'a'*64},
 'stirling-pdf':{'settings.yml':b'security:\n  enableLogin: false\n','stirling-pdf-DB-2.3.232.mv.db':b'H:2,block:2,blockSize:1000'},
 'microbin':{'database.sqlite':b'SQLite format 3\0'+b'\0'*84,'attachments/':None},
 'lingarr':{'local.db':b'SQLite format 3\0'+b'\0'*84,'Hangfire.db':b'SQLite format 3\0'+b'\0'*84,'keys/':None},
 'mosquitto':{'mosquitto.db':b'\x00\xb5\x00mosquitto db'+b'\0'*4+b'\0\0\0\6'+b'\0\0\0\1\0\0\0\20'+b'\0'*8+b'\1\10'+b'\0'*6},
 'zigbee2mqtt':{'configuration.yaml':b'version: 5\n','database.db':b'{"id":1,"type":"Coordinator"}\n','coordinator_backup.json':b'{"metadata":{"format":"zigpy/open-coordinator-backup","version":1}}','state.json':b'{}'}}

class Guard(unittest.TestCase):
 def check(self,app,change=None,accepted=False):
  if not GUARD.is_file():self.fail('Retained utility startup guard is missing')
  spec=importlib.util.spec_from_file_location('guard',GUARD);g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
  with tempfile.TemporaryDirectory() as tmp:
   r=Path(tmp)/'state';r.mkdir();m=r/('.homelab-'+app+'-data');m.write_text('homelab/'+app+'/data/v1\n')
   for name,value in LAYOUTS[app].items():
    p=r/name;p.parent.mkdir(parents=True,exist_ok=True)
    if value is None:p.mkdir()
    else:p.write_bytes(value)
   if change:change(r,m)
   def snapshot():return {str(p.relative_to(r)):(p.lstat().st_mode,hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() and not p.is_symlink() else None)for p in r.rglob('*')}
   before=snapshot()
   if accepted:g.validate(app,r)
   else:
    with self.assertRaises((OSError,ValueError)):g.validate(app,r)
   self.assertEqual(snapshot(),before)
 def test_native_layouts_are_accepted_without_writes(self):
  for a in LAYOUTS:
   with self.subTest(app=a):self.check(a,accepted=True)
 def test_each_native_file_is_required(self):
  for a,files in LAYOUTS.items():
   for n,v in files.items():
    if v is not None:
     with self.subTest(app=a,path=n):self.check(a,lambda r,m:(r/n).unlink())
 def test_wrong_missing_empty_linked_markers_refuse(self):
  for a in LAYOUTS:
   for value in ('','homelab/other/data/v1\n','x'*129):self.check(a,lambda r,m:m.write_text(value))
   self.check(a,lambda r,m:m.unlink())
   def linked(r,m):
    p=r.parent/'identity';p.write_bytes(m.read_bytes());m.unlink();m.symlink_to(p)
   self.check(a,linked)
 def test_corrupt_native_formats_refuse(self):
  for a,n in [('qbittorrent','qBittorrent/categories.json'),('changedetection','changedetection.json'),('microbin','database.sqlite'),('lingarr','Hangfire.db'),('stirling-pdf','stirling-pdf-DB-2.3.232.mv.db'),('mosquitto','mosquitto.db'),('zigbee2mqtt','database.db'),('zigbee2mqtt','coordinator_backup.json')]:
   with self.subTest(app=a,path=n):self.check(a,lambda r,m:(r/n).write_bytes(b'corrupt'))
 def test_empty_device_database_cannot_initialize_a_new_network(self):
  self.check('zigbee2mqtt',lambda r,m:(r/'database.db').write_bytes(b' \n\n'))
 def test_truncated_mqtt_persistence_cannot_look_like_an_empty_store(self):
  self.check('mosquitto',lambda r,m:(r/'mosquitto.db').write_bytes((r/'mosquitto.db').read_bytes()[:23]))
 def test_linked_parent_and_fifo_refuse_without_blocking(self):
  def linked(r,m):
   p=r/'qBittorrent';o=r.parent/'other';p.rename(o);p.symlink_to(o)
  self.check('qbittorrent',linked)
  def fifo(r,m):
   p=r/'mosquitto.db';p.unlink();os.mkfifo(p)
  self.check('mosquitto',fifo)

class Manifests(unittest.TestCase):
 def test_embedded_guard_exact_in_all_three_namespaces(self):
  for ns in ('media','operations','home-automation'):
   cm=yaml.safe_load((ROOT/'scripts/utility-home-retained/production'/('guard-'+ns+'.yaml')).read_text())
   self.assertEqual(cm['metadata']['namespace'],ns);self.assertEqual(cm['data']['guard.py'],GUARD.read_text())
 def test_static_claims_have_fixed_growth_and_single_writer(self):
  sizes=[]
  for p in (ROOT/'scripts/utility-home-retained/production').glob('*-bindings.yaml'):
   pv,pvc=list(yaml.safe_load_all(p.read_text()));s=pv['spec'];sizes.append(int(s['capacity']['storage'][:-2]));self.assertEqual(s['accessModes'],['ReadWriteOncePod']);self.assertEqual(s['persistentVolumeReclaimPolicy'],'Retain');self.assertEqual(s['csi']['driver'],'csi.proxmox.sinextra.dev');self.assertEqual(s['csi']['fsType'],'ext4');self.assertIn('/9999/vm-9999-',s['csi']['volumeHandle']);self.assertEqual(pvc['spec']['volumeName'],pv['metadata']['name']);self.assertEqual(s['claimRef']['namespace'],pvc['metadata']['namespace'])
  self.assertEqual(len(sizes),8);self.assertEqual(sum(sizes),9)
 def test_rendered_application_behavior_and_shared_mounts_preserved(self):
  if not os.environ.get('UTILITY_HOME_RENDERS'):self.skipTest('Set UTILITY_HOME_RENDERS to actual layered render output')
  out=Path(os.environ['UTILITY_HOME_RENDERS'])
  for app in LAYOUTS:
   with self.subTest(app=app):
    before=[x for x in yaml.safe_load_all((out/(app+'-before.yaml')).read_text())if x];after=[x for x in yaml.safe_load_all((out/(app+'.yaml')).read_text())if x];old=next(x for x in before if x['kind']=='Deployment')['spec']['template']['spec'];new=next(x for x in after if x['kind']=='Deployment')['spec']['template']['spec'];source=yaml.safe_load((ROOT/'scripts/utility-home-retained/production'/(app+'-values.yaml')).read_text());oldvolume=next(k for k,v in source['persistence'].items()if v.get('enabled')is False)
    self.assertEqual(new['automountServiceAccountToken'],False);self.assertEqual(new['initContainers'][0]['name'],'retained-data');self.assertEqual(new['initContainers'][0]['command'][-2:],[app,'/retained']);self.assertTrue(all(m.get('readOnly')for m in new['initContainers'][0]['volumeMounts']))
    for before_container in old['containers']:
     current=next(c for c in new['containers']if c['name']==before_container['name']);a=copy.deepcopy(before_container);b=copy.deepcopy(current);left=a.pop('volumeMounts',[]);right=b.pop('volumeMounts',[]);self.assertEqual(a,b)
     for mount in left:
      if mount['name']==oldvolume:mount['name']='retained-config'
     key=lambda m:(m['mountPath'],m['name']);self.assertEqual(sorted(left,key=key),sorted(right,key=key))
    old_services={x['metadata']['name']:x for x in before if x['kind']=='Service'};new_services={x['metadata']['name']:x for x in after if x['kind']=='Service'};self.assertEqual(old_services,new_services)
if __name__=='__main__':unittest.main()

