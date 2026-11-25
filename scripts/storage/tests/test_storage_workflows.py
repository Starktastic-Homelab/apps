"""Offline checks for the apps side of the storage workflows: an inventory push dispatches storage-changed (ADR 0017)."""
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
DISPATCH = ROOT / '.github/workflows/storage-dispatch.yaml'


class DispatchTests(unittest.TestCase):
    def test_dispatch_on_inventory_push_only(self):
        doc = yaml.safe_load(DISPATCH.read_text())
        # PyYAML (YAML 1.1) loads a bare on: key as True.
        self.assertEqual(doc.get('on', doc.get(True)), {'push': {
            'branches': ['main'], 'paths': ['infrastructure/base-configs/files/retained-volumes.json']}})
        (job,) = doc['jobs'].values()
        (step,) = job['steps']
        self.assertEqual(step['uses'], 'peter-evans/repository-dispatch@v4')
        self.assertEqual(step['with']['event-type'], 'storage-changed')
        self.assertEqual(step['with']['repository'], 'Starktastic-Homelab/ansible')
        self.assertEqual(step['with']['token'], '${{ secrets.ORG_DISPATCH_TOKEN }}')

    def test_dispatch_sends_no_sha(self):
        # The ansible storage.yml re-resolves main itself.
        step, = yaml.safe_load(DISPATCH.read_text())['jobs']['dispatch']['steps']
        self.assertNotIn('client-payload', step['with'])
        self.assertNotIn('github.sha', DISPATCH.read_text())


if __name__ == '__main__':
    unittest.main()
