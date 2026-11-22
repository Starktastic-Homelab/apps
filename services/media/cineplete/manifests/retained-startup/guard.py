#!/usr/bin/env python3
"""Read retained Cineplete identity and native headers; never open SQLite or repair data."""
import os
from pathlib import Path
import re
import stat
import sys

LAYOUT = ('config/config.yml', 'data/overrides.json', 'data/results.json')


def validate(app, root):
    if app != 'cineplete':
        raise ValueError('Guard serves Cineplete only')
    if not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', app) or root.absolute() != root.resolve(strict=True) or not root.is_dir():
        raise ValueError('Invalid retained root or application')
    marker = root / ('.homelab-' + app + '-data')
    with os.fdopen(os.open(marker, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= 128:
            raise ValueError('Invalid retained identity')
        if source.read(129) != ('homelab/' + app + '/data/v1\n').encode():
            raise ValueError('Wrong retained identity')
    for name in LAYOUT:
        path = root
        parts = Path(name).parts
        for part in parts[:-1]:
            path = path / part
            if not stat.S_ISDIR(path.lstat().st_mode):
                raise ValueError('Invalid retained parent directory')
        path = path / parts[-1]
        with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as source:
            info = os.fstat(source.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size == 0:
                raise ValueError('Missing retained file')


if __name__ == '__main__':
    try:
        if len(sys.argv) != 3:
            raise ValueError('Expected application and retained root')
        validate(sys.argv[1], Path(sys.argv[2]))
    except (OSError, ValueError, RuntimeError):
        print('Retained Cineplete state refused; recovery acceptance is required.', file=sys.stderr)
        raise SystemExit(1) from None
    print('Retained Cineplete identity and native paths accepted.')
