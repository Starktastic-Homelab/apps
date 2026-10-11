"""A changed expected filesystem or service identity must fail without disk writes."""
import json,shlex,subprocess
from lab import ROOT,PRIVATE,receipt
from ssh import ssh
r=next(r for r in json.loads((PRIVATE/'native-records.json').read_text()) if r['service']=='service-b');r.update(chap=json.loads((PRIVATE/'chap.json').read_text()),verify_marker=True)
command='sudo python3 -c '+shlex.quote((ROOT/'initiator_guest.py').read_text())
def probe(record):return ssh(19112,command,input=json.dumps(record),capture_output=True,text=True)
before=json.loads(probe(r).stdout)
checks=[]
for field,error in [('filesystem_uuid','Filesystem identity mismatch before mount'),('marker','Service marker mismatch')]:
 bad=dict(r);bad[field]='00000000-0000-0000-0000-000000000000'
 try:probe(bad)
 except subprocess.CalledProcessError as e:
  assert error in e.stderr,e.stderr;checks.append(field)
 else:raise RuntimeError('Wrong identity accepted')
after=json.loads(probe(r).stdout);assert before['sha256']==after['sha256']
receipt({'filesystem_identity_negative_checks':checks,'whole_device_hash_unchanged':True,'sha256':after['sha256']})
print(json.dumps({'identity_mismatches_rejected':checks,'whole_device_hash_unchanged':True}))
