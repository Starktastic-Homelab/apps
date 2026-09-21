"""Destructive controls target only the disposable, already-verified snapshot clone."""
import json,shlex,subprocess,uuid
from lab import PRIVATE,ROOT,receipt
from nas_rpc import NAS
from verify_recovery import capture
from identity import verify_native
from quiescence import require_quiesced
from ssh import ssh
require_quiesced();r=json.loads((PRIVATE/'clone-record.json').read_text());assert r['service']=='snapshot-restore-a' and r['dataset']=='iscsi_lab/volumes/snapshot-restore-a'
verify_native(r,capture(NAS()));r['chap']=json.loads((PRIVATE/'chap.json').read_text())
source=(ROOT/'initiator_guest.py').read_text();prefix=source[:source.index(" if r.get('initialize'):")]
control=prefix+''' assert r['service']=='snapshot-restore-a' and r['dataset']=='iscsi_lab/volumes/snapshot-restore-a'
 if r['damage']=='wrong-valid-filesystem':
  assert fs.get('UUID')==r['filesystem_uuid'];run(['mkfs.ext4','-m','0','-U',r['wrong_uuid'],device])
 elif r['damage']=='corrupt-superblock':
  assert fs.get('UUID')==r['wrong_uuid']
  with open(device,'r+b',buffering=0) as stream:stream.write(bytes(4096));os.fsync(stream.fileno())
 elif r['damage']=='partitioned':
  import struct
  assert not fs
  mbr=bytearray(512);mbr[446:462]=struct.pack('<B3sB3sII',0,b'\\0'*3,0x83,b'\\0'*3,2048,65536);mbr[510:]=b'\\x55\\xaa'
  with open(device,'r+b',buffering=0) as stream:stream.write(mbr);os.fsync(stream.fileno())
  run(['blockdev','--rereadpt',device]);run(['udevadm','settle'])
 with open(device,'rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
finally:run(base+['--logout'])
print(json.dumps({'sha256':digest}))
'''
# A read-only measurement variant bypasses only partition rejection, not native identity checks.
measure=source.replace("assert not json.loads(run(['lsblk','-J','-o','NAME,TYPE',device]).stdout)['blockdevices'][0].get('children'), 'Partitioned device refused'",'pass')
for case,expected in [('wrong-valid-filesystem','Filesystem identity mismatch before mount'),('corrupt-superblock','Filesystem identity mismatch before mount'),('partitioned','Partitioned device refused')]:
 verify_native(r,capture(NAS()));r.update(damage=case,wrong_uuid=r.get('wrong_uuid',str(uuid.uuid4())))
 before=json.loads(ssh(19112,'sudo python3 -c '+shlex.quote(control),input=json.dumps(r),capture_output=True,text=True).stdout)
 try:ssh(19112,'sudo python3 -c '+shlex.quote(source),input=json.dumps(dict(r,verify_marker=True)),capture_output=True,text=True)
 except subprocess.CalledProcessError as error:assert expected in error.stderr,error.stderr
 else:raise RuntimeError('Damaged clone accepted')
 measurement=dict(r);measurement.pop('filesystem_uuid');measurement.pop('marker');measurement['verify_marker']=False
 after=json.loads(ssh(19112,'sudo python3 -c '+shlex.quote(measure),input=json.dumps(measurement),capture_output=True,text=True).stdout)
 assert before['sha256']==after['sha256']
 receipt({'damaged_clone_case':case,'refused_before_writable_mount':True,'whole_device_hash_unchanged':True,'sha256':after['sha256']})
 print(case,'refused, bytes unchanged',flush=True)
