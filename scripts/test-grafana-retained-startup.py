"""Grafana retained identity, completion integration and actual Helm rendering checks."""
import importlib.util
import os
import json
import subprocess
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'scripts/grafana-postgresql'


def load(name):
    spec = importlib.util.spec_from_file_location('grafana_' + name, PACKAGE / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.guard = load('guard')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'data'
        self.root.mkdir()
        (self.root / 'plugins').mkdir()
        (self.root / '.homelab-grafana-data').write_text('homelab/grafana/data/v1\n')
        self.credentials = self.root.parent / 'credentials'
        self.credentials.mkdir()
        (self.credentials / 'password').write_text('fixture-only')
        self.env = {'GF_DATABASE_TYPE': 'postgres', 'GF_DATABASE_HOST': 'postgres-postgresql.databases:5432',
                    'GF_DATABASE_NAME': 'grafana', 'GF_DATABASE_USER': 'grafana', 'GF_DATABASE_PASSWORD': 'fixture-only'}

    def test_retained_identity_and_credential_accepted_without_writes(self):
        before = {p: p.read_bytes() for p in self.root.parent.rglob('*') if p.is_file()}
        self.guard.validate(self.root, self.credentials, self.env)
        self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_wrong_missing_and_linked_identity_refused(self):
        marker = self.root / '.homelab-grafana-data'
        for value in ('', 'homelab/other/data/v1\n', 'x' * 129):
            marker.write_text(value)
            with self.assertRaises(ValueError): self.guard.validate(self.root, self.credentials, self.env)
        marker.unlink()
        with self.assertRaises(ValueError): self.guard.validate(self.root, self.credentials, self.env)
        marker.symlink_to(self.credentials / 'password')
        with self.assertRaises(ValueError): self.guard.validate(self.root, self.credentials, self.env)

    def test_sqlite_fallback_and_missing_plugin_directory_refused(self):
        for suffix in ('', '-wal', '-shm', '-journal'):
            path = self.root / ('grafana.db' + suffix)
            path.symlink_to('absent')
            with self.assertRaises(ValueError): self.guard.validate(self.root, self.credentials, self.env)
            path.unlink()
        (self.root / 'plugins').rmdir()
        with self.assertRaises(ValueError): self.guard.validate(self.root, self.credentials, self.env)

    def test_projected_credentials_allowed_but_escape_refused(self):
        path = self.credentials / 'password'
        version = self.credentials / '..version'
        version.mkdir()
        path.rename(version / 'password')
        (self.credentials / '..data').symlink_to(version.name, target_is_directory=True)
        path.symlink_to('..data/password')
        self.guard.validate(self.root, self.credentials, self.env)
        path.unlink()
        outside = self.root.parent / 'outside'
        outside.write_text('fixture-only')
        path.symlink_to(outside)
        with self.assertRaises(ValueError): self.guard.validate(self.root, self.credentials, self.env)

    def test_wrong_database_or_competing_configuration_refused(self):
        for key in self.env:
            with self.assertRaises(ValueError): self.guard.validate(self.root, self.credentials, dict(self.env, **{key: 'wrong'}))
        for key in ('GF_DATABASE_URL', 'GF_DATABASE_PATH', 'GF_DATABASE_PASSWORD__FILE'):
            with self.assertRaises(ValueError): self.guard.validate(self.root, self.credentials, dict(self.env, **{key: 'conflict'}))


class SourceTests(unittest.TestCase):
    def test_completion_uses_existing_sidecar_service_account(self):
        resources, values = load('prepare').build_sources()
        g = values['grafana']
        self.assertFalse(any(r['kind'] == 'ServiceAccount' for r in resources))
        bindings = [r for r in resources if r['kind'] == 'RoleBinding']
        self.assertEqual({b['metadata']['namespace'] for b in bindings}, {'databases', 'argocd'})
        self.assertTrue(all(b['subjects'] == [{'kind': 'ServiceAccount', 'name': 'kube-prometheus-stack-grafana', 'namespace': 'monitoring'}] for b in bindings))
        self.assertEqual(g['deploymentStrategy'], {'type': 'Recreate'})
        self.assertEqual(g['persistence']['existingClaim'], 'grafana-data-block')
        self.assertEqual([i['name'] for i in g['extraInitContainers']], ['grafana-retained-state', 'postgres-enrollment-acceptance', 'postgres-canonical-login'])
        self.assertIsNone(g['securityContext']['fsGroup'])
        for kind, init in [('dashboards', 'initDashboards'), ('datasources', 'initDatasources')]:
            self.assertTrue(g['sidecar'][kind][init])
            self.assertEqual(g['sidecar'][kind]['restartPolicy'], 'Always')
            self.assertEqual(g['sidecar'][kind]['startupProbe']['httpGet']['path'], '/healthz')

    @unittest.skipUnless(os.environ.get('GRAFANA_RETAINED_RENDER'), 'actual Helm render supplied by CI')
    def test_actual_render_preserves_discovery_and_orders_guards_before_main(self):
        import yaml
        objects = list(yaml.safe_load_all(Path(os.environ['GRAFANA_RETAINED_RENDER']).read_text()))
        deployment = next(o for o in objects if o and o['kind'] == 'Deployment' and o['metadata']['name'] == 'kube-prometheus-stack-grafana')
        self.assertEqual(deployment['spec']['strategy'], {'type': 'Recreate'})
        pod = deployment['spec']['template']['spec']
        self.assertEqual(pod['serviceAccountName'], 'kube-prometheus-stack-grafana')
        self.assertTrue(pod['automountServiceAccountToken'])
        self.assertNotIn('fsGroup', pod['securityContext'])
        inits = pod['initContainers']
        self.assertEqual([i['name'] for i in inits[-3:]], ['grafana-retained-state', 'postgres-enrollment-acceptance', 'postgres-canonical-login'])
        for i in inits[:-3]:
            self.assertEqual(i['restartPolicy'], 'Always')
            self.assertIn(i['name'], ('grafana-init-sc-dashboard', 'grafana-init-sc-datasources'))
        self.assertEqual(len(inits), 5)
        main = next(c for c in pod['containers'] if c['name'] == 'grafana')
        self.assertTrue(main['image'].endswith('@sha256:202e5d5b3f8499e70ccac7991eea6d7da72d2790eb2e0597e7987acf724e7180'))
        env = {v['name']: v for v in main['env']}
        self.assertEqual(env['GF_DATABASE_TYPE']['value'], 'postgres')
        self.assertEqual(env['GF_DATABASE_PASSWORD']['valueFrom']['secretKeyRef'], {'name': 'grafana-postgres-secret', 'key': 'password'})
        self.assertEqual(main['envFrom'], [{'secretRef': {'name': 'grafana-oidc-secret'}}])
        storage = next(v for v in pod['volumes'] if v['name'] == 'storage')
        self.assertEqual(storage['persistentVolumeClaim']['claimName'], 'grafana-data-block')



@unittest.skipUnless(os.environ.get('GRAFANA_SQL_CONTAINER'), 'explicit isolated PostgreSQL fixture required')
class SQLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.container = os.environ['GRAFANA_SQL_CONTAINER']
        obj = json.loads(subprocess.check_output(['docker', 'inspect', cls.container]))[0]
        assert obj['Config']['Labels']['homelab.operation'] == 'grafana-qualification-20261016'
        assert not obj['HostConfig']['PortBindings']
        cls.argv = ['docker', 'exec', '-i', '-e', 'PGPASSWORD=fixture-only', cls.container,
                    '/opt/bitnami/postgresql/bin/psql', '-XqAtw', '-v', 'ON_ERROR_STOP=1',
                    '-h127.0.0.1', '-Ugrafana', '-dgrafana']
        reply = subprocess.run(cls.argv, input='SELECT system_identifier::text FROM pg_control_system();', text=True, capture_output=True, check=True)
        cls.original = (PACKAGE / 'main.sql').read_text()
        cls.guard = cls.original.replace('7584099661242523698', reply.stdout.strip())

    def execute(self, text):
        return subprocess.run(self.argv, input=text, text=True, capture_output=True, timeout=30)

    def test_valid_populated_stock_contract_accepted_and_wrong_physical_id_refused(self):
        rejected = self.execute(self.original)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn('physical database identity rejected', rejected.stderr)
        self.assertEqual(self.execute(self.guard).returncode, 0)

    @unittest.skipUnless(os.environ.get('GRAFANA_SECOND_SQL_CONTAINER'), 'independent stock generation supplied locally')
    def test_independent_stock_generation_and_real_app_startup_accepted(self):
        other = os.environ['GRAFANA_SECOND_SQL_CONTAINER']
        obj = json.loads(subprocess.check_output(['docker', 'inspect', other]))[0]
        self.assertEqual(obj['Config']['Labels']['homelab.operation'], 'grafana-qualification-20261016')
        argv = [other if value == self.container else value for value in self.argv]
        identifier = subprocess.run(argv, input='SELECT system_identifier::text FROM pg_control_system();', text=True, capture_output=True, check=True).stdout.strip()
        result = subprocess.run(argv, input=self.original.replace('7584099661242523698', identifier), text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, 'A separately initialized stock schema must remain usable after real-copy startup')

    def test_native_schema_and_retained_state_losses_refused(self):
        body = self.guard.replace('BEGIN READ ONLY;', '').replace('COMMIT;', '')
        changes = [
            'ALTER TABLE public.resource RENAME COLUMN value TO lost_value;',
            "DO $case$ DECLARE n text; BEGIN SELECT indexname INTO n FROM pg_indexes WHERE schemaname='public' AND indexname NOT IN (SELECT conname FROM pg_constraint) LIMIT 1; EXECUTE format('DROP INDEX public.%I', n); END $case$;",
            "DO $case$ DECLARE n text; BEGIN SELECT conname INTO n FROM pg_constraint WHERE conrelid='public.resource'::regclass LIMIT 1; EXECUTE format('ALTER TABLE public.resource DROP CONSTRAINT %I', n); END $case$;",
            'DELETE FROM public.resource_history;',
            'DELETE FROM public.migration_log;',
            'DELETE FROM public.migration_log WHERE id=(SELECT min(id) FROM public.migration_log);',
            'DELETE FROM public.resource_migration_log;',
            'DELETE FROM public.secret_migration_log;',
            'DELETE FROM public.unifiedstorage_migration_log;',
            'DELETE FROM public.data_keys;',
            'UPDATE public."user" SET is_disabled=true;',
            "UPDATE public.migration_log SET success=false WHERE id=(SELECT min(id) FROM public.migration_log);",
        ]
        for change in changes:
            with self.subTest(change=change.split()[0:3]):
                rejected = self.execute('BEGIN;'+change+body+'ROLLBACK;')
                self.assertNotEqual(rejected.returncode, 0)
                self.assertTrue(any(message in rejected.stderr for message in ('stock schema contract rejected', 'initialized state rejected')), 'Mutation must reach the guard rejection')
                self.assertEqual(self.execute(self.guard).returncode, 0)


if __name__ == '__main__':
    unittest.main()
