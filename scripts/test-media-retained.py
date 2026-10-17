#!/usr/bin/env python3
"""Retained media state must fail closed before an empty stock engine can start."""
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / 'scripts/media-retained/guard.py'
# Independent fixtures: a wrong main DB, claim or subpath must fail acceptance.
LAYOUTS = {
    'sonarr': ('sonarr.db', 'logs.db', 'config.xml'),
    'sonarr-ru': ('sonarr.db', 'logs.db', 'config.xml'),
    'radarr': ('radarr.db', 'logs.db', 'config.xml'),
    'radarr-ru': ('radarr.db', 'logs.db', 'config.xml'),
    'lidarr': ('lidarr.db', 'logs.db', 'config.xml'),
    'cleanuparr': ('DataProtection-Keys/', 'jwt-key.bin', 'plex-client-id.txt'),
    'navidrome': ('navidrome.db',),
    'audiobookshelf': ('config/absdatabase.sqlite', 'metadata/'),
    'shelfmark': ('users.db', 'settings.json', '.flask_secret'),
    'cineplete': ('config/config.yml', 'data/overrides.json', 'data/results.json'),
}


class GuardTests(unittest.TestCase):
    def check(self, app, alter=None, accepted=False, environment=None):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'root'
            root.mkdir()
            marker = root / ('.homelab-' + app + '-data')
            marker.write_text('homelab/' + app + '/data/v1\n')
            for name in LAYOUTS[app]:
                path = root / name
                if name.endswith('/'):
                    path.mkdir(parents=True)
                    if app == 'cleanuparr':
                        (path / 'key-isolated.xml').write_text('<key id="isolated" />')
                    continue
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'x' * 32 if name == 'jwt-key.bin' else b'SQLite format 3\0' + b'\0' * 100 if path.suffix in ('.db', '.sqlite') else b'private-state')
            if alter:
                alter(root, marker)
            def digest():
                return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in root.rglob('*') if p.is_file() and not p.is_symlink()}
            before = digest()
            runtime = Path(temporary) / 'guard.py'
            runtime.write_text(yaml.safe_load((ROOT / 'scripts/media-retained/production/guard-configmap.yaml').read_text())['data']['guard.py'])
            try:
                result = subprocess.run([sys.executable, '-I', '-B', str(runtime), app, str(root)], capture_output=True, timeout=3, env={**os.environ, **({'DATABASE_PROVIDER': 'postgres', 'POSTGRES_HOST': 'postgres-postgresql.databases', 'POSTGRES_PORT': '5432', 'POSTGRES_USER': 'cleanuparr', 'POSTGRES_DB': 'cleanuparr', 'POSTGRES_PASS': 'isolated-fixture-password'} if app == 'cleanuparr' else {}), **(environment or {})})
            except subprocess.TimeoutExpired:
                self.fail('Retained guard hung on invalid native state')
            self.assertEqual(result.returncode == 0, accepted, result.stderr.decode())
            self.assertEqual(before, digest())

    def test_complete_native_layouts_are_accepted_read_only(self):
        for app in LAYOUTS:
            with self.subTest(app=app):
                self.check(app, accepted=True)

    def test_missing_wrong_and_oversized_markers_fail_closed(self):
        for app in LAYOUTS:
            self.check(app, lambda r, m: m.unlink())
            for value in ('', 'homelab/other/data/v1\n', 'x' * 129):
                self.check(app, lambda r, m: m.write_text(value))

    def test_cleanuparr_requires_backend_and_preserved_key_material(self):
        for values in ({'DATABASE_PROVIDER': 'sqlite'}, {'POSTGRES_PASS': ''}, {'POSTGRES_DB': 'other'}):
            self.check('cleanuparr', environment=values)
        self.check('cleanuparr', lambda r, m: (r / 'DataProtection-Keys/key-isolated.xml').unlink())
        self.check('cleanuparr', lambda r, m: (r / 'jwt-key.bin').write_bytes(b'short'))

    def test_cleanuparr_rejects_active_sqlite_fallback(self):
        for name in ('cleanuparr.db', 'users.db', 'events.db-wal', 'users.db-journal'):
            self.check('cleanuparr', lambda r, m: (r / name).write_bytes(b'SQLite format 3\0'))

    def test_each_required_path_must_survive(self):
        for app, names in LAYOUTS.items():
            for name in names:
                def remove(root, marker):
                    path = root / name
                    __import__('shutil').rmtree(path) if path.is_dir() else path.unlink()
                with self.subTest(app=app, path=name):
                    self.check(app, remove)

    def test_wrong_or_truncated_sqlite_header_is_refused(self):
        for app, names in LAYOUTS.items():
            for name in names:
                if Path(name).suffix not in ('.db', '.sqlite'):
                    continue
                for data in (b'', b'SQLite format 3', b'wrong database'):
                    self.check(app, lambda r, m: (r / name).write_bytes(data))

    def test_marker_symlink_and_nested_parent_symlink_are_refused(self):
        def link_marker(root, marker):
            other = root.parent / 'other'
            other.write_bytes(marker.read_bytes())
            marker.unlink()
            marker.symlink_to(other)
        self.check('sonarr', link_marker)
        def link_parent(root, marker):
            original = root / 'config'
            other = root.parent / 'config'
            original.rename(other)
            original.symlink_to(other, target_is_directory=True)
        self.check('audiobookshelf', link_parent)

    def test_fifo_marker_or_native_file_is_refused_without_hanging(self):
        def marker_fifo(root, marker):
            marker.unlink()
            os.mkfifo(marker)
        def data_fifo(root, marker):
            path = root / 'sonarr.db'
            path.unlink()
            os.mkfifo(path)
        self.check('sonarr', marker_fifo)
        self.check('sonarr', data_fifo)

    def test_deployed_payload_matches_the_reviewed_source(self):
        actual = yaml.safe_load((ROOT / 'scripts/media-retained/production/guard-configmap.yaml').read_text())['data']['guard.py']
        self.assertEqual(actual, GUARD.read_text())

    def test_linked_root_and_unknown_app_are_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            link = root / 'link'
            link.symlink_to(root, target_is_directory=True)
            for app, path in [('sonarr', link), ('unknown', root)]:
                result = subprocess.run([sys.executable, '-I', '-B', str(GUARD), app, str(path)], capture_output=True)
                self.assertNotEqual(result.returncode, 0)


@unittest.skipUnless(os.environ.get('MEDIA_RETAINED_RENDERS'), 'exact layered Helm renders required')
class RenderTests(unittest.TestCase):
    def test_distinct_claims_guard_users_and_private_mounts(self):
        root = Path(os.environ['MEDIA_RETAINED_RENDERS'])
        for app in LAYOUTS:
            docs = [d for d in yaml.safe_load_all((root / (app + '.yaml')).read_text()) if d]
            deployment = next(d for d in docs if d['kind'] == 'Deployment' and d['metadata']['name'] == app)
            self.assertEqual(deployment['spec']['replicas'], 1)
            self.assertEqual(deployment['spec']['strategy']['type'], 'Recreate')
            pod = deployment['spec']['template']['spec']
            self.assertFalse(pod['automountServiceAccountToken'])
            self.assertEqual(pod.get('nodeSelector'), {'node-role.kubernetes.io/worker': 'true'})
            guard = next(c for c in pod['initContainers'] if c['name'] == 'retained-state')
            self.assertEqual(guard['command'][-2:], [app, '/retained'])
            uid = 0 if app in ('navidrome', 'audiobookshelf', 'cineplete') else 1000
            self.assertEqual(guard['securityContext']['runAsUser'], uid)
            self.assertEqual(guard['securityContext']['runAsGroup'], uid)
            self.assertTrue(all(m.get('readOnly', False) for m in guard['volumeMounts']))
            claims = {v['name']: v['persistentVolumeClaim']['claimName'] for v in pod['volumes'] if 'persistentVolumeClaim' in v}
            guard_data = next(m for m in guard['volumeMounts'] if m['mountPath'] == '/retained')
            self.assertEqual(claims[guard_data['name']], app + '-config-block')
            main = next(c for c in pod['containers'] if c['name'] == 'main')
            config = next(m for m in main['volumeMounts'] if m['mountPath'] == '/config')
            self.assertEqual(config['name'], guard_data['name'])
            if app in ('audiobookshelf', 'cineplete'):
                path = '/metadata' if app == 'audiobookshelf' else '/data'
                second = next(m for m in main['volumeMounts'] if m['mountPath'] == path)
                self.assertEqual(second['name'], config['name'])
                self.assertEqual(config['subPath'], 'config')
                self.assertEqual(second['subPath'], path[1:])
            self.assertNotIn(app, claims.values())
            if app == 'cineplete':
                self.assertNotIn('cineplete-data', claims.values())
                self.assertNotIn('cineplete-config', claims.values())
            if app in ('sonarr', 'sonarr-ru', 'radarr', 'radarr-ru', 'lidarr', 'navidrome', 'audiobookshelf', 'shelfmark'):
                self.assertIn('media-library-pvc', claims.values())
            if app == 'shelfmark':
                self.assertIn('cwa-book-ingest', claims.values())

    def test_original_image_service_env_probes_and_shared_mounts_remain(self):
        root = Path(os.environ['MEDIA_RETAINED_RENDERS'])
        for app in LAYOUTS:
            def read(name):
                return [d for d in yaml.safe_load_all((root / name).read_text()) if d]
            before, after = read(app + '-before.yaml'), read(app + '.yaml')
            old = next(d for d in before if d['kind'] == 'Deployment')['spec']['template']['spec']
            new = next(d for d in after if d['kind'] == 'Deployment')['spec']['template']['spec']
            old_main = next(c for c in old['containers'] if c['name'] == 'main')
            new_main = next(c for c in new['containers'] if c['name'] == 'main')
            for key in ('image', 'command', 'args', 'env', 'envFrom', 'livenessProbe', 'readinessProbe', 'startupProbe', 'securityContext', 'ports'):
                if app == 'cleanuparr' and key == 'env':
                    before_env = {v['name']: v for v in old_main.get('env', []) if not v['name'].startswith('POSTGRES_') and v['name'] != 'DATABASE_PROVIDER'}
                    after_env = {v['name']: v for v in new_main.get('env', []) if not v['name'].startswith('POSTGRES_') and v['name'] != 'DATABASE_PROVIDER'}
                    self.assertEqual(before_env, after_env)
                    pg_env = {v['name']: v for v in new_main.get('env', []) if v['name'].startswith('POSTGRES_') or v['name'] == 'DATABASE_PROVIDER'}
                    expected_pg = {name: {'name': name, 'value': value} for name, value in {
                        'DATABASE_PROVIDER': 'postgres', 'POSTGRES_HOST': 'postgres-postgresql.databases',
                        'POSTGRES_PORT': '5432', 'POSTGRES_USER': 'cleanuparr', 'POSTGRES_DB': 'cleanuparr',
                    }.items()}
                    expected_pg['POSTGRES_PASS'] = {'name': 'POSTGRES_PASS', 'valueFrom': {'secretKeyRef': {'name': 'cleanuparr-postgres-secret', 'key': 'password'}}}
                    self.assertEqual(pg_env, expected_pg)
                else:
                    self.assertEqual(old_main.get(key), new_main.get(key), (app, key))
            for kind in ('Service', 'Ingress'):
                self.assertEqual([d for d in before if d['kind'] == kind], [d for d in after if d['kind'] == kind])


if __name__ == '__main__':
    unittest.main()
