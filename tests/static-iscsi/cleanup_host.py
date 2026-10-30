"""Scoped cleanup of a complete or partially built disposable lab."""
import json,pathlib,subprocess,sys
from guard import owns_vm,vm_config,stop_owned
base=pathlib.Path(sys.argv[1]);m=json.loads((base/'manifest.json').read_text())
assert base==pathlib.Path('/var/lib/vz')/m['marker']
assert m['marker']=='iscsi-lab-20260921-6c168a2e'
for vmid in (910,911,912,913):
 c=vm_config(vmid)
 if c is None:continue
 assert owns_vm(vmid,c,m), 'Foreign VM identity'
 for key,value in c.items():
  if key=='scsihw':continue
  if key.startswith(('scsi','virtio','ide','sata','unused','hostpci')):
   assert not key.startswith('hostpci')
   assert value.startswith(f'vm-pool:vm-{vmid}-') or (key=='ide2' and value.split(',')[0] in ['local:iso/'+m['marker']+'.iso','local:iso/'+m['marker']+'-seed.iso']), 'Unexpected disk'
for bridge in m['bridges'].values():
 p=pathlib.Path('/sys/class/net',bridge)
 if p.exists():assert (p/'ifalias').read_text().strip()==m['marker']
stop_owned(m)
subprocess.run(['systemctl','stop',m['marker']+'-guard.service'],check=True)
subprocess.run(['systemctl','stop',m['marker']+'-dhcp.service'],check=False)
for vmid in (913,912,911,910):
 c=vm_config(vmid)
 if c is None:continue
 assert owns_vm(vmid,c,m)
 assert 'stopped' in subprocess.check_output(['qm','status',str(vmid)],text=True)
 subprocess.run(['qm','destroy',str(vmid),'--purge','1','--destroy-unreferenced-disks','0'],check=True)
for suffix in ('.iso','-seed.iso'):
 p=pathlib.Path('/var/lib/vz/template/iso')/(m['marker']+suffix)
 if p.exists():
  assert p.is_file() and not p.is_symlink();p.unlink()
for bridge in m['bridges'].values():
 p=pathlib.Path('/sys/class/net',bridge)
 if p.exists():
  assert (p/'ifalias').read_text().strip()==m['marker'] and not list((p/'brif').iterdir())
  subprocess.run(['ip','link','delete',bridge,'type','bridge'],check=True)
table=m['marker'].replace('-','_')
exists=subprocess.run(['nft','list','table','inet',table],capture_output=True).returncode==0
if exists:subprocess.run(['nft','delete','table','inet',table],check=True)
print(json.dumps({'removed_vm_ids':[910,911,912,913],'marker':m['marker']}))
