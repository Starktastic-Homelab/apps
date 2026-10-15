#!/usr/bin/env python3
"""Reject missing/wrong retained ntfy state before stock startup; never write or print secrets."""
import os
from pathlib import Path
import sys
from typing import Mapping
from urllib.parse import quote


def validate(root: Path, credentials: Path, env: Mapping[str, str]) -> None:
    if root.is_symlink() or not root.is_dir() or credentials.is_symlink() or not credentials.is_dir():
        raise ValueError('Invalid retained directory')

    def read(path, limit):
        if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= limit:
            raise ValueError('Invalid retained file')
        return path.read_text()

    if read(root / '.homelab-ntfy-data', 128) != 'homelab/ntfy/data/v1\n':
        raise ValueError('Wrong retained identity')
    attachments = root / 'attachments'
    if attachments.is_symlink() or not attachments.is_dir():
        raise ValueError('Missing retained attachment directory')
    for name in ('cache.db', 'user.db', 'webpush.db'):
        for suffix in ('', '-wal', '-shm', '-journal'):
            path = root / (name + suffix)
            if path.exists() or path.is_symlink():
                raise ValueError('Active SQLite fallback')
    # Secret volume keys use kubelet atomic-writer links; the marker must remain a plain file.
    try:
        password_path = (credentials / 'password').resolve(strict=True)
        if not password_path.is_relative_to(credentials.resolve(strict=True)):
            raise ValueError('Credential projection escapes its volume')
    except (OSError, RuntimeError) as error:
        raise ValueError('Invalid credential projection') from error
    password = read(password_path, 4096)
    if not password.strip() or any(c in password for c in '\0\r\n'):
        raise ValueError('Invalid database credential')
    expected = 'postgresql://ntfy:' + quote(password, safe='') + '@postgres-postgresql.databases:5432/ntfy'
    if env.get('NTFY_DATABASE_URL') != expected:
        raise ValueError('Wrong database URL')
    for name in ('NTFY_AUTH_FILE', 'NTFY_CACHE_FILE', 'NTFY_WEB_PUSH_FILE', 'NTFY_DATABASE_REPLICA_URLS'):
        if env.get(name):
            raise ValueError('Conflicting database configuration')


if __name__ == '__main__':
    try:
        if len(sys.argv) != 3:
            raise ValueError('Expected retained and credential directories')
        validate(Path(sys.argv[1]), Path(sys.argv[2]), os.environ)
    except (OSError, UnicodeError, ValueError):
        print('Retained ntfy state refused; restore acceptance is required.', file=sys.stderr)
        raise SystemExit(1) from None
    print('Retained ntfy identity accepted.')
