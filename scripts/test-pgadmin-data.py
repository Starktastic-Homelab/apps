"""pgAdmin's data contract must reject loss that a row count cannot detect."""
import copy
import datetime
import importlib.util
import json
import pathlib
import sqlite3
import tempfile
import unittest

PATH = pathlib.Path(__file__).parent / 'pgadmin-postgresql/data.py'


class PgAdminDataTests(unittest.TestCase):
    def data(self):
        self.assertTrue(PATH.is_file(), 'pgAdmin preservation implementation is missing')
        spec = importlib.util.spec_from_file_location('pgadmin_data', PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_native_representations_preserve_every_field_and_duplicate(self):
        data = self.data()
        columns = {'id': 'integer', 'active': 'boolean', 'password': 'character varying',
                   'confirmed_at': 'timestamp without time zone', 'settings': 'json', 'optional': 'text'}
        source = {'id': 1, 'active': 1, 'password': '00ff00',
                  'confirmed_at': '2026-10-16 12:34:56.123456', 'settings': '{"b":[null,"Δ"],"a":1}', 'optional': None}
        target = dict(source, active=True, confirmed_at=datetime.datetime(2026, 10, 16, 12, 34, 56, 123456), settings='{"a":1,"b":[null,"Δ"]}')
        expected = data.canonical_rows([source, source], columns)
        self.assertEqual(expected, data.canonical_rows([target, target], columns))
        for field, value in [('password', '00fe00'), ('id', 2), ('active', False),
                             ('optional', ''), ('settings', '{"a":1,"b":[null,"D"]}'),
                             ('confirmed_at', '2026-10-16 12:34:56.123457')]:
            changed = dict(target, **{field: value})
            self.assertNotEqual(expected, data.canonical_rows([target, changed], columns))
        self.assertNotEqual(expected, data.canonical_rows([target], columns))

    def test_literal_escape_text_is_preserved_but_actual_json_nul_is_rejected(self):
        data = self.data()
        result = data.canonical_rows([{'v': r'\u0000'}], {'v': 'text'})
        self.assertEqual(json.loads(result[0])['v'], r'\u0000')
        result = data.canonical_rows([{'v': '"\\\\u0000"'}], {'v': 'json'})
        self.assertEqual(json.loads(result[0])['v']['jsonValue'], r'\u0000')
        with self.assertRaises(ValueError):
            data.canonical_rows([{'v': '"\\u0000"'}], {'v': 'json'})

    def test_sql_null_json_null_and_json_string_are_distinct(self):
        data = self.data()
        values = [data.canonical_rows([{'v': value}], {'v': 'json'}) for value in (None, 'null', '"null"')]
        self.assertEqual(len({str(v) for v in values}), 3)

    def test_rejects_invalid_or_lossy_values_instead_of_coercing(self):
        data = self.data()
        for kind, value in [('boolean', 2), ('boolean', 'false'), ('integer', True), ('integer', 1.2),
                            ('text', b'\xff'), ('text', 'bad\x00'), ('text', '\ud800'),
                            ('json', '{"x":NaN}'), ('json', '{"x":1,"x":2}'), ('json', 'not-json'),
                            ('timestamp without time zone', '2026-10-16T12:34:56.1234567'),
                            ('timestamp without time zone', '2026-10-16T12:34:56+03:00'),
                            ('timestamp without time zone', '2026-02-30'), ('bytea', b'unknown')]:
            with self.subTest(kind=kind, value=repr(value)), self.assertRaises((ValueError, UnicodeError)):
                data.canonical_rows([{'v': value}], {'v': kind})
        for row in ({}, {'v': 'kept', 'unknown': 'must reject'}):
            with self.assertRaises(ValueError):
                data.canonical_rows([row], {'v': 'text'})

    def test_incomplete_or_symlink_sqlite_source_is_rejected_without_writing(self):
        data = self.data()
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / 'source.db'
            with sqlite3.connect(path) as db:
                db.execute('CREATE TABLE unknown(value TEXT)')
            before = path.read_bytes()
            with self.assertRaises(ValueError):
                data.read_source(path)
            self.assertEqual(path.read_bytes(), before)
            linked = pathlib.Path(directory) / 'linked.db'
            linked.symlink_to(path)
            with self.assertRaises(ValueError):
                data.read_source(linked)

    def test_bigint_preserves_database_identifiers_without_narrowing(self):
        data = self.data()
        self.assertEqual(data.canonical_rows([{'id': 9223372036854775807}], {'id': 'bigint'}),
                         ['{"id":9223372036854775807}'])
        for value in (True, 1.5, 9223372036854775808):
            with self.assertRaises(ValueError):
                data.canonical_rows([{'id': value}], {'id': 'bigint'})

    def test_complete_tables_fields_and_markers_are_required(self):
        data = self.data()
        source = {'alembic_version': [{'version_num': 'fixture52'}], 'version': [{'name': 'ConfigDB', 'value': 52}],
                  'keys': [{'name': 'SECRET_KEY', 'value': 'fixture-only'}], 'setting': [{'id': 1, 'value': None}]}
        columns = {'alembic_version': {'version_num': 'character varying'}, 'version': {'name': 'character varying', 'value': 'integer'},
                   'keys': {'name': 'text', 'value': 'text'}, 'setting': {'id': 'integer', 'value': 'text'}}
        self.assertEqual(data.compare(source, source, columns)['tables'], 4)
        bad = []
        missing = copy.deepcopy(source);missing.pop('keys');bad.append(missing)
        extra = copy.deepcopy(source);extra['future_table'] = [];bad.append(extra)
        marker = copy.deepcopy(source);marker['version'][0]['value'] = 51;bad.append(marker)
        changed = copy.deepcopy(source);changed['setting'][0]['value'] = '';bad.append(changed)
        duplicate = copy.deepcopy(source);duplicate['setting'] *= 2;bad.append(duplicate)
        for target in bad:
            with self.assertRaises(ValueError):
                data.compare(source, target, columns)


if __name__ == '__main__':
    unittest.main()
