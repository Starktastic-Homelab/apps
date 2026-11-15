import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / 'infrastructure/system/democratic-csi'
# Offline runs point this at an unpacked chart 0.15.1 directory.
CHART = os.environ.get('DEMOCRATIC_CSI_CHART')


def render():
    with tempfile.TemporaryDirectory() as tmp:
        shutil.copy(APP / 'values.yaml', tmp)
        if CHART:
            shutil.copytree(CHART, Path(tmp) / 'chart')
            src = ['chart']
        else:
            src = ['democratic-csi', '--repo', 'https://democratic-csi.github.io/charts/', '--version', '0.15.1']
        out = subprocess.run(['helm', 'template', 'dc', *src, '-n', 'democratic-csi', '-f', 'values.yaml'],
                             cwd=tmp, check=True, capture_output=True, text=True).stdout
    return [d for d in yaml.safe_load_all(out) if d]


DOCS = render()
FENCER = list(yaml.safe_load_all((APP / 'manifests/storage-fencer.yaml').read_text()))


def containers():
    for d in DOCS:
        if d['kind'] in ('Deployment', 'DaemonSet'):
            spec = d['spec']['template']['spec']
            yield d['kind'], spec.get('containers', []) + spec.get('initContainers', [])


class ValuesTests(unittest.TestCase):
    def test_images_pinned_by_digest(self):
        images = [c['image'] for _, cs in containers() for c in cs]
        self.assertTrue(images)
        for image in images:
            self.assertRegex(image, r'@sha256:[0-9a-f]{64}$', image)
        self.assertIn('ghcr.io/democratic-csi/democratic-csi:v1.9.5@sha256:'
                      'fc3b7d7ed3a616714139525075312758e23a5d425ffb539ad12c9bd20fb6001f', images)

    def test_blkid_strategy_on_node(self):
        node = next(cs for k, cs in containers() if k == 'DaemonSet')
        env = {e['name']: e.get('value') for c in node if c['name'] == 'csi-driver' for e in c['env']}
        self.assertEqual(env['FILESYSTEM_TYPE_DETECTION_STRATEGY'], 'blkid')

    def test_attacher_runs(self):
        dep = next(cs for k, cs in containers() if k == 'Deployment')
        self.assertTrue(any('csi-attacher' in c['image'] for c in dep))
        drv = next(d for d in DOCS if d['kind'] == 'CSIDriver')
        self.assertEqual(drv['metadata']['name'], 'org.democratic-csi.node-manual')
        self.assertTrue(drv['spec']['attachRequired'])

    def test_no_provisioner_resizer_snapshotter(self):
        dep = next(cs for k, cs in containers() if k == 'Deployment')
        for c in dep:
            for name in ('provisioner', 'resizer', 'snapshotter'):
                self.assertNotIn(name, c['image'])
        self.assertFalse([d for d in DOCS if d['kind'] in ('StorageClass', 'VolumeSnapshotClass')])

    def test_mkfs_options(self):
        secret = next(d for d in DOCS if d['kind'] == 'Secret')
        cfg = yaml.safe_load(secret['stringData']['driver-config-file.yaml'])
        self.assertEqual(cfg['driver'], 'node-manual')
        self.assertEqual(cfg['node']['format']['ext4']['customOptions'], ['-O', 'mmp', '-e', 'remount-ro'])

    def test_fencer_rbac(self):
        role = next(d for d in FENCER if d['kind'] == 'ClusterRole')
        rules = {(g, r): sorted(x['verbs']) for x in role['rules'] for g in x['apiGroups'] for r in x['resources']}
        self.assertEqual(rules, {('', 'nodes'): ['get', 'list', 'patch', 'watch'],
                                 ('storage.k8s.io', 'volumeattachments'): ['get', 'list']})
        by = {(d['kind'], d['metadata']['name']): d for d in FENCER}
        self.assertEqual(by['ClusterRoleBinding', 'storage-fencer']['subjects'],
                         [{'kind': 'ServiceAccount', 'name': 'storage-fencer', 'namespace': 'democratic-csi'}])
        tok = by['Secret', 'storage-fencer-token']
        self.assertEqual(tok['type'], 'kubernetes.io/service-account-token')
        self.assertEqual(tok['metadata']['annotations']['kubernetes.io/service-account.name'], 'storage-fencer')
        self.assertEqual(tok['metadata']['namespace'], 'democratic-csi')
        ns = yaml.safe_load((APP / 'manifests/namespace.yaml').read_text())
        self.assertEqual(ns['metadata']['labels']['pod-security.kubernetes.io/enforce'], 'privileged')


if __name__ == '__main__':
    unittest.main()
