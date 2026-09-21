"""Explicit disposable-API tests. Never fall back to the production kubeconfig."""
import argparse
import copy
import json
from pathlib import Path
import subprocess
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from render_storage import render, placement, record_hash, STAMP, WRITER
from test_render_storage import RECORD,NODE

parser=argparse.ArgumentParser();parser.add_argument('--kubeconfig',required=True,type=Path)
args=parser.parse_args()
config=json.loads(subprocess.check_output(['kubectl','--kubeconfig',str(args.kubeconfig),'config','view','-o','json']))
server=config['clusters'][0]['cluster']['server']
if not server.startswith('https://127.0.0.1:'):
    raise SystemExit('Tests require an explicitly selected loopback disposable API')

def kubectl(arguments,obj=None,check=True):
    result=subprocess.run(['kubectl','--kubeconfig',str(args.kubeconfig)]+arguments,
        input=json.dumps(obj) if obj is not None else None,text=True,capture_output=True)
    if check and result.returncode:raise RuntimeError(result.stderr)
    return result

def apply(obj):return kubectl(['apply','-f','-'],obj)

def admit(obj):
    result=kubectl(['create','--dry-run=server','-f','-'],obj,False)
    if result.returncode==0:return True
    if 'denied request' in result.stderr or ('forbidden' in result.stderr.lower() and 'ValidatingAdmissionPolicy' in result.stderr):return False
    raise RuntimeError('Not an admission denial: '+result.stderr)

def expect(ok,label):
    if not ok:raise AssertionError(label)
    print('PASS '+label)

ns=RECORD['namespace']
apply({'apiVersion':'v1','kind':'Namespace','metadata':{'name':ns}})
uid=json.loads(kubectl(['get','namespace',ns,'-o','json']).stdout)['metadata']['uid']
kubectl(['annotate','namespace',ns,STAMP+'-','--overwrite'])
objects=render(RECORD)
for obj in objects:
    if obj['kind'].startswith('Validating'):apply(obj)
# Admission configuration propagation is asynchronous. Wait for policy type checking,
# then exercise a deny until bindings are active (never count transport errors).
for _ in range(30):
    policies=json.loads(kubectl(['get','validatingadmissionpolicies','-o','json']).stdout)['items']
    warnings=[o.get('status',{}).get('typeChecking',{}).get('expressionWarnings',[]) for o in policies]
    if any(warnings):raise AssertionError(warnings)
    if all('typeChecking' in o.get('status',{}) for o in policies):break
    time.sleep(1)
else:raise RuntimeError('Policy type checking did not complete')

pod={'apiVersion':'v1','kind':'Pod','metadata':{'name':'retained-admission-probe','namespace':ns,'labels':{WRITER:'jellyfin'}},
     'spec':{'containers':[{'name':'fixture','image':'busybox','command':['true']}],
             'affinity':placement(NODE),'volumes':[{'name':'config','persistentVolumeClaim':{'claimName':RECORD['pvc']}}]}}
auth={'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':'retained-jellyfin-authorization','namespace':ns},
      'data':{'released':'true','recordHash':record_hash(RECORD),'namespaceUID':uid,'hostname':NODE['hostname'],
              'nodeUID':NODE['node_uid'],'smbiosUUID':NODE['smbios_uuid']}}
kubectl(['delete','configmap',auth['metadata']['name'],'-n',ns,'--ignore-not-found'])
for _ in range(30):
    if not admit(pod):break
    time.sleep(1)
else:raise AssertionError('Missing authorization did not close admission')
expect(not admit(pod),'missing authorization')
unrelated=copy.deepcopy(pod);unrelated['metadata'].pop('labels');unrelated['spec']['volumes'][0]['persistentVolumeClaim']['claimName']='unrelated-media'
expect(admit(unrelated),'unrelated media without authorization')
apply(auth)
expect(not admit(pod),'missing namespace identity stamp')
kubectl(['annotate','namespace',ns,STAMP+'='+uid,'--overwrite'])
for _ in range(30):
    if admit(pod):break
    time.sleep(1)
else:raise AssertionError('Valid writer did not pass')
expect(admit(pod),'valid exact generation writer')
for label,edit in [
    ('missing writer label',lambda p:p['metadata'].pop('labels')),
    ('wrong nodeName',lambda p:p['spec'].update(nodeName='worker-b')),
    ('correct nodeName prebinding also denied',lambda p:p['spec'].update(nodeName='worker-a')),
    ('wrong worker affinity',lambda p:p['spec'].update(affinity=placement(dict(NODE,hostname='worker-b')))),
    ('stale node generation',lambda p:p['spec'].update(affinity=placement(dict(NODE,node_uid='old-node')))),
    ('extra affinity OR term',lambda p:p['spec']['affinity']['nodeAffinity']['requiredDuringSchedulingIgnoredDuringExecution']['nodeSelectorTerms'].append({'matchExpressions':[{'key':'any','operator':'Exists'}]}))]:
    p=copy.deepcopy(pod);edit(p);expect(not admit(p),label)
for obj in objects[:2]:expect(admit(obj),'valid '+obj['kind'])
pv=objects[0];pvc=objects[1]
for label,edit in [('alias PV',lambda p:p['metadata'].update(name='alias-pv')),
                   ('foreign driver',lambda p:p['spec']['csi'].update(driver='foreign')),
                   ('wrong filesystem',lambda p:p['spec']['csi'].update(fsType='xfs')),
                   ('wrong target',lambda p:p['spec']['csi']['volumeAttributes'].update(iqn='iqn.foreign'))]:
    p=copy.deepcopy(pv);edit(p);expect(not admit(p),label)
for label,edit in [('foreign claim',lambda p:p['metadata'].update(name='foreign')),
                   ('dynamic storage',lambda p:(p['spec'].pop('volumeName'),p['spec'].update(storageClassName='nfs-pv')))]:
    p=copy.deepcopy(pvc);edit(p);expect(not admit(p),label)
auth['data']['namespaceUID']='old-namespace';apply(auth)
for _ in range(30):
    if not admit(pod):break
    time.sleep(1)
expect(not admit(pod),'old namespace authorization denied')
# A new namespace cannot import a previous stamp, even if its name is reused.
kubectl(['delete','namespace',ns,'--wait=true','--timeout=60s'])
expect(not admit({'apiVersion':'v1','kind':'Namespace','metadata':{'name':ns,'annotations':{STAMP:uid}}}),'namespace stamp replay denied on create')
apply({'apiVersion':'v1','kind':'Namespace','metadata':{'name':ns}})
auth['data']['namespaceUID']=uid;apply(auth)
expect(not admit(pod),'recreated namespace with replayed old authorization held')
print('Disposable API admission qualification passed')
