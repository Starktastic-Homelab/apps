import pathlib,sys
sys.path.insert(0,str(__import__('pathlib').Path(__file__).resolve().parent))
from ssh import ssh,p
r=ssh(19111,'sudo cat /etc/rancher/k3s/k3s.yaml',capture_output=True,text=True)
config=r.stdout;assert 'server: https://127.0.0.1:6443' in config
(p/'kubeconfig').write_text(config.replace('https://127.0.0.1:6443','https://127.0.0.1:16443'));(p/'kubeconfig').chmod(0o600)
print('Private lab kubeconfig saved; credentials not displayed')
