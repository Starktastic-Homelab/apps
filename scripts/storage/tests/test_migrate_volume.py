"""Tests for scripts/storage/migrate_volume.py and copy_volume.sh (migration-only, deleted in Task 5.9).

Every collector is replaced by fixtures: no test reaches kubectl, gh, git or a lock root.
"""
import contextlib
import copy
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import migrate_volume as mv  # noqa: E402

SCRIPT = HERE / 'copy_volume.sh'
COPY_IMAGE = 'ghcr.io/democratic-csi/democratic-csi:v1.9.5@sha256:fc3b7d7ed3a616714139525075312758e23a5d425ffb539ad12c9bd20fb6001f'
PY_IMAGE = 'python@sha256:8c9a3bf2d6dea60d60a2ae2a07c2b2fb1e7d8daed64b146b6792c74ae0d62ac4'
OLD = 'homelab//k3s-block/9999/vm-9999-tempo.raw'
AFFINITY = {'required': {'nodeSelectorTerms': [{'matchExpressions': [
    {'key': 'topology.kubernetes.io/region', 'operator': 'In', 'values': ['homelab']},
    {'key': 'topology.kubernetes.io/zone', 'operator': 'In', 'values': ['pve']}]}]}}


def entry(i, **kw):
    e = {'id': i, 'namespace': 'monitoring', 'claim': f'{i}-iscsi', 'size': '5Gi', 'class': 'retained',
         'origin': 'new'}
    e.update(kw)
    return e


def binding_pv(handle=OLD, name='tempo-data-block', capacity='5Gi'):
    return {'apiVersion': 'v1', 'kind': 'PersistentVolume', 'metadata': {'name': name}, 'spec': {
        'capacity': {'storage': capacity}, 'accessModes': ['ReadWriteOncePod'], 'volumeMode': 'Filesystem',
        'persistentVolumeReclaimPolicy': 'Retain', 'storageClassName': 'proxmox-retained',
        'claimRef': {'name': name, 'namespace': 'monitoring'},
        'csi': {'driver': mv.PROXMOX, 'fsType': 'ext4', 'volumeHandle': handle,
                'volumeAttributes': {'storage': 'k3s-block', 'cache': 'none'}},
        'nodeAffinity': AFFINITY}}


def pv(name, handle, driver=mv.NODE_MANUAL, claim=None):
    return {'kind': 'PersistentVolume', 'metadata': {'name': name}, 'spec': {
        'capacity': {'storage': '5Gi'}, 'csi': {'driver': driver, 'volumeHandle': handle},
        **({'claimRef': {'namespace': 'monitoring', 'name': claim}} if claim else {})}}


def pvc(name, volume):
    return {'kind': 'PersistentVolumeClaim', 'metadata': {'name': name, 'namespace': 'monitoring'},
            'spec': {'volumeName': volume}}


def pod(claim, phase='Running', name='p'):
    return {'kind': 'Pod', 'metadata': {'name': name, 'namespace': 'monitoring'},
            'spec': {'volumes': [{'name': 'v', 'persistentVolumeClaim': {'claimName': claim}}]},
            'status': {'phase': phase}}


def va(pv_name, name='csi-0123abcd'):
    return {'kind': 'VolumeAttachment', 'metadata': {'name': name},
            'spec': {'source': {'persistentVolumeName': pv_name}}}


def guard_init(mounts=None):
    return {'name': 'retained-state', 'image': PY_IMAGE,
            'command': ['python3', '-I', '-B', '/retained-startup/guard.py', 'tempo', '/var/tempo'],
            'env': [{'name': 'GUARD_MODE', 'value': 'strict'}],
            'securityContext': {'runAsNonRoot': True, 'runAsUser': 10001, 'readOnlyRootFilesystem': True},
            'volumeMounts': mounts if mounts is not None else [
                {'name': 'retained-startup', 'mountPath': '/retained-startup', 'readOnly': True},
                {'name': 'data', 'mountPath': '/var/tempo', 'readOnly': True}]}


def sts(replicas=0, claim='tempo-iscsi', inits=None, vct=None, extra_volumes=()):
    spec = {'securityContext': {'fsGroup': 10001, 'runAsUser': 10001},
            'initContainers': inits if inits is not None else [guard_init()],
            'containers': [{'name': 'tempo', 'volumeMounts': [{'name': 'data', 'mountPath': '/var/tempo'}]}],
            'volumes': [{'name': 'retained-startup', 'configMap': {'name': 'retained-startup-guard'}},
                        *extra_volumes]}
    if claim:
        spec['volumes'].append({'name': 'data', 'persistentVolumeClaim': {'claimName': claim}})
    o = {'kind': 'StatefulSet', 'metadata': {'name': 'tempo', 'namespace': 'monitoring'},
         'spec': {'replicas': replicas, 'template': {'spec': spec}}}
    if vct:
        o['spec']['volumeClaimTemplates'] = [{'metadata': {'name': vct}}]
    return o


def base_live():
    """A clean world under the hold: both PVs and claims present, the app at 0 replicas, nothing attached."""
    return [binding_pv(), pvc('tempo-data-block', 'tempo-data-block'),
            pv('tempo', 'tempo', claim='tempo-iscsi'), pvc('tempo-iscsi', 'tempo'), sts()]


def base_ci():
    return {'runs': {r: [{'status': 'completed'}] for r in mv.REBUILDS}, 'prs': {r: [] for r in mv.REBUILDS}}


LOCK = {'operation': 'storage-cutover:tempo', 'owner': 'ben'}
CLONE = {'head': 'a' * 40, 'origin_main': 'a' * 40, 'dirty': False}


def codes(reasons):
    return {r.split(':')[0] for r in reasons}


class Base(unittest.TestCase):
    def tree(self, bindings=1, inventory=None):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        root = Path(d.name)
        inv = root / mv.INVENTORY
        inv.parent.mkdir(parents=True)
        inv.write_text(json.dumps(inventory if inventory is not None else [entry('tempo', origin='migrated')]))
        v = root / mv.CSI_VALUES
        v.parent.mkdir(parents=True)
        v.write_text(yaml.safe_dump({'node': {'driver': {'image': {
            'registry': COPY_IMAGE.split(':')[0], 'tag': COPY_IMAGE.split(':', 1)[1]}}}}))
        g = root / mv.GLOBALS
        g.parent.mkdir(parents=True)
        g.write_text(yaml.safe_dump({'global': {'network': {'storagePortal': '192.0.2.10:3260',
                                                                'storageTargetIqnPrefix': 'iqn.2000-01.test.example:'}}}))
        t = root / mv.BINDINGS
        for n in range(bindings):
            f = t / f'b{n}/tempo-bindings.yaml'
            f.parent.mkdir(parents=True)
            f.write_text(yaml.safe_dump_all([binding_pv(), pvc('tempo-data-block', 'tempo-data-block')]))
        templated = t / 'other/templated.yaml'
        templated.parent.mkdir(parents=True)
        templated.write_text(yaml.safe_dump(binding_pv()) + '# {{ .Values.x }}\n')  # skipped: contains {{
        return root

    def decide(self, direction='forward', entry_=None, bindings=None, live=None, ci=None, lock=LOCK, clone=CLONE):
        return mv.decide('tempo', entry_ if entry_ is not None else entry('tempo', origin='migrated'),
                         bindings if bindings is not None else [binding_pv()],
                         live if live is not None else base_live(), ci or base_ci(), lock, clone, direction)

    def outdir(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        return Path(d.name, 'evidence/4.T-tempo')

    def render(self, root, out, direction='forward', live=None, ci=None, lock=LOCK, clone=CLONE):
        got = {'live': live if live is not None else base_live(), 'ci': ci or base_ci(), 'lock': lock,
               'clone': clone}
        buf = io.StringIO()
        with mock.patch.object(mv, 'collect', return_value=got), contextlib.redirect_stdout(buf):
            rc = mv.main(['render', 'tempo', '--direction', direction, '--out', str(out), '--repo', str(root)])
        return rc, buf.getvalue()

    def docs(self, path):
        return {(d['kind'], d['metadata']['name']): d for d in yaml.safe_load_all(path.read_text())}

    def assertNothingWritten(self, out, keep=()):
        self.assertEqual(sorted(p.name for p in out.glob('*') if p.name not in keep) if out.exists() else [], [])


class Decide(Base):
    def test_clean_world_passes(self):
        self.assertEqual(self.decide(), [])
        self.assertEqual(self.decide('reverse'), [])

    def test_refuses_when_source_has_pod(self):
        for extra in (pod('tempo-data-block'), pod('tempo-data-block', 'Pending'), va('tempo-data-block'),
                      {'kind': 'CronJob', 'metadata': {'name': 'c', 'namespace': 'monitoring'}, 'spec': {
                          'jobTemplate': {'spec': {'template': {'spec': {'volumes': [
                              {'name': 'v', 'persistentVolumeClaim': {'claimName': 'tempo-data-block'}}]}}}}}},
                      sts(1, claim=None, vct='data', inits=[]) | {'metadata': {'name': 'old', 'namespace': 'monitoring'}}):
            live = base_live() + [extra]
            if extra['kind'] == 'StatefulSet':  # vct data derives data-old-0, bound to the old PV
                live.append(pvc('data-old-0', 'tempo-data-block'))
            with self.subTest(kind=extra['kind']):
                self.assertIn('writer', codes(self.decide(live=live)))
        for extra in (pod('tempo-data-block', 'Succeeded'),
                      {'kind': 'CronJob', 'metadata': {'name': 'c', 'namespace': 'monitoring'}, 'spec': {
                          'suspend': True, 'jobTemplate': {'spec': {'template': {'spec': {'volumes': [
                              {'name': 'v', 'persistentVolumeClaim': {'claimName': 'tempo-data-block'}}]}}}}}}):
            self.assertNotIn('writer', codes(self.decide(live=base_live() + [extra])))
        self.assertNotIn('writer', codes(self.decide()))  # the fixture app STS is at replicas 0
        self.assertIn('writer', codes(self.decide(live=base_live()[:-1] + [sts(1)])))  # the new claim counts too
        job = {'kind': 'Job', 'metadata': {'name': 'j', 'namespace': 'monitoring'},
               'spec': {'template': {'spec': {'volumes': [{'name': 'v', 'persistentVolumeClaim': {
                   'claimName': 'tempo-iscsi'}}]}}}}
        self.assertIn('writer', codes(self.decide(live=base_live() + [job])))
        job['status'] = {'conditions': [{'type': 'Complete', 'status': 'True'}]}
        self.assertNotIn('writer', codes(self.decide(live=base_live() + [job])))

    def test_refuses_va_on_shared_handle(self):
        # Two PVs on one handle on one node share one VA; only persistentVolumeName tells them apart.
        live = base_live() + [pv('migrate-src-tempo', OLD, mv.PROXMOX), va('tempo-data-block')]
        self.assertIn('writer', codes(self.decide(live=live)))
        live = base_live() + [pv('migrate-src-tempo', OLD, mv.PROXMOX), va('migrate-src-tempo')]
        self.assertIn('writer', codes(self.decide(live=live)))
        self.assertNotIn('writer', codes(self.decide(live=base_live() + [va('loki-data-block')])))

    def test_refuses_handle_not_in_inventory(self):
        bad_live = base_live()
        bad_live[0] = binding_pv(handle='homelab//k3s-block/9999/vm-9999-loki.raw')
        loki_rendered = base_live()
        loki_rendered[2] = pv('tempo', 'loki', claim='tempo-iscsi')
        for case in ({'bindings': []}, {'bindings': [binding_pv(), binding_pv()]}, {'live': bad_live},
                     {'live': loki_rendered}, {'live': base_live() + [pv('migrate-dst-tempo', 'loki')]},
                     {'live': base_live()[:2] + base_live()[3:]}):
            with self.subTest(case=case):
                self.assertIn('handle', codes(self.decide(**case)))
        self.assertEqual(self.decide(live=base_live() + [pv('migrate-dst-tempo', 'tempo')]), [])
        # a forward pair not yet torn down blocks a reverse render: a PV's csi spec is immutable
        self.assertIn('handle', codes(self.decide('reverse', live=base_live() + [pv('migrate-src-tempo', OLD, mv.PROXMOX)])))

    def test_refuses_handle_render_writes_nothing(self):
        bad_live = base_live()
        bad_live[0] = binding_pv(handle='homelab//k3s-block/9999/vm-9999-loki.raw')
        loki_rendered = base_live()
        loki_rendered[2] = pv('tempo', 'loki', claim='tempo-iscsi')
        for bindings, live in ((0, None), (2, None), (1, bad_live), (1, loki_rendered),
                               (1, base_live() + [pv('migrate-dst-tempo', 'loki')])):
            out = self.outdir()
            rc, text = self.render(self.tree(bindings), out, live=live)
            self.assertEqual(rc, 1)
            self.assertIn('refused: handle', text)
            self.assertNothingWritten(out)

    def test_precheck_refuses_active_build(self):
        for repo, status in (('packer', 'in_progress'), ('terraform', 'queued'), ('ansible', 'in_progress')):
            ci = base_ci()
            ci['runs'][repo].append({'status': status})
            self.assertIn('rebuild', codes(self.decide(ci=ci)), repo)
        ci = base_ci()
        ci['prs']['terraform'] = [{'number': 9, 'title': 'packer-build-1', 'autoMergeRequest': {'mergeMethod': 'SQUASH'}}]
        self.assertIn('rebuild', codes(self.decide(ci=ci)))
        for lock in (None, {'operation': 'ansible-deploy'}, {'operation': 'storage-cutover:loki'}):
            self.assertIn('lock', codes(self.decide(lock=lock)), lock)
        shared = {'operation': 'storage-cutover:karakeep-data:karakeep-meilisearch'}
        for i in ('karakeep-data', 'karakeep-meilisearch'):
            self.assertEqual(mv.lock_ids(shared) >= {i}, True)
            reasons = mv.decide(i, None, [], [], base_ci(), shared, CLONE, 'forward')
            self.assertNotIn('lock', codes(reasons))

    def test_drift_pr_alone_does_not_block(self):
        ci = base_ci()
        ci['prs']['terraform'] = [{'number': 7, 'title': 'drift: terraform plan', 'autoMergeRequest': None}]
        self.assertEqual(self.decide(ci=ci), [])

    def test_refuses_target_smaller(self):
        self.assertIn('size', codes(self.decide(entry_=entry('tempo', origin='migrated', size='4Gi'))))
        self.assertIn('size', codes(self.decide('reverse', entry_=entry('tempo', origin='migrated', size='6Gi'))))
        self.assertNotIn('size', codes(self.decide(entry_=entry('tempo', origin='migrated', size='6Gi'))))

    def test_refuses_unparseable_quantity(self):
        self.assertIn('size', codes(self.decide(entry_=entry('tempo', origin='migrated', size='lots'))))
        bad = binding_pv()
        bad['spec']['capacity']['storage'] = '5G'
        self.assertIn('size', codes(self.decide(bindings=[bad])))
        got = {'live': base_live(), 'ci': base_ci(), 'lock': LOCK, 'clone': CLONE}
        root = self.tree(inventory=[entry('tempo', origin='migrated', size='lots')])
        buf = io.StringIO()
        with mock.patch.object(mv, 'collect', return_value=got), contextlib.redirect_stdout(buf):
            self.assertEqual(mv.main(['precheck', 'tempo', '--repo', str(root)]), 1)
        self.assertRegex(buf.getvalue(), r'(?m)^refused: size: .*lots')

    def test_image_comes_from_csi_values(self):
        root = self.tree()
        self.assertEqual(mv.copy_image(root), COPY_IMAGE)
        real = mv.copy_image(mv.ROOT)  # the repo's own node plugin image, whatever Renovate set
        self.assertRegex(real, r'^ghcr\.io/democratic-csi/democratic-csi:v[\d.]+@sha256:[0-9a-f]{64}$')
        (root / mv.CSI_VALUES).write_text('node: {}\n')
        got = {'live': base_live(), 'ci': base_ci(), 'lock': LOCK, 'clone': CLONE}
        out = self.outdir()
        buf = io.StringIO()
        with mock.patch.object(mv, 'collect', return_value=got), contextlib.redirect_stdout(buf):
            rc = mv.main(['render', 'tempo', '--direction', 'forward', '--out', str(out), '--repo', str(root)])
        self.assertEqual(rc, 1)
        self.assertRegex(buf.getvalue(), r'(?m)^refused: image: ')
        self.assertNothingWritten(out)

    def test_refuses_copied_entry(self):
        copied = entry('tempo', origin='migrated', copied='2026-12-01')
        self.assertIn('no-entry', codes(self.decide(entry_=copied)))
        self.assertNotIn('no-entry', codes(self.decide('reverse', entry_=copied)))
        self.assertIn('no-entry', codes(mv.decide('tempo', None, [binding_pv()], base_live(), base_ci(), LOCK,
                                                  CLONE, 'forward')))
        self.assertIn('no-entry', codes(self.decide(entry_=entry('tempo'))))

    def test_precheck_reverse_requires_lock(self):
        for lock in (None, {'operation': 'ansible-deploy'}):
            self.assertIn('lock', codes(self.decide('reverse', lock=lock)))
        self.assertNotIn('lock', codes(self.decide('reverse')))

    def test_reasons_in_order(self):
        r = mv.decide('tempo', None, [], [va('x')], base_ci(), None, dict(CLONE, dirty=True), 'forward')
        self.assertEqual([x.split(':')[0] for x in r], ['stale-clone', 'no-entry', 'handle', 'handle', 'lock'])

    def test_precheck_cli(self):
        root = self.tree()
        for lock, want in ((LOCK, 0), (None, 1)):
            got = {'live': base_live(), 'ci': base_ci(), 'lock': lock, 'clone': CLONE}
            buf = io.StringIO()
            with mock.patch.object(mv, 'collect', return_value=got), contextlib.redirect_stdout(buf):
                self.assertEqual(mv.main(['precheck', 'tempo', '--repo', str(root)]), want)
            self.assertEqual(buf.getvalue().startswith('refused: lock'), bool(want))


class Render(Base):
    def test_refuses_stale_clone(self):
        for clone in (dict(CLONE, head='b' * 40), dict(CLONE, dirty=True)):
            self.assertIn('stale-clone', codes(self.decide(clone=clone)))
            out = self.outdir()
            rc, text = self.render(self.tree(), out, clone=clone)
            self.assertEqual(rc, 1)
            self.assertIn('refused: stale-clone', text)
            self.assertNothingWritten(out)
        out = self.outdir()
        self.assertEqual(self.render(self.tree(), out)[0], 0)
        self.assertEqual(json.loads((out / 'render.json').read_text())['apps_head'], CLONE['head'])

    def test_temp_pairs_not_owned(self):
        root, out = self.tree(), self.outdir()
        self.assertEqual(self.render(root, out)[0], 0)
        objs = list(yaml.safe_load_all((out / 'pairs.yaml').read_text())) + \
            list(yaml.safe_load_all((out / 'job.yaml').read_text()))
        reverse_out = self.outdir()
        self.assertEqual(self.render(root, reverse_out, 'reverse')[0], 0)
        objs += list(yaml.safe_load_all((reverse_out / 'gate.yaml').read_text()))
        vols = [o for o in objs if o['kind'] in ('PersistentVolume', 'PersistentVolumeClaim')]
        self.assertEqual(len(vols), 8)
        for o in objs:
            m = o['metadata']
            self.assertEqual(m['labels'][mv.LABEL], 'tempo')
            self.assertNotIn('argocd.argoproj.io/tracking-id', m.get('annotations', {}))
            self.assertNotIn('app.kubernetes.io/instance', m['labels'])
            if o in vols:
                self.assertEqual(m['annotations']['argocd.argoproj.io/sync-options'], 'Prune=false,Delete=false')
            if o['kind'] == 'PersistentVolume':
                self.assertEqual(o['spec']['persistentVolumeReclaimPolicy'], 'Retain')
                self.assertEqual(o['spec']['accessModes'], ['ReadWriteOncePod'])
            elif o['kind'] != 'PersistentVolumeClaim':
                self.assertEqual(m['namespace'], 'monitoring')
        for bad in (root / 'infrastructure/x', root):
            rc, text = self.render(root, bad)
            self.assertEqual(rc, 1)
            self.assertIn('refused: out', text)
            self.assertFalse(bad.joinpath('pairs.yaml').exists())

    def test_render_forward_shape(self):
        out = self.outdir()
        rc, text = self.render(self.tree(), out)
        self.assertEqual((rc, text), (0, ''))
        self.assertEqual(sorted(p.name for p in out.iterdir()), ['job.yaml', 'pairs.yaml', 'render.json'])
        d = self.docs(out / 'pairs.yaml')
        src, dst = d['PersistentVolume', 'migrate-src-tempo'], d['PersistentVolume', 'migrate-dst-tempo']
        self.assertEqual(src['spec']['csi'], {'driver': mv.PROXMOX, 'volumeHandle': OLD,
                                              'volumeAttributes': {'storage': 'k3s-block', 'cache': 'none'}})
        self.assertEqual(src['spec']['volumeMode'], 'Block')
        self.assertEqual(src['spec']['nodeAffinity'], AFFINITY)
        self.assertEqual(src['spec']['capacity'], {'storage': '5Gi'})
        self.assertEqual(src['spec']['claimRef'], {'namespace': 'monitoring', 'name': 'migrate-src-tempo'})
        self.assertEqual(dst['spec']['csi']['driver'], mv.NODE_MANUAL)
        self.assertEqual(dst['spec']['csi']['volumeHandle'], 'tempo')
        self.assertEqual(dst['spec']['csi']['volumeAttributes']['iqn'], 'iqn.2000-01.test.example:tempo')
        self.assertEqual(dst['spec']['csi']['volumeAttributes']['portal'], '192.0.2.10:3260')
        self.assertNotIn('fsType', dst['spec']['csi'])
        self.assertNotIn('nodeAffinity', dst['spec'])
        claim = d['PersistentVolumeClaim', 'migrate-dst-tempo']
        self.assertEqual((claim['metadata']['namespace'], claim['spec']['volumeName'], claim['spec']['volumeMode']),
                         ('monitoring', 'migrate-dst-tempo', 'Block'))
        j = self.docs(out / 'job.yaml')
        job = j['Job', 'migrate-tempo']['spec']
        self.assertEqual((job['backoffLimit'], job['activeDeadlineSeconds']), (0, 14400))
        self.assertNotIn('ttlSecondsAfterFinished', job)
        p = job['template']['spec']
        self.assertEqual(p['restartPolicy'], 'Never')
        self.assertEqual(p['nodeSelector'], {'node-role.kubernetes.io/worker': 'true'})
        c, = p['containers']
        self.assertEqual(c['image'], COPY_IMAGE)
        self.assertEqual(c['command'], ['sh', '/migrate/copy_volume.sh', 'forward', str(5 << 30)])
        self.assertEqual(c['volumeDevices'], [{'name': 'migrate-src', 'devicePath': '/dev/migrate-src'},
                                              {'name': 'migrate-dst', 'devicePath': '/dev/migrate-dst'}])
        self.assertEqual(c['securityContext'], {
            'allowPrivilegeEscalation': False, 'capabilities': {'drop': ['ALL']}, 'readOnlyRootFilesystem': True,
            'seccompProfile': {'type': 'RuntimeDefault'}, 'runAsUser': 0})
        self.assertEqual(j['ConfigMap', 'migrate-tempo']['data']['copy_volume.sh'], SCRIPT.read_text())
        rec = json.loads((out / 'render.json').read_text())
        self.assertEqual(rec['handles']['migrate-src-tempo'], OLD)
        self.assertEqual(rec['claims']['old'], {'name': 'tempo-data-block', 'namespace': 'monitoring'})

    def test_render_reverse_swaps(self):
        root, out = self.tree(), self.outdir()
        self.assertEqual(self.render(root, out, 'reverse')[0], 0)  # pass 1 leaves render.json
        (out / 'gate.log').write_text('noise\ngate-fsck-ok tempo\nmore\ngate-guard-ok tempo\n')
        rc, text = self.render(root, out, 'reverse')
        self.assertEqual((rc, text), (0, ''))
        d = self.docs(out / 'pairs.yaml')
        src, dst = d['PersistentVolume', 'migrate-src-tempo'], d['PersistentVolume', 'migrate-dst-tempo']
        self.assertEqual((src['spec']['csi']['driver'], src['spec']['csi']['volumeHandle']), (mv.NODE_MANUAL, 'tempo'))
        self.assertEqual((dst['spec']['csi']['driver'], dst['spec']['csi']['volumeHandle']), (mv.PROXMOX, OLD))
        self.assertEqual(dst['spec']['nodeAffinity'], AFFINITY)
        job = self.docs(out / 'job.yaml')['Job', 'migrate-tempo']
        self.assertEqual(job['spec']['template']['spec']['containers'][0]['command'][2], 'reverse')
        self.assertEqual(json.loads((out / 'render.json').read_text())['pass'], 'copy')

    def test_reverse_requires_clean_source(self):
        root, out = self.tree(), self.outdir()
        rc, text = self.render(root, out, 'reverse')
        self.assertEqual((rc, text), (0, 'gate-required\n'))
        self.assertEqual(sorted(p.name for p in out.iterdir()), ['gate.yaml', 'render.json'])
        g = self.docs(out / 'gate.yaml')
        gate, guard = g['PersistentVolume', 'migrate-gate-tempo'], g['PersistentVolume', 'migrate-guard-tempo']
        self.assertEqual((gate['spec']['volumeMode'], gate['spec']['csi']['volumeHandle']), ('Block', 'tempo'))
        self.assertEqual((guard['spec']['volumeMode'], guard['spec']['csi']['volumeHandle']), ('Filesystem', 'tempo'))
        self.assertEqual(guard['spec']['mountOptions'], ['ro', 'noload'])
        self.assertEqual(guard['spec']['csi']['fsType'], 'ext4')
        self.assertIn(('ConfigMap', 'migrate-tempo'), g)
        gj = g['Job', 'migrate-gate-tempo']['spec']['template']['spec']
        self.assertEqual(gj['containers'][0]['command'], ['sh', '/migrate/copy_volume.sh', 'gate', 'tempo'])
        self.assertEqual(gj['containers'][0]['image'], COPY_IMAGE)
        self.assertIn({'name': 'migrate-src', 'persistentVolumeClaim': {'claimName': 'migrate-gate-tempo'}},
                      gj['volumes'])
        steps = {k: o['metadata']['labels'][mv.STEP] for k, o in g.items()}
        self.assertEqual({k for k, s in steps.items() if s == 'guard'},
                         {('PersistentVolume', 'migrate-guard-tempo'), ('PersistentVolumeClaim', 'migrate-guard-tempo'),
                          ('Job', 'migrate-guard-tempo')})
        gp = g['Job', 'migrate-guard-tempo']['spec']['template']['spec']
        ro, guard_c = gp['initContainers']
        self.assertEqual(guard_c, guard_init())  # copied whole: image, command, env, securityContext, mounts
        self.assertEqual(ro['image'], PY_IMAGE)
        self.assertEqual(ro['command'][-1], '/var/tempo')
        self.assertEqual(ro['volumeMounts'], [{'name': 'data', 'mountPath': '/var/tempo', 'readOnly': True}])
        self.assertEqual(gp['securityContext'], {'fsGroup': 10001, 'runAsUser': 10001})
        self.assertEqual(gp['volumes'], [
            {'name': 'retained-startup', 'configMap': {'name': 'retained-startup-guard'}},
            {'name': 'data', 'persistentVolumeClaim': {'claimName': 'migrate-guard-tempo', 'readOnly': True}}])
        self.assertIn('gate-guard-ok', gp['containers'][0]['command'][3])
        self.assertEqual(gp['containers'][0]['command'][-1], 'tempo')
        self.assertEqual(json.loads((out / 'render.json').read_text())['pass'], 'gate')

        # pass 2 refuses gate and writes nothing on a gate.log that does not pass, or a live gate PV
        for log, live, why in (('gate-fsck-ok tempo\n', None, 'gate'), ('gate-guard-ok tempo\n', None, 'gate'),
                               ('gate-fsck-ok loki\ngate-guard-ok loki\n', None, 'gate'),
                               ('gate-guard-ok tempo\ngate-fsck-ok tempo\n', None, 'gate'),
                               ('gate-fsck-ok tempo\ngate-guard-ok tempo\n',
                                base_live() + [pv('migrate-gate-tempo', 'tempo')], 'handle')):
            (out / 'gate.log').write_text(log)
            rc, text = self.render(root, out, 'reverse', live=live)
            self.assertEqual(rc, 1, log)
            self.assertIn(f'refused: {why}', text)
            self.assertNothingWritten(out, keep=('gate.yaml', 'render.json', 'gate.log'))

        # pass 1 refuses gate on templates it cannot run the guard from
        other_pvc = {'name': 'cache', 'persistentVolumeClaim': {'claimName': 'tempo-cache'}}
        two_mounts = guard_init(guard_init()['volumeMounts'] + [{'name': 'cache', 'mountPath': '/c'}])
        two_sts = sts() | {'metadata': {'name': 'tempo-2', 'namespace': 'monitoring'}}
        for live in (base_live()[:-1] + [sts(inits=[])], base_live() + [two_sts],
                     base_live()[:-1] + [sts(inits=[two_mounts], extra_volumes=[other_pvc])],
                     base_live()[:-1] + [sts(inits=[guard_init(), guard_init()])],
                     base_live()[:-1]):
            o = self.outdir()
            rc, text = self.render(root, o, 'reverse', live=live)
            self.assertEqual(rc, 1)
            self.assertIn('refused: gate', text)
            self.assertNothingWritten(o)
        o = self.outdir()  # before the hold: writer and gate are both printed
        rc, text = self.render(root, o, 'reverse', live=base_live()[:-1] + [sts(1, inits=[])])
        self.assertEqual(rc, 1)
        self.assertIn('refused: writer', text)
        self.assertIn('refused: gate', text)
        self.assertNothingWritten(o)
        o = self.outdir()
        rc, text = self.render(root, o, 'reverse', lock=None)
        self.assertEqual(rc, 1)
        self.assertIn('refused: lock', text)
        self.assertNothingWritten(o)

    def test_gate_from_volume_claim_template(self):
        # a volumeClaimTemplates name that derives the new claim also finds the guard template
        entry_ = entry('tempo', origin='migrated', claim='data-tempo-0')
        live = [binding_pv(), pvc('tempo-data-block', 'tempo-data-block'), pv('tempo', 'tempo', claim='data-tempo-0'),
                pvc('data-tempo-0', 'tempo'), sts(claim=None, vct='data')]
        objs, why = mv.render_gate('tempo', entry_, ('192.0.2.10:3260', 'iqn.2000-01.test.example:'), live, COPY_IMAGE)
        self.assertIsNone(why)
        guard_job = [o for o in objs if o['kind'] == 'Job' and o['metadata']['name'] == 'migrate-guard-tempo'][0]
        self.assertIn({'name': 'data', 'persistentVolumeClaim': {'claimName': 'migrate-guard-tempo', 'readOnly': True}},
                      guard_job['spec']['template']['spec']['volumes'])


class Collectors(Base):
    """The real collectors and entry point, against fake kubectl and gh on PATH, a temp clone and lock root."""

    def test_cli_end_to_end(self):
        root = self.tree()
        git = lambda *a: subprocess.run(['git', '-C', str(root), '-c', 'user.name=t', '-c', 'user.email=t@t', *a],
                                        check=True, capture_output=True)
        git('init', '-q')
        git('add', '.')
        git('commit', '-qm', 'fixture')
        git('update-ref', 'refs/remotes/origin/main', 'HEAD')
        work = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, work)
        (work / 'live.json').write_text(json.dumps({'items': base_live()}))
        (work / 'bin').mkdir()
        for name, body in (('kubectl', 'echo "$*" >> "$W/calls"\ncase "$*" in *" -l "*) echo \'{"items": []}\' ;;'
                                        ' *) cat "$W/live.json" ;; esac'),
                           ('gh', 'echo "$*" >> "$W/calls"\ncase "$*" in "run list"*) echo \'[{"status": "completed"}]\' ;;'
                                  ' *) echo "[]" ;; esac')):
            f = work / 'bin' / name
            f.write_text('#!/bin/sh\n' + body + '\n')
            f.chmod(0o755)
        lock_root = work / 'lock'
        lock_root.mkdir()
        (lock_root / 'operation.json').write_text(json.dumps(
            {'operation': 'storage-cutover:tempo', 'owner': 'ben', 'nonce': 'SECRET-NONCE'}))
        env = {**os.environ, 'PATH': f"{work / 'bin'}:{os.environ['PATH']}", 'W': str(work)}
        cli = lambda *a: subprocess.run([sys.executable, str(HERE / 'migrate_volume.py'), *a, '--repo', str(root),
                                         '--lock-root', str(lock_root)], capture_output=True, text=True, env=env)
        r = cli('precheck', 'tempo')
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, '', ''))
        calls = (work / 'calls').read_text()
        self.assertIn('get pods,pv,pvc,volumeattachments,jobs,cronjobs,deployments,statefulsets -A -o json', calls)
        for repo, wf in mv.REBUILDS.items():
            self.assertIn(f'run list -R Starktastic-Homelab/{repo} --workflow {wf} --json status --limit 20', calls)
            self.assertIn(f'pr list -R Starktastic-Homelab/{repo} --state open --json number,title,autoMergeRequest',
                          calls)
        out = work / 'out'
        r = cli('render', 'tempo', '--direction', 'forward', '--out', str(out))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn('SECRET-NONCE', ''.join(p.read_text() for p in out.iterdir()) + r.stdout + r.stderr)
        (root / 'stray').write_text('x')  # a dirty clone is stale
        r = cli('precheck', 'tempo')
        self.assertEqual(r.returncode, 1)
        self.assertIn('refused: stale-clone', r.stdout)
        (lock_root / 'operation.json').unlink()
        self.assertIn('refused: lock', cli('precheck', 'tempo').stdout)
        r = cli('verify-teardown', 'tempo')
        self.assertEqual((r.returncode, r.stdout), (0, 'teardown-ok tempo\n'))
        self.assertIn(f'get pv,pvc,pods,jobs,configmaps -A -l {mv.LABEL}=tempo -o json', (work / 'calls').read_text())


class Teardown(Base):
    def run_teardown(self, live):
        buf = io.StringIO()
        with mock.patch.object(mv, 'collect_labelled', return_value=live), mock.patch.object(mv, 'TEARDOWN_TIMEOUT', 0), \
                contextlib.redirect_stdout(buf):
            return mv.main(['verify-teardown', 'tempo']), buf.getvalue()

    def test_verify_teardown_refuses_leftovers(self):
        left = {'kind': 'PersistentVolumeClaim', 'metadata': {'name': 'migrate-dst-tempo', 'namespace': 'monitoring',
                                                              'labels': {mv.LABEL: 'tempo'}}}
        self.assertEqual(self.run_teardown([left])[0], 1)
        self.assertEqual(self.run_teardown([va('migrate-src-tempo')])[0], 1)
        self.assertEqual(self.run_teardown([va('migrate-guard-tempo')])[0], 1)
        self.assertEqual(self.run_teardown([]), (0, 'teardown-ok tempo\n'))
        other = copy.deepcopy(left)
        other['metadata']['labels'][mv.LABEL] = 'loki'
        self.assertEqual(self.run_teardown([other, va('migrate-src-loki'), va('tempo-data-block')])[0], 0)


class CopyScript(unittest.TestCase):
    def test_copy_script_steps(self):
        text = SCRIPT.read_text()
        steps = ['iflag=direct oflag=direct conv=fsync', 'cmp -n', 'e2fsck -fp',
                 'tune2fs -O mmp -E mmp_update_interval=5 -e remount-ro', 'dumpe2fs -h', 'resize2fs']
        at = [text.find(s) for s in steps]
        self.assertNotIn(-1, at)
        self.assertEqual(at, sorted(at))
        self.assertNotIn('sparse', text)
        gate = text.index('  gate)')
        gate_end = text.index(';;', gate)
        self.assertTrue(all(gate < p < gate_end for p in self._all(text, 'e2fsck -fn')))
        self.assertIn('exit 0', text[gate:gate_end])
        self.assertLess(gate_end, text.index('blockdev --getsize64'))
        self.assertIn('"$T" -ne "$S"', text)
        self.assertIn('reverse needs T == S', text)

    def test_held_mode_refuses_when_run_directly(self):
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d)
        (d / 'src').write_bytes(b'x' * (4 << 20))
        (d / 'dst').write_bytes(b'')
        r = subprocess.run(['sh', str(SCRIPT), 'held', str(4 << 20)], capture_output=True, text=True,
                           env={**os.environ, 'MIGRATE_SRC': str(d / 'src'), 'MIGRATE_DST': str(d / 'dst')})
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('refused', r.stdout)
        self.assertEqual((d / 'dst').read_bytes(), b'')

    @staticmethod
    def _all(text, s):
        i, found = text.find(s), []
        while i != -1:
            found.append(i)
            i = text.find(s, i + 1)
        return found

    @unittest.skipUnless(hasattr(os, 'geteuid') and os.geteuid() == 0 and shutil.which('losetup'),
                         'needs root and losetup')
    def test_copy_script_on_loop_devices(self):
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d)

        def sh(*a, check=True):
            return subprocess.run([str(x) for x in a], capture_output=True, text=True, check=check)

        def loop(name, mib, fs=False):
            img = d / name
            sh('truncate', '-s', f'{mib}M', img)
            if fs:
                (d / 'content').mkdir()
                (d / 'content/marker').write_text('retained-marker\n')
                sh('mkfs.ext4', '-q', '-F', '-d', d / 'content', img)
            dev = sh('losetup', '--find', '--show', img).stdout.strip()
            self.addCleanup(sh, 'losetup', '-d', dev, check=False)
            return dev

        def copy(src, dst, *args):
            return subprocess.run(['sh', str(SCRIPT), *args], capture_output=True, text=True,
                                  env={**os.environ, 'MIGRATE_SRC': src, 'MIGRATE_DST': dst})

        src, dst = loop('src.img', 64, fs=True), loop('dst.img', 128)
        mnt = d / 'mnt'
        mnt.mkdir()

        # the O_EXCL hold refuses a source that is mounted on this node
        sh('mount', '-o', 'ro', src, mnt)
        r = copy(src, dst, 'forward', str(128 << 20))
        sh('umount', mnt)
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn('copy-ok', r.stdout)
        self.assertIn('Device or resource busy', r.stderr)

        r = copy(src, dst, 'forward', str(128 << 20))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(f'copy-ok forward {64 << 20} {128 << 20}', r.stdout)
        info = sh('dumpe2fs', '-h', dst).stdout
        self.assertRegex(info, r'(?m)^Filesystem features:.*\bmmp\b')
        count = int(next(x.split(':')[1] for x in info.splitlines() if x.startswith('Block count:')))
        size = int(next(x.split(':')[1] for x in info.splitlines() if x.startswith('Block size:')))
        self.assertEqual(count * size, 128 << 20)
        sh('mount', '-o', 'ro', dst, mnt)
        try:
            self.assertEqual((mnt / 'marker').read_text(), 'retained-marker\n')
        finally:
            sh('umount', mnt)

        r = copy(dst, '/nonexistent', 'gate', 'tempo')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('gate-fsck-ok tempo', r.stdout)
        shutil.copy(d / 'dst.img', d / 'scratch.img')
        scratch = sh('losetup', '--find', '--show', d / 'scratch.img').stdout.strip()
        self.addCleanup(sh, 'losetup', '-d', scratch, check=False)
        sh('debugfs', '-w', '-R', 'clri <2>', scratch)
        r = copy(scratch, '/nonexistent', 'gate', 'tempo')
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn('gate-fsck-ok', r.stdout)

        r = copy(dst, src, 'reverse', str(128 << 20))
        self.assertEqual(r.returncode, 1)
        self.assertIn('T < S', r.stdout)
        big = loop('big.img', 192)
        r = copy(dst, big, 'reverse', str(128 << 20))
        self.assertEqual(r.returncode, 1)
        self.assertIn('T == S', r.stdout)


if __name__ == '__main__':
    unittest.main()
