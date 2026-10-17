"""Replace only this run's three K3s VM disks; preserve lab NAS disks."""
import pathlib,json,subprocess,sys,time,uuid
base=pathlib.Path('/var/lib/vz/iscsi-lab-20260921-6c168a2e');sys.path.insert(0,str(base))
from guard import owns_vm,vm_config,host_sample
m=json.loads((base/'manifest.json').read_text());generation=int((base/'generation').read_text())+1 if (base/'generation').exists() else 1
for vmid in (910,911,912,913):
 assert owns_vm(vmid,vm_config(vmid),m)
for vmid in (911,912,913):
 c=vm_config(vmid)
 disks={k:v for k,v in c.items() if k.startswith(('virtio','ide','scsi','sata','unused','hostpci')) and k!='scsihw'}
 assert set(disks)=={'virtio0','ide0','ide2'}
 assert disks['virtio0'].startswith(f'vm-pool:vm-{vmid}-') and disks['ide0'].startswith(f'vm-pool:vm-{vmid}-')
 assert disks['ide2'].startswith('local:iso/'+m['marker']+'-seed.iso,')
s=json.loads((base/'guard-status.json').read_text());assert s['production_ok'] and not s['stop_reason'] and time.time()-s['at']<20
# Stop the nodes first, with identity checked immediately before each operation.
for vmid in (913,912,911,910):
 assert owns_vm(vmid,vm_config(vmid),m)
 if 'running' in subprocess.check_output(['qm','status',str(vmid)],text=True):
  result=subprocess.run(['qm','shutdown',str(vmid),'--timeout',('45' if vmid==910 else '15')],check=False,timeout=50)
  if result.returncode and vmid!=910:
   assert owns_vm(vmid,vm_config(vmid),m)
   subprocess.run(['qm','stop',str(vmid)],check=True,timeout=30)
  elif result.returncode:raise RuntimeError('NAS graceful shutdown failed')
 assert 'stopped' in subprocess.check_output(['qm','status',str(vmid)],text=True)
if generation==2:subprocess.run(['python3',str(base/'verify_backup_host.py')],check=True)
subprocess.run(['systemctl','stop',m['marker']+'-guard.service'],check=True)
assert host_sample()[0]>=20*1024**3
(base/f'manifest-before-rebuild-{generation}.json').write_text(json.dumps(m,indent=2))
for vmid in (911,912,913):
 assert owns_vm(vmid,vm_config(vmid),m)
 subprocess.run(['qm','destroy',str(vmid),'--purge','1','--destroy-unreferenced-disks','0'],check=True)
 m['vms'][str(vmid)]['uuid']=str(uuid.uuid4())
(base/'manifest.json').write_text(json.dumps(m,indent=2));(base/'generation').write_text(str(generation))
subprocess.run(['python3',str(base/'create_nodes.py'),str(base)],check=True)
for vmid in (911,912,913):
 assert owns_vm(vmid,vm_config(vmid),m)
 subprocess.run(['qm','set',str(vmid),'--ide2','local:iso/'+m['marker']+'-seed.iso,media=cdrom','--boot','order=virtio0'],check=True)
subprocess.run(['systemd-run','--unit='+m['marker']+'-guard','--property=Restart=on-failure','--property=RestartSec=2','--property=ExecStopPost=/usr/bin/python3 '+str(base/'guard.py')+' '+str(base/'manifest.json')+' --stop','/usr/bin/python3',str(base/'guard.py'),str(base/'manifest.json')],check=True)
for _ in range(30):
 s=json.loads((base/'guard-status.json').read_text())
 if s['production_ok'] and not s['stop_reason'] and time.time()-s['at']<10:break
 time.sleep(1)
else:raise RuntimeError('Guard not healthy')
assert owns_vm(910,vm_config(910),m)
subprocess.run(['qm','start','910'],check=True)
subprocess.run(['python3',str(base/'start_nodes.py')],check=True)
print(json.dumps({'generation':generation,'new_vms':m['vms'],'nas_disks_preserved':True}))
