#!/usr/bin/env python3
"""Exact-image qualification; opt in explicitly (Docker, synthetic media only)."""
import argparse
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent / 'redis-immich-retained'
sys.path.insert(0, str(ROOT))


class RedisNative(unittest.TestCase):
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


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--app', choices=['redis', 'immich'], required=True)
    args, rest = parser.parse_known_args()
    if args.app != 'redis':
        parser.error('Immich fixture is not implemented yet')
    unittest.main(argv=[sys.argv[0], *rest])
