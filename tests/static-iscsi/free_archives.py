import sys,shlex
sys.path.insert(0,str(__import__('pathlib').Path(__file__).resolve().parent))
from ssh import ssh
remote='''import pathlib,hashlib,json
seed=pathlib.Path('/mnt/iscsi-seed');target=pathlib.Path('/var/lib/rancher/k3s/agent/images')
checks=dict((line.split()[1],line.split()[0]) for line in (seed/'SHA256SUMS').read_text().splitlines())
removed=[]
for name in ['k3s-airgap-images-amd64.tar.zst','csi-0.tar','csi-1.tar','csi-2.tar','csi-3.tar']:
 p=target/name
 if not p.exists():continue
 assert p.is_file() and not p.is_symlink()
 assert hashlib.file_digest(p.open('rb'),'sha256').hexdigest()==checks[name]
 p.unlink();removed.append(name)
print(json.dumps({'removed_verified_redundant_archives':removed}))
'''
for port in (19111,19112,19113):
 print(port,ssh(port,'sudo python3 -c '+shlex.quote(remote),capture_output=True,text=True).stdout)
