#!/usr/bin/env python3
"""Retained monitoring state must be checked read-only before native startup."""
import hashlib
import os
import yaml
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / 'scripts/monitoring-retained/guard.py'
GUARD_MAP = ROOT / 'scripts/monitoring-retained/production/guard-configmap.yaml'
FIXTURES = {
    'prometheus': (['prometheus-db', 'prometheus-db/wal'], []),
    'alertmanager': (['alertmanager-db'], ['alertmanager-db/silences', 'alertmanager-db/nflog']),
    'loki': (['wal', 'chunks', 'tsdb-shipper-active', 'compactor'], []),
    'tempo': (['wal', 'traces'], []),
}


class RetainedStateTests(unittest.TestCase):
    def check(self, app, alter=None, accepted=False):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'data'
            root.mkdir()
            marker = root / ('.homelab-' + app + '-data')
            marker.write_text('homelab/' + app + '/data/v1\n')
            for directory in FIXTURES[app][0]:
                (root / directory).mkdir(parents=True, exist_ok=True)
            for filename in FIXTURES[app][1]:
                (root / filename).write_bytes(b'isolated-policy-fixture')
            if alter:
                alter(root, marker)
            before = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in root.rglob('*') if p.is_file() and not p.is_symlink()}
            script = root.parent / 'runtime-guard.py'
            script.write_text(yaml.safe_load(GUARD_MAP.read_text())['data']['guard.py'])
            result = subprocess.run([sys.executable, '-I', '-B', str(script), app, str(root)], capture_output=True)
            self.assertEqual(result.returncode == 0, accepted, result.stderr.decode())
            after = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in root.rglob('*') if p.is_file() and not p.is_symlink()}
            self.assertEqual(before, after)

    def test_all_native_layouts_are_accepted_without_writes(self):
        for app in FIXTURES:
            with self.subTest(app=app): self.check(app, accepted=True)

    def test_valid_empty_alertmanager_snapshots_are_accepted(self):
        # The real retained source has an empty silences file. Empty snapshots
        # are valid native state; identity and required file paths must remain.
        def empty_snapshots(root, marker):
            for name in FIXTURES['alertmanager'][1]:
                (root / name).write_bytes(b'')
        self.check('alertmanager', empty_snapshots, accepted=True)

    def test_missing_wrong_and_oversized_identity_are_refused(self):
        for app in FIXTURES:
            for value in ['', 'homelab/another/data/v1\n', 'x' * 129]:
                with self.subTest(app=app, value=value):
                    self.check(app, lambda r, m: m.write_text(value))
            self.check(app, lambda r, m: m.unlink())

    def test_missing_native_paths_are_refused(self):
        for app, (directories, files) in FIXTURES.items():
            for name in [*reversed(directories), *files]:
                def alter(root, marker):
                    path = root / name
                    if path.is_file(): path.unlink()
                    else:
                        for p in sorted(path.rglob('*'), reverse=True):
                            p.rmdir() if p.is_dir() else p.unlink()
                        path.rmdir()
                with self.subTest(app=app, name=name): self.check(app, alter)

    def test_linked_marker_and_native_path_cannot_escape(self):
        for app in FIXTURES:
            def link_marker(root, marker):
                other = root.parent / 'outside'
                other.write_text(marker.read_text())
                marker.unlink()
                marker.symlink_to(other)
            self.check(app, link_marker)
            def link_directory(root, marker):
                directory = root / FIXTURES[app][0][-1]
                for p in sorted(directory.rglob('*'), reverse=True):
                    p.rmdir() if p.is_dir() else p.unlink()
                directory.rmdir()
                other = root.parent / 'outside-directory'
                other.mkdir()
                directory.symlink_to(other, target_is_directory=True)
            self.check(app, link_directory)

    def test_unknown_app_and_linked_data_root_are_refused(self):
        self.check('tempo', lambda r, m: m.write_bytes(b'\xff'))
        result = subprocess.run([sys.executable, '-I', '-B', str(GUARD), 'unknown', '/tmp'], capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        with tempfile.TemporaryDirectory() as temp:
            link = Path(temp) / 'link'
            link.symlink_to(temp, target_is_directory=True)
            result = subprocess.run([sys.executable, '-I', '-B', str(GUARD), 'tempo', str(link)], capture_output=True)
            self.assertNotEqual(result.returncode, 0)


@unittest.skipUnless(os.environ.get('MONITORING_RETAINED_RENDERS'), 'exact Helm renders supplied by CI or qualification')
class RenderedStateTests(unittest.TestCase):
    def test_guard_static_claim_and_original_process_are_rendered(self):
        root = Path(os.environ['MONITORING_RETAINED_RENDERS'])
        for app, owner in [('prometheus', 'Prometheus'), ('alertmanager', 'Alertmanager'), ('loki', 'StatefulSet'), ('tempo', 'StatefulSet')]:
            with self.subTest(app=app):
                objects = [o for o in yaml.safe_load_all((root / (app + '.yaml')).read_text()) if o]
                resource = next(o for o in objects if o['kind'] == owner)
                if owner != 'StatefulSet':
                    pod = resource['spec']
                    claim = pod['storage']['volumeClaimTemplate']
                    self.assertEqual(claim.get('metadata', {}).get('name'), app + '-data-block')
                    self.assertEqual(claim['spec']['volumeName'], app + '-data-block')
                    self.assertEqual(claim['spec']['accessModes'], ['ReadWriteOncePod'])
                    self.assertEqual(claim['spec']['storageClassName'], 'proxmox-retained')
                    self.assertEqual(pod['persistentVolumeClaimRetentionPolicy'], {'whenDeleted': 'Retain', 'whenScaled': 'Retain'})
                else:
                    pod = resource['spec']['template']['spec']
                    self.assertFalse(resource['spec'].get('volumeClaimTemplates'))
                    volumes = {v['name']: v for v in pod['volumes']}
                    self.assertIn(app + '-data-block', [v.get('persistentVolumeClaim', {}).get('claimName') for v in volumes.values()])
                self.assertIsNone((pod.get('securityContext') or {}).get('fsGroup'))
                self.assertEqual(pod['nodeSelector'], {'node-role.kubernetes.io/worker': 'true'})
                guard = next(i for i in pod.get('initContainers', []) if i['name'] == 'retained-state')
                self.assertEqual(guard['command'][-2:], [app, '/data'])
                mount = next(m for m in guard['volumeMounts'] if m['mountPath'] == '/data')
                self.assertTrue(mount['readOnly'])
                self.assertEqual(guard['securityContext']['allowPrivilegeEscalation'], False)
                self.assertEqual(guard['securityContext']['capabilities'], {'drop': ['ALL']})
                image = pod.get('image') or next(c for c in pod['containers'] if c['name'] == app)['image']
                self.assertIn('@sha256:', image)
                if app == 'tempo':
                    self.assertEqual([c['name'] for c in pod['containers']], ['tempo'])
                    self.assertEqual(resource['spec']['serviceName'], 'tempo-headless')
                    self.assertFalse(pod['containers'][0].get('env'))
                    self.assertFalse(pod['containers'][0].get('resources'))


if __name__ == '__main__': unittest.main()
