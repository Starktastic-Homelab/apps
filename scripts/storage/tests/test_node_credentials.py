import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import node_credentials

class CredentialsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.iqn='iqn.2005-10.org.freenas.ctl:jellyfin';self.portal='10.9.8.30:3260'
        self.node=self.root/self.iqn/'10.9.8.30,3260';self.node.parent.mkdir()
        self.node.write_text('node.startup = automatic\nnode.session.auth.authmethod = None\nuntouched = value\n')
        self.chap={'user':'jellyfin','secret':'do-not-log-this'}
    def test_optional_fields_added_and_file_private(self):
        node_credentials.configure(self.root,self.iqn,self.portal,self.chap)
        result=self.node.read_text()
        self.assertIn('node.session.auth.password = do-not-log-this\n',result)
        self.assertIn('node.session.auth.username = jellyfin\n',result)
        self.assertIn('node.startup = manual\n',result)
        self.assertIn('untouched = value\n',result)
        self.assertEqual(self.node.stat().st_mode & 0o777,0o600)
    def test_existing_record_blocks_creation(self):
        with self.assertRaises(ValueError):node_credentials.check_new(self.root,self.iqn,self.portal)
    def test_symlink_duplicate_and_newline_rejected_without_change(self):
        for kind in ('symlink','duplicate','newline'):
            with self.subTest(kind=kind):
                original=self.node.read_text();chap=dict(self.chap)
                if kind=='symlink':
                    saved=self.root/'saved';self.node.rename(saved);self.node.symlink_to(saved)
                elif kind=='duplicate':self.node.write_text(original+'node.startup = manual\n')
                else:chap['secret']='bad\nnode.startup = automatic'
                before=self.node.read_text()
                with self.assertRaises(ValueError):node_credentials.configure(self.root,self.iqn,self.portal,chap)
                self.assertEqual(self.node.read_text(),before)
                if kind=='symlink':self.node.unlink();saved.rename(self.node)
                self.node.write_text(original)
    def test_path_traversal_rejected(self):
        with self.assertRaises(ValueError):node_credentials.check_new(self.root,'../elsewhere',self.portal)
