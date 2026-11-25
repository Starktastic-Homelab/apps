"""The completion gate exists once in git: the base-configs source plus the hash-bound enrollment copy."""
import argparse
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts' / 'postgres-enrollment'))
import prepare  # noqa: E402
from completion_gate import generation, hook_name  # noqa: E402

GATE = prepare.GATE
TEMPLATE = ROOT / 'infrastructure/base-configs/templates/postgres-completion-gate.yaml'
ENROLLMENT = ROOT / 'infrastructure/controllers/databases/postgres/manifests'
NAME = prepare.GATE_CONFIGMAP


def template_namespaces():
    return set(re.search(r'range list((?: "[a-z0-9-]+")+)', TEMPLATE.read_text()).group(1).split('"')[1::2])


class CompletionGate(unittest.TestCase):
    def test_enrollment_copy_is_the_source_and_still_accepted(self):
        configmap = yaml.safe_load((ENROLLMENT / 'enrollment-configmap.yaml').read_text())
        data = configmap['data']
        self.assertEqual(data['completion_gate.py'], GATE.read_text())
        self.assertEqual(data['acceptance-generation'], generation(data))
        job = yaml.safe_load((ENROLLMENT / 'enrollment-job.yaml').read_text())
        self.assertEqual(job['metadata']['name'], hook_name(data['acceptance-generation']))

    def test_no_other_copy_in_git(self):
        marker = GATE.read_text().splitlines()[1]
        files = subprocess.run(['git', 'grep', '-l', '-F', marker, '--', ':!docs'], cwd=ROOT,
                               capture_output=True, text=True, check=True).stdout.split()
        self.assertEqual(sorted(files), sorted([str(GATE.relative_to(ROOT)),
                                                str((ENROLLMENT / 'enrollment-configmap.yaml').relative_to(ROOT))]))

    def test_every_consumer_namespace_has_the_configmap(self):
        consumers = set()
        for values in [*ROOT.glob('infrastructure/**/values.yaml'), *ROOT.glob('services/**/values.yaml')]:
            # Nearest app.yaml up: a kustomize helmCharts values file sits in manifests/ below its app.
            app = yaml.safe_load(next(d / 'app.yaml' for d in values.parents if (d / 'app.yaml').is_file()).read_text())
            if (re.search(r'^\s+name: ' + NAME + r'$', values.read_text(), re.M)
                    or 'templates/postgres-consumer.yaml' in (app.get('commonValuesExtras') or [])):
                consumers.add(app['namespace'])
        self.assertGreaterEqual(len(consumers), 5)
        self.assertEqual(consumers, template_namespaces())

    @unittest.skipUnless(shutil.which('helm'), 'helm not on PATH')
    def test_rendered_configmaps_hold_the_source(self):
        out = subprocess.run(['helm', 'template', 'base-configs', 'infrastructure/base-configs',
                              '-f', 'templates/globals.yaml'], cwd=ROOT, capture_output=True, text=True, check=True).stdout
        gates = [d for d in yaml.safe_load_all(out) if d and d['kind'] == 'ConfigMap' and d['metadata']['name'] == NAME]
        self.assertEqual({d['metadata']['namespace'] for d in gates}, template_namespaces())
        for d in gates:
            self.assertEqual(d['data'], {'completion_gate.py': GATE.read_text()})

    def test_generated_consumer_mounts_the_shared_configmap(self):
        options = argparse.Namespace(id='example', database='example', role='example', app_namespace='media',
                                     app_secret='example-db-secret', app_password_key='password')
        resources, fragment = prepare.consumer_sources(options)
        self.assertNotIn('ConfigMap', [r['kind'] for r in resources])
        self.assertEqual([c['name'] for c in fragment['initContainers']], ['postgres-enrollment-acceptance'])
        self.assertEqual([v['name'] for v in fragment['volumes']], ['pg-completion-script', 'pg-completion-api'])
        script = next(v for v in fragment['volumes'] if v['name'] == 'pg-completion-script')
        self.assertEqual(script['configMap']['name'], NAME)


if __name__ == '__main__':
    unittest.main()
