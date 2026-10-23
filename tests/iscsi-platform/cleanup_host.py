"""Delete only this run's identity-verified disposable infrastructure."""
import json
import pathlib
import subprocess
import sys
from guard import owns_vm, vm_config

base = pathlib.Path(sys.argv[1])
manifest = json.loads((base / 'manifest.json').read_text())
marker = manifest['marker']
assert base == pathlib.Path('/var/lib/vz') / marker
assert marker == 'iscsi-lab-20260920-1d3e8de3'
# Validate everything before stopping or deleting anything.
for vmid in (910, 911, 912, 913):
    config = vm_config(vmid)
    assert owns_vm(vmid, config, manifest)
    disks = {k: v for k, v in config.items() if k.startswith(('scsi', 'virtio', 'ide', 'sata', 'unused', 'hostpci')) and k != 'scsihw'}
    expected = {'scsi0', 'scsi1'} if vmid == 910 else {'virtio0', 'ide0', 'ide2'}
    assert set(disks) == expected, (vmid, sorted(disks))
    for key, value in disks.items():
        if key == 'ide2':
            assert value.startswith('local:iso/' + marker + '-seed.iso,media=cdrom')
        else:
            assert value.startswith(f'vm-pool:vm-{vmid}-')
    if vmid == 910:
        assert 'serial=ISCSILABBOOT' in disks['scsi0'] and 'serial=ISCSILABDATA' in disks['scsi1']
for bridge in manifest['bridges'].values():
    assert pathlib.Path('/sys/class/net', bridge, 'ifalias').read_text().strip() == marker

subprocess.run(['systemctl', 'stop', marker + '-guard.service'], check=True)
subprocess.run(['systemctl', 'stop', marker + '-dhcp.service'], check=True)
for vmid in (913, 912, 911, 910):
    assert owns_vm(vmid, vm_config(vmid), manifest)
    assert 'stopped' in subprocess.check_output(['qm', 'status', str(vmid)], text=True)
    subprocess.run(['qm', 'destroy', str(vmid), '--purge', '1', '--destroy-unreferenced-disks', '0'], check=True)
    assert not pathlib.Path(f'/etc/pve/qemu-server/{vmid}.conf').exists()
for suffix in ('.iso', '-seed.iso'):
    image = pathlib.Path('/var/lib/vz/template/iso') / (marker + suffix)
    assert image.is_file() and not image.is_symlink()
    image.unlink()
for bridge in manifest['bridges'].values():
    assert not list(pathlib.Path('/sys/class/net', bridge, 'brif').iterdir()), 'Unexpected remaining bridge ports'
    subprocess.run(['ip', 'link', 'delete', bridge, 'type', 'bridge'], check=True)
subprocess.run(['nft', 'delete', 'table', 'inet', marker.replace('-', '_')], check=True)
print(json.dumps({'removed_vm_ids': [910, 911, 912, 913], 'removed_bridges': list(manifest['bridges'].values()), 'removed_nft_table': marker.replace('-', '_')}))
# The caller separately reconciles capacity and production before deleting staging.
