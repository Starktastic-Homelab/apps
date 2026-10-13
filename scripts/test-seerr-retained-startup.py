#!/usr/bin/env python3
"""Qualify inactive Seerr retained startup and instance composition."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import uuid

import yaml

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'scripts/seerr-postgresql'
TABLES = ('blocklist', 'discover_slider', 'issue', 'issue_comment', 'media', 'media_request',
          'override_rule', 'season', 'season_request', 'session', 'user',
          'user_push_subscription', 'user_settings', 'watchlist')


class RetainedConfigTests(unittest.TestCase):
    def check(self, alter=None, env_change=None, accepted=False, instance='seerr'):
        self.assertTrue((PACKAGE / 'guard.py').is_file(), 'Retained Seerr guard not implemented')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'config'; root.mkdir()
            (root / '.homelab-seerr-config').write_text(f'homelab/{instance}/config/v1\n')
            settings = {'main': {'apiKey': 'fixture-api-secret'}, 'sessionSecret': 'fixture-session-secret',
                        'clientId': 'fixture-client', 'vapidPublic': 'fixture-public', 'vapidPrivate': 'fixture-private'}
            (root / 'settings.json').write_text(json.dumps(settings))
            env = dict(os.environ, NODE_ENV='production', DB_TYPE='postgres', DB_HOST='postgres-postgresql.databases',
                       DB_PORT='5432', DB_NAME=instance.replace('-', '_'), DB_USER=instance.replace('-', '_'),
                       DB_POOL_SIZE='3', DB_PASS='fixture-db-secret')
            for key in ('DB_SOCKET_PATH', 'CONFIG_DIRECTORY', 'API_KEY'):
                env.pop(key, None)
            if env_change:env_change(env)
            if alter:alter(root)
            def snapshot():
                return {str(p.relative_to(root.parent)): hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in root.parent.rglob('*') if p.is_file()}
            before = snapshot()
            result = subprocess.run([sys.executable, '-I', '-B', str(PACKAGE / 'guard.py'), str(root), instance],
                                    env=env, capture_output=True, timeout=10)
            self.assertEqual(result.returncode == 0, accepted, result.stderr.decode())
            self.assertEqual(before, snapshot(), 'Guard wrote retained state')
            for secret in ('fixture-api-secret', 'fixture-session-secret', 'fixture-db-secret', 'fixture-private'):
                self.assertNotIn(secret.encode(), result.stdout + result.stderr)

    def test_preserved_instances_are_accepted_without_writes(self):
        for instance in ('seerr', 'seerr-ru'):self.check(accepted=True, instance=instance)

    def test_missing_wrong_or_oversized_marker_is_rejected(self):
        self.check(lambda p: (p / '.homelab-seerr-config').unlink())
        for value in ('homelab/seerr-ru/config/v1\n', 'x' * 131073):
            self.check(lambda p: (p / '.homelab-seerr-config').write_text(value))

    def test_invalid_missing_or_duplicate_settings_are_rejected(self):
        self.check(lambda p: (p / 'settings.json').unlink())
        for value in ('{', '[]', 'null', '{"main":{"apiKey":"x","apiKey":"y"}}', 'x' * 131073):
            self.check(lambda p: (p / 'settings.json').write_text(value))

    def test_missing_or_invalid_preserved_identifiers_are_rejected(self):
        for key in ('apiKey', 'sessionSecret', 'clientId', 'vapidPublic', 'vapidPrivate'):
            for value in (None, '', ' ', 1, [], {}):
                def alter(p):
                    settings = json.loads((p / 'settings.json').read_text())
                    (settings['main'] if key == 'apiKey' else settings)[key] = value
                    (p / 'settings.json').write_text(json.dumps(settings))
                self.check(alter)
        self.check(lambda p: (p / 'settings.json').write_text('{"main":null}'))

    def test_symlinked_retained_paths_are_rejected(self):
        for name in ('.homelab-seerr-config', 'settings.json'):
            def alter(p):
                (p / name).rename(p / (name + '.real')); (p / name).symlink_to(name + '.real')
            self.check(alter)
        self.check(lambda p: (p / 'db').symlink_to('missing', target_is_directory=True))
        def root_link(p):
            p.rename(p.parent / 'real'); p.symlink_to('real', target_is_directory=True)
        self.check(root_link)

    def test_sqlite_main_and_sidecars_including_dangling_links_are_rejected(self):
        for suffix in ('', '-wal', '-shm', '-journal'):
            for linked in (False, True):
                def alter(p):
                    (p / 'db').mkdir(); target = p / 'db' / ('db.sqlite3' + suffix)
                    target.symlink_to('missing') if linked else target.write_bytes(b'fixture')
                self.check(alter)
        self.check(lambda p: (p / 'db').mkdir(), accepted=True)

    def test_wrong_database_or_environment_is_rejected(self):
        for key in ('NODE_ENV', 'DB_TYPE', 'DB_HOST', 'DB_PORT', 'DB_NAME', 'DB_USER', 'DB_POOL_SIZE'):
            self.check(env_change=lambda e: e.pop(key))
            self.check(env_change=lambda e: e.update({key: 'wrong'}))
        for key,value in (('DB_SOCKET_PATH','/tmp/socket'),('CONFIG_DIRECTORY','/other'),('API_KEY','replacement')):
            self.check(env_change=lambda e: e.update({key:value}))
        self.check(env_change=lambda e: e.pop('DB_PASS'))
        for value in ('', ' ' * 4, 'x' * 4097, 'x\n'):
            self.check(env_change=lambda e: e.update(DB_PASS=value))
        self.check(env_change=lambda e: e.update(CONFIG_DIRECTORY='/app/config', API_KEY='fixture-api-secret'), accepted=True)


@unittest.skipUnless(os.environ.get('SEERR_SQL_TEST'), 'Enable disposable local SQL qualification')
class NativeDatabaseTests(unittest.TestCase):
    def test_empty_wrong_and_incomplete_state_is_rejected_then_canonical_data_passes(self):
        self.assertTrue((PACKAGE / 'main.sql').is_file(), 'Retained SQL not implemented')
        name = 'seerr-retained-check-' + uuid.uuid4().hex[:12]
        def command(args, data=None, check=True):
            r = subprocess.run(args, input=data, text=True, capture_output=True, timeout=60)
            if check and r.returncode:raise AssertionError('Synthetic SQL fixture failed; details suppressed')
            return r
        image = yaml.safe_load((ROOT / 'scripts/postgres-enrollment/job.yaml').read_text())['spec']['template']['spec']['containers'][0]['image']
        command(['docker','run','-d','--name',name,'--network','none','--memory','256m','--cpus','1','--pids-limit','128',
                 '--tmpfs','/var/lib/postgresql:rw,size=128m','-e','PGDATA=/var/lib/postgresql/data',
                 '-e','POSTGRES_PASSWORD=fixture-admin','-e','POSTGRES_INITDB_ARGS=--auth-host=scram-sha-256 --auth-local=trust', image])
        self.addCleanup(lambda: command(['docker','rm','-f',name]))
        for _ in range(100):
            if command(['docker','exec',name,'pg_isready','-h127.0.0.1','-Upostgres'],check=False).returncode==0:break
            time.sleep(.2)
        else:self.fail('Synthetic SQL readiness deadline')
        def sql(q,db='postgres'):
            return command(['docker','exec','-i',name,'psql','-XqAt','-vON_ERROR_STOP=1','-Upostgres','-d'+db],q).stdout
        def gate(db,user=None,password='fixture-password'):
            return command(['docker','exec','-i','-e','PGPASSWORD='+password,name,'psql','-XqAt','-vON_ERROR_STOP=1',
                            '-h127.0.0.1','-U'+(user or db),'-d'+db], (PACKAGE/'main.sql').read_text(),check=False)
        sql("CREATE ROLE seerr LOGIN PASSWORD 'fixture-password'; CREATE ROLE seerr_ru LOGIN PASSWORD 'fixture-password';")
        for db in ('seerr','seerr_ru'):
            sql(f'CREATE DATABASE {db} OWNER {db};')
            self.assertNotEqual(gate(db).returncode,0)
            sql(''.join(f'CREATE TABLE "{t}" (id integer); ALTER TABLE "{t}" OWNER TO {db};' for t in TABLES)
                + f'CREATE TABLE migrations (id integer,timestamp bigint,name text); ALTER TABLE migrations OWNER TO {db};'
                + "INSERT INTO migrations SELECT n,n,'fixture' FROM generate_series(1,18) n;"
                + "INSERT INTO migrations VALUES (19,1781732098511,'AddIgnoreQuotaToMediaRequest1781732098511');",db)
            self.assertNotEqual(gate(db).returncode,0,'Empty user data accepted')
            sql('INSERT INTO "user" VALUES (1);',db)
            before = sql('SELECT * FROM "user"; SELECT * FROM migrations ORDER BY id;',db)
            self.assertEqual(gate(db).returncode,0)
            self.assertEqual(before,sql('SELECT * FROM "user"; SELECT * FROM migrations ORDER BY id;',db))
            self.assertNotEqual(gate(db,password='wrong').returncode,0)
            self.assertNotEqual(gate(db,user='postgres',password='fixture-admin').returncode,0)
            self.assertNotEqual(gate(db,user='seerr_ru' if db=='seerr' else 'seerr').returncode,0)
            sql('ALTER TABLE media RENAME TO hidden_media;',db); self.assertNotEqual(gate(db).returncode,0)
            sql('ALTER TABLE hidden_media RENAME TO media; DELETE FROM migrations WHERE id=19;',db)
            self.assertNotEqual(gate(db).returncode,0)


if __name__ == '__main__':unittest.main()
