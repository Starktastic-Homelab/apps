"""Strict typed preservation for pinned Excalidash and CrowdSec providers."""
import datetime
import decimal
import hashlib
import json
import math
import re
import struct

APPS = frozenset({'crowdsec', 'excalidash'})
KINDS = frozenset({'smallint', 'integer', 'bigint', 'boolean', 'text', 'character varying',
                  'bytea', 'real', 'double precision', 'json', 'jsonb',
                  'timestamp with time zone', 'timestamp without time zone'})
TABLES = {
    'excalidash': frozenset({'ApiKey', 'AuditLog', 'AuthIdentity', 'ChatGptAuthState',
        'ChatGptConnection', 'Collection', 'CollectionShare', 'Drawing', 'DrawingFile',
        'DrawingLinkShare', 'DrawingPermission', 'DrawingSnapshot', 'Library',
        'PasswordResetToken', 'RefreshToken', 'SystemConfig', 'User'}),
    'crowdsec': frozenset({'alerts', 'allow_list_allowlist_items', 'allow_list_items',
        'allow_lists', 'bouncers', 'config_items', 'decisions', 'events', 'locks',
        'machines', 'meta', 'metrics'}),
}


def text(value):
    if not isinstance(value, str) or '\0' in value:
        raise ValueError('Invalid native text')
    try:
        value.encode('utf-8', errors='strict')
    except UnicodeError:
        raise ValueError('Invalid native text encoding') from None
    return value



def json_text(app, value, source):
    if source and app == 'crowdsec' and isinstance(value, (bytes, memoryview)):
        try:
            value = bytes(value).decode('utf-8', errors='strict')
        except UnicodeError:
            raise ValueError('Invalid native JSON encoding') from None
    return text(value)


def json_value(value):
    def pairs(items):
        out = {}
        for key, item in items:
            if key in out:
                raise ValueError('Duplicate JSON key')
            out[text(key)] = item
        return out
    def constant(_):
        raise ValueError('Nonfinite JSON')
    try:
        value = json.loads(text(value), object_pairs_hook=pairs,
                           parse_int=decimal.Decimal, parse_float=decimal.Decimal,
                           parse_constant=constant)
    except (json.JSONDecodeError, decimal.InvalidOperation):
        raise ValueError('Malformed JSON') from None
    def tree(item):
        if isinstance(item, decimal.Decimal):
            sign, digits, exponent = item.as_tuple()
            digits = list(digits)
            while len(digits) > 1 and digits[-1] == 0:
                digits.pop()
                exponent += 1
            if not any(digits):
                exponent = 0
            return ('number', sign, ''.join(map(str, digits)), exponent)
        if isinstance(item, str):
            return ('string', text(item))
        if isinstance(item, list):
            return ('array', [tree(v) for v in item])
        if isinstance(item, dict):
            return ('object', [(text(k), tree(item[k])) for k in sorted(item)])
        return ('literal', item)
    return tree(value)


def timestamp(app, value, kind, source):
    if source and app == 'excalidash' and type(value) is int:
        try:
            value = datetime.datetime(1970, 1, 1) + datetime.timedelta(milliseconds=value)
        except OverflowError:
            raise ValueError('Invalid epoch milliseconds') from None
    if isinstance(value, str):
        pattern = r'(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?(Z|[+-]\d{2}:\d{2})?'
        match = re.fullmatch(pattern, value)
        if not match:
            raise ValueError('Unrecognized timestamp')
        fraction = match[3] or ''
        if len(fraction) > 6:
            if not (source and app == 'crowdsec'):
                raise ValueError('Unapproved timestamp precision loss')
            fraction = fraction[:6]
        suffix = match[4] or ''
        if suffix and suffix != 'Z' and (int(suffix[1:3]) > 23 or int(suffix[4:6]) > 59):
            raise ValueError('Invalid timezone offset components')
        value = datetime.datetime.fromisoformat(match[1] + 'T' + match[2]
            + ('.' + fraction if fraction else '') + suffix.replace('Z', '+00:00'))
    if not isinstance(value, datetime.datetime):
        raise ValueError('Invalid timestamp type')
    if kind == 'timestamp with time zone':
        if value.tzinfo is None:
            if not (source and app == 'crowdsec'):
                raise ValueError('Missing native timezone')
            # Pinned CrowdSec writes UtcNow; its SQLite driver's naive form is UTC.
            value = value.replace(tzinfo=datetime.timezone.utc)
        value = value.astimezone(datetime.timezone.utc)
    elif value.tzinfo is not None:
        # Excalidash Prisma timestamps are UTC without time zone.
        if not (source and app == 'excalidash'):
            raise ValueError('Unexpected native timezone')
        value = value.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    return value.isoformat(timespec='microseconds')


def normalize(app, value, kind, source=False):
    if app not in APPS or kind not in KINDS:
        raise ValueError('Unexpected provider or native type')
    if value is None:
        return None
    if kind.startswith('timestamp '):
        return timestamp(app, value, kind, source)
    if kind == 'boolean':
        if type(value) not in (int, bool) or value not in (0, 1):
            raise ValueError('Invalid boolean')
        return bool(value)
    if kind in ('smallint', 'integer', 'bigint'):
        bits = {'smallint': 16, 'integer': 32, 'bigint': 64}[kind]
        if type(value) is not int or not -(2 ** (bits - 1)) <= value < 2 ** (bits - 1):
            raise ValueError('Lossy integer')
        return value
    if kind in ('text', 'character varying'):
        return text(value)
    if kind == 'bytea':
        if not isinstance(value, (bytes, memoryview)):
            raise ValueError('Invalid binary type')
        return ('bytes', bytes(value).hex())
    if kind in ('real', 'double precision'):
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError('Invalid floating value')
        if type(value) is int and int(float(value)) != value:
            raise ValueError('Lossy integer to float')
        value = float(value)
        try:
            if kind == 'real':
                native = struct.unpack('!f', struct.pack('!f', value))[0]
                if source and native != value:
                    raise ValueError('Lossy float32')
                value = native
        except OverflowError:
            raise ValueError('Lossy float32') from None
        return ('float', value.hex())
    return json_value(json_text(app, value, source))


def canonical_rows(app, rows, columns, source=False):
    if not columns or not set(columns.values()) <= KINDS:
        raise ValueError('Unexpected native field definitions')
    out = []
    for row in rows:
        if set(row) != set(columns):
            raise ValueError('Incomplete native field coverage')
        out.append(json.dumps({name: normalize(app, row[name], kind, source)
            for name, kind in columns.items()}, sort_keys=True, ensure_ascii=False,
            separators=(',', ':'), allow_nan=False))
    return sorted(out)


def marker_tables(app):
    if app not in APPS:
        raise ValueError('Unknown application')
    return frozenset({'_prisma_migrations'}) if app == 'excalidash' else frozenset()


def read_source(app, path):
    import contextlib
    import pathlib
    import sqlite3
    path = pathlib.Path(path)
    if path.is_symlink() or not path.is_file() or any(path.with_name(path.name + s).exists()
                                                   for s in ('-wal', '-journal')):
        raise ValueError('Standalone regular SQLite copy required')
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    with contextlib.closing(sqlite3.connect(path.absolute().as_uri() + '?mode=ro', uri=True)) as c:
        c.execute('PRAGMA query_only=ON')
        if c.execute('PRAGMA integrity_check').fetchall() != [('ok',)] or c.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('Source integrity refused')
        names = {r[0] for r in c.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
        if names - {'sqlite_sequence'} != TABLES[app] | marker_tables(app):
            raise ValueError('Source table coverage changed')
        c.row_factory = sqlite3.Row
        rows, columns = {}, {}
        for name in sorted(TABLES[app]):
            ident = '"' + name.replace('"', '""') + '"'
            rows[name] = [dict(r) for r in c.execute('SELECT * FROM ' + ident)]
            columns[name] = [r[1] for r in c.execute('PRAGMA table_info(' + ident + ')')]
        floors = dict(c.execute('SELECT name,seq FROM sqlite_sequence')) if 'sqlite_sequence' in names else {}
        if set(floors) - (TABLES[app] | marker_tables(app)) or any(type(v) is not int or v < 0 for v in floors.values()):
            raise ValueError('Source allocator history refused')
    if hashlib.sha256(path.read_bytes()).hexdigest() != before:
        raise ValueError('Source changed during read')
    return {'rows': rows, 'columns': columns, 'sequenceFloors': floors, 'sourceSHA256': before}


def read_target(app, connection):
    from psycopg import sql
    fields = connection.execute("SELECT table_name,column_name,data_type FROM information_schema.columns "
        "WHERE table_schema='public' ORDER BY table_name,ordinal_position").fetchall()
    columns = {}
    for table, name, kind in fields:
        columns.setdefault(table, {})[name] = kind
    if set(columns) != TABLES[app] | marker_tables(app) or any(not set(v.values()) <= KINDS for v in columns.values()):
        raise ValueError('Unexpected target schema')
    rows = {}
    for table, definitions in columns.items():
        expressions = [sql.SQL('{}::text AS {}').format(sql.Identifier(n), sql.Identifier(n))
                       if k in ('json', 'jsonb') else sql.Identifier(n) for n, k in definitions.items()]
        values = connection.execute(sql.SQL('SELECT {} FROM {}').format(sql.SQL(',').join(expressions),
            sql.Identifier('public', table))).fetchall()
        rows[table] = [dict(zip(definitions, row)) for row in values]
    return rows, columns


def fingerprint(app, rows, columns):
    if set(rows) != set(columns):
        raise ValueError('Incomplete target snapshot')
    canonical = {name: canonical_rows(app, rows[name], fields) for name, fields in columns.items()}
    return hashlib.sha256(json.dumps({'columns': columns, 'rows': canonical}, sort_keys=True,
        separators=(',', ':')).encode()).hexdigest()


def compare(app, source, target, columns):
    if set(source) != TABLES[app] or set(target) != set(columns) or set(target) != TABLES[app] | marker_tables(app):
        raise ValueError('Incomplete application table coverage')
    proofs = {}
    for name in sorted(TABLES[app]):
        expected = canonical_rows(app, source[name], columns[name], True)
        if expected != canonical_rows(app, target[name], columns[name]):
            raise ValueError('Complete field preservation failed for ' + name)
        proofs[name] = {'rows': len(expected), 'sha256': hashlib.sha256('\n'.join(expected).encode()).hexdigest()}
    return {'tables': len(proofs), 'rows': sum(v['rows'] for v in proofs.values()), 'proofs': proofs}


def adapted(app, value, kind):
    normalized = normalize(app, value, kind, True)
    if value is None:
        return None
    if kind.startswith('timestamp '):
        return datetime.datetime.fromisoformat(normalized)
    if kind == 'boolean':
        return normalized
    if kind in ('json', 'jsonb'):
        return json_text(app, value, True)
    return value


def transfer(app, path, connection, expected_bootstrap_sha256, expected_identity):
    """One native-schema transaction; populated targets and ambiguous generations refuse."""
    import graphlib
    from psycopg import sql
    source = read_source(app, path)
    with connection.transaction():
        connection.execute('SET TRANSACTION ISOLATION LEVEL SERIALIZABLE')
        actual = connection.execute('SELECT current_database(),current_user,system_identifier::text FROM pg_control_system()').fetchone()
        if tuple(actual) != tuple(expected_identity):
            raise ValueError('Wrong native database identity')
        names = sorted(TABLES[app] | marker_tables(app))
        connection.execute(sql.SQL('LOCK TABLE {} IN ACCESS EXCLUSIVE MODE').format(
            sql.SQL(',').join(sql.Identifier('public', n) for n in names)))
        initial, columns = read_target(app, connection)
        if fingerprint(app, initial, columns) != expected_bootstrap_sha256 or any(initial[n] for n in TABLES[app]):
            raise ValueError('Target is not the accepted empty native application generation')
        if any(set(source['columns'][n]) != set(columns[n]) for n in TABLES[app]):
            raise ValueError('Source/target column coverage differs')
        for name in TABLES[app]:
            canonical_rows(app, source['rows'][name], columns[name], True)
        dependencies = {name: set() for name in TABLES[app]}
        for child, parent in connection.execute("SELECT c.relname,p.relname FROM pg_constraint k "
            "JOIN pg_class c ON c.oid=k.conrelid JOIN pg_class p ON p.oid=k.confrelid "
            "JOIN pg_namespace n ON n.oid=c.relnamespace WHERE k.contype='f' AND n.nspname='public'"):
            if child not in dependencies or parent not in dependencies:
                raise ValueError('Unexpected native foreign-key dependency')
            dependencies[child].add(parent)
        for name in graphlib.TopologicalSorter(dependencies).static_order():
            fields = columns[name]
            placeholders = [sql.SQL('%s::' + kind) if kind in ('json', 'jsonb') else sql.Placeholder()
                            for kind in fields.values()]
            query = sql.SQL('INSERT INTO {} ({}) VALUES ({})').format(sql.Identifier('public', name),
                sql.SQL(',').join(map(sql.Identifier, fields)), sql.SQL(',').join(placeholders))
            for row in source['rows'][name]:
                connection.execute(query, [adapted(app, row[k], kind) for k, kind in fields.items()])
        target, final_columns = read_target(app, connection)
        if final_columns != columns or any(initial[n] != target[n] for n in marker_tables(app)):
            raise ValueError('Native schema/migration generation changed')
        result = compare(app, source['rows'], target, columns)
        serials = connection.execute("SELECT table_name,column_name,pg_get_serial_sequence(format('%I.%I',"
            "table_schema,table_name),column_name) FROM information_schema.columns WHERE table_schema='public' "
            "AND (column_default LIKE 'nextval(%' OR is_identity='YES')").fetchall()
        for table, column, sequence in serials:
            if table not in TABLES[app] or not sequence or not sequence.startswith('public.'):
                raise ValueError('Unexpected allocator scope')
            maximum = max([int(r[column]) for r in source['rows'][table] if r[column] is not None]
                          + [source['sequenceFloors'].get(table, 0), 0])
            current, called = connection.execute(sql.SQL('SELECT last_value,is_called FROM {}').format(
                sql.Identifier(*sequence.split('.')))).fetchone()
            restart = max(maximum + 1, current + int(called), 1)
            if restart >= 2**63:
                raise ValueError('Allocator floor cannot be preserved')
            # RESTART is transactional; refused imports cannot leave sequence side effects.
            connection.execute(sql.SQL('ALTER SEQUENCE {} RESTART WITH {}').format(
                sql.Identifier(*sequence.split('.')), sql.Literal(restart)))
        result.update({'sourceSHA256': source['sourceSHA256'], 'serialFloorsChecked': len(serials),
                       'nativeMigrationMarkersUnchanged': True, 'sourceUnchanged': True})
    return result


def allocators(app, connection):
    """Read sequence history without nextval, setval or any allocator mutation."""
    from psycopg import sql
    if app not in APPS:
        raise ValueError('Unknown application')
    serials = connection.execute("SELECT table_name,column_name,pg_get_serial_sequence(format('%I.%I',"
        "table_schema,table_name),column_name) FROM information_schema.columns WHERE table_schema='public' "
        "AND (column_default LIKE 'nextval(%' OR is_identity='YES') ORDER BY table_name,column_name").fetchall()
    result = {}
    for table, column, sequence in serials:
        if app not in APPS or table not in TABLES[app] or not sequence or not sequence.startswith('public.') or sequence in result:
            raise ValueError('Unexpected native allocator')
        definition = connection.execute('SELECT seqstart,seqincrement,seqmax,seqmin,seqcache,seqcycle '
                                        'FROM pg_sequence WHERE seqrelid=%s::regclass', (sequence,)).fetchone()
        last, called = connection.execute(sql.SQL('SELECT last_value,is_called FROM {}').format(
            sql.Identifier(*sequence.split('.')))).fetchone()
        if not definition or definition[1] != 1 or definition[5]:
            raise ValueError('Unsupported native allocator definition')
        result[sequence] = {'table': table, 'column': column, 'definition': list(definition),
                            'lastValue': last, 'isCalled': called}
    return result
