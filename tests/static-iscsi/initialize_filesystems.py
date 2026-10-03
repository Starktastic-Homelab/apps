"""Explicit one-shot initialization of the two synthetic service volumes only."""
import json, os, shlex, uuid, subprocess
from lab import ROOT, PRIVATE, receipt
from verify_recovery import verify_all
from ssh import ssh

records=verify_all()
with (PRIVATE/'filesystem-initialization-consumed').open('x') as stream:
    stream.write('Reconcile before any retry.\n');stream.flush();os.fsync(stream.fileno())
chap=json.loads((PRIVATE/'chap.json').read_text())
for record in records:
    if record['service']=='blank-probe':continue
    record['filesystem_uuid']=str(uuid.uuid4())
    with (PRIVATE/'native-records.json').open('w') as stream:
        json.dump(records,stream,indent=2);stream.flush();os.fsync(stream.fileno())
    receipt({'operation':'initialize-filesystem','state':'intent','service':record['service'],'uuid':record['filesystem_uuid']})
    request=dict(record,chap=chap,initialize=True)
    try:
        result=ssh(19112,'sudo python3 -c '+shlex.quote((ROOT/'initiator_guest.py').read_text()),input=json.dumps(request),capture_output=True,text=True)
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.stderr)
    observed=json.loads(result.stdout)
    receipt({'operation':'initialize-filesystem','state':'verified','service':record['service'],'filesystem':observed['filesystem']})
    print(json.dumps(observed))
