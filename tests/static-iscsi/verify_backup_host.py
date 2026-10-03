"""Restore synthetic backups on the hypervisor while the owned NAS is stopped."""
import pathlib,json,sys,subprocess,sqlite3,shutil,hashlib
base=pathlib.Path('/var/lib/vz/iscsi-lab-20260921-6c168a2e');sys.path.insert(0,str(base));from guard import owns_vm,vm_config
m=json.loads((base/'manifest.json').read_text());assert owns_vm(910,vm_config(910),m)
assert 'stopped' in subprocess.check_output(['qm','status','910'],text=True)
acks=json.loads((base/'backup-acks.json').read_text());records=json.loads((base/'backup-records.json').read_text());results=[]
for r in records:
 if r['service']=='blank-probe':continue
 source=base/(r['service']+'-backup.sqlite');destination=base/(r['service']+'-independent-restore.sqlite');assert not destination.exists();shutil.copyfile(source,destination)
 with sqlite3.connect(destination) as db:
  assert db.execute('pragma integrity_check').fetchall()==[('ok',)]
  assert db.execute('select marker from identity').fetchall()==[(r['marker'],)]
  rows=dict(db.execute('select id,value from transactions'))
  expected=[a for a in acks if a['marker']==r['marker']]
  assert all(rows.get(a['id'])==a['value'] for a in expected)
 results.append({'service':r['service'],'rows':len(expected),'integrity':'ok','sha256':hashlib.sha256(source.read_bytes()).hexdigest()})
assert owns_vm(910,vm_config(910),m) and 'stopped' in subprocess.check_output(['qm','status','910'],text=True)
result={'nas_powered_off_throughout_restore':True,'restored_outside_nas':True,'services':results}
(base/'independent-backup-result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
