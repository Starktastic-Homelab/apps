#!/usr/bin/env python3
"""Read retained identity and native headers; never open SQLite or repair data."""
import os
from pathlib import Path
import stat
import sys

LAYOUTS = {
    'sonarr': ('sonarr.db', 'logs.db', 'config.xml'),
    'sonarr-ru': ('sonarr.db', 'logs.db', 'config.xml'),
    'radarr': ('radarr.db', 'logs.db', 'config.xml'),
    'radarr-ru': ('radarr.db', 'logs.db', 'config.xml'),
    'lidarr': ('lidarr.db', 'logs.db', 'config.xml'),
    'cleanuparr': ('DataProtection-Keys/', 'jwt-key.bin', 'plex-client-id.txt'),
    'navidrome': ('navidrome.db',),
    'audiobookshelf': ('config/absdatabase.sqlite', 'metadata/'),
    'shelfmark': ('users.db', 'settings.json', '.flask_secret'),
    'cineplete': ('config/config.yml', 'data/overrides.json', 'data/results.json'),
}


def validate(app, root):
    if app not in LAYOUTS or root.absolute() != root.resolve(strict=True) or not root.is_dir():
        raise ValueError('Invalid retained root or application')
    if app == 'cleanuparr':
        expected = {'DATABASE_PROVIDER': 'postgres', 'POSTGRES_HOST': 'postgres-postgresql.databases',
                    'POSTGRES_PORT': '5432', 'POSTGRES_USER': 'cleanuparr', 'POSTGRES_DB': 'cleanuparr'}
        if any(os.environ.get(key) != value for key, value in expected.items()):
            raise ValueError('Wrong database backend')
        password = os.environ.get('POSTGRES_PASS', '')
        if not password or len(password.encode()) > 4096 or any(c in password for c in '\0\r\n'):
            raise ValueError('Invalid database credential')
        keyring = root / 'DataProtection-Keys'
        if not stat.S_ISDIR(keyring.lstat().st_mode):
            raise ValueError('Invalid retained keyring')
        keys = list(keyring.glob('key-*.xml'))
        if not keys or any(not stat.S_ISREG(p.lstat().st_mode) or not 0 < p.stat().st_size <= 65536 for p in keys):
            raise ValueError('Missing preserved data-protection keys')
        if (root / 'jwt-key.bin').lstat().st_size != 32:
            raise ValueError('Invalid preserved JWT key')
        for database in ('cleanuparr.db', 'events.db', 'users.db'):
            for suffix in ('', '-wal', '-shm', '-journal'):
                path = root / (database + suffix)
                if path.exists() or path.is_symlink():
                    raise ValueError('Active SQLite fallback')
    marker = root / ('.homelab-' + app + '-data')
    with os.fdopen(os.open(marker, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= 128:
            raise ValueError('Invalid retained identity')
        if source.read(129) != ('homelab/' + app + '/data/v1\n').encode():
            raise ValueError('Wrong retained identity')
    for name in LAYOUTS[app]:
        path = root
        parts = Path(name).parts
        for part in parts[:-1]:
            path = path / part
            if not stat.S_ISDIR(path.lstat().st_mode):
                raise ValueError('Invalid retained parent directory')
        path = path / parts[-1]
        if name.endswith('/'):
            if not stat.S_ISDIR(path.lstat().st_mode):
                raise ValueError('Missing retained directory')
            continue
        with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as source:
            info = os.fstat(source.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size == 0:
                raise ValueError('Missing retained file')
            if path.suffix in ('.db', '.sqlite') and source.read(16) != b'SQLite format 3\0':
                raise ValueError('Invalid native SQLite header')


if __name__ == '__main__':
    try:
        if len(sys.argv) != 3:
            raise ValueError('Expected application and retained root')
        validate(sys.argv[1], Path(sys.argv[2]))
    except (OSError, ValueError, RuntimeError):
        print('Retained media state refused; recovery acceptance is required.', file=sys.stderr)
        raise SystemExit(1) from None
    print('Retained media identity and native paths accepted.')
