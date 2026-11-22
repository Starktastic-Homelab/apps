#!/usr/bin/env python3
"""Refuse missing/wrong retained Stirling-PDF state; read headers without repair or writes."""
import os
from pathlib import Path
import re
import stat
import sys


def native_file(root, name, limit=64 * 1024 * 1024):
    path = root
    for component in Path(name).parts[:-1]:
        path /= component
        if not stat.S_ISDIR(path.lstat().st_mode):
            raise ValueError('Redirected native parent')
    path /= Path(name).name
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size <= 0:
            raise ValueError('Missing native file')
        return source.read(limit)


def validate(app, root):
    if app not in ('stirling-pdf',):
        raise ValueError('Guard serves Stirling-PDF only')
    if not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', app) or root.absolute() != root.resolve(strict=True) or not stat.S_ISDIR(root.lstat().st_mode):
        raise ValueError('Invalid retained application or root')
    identity = native_file(root, '.homelab-' + app + '-data', 129)
    if identity != ('homelab/' + app + '/data/v1\n').encode():
        raise ValueError('Wrong retained identity')
    if not native_file(root, 'stirling-pdf-DB-2.3.232.mv.db', 32).startswith(b'H:2,'):
        raise ValueError('Wrong H2 MVStore header')


if __name__ == '__main__':
    try:
        if len(sys.argv) != 3:
            raise ValueError('Expected application and root')
        validate(sys.argv[1], Path(sys.argv[2]))
    except (OSError, ValueError, RuntimeError, UnicodeError):
        print('Retained Stirling-PDF state refused; verified recovery is required.', file=sys.stderr)
        raise SystemExit(1) from None
    print('Retained Stirling-PDF identity and native state headers accepted.')
