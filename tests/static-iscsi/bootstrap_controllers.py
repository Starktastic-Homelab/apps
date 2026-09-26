import pathlib,yaml,json,sys,subprocess,base64,os

from lab import kubectl,apply,PRIVATE,ROOT
base=pathlib.Path('/tmp/static-iscsi-inputs');pins={i['tag']:i['pinned'] for i in json.loads((base/'extra-images.json').read_text())}
objects=[{'apiVersion':'v1','kind':'Namespace','metadata':{'name':'argocd'}}]
cluster_kinds={'ClusterRole','ClusterRoleBinding','CustomResourceDefinition'}
for filename,namespace in [('argocd-core-v3.5.3.yaml','argocd'),('sealed-secrets-v0.40.0.yaml','kube-system')]:
 for obj in yaml.safe_load_all((base/filename).read_text()):
  if not obj:continue
  name=obj['metadata']['name']
  if name.startswith('argocd-applicationset'):continue
  if obj['kind'] not in cluster_kinds:obj['metadata']['namespace']=namespace
  if obj['kind'] in ['Deployment','StatefulSet']:
   pod=obj['spec']['template']['spec'];pod['nodeSelector']={'node-role.kubernetes.io/control-plane':'true'};pod['tolerations']=[{'key':'node-role.kubernetes.io/control-plane','operator':'Exists','effect':'NoSchedule'}]
   for c in pod.get('containers',[])+pod.get('initContainers',[]):
    c['image']=pins[c['image']];c['imagePullPolicy']='IfNotPresent'
    c['resources']={'requests':{'cpu':'10m','memory':'64Mi'},'limits':{'memory':'512Mi'}}
  objects.append(obj)
(PRIVATE/'controllers-rendered.yaml').write_text(yaml.safe_dump_all(objects,sort_keys=False))
print(apply(objects).stdout)
if '--without-key' in sys.argv:
 print('Sealing key intentionally absent for negative recovery test.');sys.exit(0)
os.umask(0o077)
if not (PRIVATE/'sealing.key').exists():
 subprocess.run(['openssl','req','-x509','-nodes','-newkey','rsa:4096','-days','7','-subj','/CN=static-iscsi-sealing','-keyout',str(PRIVATE/'sealing.key'),'-out',str(PRIVATE/'sealing.crt')],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
secret={'apiVersion':'v1','kind':'Secret','type':'kubernetes.io/tls','metadata':{'name':'static-iscsi-sealing-key','namespace':'kube-system','labels':{'sealedsecrets.bitnami.com/sealed-secrets-key':'active'}},'data':{'tls.key':base64.b64encode((PRIVATE/'sealing.key').read_bytes()).decode(),'tls.crt':base64.b64encode((PRIVATE/'sealing.crt').read_bytes()).decode()}}
print(apply([secret]).stdout)
print('Dedicated lab sealing key preserved externally; controller bootstrap applied.')
