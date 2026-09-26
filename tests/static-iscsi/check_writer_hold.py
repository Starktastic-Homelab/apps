import sys,json,copy

from lab import ROOT,PRIVATE,kubectl
pods=json.loads((PRIVATE/'initialize-pods.json').read_text());checks=json.loads((ROOT/'admission-results.json').read_text())
r=kubectl('create','--dry-run=server','-f','-',data=pods[0],check=False)
assert r.returncode and 'External storage verification for this cluster' in r.stderr,r.stderr
checks.append({'test':'stale previous-cluster verification','denied':True})
obj=copy.deepcopy(pods[0]);obj['metadata'].pop('labels')
r=kubectl('create','--dry-run=server','-f','-',data=obj,check=False)
assert r.returncode and 'Storage writer pods require' in r.stderr,r.stderr
checks.append({'test':'unlabelled writer bypass','denied':True})
(ROOT/'admission-results.json').write_text(json.dumps(checks,indent=2)+'\n')
print(json.dumps(checks[-2:]))
