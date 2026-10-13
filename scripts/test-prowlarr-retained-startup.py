#!/usr/bin/env python3
"""Check Prowlarr retained config and its inactive PostgreSQL/CSI composition."""
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
import xml.etree.ElementTree as ET

import yaml

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'scripts/prowlarr-postgresql'
PASSWORDS = {'main': 'fixture "secret"; with spaces', 'log': 'fixture-log-secret'}


def connection(kind):
    password = PASSWORDS[kind].replace('"', '""')
    return (f'Host=postgres-postgresql.databases;Port=5432;Username=prowlarr_{kind};'
            f'Password="{password}";Database=prowlarr_{kind};Maximum Pool Size=5;Timeout=10')


class RetainedConfigTests(unittest.TestCase):
    def check(self, alter=None, accepted=False):
        self.assertTrue((PACKAGE / 'guard.py').is_file(), 'Prowlarr retained guard not implemented')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = root / 'config'
            credentials = root / 'credentials'
            config.mkdir()
            credentials.mkdir()
            (config / '.homelab-prowlarr-config').write_text('homelab/prowlarr/config/v1\n')
            xml = ET.Element('Config')
            ET.SubElement(xml, 'ApiKey').text = 'fixture-api-secret'
            for kind in ('main', 'log'):
                ET.SubElement(xml, f'Postgres{kind.title()}DbConnectionString').text = connection(kind)
                (credentials / f'{kind}-password').write_text(PASSWORDS[kind])
            ET.ElementTree(xml).write(config / 'config.xml', encoding='utf-8')
            if alter:
                alter(config, credentials)
            def snapshot():
                return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).digest()
                        for p in root.rglob('*') if p.is_file()}
            before = snapshot()
            result = subprocess.run([sys.executable, '-I', '-B', str(PACKAGE / 'guard.py'),
                                     str(config), str(credentials)], capture_output=True)
            self.assertEqual(result.returncode == 0, accepted, result.stderr.decode())
            self.assertEqual(before, snapshot(), 'Guard changed retained data or credentials')
            for secret in ('fixture-api-secret', *PASSWORDS.values()):
                self.assertNotIn(secret.encode(), result.stdout + result.stderr)

    def test_preserved_config_is_accepted_read_only(self):
        self.check(accepted=True)

    def test_missing_or_wrong_marker_is_rejected(self):
        self.check(lambda c, _: (c / '.homelab-prowlarr-config').unlink())
        self.check(lambda c, _: (c / '.homelab-prowlarr-config').write_text('other\n'))

    def test_missing_or_malformed_config_is_rejected(self):
        self.check(lambda c, _: (c / 'config.xml').unlink())
        self.check(lambda c, _: (c / 'config.xml').write_text('<bad'))

    def test_config_with_missing_api_key_is_rejected(self):
        self.change_field('ApiKey', '')

    def change_field(self, name, value):
        def alter(c, _):
            tree = ET.parse(c / 'config.xml')
            field = tree.getroot().find(name)
            if field is None:
                field = ET.SubElement(tree.getroot(), name)
            field.text = value
            tree.write(c / 'config.xml')
        self.check(alter)

    def test_wrong_main_and_log_connection_is_rejected(self):
        for kind in ('main', 'log'):
            self.change_field(f'Postgres{kind.title()}DbConnectionString', connection(kind) + ';Pooling=false')

    def test_missing_password_is_rejected(self):
        for kind in ('main', 'log'):
            self.check(lambda _, p, k=kind: (p / f'{k}-password').unlink())
            self.check(lambda _, p, k=kind: (p / f'{k}-password').write_text(''))

    def test_duplicate_fields_are_rejected(self):
        def alter(c, _):
            tree = ET.parse(c / 'config.xml')
            ET.SubElement(tree.getroot(), 'PostgresMainDbConnectionString').text = connection('main')
            tree.write(c / 'config.xml')
        self.check(alter)

    def test_conflicting_scalar_configuration_is_rejected(self):
        for name in ('PostgresHost', 'PostgresPort', 'PostgresUser', 'PostgresPassword',
                     'PostgresMainDb', 'PostgresLogDb'):
            self.change_field(name, 'conflict')

    def test_active_sqlite_files_are_rejected(self):
        for name in ('prowlarr.db', 'prowlarr.db-wal', 'prowlarr.db-shm',
                     'logs.db', 'logs.db-wal', 'logs.db-shm'):
            with self.subTest(name=name):
                self.check(lambda c, _, n=name: (c / n).write_bytes(b'fixture'))

    def test_symlinked_retained_identity_or_config_is_rejected(self):
        def replace(path):
            original = path.with_name(path.name + '.original')
            path.rename(original)
            path.symlink_to(original)
        self.check(lambda c, _: replace(c / '.homelab-prowlarr-config'))
        self.check(lambda c, _: replace(c / 'config.xml'))

    def test_native_secret_projection_is_accepted(self):
        def alter(_, p):
            target = p / '..fixture'
            target.mkdir()
            for kind in ('main', 'log'):
                path = p / f'{kind}-password'
                path.rename(target / path.name)
                path.symlink_to('..data/' + path.name)
            (p / '..data').symlink_to(target.name)
        self.check(alter, accepted=True)

    def test_password_symlink_outside_credentials_is_rejected(self):
        def alter(c, p):
            (c / 'outside').write_text(PASSWORDS['main'])
            (p / 'main-password').unlink()
            (p / 'main-password').symlink_to(c / 'outside')
        self.check(alter)


class CompositionTests(unittest.TestCase):
    def test_activation_explicitly_enables_manifest_discovery_without_changing_current_app(self):
        path = PACKAGE / 'production/app-metadata.yaml'
        self.assertTrue(path.is_file(), 'Activation manifest discovery patch missing')
        patch = yaml.safe_load(path.read_text())
        self.assertEqual(patch, {'manifests': True})
        current = yaml.safe_load((ROOT / 'services/media/prowlarr/app.yaml').read_text())
        self.assertFalse(current.get('manifests', False), 'Preparation unexpectedly activates manifest discovery')
        final = {**current, **patch}
        self.assertTrue(final['manifests'])
        self.assertEqual({k: v for k, v in final.items() if k != 'manifests'}, current)
        appset = yaml.safe_load((ROOT / 'bootstrap/appsets/cluster-apps.yaml').read_text())
        self.assertIn('{{- if dig "manifests" false . }}', appset['spec']['templatePatch'])
        self.assertIn("path: '{{.path.path}}/manifests'", appset['spec']['templatePatch'])
        self.assertEqual(final['commonValuesExtras'], ['templates/media-arr-common.yaml'])

    def test_sources_are_inactive_and_reuse_named_reader_roles(self):
        path = PACKAGE / 'production/consumer-gate.yaml'
        self.assertTrue(path.is_file(), 'Dual consumer sources not generated')
        objects = list(yaml.safe_load_all(path.read_text()))
        accounts = [x for x in objects if x['kind'] == 'ServiceAccount']
        self.assertEqual(len(accounts), 1)
        self.assertFalse(accounts[0]['automountServiceAccountToken'])
        bindings = [x for x in objects if x['kind'] == 'RoleBinding']
        self.assertEqual({x['metadata']['namespace'] for x in bindings}, {'argocd', 'databases'})
        self.assertEqual(len(bindings), 2)
        for binding in bindings:
            self.assertEqual(binding['roleRef']['name'], 'postgres-enrollment-completion-reader')
            self.assertEqual(binding['subjects'], [{'kind': 'ServiceAccount',
                'name': accounts[0]['metadata']['name'], 'namespace': 'media'}])
        config = next(x for x in objects if x['kind'] == 'ConfigMap')
        self.assertEqual(config['data']['completion_gate.py'],
                         (ROOT / 'scripts/postgres-enrollment/completion_gate.py').read_text())
        self.assertFalse(list(PACKAGE.rglob('app.yaml')))
        self.assertNotIn('prowlarr_main', (ROOT / 'infrastructure/controllers/databases/postgres/manifests/enrollment-configmap.yaml').read_text())

    def test_guard_configmap_uses_the_tested_sources(self):
        path = PACKAGE / 'production/guard-configmap.yaml'
        self.assertTrue(path.is_file(), 'Retained guard ConfigMap not generated')
        config = yaml.safe_load(path.read_text())
        self.assertEqual(config['data']['guard.py'], (PACKAGE / 'guard.py').read_text())
        self.assertEqual(config['data']['main.sql'], (PACKAGE / 'main.sql').read_text())

    def test_static_binding_has_exact_identity_and_growth_budget(self):
        path = PACKAGE / 'production/pv.yaml'
        self.assertTrue(path.is_file(), 'Inactive CSI binding not generated')
        pv = yaml.safe_load(path.read_text())
        pvc = yaml.safe_load((PACKAGE / 'production/pvc.yaml').read_text())
        self.assertEqual(pv['spec']['capacity']['storage'], '4Gi')
        self.assertEqual(pvc['spec']['resources']['requests']['storage'], '4Gi')
        self.assertEqual(pv['spec']['accessModes'], ['ReadWriteOncePod'])
        self.assertEqual(pv['spec']['csi']['volumeHandle'], 'homelab//k3s-block/9999/vm-9999-prowlarr.raw')
        self.assertEqual(pv['spec']['csi']['fsType'], 'ext4')
        self.assertEqual(pv['spec']['csi']['volumeAttributes']['cache'], 'none')
        self.assertEqual(pv['spec']['persistentVolumeReclaimPolicy'], 'Retain')
        self.assertEqual(pv['spec']['claimRef'], {'name': 'prowlarr-config-block', 'namespace': 'media'})
        self.assertEqual(pvc['spec']['volumeName'], pv['metadata']['name'])
        for obj in (pv, pvc):
            self.assertEqual(obj['metadata']['annotations']['argocd.argoproj.io/sync-options'], 'Prune=false,Delete=false')

    def test_encrypted_bundle_preserves_old_inputs_and_binds_both_declarations(self):
        path = PACKAGE / 'production/enrollment/enrollment-configmap.yaml'
        self.assertTrue(path.is_file(), 'Final encrypted bundle not prepared')
        configmap = yaml.safe_load(path.read_text())
        original = yaml.safe_load((ROOT / 'infrastructure/controllers/databases/postgres/manifests/enrollment-configmap.yaml').read_text())
        config = json.loads(configmap['data']['config.json'])
        prior = json.loads(original['data']['config.json'])
        self.assertEqual(config['entries'][:-2], prior['entries'])
        self.assertEqual(config['expectedSystemIdentifier'], prior['expectedSystemIdentifier'])
        for kind, entry in zip(('main', 'log'), config['entries'][-2:]):
            self.assertEqual(entry, {'id': 'prowlarr-' + kind, 'database': 'prowlarr_' + kind,
                'role': 'prowlarr_' + kind, 'mode': 'new', 'passwordKey': 'prowlarr-' + kind + '-password'})
        aggregate = yaml.safe_load((PACKAGE / 'production/enrollment/enrollment-secret.yaml').read_text())
        existing = yaml.safe_load((ROOT / 'infrastructure/controllers/databases/postgres/manifests/enrollment-secret.yaml').read_text())
        for key, ciphertext in existing['spec']['encryptedData'].items():
            self.assertEqual(aggregate['spec']['encryptedData'][key], ciphertext)
        app = yaml.safe_load((PACKAGE / 'production/enrollment/application-secret.yaml').read_text())
        self.assertEqual(set(app['spec']['encryptedData']), {'main-password', 'log-password'})
        for obj in (app, aggregate):
            self.assertNotIn('data', obj['spec']['template'])
            self.assertNotIn('stringData', obj['spec']['template'])
            self.assertTrue(all(len(x) > 100 for x in obj['spec']['encryptedData'].values()))
        sys.path.insert(0, str(ROOT / 'scripts/postgres-enrollment'))
        import completion_gate
        self.assertEqual(configmap['data']['acceptance-generation'], completion_gate.generation(configmap['data']))
        job = yaml.safe_load((PACKAGE / 'production/enrollment/enrollment-job.yaml').read_text())
        self.assertEqual(job['metadata']['name'], completion_gate.hook_name(configmap['data']['acceptance-generation']))

    def test_both_declarations_require_current_successful_hook_acceptance(self):
        import copy
        sys.path.insert(0, str(ROOT / 'scripts/postgres-enrollment'))
        import completion_gate
        configmap = yaml.safe_load((PACKAGE / 'production/enrollment/enrollment-configmap.yaml').read_text())
        name = completion_gate.hook_name(configmap['data']['acceptance-generation'])
        application = {'metadata': {'name': 'postgres', 'namespace': 'argocd'}, 'status': {
            'sync': {'status': 'Synced', 'revisions': ['fixture-revision']}, 'health': {'status': 'Healthy'},
            'operationState': {'phase': 'Succeeded', 'operation': {'sync': {}},
                'syncResult': {'revisions': ['fixture-revision'], 'resources': [{
                    'group': 'batch', 'kind': 'Job', 'namespace': 'databases', 'name': name,
                    'hookType': 'Sync', 'hookPhase': 'Succeeded'}]}}}}
        for kind in ('main', 'log'):
            identity = {'id': 'prowlarr-' + kind, 'database': 'prowlarr_' + kind, 'role': 'prowlarr_' + kind}
            self.assertTrue(completion_gate.accepted(configmap, application, identity))
            failed = copy.deepcopy(application)
            failed['status']['operationState']['syncResult']['resources'][0]['hookPhase'] = 'Failed'
            self.assertFalse(completion_gate.accepted(configmap, failed, identity))
            stale = copy.deepcopy(configmap)
            stale['data']['encrypted-inputs-sha256'] = 'fixture-new-input'
            self.assertFalse(completion_gate.accepted(stale, application, identity))


@unittest.skipUnless(os.environ.get('PROWLARR_SQL_TEST'), 'Synthetic Docker PG18 test enabled in qualification/CI')
class NativeDatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.name = 'prowlarr-retained-check-' + uuid.uuid4().hex[:12]
        image = yaml.safe_load((ROOT / 'scripts/postgres-enrollment/job.yaml').read_text())['spec']['template']['spec']['containers'][0]['image']
        cls.command(['docker', 'run', '-d', '--name', cls.name, '--network', 'none',
                 '--memory', '256m', '--cpus', '1', '--pids-limit', '128',
                 '--tmpfs', '/var/lib/postgresql:rw,size=128m', '-e', 'PGDATA=/var/lib/postgresql/data',
                 '-e', 'POSTGRES_PASSWORD=fixture-admin-only',
                 '-e', 'POSTGRES_INITDB_ARGS=--auth-host=scram-sha-256 --auth-local=trust',
                 '-v', str(PACKAGE / 'main.sql') + ':/retained-startup/main.sql:ro', image])
        cls.addClassCleanup(lambda: cls.command(['docker', 'rm', '-f', cls.name]))
        for _ in range(100):
            result = cls.command(['docker', 'exec', cls.name, 'pg_isready', '-h', '127.0.0.1', '-U', 'postgres'], check=False)
            if not result.returncode:
                break
            time.sleep(0.2)
        else:
            raise AssertionError('Synthetic PG18 not ready')
        cls.sql("CREATE ROLE prowlarr_main LOGIN PASSWORD 'fixture-password'; CREATE ROLE prowlarr_log LOGIN PASSWORD 'fixture-password';")
        for kind in ('main', 'log'):
            cls.sql(f'CREATE DATABASE prowlarr_{kind} OWNER prowlarr_{kind};')
        cls.command(['docker', 'exec', cls.name, 'sh', '-ec',
                 'mkdir /credentials; printf fixture-password > /credentials/password'])

    @staticmethod
    def command(args, data=None, check=True):
        result = subprocess.run(args, input=data, capture_output=True, text=True, timeout=45)
        if check and result.returncode:
            raise AssertionError('Synthetic database fixture failed; private output suppressed')
        return result

    @classmethod
    def sql(cls, query, database='postgres'):
        return cls.command(['docker', 'exec', '-i', cls.name, 'psql', '-XqAt', '-v', 'ON_ERROR_STOP=1',
                        '-U', 'postgres', '-d', database], query)

    def gate(self, kind='main'):
        values = yaml.safe_load((PACKAGE / 'production/values.yaml').read_text())
        command = values['controllers']['main']['initContainers']['database-' + kind]['command']
        return self.command(['docker', 'exec', '-e', 'PGHOST=127.0.0.1', '-e', 'PGPORT=5432',
            '-e', 'PGUSER=prowlarr_' + kind, '-e', 'PGDATABASE=prowlarr_' + kind,
            '-e', 'PGCONNECT_TIMEOUT=10', self.name, *command], check=False)

    def test_empty_main_is_rejected_then_populated_schema_is_accepted_read_only(self):
        self.assertNotEqual(self.gate().returncode, 0)
        names = (
            'AppSyncProfiles', 'ApplicationIndexerMapping', 'ApplicationStatus', 'Applications', 'Commands',
            'Config', 'CustomFilters', 'DownloadClientStatus', 'DownloadClients', 'History',
            'IndexerDefinitionVersions', 'IndexerProxies', 'IndexerStatus', 'Indexers', 'NotificationStatus',
            'Notifications', 'ScheduledTasks', 'Tags', 'Users')
        # Create synthetic table shapes only; no private application data enters Docker.
        self.sql(''.join(f'CREATE TABLE "{name}" ("ID" integer); ALTER TABLE "{name}" OWNER TO prowlarr_main;' for name in names)
                 + 'CREATE TABLE "VersionInfo" ("Version" bigint); ALTER TABLE "VersionInfo" OWNER TO prowlarr_main;'
                 + 'INSERT INTO "VersionInfo" VALUES (44);', 'prowlarr_main')
        self.assertNotEqual(self.gate().returncode, 0, 'Empty Users/Config accepted')
        self.sql('INSERT INTO "Users" VALUES (1); INSERT INTO "Config" VALUES (1);', 'prowlarr_main')
        before = self.sql('SELECT count(*) FROM "Users"; SELECT count(*) FROM "Config";', 'prowlarr_main').stdout
        self.assertEqual(self.gate().returncode, 0)
        self.assertEqual(before, self.sql('SELECT count(*) FROM "Users"; SELECT count(*) FROM "Config";', 'prowlarr_main').stdout)
        self.sql('UPDATE "VersionInfo" SET "Version"=43;', 'prowlarr_main')
        self.assertNotEqual(self.gate().returncode, 0, 'Old main schema accepted')

    def test_log_login_rejects_wrong_password(self):
        self.assertEqual(self.gate('log').returncode, 0)
        self.command(['docker', 'exec', self.name, 'sh', '-ec', 'printf wrong-fixture-password > /credentials/password'])
        try:
            self.assertNotEqual(self.gate('log').returncode, 0)
            self.assertNotEqual(self.gate('main').returncode, 0)
        finally:
            self.command(['docker', 'exec', self.name, 'sh', '-ec', 'printf fixture-password > /credentials/password'])


class RenderTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('PROWLARR_RETAINED_RENDER'), 'Actual layered Helm render required for qualification')
    def test_mounts_dual_acceptance_and_writer_fencing(self):
        objects = [x for x in yaml.safe_load_all(Path(os.environ['PROWLARR_RETAINED_RENDER']).read_text()) if x]
        deployment = next(x for x in objects if x['kind'] == 'Deployment')
        pod = deployment['spec']['template']['spec']
        self.assertEqual(deployment['spec']['replicas'], 1)
        self.assertEqual(deployment['spec']['strategy']['type'], 'Recreate')
        self.assertEqual(pod['nodeSelector'], {'node-role.kubernetes.io/worker': 'true'})
        self.assertNotIn('fsGroup', pod.get('securityContext') or {})
        self.assertFalse(pod['automountServiceAccountToken'])
        inits = pod['initContainers']
        self.assertEqual([c['name'] for c in inits], ['retained-state', 'enrollment-main', 'database-main', 'enrollment-log', 'database-log'])
        volumes = {x['name']: x for x in pod['volumes']}
        for container in [*inits, *pod['containers']]:
            mounts = {x['mountPath']: x for x in container.get('volumeMounts', [])}
            name = container['name']
            if name.startswith('enrollment-'):
                kind = name.removeprefix('enrollment-')
                self.assertEqual(container['args'], ['--id', 'prowlarr-' + kind, '--database', 'prowlarr_' + kind, '--role', 'prowlarr_' + kind])
                self.assertIn('/gate-api', mounts)
                self.assertTrue(all(x['readOnly'] for x in mounts.values()))
            else:
                self.assertNotIn('/gate-api', mounts)
            if name.startswith('database-'):
                kind = name.removeprefix('database-')
                source = volumes[mounts['/credentials']['name']]['secret']
                self.assertEqual(source['secretName'], 'prowlarr-postgres-secret')
                self.assertEqual(source['items'], [{'key': kind + '-password', 'path': 'password'}])
                self.assertTrue(mounts['/credentials']['readOnly'])
                if kind == 'main':
                    self.assertIn('/retained-startup/main.sql', ' '.join(container['command']))
            if name == 'retained-state':
                self.assertTrue(mounts['/config']['readOnly'])
                self.assertTrue(mounts['/retained-startup']['readOnly'])
                self.assertTrue(mounts['/retained-credentials']['readOnly'])
            if name == 'main':
                self.assertEqual(set(mounts), {'/config'})
                self.assertEqual(volumes[mounts['/config']['name']]['persistentVolumeClaim']['claimName'], 'prowlarr-config-block')
                expected = yaml.safe_load((ROOT / 'services/media/prowlarr/values.yaml').read_text())['controllers']['main']['containers']['main']['image']
                self.assertEqual(container['image'], expected['repository'] + ':' + expected['tag'])
                self.assertEqual(container['readinessProbe']['httpGet']['path'], '/ping')
                self.assertEqual(container['readinessProbe']['httpGet']['httpHeaders'], [{'name': 'Host', 'value': 'localhost'}])
        self.assertFalse(any(x['kind'] == 'PersistentVolumeClaim' for x in objects))


if __name__ == '__main__':
    unittest.main()
