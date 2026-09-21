import pathlib,sys,json,shlex,subprocess,time
root=pathlib.Path('/home/benf/.codex/worktrees/retained-iscsi-lab/apps/tests/static-iscsi');sys.path.insert(0,str(root))
from ssh import ssh
records=json.loads((root/'.runtime/native-records.json').read_text());iqns=records[0]['initiators']
for i,port in enumerate((19111,19112,19113)):
 for attempt in range(30):
  try:
   ssh(port,'true',capture_output=True);break
  except subprocess.CalledProcessError:time.sleep(2)
 else:raise RuntimeError('SSH unavailable')
 ssh(port,'sudo mkdir -p /mnt/iscsi-seed && sudo mount -o ro /dev/disk/by-label/ISCSI_LAB /mnt/iscsi-seed',capture_output=True)
 ssh(port,'sudo sh -s',input=(root/'node-setup.sh').read_bytes(),stdout=subprocess.DEVNULL)
 ssh(port,'sudo install -m 600 /dev/stdin /etc/iscsi/initiatorname.iscsi',input=('InitiatorName='+iqns[i]+'\n').encode())
 ssh(port,'sudo systemctl restart iscsid',capture_output=True)
 print('Offline node staged with recorded initiator:',port,flush=True)
subprocess.run(['python3',str(root/'start_k3s.py'),'19111','19112','19113'],check=True)
subprocess.run(['python3','/tmp/static-iscsi-prep-route.py'],check=True)
subprocess.run(['python3','/tmp/static-iscsi-get-kubeconfig.py'],check=True)
