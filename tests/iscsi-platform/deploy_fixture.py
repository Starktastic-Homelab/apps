"""Explicit one-shot initialization, then chart-rendered guarded StatefulSets."""
import json
import os
import subprocess
import sys
import yaml
from lab import ROOT, PRIVATE, ENV, kubectl, apply, receipt
records=json.loads((ROOT/'records.json').read_text())
image=json.loads(__import__('pathlib').Path('/tmp/iscsi-lab-artifacts/oci/fixture-image.json').read_text())['pinned_reference']
config={'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':'sqlite-fixture','namespace':'iscsi-fixture'},'data':{f:(ROOT/f).read_text() for f in ('fixture.py','lifecycle.py')}}
print(apply([config]).stdout)
if sys.argv[1]=='initialize':
 previous=[json.loads(x) for x in (PRIVATE/'operations.jsonl').read_text().splitlines()]
 assert not any(x['operation']=='initialize' for x in previous),'Initialization already consumed; reconcile instead'
 receipt({'operation':'initialize','state':'consumed','services':[r['service'] for r in records]})
 for r in records:
  pod={'apiVersion':'v1','kind':'Pod','metadata':{'name':'initialize-'+r['service'],'namespace':'iscsi-fixture'},'spec':{'restartPolicy':'Never','automountServiceAccountToken':False,'containers':[{'name':'initialize','image':image,'imagePullPolicy':'IfNotPresent','command':['python','/fixture/fixture.py','initialize'],'env':[{'name':'SERVICE_MARKER','value':r['marker']}],'volumeMounts':[{'name':'data','mountPath':'/data'},{'name':'fixture','mountPath':'/fixture','readOnly':True}]}],'volumes':[{'name':'data','persistentVolumeClaim':{'claimName':r['service']}},{'name':'fixture','configMap':{'name':'sqlite-fixture'}}]}}
  print(apply([pod]).stdout)
else:
 for r in records:
  container = {
      'image': {'repository': image.split('@')[0], 'tag': '3.13-alpine@'+image.split('@')[1], 'pullPolicy': 'IfNotPresent'},
      'command': ['python', '/fixture/fixture.py', 'serve'],
      'env': {'SERVICE_MARKER': r['marker']},
      'resources': {'requests': {'cpu': '10m', 'memory': '24Mi'}, 'limits': {'memory': '96Mi'}},
      'probes': {'readiness': {'enabled': True, 'custom': True, 'spec': {
          'exec': {'command': ['python', '/fixture/fixture.py', 'verify']}, 'periodSeconds': 10}}},
  }
  v = {
      'controllers': {'main': {'type': 'statefulset', 'replicas': 1,
          'pod': {'automountServiceAccountToken': False}, 'containers': {'main': container}}},
      'persistence': {
          'data': {'existingClaim': r['service'], 'globalMounts': [{'path': '/data'}]},
          'fixture': {'type': 'configMap', 'name': 'sqlite-fixture',
              'globalMounts': [{'path': '/fixture', 'readOnly': True}]},
      },
  }
  values=ROOT/(r['service']+'-values.yaml');values.write_text(yaml.safe_dump(v))
  rendered=subprocess.check_output(['/tmp/iscsi-lab-tools/helm','template',r['service'],'/tmp/iscsi-lab-artifacts/app-template-5.2.1.tgz','-n','iscsi-fixture','-f',str(values)],text=True)
  objects=list(yaml.safe_load_all(rendered));sts=[o for o in objects if o and o['kind']=='StatefulSet'];assert len(sts)==1
  assert not sts[0]['spec'].get('volumeClaimTemplates')
  assert any(v.get('persistentVolumeClaim',{}).get('claimName')==r['service'] for v in sts[0]['spec']['template']['spec']['volumes'])
  (ROOT/(r['service']+'-rendered.yaml')).write_text(rendered)
  print(apply([o for o in objects if o]).stdout)
