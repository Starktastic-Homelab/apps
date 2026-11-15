"""Tests for scripts/check-retained-inventory.py and the retained-volumes renderer (the render tests need helm)."""
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('check_retained', ROOT / 'scripts/check-retained-inventory.py')
chk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(chk)

HELM = shutil.which('helm') or str(Path.home() / '.cache/claude-household-boundary/bin/helm')


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

    def test_regex_matches_ansible(self):
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
                ['python3', str(ROOT / 'scripts/check-retained-inventory.py'), '--base', 'HEAD',
                 '--override-label', 'ok'], cwd=d, env={**os.environ, 'PR_LABELS': labels}, capture_output=True).returncode
            self.assertEqual(run(''), 1)
            self.assertEqual(run('x,ok'), 0)
            self.assertNotEqual(subprocess.run(
                ['python3', str(ROOT / 'scripts/check-retained-inventory.py'), '--base', 'no-such-ref',
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


@unittest.skipUnless(shutil.which('helm') or os.path.exists(HELM), 'helm not available')
class RenderTests(unittest.TestCase):
    def render(self, entries, template):
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
        import yaml
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

    def test_empty_inventory_renders_nothing(self):
        self.assertEqual(self.render([], 'retained-volumes.yaml').strip(), '')


if __name__ == '__main__':
    unittest.main()
