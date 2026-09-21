import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from identity import verify_native
R=dict(service='jellyfin',marker='test-marker',dataset='apps/iscsi/jellyfin-config',pool_guid='pool',zvol_guid='zvol',bytes=64*1024**3,
       extent_id=2,serial='serial',naa='naa',target_id=3,iqn='iqn.test:jellyfin',lun=0,portal='10.9.8.30:3260',
       initiators=['iqn.worker:a','iqn.worker:b'],auth_networks=['10.9.8.0/24'],
       group=dict(portal=1,initiator=4,authmethod='CHAP',auth=5),chap_user='jellyfin',
       pv='jellyfin-config-iscsi',pvc='jellyfin-config-iscsi',namespace='media',sync='STANDARD',filesystem_uuid='test-fs')
S=dict(version='TrueNAS-25.10.7',basename='iqn.test',pools=[dict(name='apps',guid='pool',status='ONLINE')],
       datasets=[dict(id=R['dataset'],guid=dict(value='zvol'),volsize=dict(parsed=R['bytes']),sync=dict(value='STANDARD',source='LOCAL'),volblocksize=dict(value='16K'))],
       extents=[dict(id=2,name='jellyfin',disk='zvol/'+R['dataset'],serial='serial',naa='naa',enabled=True,ro=False,insecure_tpc=False,blocksize=512)],
       mappings=[dict(id=6,target=3,extent=2,lunid=0)],targets=[dict(id=3,name='jellyfin',groups=[R['group']],auth_networks=R['auth_networks'])],
       portals=[dict(id=1,listen=[dict(ip='10.9.8.30',port=3260)])],initiators=[dict(id=4,initiators=R['initiators'])],auth=[dict(tag=5,user='jellyfin')])
class IdentityTests(unittest.TestCase):
    def test_valid(self):verify_native(R,S)
    def test_changed_native_identity_refused(self):
        changes=[('datasets','guid',dict(value='other')),('datasets','sync',dict(value='DISABLED',source='LOCAL')),
                 ('datasets','volsize',dict(parsed=1)),('extents','serial','other'),('extents','naa','other'),
                 ('extents','disk','zvol/foreign'),('extents','blocksize',4096),('extents','insecure_tpc',True),
                 ('targets','auth_networks',['0.0.0.0/0']),('targets','name','alias'),('initiators','initiators',['ALL']),
                 ('portals','listen',[dict(ip='10.9.8.30',port=3260),dict(ip='0.0.0.0',port=3260)])]
        for section,key,value in changes:
            state=copy.deepcopy(S);state[section][0][key]=value
            with self.subTest(section=section,key=key),self.assertRaises(ValueError):verify_native(R,state)
    def test_duplicate_or_aliased_mapping_refused(self):
        for mapping in [dict(S['mappings'][0]),dict(S['mappings'][0],target=99)]:
            state=copy.deepcopy(S);state['mappings'].append(mapping)
            with self.assertRaises(ValueError):verify_native(R,state)
    def test_missing_any_native_object_refused(self):
        for section in ['datasets','extents','targets','mappings','portals','initiators','auth','pools']:
            state=copy.deepcopy(S);state[section]=[]
            with self.subTest(section=section),self.assertRaises(ValueError):verify_native(R,state)

if __name__=='__main__':unittest.main()
