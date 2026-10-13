#!/usr/bin/env python3
"""Check Prowlarr retained config and its inactive PostgreSQL/CSI composition."""
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

import yaml

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'scripts/prowlarr-postgresql'
PASSWORDS = {'main': 'fixture "secret"; with spaces', 'log': 'fixture-log-secret'}


def connection(kind):
    password = PASSWORDS[kind].replace('"', '""')
    return (f'Host=postgres-postgresql.databases;Port=5432;Username=prowlarr_{kind};'
            f'Password="{password}";Database=prowlarr_{kind};Maximum Pool Size=5;Timeout=10')


class RetainedConfigTests(unittest.TestCase):
    def check(self, alter=None, accepted=False):
        self.assertTrue((PACKAGE / 'guard.py').is_file(), 'Prowlarr retained guard not implemented')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = root / 'config'
            credentials = root / 'credentials'
            config.mkdir()
            credentials.mkdir()
            (config / '.homelab-prowlarr-config').write_text('homelab/prowlarr/config/v1\n')
            xml = ET.Element('Config')
            ET.SubElement(xml, 'ApiKey').text = 'fixture-api-secret'
            for kind in ('main', 'log'):
                ET.SubElement(xml, f'Postgres{kind.title()}DbConnectionString').text = connection(kind)
                (credentials / f'{kind}-password').write_text(PASSWORDS[kind])
            ET.ElementTree(xml).write(config / 'config.xml', encoding='utf-8')
            if alter:
                alter(config, credentials)
            def snapshot():
                return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).digest()
                        for p in root.rglob('*') if p.is_file()}
            before = snapshot()
            result = subprocess.run([sys.executable, '-I', '-B', str(PACKAGE / 'guard.py'),
                                     str(config), str(credentials)], capture_output=True)
            self.assertEqual(result.returncode == 0, accepted, result.stderr.decode())
            self.assertEqual(before, snapshot(), 'Guard changed retained data or credentials')
            for secret in ('fixture-api-secret', *PASSWORDS.values()):
                self.assertNotIn(secret.encode(), result.stdout + result.stderr)

    def test_preserved_config_is_accepted_read_only(self):
        self.check(accepted=True)

    def test_missing_or_wrong_marker_is_rejected(self):
        self.check(lambda c, _: (c / '.homelab-prowlarr-config').unlink())
        self.check(lambda c, _: (c / '.homelab-prowlarr-config').write_text('other\n'))

    def test_missing_or_malformed_config_is_rejected(self):
        self.check(lambda c, _: (c / 'config.xml').unlink())
        self.check(lambda c, _: (c / 'config.xml').write_text('<bad'))

    def test_config_with_missing_api_key_is_rejected(self):
        self.change_field('ApiKey', '')

    def change_field(self, name, value):
        def alter(c, _):
            tree = ET.parse(c / 'config.xml')
            field = tree.getroot().find(name)
            if field is None:
                field = ET.SubElement(tree.getroot(), name)
            field.text = value
            tree.write(c / 'config.xml')
        self.check(alter)

    def test_wrong_main_and_log_connection_is_rejected(self):
        for kind in ('main', 'log'):
            self.change_field(f'Postgres{kind.title()}DbConnectionString', connection(kind) + ';Pooling=false')

    def test_missing_password_is_rejected(self):
        for kind in ('main', 'log'):
            self.check(lambda _, p, k=kind: (p / f'{k}-password').unlink())
            self.check(lambda _, p, k=kind: (p / f'{k}-password').write_text(''))

    def test_duplicate_fields_are_rejected(self):
        def alter(c, _):
            tree = ET.parse(c / 'config.xml')
            ET.SubElement(tree.getroot(), 'PostgresMainDbConnectionString').text = connection('main')
            tree.write(c / 'config.xml')
        self.check(alter)

    def test_conflicting_scalar_configuration_is_rejected(self):
        for name in ('PostgresHost', 'PostgresPort', 'PostgresUser', 'PostgresPassword',
                     'PostgresMainDb', 'PostgresLogDb'):
            self.change_field(name, 'conflict')

    def test_active_sqlite_files_are_rejected(self):
        for name in ('prowlarr.db', 'prowlarr.db-wal', 'prowlarr.db-shm',
                     'logs.db', 'logs.db-wal', 'logs.db-shm'):
            with self.subTest(name=name):
                self.check(lambda c, _, n=name: (c / n).write_bytes(b'fixture'))

    def test_symlinked_retained_identity_or_config_is_rejected(self):
        def replace(path):
            original = path.with_name(path.name + '.original')
            path.rename(original)
            path.symlink_to(original)
        self.check(lambda c, _: replace(c / '.homelab-prowlarr-config'))
        self.check(lambda c, _: replace(c / 'config.xml'))

    def test_native_secret_projection_is_accepted(self):
        def alter(_, p):
            target = p / '..fixture'
            target.mkdir()
            for kind in ('main', 'log'):
                path = p / f'{kind}-password'
                path.rename(target / path.name)
                path.symlink_to('..data/' + path.name)
            (p / '..data').symlink_to(target.name)
        self.check(alter, accepted=True)

    def test_password_symlink_outside_credentials_is_rejected(self):
        def alter(c, p):
            (c / 'outside').write_text(PASSWORDS['main'])
            (p / 'main-password').unlink()
            (p / 'main-password').symlink_to(c / 'outside')
        self.check(alter)


if __name__ == '__main__':
    unittest.main()
