import pathlib,json,sys,shlex
sys.path.insert(0,str(__import__('pathlib').Path(__file__).resolve().parent))
from ssh import ssh
pins=json.loads(pathlib.Path('/tmp/static-iscsi-inputs/extra-images.json').read_text())
for port in (19111,19112,19113):
 for image in pins:
  ref=image['pinned'];repo=ref.split('@')[0].rsplit(':',1)[0];canonical=repo+'@'+ref.split('@')[1]
  ssh(port,'sudo k3s ctr -n k8s.io images tag '+shlex.quote(ref)+' '+shlex.quote(canonical),stdout=__import__('subprocess').DEVNULL)
 print('Canonical CRI digest references registered:',port)
