import pathlib,json,sys,time
base=pathlib.Path('/var/lib/vz/iscsi-lab-20260921-6c168a2e');sys.path.insert(0,str(base))
from guard import owns_vm,vm_config,guest_exec
m=json.loads((base/'manifest.json').read_text());c=vm_config(913)
assert owns_vm(913,c,m) and 'link_down=1' in c['net0'] and 'link_down' not in c['net1']
acks=[]
for service in ('service-a','service-b'):
 cid=guest_exec(913,['k3s','crictl','ps','--state','Running','--label','io.kubernetes.pod.name='+service+'-0','-q']).strip().splitlines()
 assert len(cid)==1,cid
 ack=json.loads(guest_exec(913,['k3s','crictl','exec',cid[0],'python','/fixture/fixture.py','write','partition-witness']))
 acks.append(ack)
print(json.dumps({'witness_at':time.time(),'acks':acks}))
