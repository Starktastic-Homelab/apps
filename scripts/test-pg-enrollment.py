#!/usr/bin/env python3
"""Actual native PostgreSQL enrollment qualification; synthetic local Docker only."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'scripts/postgres-enrollment'
CLIENT = 'postgres:18.6-alpine@sha256:6c538e7206ea40ff740ef27883529390a690b6ead6ba96b44c67a9f7c638e8fd'
SERVER = 'registry-1.docker.io/bitnami/postgresql:latest@sha256:b74b23f091dcc87041bcae557d840c36458af46b955279cb13aedec4c32d7f71'


def docker(*args, **kwargs):
    return subprocess.run(['docker', *args], capture_output=True, text=True, **kwargs)


class EnrollmentTests(unittest.TestCase):
    def setUp(self):
        self.prefix = 'pg-enrollment-' + secrets.token_hex(6)
        self.tmp = tempfile.TemporaryDirectory(prefix=self.prefix)
        self.root = Path(self.tmp.name)
        self.root.chmod(0o755)
        self.clients = []
        self.addCleanup(self.cleanup)
        self.admin = 'synthetic-admin-' + secrets.token_hex(20)
        self.password = " synthetic 'quote' \\ dollar$ tick` UTF8-é "
        for sub in ('config', 'admin', 'apps'):
            (self.root / sub).mkdir(mode=0o755)
        (self.root / 'admin/postgres-password').write_text(self.admin)
        (self.root / 'apps/alpha-password').write_text(self.password)
        for p in self.root.glob('*/*'):
            p.chmod(0o444)
        self.network = self.prefix + '-net'
        self.volume = self.prefix + '-data'
        self.server = self.prefix + '-server'
        self.assertEqual(docker('network', 'create', '--internal', self.network).returncode, 0)
        self.assertEqual(docker('volume', 'create', self.volume).returncode, 0)
        env = self.root / 'server.env'
        env.write_text('POSTGRESQL_PASSWORD=' + self.admin + '\nPOSTGRESQL_DATABASE=postgres\n')
        env.chmod(0o600)
        result = docker('run', '-d', '--name', self.server, '--network', self.network,
                        '--network-alias', 'server', '--memory', '1g', '--cpus', '1',
                        '--log-opt', 'max-size=5m', '--log-opt', 'max-file=2',
                        '--env-file', str(env), '-v', self.volume + ':/bitnami/postgresql', SERVER)
        self.assertEqual(result.returncode, 0, 'Cannot start isolated server')
        for _ in range(120):
            if docker('exec', self.server, 'pg_isready', '-h', '127.0.0.1', '-U', 'postgres').returncode == 0:
                break
            time.sleep(0.25)
        else:
            self.fail('Isolated server not ready')
        probe = docker('run', '--rm', '--network', self.network, '--memory', '128m', '--cpus', '0.5',
                       '--log-opt', 'max-size=5m', '--log-opt', 'max-file=2',
                       '--entrypoint', '/bin/sh', CLIENT, '-c',
                       'n=0; until pg_isready -h server -U postgres >/dev/null 2>&1; do n=$((n+1)); [ $n -lt 120 ] || exit 1; sleep 0.25; done')
        self.assertEqual(probe.returncode, 0, 'Server network readiness failed')
        self.system_id = self.sql('SELECT system_identifier FROM pg_control_system()').strip()
        self.config = {'version': 1, 'expectedSystemIdentifier': self.system_id,
                       'entries': [self.entry('alpha')]}

    def cleanup(self):
        for name in self.clients:
            docker('rm', '-f', name)
        if hasattr(self, 'server'):
            size = docker('exec', self.server, 'du', '-sk', '/bitnami/postgresql')
            if size.returncode == 0:
                assert int(size.stdout.split()[0]) < 1024 * 1024, 'Lab data cap exceeded'
            docker('rm', '-f', self.server)
            docker('volume', 'rm', self.volume)
            docker('network', 'rm', self.network)
        self.tmp.cleanup()

    @staticmethod
    def entry(name, mode='new'):
        return {'id': name, 'database': name, 'role': name, 'mode': mode,
                'passwordKey': name + '-password'}

    def sql(self, sql, database='postgres'):
        result = docker('exec', '-i', self.server, '/bin/sh', '-c',
                        'export PGPASSWORD="$POSTGRESQL_PASSWORD"; exec psql -XAt -U postgres -v ON_ERROR_STOP=1 -d "$1"',
                        'fixture', database, input=sql)
        self.assertEqual(result.returncode, 0, 'Private fixture SQL failed: ' + result.stderr.replace(self.admin, '[redacted]'))
        return result.stdout

    def client(self, command, *, runtime=None, asynchronous=False):
        if (self.root / 'config/config.json').exists():
            (self.root / 'config/config.json').chmod(0o644)
        (self.root / 'config/config.json').write_text(json.dumps(self.config))
        (self.root / 'config/config.json').chmod(0o444)
        name = self.prefix + '-client-' + str(len(self.clients))
        self.clients.append(name)
        args = ['run', '--name', name, '--network', self.network, '--memory', '128m',
                '--cpus', '0.5', '--log-opt', 'max-size=5m', '--log-opt', 'max-file=2',
                '--user', '1001:1001', '--read-only', '--cap-drop', 'ALL',
                '--security-opt', 'no-new-privileges', '--tmpfs', '/tmp:rw,noexec,nosuid,size=16m',
                '-e', 'PGHOST=server', '-e', 'PGPORT=5432', '-e', 'PGUSER=postgres',
                '-e', 'PGDATABASE=postgres', '-e', 'PGAPPNAME=homelab-enrollment', '-v', str(self.root / 'config') + ':/config:ro',
                '-v', str(self.root / 'admin') + ':/credentials/admin:ro',
                '-v', str(self.root / 'apps') + ':/credentials/apps:ro',
                '-v', str(runtime or SOURCE / 'runtime') + ':/scripts:ro',
                '--entrypoint', '/bin/sh', CLIENT, '-c', command]
        if asynchronous:
            return subprocess.Popen(['docker', *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        result = docker(*args, timeout=100)
        self.assertNotIn(self.password, result.stdout + result.stderr, 'Credential leaked')
        self.assertNotIn(self.admin, result.stdout + result.stderr, 'Admin credential leaked')
        return result

    def bootstrap(self):
        result = self.client('PGPASSWORD=$(cat /credentials/admin/postgres-password); export PGPASSWORD; psql -Xq -v ON_ERROR_STOP=1 -v expected="$(cat /config/config.json | sed -n \'s/.*"expectedSystemIdentifier": "\\([0-9]*\\)".*/\\1/p\')" -f /scripts/bootstrap.sql')
        self.assertEqual(result.returncode, 0, 'Explicit bootstrap failed: ' + result.stderr)

    def run_enrollment(self, ok=True, runtime=None):
        result = self.client('/bin/sh /scripts/enroll.sh run', runtime=runtime)
        if ok:
            self.assertEqual(result.returncode, 0, 'Enrollment did not complete: ' + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, 'Enrollment unexpectedly accepted unsafe state')
        return result

    def snapshot(self):
        # Never use assertEqual on this: its diff could disclose the synthetic verifier.
        return self.sql("SELECT d.oid,r.oid,r.rolpassword,d.datdba FROM pg_database d JOIN pg_authid r ON r.rolname='alpha' WHERE d.datname='alpha'")

    def test_new_enrollment_then_repeat_preserves_identity_and_data(self):
        # Break caught: recreating an enrolled object or resetting its password on retry.
        self.assertTrue((SOURCE / 'runtime/bootstrap.sql').is_file(), 'Native lifecycle is missing')
        self.bootstrap()
        self.run_enrollment()
        self.assertEqual(self.sql("SELECT phase FROM homelab_enrollment.enrollments WHERE id='alpha'").strip(), 'ready')
        self.assertEqual(self.sql("SELECT rolcanlogin FROM pg_roles WHERE rolname='alpha'").strip(), 't')
        self.sql('CREATE TABLE sentinel(value text); INSERT INTO sentinel VALUES (\'committed\');', 'alpha')
        before = self.snapshot()
        self.run_enrollment()
        self.assertTrue(before == self.snapshot(), 'Established identity/credential changed')
        self.assertEqual(self.sql('SELECT value FROM sentinel', 'alpha').strip(), 'committed')
        self.assertEqual(self.sql('SELECT system_identifier FROM pg_control_system()').strip(), self.system_id)
        logs = docker('logs', self.server)
        self.assertNotIn(self.password, logs.stdout + logs.stderr, 'Server log leaked credential')

    def app_query(self, sql, database='alpha'):
        # Copy SQL into mounted config; synthetic credential stays in its projected file.
        target = self.root / 'config/query.sql'
        if target.exists():
            target.chmod(0o644)
        target.write_text(sql)
        target.chmod(0o444)
        return self.client('PGPASSWORD=$(cat /credentials/apps/alpha-password); export PGPASSWORD; '
                           'psql -XqAt -U alpha -d ' + database + ' -v ON_ERROR_STOP=1 -f /config/query.sql')

    def test_registry_identity_and_child_failure_are_fail_closed(self):
        # Break caught: any bootstrap/repair inference from missing or corrupt metadata.
        self.run_enrollment(ok=False)
        self.assertEqual(self.sql("SELECT count(*) FROM pg_roles WHERE rolname='alpha'").strip(), '0')
        self.bootstrap()
        original = self.config['expectedSystemIdentifier']
        for identity in ('1', '', None):
            self.config['expectedSystemIdentifier'] = identity
            self.run_enrollment(ok=False)
        self.config['expectedSystemIdentifier'] = original
        self.sql('CREATE ROLE registry_intruder NOLOGIN')
        changes = [
            ('ALTER SCHEMA homelab_enrollment OWNER TO registry_intruder',
             'ALTER SCHEMA homelab_enrollment OWNER TO postgres'),
            ('ALTER TABLE homelab_enrollment.enrollments OWNER TO registry_intruder',
             'ALTER TABLE homelab_enrollment.enrollments OWNER TO postgres'),
            ('GRANT USAGE ON SCHEMA homelab_enrollment TO PUBLIC',
             'REVOKE ALL ON SCHEMA homelab_enrollment FROM PUBLIC'),
            ('GRANT SELECT ON homelab_enrollment.enrollments TO PUBLIC',
             'REVOKE ALL ON homelab_enrollment.enrollments FROM PUBLIC'),
            ('ALTER TABLE homelab_enrollment.enrollments ADD COLUMN unexpected text',
             'ALTER TABLE homelab_enrollment.enrollments DROP COLUMN unexpected'),
        ]
        for change, undo in changes:
            with self.subTest(change=change):
                self.sql(change)
                self.run_enrollment(ok=False)
                self.assertEqual(self.sql("SELECT count(*) FROM pg_roles WHERE rolname='alpha'").strip(), '0')
                self.sql(undo)
        # A dropped attribute is intentionally incompatible; explicit fresh fixture bootstrap.
        self.sql('DROP SCHEMA homelab_enrollment CASCADE')
        self.bootstrap()
        import shutil
        runtime = self.root / 'failed-runtime'
        shutil.copytree(SOURCE / 'runtime', runtime)
        (runtime / 'schema.sql').write_text('SELECT 1/0;')
        self.run_enrollment(ok=False, runtime=runtime)
        self.assertEqual(self.sql("SELECT phase FROM homelab_enrollment.enrollments").strip(), 'provisioning')
        self.assertEqual(self.sql("SELECT rolcanlogin FROM pg_roles WHERE rolname='alpha'").strip(), 'f')
        self.run_enrollment()
        self.config['entries'].append(self.entry('beta'))
        (self.root / 'apps/beta-password').write_text('synthetic-beta-password')
        (self.root / 'apps/beta-password').chmod(0o444)
        self.run_enrollment()
        self.assertNotEqual(self.app_query('SELECT * FROM homelab_enrollment.enrollments', 'postgres').returncode, 0)
        self.assertNotEqual(self.app_query('SELECT 1', 'beta').returncode, 0)
        self.sql('CREATE TABLE private_data(value text); INSERT INTO private_data VALUES (\'private\');', 'beta')
        # Even accidental CONNECT alone must not grant object access.
        self.sql('GRANT CONNECT ON DATABASE beta TO alpha')
        self.assertNotEqual(self.app_query('SELECT * FROM private_data', 'beta').returncode, 0)

    def set_password(self, key, value):
        p = self.root / 'apps' / key
        if p.exists():
            p.chmod(0o644)
        p.write_bytes(value.encode() if isinstance(value, str) else value)
        p.chmod(0o444)

    def catalog_snapshot(self):
        return self.snapshot() + self.sql("SELECT row_to_json(r) FROM pg_roles r WHERE rolname='alpha'") + self.sql(
            "SELECT datacl FROM pg_database WHERE datname='alpha'; SELECT roleid,member,admin_option,inherit_option,set_option FROM pg_auth_members ORDER BY roleid,member") + self.sql(
            "SELECT nspname,nspowner,nspacl FROM pg_namespace ORDER BY nspname; SELECT relname,relowner,relacl FROM pg_class WHERE relnamespace='public'::regnamespace ORDER BY relname; SELECT defaclrole,defaclnamespace,defaclobjtype,defaclacl FROM pg_default_acl ORDER BY oid; SELECT extname,extversion FROM pg_extension ORDER BY extname; SELECT * FROM sentinel", 'alpha')

    def test_adopt_and_remove_preserve_existing_database(self):
        # Break caught: adoption rewrites passwords, owners, memberships or legacy grants.
        self.bootstrap()
        self.run_enrollment()
        self.sql("DELETE FROM homelab_enrollment.enrollments; CREATE ROLE readers NOLOGIN; GRANT readers TO alpha; GRANT CONNECT ON DATABASE alpha TO PUBLIC")
        self.sql("CREATE EXTENSION pgcrypto; CREATE TABLE sentinel(value text); INSERT INTO sentinel VALUES ('legacy'); GRANT SELECT ON sentinel TO readers; ALTER DEFAULT PRIVILEGES FOR ROLE alpha GRANT SELECT ON TABLES TO readers", 'alpha')
        before = self.catalog_snapshot()
        self.config['entries'][0]['mode'] = 'adopt'
        self.run_enrollment()
        self.run_enrollment()
        self.config['entries'] = []
        self.run_enrollment()
        self.assertTrue(before == self.catalog_snapshot(), 'Adoption/removal changed legacy catalog or credential')
        self.assertEqual(self.sql("SELECT phase FROM homelab_enrollment.enrollments").strip(), 'ready')
        self.config['entries'] = [self.entry('alpha', 'adopt')]
        self.set_password('alpha-password', 'wrong-synthetic')
        self.run_enrollment(ok=False)
        self.set_password('alpha-password', self.password)
        for change, undo in [('ALTER DATABASE alpha OWNER TO postgres', 'ALTER DATABASE alpha OWNER TO alpha'),
                             ('ALTER ROLE alpha CREATEDB', 'ALTER ROLE alpha NOCREATEDB')]:
            self.sql(change)
            self.run_enrollment(ok=False)
            self.sql(undo)
        self.assertTrue(before == self.catalog_snapshot(), 'Rejected adoption modified legacy state')

    def test_conflicting_set_is_rejected_before_writes(self):
        # Break caught: one valid entry mutates before a later incompatible entry fails.
        import copy
        self.bootstrap()
        base = copy.deepcopy(self.config)
        invalid = []
        for field in ('id', 'database', 'role', 'passwordKey'):
            c = copy.deepcopy(base)
            second = self.entry('beta')
            second[field] = c['entries'][0][field]
            c['entries'].append(second)
            invalid.append(c)
        for field, value in [('role','postgres'), ('role','pg_shadow'), ('database','template1'),
                             ('database','A'), ('database','a'*64), ('passwordKey','../alpha'), ('id','bad\nname')]:
            c = copy.deepcopy(base)
            c['entries'][0][field] = value
            invalid.append(c)
        for c in invalid:
            self.config = c
            self.run_enrollment(ok=False)
            self.assertEqual(self.sql("SELECT count(*) FROM pg_roles WHERE rolname IN ('alpha','beta')").strip(), '0')
        self.config = base
        for value in (b'bad\npassword', b'bad\rpassword', b'bad\0password', b''):
            self.set_password('alpha-password', value)
            self.run_enrollment(ok=False)
            self.assertEqual(self.sql("SELECT count(*) FROM pg_roles WHERE rolname='alpha'").strip(), '0')
        self.set_password('alpha-password', self.password)
        self.run_enrollment()
        self.config['entries'] = [dict(self.entry('alpha'), id='renamed')]
        self.run_enrollment(ok=False)
        self.config['entries'] = [self.entry('beta'), dict(self.entry('alpha'), id='renamed')]
        self.set_password('beta-password', 'synthetic-beta')
        self.run_enrollment(ok=False)
        self.assertEqual(self.sql("SELECT count(*) FROM pg_roles WHERE rolname='beta'").strip(), '0')
        # Authentication preflight is also whole-set: valid beta cannot precede bad alpha.
        self.sql('DELETE FROM homelab_enrollment.enrollments')
        self.config['entries'] = [dict(self.entry('beta'), id='abeta'), dict(self.entry('alpha','adopt'), id='zalpha')]
        self.set_password('alpha-password', 'wrong-synthetic')
        self.run_enrollment(ok=False)
        self.assertEqual(self.sql("SELECT count(*) FROM pg_roles WHERE rolname='beta'").strip(), '0')

    def paused_runtime(self, boundary, schema=False):
        import hashlib
        import shutil
        path = self.root / ('pause-' + boundary)
        shutil.copytree(SOURCE / 'runtime', path)
        target = path / ('schema.sql' if schema else 'enroll.sql')
        source = target.read_text()
        pause = "SELECT pg_sleep(50) /* enrollment_test_pause */;\n"
        changed = source + pause if schema else source.replace('-- boundary: ' + boundary + '\n', '-- boundary: ' + boundary + '\n' + pause)
        self.assertTrue(changed.replace(pause, '') == source, 'Fault fixture changed more than adding pause')
        target.write_text(changed)
        # Public transformation evidence contains only hashes and boundary names.
        self.pause_hash = hashlib.sha256(source.encode()).hexdigest()
        return path

    def wait_pause(self):
        for _ in range(100):
            result = self.sql("SELECT pid FROM pg_stat_activity WHERE application_name='homelab-enrollment' AND query LIKE 'SELECT pg_sleep(50)%'").strip()
            if result:
                return int(result)
            time.sleep(0.1)
        self.fail('Native fault fixture never reached pause boundary')

    def test_interrupted_provisioning_resumes_exact_objects(self):
        # Break caught: a durable pending role/DB is taken over, replaced or enabled early.
        self.bootstrap()
        for boundary in ('before-role', 'after-role', 'after-password', 'after-database', 'after-schema', 'after-ready'):
            with self.subTest(boundary=boundary):
                runtime = self.paused_runtime(boundary)
                process = self.client('/bin/sh /scripts/enroll.sh run', runtime=runtime, asynchronous=True)
                pid = self.wait_pause()
                role_oid = self.sql("SELECT oid FROM pg_roles WHERE rolname='alpha'").strip()
                db_oid = self.sql("SELECT oid FROM pg_database WHERE datname='alpha'").strip()
                if boundary != 'after-ready' and role_oid:
                    self.assertEqual(self.sql("SELECT rolcanlogin FROM pg_roles WHERE rolname='alpha'").strip(), 'f')
                if boundary == 'after-ready':
                    self.sql("CREATE TABLE sentinel(value text); INSERT INTO sentinel VALUES ('latest-ack')", 'alpha')
                docker('kill', self.clients[-1])
                self.sql(f'SELECT pg_terminate_backend({pid})')
                process.communicate(timeout=10)
                self.run_enrollment()
                if role_oid:
                    self.assertEqual(self.sql("SELECT oid FROM pg_roles WHERE rolname='alpha'").strip(), role_oid)
                if db_oid:
                    self.assertEqual(self.sql("SELECT oid FROM pg_database WHERE datname='alpha'").strip(), db_oid)
                if boundary == 'after-ready':
                    self.assertEqual(self.sql('SELECT value FROM sentinel', 'alpha').strip(), 'latest-ack')
                self.sql('DROP DATABASE alpha; DROP ROLE alpha; DELETE FROM homelab_enrollment.enrollments')
        # Pending LOGIN tamper and missing recorded role are rejection, not repair.
        import shutil
        shutil.rmtree(self.root / 'pause-after-role')
        runtime = self.paused_runtime('after-role')
        process = self.client('/bin/sh /scripts/enroll.sh run', runtime=runtime, asynchronous=True)
        pid = self.wait_pause()
        docker('kill', self.clients[-1]); self.sql(f'SELECT pg_terminate_backend({pid})'); process.communicate(timeout=10)
        self.sql('ALTER ROLE alpha LOGIN')
        self.run_enrollment(ok=False)
        self.sql('ALTER ROLE alpha NOLOGIN; DROP ROLE alpha')
        self.run_enrollment(ok=False)
        self.assertEqual(self.sql("SELECT count(*) FROM pg_roles WHERE rolname='alpha'").strip(), '0')

    def test_ready_missing_or_changed_state_is_not_recreated(self):
        # Break caught: an established missing object is recreated empty.
        self.bootstrap(); self.run_enrollment()
        self.sql("UPDATE homelab_enrollment.enrollments SET database_name='other'")
        self.run_enrollment(ok=False)
        self.sql("UPDATE homelab_enrollment.enrollments SET database_name='alpha'; DROP DATABASE alpha")
        self.run_enrollment(ok=False)
        self.assertEqual(self.sql("SELECT count(*) FROM pg_database WHERE datname='alpha'").strip(), '0')
        self.sql('DROP ROLE alpha')
        self.run_enrollment(ok=False)
        self.assertEqual(self.sql("SELECT count(*) FROM pg_roles WHERE rolname='alpha'").strip(), '0')
        self.sql('DROP SCHEMA homelab_enrollment CASCADE')
        self.run_enrollment(ok=False)
        self.assertEqual(self.sql("SELECT count(*) FROM pg_namespace WHERE nspname='homelab_enrollment'").strip(), '0')

    def test_concurrent_clients_serialize_and_timeout(self):
        # Break caught: parent unlocks while the child is still granting schema rights.
        self.bootstrap()
        runtime = self.paused_runtime('schema', schema=True)
        first = self.client('/bin/sh /scripts/enroll.sh run', runtime=runtime, asynchronous=True)
        child_pid = self.wait_pause()
        self.assertEqual(self.sql("SELECT count(*) FROM pg_locks l JOIN pg_stat_activity a USING(pid) WHERE l.locktype='advisory' AND l.granted AND a.application_name='homelab-enrollment' AND a.datname='postgres'").strip(), '1')
        started = time.monotonic()
        second = self.client('/bin/sh /scripts/enroll.sh run', asynchronous=True)
        # Force the second client to exhaust the actual 30-second acquisition deadline.
        out, err = second.communicate(timeout=45)
        self.assertNotEqual(second.returncode, 0)
        self.assertTrue(29 <= time.monotonic() - started < 45, 'Lock wait was not bounded')
        self.sql(f'SELECT pg_terminate_backend({child_pid})')
        first.communicate(timeout=10)
        self.assertNotEqual(first.returncode, 0)
        self.run_enrollment()
        a = self.client('/bin/sh /scripts/enroll.sh run', asynchronous=True)
        b = self.client('/bin/sh /scripts/enroll.sh run', asynchronous=True)
        a.communicate(timeout=40); b.communicate(timeout=40)
        self.assertEqual(a.returncode, 0); self.assertEqual(b.returncode, 0)



class PreparationTests(unittest.TestCase):
    def setUp(self):
        import importlib.util
        from argparse import Namespace
        self.assertTrue((SOURCE / 'prepare.py').is_file(), 'Sealed preparation helper is missing')
        spec = importlib.util.spec_from_file_location('prepare', SOURCE / 'prepare.py')
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.config = self.root / 'config.json'
        self.config.write_text(json.dumps({'version':1,'expectedSystemIdentifier':'12345','entries':[]}))
        self.opts = Namespace(mode='new', config=self.config, id='alpha', database='alpha', role='alpha',
                              password_key='alpha-password', app_namespace='media', app_secret='alpha-secret',
                              app_password_key='password', app_url_key='url', output_dir=self.root / 'bundle',
                              aggregate_secret=None, app_sealed_secret=None)
        self.calls = []

    def fake_seal(self, args, **kwargs):
        import base64
        import hashlib
        import yaml
        name, namespace = args[1:3]
        self.calls.append((name, namespace, kwargs['input']))
        if getattr(self, 'fail_second', False) and len(self.calls) == 2:
            raise subprocess.CalledProcessError(1, args, stderr=kwargs['input'])
        values = dict(line.split('=',1) for line in kwargs['input'].splitlines())
        obj = {'apiVersion':'bitnami.com/v1alpha1','kind':'SealedSecret',
               'metadata':{'name':name,'namespace':namespace},
               'spec':{'encryptedData':{k:'ciphertext-' + hashlib.sha256(v.encode()).hexdigest() for k,v in values.items()},
                       'template':{'metadata':{'name':name,'namespace':namespace},'type':'Opaque'}}}
        (Path(kwargs['cwd']) / (name + '.yaml')).write_text(yaml.safe_dump(obj))
        return subprocess.CompletedProcess(args,0,'sealed','')

    def prepare(self, password=None):
        import io
        from unittest.mock import patch
        with patch.object(self.module.subprocess, 'run', side_effect=self.fake_seal), patch.object(self.module.sys,'stdin',io.StringIO(password or '')):
            return self.module.prepare_bundle(self.opts)

    def test_pair_generation_and_retry_preserve_ciphertext(self):
        # Break caught: independently generated passwords or overwriting a prepared bundle.
        import yaml
        import yaml
        original = {'apiVersion':'bitnami.com/v1alpha1','kind':'SealedSecret',
                    'metadata':{'name':'postgres-enrollment-credentials','namespace':'databases','labels':{'keep':'yes'}},
                    'spec':{'encryptedData':{'beta-password':'unchanged-aggregate-ciphertext'},
                            'template':{'metadata':{'name':'postgres-enrollment-credentials','namespace':'databases'},'type':'Opaque'}}}
        self.opts.aggregate_secret = self.root / 'aggregate.yaml'
        self.opts.aggregate_secret.write_text(yaml.safe_dump(original))
        self.config.write_text(json.dumps({'version':1,'expectedSystemIdentifier':'12345',
                                          'entries':[EnrollmentTests.entry('beta')]}))
        path = self.prepare()
        aggregate = yaml.safe_load((path / 'enrollment-secret.yaml').read_text())
        app = yaml.safe_load((path / 'application-secret.yaml').read_text())
        self.assertEqual(aggregate['spec']['encryptedData']['beta-password'], 'unchanged-aggregate-ciphertext')
        self.assertEqual(aggregate['metadata']['labels'], {'keep':'yes'})
        self.assertEqual(aggregate['spec']['encryptedData']['alpha-password'], app['spec']['encryptedData']['password'])
        before = {p.name:p.read_bytes() for p in path.iterdir()}
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertEqual(before, {p.name:p.read_bytes() for p in path.iterdir()})
        plain = self.calls[0][2].split('=',1)[1].strip()
        self.assertGreaterEqual(len(plain),40)
        self.opts.config = path / 'config.json'
        self.opts.output_dir = self.root / 'duplicate'
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertFalse(self.opts.output_dir.exists())
        for data in before.values():
            self.assertNotIn(plain.encode(), data, 'Published bundle contains plaintext')

    def test_adopt_uses_supplied_password_and_preserves_unrelated_keys(self):
        # Break caught: canonical credentials or unrelated sealed inputs are replaced.
        import copy
        import yaml
        original = {'apiVersion':'bitnami.com/v1alpha1','kind':'SealedSecret',
                    'metadata':{'name':'alpha-secret','namespace':'media','labels':{'keep':'yes'}},
                    'spec':{'encryptedData':{'existing':'unchanged-ciphertext'},
                            'template':{'metadata':{'name':'alpha-secret','namespace':'media'},'type':'Opaque'}}}
        supplied = " exact 'quote' \\ $ ` UTF8-é "
        self.opts.mode='adopt'
        self.opts.app_sealed_secret=self.root / 'app.yaml'
        self.opts.app_sealed_secret.write_text(yaml.safe_dump(original))
        path=self.prepare(supplied)
        app=yaml.safe_load((path/'application-secret.yaml').read_text())
        self.assertEqual(app['spec']['encryptedData']['existing'],'unchanged-ciphertext')
        self.assertEqual(app['metadata']['labels'],{'keep':'yes'})
        import hashlib
        self.assertEqual(app['spec']['encryptedData']['password'], 'ciphertext-' + hashlib.sha256(supplied.encode()).hexdigest())
        from urllib.parse import quote
        expected_url='postgresql://alpha:' + quote(supplied,safe='') + '@postgres-postgresql.databases:5432/alpha'
        self.assertEqual(app['spec']['encryptedData']['url'], 'ciphertext-' + hashlib.sha256(expected_url.encode()).hexdigest())
        # Invalid scope, collisions and bytes fail before a final directory is visible.
        for i, bad in enumerate(('scope','collision','bytes','template','unknown-config')):
            self.opts.output_dir=self.root / ('bad-'+bad)
            obj=copy.deepcopy(original)
            pw=supplied
            if bad=='scope': obj['metadata']['annotations']={'sealedsecrets.bitnami.com/cluster-wide':'true'}
            if bad=='collision': obj['spec']['encryptedData']['password']='already-encrypted'
            if bad=='bytes': pw='bad\npassword'
            if bad=='template': obj['spec']['template']['metadata']['namespace']='different'
            if bad=='unknown-config': self.config.write_text('{"version":1,"expectedSystemIdentifier":"12345","entries":[],"extra":true}')
            self.opts.app_sealed_secret.write_text(yaml.safe_dump(obj))
            with self.assertRaises(ValueError): self.prepare(pw)
            self.assertFalse(self.opts.output_dir.exists())

    def test_partial_sealing_failure_publishes_nothing(self):
        # Break caught: a partial pair/config becomes reviewable despite failed second sealing.
        self.fail_second=True
        with self.assertRaises(ValueError) as raised:
            self.prepare()
        self.assertFalse(self.opts.output_dir.exists())
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ['config.json'])
        for _,_,text in self.calls:
            self.assertNotIn(text, str(raised.exception))


if __name__ == '__main__':
    unittest.main()
