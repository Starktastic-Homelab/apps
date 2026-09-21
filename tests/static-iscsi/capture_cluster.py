"""External before/after receipt for fresh-cluster identity and retained storage."""
import base64,hashlib,json,sys
from lab import PRIVATE,kubectl
from verify_recovery import capture,NAS
result={'phase':sys.argv[1]}
config=json.loads(kubectl('config','view','--raw','-o','json').stdout)
result['ca_sha256']=hashlib.sha256(base64.b64decode(config['clusters'][0]['cluster']['certificate-authority-data'])).hexdigest()
for resource in ['nodes','pv','pvc -n iscsi-fixture']:
 result[resource]={o['metadata']['name']:o['metadata']['uid'] for o in json.loads(kubectl('get',*resource.split(),'-o','json').stdout)['items']}
state=capture(NAS());result['zvols']={d['id']:d['guid']['value'] for d in state['datasets'] if d['type']=='VOLUME'}
result['acknowledgements']=[json.loads(x) for x in (PRIVATE/'acknowledged.jsonl').read_text().splitlines()]
(PRIVATE/(sys.argv[1]+'.json')).write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='acknowledgements'}))
