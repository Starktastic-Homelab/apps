"""Capture native identities once; retries must reconcile the existing record."""
import json
import uuid
from lab import ROOT, PRIVATE, kubectl, apply, receipt
from lifecycle import export_pv
from nas_rpc import NAS

assert not (ROOT/'records.json').exists(), 'Record exists: reconcile, never recapture identity blindly'
n=NAS()
pvs=json.loads(kubectl('get','pv','-o','json').stdout)['items']
ds=n.call('pool.dataset.query',[['id','^','iscsi_lab/volumes/']],{'extra':{'properties':['guid','volsize']}})
assert len(pvs)==len(ds)==2
extents=n.call('iscsi.extent.query');mappings=n.call('iscsi.targetextent.query');targets=n.call('iscsi.target.query')
records=[];resources=[]
for pv in pvs:
 exported=export_pv(pv);spec=exported['spec'];name=spec['claimRef']['name']
 dataset=next(d for d in ds if d['id']=='iscsi_lab/volumes/'+spec['csi']['volumeHandle'])
 extent=next(e for e in extents if e['disk']=='zvol/'+dataset['id'])
 mapping=next(m for m in mappings if m['extent']==extent['id'])
 target=next(t for t in targets if t['id']==mapping['target'])
 assert spec['csi']['volumeAttributes']['iqn']=='iqn.2026-09.lab.iscsi:'+target['name']
 assert int(spec['csi']['volumeAttributes']['lun'])==mapping['lunid']
 claim={'apiVersion':'v1','kind':'PersistentVolumeClaim','metadata':{'name':name,'namespace':'iscsi-fixture','annotations':{'argocd.argoproj.io/sync-options':'Prune=false,Delete=false'}},'spec':{'volumeName':exported['metadata']['name'],'storageClassName':spec['storageClassName'],'accessModes':['ReadWriteOncePod'],'resources':{'requests':spec['capacity']}}}
 records.append({'service':name,'marker':str(uuid.uuid4()),'pv':exported,'pvc':claim,'backend':{'dataset':dataset['id'],'guid':dataset['guid']['value'],'bytes':dataset['volsize']['parsed'],'extent_id':extent['id'],'serial':extent['serial'],'naa':extent['naa'],'target_id':target['id'],'lun':mapping['lunid']}})
 resources.extend([exported,claim])
# External durable capture precedes adoption and any writes.
with (ROOT/'records.json').open('x') as f:
 json.dump(records,f,indent=2);f.flush();__import__('os').fsync(f.fileno())
receipt({'operation':'export','claims':[r['service'] for r in records],'state':'captured'})
print(apply(resources).stdout)
print('Correlated and saved two distinct retained mappings; adopted existing PVs/PVCs with SSA.')
