"""SQLite online backups copied outside the NAS and cluster."""
import hashlib,json,os,subprocess
from lab import PRIVATE,ENV,kubectl,receipt
records=json.loads((PRIVATE/'native-records.json').read_text())
for r in records:
 if r['service']=='blank-probe':continue
 service=r['service'];kubectl('exec','-n','iscsi-fixture',service+'-0','--','python','/fixture/fixture.py','backup')
 result=subprocess.run(['kubectl','exec','-n','iscsi-fixture',service+'-0','--','cat','/tmp/backup.sqlite'],env=ENV,capture_output=True,check=True)
 with (PRIVATE/(service+'-backup.sqlite')).open('wb') as stream:stream.write(result.stdout);stream.flush();os.fsync(stream.fileno())
 receipt({'external_backup':service,'sha256':hashlib.sha256(result.stdout).hexdigest(),'bytes':len(result.stdout)})
(PRIVATE/'backup-acks.json').write_text(json.dumps([json.loads(x) for x in (PRIVATE/'acknowledged.jsonl').read_text().splitlines()],indent=2))
print('Both consistent SQLite backups and backup-time acknowledgements captured outside NAS.')
