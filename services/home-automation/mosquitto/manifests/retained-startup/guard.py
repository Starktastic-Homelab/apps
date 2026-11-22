#!/usr/bin/env python3
"""Refuse missing/wrong retained Mosquitto state; read headers without repair or writes."""
import os
from pathlib import Path
import re
import stat
import struct
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


def validate_mqtt(root):
    with os.fdopen(os.open(root / 'mosquitto.db', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as source:
        info = os.fstat(source.fileno())
        header = source.read(23)
        if not stat.S_ISREG(info.st_mode) or len(header) != 23 or header[:15] != b'\x00\xb5\x00mosquitto db' or int.from_bytes(header[19:23], 'big') != 6:
            raise ValueError('Wrong Mosquitto persistence format')
        configuration = False
        while source.tell() < info.st_size:
            chunk = source.read(8)
            if len(chunk) != 8:
                raise ValueError('Truncated Mosquitto chunk header')
            kind, length = struct.unpack('!II', chunk)
            if kind not in range(1, 7) or not 0 < length <= info.st_size - source.tell():
                raise ValueError('Truncated or unknown Mosquitto chunk')
            if kind == 1:
                if configuration or length != 16:
                    raise ValueError('Invalid Mosquitto configuration chunk')
                body = source.read(length)
                if body[9] != 8:
                    raise ValueError('Wrong Mosquitto identifier width')
                configuration = True
            else:
                source.seek(length, os.SEEK_CUR)
        if not configuration:
            raise ValueError('Missing Mosquitto configuration chunk')


def validate(app, root):
    if app not in ('mosquitto',):
        raise ValueError('Guard serves Mosquitto only')
    if not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', app) or root.absolute() != root.resolve(strict=True) or not stat.S_ISDIR(root.lstat().st_mode):
        raise ValueError('Invalid retained application or root')
    identity = native_file(root, '.homelab-' + app + '-data', 129)
    if identity != ('homelab/' + app + '/data/v1\n').encode():
        raise ValueError('Wrong retained identity')
    validate_mqtt(root)


if __name__ == '__main__':
    try:
        if len(sys.argv) != 3:
            raise ValueError('Expected application and root')
        validate(sys.argv[1], Path(sys.argv[2]))
    except (OSError, ValueError, RuntimeError, UnicodeError):
        print('Retained Mosquitto state refused; verified recovery is required.', file=sys.stderr)
        raise SystemExit(1) from None
    print('Retained Mosquitto identity and native state headers accepted.')
