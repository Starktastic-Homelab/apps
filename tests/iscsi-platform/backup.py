"""Copy a SQLite online backup outside the lab; binary payload never reaches logs."""
import json,subprocess,os,hashlib
from lab import ROOT,PRIVATE,ENV,kubectl
records=json.loads((ROOT/'records.json').read_text())
for r in records:
 pod=r['service']+'-0'
 kubectl('exec','-n','iscsi-fixture',pod,'--','python','/fixture/fixture.py','backup')
 p=PRIVATE/(r['service']+'-backup.sqlite')
 with p.open('wb') as f:
  subprocess.run(['kubectl','exec','-n','iscsi-fixture',pod,'--','cat','/tmp/backup.sqlite'],env=ENV,stdout=f,check=True)
  f.flush();os.fsync(f.fileno())
 print(json.dumps({'service':r['service'],'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}))
