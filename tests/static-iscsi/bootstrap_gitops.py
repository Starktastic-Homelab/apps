"""Restore declarative fixture with writers held by absent external verification."""
import json,subprocess,sys
from lab import PRIVATE,ROOT,apply,kubectl
apply([{'apiVersion':'v1','kind':'Namespace','metadata':{'name':n}} for n in ('iscsi-fixture','static-iscsi-system')])
ns=json.loads(kubectl('get','ns','iscsi-fixture','-o','json').stdout)
kubectl('annotate','ns','iscsi-fixture','storage-lab/namespace-uid='+ns['metadata']['uid'],'--overwrite')
assert kubectl('get','cm','-n','iscsi-fixture','storage-recovery-verification',check=False).returncode
print(kubectl('apply','--server-side','-f',str(ROOT/'csi-rendered.yaml')).stdout)
subprocess.run([sys.executable,str(ROOT/'bootstrap_controllers.py'),*sys.argv[1:]],check=True)
subprocess.run([sys.executable,str(ROOT/'set_replicas.py'),'1'],check=True)
subprocess.run([sys.executable,str(ROOT/'publish_git.py'),'Restore existing retained volumes on fresh cluster'],check=True)
print(kubectl('rollout','status','deployment/fixture-git','-n','iscsi-fixture','--timeout=90s').stdout)
print(kubectl('rollout','status','deployment/argocd-repo-server','-n','argocd','--timeout=90s').stdout)
print(kubectl('rollout','status','statefulset/argocd-application-controller','-n','argocd','--timeout=90s').stdout)
print(kubectl('apply','-f',str(ROOT/'argocd-app.json')).stdout)
print('GitOps restored; verification object absent, so writers must remain held.')
