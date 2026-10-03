import pathlib,json,copy,sys

from lab import ROOT,PRIVATE,kubectl,apply
records=json.loads((ROOT/'records.json').read_text());a=records[0];results=[]
def deny(label,obj,needle='Retained storage must match'):
 r=kubectl('create','--dry-run=server','-f','-',data=obj,check=False)
 assert r.returncode and needle in r.stderr,(label,r.stderr)
 results.append({'test':label,'denied':True})
for label,change in [('dynamic claim',{'volumeName':None}),('substituted class',{'storageClassName':'other'}),('foreign binding',{'volumeName':'foreign'})]:
 obj=copy.deepcopy(a['pvc']);obj['metadata']['name']='service-b';obj['spec'].update(change)
 if obj['spec'].get('volumeName') is None:obj['spec'].pop('volumeName')
 deny(label,obj)
obj=copy.deepcopy(a['pvc']);obj['metadata']['name']='spoofed';obj['metadata']['labels']={'onboarding':'approved'};obj['spec'].pop('volumeName');deny('spoofed onboarding label',obj)
obj=copy.deepcopy(a['pv']);obj['metadata']['name']='foreign-alias';deny('PV alias',obj)
r=kubectl('patch','pv',a['pv']['metadata']['name'],'--type=merge','--dry-run=server','--patch-file=/dev/stdin',data={'spec':{'persistentVolumeReclaimPolicy':'Delete'}},check=False)
assert r.returncode and 'Retained storage must match' in r.stderr,r.stderr
results.append({'test':'Retain changed','denied':True})
for label,key,value in [('filesystem substituted','fsType','xfs'),('driver substituted','driver','other-driver')]:
 obj=copy.deepcopy(a['pv']);obj['spec']['csi'][key]=value;deny(label,obj)
image='docker.io/library/python:3.13-alpine@sha256:f3ebba2ace255c93267a0278da88c7f1044432991abc4e6ad20d22e34dd0f8ee'
pods=[]
for r in records:
 pods.append({'apiVersion':'v1','kind':'Pod','metadata':{'name':'initialize-'+r['service'],'namespace':'iscsi-fixture','labels':{'storage-lab/writer':'true'}},'spec':{'automountServiceAccountToken':False,'restartPolicy':'Never','containers':[{'name':'initialize','image':image,'imagePullPolicy':'IfNotPresent','command':['python','/fixture/fixture.py','initialize'],'env':[{'name':'SERVICE_MARKER','value':r['marker']}],'volumeMounts':[{'name':'data','mountPath':'/data'},{'name':'fixture','mountPath':'/fixture','readOnly':True}]}],'volumes':[{'name':'data','persistentVolumeClaim':{'claimName':r['service']}},{'name':'fixture','configMap':{'name':'sqlite-fixture'}}]}})
(PRIVATE/'initialize-pods.json').write_text(json.dumps(pods,indent=2))
deny('writer without external verification',pods[0],needle='static-iscsi-writer-hold')
cm={'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':'storage-recovery-verification','namespace':'iscsi-fixture'},'data':{'released':'true','namespaceUID':'stale-previous-cluster'}}
apply([cm])
# Admission parameters are asynchronously observed; caller runs stale check separately.
(ROOT/'admission-results.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps(results))
