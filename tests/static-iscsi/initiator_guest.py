import sys,json,subprocess,pathlib,time,hashlib,os,stat
r=json.load(sys.stdin)
def run(args,check=True):
 p=subprocess.run(args,capture_output=True,text=True)
 if check and p.returncode:raise RuntimeError("Initiator command failed: "+args[0]+" ("+str(p.returncode)+")")
 return p
base=['iscsiadm','-m','node','-T',r['iqn'],'-p',r['portal']]
run(base+['--op','new'])
for key,value in [('node.session.auth.authmethod','CHAP'),('node.session.auth.username',r['chap']['user']),('node.session.auth.password',r['chap']['secret']),('node.startup','manual')]:
 run(base+['--op','update','-n',key,'-v',value])
login=run(base+['--login'],False);assert login.returncode in [0,15]
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
 if r.get('initialize'):
  assert not fs, 'Existing filesystem must never be initialized'
  assert str(__import__('uuid').UUID(r['filesystem_uuid']))==r['filesystem_uuid']
  run(['mkfs.ext4','-m','0','-U',r['filesystem_uuid'],device])
  result=run(['blkid','-p','-o','export',device])
  fs=dict(line.split('=',1) for line in result.stdout.splitlines() if '=' in line)
  assert fs.get('TYPE')=='ext4' and fs.get('UUID')==r['filesystem_uuid']
 else:
  if r.get('filesystem_uuid'):
   assert fs.get('TYPE')=='ext4' and fs.get('UUID')==r['filesystem_uuid'], 'Filesystem identity mismatch before mount'
  if r.get('verify_marker'):
   import tempfile,sqlite3
   with tempfile.TemporaryDirectory(prefix='iscsi-verify-') as directory:
    run(['mount','-t','ext4','-o','ro,noload',device,directory])
    try:
     db=pathlib.Path(directory)/'catalog.sqlite'
     assert db.is_file(), 'Existing SQLite database required'
     # Recover a private copy of SQLite WAL; the block filesystem remains ro,noload.
     import shutil
     with tempfile.TemporaryDirectory(prefix='sqlite-copy-') as copydir:
      copydb=pathlib.Path(copydir)/'catalog.sqlite'
      shutil.copyfile(db,copydb)
      if pathlib.Path(str(db)+'-wal').exists():shutil.copyfile(str(db)+'-wal',str(copydb)+'-wal')
      with sqlite3.connect(copydb.as_uri()+'?mode=rw',uri=True) as connection:
       assert connection.execute('select marker from identity').fetchall()==[(r['marker'],)], 'Service marker mismatch'
       assert connection.execute('pragma integrity_check').fetchall()==[('ok',)], 'SQLite copy integrity failure'
       if r.get('verify_rows'):
        rows=dict(connection.execute('select id,value from transactions').fetchall())
        assert all(rows.get(a['id'])==a['value'] for a in r['verify_rows']), 'Acknowledged rows missing'
    finally:run(['umount',directory])
  with open(device,'rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
finally:
 run(base+['--logout'])
print(json.dumps({'service':r['service'],'device':device,'serial':props['ID_SCSI_SERIAL'],'naa':props['ID_WWN_WITH_EXTENSION'],'bytes':size,'sha256':digest,'filesystem':fs}))
