import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / 'infrastructure/system/democratic-csi'
MANIFESTS = APP / 'manifests'
KUSTOMIZATION = yaml.safe_load((MANIFESTS / 'kustomization.yaml').read_text())
CHART_REF = KUSTOMIZATION['helmCharts'][0]
DRIVER = 'org.democratic-csi.node-manual'
# Offline runs point this at an unpacked chart directory of CHART_REF['version'].
CHART = os.environ.get('DEMOCRATIC_CSI_CHART')


def _kustomize(path):
    cmd = (['kubectl', 'kustomize', '--enable-helm', str(path)] if shutil.which('kubectl')
           else ['kustomize', 'build', '--enable-helm', str(path)])
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout


def render():
    """The manifests kustomize builds for Argo CD: the chart, the node shutdown patch and our resources."""
    with tempfile.TemporaryDirectory() as tmp:
        shutil.copytree(MANIFESTS, tmp, dirs_exist_ok=True)
        if CHART:
            home = Path(tmp) / 'charts'
            for name in (CHART_REF['name'], f"{CHART_REF['name']}-{CHART_REF['version']}/{CHART_REF['name']}"):
                shutil.copytree(CHART, home / name)
        out = _kustomize(tmp)
    return [d for d in yaml.safe_load_all(out) if d]


def render_chart_only():
    """The upstream chart with our values and no patch, as `helm template` renders it."""
    with tempfile.TemporaryDirectory() as tmp:
        shutil.copy(MANIFESTS / 'values.yaml', tmp)
        if CHART:
            shutil.copytree(CHART, Path(tmp) / 'chart')
            src = ['chart']
        else:
            src = [CHART_REF['name'], '--repo', CHART_REF['repo'], '--version', str(CHART_REF['version'])]
        out = subprocess.run(['helm', 'template', CHART_REF['releaseName'], *src, '-n', CHART_REF['namespace'],
                              '-f', 'values.yaml'], cwd=tmp, check=True, capture_output=True, text=True).stdout
    return [d for d in yaml.safe_load_all(out) if d]


DOCS = render()
FENCER = list(yaml.safe_load_all((MANIFESTS / 'storage-fencer.yaml').read_text()))


def node_ds(docs):
    return next(d for d in docs if d['kind'] == 'DaemonSet')['spec']['template']['spec']


def by_name(cs):
    return {c['name']: c for c in cs}


def prestop_script():
    cmd = by_name(node_ds(DOCS)['containers'])['csi-driver']['lifecycle']['preStop']['exec']['command']
    assert cmd[:2] == ['sh', '-c'], cmd
    return cmd[2]


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

    def test_no_values_for_patched_out_containers(self):
        # node-shutdown-patch.yaml removes cleanup, so values for it would be dead (and an unused pin for Renovate).
        values = yaml.safe_load((MANIFESTS / 'values.yaml').read_text())
        self.assertNotIn('cleanup', values.get('node', {}))
        self.assertNotIn('cleanup', by_name(node_ds(DOCS)['containers'] + node_ds(DOCS)['initContainers']))

    def test_blkid_strategy_on_node(self):
        node = next(cs for k, cs in containers() if k == 'DaemonSet')
        env = {e['name']: e.get('value') for c in node if c['name'] == 'csi-driver' for e in c['env']}
        self.assertEqual(env['FILESYSTEM_TYPE_DETECTION_STRATEGY'], 'blkid')

    def test_mount_timeout_outlasts_mmp_and_kubelet(self):
        # F6 (ADR 0017): the driver's mount timeout (ms) must outlast ext4's worst MMP wait (~720 s) and kubelet's
        # 2 min NodeStage deadline, so a long wait ends non-final (DeadlineExceeded/Aborted), never INTERNAL.
        node = next(cs for k, cs in containers() if k == 'DaemonSet')
        env = {e['name']: e.get('value') for c in node if c['name'] == 'csi-driver' for e in c['env']}
        self.assertEqual(env['MOUNT_DEFAULT_TIMEOUT'], '900000')
        self.assertGreater(int(env['MOUNT_DEFAULT_TIMEOUT']), 720000)
        self.assertGreater(int(env['MOUNT_DEFAULT_TIMEOUT']), 120000)
        for name in ('ISCSI_DEFAULT_TIMEOUT', 'FILESYSTEM_DEFAULT_TIMEOUT'):
            self.assertNotIn(name, env)
        others = [(k, c['name']) for k, cs in containers() for c in cs
                  if (k, c['name']) != ('DaemonSet', 'csi-driver')
                  and any(e['name'] == 'MOUNT_DEFAULT_TIMEOUT' for e in c.get('env', []))]
        self.assertEqual(others, [])

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
        ns = yaml.safe_load((MANIFESTS / 'namespace.yaml').read_text())
        self.assertEqual(ns['metadata']['labels']['pod-security.kubernetes.io/enforce'], 'privileged')


class ShutdownTests(unittest.TestCase):
    """F14: the node plugin must outlive the unstage on an undrained shutdown (ADR 0017)."""

    def test_chart_ref(self):
        # Exact pin, any version: Renovate gates bumps by hand (renovate.json democratic-csi rule).
        self.assertRegex(str(CHART_REF['version']), r'^\d+\.\d+\.\d+$')
        self.assertEqual({k: CHART_REF[k] for k in ('name', 'repo', 'releaseName', 'namespace', 'valuesFile')},
                         {'name': 'democratic-csi', 'repo': 'https://democratic-csi.github.io/charts/',
                          'releaseName': 'democratic-csi', 'namespace': 'democratic-csi', 'valuesFile': 'values.yaml'})
        self.assertNotIn('chart', yaml.safe_load((APP / 'app.yaml').read_text()))

    def test_sidecars(self):
        # cleanup is dropped: its shell ignores SIGTERM, so it held every pod stop to the full grace.
        spec, upstream = node_ds(DOCS), by_name(node_ds(render_chart_only())['containers'])
        self.assertEqual([c['name'] for c in spec['containers']], ['csi-driver'])
        self.assertEqual([c['name'] for c in spec['initContainers']], ['csi-proxy', 'driver-registrar'])
        for name, c in by_name(spec['initContainers']).items():
            self.assertEqual(c.get('restartPolicy'), 'Always', name)
            self.assertEqual(c['image'], upstream[name]['image'], name)

    def test_prestops(self):
        spec = node_ds(DOCS)
        script = prestop_script()
        for part in (DRIVER, 'globalmount', 'iscsi_session', '20', '12'):
            self.assertIn(part, script)
        # The preStop also runs on a liveness restart: deleting sockets there would orphan the
        # live sidecars. The registrar removes its own socket on SIGTERM.
        self.assertNotIn('rm ', script)
        self.assertEqual(spec['terminationGracePeriodSeconds'], 45)

    def test_prestop_iqn_matches_inventory(self):
        # retained-volumes.yaml builds each IQN from this one globals value.
        globals_yaml = (ROOT / 'templates/globals.yaml').read_text()
        prefix = re.search(r'storageTargetIqnPrefix: "(iqn\.[^:]+:)"', globals_yaml).group(1)
        self.assertIn(prefix.replace('.', r'\.'), prestop_script())

    def test_patch_targets_exist_upstream(self):
        # node-shutdown-patch.yaml edits containers by index: a chart bump that reorders them, or adds
        # initContainers the patch would overwrite, must fail here.
        upstream = node_ds(render_chart_only())
        self.assertEqual([c['name'] for c in upstream['containers']],
                         ['csi-driver', 'csi-proxy', 'driver-registrar', 'cleanup'])
        self.assertNotIn('initContainers', upstream)

    def _run_hook(self, globalmount=False, target=None, clear_after=None):
        # The hook holds while a democratic-csi globalmount dir or one of our iSCSI sessions exists.
        with tempfile.TemporaryDirectory() as tmp:
            k, s = Path(tmp) / 'k', Path(tmp) / 's'
            csi = k / 'plugins/kubernetes.io/csi'
            (csi / 'other.driver/ff/globalmount').mkdir(parents=True)
            (s / 'session1').mkdir(parents=True)
            (s / 'session1/targetname').write_text('iqn.2005-10.org.freenas.ctl:old\n')
            gm = csi / DRIVER / '0a1b/globalmount'
            if globalmount:
                gm.mkdir(parents=True)
            if target:
                (s / 'session2').mkdir()
                (s / 'session2/targetname').write_text(target + '\n')
            env = dict(os.environ, KUBELET_DIR=str(k), ISCSI_SESSIONS=str(s))
            start = time.monotonic()
            proc = subprocess.Popen(['sh', '-c', prestop_script()], env=env)
            if clear_after is not None:
                time.sleep(clear_after)
                if globalmount:
                    gm.rmdir()
                if target:
                    shutil.rmtree(s / 'session2')
            self.assertEqual(proc.wait(timeout=60), 0)
            return time.monotonic() - start

    OURS = 'iqn.2026-11.net.starktastic.storage:lab-sqlite'

    def test_prestop_idle_returns_at_once(self):
        # Foreign driver dirs and foreign iSCSI targets do not hold the stop.
        self.assertLess(self._run_hook(), 2)

    def test_prestop_holds_through_unstage(self):
        # F22: the globalmount entry leaves /proc/mounts at the unstage's first step (umount); the dir
        # lasts until the driver's last step (rmdir), after the logout.
        self.assertTrue(15 <= self._run_hook(globalmount=True, clear_after=3) <= 17.5)

    def test_prestop_holds_on_our_session(self):
        self.assertTrue(15 <= self._run_hook(target=self.OURS, clear_after=3) <= 17.5)

    def test_prestop_wait_is_bounded(self):
        # 20 s + 12 s stays inside the 40 s critical-pod tier and the 45 s grace.
        self.assertTrue(32 <= self._run_hook(globalmount=True, target=self.OURS) <= 34.5)


class MountPropagationTests(unittest.TestCase):
    """F21: a node-pod container with a private copy of the kubelet tree pins every volume staged
    before it started, so the driver's umount does not end the fs and the iSCSI logout lands under it."""

    def test_no_private_kubelet_mounts(self):
        spec = node_ds(DOCS)
        host = {v['name']: v['hostPath']['path'].rstrip('/') or '/' for v in spec['volumes'] if 'hostPath' in v}
        covered = ('/var/lib/kubelet/plugins/kubernetes.io/csi', '/var/lib/kubelet/pods')
        for c in spec['containers'] + spec['initContainers']:
            for m in c.get('volumeMounts', []):
                p = host.get(m['name'])
                if p and any(t == p or t.startswith(p.rstrip('/') + '/') for t in covered):
                    self.assertIn(m.get('mountPropagation'), ('HostToContainer', 'Bidirectional'),
                                  f"{c['name']}:{m['name']}")

    def test_registrar_mounts(self):
        # v2.9.0 never reads the kubelet dir: --mode=kubelet-registration-probe just exits 0.
        reg = by_name(node_ds(DOCS)['initContainers'])['driver-registrar']
        self.assertEqual([m['name'] for m in reg['volumeMounts']], ['socket-dir', 'registration-dir'])
        self.assertIn(':v2.9.0@', reg['image'])

if __name__ == '__main__':
    unittest.main()
