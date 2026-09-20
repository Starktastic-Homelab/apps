"""Clone only stopped, identified lab guests; replace inherited NICs before boot."""
import json
import pathlib
import subprocess
import sys

base=pathlib.Path(sys.argv[1]);m=json.loads((base/'manifest.json').read_text())
assert m['host_dir']==str(base) and m['marker']==base.name
assert set(m['vms'])=={'910','911','912','913'}
for vmid in (911,912,913):
    assert not pathlib.Path(f'/etc/pve/qemu-server/{vmid}.conf').exists()
    v=m['vms'][str(vmid)]
    subprocess.run(['qm','clone','900',str(vmid),'--name',v['name'],'--full','1','--storage','vm-pool'],check=True)
    subprocess.run(['qm','set',str(vmid),'--delete','net0'],check=True)
    subprocess.run(['qm','set',str(vmid),'--memory',str(v['memory']),'--cores','2' if vmid==911 else '1',
        '--smbios1','uuid='+v['uuid'],'--tags',m['marker'],'--onboot','0',
        '--net0','virtio,bridge=ilabctl0','--net1','virtio,bridge=ilabstor0',
        '--ciuser','lab','--sshkeys',str(base/'id_ed25519.pub'),
        '--ipconfig0',f'ip=172.30.90.{vmid-900}/24','--ipconfig1',f'ip=172.30.91.{vmid-900}/24',
        '--nameserver','127.0.0.1','--searchdomain','invalid',
        '--boot','order=virtio0','--serial0','socket','--vga','serial0'],check=True)
    subprocess.run(['qm','resize',str(vmid),'virtio0','6G'],check=True)
    print(subprocess.check_output(['qm','status',str(vmid)],text=True).strip())
