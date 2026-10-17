import copy,json
from lab import ROOT,kubectl
records=json.loads((ROOT/'records.json').read_text());a=records[0]
checks=[]
def denied(name,obj):
 r=kubectl('create','--dry-run=server','-f','-',data=obj,check=False)
 assert r.returncode and 'Retained storage must match' in r.stderr,(name,r.stderr)
 checks.append({'test':name,'denied':True})
for name,change in [('dynamic ordinary claim',{'volumeName':None}),('substituted class',{'storageClassName':'other'}),('foreign binding',{'volumeName':'foreign'})]:
 obj=copy.deepcopy(a['pvc']);obj['metadata']['name']='service-b' # existing update is checked separately below
 obj['metadata']['namespace']='default'
 if name!='dynamic ordinary claim':obj['metadata']['namespace']='iscsi-fixture'
 obj['spec'].update({k:v for k,v in change.items() if v is not None})
 if change.get('volumeName','present') is None:obj['spec'].pop('volumeName')
 # API admission precedes create conflict checks.
 denied(name,obj)
obj=copy.deepcopy(a['pvc']);obj['metadata']['name']='spoofed';obj['metadata']['labels']={'onboarding':'approved'};obj['spec'].pop('volumeName');denied('spoofed onboarding label',obj)
obj=copy.deepcopy(a['pv']);obj['metadata']['name']='foreign-alias';denied('second PV alias',obj)
r=kubectl('patch','pv',a['pv']['metadata']['name'],'--type=merge','--dry-run=server','--patch-file=/dev/stdin',data={'spec':{'persistentVolumeReclaimPolicy':'Delete'}},check=False)
assert r.returncode and 'Retained storage must match' in r.stderr;checks.append({'test':'reclaim policy update','denied':True})
(ROOT/'admission-results.json').write_text(json.dumps(checks,indent=2));print(json.dumps(checks))
