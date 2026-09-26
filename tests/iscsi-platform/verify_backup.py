"""Restore independent SQLite backups into a new local destination and verify."""
import json,pathlib,shutil,sqlite3
from lab import ROOT,PRIVATE
from lifecycle import verify_database
records=json.loads((ROOT/'records.json').read_text());receipts=[]
for r in records:
 source=PRIVATE/(r['service']+'-backup.sqlite');destination=PRIVATE/(r['service']+'-independent-restore.sqlite')
 assert not destination.exists()
 shutil.copyfile(source,destination)
 verify_database(destination,r['marker'])
 with sqlite3.connect(destination.resolve().as_uri()+'?mode=ro',uri=True) as c:
  values=dict(c.execute('select id,value from transactions'))
 # Backup was captured before subsequent expansion writes.
 expected=[json.loads(x) for x in (PRIVATE/'acknowledged.jsonl').read_text().splitlines() if json.loads(x)['marker']==r['marker'] and not json.loads(x)['id'].startswith('during-grow')]
 assert all(values.get(x['id'])==x['value'] for x in expected)
 receipts.append({'service':r['service'],'integrity':'ok','acknowledged_survived':len(expected),'independent_destination':True})
(ROOT/'independent-backup-result.json').write_text(json.dumps(receipts,indent=2));print(json.dumps(receipts))
