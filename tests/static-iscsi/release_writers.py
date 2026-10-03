"""Release only this fresh cluster after external native/filesystem/marker checks."""
import base64,json,subprocess,sys,time
from lab import ROOT,PRIVATE,apply,kubectl,receipt
from quiescence import require_quiesced
require_quiesced()
subprocess.run([sys.executable,str(ROOT/'verify_filesystems.py')],check=True)
secret=kubectl('get','secret','static-iscsi-chap','-n','static-iscsi-system','-o','json',check=False)
assert secret.returncode==0,'CHAP has not been recovered'
data=json.loads(secret.stdout)['data'];chap=json.loads((PRIVATE/'chap.json').read_text())
for key,value in [('node-db.node.session.auth.username',chap['user']),('node-db.node.session.auth.password',chap['secret'])]:
 assert base64.b64decode(data[key]).decode()==value,'Recovered CHAP credential mismatch'
ns=json.loads(kubectl('get','ns','iscsi-fixture','-o','json').stdout)
uid=ns['metadata']['uid'];assert ns['metadata']['annotations']['storage-lab/namespace-uid']==uid
receipt({'external_verification_completed':True,'namespace_uid':uid,'at':time.time()})
data={'released':'true','namespaceUID':uid}
existing=kubectl('get','cm','storage-recovery-verification','-n','iscsi-fixture',check=False)
if existing.returncode:
 print(apply([{'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':'storage-recovery-verification','namespace':'iscsi-fixture'},'data':data}]).stdout)
else:
 print(kubectl('patch','cm','storage-recovery-verification','-n','iscsi-fixture','--type=merge','-p',json.dumps({'data':data})).stdout)
