#!/usr/bin/env python3
"""Read-only retained Bazarr configuration check; no app initialization or secrets output."""
import os
from pathlib import Path
import sys
from typing import Mapping

# The pinned Bazarr image carries its YAML parser with the application libraries.
if Path('/app/bazarr/bin/libs/yaml').is_dir():
    sys.path.insert(0, '/app/bazarr/bin/libs')
import yaml


class UniqueLoader(yaml.SafeLoader):
    pass


def mapping(loader, node, deep=False):
    result = {}
    for key, value in node.value:
        name = loader.construct_object(key, deep=deep)
        if name in result:
            raise ValueError('Duplicate configuration key')
        result[name] = loader.construct_object(value, deep=deep)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)


def validate(root: Path, env: Mapping[str, str]) -> None:
    if root.is_symlink() or not root.is_dir() or (root / 'config').is_symlink():
        raise ValueError('Invalid retained directory')

    def read(name, limit):
        path = root / name
        if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= limit:
            raise ValueError('Invalid retained file')
        return path.read_text()

    if read('.homelab-bazarr-config', 128) != 'homelab/bazarr/config/v1\n':
        raise ValueError('Wrong retained identity')
    try:
        settings = yaml.load(read('config/config.yaml', 512 * 1024), Loader=UniqueLoader)
    except (yaml.YAMLError, TypeError) as error:
        raise ValueError('Invalid retained YAML') from error
    if not isinstance(settings, dict) or not isinstance(settings.get('auth'), dict) or not isinstance(settings.get('general'), dict):
        raise ValueError('Missing retained configuration')
    required = (settings['auth'].get('apikey'), settings['general'].get('flask_secret_key'))
    if any(not isinstance(v, str) or not v.strip() for v in required):
        raise ValueError('Missing preserved identifier')
    expected = {'POSTGRES_ENABLED': 'true', 'POSTGRES_HOST': 'postgres-postgresql.databases',
                'POSTGRES_PORT': '5432', 'POSTGRES_DATABASE': 'bazarr', 'POSTGRES_USERNAME': 'bazarr'}
    if any(env.get(key) != value for key, value in expected.items()):
        raise ValueError('Wrong database configuration')
    password = env.get('POSTGRES_PASSWORD', '')
    if not password.strip() or len(password.encode()) > 4096 or any(c in password for c in '\0\r\n'):
        raise ValueError('Invalid database credential')
    pg = settings.get('postgresql', {})
    if not isinstance(pg, dict) or pg.get('enabled') is not True or pg.get('url') or env.get('POSTGRES_URL'):
        raise ValueError('Conflicting PostgreSQL URL')
    if (env.get('BAZARR_CONFIG_BASE_FILE_PATH', '/config/config') != '/config/config'
            or (env.get('BAZARR_APIKEY') and env['BAZARR_APIKEY'] != settings['auth']['apikey'])):
        raise ValueError('Conflicting retained configuration')
    database = root / 'db'
    if database.is_symlink() or (database.exists() and not database.is_dir()):
        raise ValueError('Invalid database directory')
    for suffix in ('', '-wal', '-shm', '-journal'):
        path = database / ('bazarr.db' + suffix)
        if path.exists() or path.is_symlink():
            raise ValueError('Active SQLite fallback')


if __name__ == '__main__':
    try:
        if len(sys.argv) != 2:
            raise ValueError('Expected retained configuration directory')
        validate(Path(sys.argv[1]), os.environ)
    except (OSError, ValueError):
        print('Retained Bazarr configuration refused; restore acceptance is required.', file=sys.stderr)
        raise SystemExit(1) from None
    print('Retained Bazarr configuration accepted.')
