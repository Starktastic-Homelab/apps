#!/usr/bin/env python3
"""Exact-image qualification; opt in explicitly (Docker, synthetic media only)."""
import argparse
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent / 'redis-immich-retained'
sys.path.insert(0, str(ROOT))


class RedisNative(unittest.TestCase):
    def test_application_configuration_is_protected_after_recreation(self):
        import fixtures
        self.assertTrue(hasattr(fixtures, 'run_acl'), 'Native startup ACL qualification is missing')
        result = fixtures.run_acl()
        for key in ('dispatcharr_clients_work','unrestricted_disabling_reproduced','application_config_refused',
                    'application_acl_refused','maintenance_config_works','recreation_preserved','cleanup_verified'):
            self.assertTrue(result[key], key)
        self.assertEqual(result['exporter_error'], 0)

    def test_exporter_reports_native_durability_and_recovery(self):
        import fixtures
        self.assertTrue(hasattr(fixtures, 'run_exporter'), 'Native exporter durability qualification is missing')
        result = fixtures.run_exporter()
        self.assertEqual(result['enabled'], {'aof_enabled': 1.0, 'aof_last_write_status': 1.0})
        self.assertEqual(result['disabled']['aof_enabled'], 0.0)
        self.assertEqual(result['failed_write'], {'aof_enabled': 1.0, 'aof_last_write_status': 0.0})
        self.assertEqual(result['recovered'], result['enabled'])
        self.assertTrue(result['cleanup_verified'])

    def test_deployed_module_and_identity_configuration(self):
        import fixtures
        result = fixtures.run_redis_case('source-config')
        self.assertEqual(result['modules'], ['ReJSON', 'search', 'vectorset'])
        self.assertEqual((result['uid'], result['gid']), (1001, 1001))
        self.assertTrue(result['cleanup_verified'])

    def test_middle_corruption_never_starts_an_empty_server(self):
        import fixtures
        result = fixtures.run_redis_case('corrupt-increment')
        self.assertTrue(result['native_refused'])
        self.assertTrue(result['guard_read_only'])
        self.assertTrue(result['cleanup_verified'])

    def test_torn_tail_contract(self):
        import fixtures
        result = fixtures.run_redis_case('torn-tail')
        self.assertFalse(result['guard_refused'], 'Qualified stock tail recovery must remain automatic')
        self.assertTrue(result['guard_read_only'])
        self.assertTrue(result['stock_recovery_preserved'])
        self.assertTrue(result['native_truncates'])
        self.assertTrue(result['cleanup_verified'])

    def test_stock_manifest_history_does_not_block_rebuild(self):
        import fixtures
        result = fixtures.run_redis_case('history')
        self.assertTrue(result['accepted'], 'Stock manifest history must not block an intact rebuild')
        self.assertTrue(result['cleanup_verified'])

    def test_stale_disk_is_not_memory_recovery(self):
        self.assertTrue((ROOT / 'fixtures.py').exists(), 'Exact-image recovery fixture is missing')
        import fixtures
        result = fixtures.run_redis()
        self.assertTrue(result['stale_disk_rejected'])
        self.assertTrue(result['memory_restore_preserved'])
        self.assertTrue(result['aof_restore_preserved'])
        self.assertTrue(result['guard_read_only'])
        self.assertTrue(result['cleanup_verified'])
        self.assertTrue(result.get('celery_pending_recovered'), 'Native Celery recovery is unqualified')
        self.assertTrue(result.get('bullmq_pending_recovered'), 'Native BullMQ recovery is unqualified')


class PostgresNative(unittest.TestCase):
    def test_crc_warning_and_stale_pid_contract(self):
        import fixtures
        self.assertTrue(hasattr(fixtures, 'run_postgres_case'), 'Exact PG17 guard/recovery fixture is missing')
        for case in ('crc-warning-exit-zero', 'standby-signal', 'wrong-identity'):
            result = fixtures.run_postgres_case(case)
            self.assertTrue(result['guard_refused'])
            self.assertTrue(result['guard_read_only'])
        result = fixtures.run_postgres_case('stale-pid')
        self.assertTrue(result['guard_read_only'])
        self.assertTrue(result['stock_recovery_qualified'])

    def test_complete_physical_and_independent_logical_recovery(self):
        import fixtures
        self.assertTrue(hasattr(fixtures, 'run_postgres'), 'Exact PG17 physical/logical fixture is missing')
        result = fixtures.run_postgres()
        self.assertTrue(result['physical_identity_preserved'])
        self.assertTrue(result['logical_identity_differs'])
        self.assertTrue(result['all_state_preserved'])
        self.assertTrue(result['cleanup_verified'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--app', choices=['redis', 'immich'], required=True)
    args, rest = parser.parse_known_args()
    unittest.main(argv=[sys.argv[0], RedisNative.__name__ if args.app == 'redis' else PostgresNative.__name__, *rest])
