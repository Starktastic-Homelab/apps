#!/usr/bin/env python3
"""Reject unusable retained Paperless data before stock startup."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / 'scripts/paperless-retained/guard.py'


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(GUARD.is_file(), 'Retained Paperless guard must exist')
        spec = importlib.util.spec_from_file_location('paperless_guard', GUARD)
        self.guard = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.guard)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.root = self.base / 'data'
        self.root.mkdir()
        (self.root / '.homelab-paperless-data').write_text('homelab/paperless/data/v1\n')
        (self.root / '.index_version').write_text('9\n')
        (self.root / 'celerybeat-schedule.db').write_bytes(bytes.fromhex('cf9a5713') + bytes(4092))
        index = self.root / 'index'
        index.mkdir()
        (index / '.index_settings.json').write_text(json.dumps({'schema_version': 1, 'language': 'en'}))
        self.segment = '3c097b0c-62a4-49d0-8708-63cb18a7e552'
        self.meta = {'schema': [{'name': 'id', 'type': 'u64'}, {'name': 'content', 'type': 'text'}],
                     'segments': [{'segment_id': self.segment, 'max_doc': 1}], 'opstamp': 1}
        self.meta_path = index / 'meta.json'
        self.meta_path.write_text(json.dumps(self.meta))
        (index / (self.segment.replace('-', '') + '.store')).write_bytes(b'native-segment-fixture')

    def test_valid_preserved_layout_is_read_only(self):
        before = {str(p.relative_to(self.root)): (p.read_bytes(), p.stat().st_mtime_ns)
                  for p in self.root.rglob('*') if p.is_file()}
        self.guard.validate(self.root)
        after = {str(p.relative_to(self.root)): (p.read_bytes(), p.stat().st_mtime_ns)
                 for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(after, before)

    def test_empty_wrong_or_missing_identity_is_refused(self):
        marker = self.root / '.homelab-paperless-data'
        for value in ('', 'homelab/another/data/v1\n'):
            marker.write_text(value)
            with self.assertRaises((ValueError, OSError)): self.guard.validate(self.root)
        marker.unlink()
        with self.assertRaises((ValueError, OSError)): self.guard.validate(self.root)

    def test_missing_or_unparseable_native_state_is_refused(self):
        for path in (self.meta_path, self.root / 'index/.index_settings.json',
                     self.root / '.index_version', self.root / 'celerybeat-schedule.db'):
            data = path.read_bytes()
            path.write_bytes(b'')
            with self.subTest(path=path.name), self.assertRaises((ValueError, OSError)):
                self.guard.validate(self.root)
            path.write_bytes(data)
        self.meta_path.write_text('not JSON')
        with self.assertRaises(ValueError): self.guard.validate(self.root)

    def test_segments_require_native_files_and_valid_identifiers(self):
        path = self.root / 'index' / (self.segment.replace('-', '') + '.store')
        path.unlink()
        with self.assertRaises((ValueError, OSError)): self.guard.validate(self.root)
        for invalid in ('../outside', '', 'unqualified'):
            self.meta['segments'][0]['segment_id'] = invalid
            self.meta_path.write_text(json.dumps(self.meta))
            with self.assertRaises(ValueError): self.guard.validate(self.root)

    def test_redirected_roots_critical_files_and_fifos_are_refused(self):
        alias = self.base / 'alias'
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError): self.guard.validate(alias)
        self.meta_path.rename(self.base / 'outside-meta')
        self.meta_path.symlink_to(self.base / 'outside-meta')
        with self.assertRaises((ValueError, OSError)): self.guard.validate(self.root)
        self.meta_path.unlink()
        os.mkfifo(self.meta_path)
        with self.assertRaises((ValueError, OSError)): self.guard.validate(self.root)

    def test_invalid_native_shapes_and_schedule_header_are_refused(self):
        for value in ({}, {'schema': [], 'segments': [], 'opstamp': 0},
                      dict(self.meta, segments='invalid'), dict(self.meta, opstamp=-1)):
            self.meta_path.write_text(json.dumps(value))
            with self.assertRaises(ValueError): self.guard.validate(self.root)
        self.meta_path.write_text(json.dumps(self.meta))
        (self.root / 'celerybeat-schedule.db').write_bytes(b'not a native schedule')
        with self.assertRaises(ValueError): self.guard.validate(self.root)


class SourceTests(unittest.TestCase):
    def test_guard_and_bindings_have_one_canonical_source(self):
        cm=yaml.safe_load((ROOT/'services/operations/paperless-ngx/manifests/retained-startup-guard.yaml').read_text())
        self.assertEqual(cm['data']['guard.py'],GUARD.read_text())
        prepared=list(yaml.safe_load_all((ROOT/'scripts/paperless-retained/production/bindings.yaml').read_text()))
        for obj in prepared:
            name='pv.yaml' if obj['kind']=='PersistentVolume' else 'pvc.yaml'
            self.assertEqual(obj,yaml.safe_load((ROOT/'infrastructure/base-configs/templates/paperless-data-block-storage'/name).read_text()))
            self.assertEqual(obj['metadata']['annotations']['argocd.argoproj.io/sync-options'],'Prune=false,Delete=false')
            self.assertEqual(obj['spec']['accessModes'],['ReadWriteOncePod'])
        pv,pvc=prepared
        self.assertEqual(pv['spec']['persistentVolumeReclaimPolicy'],'Retain')
        self.assertEqual(pv['spec']['csi']['volumeHandle'],'homelab//k3s-block/9999/vm-9999-paperless-data.raw')
        self.assertEqual(pv['spec']['claimRef'],{'name':'paperless-data-block','namespace':'operations'})
        self.assertEqual(pvc['spec']['volumeName'],'paperless-data-block')
        self.assertEqual(pvc['spec']['resources']['requests']['storage'],'1Gi')

    def test_source_hold_and_active_storage_phase_agree(self):
        current=yaml.safe_load((ROOT/'services/operations/paperless-ngx/values.yaml').read_text())
        path=ROOT/'services/operations/paperless-ngx/manifests/source-hold.yaml'
        active=current['persistence']['data']['existingClaim']=='paperless-data-block'
        self.assertEqual(path.is_file(),active)
        if active:self.assertEqual(path.read_text(),(ROOT/'scripts/paperless-retained/production/source-hold.yaml').read_text())
        policy=next(yaml.safe_load_all((ROOT/'scripts/paperless-retained/production/source-hold.yaml').read_text()))
        rules=policy['spec']['matchConstraints']['resourceRules']
        self.assertTrue(any('UPDATE' in r['operations'] and 'pods/ephemeralcontainers' in r['resources'] for r in rules))
        source=yaml.safe_load((ROOT/'services/operations/paperless-ngx/manifests/pvc.yaml').read_text())
        self.assertEqual(source['metadata']['annotations']['argocd.argoproj.io/sync-options'],'Prune=false,Delete=false')


@unittest.skipUnless(os.environ.get('PAPERLESS_RETAINED_RENDER') and os.environ.get('PAPERLESS_BEFORE_RENDER'),'actual chart layers required')
class RenderTests(unittest.TestCase):
    def test_only_private_data_moves_and_every_native_setting_is_preserved(self):
        def deployment(flag):
            return next(v for v in yaml.safe_load_all(Path(os.environ[flag]).read_text())if v and v['kind']=='Deployment')
        old=deployment('PAPERLESS_BEFORE_RENDER');new=deployment('PAPERLESS_RETAINED_RENDER');pod=new['spec']['template']['spec']
        self.assertEqual(new['spec']['replicas'],1)
        self.assertEqual(new['spec']['strategy']['type'],'Recreate')
        self.assertEqual(pod['nodeSelector'],{'node-role.kubernetes.io/worker':'true'})
        self.assertFalse(pod['automountServiceAccountToken'])
        self.assertEqual(pod['tolerations'],[{'key':'node.kubernetes.io/not-ready','operator':'Exists','effect':'NoExecute'}, {'key':'node.kubernetes.io/unreachable','operator':'Exists','effect':'NoExecute'}])
        self.assertNotIn('fsGroup',pod.get('securityContext')or {})
        old_main=dict(old['spec']['template']['spec']['containers'][0]);main=dict(pod['containers'][0])
        old_main.pop('volumeMounts');mounts={m['mountPath']:m for m in main.pop('volumeMounts')}
        self.assertEqual(main,old_main)
        volumes={v['name']:v for v in pod['volumes']}
        self.assertEqual(volumes[mounts['/config']['name']]['persistentVolumeClaim']['claimName'],'paperless-ngx')
        self.assertEqual(volumes[mounts['/usr/src/paperless/data']['name']]['persistentVolumeClaim']['claimName'],'paperless-data-block')
        self.assertNotIn('subPath',mounts['/usr/src/paperless/data'])
        for name in ('media','consume'):
            m=mounts['/usr/src/paperless/'+name]
            self.assertEqual(m['subPath'],name)
            self.assertEqual(volumes[m['name']]['persistentVolumeClaim']['claimName'],'paperless-ngx-data')
        self.assertEqual(len(pod['initContainers']),1)
        guard=pod['initContainers'][0]
        self.assertEqual(guard['name'],'retained-data')
        self.assertEqual(guard['command'][-2:],['/retained-startup/guard.py','/retained'])
        self.assertFalse(guard.get('envFrom'))
        self.assertEqual(len(guard['volumeMounts']),2)
        self.assertTrue(all(m.get('readOnly')for m in guard['volumeMounts']))
        self.assertEqual(guard['securityContext']['capabilities']['drop'],['ALL'])


if __name__ == '__main__': unittest.main()
