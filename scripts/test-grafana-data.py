import copy
import hashlib
import importlib.util
import pathlib
import sqlite3
import tempfile
import unittest

MODULE = pathlib.Path(__file__).parent / 'grafana-postgresql/data.py'


class GrafanaDataTests(unittest.TestCase):
    def module(self):
        spec = importlib.util.spec_from_file_location('grafana_data', MODULE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_timestamp_literal_preserves_nanoseconds_and_rejects_ambiguous_values(self):
        data = self.module()
        self.assertEqual(data.timestamp_literal('2026-04-23 16:36:24.153832131 +0000 UTC'),
                         '2026-04-23 16:36:24.153832131+00:00')
        self.assertEqual(data.timestamp_literal('2026-04-23 16:36:24.153832131 +0000 UTC m=+0.123456789'), '2026-04-23 16:36:24.153832131+00:00')
        for value in ['2026-04-23', '2026-04-23T16:36:24.153832131Z', '2026-04-23 16:36:24.1', '2026-04-23 16:36:24+00:00']:
            self.assertEqual(data.timestamp_literal(value), value)
        for value in ['2026-04-23 16:36:24 +0300 IDT', '2026-04-23T16:36:24+03:00',
                      '2026-02-30 12:00:00', '2026-02-30', '2026-04-23 16:36:24 +0000 UTC m=garbage', '2026-04-23 16:36:24\x00', '', None]:
            with self.assertRaises(ValueError):
                data.timestamp_literal(value)

    def test_fixed_character_padding_is_bounded_and_does_not_trim_content(self):
        data = self.module()
        self.assertEqual(data.character_literal('', 44), ' ' * 44)
        self.assertEqual(data.character_literal('hash', 8), 'hash    ')
        self.assertEqual(data.character_literal('Δ ', 4), 'Δ   ')
        for value, width in [('too long', 3), ('invalid\x00', 12), (None, 4), ('x', 0)]:
            with self.assertRaises(ValueError):
                data.character_literal(value, width)

    def test_materialize_changes_only_legacy_timestamp_working_values(self):
        data = self.module()
        with tempfile.TemporaryDirectory() as directory:
            source = pathlib.Path(directory) / 'source.db'
            destination = pathlib.Path(directory) / 'working.db'
            with sqlite3.connect(source) as db:
                db.executescript('CREATE TABLE resource_last_import_time(name TEXT, last_import_time DATETIME, payload BLOB); CREATE TABLE migration_log(id INTEGER, timestamp DATETIME);')
                value = '2026-04-23 16:36:24.153832131 +0000 UTC'
                db.execute('INSERT INTO resource_last_import_time VALUES(?,?,?)', ('fixture', value, b'\x00\xff\x01'))
                db.execute('INSERT INTO migration_log VALUES(1,?)', (value,))
            before = hashlib.sha256(source.read_bytes()).hexdigest()
            columns = [{'table_name': 'resource_last_import_time', 'column_name': 'last_import_time', 'data_type': 'timestamp without time zone'},
                       {'table_name': 'migration_log', 'column_name': 'timestamp', 'data_type': 'timestamp without time zone'}]
            result = data.materialize(source, destination, columns)
            self.assertEqual(result['changedRows'], 1)
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), before)
            self.assertEqual(destination.stat().st_mode & 0o077, 0)
            with sqlite3.connect(destination) as db:
                self.assertEqual(db.execute('SELECT last_import_time,payload FROM resource_last_import_time').fetchone(),
                                 ('2026-04-23 16:36:24.153832131+00:00', b'\x00\xff\x01'))
                self.assertEqual(db.execute('SELECT timestamp FROM migration_log').fetchone()[0], value)
            with self.assertRaises(FileExistsError):
                data.materialize(source, destination, columns)



    def test_field_comparison_rejects_loss_even_when_counts_match(self):
        data = self.module()
        columns = [
            {'column_name': 'password', 'data_type': 'text'},
            {'column_name': 'cipher', 'data_type': 'bytea'},
            {'column_name': 'resource', 'data_type': 'text'},
            {'column_name': 'stamp', 'data_type': 'timestamp without time zone'},
            {'column_name': 'fixed', 'data_type': 'character', 'character_maximum_length': 4},
            {'column_name': 'enabled', 'data_type': 'boolean'},
            {'column_name': 'optional', 'data_type': 'text'},
        ]
        source = {'password': 'hash', 'cipher': b'\x00\xff', 'resource': 'Δ'.encode(),
                  'stamp': '2026-04-23 16:36:24.153832131 +0000 UTC', 'fixed': '', 'enabled': 1, 'optional': None}
        target = {'password': 'hash', 'cipher': '\\x00ff', 'resource': 'Δ',
                  'stamp': '2026-04-23T16:36:24.153832', 'fixed': '    ', 'enabled': True, 'optional': None}
        casts = {source['stamp']: '2026-04-23 16:36:24.153832'}
        expected = data.canonical_rows([source, source], columns, True, casts)
        self.assertEqual(expected, data.canonical_rows([target, target], columns, False, casts))
        for name, value in [('password', 'different'), ('cipher', '\\x00fe'), ('resource', 'changed'),
                            ('stamp', '2026-04-23T16:36:24.153833'), ('optional', '')]:
            changed = copy.deepcopy(target)
            changed[name] = value
            self.assertNotEqual(expected, data.canonical_rows([target, changed], columns, False, casts))
        self.assertNotEqual(expected, data.canonical_rows([target], columns, False, casts))
        for changed in [dict(source, resource=b'\xff'), dict(source, stamp='unmapped'), dict(source, extra='unknown')]:
            with self.assertRaises((ValueError, UnicodeError)):
                data.canonical_rows([changed], columns, True, casts)

    def test_source_only_tables_are_allowed_only_when_obsolete_and_empty(self):
        data = self.module()
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / 'source.db'
            with sqlite3.connect(path) as db:
                db.executescript('CREATE TABLE resource(value TEXT); CREATE TABLE entity_event(value TEXT);')
                db.execute('INSERT INTO resource VALUES(?)', ('kept',))
            columns = [{'table_name': 'resource', 'column_name': 'value', 'data_type': 'text'}]
            target = {'resource': [{'value': 'kept'}]}
            self.assertEqual(data.compare(path, target, columns, {})['resource']['rows'], 1)
            with sqlite3.connect(path) as db:
                db.execute('INSERT INTO entity_event VALUES(?)', ('must not drop',))
            with self.assertRaises(ValueError):
                data.compare(path, target, columns, {})
            with sqlite3.connect(path) as db:
                db.execute('DELETE FROM entity_event')
                db.execute('CREATE TABLE future_table(value TEXT)')
            with self.assertRaises(ValueError):
                data.compare(path, target, columns, {})


if __name__ == '__main__':
    unittest.main()
