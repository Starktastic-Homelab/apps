"""Tests for scripts/check-retained-inventory.py and the retained-volumes renderer (the render tests need helm)."""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('check_retained', ROOT / 'scripts/check-retained-inventory.py')
chk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(chk)

HELM = shutil.which('helm')


def entry(i='data', **kw):
    e = {'id': i, 'namespace': 'ns', 'claim': i + '-claim', 'size': '10Gi', 'class': 'retained', 'origin': 'new'}
    e.update(kw)
    return e


def errs(base, head, override=False):
    return chk.check(base, head, override)


class CheckTests(unittest.TestCase):
    def test_valid_change_passes(self):
        self.assertEqual(errs([entry()], [entry(size='20Gi'), entry('other')]), [])

    def test_id_change_rejected(self):
        e = errs([entry('old')], [entry('new', claim='old-claim')])
        self.assertTrue(any('id changed' in x for x in e), e)

    def test_class_or_origin_change_rejected(self):
        self.assertTrue(errs([entry()], [entry(**{'class': 'regenerable'})]))
        self.assertTrue(errs([entry()], [entry(origin='migrated')]))

    def test_size_decrease_rejected(self):
        self.assertTrue(errs([entry(size='10Gi')], [entry(size='9Gi')]))
        self.assertTrue(errs([entry(size='1Gi')], [entry(size='1020Mi')]))

    def test_bad_id_rejected(self):
        for bad in ['Abc', '-a', 'snapshot1', 'pvmove0', 'a_b', '', 'a' * 64, 'abc\n']:
            self.assertTrue(errs([], [entry(bad)]), bad)
        self.assertEqual(errs([], [entry('a' * 63), entry('0-a')]), [])

    def test_bad_size_rejected(self):
        for bad in ['10Mi', '0Gi', '10G', '1.5Gi', 'Gi', '010Gi']:
            self.assertTrue(errs([], [entry(size=bad)]), bad)
        self.assertEqual(errs([], [entry(size='512Mi')]), [])

    def test_duplicate_id_rejected(self):
        self.assertTrue(errs([], [entry(), entry(claim='x')]))

    def test_id_pattern_tripwire(self):
        # Pins the literal so a change is deliberate; ansible roles/storage_vm/files/homelab_storage/inventory.py:7
        # must change with it.
        self.assertEqual(chk.ID_PATTERN, r'^(?!snapshot|pvmove)[a-z0-9][a-z0-9-]{0,62}$')

    def test_three_removals_need_label(self):
        base = [entry(c) for c in 'abc']
        self.assertTrue(errs(base, []))
        self.assertEqual(errs(base, [], override=True), [])
        self.assertEqual(errs(base, [entry('a')]), [])

    def test_readd_allowed(self):
        self.assertEqual(errs([], [entry()]), [])
        self.assertEqual(errs([entry()], []), [])

    def test_cli_label_and_missing_base(self):
        with tempfile.TemporaryDirectory() as d:
            def git(*a):
                subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@t', *a], cwd=d, check=True, capture_output=True)
            inv = Path(d, chk.PATH)
            inv.parent.mkdir(parents=True)
            inv.write_text(json.dumps([entry(c) for c in 'abc']))
            git('init', '-q')
            git('add', '.')
            git('commit', '-qm', 'base')
            inv.write_text('[]')
            run = lambda labels: subprocess.run(
                [sys.executable, str(ROOT / 'scripts/check-retained-inventory.py'), '--base', 'HEAD',
                 '--override-label', 'ok'], cwd=d, env={**os.environ, 'PR_LABELS': labels}, capture_output=True).returncode
            self.assertEqual(run(''), 1)
            self.assertEqual(run('x,ok'), 0)
            self.assertNotEqual(subprocess.run(
                [sys.executable, str(ROOT / 'scripts/check-retained-inventory.py'), '--base', 'no-such-ref',
                 '--override-label', 'ok'], cwd=d, env={**os.environ, 'PR_LABELS': 'ok'}, capture_output=True).returncode, 0)
            with self.assertRaises(SystemExit):
                chk.load_base('no-such-ref')
            # ref resolves but file absent: first inventory PR
            inv.unlink()
            git('rm', '-q', '--cached', chk.PATH)
            git('commit', '-qm', 'drop')
            self.addCleanup(os.chdir, os.getcwd())
            os.chdir(d)
            self.assertEqual(chk.load_base('HEAD'), [])
            os.chdir(ROOT)

    def test_copied_optional_iso_date(self):
        self.assertEqual(errs([], [entry(origin='migrated', copied='2026-12-01')]), [])
        for bad in ['2026-13-01', '01-12-2026', '', 20261201, '20261201']:
            e = errs([], [entry(origin='migrated', copied=bad)])
            self.assertTrue(any('bad copied' in x for x in e), (bad, e))

    def test_copied_forbidden_on_new(self):
        e = errs([], [entry(origin='new', copied='2026-12-01')])
        self.assertTrue(any('copied is only allowed on origin migrated' in x for x in e), e)

    def test_copied_may_be_removed(self):
        # A revert of a switch PR has to pass CI.
        self.assertEqual(errs([entry(origin='migrated', copied='2026-12-01')], [entry(origin='migrated')]), [])

    def test_unknown_field_still_rejected(self):
        self.assertTrue(errs([], [entry(foo='1')]))


def dump(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data) if not isinstance(data, str) else data)


def real(rel):
    return yaml.safe_load((ROOT / rel).read_text())


def named(items, name):
    return next(i for i in items if i['name'] == name)


class BindingTests(unittest.TestCase):
    """Fixtures start from the real tempo, loki and kube-prometheus-stack values, so the resolvers see real shapes."""

    def bindings(self, entries, apps, files=()):
        with tempfile.TemporaryDirectory() as d:
            shutil.copytree(ROOT / 'templates', Path(d, 'templates'))
            for rel, (app, values) in apps.items():
                dump(Path(d, rel, 'app.yaml'), app)
                if values is not None:
                    dump(Path(d, rel, 'values.yaml'), values)
            for rel in files:
                dump(Path(d, rel), (ROOT / rel).read_text())
            return chk.check_bindings(entries, Path(d))

    def tempo(self, claim='tempo-iscsi', guard=True):
        values = real('services/operations/tempo/values.yaml')
        values['persistence']['data']['existingClaim'] = claim
        if not guard:
            del values['persistence']['data']['advancedMounts']['main']['retained-state']
        return {'services/operations/tempo': (real('services/operations/tempo/app.yaml'), values)}

    def loki(self, guard=True):
        values = real('services/operations/loki/values.yaml')
        sb = values['singleBinary']
        named(sb['extraVolumes'], 'retained-data')['persistentVolumeClaim']['claimName'] = 'loki-iscsi'
        if not guard:
            named(named(sb['initContainers'], 'retained-state')['volumeMounts'], 'retained-data')['name'] = 'other'
        return {'services/operations/loki': (real('services/operations/loki/app.yaml'), values)}

    def kps(self, guard=True):
        rel = 'services/operations/kube-prometheus-stack'
        values = real(f'{rel}/values.yaml')
        spec = values['prometheus']['prometheusSpec']
        vct = spec['storageSpec']['volumeClaimTemplate']
        vct['metadata']['name'] = 'prometheus-iscsi'
        vct['spec'].update(volumeName='prometheus', storageClassName='')
        if guard:
            named(named(spec['initContainers'], 'retained-state')['volumeMounts'], 'prometheus-data-block')['name'] = \
                'prometheus-iscsi'
        return {rel: (real(f'{rel}/app.yaml'), values)}

    def test_flag_without_copied_marker_fails(self):
        e = self.bindings([entry('tempo', namespace='monitoring', claim='tempo-iscsi', origin='migrated')], self.tempo())
        self.assertTrue(any('tempo' in x and 'copied' in x for x in e), e)
        self.assertEqual(self.bindings([entry('tempo', namespace='monitoring', claim='tempo-iscsi', origin='migrated',
                                              copied='2026-12-01')], self.tempo()), [])

    def test_switch_requires_guard_mounted(self):
        tempo = entry('tempo', namespace='monitoring', claim='tempo-iscsi', origin='migrated', copied='2026-12-01')
        loki = entry('loki', namespace='monitoring', claim='loki-iscsi', origin='migrated', copied='2026-12-01')
        prom = entry('prometheus', namespace='monitoring', origin='migrated', copied='2026-12-01',
                     claim='prometheus-iscsi-prometheus-kube-prometheus-stack-prometheus-0')
        for e, tree in [(tempo, self.tempo), (loki, self.loki), (prom, self.kps)]:
            with self.subTest(e['id']):
                self.assertEqual(self.bindings([e], tree()), [])
                errors = self.bindings([e], tree(guard=False))
                self.assertTrue(any('init container' in x for x in errors), errors)

    def test_claim_reuses_static_pvc_fails(self):
        e = self.bindings([entry('tempo', namespace='monitoring', claim='tempo-data-block')], {},
                          ['infrastructure/base-configs/templates/monitoring-block-storage/tempo-bindings.yaml'])
        self.assertTrue(any('tempo-data-block' in x and 'static' in x for x in e), e)

    def test_sts_claim_must_match_template(self):
        e = self.bindings([entry('prometheus', namespace='monitoring', claim='prometheus-iscsi', origin='migrated',
                                 copied='2026-12-01')], self.kps())
        self.assertTrue(any('prometheus-iscsi-prometheus-kube-prometheus-stack-prometheus-0' in x for x in e), e)

    def test_variant_inherits_base_claim_fails(self):
        ok = entry('tempo', namespace='monitoring', claim='tempo-iscsi', origin='migrated', copied='2026-12-01')
        variant = {'name': 'tempo-ru', 'namespace': 'monitoring', 'baseApp': 'services/operations/tempo',
                   'valuesOverride': True}
        apps = {**self.tempo(), 'services/operations/tempo-ru': (variant, {'controllers': {}})}
        e = self.bindings([ok], apps)
        self.assertTrue(any('tempo-ru' in x and 'tempo-iscsi' in x for x in e), e)
        # Overriding the claim (as sonarr-ru, radarr-ru and qbittorrent-ru do) scopes the variant.
        own = {'persistence': {'data': {'existingClaim': 'tempo-ru-data'}}}
        self.assertEqual(self.bindings([ok], {**self.tempo(), 'services/operations/tempo-ru': (variant, own)}), [])

    def test_unknown_binding_style_fails(self):
        app = {'name': 'db', 'namespace': 'databases', 'chart': {'repo': 'x', 'name': 'y', 'version': '1'}}
        values = {'primary': {'persistence': {'existingClaim': 'db-iscsi'}}}
        e = self.bindings([entry('db', namespace='databases', claim='db-iscsi')], {'services/data/db': (app, values)})
        self.assertTrue(any('db-iscsi' in x and 'resolver' in x for x in e), e)

    def test_repo_bindings_pass(self):
        head = json.loads((ROOT / chk.PATH).read_text())
        self.assertEqual(chk.check_bindings(head, ROOT), [])


class RenderTests(unittest.TestCase):
    def render(self, entries, template):
        self.assertIsNotNone(HELM, 'helm not on PATH')
        with tempfile.TemporaryDirectory() as d:
            # Copy so the fixture replaces .Files content; helm runs with cwd=d (the helm wrapper mounts $PWD).
            shutil.copytree(ROOT / 'infrastructure/base-configs', Path(d, 'chart'))
            shutil.copy(ROOT / 'templates/globals.yaml', Path(d, 'globals.yaml'))
            Path(d, 'chart/files/retained-volumes.json').write_text(json.dumps(entries))
            out = subprocess.run([HELM, 'template', 'retained', 'chart', '-f', 'globals.yaml', '--show-only',
                                  f'templates/{template}'], cwd=d, capture_output=True, text=True)
        if out.returncode and 'could not find template' in out.stderr:
            return ''  # helm refuses --show-only for an empty render
        self.assertEqual(out.returncode, 0, out.stderr)
        return out.stdout

    def test_render_pv_shape(self):
        docs = [d for d in yaml.safe_load_all(self.render([entry('app-data', size='5Gi')], 'retained-volumes.yaml')) if d]
        pv, pvc = docs
        self.assertEqual(pv['metadata']['name'], 'app-data')
        self.assertEqual(pv['spec']['accessModes'], ['ReadWriteOncePod'])
        self.assertEqual(pv['spec']['persistentVolumeReclaimPolicy'], 'Retain')
        self.assertEqual(pv['spec']['claimRef'], {'name': 'app-data-claim', 'namespace': 'ns'})
        self.assertEqual(pv['metadata']['annotations']['argocd.argoproj.io/sync-options'], 'Prune=false,Delete=false')
        csi = pv['spec']['csi']
        self.assertEqual((csi['driver'], csi['fsType'], csi['volumeHandle']), ('org.democratic-csi.node-manual', 'ext4', 'app-data'))
        self.assertEqual(csi['volumeAttributes'], {
            'portal': '192.0.2.10:3260', 'iqn': 'iqn.2026-11.net.starktastic.storage:app-data', 'lun': '0',
            'node_attach_driver': 'iscsi', 'provisioner_driver': 'node-manual'})
        self.assertEqual(pvc['spec']['volumeName'], 'app-data')
        self.assertEqual((pvc['metadata']['namespace'], pvc['metadata']['name']), ('ns', 'app-data-claim'))
        self.assertEqual(pvc['spec']['storageClassName'], '')

    def test_guard_marker_only_for_new(self):
        out = self.render([entry('fresh'), entry('moved', origin='migrated')], 'retained-volumes-guard.yaml')
        self.assertIn('fresh-retained-guard', out)
        self.assertNotIn('moved', out)
        self.assertIn(".homelab-' + ID + '-data", out)

    def test_numeric_like_values_render_as_strings(self):
        e = entry('123', claim='true', namespace='1e3')
        pv, pvc = [d for d in yaml.safe_load_all(self.render([e], 'retained-volumes.yaml')) if d]
        self.assertEqual(pv['metadata']['name'], '123')
        self.assertEqual(pv['spec']['claimRef'], {'name': 'true', 'namespace': '1e3'})
        self.assertEqual(pv['spec']['csi']['volumeHandle'], '123')
        self.assertEqual((pvc['metadata']['name'], pvc['metadata']['namespace'], pvc['spec']['volumeName']),
                         ('true', '1e3', '123'))
        guard = yaml.safe_load(self.render([e], 'retained-volumes-guard.yaml'))
        self.assertEqual((guard['metadata']['name'], guard['metadata']['namespace']), ('123-retained-guard', '1e3'))

    def test_copied_does_not_change_render(self):
        for template in ('retained-volumes.yaml', 'retained-volumes-guard.yaml'):
            self.assertEqual(self.render([entry('app-data', origin='migrated')], template),
                             self.render([entry('app-data', origin='migrated', copied='2026-12-01')], template))
        self.assertNotIn('copied', (ROOT / 'infrastructure/base-configs/templates/retained-volumes.yaml').read_text())

    def test_empty_inventory_renders_nothing(self):
        self.assertEqual(self.render([], 'retained-volumes.yaml').strip(), '')


if __name__ == '__main__':
    unittest.main()
