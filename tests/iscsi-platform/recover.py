"""Recover only captured backends; never issue CreateVolume for established state."""
import json
from lab import ROOT, PRIVATE, kubectl, apply, receipt
from nas_rpc import NAS
from lifecycle import verify_backend

records=json.loads((ROOT/'records.json').read_text())
n=NAS()
existing=json.loads(kubectl('get','pv','-o','json').stdout)['items']
assert not existing, 'Recovery requires an empty new cluster; reconcile existing PVs'
extents=n.call('iscsi.extent.query');targets=n.call('iscsi.target.query');mappings=n.call('iscsi.targetextent.query');basename=n.call('iscsi.global.config')['basename']
for r in records:
 ds=n.call('pool.dataset.query',[['id','=',r['backend']['dataset']]],{'extra':{'properties':['guid','volsize']}})
 actual=verify_backend(r,ds,extents,targets,mappings,basename)
 expected=r['backend']['bytes']
 if actual!=expected:
  pending=[json.loads(x) for x in (PRIVATE/'operations.jsonl').read_text().splitlines() if json.loads(x).get('service')==r['service'] and json.loads(x).get('state')=='interrupted-before-filesystem-and-record']
  assert len(pending)==1 and pending[0]['backend_bytes']==actual,'Unexplained capacity mismatch; startup blocked'
  receipt({'operation':'reconcile-resize','service':r['service'],'same_guid':True,'actual_backend_bytes':actual,'action':'resume native expansion after binding'})
resources=[{'apiVersion':'v1','kind':'Namespace','metadata':{'name':'iscsi-fixture'}}]
for r in records:resources.extend([r['pv'],r['pvc']])
print(apply(resources).stdout)
print('Restored explicit PV/PVC identities; no dynamic allocation requested.')
