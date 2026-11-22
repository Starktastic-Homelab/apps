#!/usr/bin/env python3
"""Refuse missing/wrong retained changedetection.io state; read headers without repair or writes."""
import json
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


def native_json(root, name):
    raw = native_file(root, name, 64 * 1024 * 1024 + 1)
    if len(raw) > 64 * 1024 * 1024:
        raise ValueError('Oversized native configuration')
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError('Wrong native configuration type')
    return value


def validate(app, root):
    if app not in ('changedetection',):
        raise ValueError('Guard serves changedetection.io only')
    if not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', app) or root.absolute() != root.resolve(strict=True) or not stat.S_ISDIR(root.lstat().st_mode):
        raise ValueError('Invalid retained application or root')
    identity = native_file(root, '.homelab-' + app + '-data', 129)
    if identity != ('homelab/' + app + '/data/v1\n').encode():
        raise ValueError('Wrong retained identity')
    for name in ('changedetection.json', 'secret.txt'):
        native_file(root, name, 1)
    native_json(root, 'changedetection.json')
    if len(native_file(root, 'secret.txt', 65)) != 64:
        raise ValueError('Wrong preserved application secret')


if __name__ == '__main__':
    try:
        if len(sys.argv) != 3:
            raise ValueError('Expected application and root')
        validate(sys.argv[1], Path(sys.argv[2]))
    except (OSError, ValueError, RuntimeError, UnicodeError):
        print('Retained changedetection.io state refused; verified recovery is required.', file=sys.stderr)
        raise SystemExit(1) from None
    print('Retained changedetection.io identity and native state headers accepted.')
