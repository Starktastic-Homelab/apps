#!/usr/bin/env python3
"""Full-field SQLite/PostgreSQL ntfy comparison; only metadata and digests leave compare()."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3

TABLES = {
    'auth': {'tier': 'tier', 'user': 'user', 'user_access': 'user_access', 'user_token': 'user_token',
             'user_phone': 'user_phone', 'user_email': 'user_email', 'user_magic_link': 'user_magic_link'},
    'cache': {'messages': 'message', 'stats': 'message_stats'},
    'webpush': {'subscription': 'webpush_subscription', 'subscription_topic': 'webpush_subscription_topic'}}
VERSIONS = {'user': 9, 'message': 15, 'webpush': 1}


def canonical(rows):
    return sorted(json.dumps(row, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)
                  for row in rows)


def compare(paths: dict[str, Path], postgres: dict) -> dict:
    if set(paths) != set(TABLES) or postgres.get('versions') != VERSIONS:
        raise ValueError('Wrong ntfy stores or versions')
    expected_tables = {name for mapping in TABLES.values() for name in mapping.values()}
    if set(postgres.get('tables', {})) != expected_tables:
        raise ValueError('Unexpected PostgreSQL application tables')
    result = {}
    for store, mapping in TABLES.items():
        path = paths[store]
        if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= 64 * 1024**2:
            raise ValueError('Invalid source copy')
        for suffix in ('-wal', '-shm', '-journal'):
            sidecar = path.with_name(path.name + suffix)
            if sidecar.exists() or sidecar.is_symlink():
                raise ValueError('Source must be a standalone consistent SQLite backup')
        with path.open('rb') as file:
            original = hashlib.file_digest(file, 'sha256').hexdigest()
        try:
            with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro&immutable=1', uri=True)) as connection:
                connection.row_factory = sqlite3.Row
                names = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if names - {'schemaVersion', 'sqlite_sequence'} != set(mapping):
                    raise ValueError('Unexpected SQLite tables')
                version = connection.execute('SELECT version FROM schemaVersion WHERE id=1').fetchone()
                if version is None or version[0] != VERSIONS[{'auth': 'user', 'cache': 'message', 'webpush': 'webpush'}[store]]:
                    raise ValueError('Wrong SQLite schema version')
                for source, target in mapping.items():
                    rows = [dict(r) for r in connection.execute('SELECT * FROM "' + source + '"')]
                    if source in ('user_email', 'user_magic_link') and rows:
                        raise ValueError('Stock importer omits populated newer authentication stores')
                    expected = []
                    for row in rows:
                        converted = {}
                        for key, value in row.items():
                            if source == 'messages' and key == 'id':
                                continue  # Backend-local row IDs; externally used mid and sequence_id stay exact.
                            if key == 'user':
                                key = 'user_name' if source == 'user' else 'user_id'
                            datatype = postgres.get('types', {}).get(target, {}).get(key)
                            if datatype == 'boolean':
                                if type(value) is not int or value not in (0, 1):
                                    raise ValueError('Invalid SQLite boolean')
                                value = bool(value)
                            if datatype in ('json', 'jsonb'):
                                value = json.loads(value)
                            if isinstance(value, str):
                                if '\0' in value:
                                    raise ValueError('Lossy NUL conversion')
                                value.encode('utf-8')
                            converted[key] = value
                        expected.append(converted)
                    actual = postgres['tables'][target]
                    if source == 'messages':
                        if len({r['mid'] for r in rows}) != len(rows):
                            raise ValueError('Duplicate externally used message IDs')
                        actual = [{k: v for k, v in row.items() if k != 'id'} for row in actual]
                    if canonical(expected) != canonical(actual):
                        raise ValueError('ntfy table fields differ: ' + store + '.' + source)
                    encoded = '\n'.join(canonical(expected)).encode()
                    result[store + '.' + source] = {'rows': len(rows), 'sha256': hashlib.sha256(encoded).hexdigest()}
        except (sqlite3.Error, UnicodeError, TypeError, KeyError, json.JSONDecodeError):
            raise ValueError('Invalid ntfy source or target data') from None
        with path.open('rb') as file:
            if hashlib.file_digest(file, 'sha256').hexdigest() != original:
                raise ValueError('Source copy changed during comparison')
    return {'allApplicationFieldsPreserved': True, 'tables': result, 'schemaVersions': VERSIONS}
