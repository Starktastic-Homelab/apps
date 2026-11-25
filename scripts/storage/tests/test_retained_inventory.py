"""Tests for scripts/check-retained-inventory.py and the retained-volumes renderer (the render tests need helm)."""
import contextlib
import importlib.util
import io
import ipaddress
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
MI, GI = 1024 ** 2, 1024 ** 3
VG_BYTES = {'retained': 10 * GI - 4 * MI, 'regen': 2 * GI - 4 * MI}  # retained usable 10236Mi
VG_ALIGNED = {'retained': 10232 * MI, 'regen': VG_BYTES['regen']}  # usable/2 on a 4Mi boundary, for the edge cases


# The shape of terraform storage/terraform.tfvars data_disks; check-retained-inventory.py reads it from terraform main.
TFVARS = '''data_disks = [
  {
    interface         = "virtio1"
    datastore_id      = "k3s-block"
    path_in_datastore = "9998/vm-9998-disk-0.raw"
    size              = 232
    serial            = "retained"
  },
  {
    interface         = "virtio2"
    datastore_id      = "k3s-block"
    path_in_datastore = "9998/vm-9998-disk-1.raw"
    size              = 56
    serial            = "regen"
  },
]
'''


def tfvars(d, text=TFVARS):
    path = Path(d, 'storage.tfvars')
    path.write_text(text)
    return str(path)


def entry(i='data', **kw):
    e = {'id': i, 'namespace': 'ns', 'claim': i + '-iscsi', 'size': '10Gi', 'class': 'retained', 'origin': 'new'}
    e.update(kw)
    return e


def errs(base, head, override=False):
    return chk.check(base, head, override)


class CheckTests(unittest.TestCase):
    def test_valid_change_passes(self):
        self.assertEqual(errs([entry()], [entry(size='20Gi'), entry('other')]), [])

    def test_claim_must_follow_id(self):
        # One rule: <id>-iscsi, or <id>-iscsi-<sts>-0 for a kube-prometheus-stack operator StatefulSet.
        self.assertEqual(errs([], [entry('data', claim='data-iscsi')]), [])
        for sts in chk.KPS_STS.values():
            self.assertEqual(errs([], [entry('prometheus', claim=f'prometheus-iscsi-{sts}-0')]), [], sts)
        for bad in ['data', 'data-claim', 'other-iscsi', 'data-iscsi-0', 'data-iscsi-foo-0', 'data-iscsi-x',
                    'xdata-iscsi', f'data-iscsi-{next(iter(chk.KPS_STS.values()))}-1', '', 7, ['data-iscsi'], {'a': 1}]:
            e = errs([], [entry('data', claim=bad)])
            self.assertTrue(any('claim must be data-iscsi' in x for x in e), (bad, e))

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
        self.assertTrue(any('duplicate id' in x for x in errs([], [entry(), entry()])))

    def test_id_pattern_tripwire(self):
        # Pins the literal so a change is deliberate; ansible roles/storage_vm/files/homelab_storage/inventory.py:7
        # must change with it.
        self.assertEqual(chk.ID_PATTERN, r'^(?!snapshot|pvmove)[a-z0-9][a-z0-9-]{0,62}$')

    def test_target_iqn_prefix_tripwire(self):
        # Pins the literal so a change is deliberate; ansible roles/storage_vm/files/homelab_storage/lio.py
        # TARGET_PREFIX must change with it (and a change renames every target and its wwn).
        network = yaml.safe_load((ROOT / 'templates/globals.yaml').read_text())['global']['network']
        self.assertEqual(network['storageTargetIqnPrefix'], 'iqn.2026-11.net.starktastic.storage:')

    def test_vg_for_tripwire(self):
        # Pins the class -> VG map; ansible roles/storage_vm/files/homelab_storage/inventory.py vg_for and
        # lvm.py VG_NAMES must change with it.
        self.assertEqual(chk.VG_FOR, {'retained': 'retained', 'regenerable': 'regen'})

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
                 '--override-label', 'ok', '--storage-tfvars', tfvars(d)], cwd=d, env={**os.environ, 'PR_LABELS': labels}, capture_output=True).returncode
            self.assertEqual(run(''), 1)
            self.assertEqual(run('x,ok'), 0)
            self.assertNotEqual(subprocess.run(
                [sys.executable, str(ROOT / 'scripts/check-retained-inventory.py'), '--base', 'no-such-ref',
                 '--override-label', 'ok', '--storage-tfvars', tfvars(d)], cwd=d, env={**os.environ, 'PR_LABELS': 'ok'}, capture_output=True).returncode, 0)
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

    def vg(self, head, base=(), vg_bytes=VG_BYTES):
        return chk.check(list(base), head, vg_bytes=vg_bytes)

    def test_sizes_over_vg_refused(self):
        e = self.vg([entry('a', size='5Gi'), entry('b', size='5Gi')])
        self.assertTrue(any('VG retained' in x and str(10 * GI) in x and str(VG_BYTES['retained']) in x for x in e), e)
        e = self.vg([entry('a', size='10236Mi')])  # fits, but leaves no reserve
        self.assertTrue(any('VG retained' in x and 'reserve' in x for x in e), e)
        e = self.vg([entry('a', size='2Gi'), entry('b', size='3Gi'), entry('c', size='3Gi', **{'class': 'regenerable'})])
        self.assertTrue(e and all('VG regen' in x for x in e), e)
        base = [entry('a', size='2Gi'), entry('b', size='3Gi')]
        self.assertEqual(self.vg([entry('a', size='2Gi'), entry('b', size='3584Mi')], base), [])  # free 4604Mi
        for grown in ('8Gi', '5Gi'):  # over the VG, then into the reserve
            e = self.vg([entry('a', size='2Gi'), entry('b', size=grown)], base)
            self.assertTrue(any('VG retained' in x for x in e), (grown, e))

    def test_inventory_refused_when_reserve_not_free(self):
        e = self.vg([entry('a', size='4Gi'), entry('b', size='3Gi')])  # free 3068Mi < largest 4Gi
        self.assertTrue(any('VG retained' in x and str(3068 * MI) in x and str(4 * GI) in x for x in e), e)
        e = self.vg([entry('a', size='5120Mi')], vg_bytes=VG_ALIGNED)  # free 5112Mi < its own 5120Mi
        self.assertTrue(any('VG retained' in x and str(5120 * MI) in x for x in e), e)
        e = self.vg([entry(f'v{n}', size='500Mi') for n in range(19)])  # free 736Mi < the 10% floor
        self.assertTrue(any('VG retained' in x and str(VG_BYTES['retained'] // 10) in x for x in e), e)

    def test_inventory_accepted_with_reserve_free(self):
        self.assertEqual(self.vg([entry('a', size='2Gi'), entry('b', size='3Gi')]), [])
        self.assertEqual(self.vg([entry('a', size='5116Mi')], vg_bytes=VG_ALIGNED), [])  # free equals the reserve
        self.assertEqual(self.vg([entry(f'v{n}', size='500Mi') for n in range(18)]), [])  # free 1236Mi
        self.assertEqual(self.vg([entry('a', size='2Gi'), entry('b', size='3Gi'),
                                  entry('c', size='512Mi', **{'class': 'regenerable'})]), [])

    def test_vg_sizes_from_terraform_tfvars(self):
        self.assertEqual(chk.vg_bytes_from_tfvars(TFVARS), {'retained': 232 * GI - 4 * MI, 'regen': 56 * GI - 4 * MI})
        self.assertTrue(chk.STORAGE_TFVARS.startswith('https://raw.githubusercontent.com/Starktastic-Homelab/terraform/main/'))
        self.assertTrue(chk.STORAGE_TFVARS.endswith('/storage/terraform.tfvars'))
        one = TFVARS[:TFVARS.index('  {', 20)] + ']\n'  # retained only
        with tempfile.TemporaryDirectory() as d:  # fail closed: a missing or malformed source is an error, never a skip
            changed = Path(d, 'inventory.json')  # differs from the base, so the sizes are read
            changed.write_text(json.dumps([entry('a', size='1Gi')]))
            args = ['--base', 'HEAD', '--override-label', 'x', '--inventory', str(changed), '--storage-tfvars']

            def main(path):
                with contextlib.redirect_stderr(io.StringIO()) as err:
                    rc = chk.main(args + [path])
                self.assertIn('VG sizes', err.getvalue())
                return rc
            self.assertEqual(main(str(Path(d, 'missing.tfvars'))), 1)
            for bad in ['', 'nope', one, TFVARS.replace('"regen"', '"other"'), TFVARS.replace('= 56', '= 0'),
                        TFVARS.replace('= 56', '= 5.6'), TFVARS.replace('"retained"', '"regen"'),
                        TFVARS + TFVARS.replace('virtio', 'scsi')]:
                self.assertEqual(main(tfvars(d, bad)), 1, bad)

    def test_tfvars_tolerates_ordinary_terraform_edits(self):
        want = chk.vg_bytes_from_tfvars(TFVARS)
        edits = [
            TFVARS.replace('= 232', '= 232 # GiB').replace('"regen"', '"regen" // VG name'),
            'tags = { env = "prod" }\nlabels = {}\n' + TFVARS + 'extra = { a = { b = 1 } }\n',
            TFVARS.replace('serial            = "retained"', 'serial = "retained"\n    opts = { ssd = true }'),
            'data_disks = [\n  { interface = "virtio1", size = 232, serial = "retained" },\n'
            '  { size = 56, serial = "regen", interface = "virtio2" },\n]\n',
            TFVARS.replace('\n', '\r\n'),
            '/* size = 1 */\n' + TFVARS,
            TFVARS.replace('size              = 232', '/*\n size = 999\n */\n size = 232'),  # commented out
        ]
        for text in edits:
            self.assertEqual(chk.vg_bytes_from_tfvars(text), want, text)

    def test_tfvars_fails_closed_on_ambiguity(self):
        for bad in [TFVARS.replace('size              = 232', 'size = 232\n    size = 999'),
                    TFVARS + TFVARS.replace('virtio', 'scsi'),
                    TFVARS.replace('data_disks', 'other_disks'),
                    TFVARS.replace('= 56', '= var.regen_size')]:
            with self.assertRaises(ValueError, msg=bad):
                chk.vg_bytes_from_tfvars(bad)

    def test_unchanged_inventory_skips_the_terraform_fetch(self):
        # Only an inventory change depends on terraform main; other PRs must not fail on a raw.githubusercontent outage.
        with tempfile.TemporaryDirectory() as d:
            def git(*a):
                subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@t', *a], cwd=d, check=True, capture_output=True)
            inv = Path(d, chk.PATH)
            inv.parent.mkdir(parents=True)
            inv.write_text(json.dumps([entry('a', size='1Gi')]))
            git('init', '-q')
            git('add', '.')
            git('commit', '-qm', 'base')
            run = lambda: subprocess.run(
                [sys.executable, str(ROOT / 'scripts/check-retained-inventory.py'), '--base', 'HEAD',
                 '--override-label', 'ok', '--storage-tfvars', str(Path(d, 'missing.tfvars'))], cwd=d,
                env={**os.environ, 'PR_LABELS': ''}, capture_output=True, text=True)
            r = run()
            self.assertEqual(r.returncode, 0, r.stderr)
            inv.write_text(json.dumps([entry('a', size='2Gi')]))
            r = run()
            self.assertEqual(r.returncode, 1, r.stderr)
            self.assertIn('VG sizes', r.stderr)

    def test_bad_types_reported_not_raised(self):
        for field in ('namespace', 'class', 'origin'):
            for bad in (['x'], {'a': 1}, 7):
                e = errs([], [entry(**{field: bad})])
                self.assertTrue(e and any(field in x for x in e), (field, bad, e))

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

    def kps(self, guard=True, part='prometheus', volume=True):
        """Switch one kube-prometheus-stack StatefulSet: template renamed to <part>-iscsi, volumeName <part>."""
        rel = 'services/operations/kube-prometheus-stack'
        values = real(f'{rel}/values.yaml')
        spec = values[part][f'{part}Spec']
        storage = spec['storageSpec' if part == 'prometheus' else 'storage']
        vct = storage['volumeClaimTemplate']
        old = vct['metadata']['name']
        vct['metadata']['name'] = f'{part}-iscsi'
        vct['spec'].update(volumeName=part, storageClassName='')
        if not volume:
            del vct['spec']['volumeName']
        if guard:
            named(named(spec['initContainers'], 'retained-state')['volumeMounts'], old)['name'] = f'{part}-iscsi'
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
        am = entry('alertmanager', namespace='monitoring', origin='migrated', copied='2026-12-01',
                   claim='alertmanager-iscsi-alertmanager-kube-prometheus-stack-alertmanager-0')
        for e, tree in [(tempo, self.tempo), (loki, self.loki), (prom, self.kps),
                        (am, lambda **kw: self.kps(part='alertmanager', **kw))]:
            with self.subTest(e['id']):
                self.assertEqual(self.bindings([e], tree()), [])
                errors = self.bindings([e], tree(guard=False))
                self.assertTrue(any('init container' in x for x in errors), errors)

    def test_claim_reuses_static_pvc_fails(self):
        e = self.bindings([entry('tempo', namespace='monitoring', claim='tempo-data-block')], {},
                          ['infrastructure/base-configs/templates/monitoring-block-storage/tempo-bindings.yaml'])
        self.assertTrue(any('tempo-data-block' in x and 'static' in x for x in e), e)
        with tempfile.TemporaryDirectory() as d:  # no metadata.namespace: matched on name alone
            dump(Path(d, 'services/x/y/manifests/pvc.yaml'), {'kind': 'PersistentVolumeClaim', 'metadata': {'name': 'c'}})
            e = chk.check_bindings([entry('c', namespace='anywhere', claim='c')], Path(d))
        self.assertTrue(any('static' in x for x in e), e)

    def test_kps_template_rename_without_volume_name_binds(self):
        # The STS adopts the PVC named <template>-<sts>-0 even without volumeName: the copied marker still applies.
        prom = entry('prometheus', namespace='monitoring', origin='migrated',
                     claim='prometheus-iscsi-prometheus-kube-prometheus-stack-prometheus-0')
        e = self.bindings([prom], self.kps(volume=False))
        self.assertTrue(any('prometheus' in x and 'copied' in x for x in e), e)
        self.assertEqual(self.bindings([dict(prom, copied='2026-12-01')], self.kps(volume=False)), [])
        e = self.bindings([dict(prom, copied='2026-12-01')], self.kps(volume=False, guard=False))
        self.assertTrue(any('init container' in x for x in e), e)

    def test_kps_sts_names_tripwire(self):
        # KPS_STS hardcodes chart-derived STS names: <kind>-<release>-<kind>, release = app name, no name overrides.
        rel = 'services/operations/kube-prometheus-stack'
        self.assertEqual(real(f'{rel}/app.yaml')['name'], 'kube-prometheus-stack')
        _, values = chk.effective_values(ROOT, ROOT / rel / 'app.yaml')
        # cleanPrometheusOperatorObjectNames would drop the -<kind> suffix from the STS names.
        self.assertFalse({'fullnameOverride', 'nameOverride', 'cleanPrometheusOperatorObjectNames'} & set(values),
                         values.keys())
        for path, sts in chk.KPS_STS.items():
            self.assertFalse({'fullnameOverride', 'nameOverride'} & set(values.get(path[0]) or {}), path)
            self.assertIsInstance(chk.dig(values, *path, 'volumeClaimTemplate', 'metadata', 'name'), str, path)
            self.assertEqual(sts, f'{path[0]}-kube-prometheus-stack-{path[0]}')

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

    def removed(self, entries, apps, files=None):
        with tempfile.TemporaryDirectory() as d:
            shutil.copytree(ROOT / 'templates', Path(d, 'templates'))
            for rel, (app, values) in apps.items():
                dump(Path(d, rel, 'app.yaml'), app)
                dump(Path(d, rel, 'values.yaml'), values)
            for rel, text in (files or {}).items():
                dump(Path(d, rel), text)
            return chk.check_removed(entries, Path(d))

    def test_removal_while_bound_refused(self):
        # Expiry deletes the LV of a removed entry; git still binding its claim makes the PR contradict itself.
        tempo = entry('tempo', namespace='monitoring', claim='tempo-iscsi', origin='migrated', copied='2026-12-01')
        e = self.removed([tempo], self.tempo())
        self.assertTrue(any('tempo' in x and 'tempo-iscsi' in x for x in e), e)
        self.assertEqual(self.removed([tempo], self.tempo(claim='tempo-data-block')), [])
        self.assertEqual(self.removed([dict(tempo, namespace='other')], self.tempo()), [])
        prom = entry('prometheus', namespace='monitoring', origin='migrated', copied='2026-12-01',
                     claim='prometheus-iscsi-prometheus-kube-prometheus-stack-prometheus-0')
        for volume in (True, False):  # the derived STS claim binds with or without volumeName
            e = self.removed([prom], self.kps(volume=volume))
            self.assertTrue(any('prometheus' in x and 'removed' in x for x in e), (volume, e))
        self.assertEqual(self.removed([prom], {}), [])

    def test_removal_while_manifest_names_claim_refused(self):
        e1 = entry('job', namespace='batch', claim='job-iscsi')
        pod = {'kind': 'CronJob', 'metadata': {'name': 'j'}, 'spec': {'jobTemplate': {'spec': {'template': {'spec': {
            'containers': [], 'volumes': [{'name': 'd', 'persistentVolumeClaim': {'claimName': 'job-iscsi'}}]}}}}}}
        for files in [{'services/x/job/manifests/cron.yaml': yaml.safe_dump(pod)},
                      {'services/x/job/manifests/cron.yaml': 'claimName: {{ "job-iscsi" }}\n'}]:
            e = self.removed([e1], {}, files)
            self.assertTrue(any('cron.yaml' in x and 'job-iscsi' in x for x in e), e)
        other = dict(pod, metadata={'name': 'j', 'namespace': 'elsewhere'})
        self.assertEqual(self.removed([e1], {}, {'services/x/job/manifests/cron.yaml': yaml.safe_dump(other)}), [])
        self.assertEqual(self.removed([e1], {}, {'services/x/job/manifests/cron.yaml': 'name: {{ "job-iscsi-old" }}\n'}), [])
        # A values.yaml no app layers (a Helm path source's) is read as a manifest.
        e = self.removed([e1], {}, {'infrastructure/x/job/manifests/values.yaml': yaml.safe_dump({'claim': 'job-iscsi'})})
        self.assertTrue(any('values.yaml' in x and 'job-iscsi' in x for x in e), e)

    def test_removal_while_bound_refused_on_repo(self):
        # The real tree parses, and today's monitoring block bindings would refuse their removal.
        e = chk.check_removed([entry('tempo', namespace='monitoring', claim='tempo-data-block')], ROOT)
        self.assertTrue(any('tempo still binds monitoring/tempo-data-block' in x for x in e), e)
        self.assertTrue(any('tempo-bindings.yaml' in x for x in e), e)
        self.assertEqual(chk.check_removed([entry('nobody', namespace='monitoring', claim='nobody-iscsi')], ROOT), [])

    def test_cli_refuses_removal_while_bound(self):
        with tempfile.TemporaryDirectory() as d:
            def git(*a):
                subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@t', *a], cwd=d, check=True, capture_output=True)
            for rel, (app, values) in self.tempo().items():
                dump(Path(d, rel, 'app.yaml'), app)
                dump(Path(d, rel, 'values.yaml'), values)
            shutil.copytree(ROOT / 'templates', Path(d, 'templates'))
            inv = Path(d, chk.PATH)
            inv.parent.mkdir(parents=True)
            inv.write_text(json.dumps([entry('tempo', namespace='monitoring', claim='tempo-iscsi', origin='migrated',
                                             copied='2026-12-01', size='4Gi', **{'class': 'regenerable'})]))
            git('init', '-q')
            git('add', '.')
            git('commit', '-qm', 'base')
            inv.write_text('[]')
            r = subprocess.run([sys.executable, str(ROOT / 'scripts/check-retained-inventory.py'), '--base', 'HEAD',
                                '--override-label', 'ok', '--storage-tfvars', tfvars(d)], cwd=d,
                               env={**os.environ, 'PR_LABELS': 'ok'}, capture_output=True, text=True)
            self.assertEqual(r.returncode, 1, r.stderr)
            self.assertIn('still binds monitoring/tempo-iscsi', r.stderr)

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
        self.assertEqual(pv['spec']['claimRef'], {'name': 'app-data-iscsi', 'namespace': 'ns'})
        self.assertEqual(pv['metadata']['annotations']['argocd.argoproj.io/sync-options'], 'Prune=false,Delete=false')
        csi = pv['spec']['csi']
        self.assertEqual((csi['driver'], csi['fsType'], csi['volumeHandle']), ('org.democratic-csi.node-manual', 'ext4', 'app-data'))
        network = yaml.safe_load((ROOT / 'templates/globals.yaml').read_text())['global']['network']
        portal = network['storagePortal']
        # The RFC 5737 placeholder made PVs fail closed until the storage VM address was decided (D1).
        self.assertNotIn(ipaddress.ip_address(portal.rsplit(':', 1)[0]), ipaddress.ip_network('192.0.2.0/24'))
        self.assertEqual(csi['volumeAttributes'], {
            'portal': portal, 'iqn': network['storageTargetIqnPrefix'] + 'app-data', 'lun': '0',
            'node_attach_driver': 'iscsi', 'provisioner_driver': 'node-manual'})
        self.assertEqual(pvc['spec']['volumeName'], 'app-data')
        self.assertEqual((pvc['metadata']['namespace'], pvc['metadata']['name']), ('ns', 'app-data-iscsi'))
        self.assertEqual(pvc['spec']['storageClassName'], '')
        # A pruned PVC leaves the Retain PV Released with a stale claimRef.uid, so reverting a removal would not rebind.
        self.assertEqual((pvc['metadata'].get('annotations') or {}).get('argocd.argoproj.io/sync-options'),
                         'Prune=false,Delete=false')
        self.assertEqual(pvc['spec']['accessModes'], ['ReadWriteOncePod'])

    def test_numeric_like_values_render_as_strings(self):
        e = entry('123', claim='true', namespace='1e3')
        pv, pvc = [d for d in yaml.safe_load_all(self.render([e], 'retained-volumes.yaml')) if d]
        self.assertEqual(pv['metadata']['name'], '123')
        self.assertEqual(pv['spec']['claimRef'], {'name': 'true', 'namespace': '1e3'})
        self.assertEqual(pv['spec']['csi']['volumeHandle'], '123')
        self.assertEqual((pvc['metadata']['name'], pvc['metadata']['namespace'], pvc['spec']['volumeName']),
                         ('true', '1e3', '123'))

    def test_growth_changes_pv_not_pvc(self):
        small, big = ([d for d in yaml.safe_load_all(self.render([entry('app-data', size=size)], 'retained-volumes.yaml'))
                       if d] for size in ('5Gi', '6Gi'))
        self.assertEqual((small[0]['spec']['capacity']['storage'], big[0]['spec']['capacity']['storage']), ('5Gi', '6Gi'))
        self.assertEqual(small[1], big[1])

    def test_pvc_request_immutable_across_size_change(self):
        for size in ('4Mi', '5Gi', '64Gi'):
            pv, pvc = [d for d in yaml.safe_load_all(self.render([entry('app-data', size=size)], 'retained-volumes.yaml'))
                       if d]
            # Pinned: raising it is refused by admission (class ""), lowering it below status.capacity by validation.
            self.assertEqual(pvc['spec']['resources']['requests']['storage'], '1Mi')
            self.assertGreaterEqual(chk.size_bytes(pv['spec']['capacity']['storage']), MI)

    def test_copied_does_not_change_render(self):
        self.assertEqual(self.render([entry('app-data', origin='migrated')], 'retained-volumes.yaml'),
                         self.render([entry('app-data', origin='migrated', copied='2026-12-01')], 'retained-volumes.yaml'))
        self.assertNotIn('copied', (ROOT / 'infrastructure/base-configs/templates/retained-volumes.yaml').read_text())

    def test_empty_inventory_renders_nothing(self):
        self.assertEqual(self.render([], 'retained-volumes.yaml').strip(), '')


if __name__ == '__main__':
    unittest.main()
