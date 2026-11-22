#!/usr/bin/env python3
"""Read-only retained Grafana file identity and canonical PostgreSQL configuration guard."""
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

    if read(root / '.homelab-grafana-data', 128) != 'homelab/grafana/data/v1\n':
        raise ValueError('Wrong retained identity')
    if (root / 'plugins').is_symlink() or not (root / 'plugins').is_dir():
        raise ValueError('Missing retained plugins')
    for suffix in ('', '-wal', '-shm', '-journal'):
        path = root / ('grafana.db' + suffix)
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
    expected = {'GF_DATABASE_TYPE': 'postgres', 'GF_DATABASE_HOST': 'postgres-postgresql.databases:5432',
                'GF_DATABASE_NAME': 'grafana', 'GF_DATABASE_USER': 'grafana', 'GF_DATABASE_PASSWORD': password}
    if any(env.get(k) != v for k, v in expected.items()):
        raise ValueError('Wrong canonical database configuration')
    if any(env.get(k) for k in ('GF_DATABASE_URL', 'GF_DATABASE_PATH', 'GF_DATABASE_PASSWORD__FILE')):
        raise ValueError('Competing database configuration')


if __name__ == '__main__':
    try:
        if len(sys.argv) != 3:
            raise ValueError('Expected retained and credential directories')
        validate(Path(sys.argv[1]), Path(sys.argv[2]), os.environ)
    except (OSError, UnicodeError, ValueError):
        print('Retained Grafana state refused; restore acceptance is required.', file=sys.stderr)
        raise SystemExit(1) from None
    print('Retained Grafana identity accepted.')
