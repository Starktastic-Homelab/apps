import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from onboard import onboard, reconcile_onboarding, snapshot_policy

INTENT=dict(service='jellyfin',dataset='apps/iscsi/jellyfin-config',pool_guid='pool',bytes=64*1024**3,
            initiators=['iqn.worker:a','iqn.worker:b'],auth_networks=['10.9.8.0/24'],portal='10.9.8.30:3260',
            portal_id=1,chap_tag=19701,pv='jellyfin-config-iscsi',pvc='jellyfin-config-iscsi',namespace='media',sync='STANDARD')
class NAS:
    def __init__(self,fail=None):
        self.objects={k:[] for k in ['iscsi.target','iscsi.extent','iscsi.initiator','iscsi.auth','iscsi.targetextent','pool.snapshottask']}
        self.objects['pool.snapshottask']=[dict(id=7,dataset='apps/pv',recursive=True,schedule={'minute':'0','hour':'*'},naming_schema='auto-%Y-%m-%d_%H-%M',lifetime_value=1,lifetime_unit='WEEK')]
        self.datasets={'apps':dict(id='apps',available=dict(parsed=400*1024**3))}
        self.mutations=[];self.fail=fail;self.enabled=False;self.running=False
    def call(self,method,*args):
        if method=='system.version':return 'TrueNAS-25.10.7'
        if method=='pool.query':return [dict(name='apps',guid='pool',status='ONLINE')]
        if method=='iscsi.global.config':return dict(basename='iqn.original')
        if method=='iscsi.portal.query':return [dict(id=1,listen=[dict(ip='10.9.8.30',port=3260)])]
        if method=='pool.dataset.query':
            if args and args[0] and args[0][0][0]=='type':return [d for d in self.datasets.values() if d.get('type')=='VOLUME']
            if args and args[0]:return [copy.deepcopy(self.datasets[args[0][0][2]])] if args[0][0][2] in self.datasets else []
            return list(self.datasets.values())
        if method=='service.query':return [dict(id=1,service='iscsitarget',enable=self.enabled,state='RUNNING' if self.running else 'STOPPED')]
        if method.endswith('.query'):return copy.deepcopy(self.objects[method[:-6]])
        self.mutations.append(method)
        if method=='pool.dataset.create':
            data=args[0];result=dict(id=data['name'],type=data['type'],guid=dict(value='guid'),volsize=dict(parsed=data.get('volsize')),sync=dict(value='STANDARD',source='LOCAL'),volblocksize=dict(value='16K'))
            self.datasets[data['name']]=result
        elif method=='service.update':self.enabled=True;result={}
        elif method=='service.start':self.running=True;result=True
        else:
            data=args[0];result=dict(data,id=len(self.mutations),serial=data.get('serial'),naa='naa')
            self.objects[method[:-7]].append(result)
        if self.fail==len(self.mutations):raise TimeoutError('lost reply after commit')
        return result

class OnboardTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)/'intent.jsonl'
        patcher=patch('onboard.require_maintenance');patcher.start();self.addCleanup(patcher.stop)
        patcher=patch('onboard.read_chap',return_value={'user':'jellyfin','secret':'do-not-log-secret'});patcher.start();self.addCleanup(patcher.stop)
    def test_single_allocation_preserves_basename_and_credentials(self):
        nas=NAS();record=onboard(nas,INTENT,self.path)
        self.assertEqual(record['iqn'],'iqn.original:jellyfin')
        self.assertNotIn('iscsi.global.update',nas.mutations)
        self.assertNotIn('do-not-log-secret',self.path.read_text())
        self.assertNotIn('filesystem_uuid',record)
    def test_lost_reply_after_every_mutation_never_reallocates(self):
        completed=NAS();onboard(completed,INTENT,self.path)
        for count in range(1,len(completed.mutations)+1):
            self.path.unlink();nas=NAS(fail=count)
            with self.subTest(count=count),self.assertRaises(TimeoutError):onboard(nas,INTENT,self.path)
            before=len(nas.mutations)
            with self.assertRaises(FileExistsError):onboard(nas,INTENT,self.path)
            self.assertEqual(len(nas.mutations),before)
    def test_existing_foreign_target_refused(self):
        nas=NAS();nas.datasets[INTENT['dataset']]=dict(id=INTENT['dataset'])
        with self.assertRaises(ValueError):onboard(nas,INTENT,self.path)
        self.assertFalse(nas.mutations)
    def test_wrong_pool_or_capacity_never_allocates(self):
        for intent in [dict(INTENT,pool_guid='other'),dict(INTENT,bytes=1),dict(INTENT,auth_networks=['0.0.0.0/0'])]:
            nas=NAS()
            with self.assertRaises(ValueError):onboard(nas,intent,self.path)
            self.assertFalse(nas.mutations)
    def test_snapshot_lost_reply_reconciles_without_create(self):
        nas=NAS(fail=1)
        with self.assertRaises(TimeoutError):snapshot_policy(nas,self.path,pool_guid='pool')
        self.assertEqual(snapshot_policy(nas,self.path,reconcile=True,pool_guid='pool')['verified'],True)
        self.assertEqual(nas.mutations,['pool.snapshottask.create'])
    def test_snapshot_wrong_dataset_or_conflicting_policy_refused(self):
        nas=NAS();nas.objects['pool.snapshottask'].append(dict(nas.objects['pool.snapshottask'][0],dataset='apps/iscsi',recursive=False))
        with self.assertRaises(ValueError):snapshot_policy(nas,self.path,pool_guid='pool')
        self.assertFalse(nas.mutations)

if __name__=='__main__':unittest.main()
