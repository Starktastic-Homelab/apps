"""Offline maintenance requires all current lab nodes reachable and no writers."""
import json
from lab import kubectl
from ssh import ssh

def require_quiesced():
 nodes=json.loads(kubectl('get','nodes','-o','json').stdout)['items']
 assert len(nodes)==3 and all(any(c['type']=='Ready' and c['status']=='True' for c in n['status']['conditions']) for n in nodes),'All current nodes must be Ready; otherwise fence before maintenance'
 pods=json.loads(kubectl('get','pods','-A','-o','json').stdout)['items']
 assert not any(v.get('persistentVolumeClaim',{}).get('claimName') in ('service-a','service-b') for p in pods if p['metadata']['namespace']=='iscsi-fixture' for v in p['spec'].get('volumes',[])),'Writer pod still exists'
 for port in (19111,19112,19113):
  sources=ssh(port,'findmnt -rn -t ext4 -o SOURCE',capture_output=True,text=True).stdout.splitlines()
  assert sources==['/dev/vda1'],'Unexpected mounted ext4 volume on lab node'
