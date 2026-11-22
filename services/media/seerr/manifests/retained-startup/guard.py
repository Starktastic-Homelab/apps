#!/usr/bin/env python3
"""Read-only retained Seerr settings acceptance; never generates or prints secrets."""
import json
import os
from pathlib import Path
import sys
from typing import Mapping


def validate(root: Path, instance: str, env: Mapping[str, str]) -> None:
    if instance not in ('seerr', 'seerr-ru') or root.is_symlink() or not root.is_dir():
        raise ValueError('Invalid retained identity')

    def read(name):
        p = root / name
        if p.is_symlink() or not p.is_file() or p.stat().st_size > 128 * 1024:
            raise ValueError('Invalid retained file')
        return p.read_text()

    if read('.homelab-seerr-config') != f'homelab/{instance}/config/v1\n':
        raise ValueError('Wrong retained identity')

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate setting')
            result[key] = value
        return result

    def invalid_constant(_):
        raise ValueError('Invalid JSON constant')

    settings = json.loads(read('settings.json'), object_pairs_hook=unique, parse_constant=invalid_constant)
    if not isinstance(settings, dict) or not isinstance(settings.get('main'), dict):
        raise ValueError('Invalid retained settings')
    required = [settings['main'].get('apiKey'), *(settings.get(k) for k in
                ('sessionSecret', 'clientId', 'vapidPublic', 'vapidPrivate'))]
    if any(not isinstance(v, str) or not v.strip() for v in required):
        raise ValueError('Missing preserved identifier')
    expected = {'NODE_ENV': 'production', 'DB_TYPE': 'postgres',
                'DB_HOST': 'postgres-postgresql.databases', 'DB_PORT': '5432',
                'DB_USER': instance.replace('-', '_'), 'DB_NAME': instance.replace('-', '_'), 'DB_POOL_SIZE': '3'}
    if any(env.get(k) != v for k, v in expected.items()):
        raise ValueError('Wrong database configuration')
    password = env.get('DB_PASS', '')
    if not password.strip() or len(password.encode()) > 4096 or any(c in password for c in '\0\r\n'):
        raise ValueError('Invalid database credential')
    if (env.get('DB_SOCKET_PATH') or env.get('CONFIG_DIRECTORY', '/app/config') != '/app/config'
            or (env.get('API_KEY') and env['API_KEY'] != settings['main']['apiKey'])):
        raise ValueError('Conflicting configuration override')
    database = root / 'db'
    if database.is_symlink() or (database.exists() and not database.is_dir()):
        raise ValueError('Invalid database path')
    for suffix in ('', '-wal', '-shm', '-journal'):
        path = database / ('db.sqlite3' + suffix)
        if path.exists() or path.is_symlink():
            raise ValueError('Active SQLite fallback')


if __name__ == '__main__':
    try:
        if len(sys.argv) != 3:
            raise ValueError('Expected config directory and instance')
        validate(Path(sys.argv[1]), sys.argv[2], os.environ)
    except (OSError, ValueError):
        print('Retained Seerr configuration is invalid; restore acceptance is required.', file=sys.stderr)
        raise SystemExit(1) from None
    print('Retained Seerr settings and database configuration accepted.')
