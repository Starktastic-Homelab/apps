#!/usr/bin/env python3
"""Lossless state contracts; native engine capture is exercised separately."""
import copy
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent / 'redis-immich-retained'
sys.path.insert(0, str(ROOT))


class RedisState(unittest.TestCase):
    def setUp(self):
        self.assertTrue((ROOT / 'redis_checkpoint.py').exists(), 'Redis checkpoint implementation is missing')
        import redis_checkpoint
        self.state = redis_checkpoint
        self.before = {'version': 1, 'captured_at_ms': 1000, 'databases': {
            0: {b'\xff\x00job': {'type': 'string', 'value': b'\x00payload', 'expires_at_ms': 5000}},
            4: {b'queue': {'type': 'list', 'value': [b'a', b'a', b'\xff'], 'expires_at_ms': None}}}}

    def test_only_deadline_explains_absence(self):
        missing = copy.deepcopy(self.before)
        del missing['databases'][0][b'\xff\x00job']
        with self.assertRaises(ValueError):
            self.state.compare(self.before, missing, now_ms=4999)
        missing['captured_at_ms'] = 5001
        self.assertEqual(self.state.compare(self.before, missing, now_ms=5001), {'preserved': 1, 'expired': 1})

    def test_payload_type_order_expiry_and_unexpected_keys_are_preserved(self):
        for record in (
            {'type': 'string', 'value': b'changed', 'expires_at_ms': 5000},
            {'type': 'list', 'value': [b'\x00payload'], 'expires_at_ms': 5000},
            {'type': 'string', 'value': b'\x00payload', 'expires_at_ms': 5001},
        ):
            changed = copy.deepcopy(self.before)
            changed['databases'][0][b'\xff\x00job'] = record
            with self.assertRaises(ValueError):
                self.state.compare(self.before, changed, now_ms=2000)
        changed = copy.deepcopy(self.before)
        changed['databases'][4][b'queue']['value'].reverse()
        with self.assertRaises(ValueError):
            self.state.compare(self.before, changed, now_ms=2000)
        changed = copy.deepcopy(self.before)
        changed['databases'][0][b'new'] = changed['databases'][0][b'\xff\x00job']
        with self.assertRaises(ValueError):
            self.state.compare(self.before, changed, now_ms=2000)

    def test_private_serialization_roundtrips_bytes_integer_databases_and_order(self):
        self.assertEqual(self.state.loads(self.state.dumps(self.before)), self.before)
        with self.assertRaises(ValueError):
            self.state.loads('{"unknown":true}')

    def test_uncertain_clock_cannot_explain_loss(self):
        later = copy.deepcopy(self.before)
        later['captured_at_ms'] = 6000
        with self.assertRaises(ValueError):
            self.state.compare(self.before, later, now_ms=2000)

    def test_waiting_to_compare_cannot_reclassify_an_early_disappearance(self):
        missing = copy.deepcopy(self.before)
        missing['captured_at_ms'] = 4999
        del missing['databases'][0][b'\xff\x00job']
        with self.assertRaises(ValueError):
            self.state.compare(self.before, missing, now_ms=6000)

    def test_unknown_type_refuses_instead_of_silent_drop(self):
        changed = copy.deepcopy(self.before)
        changed['databases'][4][b'queue']['type'] = 'ReJSON-RL'
        with self.assertRaises(ValueError):
            self.state.compare(changed, changed, now_ms=2000)


if __name__ == '__main__':
    unittest.main()
