"""Stage iSCSI packages selected by the clone's authenticated Debian metadata."""
import hashlib
import json
import pathlib
import shlex
import subprocess
import urllib.parse
import urllib.request
import sys

base=pathlib.Path(sys.argv[1]);sys.path.insert(0,str(base))
from guard import owns_vm, vm_config, guest_exec
m=json.loads((base/'manifest.json').read_text());assert owns_vm(911,vm_config(911),m)
plan=guest_exec(911,['apt-get','--print-uris','--yes','install','open-iscsi','lsscsi','sg3-utils'])
items=[shlex.split(line) for line in plan.splitlines() if line.startswith("'http")]
assert items
packages=[name.split('_')[0] for url,name,size,md5 in items]
metadata=guest_exec(911,['apt-cache','show','--no-all-versions']+packages)
records={}
for paragraph in metadata.split('\n\n'):
    fields=dict(line.split(': ',1) for line in paragraph.splitlines() if ': ' in line and not line.startswith(' '))
    if 'Filename' in fields:records[pathlib.PurePosixPath(fields['Filename']).name]=fields
stage=base/'seed/packages';stage.mkdir(parents=True,exist_ok=True)
evidence=[]
for url,name,size,md5 in items:
    fields=records[name];assert fields['Filename'].startswith('pool/') and '/' not in name
    expected=fields['SHA256'];assert len(expected)==64
    data=urllib.request.urlopen('https://deb.debian.org/debian/'+urllib.parse.quote(fields['Filename'],safe='/'),timeout=40).read()
    assert len(data)==int(size) and hashlib.sha256(data).hexdigest()==expected
    (stage/name).write_bytes(data)
    evidence.append({'package':fields['Package'],'version':fields['Version'],'filename':name,'sha256':expected})
(base/'package-pins.json').write_text(json.dumps(evidence,indent=2)+'\n')
print(json.dumps({'verified_packages':len(evidence),'bytes':sum(p.stat().st_size for p in stage.glob('*.deb'))}))
