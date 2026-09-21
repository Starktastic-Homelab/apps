import pathlib,sys,json
sys.path.insert(0,str(__import__('pathlib').Path(__file__).resolve().parent))
from ssh import ssh
base=pathlib.Path('/tmp/static-iscsi-inputs')
for port in (19111,19112,19113):
 for image in json.loads((base/'extra-images.json').read_text()):
  with (base/'extra'/image['archive']).open('rb') as stream:
   ssh(port,'sudo k3s ctr images import -',stdin=stream,stdout=__import__('subprocess').DEVNULL)
 print('Verified pinned image archives imported:',port,flush=True)
