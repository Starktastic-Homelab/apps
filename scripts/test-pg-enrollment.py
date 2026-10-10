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
                '-e', 'PGDATABASE=postgres', '-v', str(self.root / 'config') + ':/config:ro',
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


if __name__ == '__main__':
    unittest.main()
