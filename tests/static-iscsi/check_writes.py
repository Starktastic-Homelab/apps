"""Record acknowledged transactions outside the cluster, then verify exact values."""
import json,os,sys,time
from lab import ROOT,PRIVATE,kubectl
records=json.loads((ROOT/'records.json').read_text())
mode=sys.argv[1]
for r in records:
 service=r['service'];pod=service+'-0'
 if mode=='write':
  for i in range(5):
   tx=sys.argv[2]+'-'+str(i)
   result=kubectl('exec','-n','iscsi-fixture',pod,'--','python','/fixture/fixture.py','write',tx)
   ack=json.loads(result.stdout)
   with (PRIVATE/'acknowledged.jsonl').open('a') as f:
    f.write(json.dumps(ack)+'\n');f.flush();os.fsync(f.fileno())
 else:
  actual=json.loads(kubectl('exec','-n','iscsi-fixture',pod,'--','python','/fixture/fixture.py','verify').stdout)
  values=dict(actual['rows'])
  expected=[json.loads(x) for x in (PRIVATE/'acknowledged.jsonl').read_text().splitlines() if json.loads(x)['marker']==r['marker']]
  assert all(values.get(x['id'])==x['value'] for x in expected)
  print(json.dumps({'service':service,'integrity':actual['integrity'],'acknowledged_survived':len(expected),'rows':len(values)}))
print(mode,'completed')
