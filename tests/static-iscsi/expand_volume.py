"""Run one maintenance boundary, then stop; reconcile observed identity on resume."""
import json,sys,shlex
from lab import PRIVATE,ROOT,receipt
from identity import reconcile_capacity,verify_native
from verify_recovery import capture,NAS
from ssh import ssh
from quiescence import require_quiesced
require_quiesced()
stage=sys.argv[1];assert stage in ('nas','device','filesystem','record')
records=json.loads((PRIVATE/'native-records.json').read_text());r=next(x for x in records if x['service']=='service-a');intent=PRIVATE/'growth-intent.json'
if not intent.exists():
 assert stage=='nas';verify_native(r,capture(NAS()))
 intent.write_text(json.dumps({'original':r,'planned_bytes':3*1024**3},indent=2))
plan=json.loads(intent.read_text());original=plan['original'];planned=plan['planned_bytes'];n=NAS()
observed=reconcile_capacity(original,capture(n),planned)
if stage=='nas':
 receipt({'growth_stage':'nas','state':'intent','guid':original['zvol_guid'],'planned_bytes':planned})
 if observed['bytes']!=planned:n.call('pool.dataset.update',original['dataset'],{'volsize':planned})
 observed=reconcile_capacity(original,capture(n),planned);assert observed['bytes']==planned
 receipt({'growth_stage':'nas','state':'observed','guid':original['zvol_guid'],'bytes':observed['bytes'],'record_not_updated':True})
else:
 assert observed['bytes']==planned
 request=dict(observed,chap=json.loads((PRIVATE/'chap.json').read_text()),action=('grow' if stage=='filesystem' else 'observe'))
 result=ssh(19112,'sudo python3 -c '+shlex.quote((ROOT/'grow_guest.py').read_text()),input=json.dumps(request),capture_output=True,text=True)
 result=json.loads(result.stdout);receipt({'growth_stage':stage,**result})
 if stage=='record':
  assert result['filesystem_after']==planned
  r.update(bytes=planned);(PRIVATE/'native-records.json').write_text(json.dumps(records,indent=2)+'\n')
  public=json.loads((ROOT/'records.json').read_text())
  next(x for x in public if x['service']=='service-a')['bytes']=planned
  (ROOT/'records.json').write_text(json.dumps(public,indent=2)+'\n')
print('Maintenance boundary completed:',stage)
