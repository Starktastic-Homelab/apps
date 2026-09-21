"""External snapshot/clone with intentionally lost response and retained ACLs."""
import json,time,uuid,shlex
from lab import PRIVATE,ROOT,receipt
from nas_rpc import NAS
from identity import verify_native
from verify_recovery import capture
from ssh import ssh
from quiescence import require_quiesced
require_quiesced()
n=NAS();source=next(r for r in json.loads((PRIVATE/'native-records.json').read_text()) if r['service']=='service-a')
verify_native(source,capture(n));snapshot=source['dataset']+'@recovery-checkpoint';destination='iscsi_lab/volumes/snapshot-restore-a'
assert not n.call('pool.snapshot.query',[['id','=',snapshot]])
assert not n.call('pool.dataset.query',[['id','=',destination]])
receipt({'operation':'snapshot-create','state':'intent','source_guid':source['zvol_guid'],'snapshot':snapshot})
# Deliberately close without reading the mutation response. Reconcile, never retry create.
n.sequence+=1;n.ws.send(json.dumps({'jsonrpc':'2.0','id':n.sequence,'method':'pool.snapshot.create','params':[{'dataset':source['dataset'],'name':'recovery-checkpoint'}]}));n.ws.close()
n=NAS()
for _ in range(20):
 snapshots=n.call('pool.snapshot.query',[['id','=',snapshot]])
 if len(snapshots)==1:break
 time.sleep(1)
assert len(snapshots)==1,'Lost response unresolved; do not allocate again'
receipt({'operation':'snapshot-create','state':'reconciled-after-lost-response','snapshot':snapshot,'count':len(snapshots)})
n.call('pool.snapshot.clone',{'snapshot':snapshot,'dataset_dst':destination})
extent=n.call('iscsi.extent.create',{'name':'snapshot-restore-a','type':'DISK','disk':'zvol/'+destination,'serial':uuid.uuid4().hex[:16],'blocksize':512,'insecure_tpc':False,'comment':'static-iscsi-lab'})
target=n.call('iscsi.target.create',{'name':'snapshot-restore-a','groups':[source['group']],'auth_networks':['172.30.91.0/24']})
mapping=n.call('iscsi.targetextent.create',{'target':target['id'],'extent':extent['id'],'lunid':0})
ds=n.call('pool.dataset.query',[['id','=',destination]],{'extra':{'properties':['guid','volsize']}})[0]
r=dict(source,service='snapshot-restore-a',dataset=destination,zvol_guid=ds['guid']['value'],extent_id=extent['id'],serial=extent['serial'],naa=extent['naa'],target_id=target['id'],iqn='iqn.2026-09.lab.static:'+target['name'])
(PRIVATE/'clone-record.json').write_text(json.dumps(r,indent=2))
state=capture(n);verify_native(source,state);verify_native(r,state);assert r['zvol_guid']!=source['zvol_guid'] and r['naa']!=source['naa']
acks=[json.loads(x) for x in (PRIVATE/'acknowledged.jsonl').read_text().splitlines() if json.loads(x)['marker']==source['marker']]
result=ssh(19112,'sudo python3 -c '+shlex.quote((ROOT/'initiator_guest.py').read_text()),input=json.dumps(dict(r,chap=json.loads((PRIVATE/'chap.json').read_text()),verify_marker=True,verify_rows=acks)),capture_output=True,text=True)
receipt({'snapshot_clone_verified':True,'source_guid':source['zvol_guid'],'clone_guid':r['zvol_guid'],'chap_acl_preserved':True,'acknowledged_rows':len(acks),'lost_response_reconciled_without_retry':True})
print(json.dumps({'snapshot_clone_verified':True,'rows':len(acks),'chap_acl_preserved':True,'lost_response_reconciled_without_retry':True}))
