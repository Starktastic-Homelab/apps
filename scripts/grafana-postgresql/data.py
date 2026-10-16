"""Strict Grafana conversion preparation; the source and native schema logs stay intact."""
import contextlib
import datetime
import hashlib
import os
import pathlib
import re
import sqlite3

MIGRATION_TABLES = frozenset({
    'migration_log', 'resource_migration_log', 'secret_migration_log',
    'unifiedstorage_migration_log',
})


def timestamp_literal(value):
    if not isinstance(value, str):
        raise ValueError('Expected a UTC timestamp string')
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        datetime.date.fromisoformat(value)
        return value
    legacy = re.fullmatch(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d{1,9})?) \+0000 UTC(?: m=[+-]\d+(?:\.\d{1,9})?)?', value)
    result = legacy[1] + '+00:00' if legacy else value
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|\+00:00)?', result):
        raise ValueError('Unrecognized or non-UTC timestamp representation')
    datetime.datetime.fromisoformat(result)
    return result


def character_literal(value, width):
    if not isinstance(value, str) or not isinstance(width, int) or width <= 0 or len(value) > width or '\x00' in value:
        raise ValueError('Value cannot fit the native fixed-character type')
    return value.ljust(width)


def materialize(source, destination, columns):
    source, destination = pathlib.Path(source), pathlib.Path(destination)
    if source.is_symlink() or not source.is_file():
        raise ValueError('A regular source copy is required')
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
    os.close(descriptor)
    changes = []
    with contextlib.closing(sqlite3.connect(source.absolute().as_uri() + '?mode=ro', uri=True)) as original, contextlib.closing(sqlite3.connect(destination)) as working:
        original.execute('PRAGMA query_only=ON')
        original.backup(working)
        with working:
            for column in columns:
                table, name = column['table_name'], column['column_name']
                if table in MIGRATION_TABLES or not column['data_type'].startswith('timestamp'):
                    continue
                table_sql = '"' + table.replace('"', '""') + '"'
                name_sql = '"' + name.replace('"', '""') + '"'
                values = [r[0] for r in working.execute(f'SELECT DISTINCT {name_sql} FROM {table_sql} WHERE {name_sql} IS NOT NULL')]
                for value in values:
                    normalized = timestamp_literal(value)
                    if normalized != value:
                        count = working.execute(f'UPDATE {table_sql} SET {name_sql}=? WHERE {name_sql}=?', (normalized, value)).rowcount
                        changes.append({'table': table, 'column': name, 'rows': count})
        if [r[0] for r in working.execute('PRAGMA integrity_check')] != ['ok'] or list(working.execute('PRAGMA foreign_key_check')):
            raise ValueError('Working-copy integrity check failed')
    if hashlib.sha256(source.read_bytes()).hexdigest() != before:
        raise ValueError('Source changed during working-copy preparation')
    return {'sourceSHA256': before, 'changedRows': sum(c['rows'] for c in changes), 'changes': changes}


def canonical_rows(rows, columns, source, timestamp_casts):
    """Preserve duplicates and every field; allow only explicit native SQL representations."""
    import json
    expected = {c['column_name'] for c in columns}
    result = []
    for row in rows:
        if set(row) != expected:
            raise ValueError('Unexpected row fields')
        normalized = {}
        for column in columns:
            name, kind = column['column_name'], column['data_type']
            value = row[name]
            if value is None:
                pass
            elif kind == 'bytea':
                if source:
                    if not isinstance(value, bytes):
                        raise ValueError('Expected binary source')
                    value = value.hex()
                else:
                    if not isinstance(value, str) or not value.startswith('\\x'):
                        raise ValueError('Expected native binary destination')
                    value = bytes.fromhex(value[2:]).hex()
            elif kind == 'boolean':
                if value not in (0, 1, False, True):
                    raise ValueError('Invalid boolean')
                value = bool(value)
            elif kind.startswith('timestamp'):
                if source:
                    timestamp_literal(value)
                    if value not in timestamp_casts:
                        raise ValueError('Missing native timestamp cast')
                    value = timestamp_casts[value]
                value = datetime.datetime.fromisoformat(timestamp_literal(value))
                value = value.replace(tzinfo=datetime.timezone.utc) if value.tzinfo is None else value
                value = value.astimezone(datetime.timezone.utc).isoformat(timespec='microseconds')
            elif kind in ('integer', 'bigint', 'smallint'):
                if type(value) is not int:
                    raise ValueError('Invalid integer')
            elif kind in ('text', 'character varying', 'character'):
                if source and isinstance(value, bytes):
                    original = value
                    value = value.decode('utf-8')
                    if value.encode('utf-8') != original:
                        raise ValueError('Non-round-tripping UTF-8')
                if not isinstance(value, str):
                    raise ValueError('Invalid text')
                if source and kind == 'character':
                    value = character_literal(value, column['character_maximum_length'])
            elif kind in ('json', 'jsonb'):
                value = json.loads(value) if source and isinstance(value, str) else value
            elif kind in ('real', 'double precision'):
                if type(value) not in (int, float):
                    raise ValueError('Invalid floating-point value')
                value = float(value)
            else:
                raise ValueError('Unhandled SQL type')
            normalized[name] = value
        result.append(json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False))
    return sorted(result)


def compare(source, target, columns, timestamp_casts):
    """Compare a read-only SQLite copy with private native PostgreSQL snapshots."""
    groups = {}
    for column in columns:
        if column['table_name'] not in MIGRATION_TABLES:
            groups.setdefault(column['table_name'], []).append(column)
    if set(target) != set(groups):
        raise ValueError('Incomplete destination table coverage')
    path = pathlib.Path(source)
    if path.is_symlink() or not path.is_file():
        raise ValueError('Regular source copy required')
    proof = {}
    with contextlib.closing(sqlite3.connect(path.absolute().as_uri() + '?mode=ro', uri=True)) as db:
        db.execute('PRAGMA query_only=ON')
        db.row_factory = sqlite3.Row
        names = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        extra = names - set(groups) - MIGRATION_TABLES
        if not set(groups) <= names or not extra <= {'entity_event', 'playlist', 'playlist_item'}:
            raise ValueError('Unexpected source tables')
        for name in extra:
            if db.execute('SELECT count(*) FROM "' + name + '"').fetchone()[0]:
                raise ValueError('Populated obsolete table cannot be omitted')
        for table, definitions in groups.items():
            quoted = '"' + table.replace('"', '""') + '"'
            rows = [dict(row) for row in db.execute('SELECT * FROM ' + quoted)]
            expected = canonical_rows(rows, definitions, True, timestamp_casts)
            actual = canonical_rows(target[table], definitions, False, timestamp_casts)
            if expected != actual:
                raise ValueError('Application field preservation rejected for ' + table)
            proof[table] = {'rows': len(expected), 'sha256': hashlib.sha256('\n'.join(expected).encode()).hexdigest()}
    return proof
