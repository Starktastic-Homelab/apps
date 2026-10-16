"""pgAdmin retained identity, completion integration and actual Helm rendering checks."""
import importlib.util
import os
import json
import subprocess
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'scripts/pgadmin-postgresql'


def load(name):
    spec = importlib.util.spec_from_file_location('pgadmin_' + name, PACKAGE / (name + '.py'))
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
        for name in ('storage', 'sessions', 'azurecredentialcache'):
            (self.root / name).mkdir()
        (self.root / '.homelab-pgadmin-data').write_text('homelab/pgadmin/data/v1\n')
        self.credentials = self.root.parent / 'credentials'
        self.credentials.mkdir()
        (self.credentials / 'password').write_text('fixture-only')
        (self.credentials / 'uri').write_text(repr('postgresql://pgadmin:fixture-only@postgres-postgresql.databases:5432/pgadmin'))
        self.env = {'PGADMIN_CONFIG_CONFIG_DATABASE_URI_FILE': '/etc/pgadmin-postgres/uri',
                    'PGADMIN_CONFIG_SQLALCHEMY_ENGINE_OPTIONS': "{'pool_size': 2, 'max_overflow': 1, 'pool_recycle': 300, 'pool_pre_ping': True}"}

    def test_retained_identity_and_credential_accepted_without_writes(self):
        before = {p: p.read_bytes() for p in self.root.parent.rglob('*') if p.is_file()}
        self.guard.validate(self.root, self.credentials, self.env)
        self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_wrong_missing_and_linked_identity_refused(self):
        marker = self.root / '.homelab-pgadmin-data'
        for value in ('', 'homelab/other/data/v1\n', 'x' * 129):
            marker.write_text(value)
            with self.assertRaises(ValueError): self.guard.validate(self.root, self.credentials, self.env)
        marker.unlink()
        with self.assertRaises(ValueError): self.guard.validate(self.root, self.credentials, self.env)
        marker.symlink_to(self.credentials / 'password')
        with self.assertRaises(ValueError): self.guard.validate(self.root, self.credentials, self.env)

    def test_sqlite_fallback_and_missing_private_directory_refused(self):
        for suffix in ('', '-wal', '-shm', '-journal'):
            path = self.root / ('pgadmin4.db' + suffix)
            path.symlink_to('absent')
            with self.assertRaises(ValueError): self.guard.validate(self.root, self.credentials, self.env)
            path.unlink()
        (self.root / 'storage').rmdir()
        with self.assertRaises(ValueError): self.guard.validate(self.root, self.credentials, self.env)

    def test_uri_credential_mismatch_and_sqlite_fallback_refused(self):
        uri = self.credentials / 'uri'
        for value in ("'sqlite:////var/lib/pgadmin/pgadmin4.db'", "'postgresql://pgadmin:wrong@postgres-postgresql.databases:5432/pgadmin'", "__import__('os').getcwd()", "'postgresql://pgadmin:fixture-only@wrong:5432/pgadmin'"):
            uri.write_text(value)
            with self.assertRaises(ValueError): self.guard.validate(self.root,self.credentials,self.env)

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
        for key in ('PGADMIN_CONFIG_CONFIG_DATABASE_URI', 'PGADMIN_CUSTOM_CONFIG_DISTRO_FILE', 'PGADMIN_CONFIG_SQLALCHEMY_DATABASE_URI', 'PGADMIN_CONFIG_SQLITE_PATH'):
            with self.assertRaises(ValueError): self.guard.validate(self.root, self.credentials, dict(self.env, **{key: 'conflict'}))


class SourceTests(unittest.TestCase):
    def test_scoped_completion_and_stock_uri_file(self):
        resources, values = load('prepare').build_sources()
        self.assertEqual(sum(r['kind'] == 'ServiceAccount' for r in resources), 1)
        account = next(r for r in resources if r['kind'] == 'ServiceAccount')
        self.assertEqual(account['metadata']['name'], 'pgadmin-postgres-completion')
        self.assertFalse(account['automountServiceAccountToken'])
        for binding in (r for r in resources if r['kind'] == 'RoleBinding'):
            self.assertEqual(binding['subjects'], [{'kind':'ServiceAccount', 'name':'pgadmin-postgres-completion', 'namespace':'databases'}])
        self.assertEqual(values['strategy'], {'type':'Recreate'})
        self.assertEqual(values['persistentVolume']['existingClaim'], 'pgadmin-data-block')
        self.assertIsNone(values['securityContext']['fsGroup'])
        self.assertFalse(values['VolumePermissions']['enabled'])
        import yaml
        inits = yaml.safe_load(values['extraInitContainers'])
        self.assertEqual([i['name'] for i in inits], ['pgadmin-retained-state', 'postgres-enrollment-acceptance', 'postgres-canonical-login'])
        env = {e['name']: e for e in values['envVarsExtra']}
        self.assertEqual(env['PGADMIN_CONFIG_CONFIG_DATABASE_URI_FILE']['value'], '/etc/pgadmin-postgres/uri')
        self.assertNotIn('PGADMIN_CONFIG_CONFIG_DATABASE_URI', env)
        self.assertEqual(env['PGADMIN_CONFIG_AUTHENTICATION_SOURCES']['value'], "['webserver', 'internal']")
        self.assertEqual(env['PGADMIN_CONFIG_SQLALCHEMY_ENGINE_OPTIONS']['value'], "{'pool_size': 2, 'max_overflow': 1, 'pool_recycle': 300, 'pool_pre_ping': True}")

    @unittest.skipUnless(os.environ.get('PGADMIN_RETAINED_RENDER'), 'actual Helm render supplied by CI')
    def test_actual_render_guards_precede_unchanged_stock_authentication(self):
        import yaml
        objects = [o for o in yaml.safe_load_all(Path(os.environ['PGADMIN_RETAINED_RENDER']).read_text()) if o]
        d = next(o for o in objects if o['kind'] == 'Deployment')
        self.assertEqual(d['spec']['strategy'], {'type':'Recreate'})
        p = d['spec']['template']['spec']
        self.assertEqual(p['serviceAccountName'], 'pgadmin-postgres-completion')
        self.assertFalse(p['automountServiceAccountToken'])
        self.assertNotIn('fsGroup', p['securityContext'])
        self.assertEqual([i['name'] for i in p['initContainers']], ['pgadmin-retained-state', 'postgres-enrollment-acceptance', 'postgres-canonical-login'])
        main = p['containers'][0]
        self.assertTrue(main['image'].endswith('@sha256:c332c5f6dfba995d9ebc4af261d93506d6876085d712eaaa3defc8dd1a3f26de'))
        env = {v['name']: v for v in main['env']}
        self.assertEqual(env['PGADMIN_DEFAULT_PASSWORD']['valueFrom']['secretKeyRef'], {'name':'pgadmin-secret', 'key':'password'})
        self.assertEqual(env['PGADMIN_CONFIG_CONFIG_DATABASE_URI_FILE']['value'], '/etc/pgadmin-postgres/uri')
        self.assertEqual(next(v for v in p['volumes'] if v['name']=='pgadmin-data')['persistentVolumeClaim']['claimName'], 'pgadmin-data-block')


@unittest.skipUnless(os.environ.get('PGADMIN_SQL_CONTAINER'), 'explicit isolated native PostgreSQL fixture required')
class SQLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.container = os.environ['PGADMIN_SQL_CONTAINER']
        obj = json.loads(subprocess.check_output(['docker','inspect',cls.container]))[0]
        assert obj['Config']['Labels']['homelab.operation'] == 'pgadmin-qualification-20261016'
        assert not obj['HostConfig']['PortBindings']
        cls.argv = ['docker','exec','-i',cls.container,'psql','-XqAt','-v','ON_ERROR_STOP=1','-Upostgres','-dpgadminreal']
        identifier = subprocess.run(cls.argv, input='SELECT system_identifier::text FROM pg_control_system();', capture_output=True, text=True, check=True).stdout.strip()
        cls.original = (PACKAGE/'main.sql').read_text().replace("current_database() <> 'pgadmin'", "current_database() <> 'pgadminreal'").replace("'pgadmin'", "'pgadmin_real'")
        cls.guard = cls.original.replace('7584099661242523698', identifier)

    def execute(self, sql):
        return subprocess.run(self.argv, input=sql, text=True, capture_output=True, timeout=30)

    def test_valid_stock_contract_and_wrong_physical_identity(self):
        rejected = self.execute('SET ROLE pgadmin_real;'+self.original)
        self.assertNotEqual(rejected.returncode,0)
        self.assertIn('physical database identity rejected',rejected.stderr)
        result = self.execute('SET ROLE pgadmin_real;'+self.guard)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_native_schema_markers_keys_and_administrator_losses_are_rejected(self):
        body = self.guard.replace('BEGIN READ ONLY;', '').replace('COMMIT;', '')
        changes = [
            'ALTER TABLE public.server RENAME COLUMN password TO lost_password;',
            "DO $case$ DECLARE n text; BEGIN SELECT indexname INTO n FROM pg_indexes WHERE schemaname='public' AND indexname NOT IN (SELECT conname FROM pg_constraint) LIMIT 1; EXECUTE format('DROP INDEX public.%I',n); END $case$;",
            "DO $case$ DECLARE n text; BEGIN SELECT conname INTO n FROM pg_constraint WHERE conrelid='public.server'::regclass AND contype='f' LIMIT 1; EXECUTE format('ALTER TABLE public.server DROP CONSTRAINT %I',n); END $case$;",
            'DELETE FROM public.keys;',
            "UPDATE public.keys SET value='wrong' WHERE name=(SELECT min(name) FROM public.keys);",
            'DELETE FROM public.alembic_version;',
            'UPDATE public.version SET value=51;',
            'UPDATE public."user" SET active=false;',
            'DELETE FROM public.roles_users;',
        ]
        for change in changes:
            with self.subTest(change=change.split()[:3]):
                result=self.execute('BEGIN;'+change+'SET LOCAL ROLE pgadmin_real;'+body+'ROLLBACK;')
                self.assertNotEqual(result.returncode,0)
                self.assertTrue(any(s in result.stderr for s in ('stock schema contract rejected','initialized state rejected')),result.stderr)
                self.assertEqual(self.execute('SET ROLE pgadmin_real;'+self.guard).returncode,0)


if __name__ == '__main__':
    unittest.main()
