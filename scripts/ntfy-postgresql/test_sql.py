"""Synthetic native PostgreSQL guard tests; no production data or credentials."""
import json
from pathlib import Path
import subprocess
import time
import unittest
import uuid

import yaml

HERE = Path(__file__).resolve().parent
IMAGE = 'postgres:18.6-alpine@sha256:6c538e7206ea40ff740ef27883529390a690b6ead6ba96b44c67a9f7c638e8fd'


class NativeSQLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.name = 'ntfy-schema-check-' + uuid.uuid4().hex[:12]
        cls.command(['docker', 'run', '-d', '--name', cls.name, '--network', 'none',
                     '--memory', '256m', '--cpus', '1', '--pids-limit', '128',
                     '--tmpfs', '/var/lib/postgresql:rw,size=128m',
                     '-e', 'PGDATA=/var/lib/postgresql/data', '-e', 'POSTGRES_PASSWORD=fixture-only', IMAGE])
        cls.addClassCleanup(lambda: cls.command(['docker', 'rm', '-f', cls.name], check=False))
        for _ in range(100):
            if not cls.command(['docker', 'exec', cls.name, 'pg_isready', '-h', '127.0.0.1', '-U', 'postgres'], check=False).returncode:
                break
            time.sleep(0.2)
        else:
            raise AssertionError('Synthetic PostgreSQL not ready')
        cls.sql("CREATE ROLE ntfy LOGIN; CREATE DATABASE ntfy OWNER ntfy;")
        cls.sql('GRANT EXECUTE ON FUNCTION pg_control_system() TO ntfy;')
        identity = cls.sql('SELECT system_identifier::text FROM pg_control_system();').stdout.strip()
        cls.guard = (HERE / 'main.sql').read_text().replace('7584099661242523698', identity)

    @staticmethod
    def command(args, data=None, check=True):
        r = subprocess.run(args, input=data, text=True, capture_output=True, timeout=45)
        if check and r.returncode:
            raise AssertionError(r.stderr[:1200])
        return r

    @classmethod
    def sql(cls, sql, database='postgres', check=True):
        return cls.command(['docker', 'exec', '-i', cls.name, 'psql', '-XqAt',
                            '-v', 'ON_ERROR_STOP=1', '-U', 'postgres', '-d', database], sql, check)

    def fixture(self, version=15):
        cols = json.loads((HERE / 'test-schema15.json').read_text())
        if version == 16:
            cols['message'].append(['claimed_at', 'bigint', 'NO'])
        queries = ['DROP SCHEMA public CASCADE;', 'CREATE SCHEMA public AUTHORIZATION ntfy;', 'SET ROLE ntfy;']
        for table, fields in cols.items():
            declarations = ','.join('"%s" %s%s' % (n, t, ' NOT NULL' if nullable == 'NO' else '') for n,t,nullable in fields)
            queries.append('CREATE TABLE "%s" (%s);' % (table, declarations))
        queries.append("INSERT INTO schema_version VALUES ('user',9),('message',%d),('webpush',1);" % version)
        for ident, name, role in [('u_everyone','*','anonymous'), ('fixture_admin','fixture','admin')]:
            values = []
            for column, typ, nullable in cols['user']:
                value = {'id': ident, 'user_name': name, 'role': role}.get(column, '')
                values.append('NULL' if nullable == 'YES' else ('false' if typ == 'boolean' else ('0' if typ in ('integer','bigint') else ("'{}'::jsonb" if typ == 'jsonb' else "'%s'" % value))))
            queries.append('INSERT INTO "user" VALUES (%s);' % ','.join(values))
        queries.append("INSERT INTO message_stats VALUES ('messages',9);")
        self.sql('\n'.join(queries), 'ntfy')

    def gate(self, guard=None):
        return self.sql('SET ROLE ntfy;\n' + (self.guard if guard is None else guard), 'ntfy', check=False)

    def test_both_exact_schemas_are_accepted_without_changes(self):
        for version in (15,16):
            with self.subTest(version=version):
                self.fixture(version)
                before = self.sql('TABLE schema_version; TABLE "user"; TABLE message_stats;', 'ntfy').stdout
                self.assertEqual(self.gate().returncode, 0)
                self.assertEqual(before, self.sql('TABLE schema_version; TABLE "user"; TABLE message_stats;', 'ntfy').stdout)

    def test_pinned_ntfy_upgrade_and_restart_remain_guard_compatible(self):
        # Exercise the actual pinned binary against its independent upstream DDL.
        # CI repeats this when Renovate changes the image, catching schema drift.
        self.sql('DROP SCHEMA public CASCADE; CREATE SCHEMA public AUTHORIZATION ntfy;', 'ntfy')
        self.sql('SET ROLE ntfy;\n' + (HERE / 'initial.sql').read_text(), 'ntfy')
        self.sql("INSERT INTO public.\"user\" (id,user_name,pass,role,sync_topic,provisioned,created) "
                 "VALUES ('fixture_admin','fixture','fixture','admin','',false,0), "
                 "('u_everyone','*','','anonymous','',false,123);", 'ntfy')
        self.sql("ALTER ROLE ntfy PASSWORD 'fixture-only';")
        root = HERE.parents[1]
        image = yaml.safe_load((root / 'services/operations/ntfy/values.yaml').read_text())['controllers']['main']['containers']['main']['image']
        reference = image['repository'] + ':' + image['tag']
        app = self.name + '-app'
        self.addCleanup(lambda: self.command(['docker', 'rm', '-f', app], check=False))
        # No external network, ports, credentials, subscribers or production data.
        self.command(['docker', 'run', '-d', '--name', app, '--network', 'container:' + self.name,
                      '--memory', '256m', '--cpus', '1', '--pids-limit', '128',
                      '-e', 'NTFY_DATABASE_URL=postgresql://ntfy:fixture-only@127.0.0.1:5432/ntfy',
                      '-e', 'NTFY_BASE_URL=http://localhost:8080', '-e', 'NTFY_LISTEN_HTTP=:8080',
                      reference, 'serve'])
        for _ in range(80):
            health = self.command(['docker', 'exec', self.name, 'wget', '-qO-',
                                   'http://127.0.0.1:8080/v1/health'], check=False)
            if health.returncode == 0:
                break
            time.sleep(0.2)
        logs = self.command(['docker', 'logs', '--tail', '30', app], check=False)
        self.assertEqual(health.returncode, 0, logs.stdout + logs.stderr)
        gate = self.gate()
        self.assertEqual(gate.returncode, 0, gate.stderr + self.sql("SELECT store,version FROM schema_version; SELECT id,user_name,role FROM public.\"user\"; TABLE message_stats;", 'ntfy').stdout)
        self.command(['docker', 'restart', app])
        for _ in range(80):
            health = self.command(['docker', 'exec', self.name, 'wget', '-qO-',
                                   'http://127.0.0.1:8080/v1/health'], check=False)
            if health.returncode == 0:
                break
            time.sleep(0.2)
        self.assertEqual(health.returncode, 0)
        self.assertEqual(self.gate().returncode, 0)

    def test_mismatched_or_future_versions_and_damaged_state_are_rejected(self):
        alterations = [
            "UPDATE schema_version SET version=16 WHERE store='message';",
            "UPDATE schema_version SET version=17 WHERE store='message';",
            "UPDATE schema_version SET version=10 WHERE store='user';",
            "DELETE FROM schema_version WHERE store='webpush';",
            "ALTER TABLE message ADD COLUMN unexpected text;",
            "ALTER TABLE message DROP COLUMN mid;",
            "ALTER TABLE message ALTER COLUMN mid DROP NOT NULL;",
            "ALTER TABLE message OWNER TO postgres;",
            "DELETE FROM \"user\" WHERE role='admin';",
            "DELETE FROM \"user\" WHERE role='anonymous';",
            "UPDATE message_stats SET value=-1;",
            "CREATE TABLE unexpected (id integer);",
        ]
        for alteration in alterations:
            with self.subTest(alteration=alteration):
                self.fixture()
                self.sql(alteration, 'ntfy')
                self.assertNotEqual(self.gate().returncode,0)
        self.fixture(16)
        self.sql("UPDATE schema_version SET version=15 WHERE store='message';", 'ntfy')
        self.assertNotEqual(self.gate().returncode,0)
        self.fixture(16)
        self.assertNotEqual(self.gate(self.guard.replace("current_user <> 'ntfy'", "current_user <> 'wrong' ")).returncode,0)
        self.assertNotEqual(self.gate(self.guard.replace("system_identifier::text", "(system_identifier + 1)::text")).returncode,0)


if __name__ == '__main__':
    unittest.main()
