"""One-shot synthetic lab provisioning; interrupted runs require reconciliation."""
import json, os, secrets, uuid
from lab import PRIVATE, receipt
from nas_rpc import NAS
from ssh import ssh

os.umask(0o077)
n = NAS()
pool_record = json.loads((PRIVATE/'nas-pool.json').read_text())
pools = n.call('pool.query')
assert len(pools) == 1 and str(pools[0]['guid']) == str(pool_record['guid'])
assert not n.call('iscsi.target.query') and not n.call('iscsi.extent.query')
assert not n.call('pool.dataset.query', [['type', '=', 'VOLUME']])
with (PRIVATE/'onboarding-consumed').open('x') as stream:
    stream.write('Reconcile existing identities after any interrupted response. Never rerun blindly.\n')
    stream.flush(); os.fsync(stream.fileno())
initiators = []
for port in (19111, 19112, 19113):
    text = ssh(port, 'sudo cat /etc/iscsi/initiatorname.iscsi', capture_output=True, text=True).stdout
    initiators.append(next(line.split('=',1)[1] for line in text.splitlines() if line.startswith('InitiatorName=')))
assert len(set(initiators)) == 3
chap = {'user': 'staticlab', 'secret': secrets.token_hex(8)}
(PRIVATE/'chap.json').write_text(json.dumps(chap))
def once(label, method, *params):
    receipt({'operation': label, 'state': 'intent', 'method': method})
    value = n.call(method, *params)
    receipt({'operation': label, 'state': 'responded', 'id': value.get('id') if isinstance(value,dict) else value})
    return value
basename = 'iqn.2026-09.lab.static'
once('basename', 'iscsi.global.update', {'basename': basename})
portal = once('portal', 'iscsi.portal.create', {'listen': [{'ip':'172.30.91.10'}], 'comment':'static-iscsi-lab'})
initiator = once('initiators', 'iscsi.initiator.create', {'initiators':initiators, 'comment':'static-iscsi-lab'})
auth = once('chap', 'iscsi.auth.create', {'tag':1, 'user':chap['user'], 'secret':chap['secret']})
records = []
for service, size in [('blank-probe',128*1024**2), ('service-a',2*1024**3), ('service-b',2*1024**3)]:
    dataset = 'iscsi_lab/volumes/'+service
    once(service+'-zvol', 'pool.dataset.create', {'name':dataset,'type':'VOLUME','volsize':size,'volblocksize':'16K','sparse':False})
    extent = once(service+'-extent','iscsi.extent.create',{'name':service,'type':'DISK','disk':'zvol/'+dataset,'serial':uuid.uuid4().hex[:16],'blocksize':512,'insecure_tpc':False,'comment':'static-iscsi-lab'})
    target = once(service+'-target','iscsi.target.create',{'name':service,'groups':[{'portal':portal['id'],'initiator':initiator['id'],'authmethod':'CHAP','auth':auth['tag']}],'auth_networks':['172.30.91.0/24']})
    mapping = once(service+'-mapping','iscsi.targetextent.create',{'target':target['id'],'extent':extent['id'],'lunid':0})
    ds = n.call('pool.dataset.query',[['id','=',dataset]],{'extra':{'properties':['guid','volsize']}})[0]
    record = {'service':service,'marker':str(uuid.uuid4()),'pool_guid':str(pool_record['guid']),'dataset':dataset,'zvol_guid':ds['guid']['value'],'bytes':ds['volsize']['parsed'],'extent_id':extent['id'],'serial':extent['serial'],'naa':extent['naa'],'target_id':target['id'],'iqn':basename+':'+target['name'],'lun':mapping['lunid'],'portal':'172.30.91.10:3260','initiators':initiators,'group':target['groups'][0]}
    records.append(record)
    with (PRIVATE/'native-records.json').open('w') as stream:
        json.dump(records,stream,indent=2);stream.flush();os.fsync(stream.fileno())
once('iscsi-enabled','service.update', 'iscsitarget', {'enable':True})
once('iscsi-start','service.start','iscsitarget')
print(json.dumps({'volumes':len(records),'services':[r['service'] for r in records],'chap':True,'initiator_count':len(initiators),'pool_guid':str(pool_record['guid'])}))
