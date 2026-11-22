#!/usr/bin/env python3
"""Refuse a retained volume without its identity marker; read only, never repair data.

Apps that check native content own their guard in their manifests dir.
"""
import os
from pathlib import Path
import re
import stat
import sys


def validate(app, root):
    if not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', app) or root.absolute() != root.resolve(strict=True) or not root.is_dir():
        raise ValueError('Invalid retained root or application')
    marker = root / ('.homelab-' + app + '-data')
    with os.fdopen(os.open(marker, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= 128:
            raise ValueError('Invalid retained identity')
        if source.read(129) != ('homelab/' + app + '/data/v1\n').encode():
            raise ValueError('Wrong retained identity')


if __name__ == '__main__':
    try:
        if len(sys.argv) != 3:
            raise ValueError('Expected application and retained root')
        validate(sys.argv[1], Path(sys.argv[2]))
    except (OSError, ValueError, RuntimeError):
        print('Retained state refused; recovery acceptance is required.', file=sys.stderr)
        raise SystemExit(1) from None
    print('Retained identity accepted.')
