#!/usr/bin/env python3
"""Check inactive cutover inputs and real charts, without touching a cluster."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import hashlib
import re
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / 'scripts/postgres-retained-startup/production/cutover'


class CutoverTests(unittest.TestCase):
    def test_stages_keep_writers_held_until_restore_and_hook_acceptance(self):
        self.assertTrue((BUNDLE / 'states.yaml').exists(), 'Inactive cutover states are missing')
        states = yaml.safe_load((BUNDLE / 'states.yaml').read_text())
        self.assertEqual(set(states['consumers']), {'authentik', 'dispatcharr', 'lingarr', 'listmonk', 'mealie', 'paperless-ngx', 'vaultwarden', 'vikunja', 'postgres-enrollment-pilot'})
        self.assertEqual(states['stages']['nfs-held'], {'postgresStorage': 'source', 'postgresReplicas': 0, 'enrollmentHook': False, 'pilotReleased': False, 'consumersReleased': False, 'backupSuspended': True})
        for name in ('target-held', 'server-only'):
            self.assertFalse(states['stages'][name]['enrollmentHook'])
            self.assertFalse(states['stages'][name]['pilotReleased'])
            self.assertFalse(states['stages'][name]['consumersReleased'])
            self.assertTrue(states['stages'][name]['backupSuspended'])
        self.assertEqual(states['stages']['target-held']['postgresReplicas'], 0)
        self.assertEqual(states['stages']['server-only']['postgresReplicas'], 1)
        self.assertTrue(states['stages']['hook-pilot']['enrollmentHook'])
        self.assertTrue(states['stages']['hook-pilot']['pilotReleased'])
        self.assertFalse(states['stages']['hook-pilot']['consumersReleased'])
        self.assertTrue(states['stages']['released']['consumersReleased'])
        self.assertFalse(states['stages']['released']['backupSuspended'])
        self.assertEqual(yaml.safe_load((BUNDLE / 'postgres-held-values.yaml').read_text()), {'primary': {'replicaCount': 0}})
        policy, binding = list(yaml.safe_load_all((BUNDLE / 'source-hold.yaml').read_text()))
        self.assertEqual(policy['spec']['failurePolicy'], 'Fail')
        self.assertEqual(policy['spec']['validations'], [{'expression': 'false', 'message': 'The preserved PostgreSQL NFS claim is held. Restore acceptance is required before reopening any source writer.'}])
        self.assertEqual(policy['spec']['matchConstraints']['resourceRules'][0]['operations'], ['CREATE', 'UPDATE'])
        self.assertIn("object.metadata.namespace == 'databases'", policy['spec']['matchConditions'][0]['expression'])
        self.assertIn("v.persistentVolumeClaim.claimName == 'data-postgres-postgresql-0'", policy['spec']['matchConditions'][0]['expression'])
        self.assertEqual(binding['spec'], {'policyName': policy['metadata']['name'], 'validationActions': ['Deny']})
        for obj in (policy, binding):
            self.assertEqual(obj['metadata']['annotations']['argocd.argoproj.io/sync-options'], 'Prune=false,Delete=false')
        self.assertEqual(list(BUNDLE.rglob('app.yaml')), [])

    def test_reviewed_git_stages_apply_and_preserve_all_other_inputs(self):
        index_path = BUNDLE / 'patches/index.yaml'
        self.assertTrue(index_path.exists(), 'Concrete staged Git patches are missing')
        index = yaml.safe_load(index_path.read_text())
        self.assertTrue('bootstrap/appsets/config-apps.yaml' in index['baseline'], 'Config ApplicationSet discovery must be frozen')
        self.assertEqual([s['name'] for s in index['stages']], [
            'clients-held', 'nfs-held', 'target-held', 'server-only',
            'hook-only', 'hook-pilot', 'authentik-only', 'consumers-only', 'released'])
        source = 'infrastructure/controllers/databases/postgres'
        hook = source + '/manifests/enrollment-job.yaml'
        backup = 'infrastructure/base-configs/templates/pg-backup/cronjob.yaml'
        target = 'infrastructure/base-configs/templates/postgres-block-storage/'
        added = {source + '/manifests/source-hold.yaml', source + '/manifests/retained-startup-guard.yaml', target + 'pv.yaml', target + 'pvc.yaml'}
        states = yaml.safe_load((BUNDLE / 'states.yaml').read_text())
        consumer_files = {v['path'] + '/values.yaml' for v in states['consumers'].values()}
        allowed = consumer_files | added | {source + '/values.yaml', hook, backup}
        vectors = [index['baseline'].copy()]
        for stage in index['stages']:
            self.assertLessEqual(set(stage['updates']), allowed)
            vectors.append(vectors[-1] | stage['updates'])
        self.assertLessEqual(allowed, set(index['baseline']))
        def digest(path):
            return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
        current = {p: digest(ROOT / p) for p in index['baseline']}
        archived_hook = None
        # A completed cutover must not freeze future enrollment generations. Use
        # its exact archived hook only in this temporary patch-test workspace.
        if current[hook] != vectors[-1][hook] and all(current[p] == vectors[-1][p] for p in current if p != hook):
            patch = next(stage for stage in index['stages'] if stage['name'] == 'hook-only')
            archived_hook = ''.join(line[1:] + '\n' for line in (BUNDLE / 'patches' / patch['patch']).read_text().splitlines()
                                    if line.startswith('+') and not line.startswith('+++')).encode()
            self.assertEqual(hashlib.sha256(archived_hook).hexdigest(), index['baseline'][hook])
            expected = yaml.safe_load(archived_hook)
            actual = yaml.safe_load((ROOT / hook).read_text())
            data = yaml.safe_load((ROOT / source / 'manifests/enrollment-configmap.yaml').read_text())['data']
            import sys
            sys.path.insert(0, str(ROOT / 'scripts/postgres-enrollment'))
            import completion_gate
            self.assertEqual(data['acceptance-generation'], completion_gate.generation(data))
            expected['metadata']['name'] = completion_gate.hook_name(data['acceptance-generation'])
            self.assertEqual(actual, expected, 'Only a verified enrollment hook name may differ after release')
            current[hook] = index['baseline'][hook]
        matches = [i for i, v in enumerate(vectors) if v == current]
        self.assertEqual(len(matches), 1, 'Inputs drifted from all reviewed states; refresh/review rather than applying old patches')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for p in current:
                if (ROOT / p).exists():
                    (root / p).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(ROOT / p, root / p)
            if archived_hook is not None:
                (root / hook).write_bytes(archived_hook)
            def apply(stage, reverse=False):
                patch = BUNDLE / 'patches' / stage['patch']
                self.assertEqual(Path(stage['patch']).name, stage['patch'])
                self.assertEqual(digest(patch), stage['sha256'])
                headers = re.findall(r'^diff --git a/(\S+) b/(\S+)$', patch.read_text(), re.M)
                self.assertTrue(all(a == b for a, b in headers))
                self.assertEqual({a for a, _ in headers}, set(stage['updates']))
                cmd = ['git', 'apply', '--reverse'] if reverse else ['git', 'apply']
                check = subprocess.run(cmd + ['--check', str(patch)], cwd=root, capture_output=True, text=True)
                self.assertEqual(check.returncode, 0, check.stderr)
                subprocess.run(cmd + [str(patch)], cwd=root, check=True, capture_output=True)
            for stage in reversed(index['stages'][:matches[0]]):
                apply(stage, reverse=True)
            baseline = {p: (root / p).read_bytes() for p in allowed if (root / p).exists()}
            original_values = {p: yaml.safe_load(v) for p, v in baseline.items() if p.endswith('values.yaml')}
            final_overlay = yaml.safe_load((BUNDLE.parent / 'values.yaml').read_text())
            def merge(a, b):
                result = dict(a)
                for k, v in b.items():
                    result[k] = merge(result.get(k, {}), v) if isinstance(v, dict) else v
                return result
            rendered = {}
            pg_chart = os.environ.get('PG_CUTOVER_POSTGRES_CHART')
            def render_pg():
                key = (root / source / 'values.yaml').read_bytes()
                if key not in rendered:
                    helm = os.environ.get('PG_CUTOVER_HELM', shutil.which('helm'))
                    self.assertTrue(helm)
                    app = yaml.safe_load((root / source / 'app.yaml').read_text())
                    cmd = [str(helm), 'template', 'postgres', pg_chart, '--version', app['chart']['version'], '--namespace', 'databases', '-f', str(root / 'templates/globals.yaml'), '-f', str(root / source / 'values.yaml')]
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    rendered[key] = [d for d in yaml.safe_load_all(result.stdout) if d]
                return rendered[key]
            baseline_sts = next(d for d in render_pg() if d['kind'] == 'StatefulSet') if pg_chart else None
            for n, stage in enumerate(index['stages'], 1):
                apply(stage)
                self.assertEqual({p: digest(root / p) for p in current}, vectors[n])
                spec = states['stages'][stage['name']]
                for name, consumer in states['consumers'].items():
                    path = consumer['path'] + '/values.yaml'
                    released = spec['consumersReleased'] or (name == 'postgres-enrollment-pilot' and spec['pilotReleased']) or (name == 'authentik' and spec.get('authentikReleased', False))
                    # Release removes temporary keys as well as restoring explicit counts.
                    expected = original_values[path] if released else merge(original_values[path], consumer['hold'])
                    self.assertEqual(yaml.safe_load((root / path).read_text()), expected, stage['name'] + ': ' + name)
                pg = original_values[source + '/values.yaml']
                expected_pg = merge(pg, final_overlay) if spec['postgresStorage'] == 'target' else pg
                expected_pg = merge(expected_pg, {'primary': {'replicaCount': spec['postgresReplicas']}}) if stage['name'] != 'clients-held' else expected_pg
                self.assertEqual(yaml.safe_load((root / source / 'values.yaml').read_text()), expected_pg)
                self.assertEqual((root / hook).exists(), spec['enrollmentHook'])
                if spec['enrollmentHook']:
                    self.assertEqual((root / hook).read_bytes(), baseline[hook])
                cron = yaml.safe_load((root / backup).read_text())
                expected_cron = yaml.safe_load(baseline[backup])
                if spec['backupSuspended']:
                    expected_cron['spec']['suspend'] = True
                self.assertEqual(cron, expected_cron)
                held = stage['name'] != 'clients-held'
                self.assertEqual((root / source / 'manifests/source-hold.yaml').exists(), held)
                if held:
                    self.assertEqual((root / source / 'manifests/source-hold.yaml').read_bytes(), (BUNDLE / 'source-hold.yaml').read_bytes())
                if spec['postgresStorage'] == 'target':
                    for name, destination in [('pv.yaml', target + 'pv.yaml'), ('pvc.yaml', target + 'pvc.yaml'), ('guard-configmap.yaml', source + '/manifests/retained-startup-guard.yaml')]:
                        self.assertEqual(yaml.safe_load((root / destination).read_text()), yaml.safe_load((BUNDLE.parent / name).read_text()))
                else:
                    self.assertTrue(all(not (root / p).exists() for p in added - {source + '/manifests/source-hold.yaml'}))
                if pg_chart:
                    docs = render_pg()
                    self.assertFalse(any(d['kind'] == 'HorizontalPodAutoscaler' for d in docs))
                    controllers = [d for d in docs if d['kind'] in ('StatefulSet', 'Deployment')]
                    self.assertEqual(len(controllers), 1)
                    sts = controllers[0]
                    self.assertEqual(sts['spec']['replicas'], spec['postgresReplicas'])
                    pod = sts['spec']['template']['spec']
                    self.assertEqual(pod['containers'], baseline_sts['spec']['template']['spec']['containers'])
                    if spec['postgresStorage'] == 'target':
                        self.assertFalse(sts['spec'].get('volumeClaimTemplates'))
                        volumes = {v['name']: v for v in pod['volumes']}
                        self.assertEqual(volumes['data']['persistentVolumeClaim']['claimName'], 'postgres-data-block')
                        self.assertFalse(pod['securityContext'].get('fsGroup'))
                        self.assertEqual([c['name'] for c in pod['initContainers']], ['verify-retained-data'])
                        self.assertTrue(pod['initContainers'][0]['volumeMounts'][0]['readOnly'])
                        self.assertEqual(pod['initContainers'][0]['env'], [{'name': 'EXPECTED_SYSTEM_IDENTIFIER', 'value': '7584099661242523698'}])
                    else:
                        self.assertEqual(sts['spec']['volumeClaimTemplates'], baseline_sts['spec']['volumeClaimTemplates'])
                        self.assertEqual(pod, baseline_sts['spec']['template']['spec'])
            for p in consumer_files | {hook, backup}:
                self.assertEqual((root / p).read_bytes(), baseline[p], p + ': final release must restore exact bytes')

    @unittest.skipUnless(os.environ.get('PG_CUTOVER_CHARTS'), 'Set PG_CUTOVER_CHARTS to downloaded chart directories')
    def test_actual_consumer_charts_hold_and_restore_only_replica_counts(self):
        self.assertTrue((BUNDLE / 'states.yaml').exists(), 'Inactive cutover states are missing')
        states = yaml.safe_load((BUNDLE / 'states.yaml').read_text())
        charts = json.loads(os.environ['PG_CUTOVER_CHARTS'])
        helm = os.environ.get('PG_CUTOVER_HELM', shutil.which('helm'))
        self.assertTrue(helm)
        with tempfile.TemporaryDirectory() as tmp:
            for name, inputs in states['consumers'].items():
                app = yaml.safe_load((ROOT / inputs['path'] / 'app.yaml').read_text())
                chart = charts['authentik' if name == 'authentik' else 'app-template']
                layers = [ROOT / 'templates/globals.yaml']
                if inputs['path'].startswith('services/'):
                    layers.append(ROOT / 'templates/common.yaml')
                layers.extend(ROOT / p for p in app.get('commonValuesExtras', []))
                layers.append(ROOT / inputs['path'] / 'values.yaml')
                def render(extra=None):
                    cmd = [str(helm), 'template', name, chart, '--namespace', inputs['namespace']]
                    for p in layers:
                        cmd.extend(['-f', str(p)])
                    if extra is not None:
                        overlay = Path(tmp) / 'overlay.yaml'
                        overlay.write_text(yaml.safe_dump(extra))
                        cmd.extend(['-f', str(overlay)])
                    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                    self.assertEqual(r.returncode, 0, name + ': ' + r.stderr)
                    docs = [d for d in yaml.safe_load_all(r.stdout) if d]
                    self.assertFalse(any(d['kind'] == 'HorizontalPodAutoscaler' for d in docs), name + ': independently held autoscaler required')
                    return {d['metadata']['name']: d for d in docs if d['kind'] in ('Deployment', 'StatefulSet')}
                before, held, released = render(), render(inputs['hold']), render(inputs['release'])
                self.assertEqual(set(before), set(held), name + ': hold added or removed a controller')
                for key, obj in before.items():
                    expected_replicas = 2 if name == 'authentik' and key == 'authentik-server' else 1
                    self.assertEqual(released[key]['spec']['replicas'], expected_replicas)
                    obj['spec']['replicas'] = expected_replicas
                self.assertEqual(released, before, name + ': release changed more than replica counts')
                for key, obj in held.items():
                    self.assertEqual(obj['spec']['replicas'], 0, key + ': writer was not held')
                    obj['spec']['replicas'] = before[key]['spec'].get('replicas', 1)
                    self.assertEqual(obj, before[key], key + ': hold changed more than replicas')


if __name__ == '__main__':
    unittest.main(verbosity=2)
