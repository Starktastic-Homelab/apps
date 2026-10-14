#!/usr/bin/env python3
"""Exact typed Bazarr conversion proof, WAL materialization and real allocator discovery."""
import datetime
from contextlib import closing
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3

TABLES = ('system', 'table_announcements', 'table_blacklist', 'table_blacklist_movie',
          'table_episodes', 'table_episodes_subtitles', 'table_history', 'table_history_movie',
          'table_languages_profiles', 'table_movies', 'table_movies_rootfolder', 'table_movies_subtitles',
          'table_settings_languages', 'table_settings_notifier', 'table_shows', 'table_shows_rootfolder')
REVISION = '537e9b4d10e3'


def require(condition):
    if not condition:
        raise ValueError('Bazarr exact preservation refused')


def ident(value):
    return '"' + value.replace('"', '""') + '"'


def literal(value):
    return "'" + value.replace("'", "''") + "'"


def digest(rows):
    values = [json.dumps(row, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode() for row in rows]
    return hashlib.sha256(b''.join(sorted(hashlib.sha256(v).digest() for v in values))).hexdigest()


def snapshot(con):
    con.row_factory = sqlite3.Row
    require(con.execute('PRAGMA integrity_check').fetchone()[0] == 'ok')
    require(not con.execute('PRAGMA foreign_key_check').fetchall())
    names = {r[0] for r in con.execute("SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
    require(names == set(TABLES) | {'alembic_version'})
    revision = [r[0] for r in con.execute('SELECT version_num FROM alembic_version')]
    require(revision == [REVISION])
    sequences = dict(con.execute('SELECT name,seq FROM sqlite_sequence')) if con.execute("SELECT 1 FROM sqlite_schema WHERE name='sqlite_sequence'").fetchone() else {}
    result = {'revision': REVISION, 'tables': {}, 'allocators': {}}
    for table in TABLES:
        columns = [dict(row) for row in con.execute('PRAGMA table_info(' + ident(table) + ')')]
        rows = [dict(row) for row in con.execute('SELECT * FROM ' + ident(table))]
        floors = {}
        keys = [r for r in columns if r['pk']]
        if len(keys) == 1 and keys[0]['type'].upper() == 'INTEGER':
            name = keys[0]['name']
            maximum = max((r[name] for r in rows if r[name] is not None), default=0)
            require(isinstance(maximum, int))
            floors[name] = max(0, maximum, sequences.get(table, 0))
        result['tables'][table] = {'columns': columns, 'rows': rows}
        result['allocators'][table] = floors
    return result


def proof(value):
    hashes = {}
    for table, entry in value['tables'].items():
        rows = [{k: {'blob': bytes(v).hex()} if isinstance(v, (bytes, memoryview)) else v for k, v in row.items()} for row in entry['rows']]
        hashes[table] = digest(rows)
    return {'revision': value['revision'], 'counts': {k: len(v['rows']) for k, v in value['tables'].items()},
            'digests': hashes, 'allocators': value['allocators'],
            'schemaSHA256': hashlib.sha256(json.dumps({k: v['columns'] for k, v in value['tables'].items()}, sort_keys=True).encode()).hexdigest()}


def materialize(source: Path, destination: Path) -> dict:
    if source.is_symlink() or not source.is_file():
        raise ValueError('Invalid SQLite input')
    if destination.exists() or destination.is_symlink():
        raise FileExistsError('Materialization exists')
    with closing(sqlite3.connect(source.resolve().as_uri() + '?mode=ro', uri=True)) as original:
        original.execute('BEGIN')
        accepted = proof(snapshot(original))
        with closing(sqlite3.connect(destination)) as copied:
            original.backup(copied)
            require(copied.execute('PRAGMA journal_mode=DELETE').fetchone()[0] == 'delete')
            require(proof(snapshot(copied)) == accepted)
    require(not destination.with_name(destination.name + '-wal').exists())
    accepted['bytes'] = destination.stat().st_size
    with destination.open('rb') as file:
        accepted['sha256'] = hashlib.file_digest(file, 'sha256').hexdigest()
    return accepted


def normalized(value, kind):
    if value is None:
        return None
    if kind == 'bytea':
        if isinstance(value, (bytes, memoryview)):
            return {'blob': bytes(value).hex()}
        require(isinstance(value, str) and value.startswith('\\x'))
        return {'blob': bytes.fromhex(value[2:]).hex()}
    if kind == 'boolean':
        require(value in (0, 1, False, True))
        return bool(value)
    if kind in ('smallint', 'integer', 'bigint'):
        require(isinstance(value, int) and not isinstance(value, bool))
        return value
    if kind.startswith('timestamp'):
        require(isinstance(value, str))
        date = datetime.datetime.fromisoformat(value)
        require(date.tzinfo is None and kind == 'timestamp without time zone')
        return date.isoformat(timespec='microseconds')
    if kind in ('numeric', 'real', 'double precision'):
        number = Decimal(str(value))
        require(number.is_finite())
        return format(number.normalize(), 'f')
    require(kind in ('text', 'character varying', 'character') and isinstance(value, str))
    value.encode('utf-8')
    return value


def compare(sqlite: Path, postgres: dict) -> dict:
    require(postgres['database'] == postgres['role'] == 'bazarr' and postgres['revision'] == REVISION)
    require(not postgres['unvalidatedConstraints'] and not postgres['disabledTriggers'] and set(postgres['tables']) == set(TABLES))
    with closing(sqlite3.connect(sqlite.resolve().as_uri() + '?mode=ro', uri=True)) as con:
        con.execute('BEGIN')
        original = snapshot(con)
    counts, hashes = {}, {}
    for table in TABLES:
        src, pg = original['tables'][table], postgres['tables'][table]
        columns = pg['columns']
        require(set(columns) == {c['name'] for c in src['columns']})
        def fingerprint(rows):
            require(all(set(row) == set(columns) for row in rows))
            return digest([{k: normalized(v, columns[k]) for k, v in row.items()} for row in rows])
        require(len(src['rows']) == len(pg['rows']) and fingerprint(src['rows']) == fingerprint(pg['rows']))
        for column, floor in pg['sequenceFloors'].items():
            require(column in original['allocators'][table] and floor >= original['allocators'][table][column])
        counts[table], hashes[table] = len(src['rows']), fingerprint(src['rows'])
    return {'allTypedApplicationTablesPreserved': True, 'counts': counts, 'digests': hashes,
            'sourceAllocatorFloors': original['allocators'], 'revision': REVISION}


def capture(query) -> dict:
    require(query('SELECT current_database() AS database,current_user AS role') == [{'database': 'bazarr', 'role': 'bazarr'}])
    require({r['table_name'] for r in query("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE'")} == set(TABLES) | {'alembic_version'})
    require(query('SELECT version_num FROM public.alembic_version') == [{'version_num': REVISION}])
    result = {'database': 'bazarr', 'role': 'bazarr', 'revision': REVISION, 'tables': {},
              'unvalidatedConstraints': query("SELECT conname FROM pg_constraint WHERE connamespace='public'::regnamespace AND NOT convalidated"),
              'disabledTriggers': query("SELECT tgname FROM pg_trigger WHERE tgrelid IN (SELECT oid FROM pg_class WHERE relnamespace='public'::regnamespace) AND tgenabled='D'")}
    for table in TABLES:
        cols = query("SELECT column_name,data_type FROM information_schema.columns WHERE table_schema='public' AND table_name=" + literal(table) + ' ORDER BY ordinal_position')
        floors = {}
        for col in cols:
            sequence = query('SELECT pg_get_serial_sequence(' + literal('public.' + ident(table)) + ',' + literal(col['column_name']) + ') AS sequence')[0]['sequence']
            if sequence:
                name = query('SELECT n.nspname,c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE c.oid=' + literal(sequence) + '::regclass')[0]
                row = query('SELECT last_value,is_called FROM ' + ident(name['nspname']) + '.' + ident(name['relname']))[0]
                floors[col['column_name']] = row['last_value'] - int(not row['is_called'])
        result['tables'][table] = {'columns': {r['column_name']: r['data_type'] for r in cols},
                                   'rows': query('SELECT * FROM public.' + ident(table)), 'sequenceFloors': floors}
    return result
