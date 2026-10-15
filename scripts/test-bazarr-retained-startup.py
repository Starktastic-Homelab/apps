#!/usr/bin/env python3
"""Bazarr retained startup and exact conversion contract checks."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import time
import uuid
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'scripts/bazarr-postgresql'
ENV = {'POSTGRES_ENABLED': 'true', 'POSTGRES_HOST': 'postgres-postgresql.databases',
       'POSTGRES_PORT': '5432', 'POSTGRES_DATABASE': 'bazarr', 'POSTGRES_USERNAME': 'bazarr',
       'POSTGRES_PASSWORD': 'fixture-only', 'BAZARR_APIKEY': 'preserved-api'}
SETTINGS = {'auth': {'apikey': 'preserved-api', 'type': None},
            'general': {'flask_secret_key': 'preserved-session', 'use_sonarr': True, 'use_radarr': True},
            'postgresql': {'enabled': True, 'url': ''}, 'sonarr': {'apikey': 'preserved-sonarr'},
            'radarr': {'apikey': 'preserved-radarr'}}


def module(test, name):
    path = PACKAGE / (name + '.py')
    test.assertTrue(path.is_file(), 'Bazarr ' + name + ' contract missing')
    spec = importlib.util.spec_from_file_location('bazarr_' + name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.guard = module(self, 'guard')
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / 'config').mkdir()
        (self.root / 'db').mkdir()
        (self.root / '.homelab-bazarr-config').write_text('homelab/bazarr/config/v1\n')
        self.write(SETTINGS)

    def write(self, settings):
        (self.root / 'config/config.yaml').write_text(yaml.safe_dump(settings))

    def test_preserved_settings_and_native_environment(self):
        self.guard.validate(self.root, ENV)

    def test_missing_wrong_identity_and_symlink(self):
        marker = self.root / '.homelab-bazarr-config'
        for value in ('', 'homelab/seerr/config/v1\n'):
            marker.write_text(value)
            with self.assertRaises(ValueError):
                self.guard.validate(self.root, ENV)
        marker.unlink()
        marker.symlink_to(self.root / 'config/config.yaml')
        with self.assertRaises(ValueError):
            self.guard.validate(self.root, ENV)

    def test_missing_api_or_session_or_malformed_config(self):
        for section, key in (('auth', 'apikey'), ('general', 'flask_secret_key')):
            settings = copy.deepcopy(SETTINGS)
            settings[section][key] = ''
            self.write(settings)
            with self.assertRaises(ValueError):
                self.guard.validate(self.root, ENV)
        for value in ('', '[]', 'auth: [', 'auth: {}\nauth: {}\n'):
            (self.root / 'config/config.yaml').write_text(value)
            with self.assertRaises(ValueError):
                self.guard.validate(self.root, ENV)

    def test_wrong_database_overrides_and_api_key(self):
        for key, value in (('POSTGRES_ENABLED', 'false'), ('POSTGRES_DATABASE', 'seerr'),
                           ('POSTGRES_HOST', 'elsewhere'), ('POSTGRES_PASSWORD', ''),
                           ('POSTGRES_URL', 'postgresql://other/db'),
                           ('BAZARR_CONFIG_BASE_FILE_PATH', '/elsewhere'), ('BAZARR_APIKEY', 'new-api')):
            with self.assertRaises(ValueError):
                self.guard.validate(self.root, dict(ENV, **{key: value}))
        settings = copy.deepcopy(SETTINGS)
        settings['postgresql']['url'] = 'postgresql://other/db'
        self.write(settings)
        with self.assertRaises(ValueError):
            self.guard.validate(self.root, ENV)

    def test_config_engine_flag_matches_stock_backup_backend(self):
        settings = copy.deepcopy(SETTINGS)
        settings['postgresql']['enabled'] = False
        self.write(settings)
        with self.assertRaises(ValueError):
            self.guard.validate(self.root, ENV)

    def test_active_sqlite_and_sidecars_refused(self):
        for suffix in ('', '-wal', '-shm', '-journal'):
            p = self.root / ('db/bazarr.db' + suffix)
            p.touch()
            with self.assertRaises(ValueError):
                self.guard.validate(self.root, ENV)
            p.unlink()


class DataTests(unittest.TestCase):
    def setUp(self):
        self.data = module(self, 'data')
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / 'source.db'
        self.writer = sqlite3.connect(self.path)
        self.addCleanup(self.writer.close)
        self.writer.execute('PRAGMA journal_mode=WAL')
        for table in self.data.TABLES:
            self.writer.execute('CREATE TABLE "' + table + '" (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, ffprobe_cache BLOB, timestamp DATETIME, enabled BOOLEAN)')
            self.writer.execute('INSERT INTO "' + table + '" VALUES (2,?, ?, ?, 1)', ('עברית café', b'\x00\xff\x12', '2026-10-15 01:02:03.123456'))
            self.writer.execute('INSERT INTO "' + table + '"(id) VALUES (30)')
            self.writer.execute('DELETE FROM "' + table + '" WHERE id=30')
        self.writer.execute('CREATE TABLE alembic_version(version_num TEXT NOT NULL)')
        self.writer.execute("INSERT INTO alembic_version VALUES ('537e9b4d10e3')")
        self.writer.commit()

    def postgres(self):
        result = {'database': 'bazarr', 'role': 'bazarr', 'revision': '537e9b4d10e3',
                  'unvalidatedConstraints': [], 'disabledTriggers': [], 'tables': {}}
        for table in self.data.TABLES:
            result['tables'][table] = {'columns': {'id': 'integer', 'title': 'text', 'ffprobe_cache': 'bytea',
                                                  'timestamp': 'timestamp without time zone', 'enabled': 'boolean'},
                                      'rows': [{'id': 2, 'title': 'עברית café', 'ffprobe_cache': '\\x00ff12',
                                                'timestamp': '2026-10-15T01:02:03.123456', 'enabled': True}],
                                      'sequenceFloors': {'id': 30}}
        return result

    def test_native_materialization_includes_committed_wal_and_floors(self):
        destination = self.path.with_name('materialized.db')
        proof = self.data.materialize(self.path, destination)
        self.assertEqual(proof['counts'], {t: 1 for t in self.data.TABLES})
        self.assertTrue(all(x == {'id': 30} for x in proof['allocators'].values()))
        with sqlite3.connect(destination) as con:
            self.assertEqual(con.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(con.execute('PRAGMA journal_mode').fetchone()[0], 'delete')
        self.assertFalse(destination.with_name(destination.name + '-wal').exists())
        with self.assertRaises(FileExistsError):
            self.data.materialize(self.path, destination)

    def test_all_typed_rows_match_including_blob_unicode_and_microseconds(self):
        result = self.data.compare(self.path, self.postgres())
        self.assertEqual(result['counts'], {t: 1 for t in self.data.TABLES})
        self.assertEqual(len(result['digests']), 16)

    def test_changed_field_omitted_column_and_row_rejected(self):
        for key, value in (('title', 'lost'), ('ffprobe_cache', '\\x00ff13'),
                           ('timestamp', '2026-10-15T01:02:03.123000'), ('enabled', False)):
            pg = self.postgres()
            pg['tables']['table_history']['rows'][0][key] = value
            with self.assertRaises(ValueError):
                self.data.compare(self.path, pg)
        for key in ('rows', 'columns'):
            pg = self.postgres()
            if key == 'rows':
                pg['tables']['table_history'][key] = []
            else:
                del pg['tables']['table_history'][key]['title']
            with self.assertRaises(ValueError):
                self.data.compare(self.path, pg)

    def test_deleted_ids_foreign_role_revision_and_partial_loader_rejected(self):
        pg = self.postgres()
        pg['tables']['table_history']['sequenceFloors']['id'] = 2
        with self.assertRaises(ValueError):
            self.data.compare(self.path, pg)
        for key, value in (('role', 'postgres'), ('database', 'other'), ('revision', 'old'),
                           ('unvalidatedConstraints', ['bad']), ('disabledTriggers', ['bad'])):
            with self.assertRaises(ValueError):
                self.data.compare(self.path, dict(self.postgres(), **{key: value}))

    def test_external_or_text_keys_do_not_require_invented_sequences(self):
        pg = self.postgres()
        pg['tables']['table_shows']['sequenceFloors'] = {}
        self.data.compare(self.path, pg)
        self.writer.execute('DROP TABLE table_settings_languages')
        self.writer.execute('CREATE TABLE table_settings_languages(code3 TEXT PRIMARY KEY, title TEXT)')
        self.writer.execute("INSERT INTO table_settings_languages VALUES ('heb','עברית')")
        self.writer.commit()
        pg['tables']['table_settings_languages'] = {'columns': {'code3': 'text', 'title': 'text'},
                                                    'rows': [{'code3': 'heb', 'title': 'עברית'}], 'sequenceFloors': {}}
        self.data.compare(self.path, pg)


@unittest.skipUnless(os.environ.get('BAZARR_SQL_TEST'), 'Enable disposable local SQL qualification')
class NativeDatabaseTests(unittest.TestCase):
    def test_empty_extra_wrong_and_incomplete_state_rejected_then_preserved_state_passes(self):
        name = 'bazarr-retained-check-' + uuid.uuid4().hex[:12]
        def command(args, data=None, check=True):
            result = subprocess.run(args, input=data, text=True, capture_output=True, timeout=60)
            if check and result.returncode:
                raise AssertionError('Synthetic SQL fixture failed; private output suppressed')
            return result
        image = yaml.safe_load((ROOT / 'scripts/postgres-enrollment/job.yaml').read_text())['spec']['template']['spec']['containers'][0]['image']
        command(['docker', 'run', '-d', '--name', name, '--network', 'none', '--memory', '256m', '--cpus', '1', '--pids-limit', '128',
                 '--tmpfs', '/var/lib/postgresql:rw,size=128m', '-e', 'PGDATA=/var/lib/postgresql/data',
                 '-e', 'POSTGRES_PASSWORD=fixture-admin', '-e', 'POSTGRES_INITDB_ARGS=--auth-host=scram-sha-256 --auth-local=trust', image])
        self.addCleanup(lambda: command(['docker', 'rm', '-f', name]))
        for _ in range(100):
            if command(['docker', 'exec', name, 'pg_isready', '-h127.0.0.1', '-Upostgres'], check=False).returncode == 0:
                break
            time.sleep(.2)
        else:
            self.fail('Synthetic SQL readiness deadline')
        def sql(query, database='bazarr'):
            return command(['docker', 'exec', '-i', name, 'psql', '-XqAt', '-vON_ERROR_STOP=1', '-Upostgres', '-d' + database], query).stdout
        def gate(user='bazarr', password='fixture-password'):
            return command(['docker', 'exec', '-i', '-e', 'PGPASSWORD=' + password, name, 'psql', '-XqAt', '-vON_ERROR_STOP=1',
                            '-h127.0.0.1', '-U' + user, '-dbazarr'], (PACKAGE / 'main.sql').read_text(), check=False)
        sql("CREATE ROLE bazarr LOGIN PASSWORD 'fixture-password';", 'postgres')
        sql('CREATE DATABASE bazarr OWNER bazarr;', 'postgres')
        self.assertNotEqual(gate().returncode, 0, 'Empty database accepted')
        data = module(self, 'data')
        sql(''.join('CREATE TABLE "' + table + '" (id integer); ALTER TABLE "' + table + '" OWNER TO bazarr;' for table in data.TABLES)
            + 'ALTER TABLE public.system ADD COLUMN configured text; CREATE TABLE public.alembic_version(version_num text); ALTER TABLE public.alembic_version OWNER TO bazarr;'
            + "INSERT INTO public.alembic_version VALUES ('537e9b4d10e3');")
        self.assertNotEqual(gate().returncode, 0, 'Empty installation accepted')
        sql("INSERT INTO public.system VALUES (1,'1'); INSERT INTO public.table_languages_profiles VALUES (1); INSERT INTO public.table_shows VALUES (1);")
        self.assertEqual(gate().returncode, 0)
        before = sql('SELECT * FROM public.system; SELECT * FROM public.alembic_version;')
        self.assertEqual(gate().returncode, 0)
        self.assertEqual(before, sql('SELECT * FROM public.system; SELECT * FROM public.alembic_version;'))
        self.assertNotEqual(gate(password='wrong').returncode, 0)
        self.assertNotEqual(gate(user='postgres', password='fixture-admin').returncode, 0)
        sql('CREATE TABLE public.unrelated_extra(id integer);')
        self.assertNotEqual(gate().returncode, 0, 'Unexpected public table accepted')
        sql('DROP TABLE public.unrelated_extra;')
        self.assertEqual(gate().returncode, 0)
        sql('ALTER TABLE public.table_movies RENAME TO missing_movies;')
        self.assertNotEqual(gate().returncode, 0, 'Missing stock table accepted')
        sql("ALTER TABLE public.missing_movies RENAME TO table_movies; UPDATE public.alembic_version SET version_num='wrong';")
        self.assertNotEqual(gate().returncode, 0, 'Wrong revision accepted')
        sql("UPDATE public.alembic_version SET version_num='537e9b4d10e3'; DELETE FROM public.table_languages_profiles;")
        self.assertNotEqual(gate().returncode, 0, 'Missing retained profile accepted')


class SourcesTests(unittest.TestCase):
    def test_embedded_guard_matches_source_and_encrypted_bundle_preserves_prior_inputs(self):
        cm = yaml.safe_load((PACKAGE / 'production/guard-configmap.yaml').read_text())
        for name in ('guard.py', 'main.sql'):
            self.assertEqual(cm['data'][name], (PACKAGE / name).read_text())
        folder = PACKAGE / 'production/enrollment'
        cm = yaml.safe_load((folder / 'enrollment-configmap.yaml').read_text())
        config = json.loads(cm['data']['config.json'])
        prior = json.loads(yaml.safe_load((ROOT / 'infrastructure/controllers/databases/postgres/manifests/enrollment-configmap.yaml').read_text())['data']['config.json'])
        if len(config['entries']) == len(prior['entries']) + 1:
            self.assertEqual(config['entries'][:-1], prior['entries'])
        else:
            self.assertEqual(prior['entries'][:len(config['entries'])], config['entries'])
        self.assertEqual(config['expectedSystemIdentifier'], prior['expectedSystemIdentifier'])
        self.assertEqual(config['entries'][-1], {'id': 'bazarr', 'database': 'bazarr', 'role': 'bazarr', 'mode': 'new', 'passwordKey': 'bazarr-password'})
        aggregate = yaml.safe_load((folder / 'enrollment-secret.yaml').read_text())
        old = yaml.safe_load((ROOT / 'infrastructure/controllers/databases/postgres/manifests/enrollment-secret.yaml').read_text())
        for key, value in old['spec']['encryptedData'].items():
            self.assertEqual(aggregate['spec']['encryptedData'][key], value)
        app = yaml.safe_load((folder / 'application-secret.yaml').read_text())
        self.assertEqual(app['metadata']['name'], 'bazarr-postgres-secret')
        self.assertEqual(app['metadata']['namespace'], 'media')
        self.assertEqual(set(app['spec']['encryptedData']), {'password'})
        self.assertNotIn('data', app['spec']['template'])
        self.assertNotIn('stringData', app['spec']['template'])

    def test_fixed_target_native_env_and_existing_consumer_gate(self):
        prepare = module(self, 'prepare')
        resources, values = prepare.build_sources()
        self.assertEqual(resources[0]['metadata']['name'], 'bazarr-postgres-completion')
        main = values['controllers']['main']
        self.assertEqual(main['pod']['nodeSelector'], {'node-role.kubernetes.io/worker': 'true'})
        self.assertEqual(main['replicas'], 1)
        self.assertEqual(main['strategy'], 'Recreate')
        env = main['containers']['main']['env']
        self.assertEqual(env['POSTGRES_ENABLED'], 'true')
        self.assertEqual(env['POSTGRES_PASSWORD']['valueFrom']['secretKeyRef'], {'name': 'bazarr-postgres-secret', 'key': 'password'})
        self.assertEqual(values['persistence']['bazarr-config']['existingClaim'], 'bazarr-config-block')
        self.assertNotIn('media', values['persistence'])
        self.assertEqual(main['initContainers']['retained-state']['image']['repository'], 'lscr.io/linuxserver/bazarr')


@unittest.skipUnless(os.environ.get('BAZARR_RETAINED_RENDER'), 'Actual chart render required')
class RenderTests(unittest.TestCase):
    def test_actual_layered_render_preserves_media_scripts_and_image(self):
        objects = [v for v in yaml.safe_load_all(Path(os.environ['BAZARR_RETAINED_RENDER']).read_text()) if v]
        deployment = next(v for v in objects if v['kind'] == 'Deployment')
        spec = deployment['spec']['template']['spec']
        self.assertEqual(deployment['spec']['strategy']['type'], 'Recreate')
        self.assertEqual(spec['nodeSelector'], {'node-role.kubernetes.io/worker': 'true'})
        self.assertEqual([v['name'] for v in spec['initContainers']], ['retained-state', 'enrollment', 'database'])
        volumes = {v['name']: v for v in spec['volumes']}
        self.assertEqual(volumes['media']['persistentVolumeClaim']['claimName'], 'media-library-pvc')
        self.assertEqual(volumes['bazarr-config']['persistentVolumeClaim']['claimName'], 'bazarr-config-block')
        self.assertEqual(volumes['scripts']['configMap']['name'], 'bazarr-scripts')
        main = spec['containers'][0]
        self.assertEqual(main['image'], 'lscr.io/linuxserver/bazarr:v1.6.1-ls364@sha256:d24bd0048c759a468970989e9df11a6b96a7628d556d00f923e60a35ba59237b')
        self.assertEqual({v['mountPath'] for v in main['volumeMounts']}, {'/config', '/data', '/scripts'})
        self.assertFalse(spec['automountServiceAccountToken'])
        self.assertFalse(any(v['kind'] == 'PersistentVolumeClaim' for v in objects))

    def test_retained_and_original_source_bindings_are_protected(self):
        pv = yaml.safe_load((PACKAGE / 'production/pv.yaml').read_text())
        pvc = yaml.safe_load((PACKAGE / 'production/pvc.yaml').read_text())
        self.assertEqual(pv['spec']['capacity']['storage'], '4Gi')
        self.assertEqual(pv['spec']['accessModes'], ['ReadWriteOncePod'])
        self.assertEqual(pv['spec']['persistentVolumeReclaimPolicy'], 'Retain')
        self.assertEqual(pv['spec']['csi']['volumeHandle'], 'homelab//k3s-block/9999/vm-9999-bazarr.raw')
        self.assertEqual(pvc['spec']['volumeName'], pv['metadata']['name'])
        policy = list(yaml.safe_load_all((PACKAGE / 'production/source-hold.yaml').read_text()))
        self.assertIn("claimName == 'bazarr'", policy[0]['spec']['matchConditions'][0]['expression'])
        self.assertEqual(policy[1]['spec']['validationActions'], ['Deny'])


if __name__ == '__main__':
    unittest.main()
