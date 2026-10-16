"""Strict pgAdmin 9.18 data comparison; never reinterpret encrypted hex strings."""
import datetime
import hashlib
import json
import re

SCHEMA_VERSION = 52
KINDS = frozenset({'integer', 'bigint', 'boolean', 'text', 'character varying', 'timestamp without time zone', 'json'})
MARKERS = frozenset({'alembic_version', 'version'})
TABLES = frozenset({'alembic_version', 'application_state', 'database', 'debugger_function_arguments',
    'keys', 'macros', 'module_preference', 'preference_category', 'preferences', 'process',
    'query_history', 'role', 'roles_users', 'server', 'servergroup', 'setting', 'sharedserver',
    'user', 'user_macros', 'user_mfa', 'user_preferences', 'version'})


def json_value(value):
    """Canonical JSON text; keep numeric tokens exact, including signed zero."""
    class Number(str):
        pass

    def pairs(items):
        result = {}
        for key, item in items:
            if key in result:
                raise ValueError('Duplicate JSON key cannot be accepted')
            result[key] = item
        return result

    def constant(_):
        raise ValueError('Non-finite JSON cannot be accepted')

    if not isinstance(value, str):
        raise ValueError('Expected native JSON text, preserving SQL NULL separately')
    result = json.loads(value, object_pairs_hook=pairs, parse_constant=constant,
                        parse_int=Number, parse_float=Number)

    def validate(item):
        if isinstance(item, str):
            if '\x00' in item:
                raise ValueError('NUL cannot be accepted')
            item.encode('utf-8', errors='strict')
        elif isinstance(item, list):
            for child in item:
                validate(child)
        elif isinstance(item, dict):
            for key, child in item.items():
                validate(key)
                validate(child)
    validate(result)

    def render(item):
        # Number tokens come only from the strict JSON parser. Rendering them
        # directly avoids binary-float rounding, overflow and string collisions.
        if isinstance(item, Number):
            return str(item)
        if isinstance(item, str):
            return json.dumps(item, ensure_ascii=False)
        if item is None:
            return 'null'
        if type(item) is bool:
            return 'true' if item else 'false'
        if isinstance(item, list):
            return '[' + ','.join(render(child) for child in item) + ']'
        return '{' + ','.join(json.dumps(key, ensure_ascii=False) + ':' + render(item[key])
                              for key in sorted(item)) + '}'
    return render(result)


def timestamp(value):
    if isinstance(value, str):
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?', value):
            raise ValueError('Unrecognized or lossy timestamp')
        value = datetime.datetime.fromisoformat(value)
    if not isinstance(value, datetime.datetime) or value.tzinfo is not None:
        raise ValueError('Expected native timestamp without time zone')
    return value.isoformat(timespec='microseconds')


def canonical_rows(rows, columns):
    if not columns or not set(columns.values()) <= KINDS:
        raise ValueError('Unexpected native column types')
    result = []
    for row in rows:
        if set(row) != set(columns):
            raise ValueError('Incomplete row field coverage')
        normalized = {}
        for name, kind in columns.items():
            value = row[name]
            if value is None:
                pass
            elif kind == 'boolean':
                if type(value) not in (int, bool) or value not in (0, 1):
                    raise ValueError('Invalid boolean')
                value = bool(value)
            elif kind in ('integer', 'bigint'):
                bits = 64 if kind == 'bigint' else 32
                if type(value) is not int or not -(2**(bits - 1)) <= value < 2**(bits - 1):
                    raise ValueError('Invalid native integer')
            elif kind in ('text', 'character varying'):
                if not isinstance(value, str) or '\x00' in value:
                    raise ValueError('Invalid native text')
                value.encode('utf-8', errors='strict')
            elif kind == 'timestamp without time zone':
                value = timestamp(value)
            elif kind == 'json':
                value = {'jsonValue': json_value(value)}
            normalized[name] = value
        encoded = json.dumps(normalized, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
        encoded.encode('utf-8', errors='strict')
        result.append(encoded)
    return sorted(result)


def compare(source, target, columns):
    if set(source) != set(target) or set(source) != set(columns) or not MARKERS <= set(source):
        raise ValueError('Incomplete table coverage')
    if source['version'] != [{'name': 'ConfigDB', 'value': SCHEMA_VERSION}]:
        raise ValueError('Unexpected source schema version')
    proofs = {}
    for table, definitions in columns.items():
        expected = canonical_rows(source[table], definitions)
        if expected != canonical_rows(target[table], definitions):
            raise ValueError('Complete field preservation failed for ' + table)
        proofs[table] = {'rows': len(expected), 'sha256': hashlib.sha256('\n'.join(expected).encode()).hexdigest()}
    return {'tables': len(proofs), 'rows': sum(v['rows'] for v in proofs.values()), 'proofs': proofs}


def read_source(path):
    import contextlib
    import pathlib
    import sqlite3
    path = pathlib.Path(path)
    if not path.is_file() or path.is_symlink() or any(path.with_name(path.name + s).exists() for s in ('-wal', '-journal')):
        raise ValueError('A standalone regular SQLite copy is required')
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    with contextlib.closing(sqlite3.connect(path.absolute().as_uri() + '?mode=ro', uri=True)) as db:
        db.execute('PRAGMA query_only=ON')
        if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)] or db.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('SQLite integrity refused')
        tables = {v[0] for v in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if tables - {'sqlite_sequence'} != TABLES:
            raise ValueError('Unexpected source tables')
        db.row_factory = sqlite3.Row
        rows = {name: [dict(v) for v in db.execute('SELECT * FROM "' + name + '"')] for name in sorted(TABLES)}
        columns = {name: [v[1] for v in db.execute('PRAGMA table_info("' + name + '")')] for name in sorted(TABLES)}
        floors = dict(db.execute('SELECT name,seq FROM sqlite_sequence')) if 'sqlite_sequence' in tables else {}
        if rows['version'] != [{'name': 'ConfigDB', 'value': SCHEMA_VERSION}] or set(floors) - TABLES:
            raise ValueError('Source schema or sequence identity refused')
    if hashlib.sha256(path.read_bytes()).hexdigest() != before:
        raise ValueError('Source changed while reading')
    return {'rows': rows, 'columns': columns, 'sequenceFloors': floors, 'sourceSHA256': before}


def read_target(connection):
    from psycopg import sql
    definitions = connection.execute("SELECT table_name,column_name,data_type FROM information_schema.columns WHERE table_schema='public' ORDER BY table_name,ordinal_position").fetchall()
    columns = {}
    for table, name, kind in definitions:
        columns.setdefault(table, {})[name] = kind
    if set(columns) != TABLES or any(not set(v.values()) <= KINDS for v in columns.values()):
        raise ValueError('Unexpected native target schema')
    rows = {}
    for name, fields in columns.items():
        expressions = [sql.SQL('{}::text AS {}').format(sql.Identifier(k), sql.Identifier(k)) if kind == 'json' else sql.Identifier(k) for k, kind in fields.items()]
        records = connection.execute(sql.SQL('SELECT {} FROM {}').format(sql.SQL(',').join(expressions), sql.Identifier('public', name))).fetchall()
        rows[name] = [dict(zip(fields, row)) for row in records]
    return rows, columns


def fingerprint(rows, columns):
    normalized = {name: canonical_rows(rows[name], fields) for name, fields in columns.items()}
    return hashlib.sha256(json.dumps({'columns': columns, 'rows': normalized}, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def transfer(path, connection, expected_bootstrap_sha256, expected_identity):
    """One transaction, native schema/markers intact; caller owns exclusive operation fencing."""
    import graphlib
    from psycopg import sql
    source = read_source(path)
    with connection.transaction():
        connection.execute('SET TRANSACTION ISOLATION LEVEL SERIALIZABLE')
        identity = connection.execute('SELECT current_database(),current_user,system_identifier::text FROM pg_control_system()').fetchone()
        if tuple(identity) != tuple(expected_identity):
            raise ValueError('Wrong native database identity')
        connection.execute(sql.SQL('LOCK TABLE {} IN EXCLUSIVE MODE').format(sql.SQL(',').join(sql.Identifier('public', n) for n in sorted(TABLES))))
        initial, columns = read_target(connection)
        if fingerprint(initial, columns) != expected_bootstrap_sha256:
            raise ValueError('Target is not the exact accepted fresh stock generation')
        if any(set(source['columns'][name]) != set(columns[name]) for name in TABLES):
            raise ValueError('Source/target column coverage differs')
        for name in TABLES:
            canonical_rows(source['rows'][name], columns[name])
        if any(canonical_rows(source['rows'][name], columns[name]) != canonical_rows(initial[name], columns[name]) for name in MARKERS):
            raise ValueError('Native migration markers differ; refusing rewrite')
        application = TABLES - MARKERS
        dependencies = {name: set() for name in application}
        for child, parent in connection.execute("SELECT c.relname,p.relname FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid JOIN pg_class p ON p.oid=k.confrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE k.contype='f' AND n.nspname='public'"):
            if child in application and parent in application:
                dependencies[child].add(parent)
        order = list(graphlib.TopologicalSorter(dependencies).static_order())
        connection.execute(sql.SQL('TRUNCATE {}').format(sql.SQL(',').join(sql.Identifier('public', n) for n in sorted(application))))
        for name in order:
            fields = columns[name]
            for row in source['rows'][name]:
                values = []
                for key, kind in fields.items():
                    value = row[key]
                    if value is not None and kind == 'boolean':
                        value = bool(value)
                    elif value is not None and kind == 'timestamp without time zone':
                        value = datetime.datetime.fromisoformat(timestamp(value))
                    values.append(value)
                placeholders = [sql.SQL('%s::json') if kind == 'json' else sql.Placeholder() for kind in fields.values()]
                connection.execute(sql.SQL('INSERT INTO {} ({}) VALUES ({})').format(sql.Identifier('public', name), sql.SQL(',').join(map(sql.Identifier, fields)), sql.SQL(',').join(placeholders)), values)
        serials = connection.execute("SELECT table_name,column_name,pg_get_serial_sequence(format('%I.%I',table_schema,table_name),column_name) FROM information_schema.columns WHERE table_schema='public' AND column_default LIKE 'nextval(%'").fetchall()
        for table, column, sequence in serials:
            maximum = max([int(row[column]) for row in source['rows'][table] if row[column] is not None] + [int(source['sequenceFloors'].get(table, 0)), 0])
            # Never lower a native allocator, including deleted source AUTOINCREMENT IDs.
            current, called = connection.execute(sql.SQL('SELECT last_value,is_called FROM {}').format(sql.Identifier(*sequence.split('.')))).fetchone()
            floor = max(maximum, current if called else current - 1)
            connection.execute('SELECT setval(%s::regclass,%s,%s)', (sequence, max(floor, 1), floor > 0))
        actual, final_columns = read_target(connection)
        if final_columns != columns:
            raise ValueError('Native catalog changed')
        proof = compare(source['rows'], actual, columns)
        proof.update({'sourceSHA256': source['sourceSHA256'], 'serialFloorsChecked': len(serials), 'nativeMigrationMarkersUnchanged': True})
    return proof
