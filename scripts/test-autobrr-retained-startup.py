#!/usr/bin/env python3
"""Retained Autobrr startup must reject absent/wrong state without changing it."""
import hashlib
import os
import pathlib
import sqlite3
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
GUARD = ROOT / 'services/media/autobrr/manifests/retained-startup-guard.yaml'


class RetainedStartupTests(unittest.TestCase):
    def check(self, alter=None, accepted=False):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            config = root / 'config'
            config.mkdir()
            (config / '.homelab-autobrr-config').write_text('homelab/autobrr/config/v1\n')
            (config / 'config.toml').write_text('sessionSecret = "test-preserved-session-secret"\n')
            database = config / 'autobrr.db'
            with sqlite3.connect(database) as connection:
                for name in ('indexer', 'irc_network', 'filter', 'action', 'client', 'release_profile_duplicate'):
                    connection.execute(f'CREATE TABLE {name} (id INTEGER PRIMARY KEY)')
            if alter:
                alter(config)
            before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in config.iterdir() if p.is_file()}
            script = root / 'guard.py'
            script.write_text(yaml.safe_load(GUARD.read_text())['data']['guard.py'])
            result = subprocess.run([sys.executable, '-I', '-B', str(script), str(config)], capture_output=True)
            self.assertEqual(result.returncode == 0, accepted, result.stderr.decode())
            after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in config.iterdir() if p.is_file()}
            self.assertEqual(before, after)
            self.assertNotIn(b'test-preserved-session-secret', result.stdout + result.stderr)

    def test_retained_state_is_read_only(self):
        self.check(accepted=True)

    def test_missing_database_does_not_bootstrap(self):
        self.check(lambda p: (p / 'autobrr.db').unlink())

    def test_missing_config_does_not_bootstrap(self):
        self.check(lambda p: (p / 'config.toml').unlink())

    def test_missing_identity_is_rejected(self):
        self.check(lambda p: (p / '.homelab-autobrr-config').unlink())

    def test_wrong_identity_is_rejected(self):
        self.check(lambda p: (p / '.homelab-autobrr-config').write_text('another-app\n'))

    def test_missing_session_secret_is_rejected(self):
        self.check(lambda p: (p / 'config.toml').write_text('host = "0.0.0.0"\n'))

    def test_wrong_database_is_rejected(self):
        self.check(lambda p: (p / 'autobrr.db').write_bytes(b'not a sqlite database'))

    def test_wrong_sqlite_application_is_rejected(self):
        def alter(p):
            with sqlite3.connect(p / 'autobrr.db') as connection:
                connection.execute('DROP TABLE indexer')
        self.check(alter)


class RenderedStartupTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('AUTOBRR_RETAINED_RENDER'), 'actual Helm render supplied during qualification')
    def test_actual_mounts_fencing_and_preserved_settings(self):
        objects = list(yaml.safe_load_all(pathlib.Path(os.environ['AUTOBRR_RETAINED_RENDER']).read_text()))
        deployment = next(x for x in objects if x and x['kind'] == 'Deployment')
        pod = deployment['spec']['template']['spec']
        self.assertEqual(deployment['spec']['replicas'], 1)
        self.assertEqual(deployment['spec']['strategy']['type'], 'Recreate')
        self.assertNotIn('fsGroup', pod.get('securityContext') or {})
        self.assertEqual(pod['nodeSelector'], {'node-role.kubernetes.io/worker': 'true'})
        guard = pod['initContainers'][0]
        mounts = {x['mountPath']: x for x in guard['volumeMounts']}
        self.assertTrue(mounts['/config']['readOnly'])
        self.assertTrue(mounts['/retained-startup']['readOnly'])
        self.assertEqual(guard['securityContext']['runAsUser'], 1000)
        volumes = {x['name']: x for x in pod['volumes']}
        self.assertEqual(volumes[mounts['/config']['name']]['persistentVolumeClaim']['claimName'], 'autobrr-config-block')
        main = pod['containers'][0]
        image = yaml.safe_load((ROOT / 'services/media/autobrr/values.yaml').read_text())['controllers']['main']['containers']['main']['image']
        self.assertEqual(main['image'], image['repository'] + ':' + image['tag'])
        env = {x['name']: x.get('value') for x in main['env']}
        self.assertEqual(env['AUTOBRR__DATABASE_TYPE'], 'sqlite')
        self.assertEqual(env['AUTOBRR__OIDC_ENABLED'], 'true')
        self.assertEqual(env['TZ'], 'Asia/Jerusalem')
        self.assertEqual(main['envFrom'], [{'secretRef': {'name': 'autobrr-secret'}}])
        self.assertFalse(any(x and x['kind'] == 'PersistentVolumeClaim' for x in objects))


if __name__ == '__main__':
    unittest.main()
