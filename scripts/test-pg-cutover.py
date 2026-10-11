#!/usr/bin/env python3
"""Check inactive cutover inputs and real charts, without touching a cluster."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
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
                self.assertEqual(released, before, name + ': release changed the original desired state')
                for key, obj in held.items():
                    self.assertEqual(obj['spec']['replicas'], 0, key + ': writer was not held')
                    obj['spec']['replicas'] = before[key]['spec'].get('replicas', 1)
                    self.assertEqual(obj, before[key], key + ': hold changed more than replicas')


if __name__ == '__main__':
    unittest.main(verbosity=2)
