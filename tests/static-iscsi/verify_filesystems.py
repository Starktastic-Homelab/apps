import sys,json,shlex,subprocess

from verify_recovery import verify_all
from lab import ROOT,PRIVATE
from ssh import ssh
records=verify_all();chap=json.loads((PRIVATE/'chap.json').read_text())
for record in records:
 if record['service']=='blank-probe':continue
 try:r=ssh(19112,'sudo python3 -c '+shlex.quote((ROOT/'initiator_guest.py').read_text()),input=json.dumps(dict(record,chap=chap,verify_marker=True)),capture_output=True,text=True)
 except subprocess.CalledProcessError as error:
  raise SystemExit(error.stderr)
 observed=json.loads(r.stdout)
 assert observed['filesystem']['TYPE']=='ext4' and observed['filesystem']['UUID']==record['filesystem_uuid']
 print(json.dumps({'service':record['service'],'filesystem_uuid':observed['filesystem']['UUID'],'native_and_filesystem_verified':True}))
