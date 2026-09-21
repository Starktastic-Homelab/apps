"""Publish the private lab Git source through a read-only in-cluster fixture."""
import base64, json, pathlib, subprocess, sys
from lab import PRIVATE, ROOT, apply, kubectl
repo=PRIVATE/'repo'
def git(*args):
    return subprocess.run(['git','-C',str(repo),*args],check=True,capture_output=True,text=True)
git('add','manifests')
if subprocess.run(['git','-C',str(repo),'diff','--cached','--quiet']).returncode:
    git('-c','user.name=Storage Lab','-c','user.email=storage-lab@example.invalid','commit','-m',sys.argv[1])
git('update-server-info')
files=[p for p in (repo/'.git').rglob('*') if p.is_file() and not any(part in ['hooks','logs'] for part in p.relative_to(repo/'.git').parts) and p.name not in ['index','COMMIT_EDITMSG']]
assert sum(p.stat().st_size for p in files)<700000
revision=git('rev-parse','HEAD').stdout.strip()
config_name='fixture-git-'+revision[:12]
items=[];data={}
for i,path in enumerate(sorted(files)):
    key='file'+str(i);data[key]=base64.b64encode(path.read_bytes()).decode();items.append({'key':key,'path':'fixture.git/'+str(path.relative_to(repo/'.git'))})
cm={'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':config_name,'namespace':'iscsi-fixture'},'immutable':True,'binaryData':data}
image='quay.io/argoproj/argocd:v3.5.3@sha256:5a7367b15ab5c9fcce917954ec74527c8e401671756611654a9d998d9fff0662'
deploy={'apiVersion':'apps/v1','kind':'Deployment','metadata':{'name':'fixture-git','namespace':'iscsi-fixture'},'spec':{'replicas':1,'strategy':{'type':'Recreate','rollingUpdate':None},'selector':{'matchLabels':{'app':'fixture-git'}},'template':{'metadata':{'labels':{'app':'fixture-git'}},'spec':{'automountServiceAccountToken':False,'containers':[{'name':'git','image':image,'imagePullPolicy':'IfNotPresent','command':['git','-c','safe.directory=/git/fixture.git','daemon','--reuseaddr','--export-all','--base-path=/git','--listen=0.0.0.0','--port=9418'],'ports':[{'containerPort':9418}],'resources':{'requests':{'cpu':'5m','memory':'24Mi'},'limits':{'memory':'64Mi'}},'volumeMounts':[{'name':'git','mountPath':'/git','readOnly':True}]}],'volumes':[{'name':'git','configMap':{'name':config_name,'items':items}}]}}}}
service={'apiVersion':'v1','kind':'Service','metadata':{'name':'fixture-git','namespace':'iscsi-fixture'},'spec':{'selector':{'app':'fixture-git'},'ports':[{'port':9418,'targetPort':9418}]}}
print(apply([cm,deploy,service]).stdout)
print('Lab Git commit',git('rev-parse','HEAD').stdout.strip())

print(kubectl('rollout','status','deployment/fixture-git','-n','iscsi-fixture','--timeout=90s').stdout)
served=kubectl('exec','-n','iscsi-fixture','deployment/fixture-git','--','git','-c','safe.directory=/git/fixture.git','--git-dir=/git/fixture.git','rev-parse','HEAD').stdout.strip()
assert served==revision,'Lab Git server still serves an older revision'
