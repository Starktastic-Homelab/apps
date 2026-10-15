#!/usr/bin/env python3
"""ntfy retained startup and lossless conversion rejection checks."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'scripts/ntfy-postgresql'


def load(test, name):
    path = PACKAGE / (name + '.py')
    test.assertTrue(path.is_file(), 'ntfy ' + name + ' contract missing')
    spec = importlib.util.spec_from_file_location('ntfy_' + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.guard = load(self, 'guard')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'data'
        self.root.mkdir()
        (self.root / 'attachments').mkdir()
        (self.root / '.homelab-ntfy-data').write_text('homelab/ntfy/data/v1\n')
        self.credentials = self.root.parent / 'credentials'
        self.credentials.mkdir()
        (self.credentials / 'password').write_text('fixture-only-password')
        self.env = {'NTFY_DATABASE_URL': 'postgresql://ntfy:fixture-only-password@postgres-postgresql.databases:5432/ntfy'}

    def test_retained_identity_and_canonical_secret_accepted_without_writes(self):
        before = {str(p): p.read_bytes() for p in self.root.parent.rglob('*') if p.is_file()}
        self.guard.validate(self.root, self.credentials, self.env)
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.root.parent.rglob('*') if p.is_file()})

    def test_wrong_missing_and_symlinked_identity_rejected(self):
        marker = self.root / '.homelab-ntfy-data'
        for value in ('', 'homelab/other/data/v1\n', 'x' * 129):
            marker.write_text(value)
            with self.assertRaises(ValueError): self.guard.validate(self.root, self.credentials, self.env)
        marker.unlink()
        with self.assertRaises(ValueError): self.guard.validate(self.root, self.credentials, self.env)
        marker.symlink_to(self.credentials / 'password')
        with self.assertRaises(ValueError): self.guard.validate(self.root, self.credentials, self.env)

    def test_sqlite_fallback_and_attachment_symlink_rejected(self):
        for base in ('cache.db', 'user.db', 'webpush.db'):
            for suffix in ('', '-wal', '-shm', '-journal'):
                p = self.root / (base + suffix)
                p.symlink_to('missing')
                with self.assertRaises(ValueError): self.guard.validate(self.root, self.credentials, self.env)
                p.unlink()
        (self.root / 'attachments').rmdir()
        (self.root / 'attachments').symlink_to('missing', target_is_directory=True)
        with self.assertRaises(ValueError): self.guard.validate(self.root, self.credentials, self.env)

    def test_wrong_database_credential_or_sqlite_environment_rejected(self):
        for value in ('', self.env['NTFY_DATABASE_URL'] + '?search_path=other', self.env['NTFY_DATABASE_URL'].replace('/ntfy', '/other'), self.env['NTFY_DATABASE_URL'].replace('fixture-only-password', 'wrong')):
            with self.assertRaises(ValueError): self.guard.validate(self.root, self.credentials, {'NTFY_DATABASE_URL': value})
        for name in ('NTFY_AUTH_FILE', 'NTFY_CACHE_FILE', 'NTFY_WEB_PUSH_FILE', 'NTFY_DATABASE_REPLICA_URLS'):
            with self.assertRaises(ValueError): self.guard.validate(self.root, self.credentials, dict(self.env, **{name: '/wrong'}))


class DataTests(unittest.TestCase):
    def setUp(self):
        self.data = load(self, 'data')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.paths = {name: Path(self.temp.name) / (name + '.sqlite3') for name in ('auth', 'cache', 'webpush')}
        schemas = {
            'auth': "CREATE TABLE tier(id TEXT,code TEXT);CREATE TABLE user(id TEXT,user TEXT,pass TEXT,role TEXT,prefs JSON,provisioned INT,created INT);CREATE TABLE user_access(user_id TEXT,topic TEXT,read INT,write INT);CREATE TABLE user_token(user_id TEXT,token TEXT,last_access INT);CREATE TABLE user_phone(user_id TEXT,phone_number TEXT);CREATE TABLE user_email(user_id TEXT,email TEXT,is_primary INT);CREATE TABLE user_magic_link(token_hash TEXT);INSERT INTO user VALUES('u','fixture','preserved-hash','admin','{\"dark\":true}',0,123);INSERT INTO user_access VALUES('u','private',1,0);INSERT INTO user_token VALUES('u','fixture-token',7);",
            'cache': "CREATE TABLE messages(id INTEGER PRIMARY KEY,mid TEXT,sequence_id TEXT,message TEXT,published INT,user TEXT);CREATE TABLE stats(key TEXT,value INT);INSERT INTO messages VALUES(3,'mid','seq','Unicode שלום',1,'u');INSERT INTO stats VALUES('messages',9);",
            'webpush': 'CREATE TABLE subscription(id TEXT,endpoint TEXT,updated_at INT);CREATE TABLE subscription_topic(subscription_id TEXT,topic TEXT);'}
        for name, sql in schemas.items():
            with sqlite3.connect(self.paths[name]) as c:
                c.executescript(sql + 'CREATE TABLE schemaVersion(id INT,version INT);')
                c.execute('INSERT INTO schemaVersion VALUES(1,?)', ({'auth': 9, 'cache': 15, 'webpush': 1}[name],))
        tables = {'tier': [], 'user': [{'id': 'u', 'user_name': 'fixture', 'pass': 'preserved-hash', 'role': 'admin', 'prefs': {'dark': True}, 'provisioned': False, 'created': 123}], 'user_access': [{'user_id': 'u', 'topic': 'private', 'read': True, 'write': False}], 'user_token': [{'user_id': 'u', 'token': 'fixture-token', 'last_access': 7}], 'user_phone': [], 'user_email': [], 'user_magic_link': [], 'message': [{'id': 99, 'mid': 'mid', 'sequence_id': 'seq', 'message': 'Unicode שלום', 'published': True, 'user_id': 'u'}], 'message_stats': [{'key': 'messages', 'value': 9}], 'webpush_subscription': [], 'webpush_subscription_topic': []}
        self.pg = {'versions': {'user': 9, 'message': 15, 'webpush': 1}, 'tables': tables, 'types': {'user': {'provisioned': 'boolean', 'prefs': 'jsonb'}, 'user_access': {'read': 'boolean', 'write': 'boolean'}, 'message': {'published': 'boolean'}}}

    def test_all_fields_and_external_message_ids_preserved(self):
        result = self.data.compare(self.paths, self.pg)
        self.assertEqual(len(result['tables']), 11)
        self.assertTrue(result['allApplicationFieldsPreserved'])

    def test_changed_password_acl_token_message_or_stats_rejected(self):
        for table, key, value in (('user', 'pass', 'changed'), ('user_access', 'write', True), ('user_token', 'token', 'changed'), ('message', 'mid', 'changed'), ('message_stats', 'value', 8)):
            pg = copy.deepcopy(self.pg)
            pg['tables'][table][0][key] = value
            with self.assertRaises(ValueError): self.data.compare(self.paths, pg)

    def test_omitted_new_auth_data_invalid_text_and_unexpected_tables_rejected(self):
        with sqlite3.connect(self.paths['auth']) as c: c.execute("INSERT INTO user_email VALUES('u','fixture@example.invalid',1)")
        with self.assertRaises(ValueError): self.data.compare(self.paths, self.pg)
        with sqlite3.connect(self.paths['auth']) as c: c.execute('DELETE FROM user_email')
        with sqlite3.connect(self.paths['cache']) as c: c.execute("UPDATE messages SET message=CAST(x'80' AS TEXT)")
        with self.assertRaises(ValueError): self.data.compare(self.paths, self.pg)
        with sqlite3.connect(self.paths['cache']) as c: c.execute("UPDATE messages SET message='valid'")
        with sqlite3.connect(self.paths['cache']) as c: c.execute('CREATE TABLE unexpected(id INT)')
        with self.assertRaises(ValueError): self.data.compare(self.paths, self.pg)


class SourceTests(unittest.TestCase):
    def test_sources_reuse_gate_with_retained_identity_and_no_sqlite_environment(self):
        prepare = load(self, 'prepare')
        resources, values = prepare.build_sources()
        controller = values['controllers']['main']
        self.assertEqual(controller['strategy'], 'Recreate')
        self.assertEqual(controller['serviceAccount']['name'], 'ntfy-postgres-completion')
        self.assertFalse(controller['pod']['automountServiceAccountToken'])
        self.assertEqual(set(controller['initContainers']), {'retained-state', 'enrollment', 'database'})
        names = {e['name'] for e in controller['containers']['main']['env']}
        self.assertFalse(names & {'NTFY_AUTH_FILE', 'NTFY_CACHE_FILE', 'NTFY_WEB_PUSH_FILE'})
        self.assertEqual(values['persistence']['ntfy-data']['existingClaim'], 'ntfy-data-block')
        self.assertFalse(values['persistence']['config']['enabled'])
        self.assertFalse(values['persistence']['cache']['enabled'])
        self.assertEqual(controller['initContainers']['enrollment']['dependsOn'], 'retained-state')
        self.assertEqual(controller['initContainers']['database']['dependsOn'], 'enrollment')
        bindings = [o for o in resources if o['kind'] == 'RoleBinding']
        self.assertEqual({o['metadata']['namespace'] for o in bindings}, {'argocd', 'databases'})
        self.assertTrue(all(o['subjects'][0]['namespace'] == 'operations' for o in bindings))


    def test_generator_accepts_the_reconciled_list_environment(self):
        from unittest.mock import patch
        import yaml
        prepare = load(self, 'prepare')
        _, initial = prepare.build_sources()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / 'templates').mkdir()
            (root / 'services/operations/ntfy').mkdir(parents=True)
            (root / 'templates/common.yaml').write_text((ROOT / 'templates/common.yaml').read_text())
            (root / 'services/operations/ntfy/values.yaml').write_text(yaml.safe_dump(initial))
            with patch.object(prepare, 'ROOT', root):
                _, reconciled = prepare.build_sources()
            self.assertEqual(reconciled, initial)


@unittest.skipUnless(os.environ.get('NTFY_RETAINED_RENDER'), 'Provide the actual layered Helm render')
class RenderTests(unittest.TestCase):
    def test_actual_layers_have_one_retained_claim_and_no_sqlite_env(self):
        import yaml
        objects = list(yaml.safe_load_all(Path(os.environ['NTFY_RETAINED_RENDER']).read_text()))
        deployments = [o for o in objects if o and o['kind'] == 'Deployment']
        self.assertEqual(len(deployments), 1)
        pod = deployments[0]['spec']['template']['spec']
        self.assertEqual(pod['serviceAccountName'], 'ntfy-postgres-completion')
        self.assertFalse(pod['automountServiceAccountToken'])
        self.assertFalse(pod.get('securityContext', {}).get('fsGroup'))
        self.assertEqual([c['name'] for c in pod['initContainers']], ['retained-state', 'enrollment', 'database'])
        main = pod['containers'][0]
        env = {v['name']: v for v in main['env']}
        self.assertFalse(set(env) & {'NTFY_AUTH_FILE', 'NTFY_CACHE_FILE', 'NTFY_WEB_PUSH_FILE'})
        self.assertEqual(env['NTFY_DATABASE_URL']['valueFrom']['secretKeyRef'], {'name': 'ntfy-postgres-secret', 'key': 'database-url'})
        self.assertEqual(main['envFrom'], [{'secretRef': {'name': 'ntfy-webpush-secret', 'optional': True}}])
        self.assertEqual([v['persistentVolumeClaim']['claimName'] for v in pod['volumes'] if 'persistentVolumeClaim' in v], ['ntfy-data-block'])
        self.assertEqual(next(m['mountPath'] for m in main['volumeMounts'] if m['name'] == 'ntfy-data'), '/var/cache/ntfy')


if __name__ == '__main__': unittest.main()
