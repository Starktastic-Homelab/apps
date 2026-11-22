#!/usr/bin/env python3
"""Read-only retained pgAdmin file identity and canonical PostgreSQL configuration guard."""
import os
from pathlib import Path
import sys


def validate(root, credentials, env):
    if root.is_symlink() or not root.is_dir() or credentials.is_symlink() or not credentials.is_dir():
        raise ValueError('Invalid retained directory')

    def read(path, limit):
        if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= limit:
            raise ValueError('Invalid retained file')
        return path.read_text()

    if read(root / '.homelab-pgadmin-data', 128) != 'homelab/pgadmin/data/v1\n':
        raise ValueError('Wrong retained identity')
    for name in ('storage', 'sessions', 'azurecredentialcache'):
        if (root / name).is_symlink() or not (root / name).is_dir():
            raise ValueError('Missing retained private directory')
    for suffix in ('', '-wal', '-shm', '-journal', '.prev.bak'):
        path = root / ('pgadmin4.db' + suffix)
        if path.exists() or path.is_symlink():
            raise ValueError('Active SQLite fallback')
    try:
        password_path = (credentials / 'password').resolve(strict=True)
        if not password_path.is_relative_to(credentials.resolve(strict=True)):
            raise ValueError('Credential projection escapes its volume')
    except (OSError, RuntimeError) as error:
        raise ValueError('Invalid credential projection') from error
    password = read(password_path, 4096)
    if not password.strip() or any(c in password for c in '\0\r\n'):
        raise ValueError('Invalid database credential')
    import ast
    from urllib.parse import quote
    uri_path = (credentials / 'uri').resolve(strict=True)
    if not uri_path.is_relative_to(credentials.resolve(strict=True)):
        raise ValueError('URI projection escapes its volume')
    uri = ast.literal_eval(read(uri_path, 8192))
    expected_uri = 'postgresql://pgadmin:' + quote(password, safe='') + '@postgres-postgresql.databases:5432/pgadmin'
    if uri != expected_uri:
        raise ValueError('Wrong canonical database URI')
    expected = {'PGADMIN_CONFIG_CONFIG_DATABASE_URI_FILE': '/etc/pgadmin-postgres/uri',
                'PGADMIN_CONFIG_SQLALCHEMY_ENGINE_OPTIONS': "{'pool_size': 2, 'max_overflow': 1, 'pool_recycle': 300, 'pool_pre_ping': True}"}
    if any(env.get(k) != v for k, v in expected.items()):
        raise ValueError('Wrong canonical database configuration')
    if any(env.get(k) for k in ('PGADMIN_CONFIG_CONFIG_DATABASE_URI', 'PGADMIN_CUSTOM_CONFIG_DISTRO_FILE',
                                'PGADMIN_CONFIG_SQLALCHEMY_DATABASE_URI', 'PGADMIN_CONFIG_SQLITE_PATH')):
        raise ValueError('Competing database configuration')


if __name__ == '__main__':
    try:
        if len(sys.argv) != 3:
            raise ValueError('Expected retained and credential directories')
        validate(Path(sys.argv[1]), Path(sys.argv[2]), os.environ)
    except (OSError, UnicodeError, ValueError, SyntaxError, RuntimeError):
        print('Retained pgAdmin state refused; restore acceptance is required.', file=sys.stderr)
        raise SystemExit(1) from None
    print('Retained pgAdmin identity accepted.')
