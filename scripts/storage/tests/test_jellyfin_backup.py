import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from jellyfin_backup import capture, capture_stream, verify_restore, verify_application, write_json, IMAGE

class BackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.source=self.root/'source';self.source.mkdir()
        (self.source/'data/data').mkdir(parents=True);(self.source/'plugins').mkdir()
        (self.source/'plugins/plugin.db').write_bytes(b'LiteDB-fixture')
        (self.source/'system.xml').write_text('<ServerConfiguration/>')
        db=sqlite3.connect(self.source/'data/data/jellyfin.db');db.execute('create table entries(id integer)');db.commit();db.close()
        self.destination=self.root/'approved'/'capture'
        self.meta=dict(image=IMAGE,source=dict(dataset_guid='source-guid',path='/mnt/apps/pv/media/jellyfin-config'),
                       snapshot=dict(guid='snapshot-guid'),held=True,no_writers=True)
        p=patch('jellyfin_backup.BACKUP_ROOT',self.root/'approved');p.start();self.addCleanup(p.stop)
    def test_roundtrip_preserves_files_metadata_and_xattrs(self):
        os.setxattr(self.source/'system.xml','user.test',b'metadata')
        archive=capture(self.source,self.destination,self.meta)
        result=verify_restore(archive,self.root/'restored')
        self.assertTrue(result['files_verified']);self.assertTrue(result['sqlite_verified'])
        self.assertFalse(result['application_verified'])
        self.assertFalse((self.destination/'passed.json').exists())
        self.assertEqual(os.getxattr(self.root/'restored/system.xml','user.test'),b'metadata')
    def test_failed_partial_producer_never_publishes(self):
        command=[sys.executable,'-c',"import sys;sys.stdout.buffer.write(b'partial');sys.exit(1)"]
        with self.assertRaises(RuntimeError):capture_stream(command,self.destination,self.meta,{})
        self.assertFalse((self.destination/'config.tar').exists())
    def test_disk_full_never_publishes(self):
        with patch('jellyfin_backup.shutil.copyfileobj',side_effect=OSError('No space')):
            with self.assertRaises(OSError):capture(self.source,self.destination,self.meta)
        self.assertFalse((self.destination/'config.tar').exists())
    def test_metadata_failure_never_publishes(self):
        with patch('jellyfin_backup.write_json',side_effect=OSError('No space')):
            with self.assertRaises(OSError):capture(self.source,self.destination,self.meta)
        self.assertFalse((self.destination/'config.tar').exists())
    def test_wrong_hash_and_truncated_archive_fail(self):
        archive=capture(self.source,self.destination,self.meta)
        archive.write_bytes(archive.read_bytes()[:200])
        with self.assertRaises(ValueError):verify_restore(archive,self.root/'restored')
    def test_escape_entries_are_rejected(self):
        for name,link in [('/outside',None),('../outside',None),('escape','../../outside')]:
            folder=self.root/str(len(list(self.root.iterdir())));folder.mkdir();archive=folder/'config.tar'
            with tarfile.open(archive,'w') as tar:
                entry=tarfile.TarInfo(name)
                if link:entry.type=tarfile.SYMTYPE;entry.linkname=link
                tar.addfile(entry)
            manifest=dict(self.meta,sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),inventory={})
            archive.with_suffix('.json').write_text(json.dumps(manifest))
            with self.subTest(name=name),self.assertRaises(ValueError):verify_restore(archive,folder/'restore')
    def test_unapproved_or_symlinked_destination_refused(self):
        with self.assertRaises(ValueError):capture(self.source,self.root/'outside',self.meta)
        self.destination.parent.mkdir();self.destination.symlink_to(self.source,target_is_directory=True)
        with self.assertRaises(ValueError):capture(self.source,self.destination,self.meta)
    def test_missing_plugin_or_wrong_ownership_is_not_a_verified_restore(self):
        archive=capture(self.source,self.destination,self.meta)
        manifest=json.loads(archive.with_suffix('.json').read_text())
        manifest['inventory']['plugins/missing.db']=manifest['inventory']['plugins/plugin.db']
        archive.with_suffix('.json').write_text(json.dumps(manifest))
        with self.assertRaises(ValueError):verify_restore(archive,self.root/'restored')
    def test_changed_ownership_or_unpreservable_xattrs_fail(self):
        archive=capture(self.source,self.destination,self.meta)
        manifest=json.loads(archive.with_suffix('.json').read_text())
        manifest['inventory']['system.xml']['uid']+=1
        archive.with_suffix('.json').write_text(json.dumps(manifest))
        with self.assertRaises(ValueError):verify_restore(archive,self.root/'bad-owner')
        self.assertFalse((self.destination/'passed.json').exists())

    def test_setup_wizard_is_not_an_accepted_application_restore(self):
        metadata=dict(self.meta,server_id_sha256='expected',user_count=1,item_counts={},plugins=[])
        archive=capture(self.source,self.destination,metadata)
        key=self.root/'key';key.write_text('synthetic');key.chmod(0o600)
        commands=[]
        def docker(args,**kwargs):
            commands.append(args)
            if args[1] == 'exec':
                self.assertEqual(kwargs['input'], 'header = \"Authorization: MediaBrowser Token=\\\"synthetic\\\"\"\n')
            output='Healthy' if args[-1].endswith('/health') else json.dumps({'StartupWizardCompleted':False})
            return subprocess.CompletedProcess(args,0,stdout=output)
        with patch('jellyfin_backup.subprocess.run',side_effect=docker):
            with self.assertRaises(ValueError):verify_application(archive,self.root/'app-copy',key)
        self.assertFalse((self.destination/'passed.json').exists())
        launched=next(c for c in commands if c[1]=='run')
        self.assertIn('none',launched);self.assertEqual(launched[-1],IMAGE)
        self.assertEqual(commands[-1][1:3],['rm','-f'])

    def test_fsync_failure_cannot_publish_accepted_application_receipt(self):
        server_id='synthetic-server'
        metadata=dict(self.meta,server_id_sha256=hashlib.sha256(server_id.encode()).hexdigest(),
                      user_count=1,item_counts={'MovieCount':1},plugins=[])
        archive=capture(self.source,self.destination,metadata)
        key=self.root/'key';key.write_text('synthetic');key.chmod(0o600)
        responses={'/health':'Healthy','/System/Info/Public':json.dumps({'StartupWizardCompleted':True,'Id':server_id}),
                   '/Users':'[{}]','/Items/Counts':'{"MovieCount":1}','/Plugins':'[]'}
        def docker(args,**kwargs):
            output=next((v for k,v in responses.items() if args[-1].endswith(k)),'')
            return subprocess.CompletedProcess(args,0,stdout=output)
        with patch('jellyfin_backup.subprocess.run',side_effect=docker),patch('jellyfin_backup.subprocess.check_output',return_value=b''),patch('jellyfin_backup.os.fsync',side_effect=OSError('sync failed')):
            with self.assertRaises(OSError):verify_application(archive,self.root/'app-copy',key)
        self.assertFalse((self.destination/'passed.json').exists())

    def test_directory_sync_failure_removes_new_receipt_without_overwriting_old(self):
        path=self.root/'passed.json'
        with patch('jellyfin_backup.os.fsync',side_effect=[None,OSError('directory sync failed')]):
            with self.assertRaises(OSError):write_json(path,{'application_verified':True})
        self.assertFalse(path.exists())
        path.write_text('original')
        with self.assertRaises(FileExistsError):write_json(path,{'replacement':True})
        self.assertEqual(path.read_text(),'original')

    def test_sqlite_wal_is_recovered_on_copy(self):
        connection=sqlite3.connect(self.source/'data/data/jellyfin.db');connection.execute('pragma journal_mode=WAL')
        connection.execute('insert into entries values (7)');connection.commit()
        archive=capture(self.source,self.destination,self.meta)
        connection.close()
        result=verify_restore(archive,self.root/'restored');self.assertTrue(result['sqlite_verified'])
        restored=sqlite3.connect(self.root/'restored/data/data/jellyfin.db')
        self.assertEqual(restored.execute('select * from entries').fetchall(),[(7,)]);restored.close()

if __name__=='__main__':unittest.main()
