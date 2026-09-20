"""Create the stopped lab NAS after validating IDs, capacity and guard state."""
import json
import os
import pathlib
import subprocess
import sys
import time

base = pathlib.Path(sys.argv[1])
m = json.loads((base/'manifest.json').read_text())
assert m['host_dir'] == str(base) and m['marker'] == base.name
status = json.loads((base/'guard-status.json').read_text())
assert status['production_ok'] is True and status['stop_reason'] is None
assert time.time()-status['at'] < 20 and status['available'] >= 20*1024**3
assert all(not pathlib.Path(f'/etc/pve/qemu-server/{v}.conf').exists() for v in (910, 911, 912, 913))
space = json.loads(subprocess.check_output(['pvesh','get','/nodes/pve/storage/vm-pool/status','--output-format','json'],text=True))
assert space['avail'] >= (50+80)*1024**3
assert os.statvfs(base).f_bavail*os.statvfs(base).f_frsize >= 16*1024**3
for bridge in m['bridges'].values():
    assert pathlib.Path('/sys/class/net', bridge, 'ifalias').read_text().strip() == m['marker']
iso_name = m['marker']+'.iso'
iso = pathlib.Path('/var/lib/vz/template/iso',iso_name)
assert not iso.exists()
os.rename(base/'TrueNAS-SCALE-25.10.6.iso',iso)
v = m['vms']['910']
subprocess.run(['qm','create','910','--name',v['name'],'--memory',str(v['memory']),
 '--cores','2','--sockets','1','--cpu','host','--machine','q35','--ostype','l26',
 '--scsihw','virtio-scsi-single','--scsi0','vm-pool:16,serial=ISCSILABBOOT',
 '--scsi1','vm-pool:16,serial=ISCSILABDATA','--net0','virtio,bridge=ilabctl0',
 '--net1','virtio,bridge=ilabstor0','--serial0','socket','--vga','serial0',
 '--smbios1','uuid='+v['uuid'],'--tags',m['marker'],'--onboot','0','--agent','1',
 '--ide2','local:iso/'+iso_name+',media=cdrom','--boot','order=ide2;scsi0'],check=True)
print(subprocess.check_output(['qm','config','910'],text=True))
