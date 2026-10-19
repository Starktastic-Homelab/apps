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


class RedisStreamState(unittest.TestCase):
    def setUp(self):
        import redis_checkpoint
        self.state = redis_checkpoint
        self.before = {'version': 1, 'captured_at_ms': 1000, 'databases': {0: {
            b'jobs': {'type': 'stream', 'expires_at_ms': 5000, 'value': [
                b'length', 1, b'radix-tree-keys', 1, b'radix-tree-nodes', 2,
                b'last-generated-id', b'1-0', b'entries-added', 1,
                b'entries', [[b'1-0', [b'payload', b'\xff\x00']]],
                b'groups', [[b'name', b'workers', b'last-delivered-id', b'1-0',
                             b'pending', [[b'1-0', b'consumer', 1000, 1]],
                             b'consumers', [[b'name', b'consumer', b'seen-time', 1000]]]]
            ]}}}}

    def test_only_internal_radix_node_count_can_change(self):
        actual = copy.deepcopy(self.before)
        actual['databases'][0][b'jobs']['value'][5] = 1
        self.assertEqual(self.state.compare(self.before, actual, 2000), {'preserved': 1, 'expired': 0})
        self.assertEqual(self.before['databases'][0][b'jobs']['value'][5], 2)
        self.assertEqual(actual['databases'][0][b'jobs']['value'][5], 1)

    def test_every_other_stream_field_stays_exact(self):
        original = self.before['databases'][0][b'jobs']['value']
        for index in range(1, len(original), 2):
            if original[index - 1] == b'radix-tree-nodes':
                continue
            actual = copy.deepcopy(self.before)
            actual['databases'][0][b'jobs']['value'][index] = b'changed'
            with self.subTest(field=original[index - 1]), self.assertRaises(ValueError):
                self.state.compare(self.before, actual, 2000)

    def test_binary_entry_and_nested_group_metadata_stay_exact(self):
        for path in ((11, 0, 1, 1), (13, 0, 3), (13, 0, 5, 0, 1),
                     (13, 0, 5, 0, 2), (13, 0, 5, 0, 3), (13, 0, 7, 0, 3)):
            actual = copy.deepcopy(self.before)
            cursor = actual['databases'][0][b'jobs']['value']
            for index in path[:-1]:
                cursor = cursor[index]
            cursor[path[-1]] = b'changed'
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.state.compare(self.before, actual, 2000)

    def test_counter_is_required_unique_and_nonnegative_integer(self):
        source = self.before['databases'][0][b'jobs']['value']
        candidates = [source[:4] + source[6:], source + [b'radix-tree-nodes', 2],
                      source[:5] + [-1] + source[6:], source[:5] + [True] + source[6:],
                      source[:5] + [b'2'] + source[6:], source + [b'odd'],
                      source + [b'length', 1]]
        for values in candidates:
            invalid = copy.deepcopy(self.before)
            invalid['databases'][0][b'jobs']['value'] = values
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.state.compare(invalid, invalid, 2000)

    def test_expiry_and_inventory_stay_exact(self):
        actual = copy.deepcopy(self.before)
        actual['databases'][0][b'jobs']['expires_at_ms'] += 1
        with self.assertRaises(ValueError):
            self.state.compare(self.before, actual, 2000)
        actual = copy.deepcopy(self.before)
        del actual['databases'][0][b'jobs']
        with self.assertRaises(ValueError):
            self.state.compare(self.before, actual, 2000)


class PostgresState(unittest.TestCase):
    def setUp(self):
        self.assertTrue((ROOT / 'postgres_checkpoint.py').exists(), 'PG17 checkpoint implementation is missing')
        import postgres_checkpoint
        self.state = postgres_checkpoint
        self.before = {'version': 1, 'physical_system_identifier': '7614955115223928876',
            'server_version': '17.6', 'globals_sha256': 'all-roles-and-password-verifiers',
            'databases': {'immich': {'schema_sha256': 'all-columns-acls-and-extensions',
                'tables': {'public.assets': {'rows': 3, 'sha256': 'duplicates-binary-unicode-vector-and-migration-rows'}},
                'sequences': {'public.assets_id_seq': {'last_value': 42, 'is_called': True, 'increment': 1, 'cycle': False}}}}}

    def test_logical_restore_may_change_physical_identity_only(self):
        actual = copy.deepcopy(self.before)
        actual['physical_system_identifier'] = '9999999999999999999'
        self.assertTrue(self.state.compare(self.before, actual)['logical_preserved'])
        self.assertFalse(self.state.compare(self.before, actual)['physical_identity_equal'])

    def test_all_logical_content_and_metadata_are_required(self):
        for path, value in (
            (('globals_sha256',), 'changed-verifier'),
            (('server_version',), '18.0'),
            (('databases', 'immich', 'schema_sha256'), 'changed-columns-extension-owner-or-schema'),
            (('databases', 'immich', 'tables', 'public.assets', 'rows'), 2),
            (('databases', 'immich', 'tables', 'public.assets', 'sha256'), 'changed-binary-vector-or-row'),
        ):
            actual = copy.deepcopy(self.before)
            cursor = actual
            for name in path[:-1]:
                cursor = cursor[name]
            cursor[path[-1]] = value
            with self.assertRaises(ValueError):
                self.state.compare(self.before, actual)
        actual = copy.deepcopy(self.before)
        del actual['databases']['immich']['tables']['public.assets']
        with self.assertRaises(ValueError):
            self.state.compare(self.before, actual)

    def test_native_sequence_recovery_must_never_lower_the_floor(self):
        actual = copy.deepcopy(self.before)
        actual['databases']['immich']['sequences']['public.assets_id_seq']['last_value'] = 41
        with self.assertRaises(ValueError):
            self.state.compare(self.before, actual)
        actual['databases']['immich']['sequences']['public.assets_id_seq']['last_value'] = 74
        self.assertTrue(self.state.compare(self.before, actual)['logical_preserved'])
        actual['databases']['immich']['sequences']['public.assets_id_seq']['increment'] = 2
        with self.assertRaises(ValueError):
            self.state.compare(self.before, actual)


class RedisACL(unittest.TestCase):
    def test_existing_password_verifier_avoids_copying_the_password_for_sealing(self):
        import hashlib
        import redis_acl
        self.assertTrue(callable(getattr(redis_acl, 'users_from_verifier', None)))
        verifier = hashlib.sha256(b'existing-application').hexdigest()
        self.assertEqual(redis_acl.users_from_verifier(verifier, b'new-maintenance'),
                         redis_acl.users(b'existing-application', b'new-maintenance'))
        for invalid in ('', 'a' * 63, 'g' * 64, verifier.upper(), None):
            with self.subTest(verifier=invalid), self.assertRaises(ValueError):
                redis_acl.users_from_verifier(invalid, b'new-maintenance')
        with self.assertRaises(ValueError):
            redis_acl.users_from_verifier(verifier, b'existing-application')

    def test_declarations_keep_passwords_hashed_and_app_commands_scoped(self):
        import redis_acl
        import hashlib
        value = redis_acl.users(b'application-synthetic', b'maintenance-synthetic')
        self.assertEqual(value.splitlines(), [
            'user default on #' + hashlib.sha256(b'application-synthetic').hexdigest() + ' ~* &* +@all -config|set -acl',
            'user homelab-maintenance on #' + hashlib.sha256(b'maintenance-synthetic').hexdigest() + ' ~* &* +@all'])
        self.assertNotIn('application-synthetic', value)
        self.assertNotIn('maintenance-synthetic', value)
        for app, admin in [(b'',b'x'),(b'x',b''),(b'x',b'x'),('x',b'y')]:
            with self.subTest(app=type(app).__name__, admin=type(admin).__name__), self.assertRaises(ValueError):
                redis_acl.users(app,admin)


if __name__ == '__main__':
    unittest.main()
