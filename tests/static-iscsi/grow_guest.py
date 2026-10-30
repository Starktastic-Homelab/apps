"""Explicit offline expansion; no filesystem initialization path."""
import sys,json,subprocess,pathlib,time,hashlib,os,stat
r=json.load(sys.stdin)
def run(args,check=True):
 p=subprocess.run(args,capture_output=True,text=True)
 if check and p.returncode:raise RuntimeError("Initiator command failed: "+args[0]+" ("+str(p.returncode)+")")
 return p
# A CSI-owned session is not ours to update or disconnect.
sessions=run(['iscsiadm','-m','session'],False)
assert sessions.returncode in (0,21), 'Cannot determine existing sessions'
assert r['iqn'] not in sessions.stdout.split(), 'Existing target session refused before node updates'
base=['iscsiadm','-m','node','-T',r['iqn'],'-p',r['portal']]
run(base+['--op','new'])
for key,value in [('node.session.auth.authmethod','CHAP'),('node.session.auth.username',r['chap']['user']),('node.session.auth.password',r['chap']['secret']),('node.startup','manual')]:
 run(base+['--op','update','-n',key,'-v',value])
login=run(base+['--login'],False);assert login.returncode==0, 'Probe did not create a session; do not disconnect an existing owner'
try:
 path=pathlib.Path('/dev/disk/by-path/ip-'+r['portal']+'-iscsi-'+r['iqn']+'-lun-'+str(r['lun']))
 for _ in range(30):
  if path.exists():break
  time.sleep(1)
 assert path.exists() and stat.S_ISBLK(path.stat().st_mode)
 device=str(path.resolve())
 props=dict(line.split('=',1) for line in run(['udevadm','info','--query=property','--name',device]).stdout.splitlines() if '=' in line)
 assert props.get('ID_SCSI_SERIAL')==r['serial'], 'Extent serial mismatch'
 assert props.get('ID_WWN_WITH_EXTENSION')==r['naa'], 'Extent NAA mismatch'
 size=int(run(['blockdev','--getsize64',device]).stdout);assert size==r['bytes']
 assert not json.loads(run(['lsblk','-J','-o','NAME,TYPE',device]).stdout)['blockdevices'][0].get('children'), 'Partitioned device refused'
 mounted=run(['findmnt','-rn','-S',device],False);assert mounted.returncode==1, 'Device already mounted'
 result=run(['blkid','-p','-o','export',device],False);assert result.returncode in [0,2]
 fs=dict(line.split('=',1) for line in result.stdout.splitlines() if '=' in line)
 digest=None
 assert fs.get('TYPE')=='ext4' and fs.get('UUID')==r['filesystem_uuid'], 'Filesystem identity mismatch'
 def filesystem_bytes():
  fields=dict(line.split(':',1) for line in run(['dumpe2fs','-h',device]).stdout.splitlines() if ':' in line)
  return int(fields['Block count'])*int(fields['Block size'])
 before=filesystem_bytes()
 if r['action']=='grow':
  checked=run(['e2fsck','-pf',device],False);assert checked.returncode in (0,1),'Offline check failed'
  run(['resize2fs',device])
 after=filesystem_bytes()
 assert before<=r['bytes'] and after<=r['bytes']
 if r['action']=='grow':assert after==r['bytes'],'Filesystem growth incomplete'
finally:
 run(base+['--logout'])
print(json.dumps({'service':r['service'],'device_bytes':size,'filesystem_before':before,'filesystem_after':after,'filesystem_uuid':fs['UUID']}))
