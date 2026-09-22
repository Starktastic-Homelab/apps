import json
from pathlib import Path
import subprocess
import sys
import tempfile
import sqlite3
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from initiator_probe import probe_filesystem, SQLITE_COPY_CHECK
from test_identity import R

class Runner:
    def __init__(self,**changes):
        self.calls=[];self.inputs=[];self.existing=False;self.mounted=False;self.login=0;self.fs='ext4';self.uuid=R['filesystem_uuid'];self.partition=False;self.dirty=False;self.bad_db=False;self.unmount_fail=False
        self.__dict__.update(changes)
    def run(self,args,**kwargs):
        self.calls.append(args);self.inputs.append(kwargs.get('input'));rc=0;out=''
        if args[:3]==['iscsiadm','-m','session']:rc=0 if self.existing else 21;out='tcp: [1] '+R['portal']+' '+R['iqn']
        elif args[0]=='findmnt':rc=0 if self.mounted else 1
        elif args[0]=='test':rc=1 # No stale by-path device before login.
        elif '--login' in args:rc=self.login
        elif args[0]=='readlink':out='/dev/sdz'
        elif args[0]=='udevadm':out='ID_SCSI_SERIAL=serial\nID_WWN_WITH_EXTENSION=naa'
        elif args[0]=='blockdev':out=str(R['bytes'])
        elif args[0]=='lsblk':out=json.dumps({'blockdevices':[{'children':[{}]} if self.partition else {}]})
        elif args[0]=='blkid':out=f'TYPE={self.fs}\nUUID={self.uuid}'
        elif args[0]=='dumpe2fs':out='Filesystem state: clean\nFilesystem features: has_journal'+(' needs_recovery' if self.dirty else '')
        elif args[0]=='mktemp':out='/var/tmp/retained-probe.owned'
        elif args[0]=='python3' and args[2]==SQLITE_COPY_CHECK:rc=1 if self.bad_db else 0;out='{"sqlite_verified":true,"marker_verified":true}'
        elif args[0]=='umount':rc=1 if self.unmount_fail else 0
        return subprocess.CompletedProcess(args,rc,stdout=out,stderr='')
    def called(self,text):return any(text in a for a in self.calls)

class ProbeTests(unittest.TestCase):
    def setUp(self):
        p=patch('initiator_probe.require_maintenance');p.start();self.addCleanup(p.stop)
        p=patch('initiator_probe.read_chap',return_value=dict(user='u',secret='secret'));p.start();self.addCleanup(p.stop)
    def test_existing_csi_session_refused_before_update_or_logout(self):
        runner=Runner(existing=True)
        with self.assertRaises(RuntimeError):probe_filesystem(R,runner)
        self.assertFalse(runner.called('--op'));self.assertFalse(runner.called('--logout'))
    def test_credentials_use_stdin_never_arguments(self):
        runner=Runner()
        with patch('initiator_probe.read_chap',return_value=dict(user='chap-user-private',secret='chap-password-private')):
            probe_filesystem(R,runner)
        self.assertFalse(any('chap-password-private' in str(a) or 'chap-user-private' in str(a) for a in runner.calls))
        self.assertTrue(any(v and 'chap-password-private' in v for v in runner.inputs))

    def test_login_15_is_not_owned(self):
        runner=Runner(login=15)
        with self.assertRaises(RuntimeError):probe_filesystem(R,runner)
        self.assertFalse(runner.called('--logout'));self.assertFalse(runner.called('mount'))
    def test_bad_filesystem_never_mounted_or_repaired(self):
        for changes in [dict(fs=''),dict(uuid='wrong'),dict(partition=True),dict(dirty=True),dict(mounted=True)]:
            runner=Runner(**changes)
            with self.subTest(changes=changes),self.assertRaises(RuntimeError):probe_filesystem(R,runner)
            self.assertFalse(runner.called('mount'));self.assertFalse(runner.called('mkfs.ext4'));self.assertFalse(runner.called('fsck'))
    def test_integrity_failure_cleans_only_owned_mount_and_session(self):
        runner=Runner(bad_db=True)
        with self.assertRaises(RuntimeError):probe_filesystem(R,runner)
        self.assertTrue(runner.called('umount'));self.assertTrue(runner.called('--logout'))
    def test_unmount_failure_never_disconnects_mounted_device(self):
        runner=Runner(unmount_fail=True)
        with self.assertRaises(RuntimeError):probe_filesystem(R,runner)
        self.assertFalse(runner.called('--logout'))
    def test_actual_sqlite_copy_checker_recovers_only_a_copy(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); (root/'data/data').mkdir(parents=True)
            db=root/'data/data/jellyfin.db'
            connection=sqlite3.connect(db)
            connection.execute('pragma journal_mode=WAL')
            connection.execute('create table entries(id integer)')
            connection.execute('insert into entries values (1)');connection.commit()
            (root/'.retained-volume.json').write_text(json.dumps({k:R[k] for k in ('service','marker','filesystem_uuid')}))
            before=db.read_bytes()
            result=subprocess.run([sys.executable,'-c',SQLITE_COPY_CHECK,str(root),json.dumps(R)],capture_output=True,text=True)
            connection.close()
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertTrue(json.loads(result.stdout)['sqlite_verified'])

    def test_success_readonly_noload_and_owned_cleanup(self):
        runner=Runner();self.assertTrue(probe_filesystem(R,runner)['filesystem_verified'])
        self.assertIn(['mount','-t','ext4','-o','ro,noload','/dev/sdz','/var/tmp/retained-probe.owned'],runner.calls)
        self.assertTrue(runner.called('--logout'))

if __name__=='__main__':unittest.main()
