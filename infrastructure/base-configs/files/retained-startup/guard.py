#!/usr/bin/env python3
"""Refuse a retained volume without its identity marker; read only, never repair data.

Usage: guard.py <app> <root> [<kind> [<marker-file>]]. The marker is <root>/<marker-file>
(default .homelab-<app>-<kind>) and must hold exactly homelab/<app>/<kind>/v1 and a newline.
"""
import os
from pathlib import Path
import re
import stat
import sys


NAME = r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?'


def validate(app, root, kind='data', marker_file=None):
    if marker_file is None:
        marker_file = '.homelab-' + app + '-' + kind
    if (not re.fullmatch(NAME, app) or not re.fullmatch(NAME, kind)
            or not re.fullmatch(r'\.homelab-' + NAME + '-' + NAME, marker_file)
            or root.absolute() != root.resolve(strict=True) or not root.is_dir()):
        raise ValueError('Invalid retained root, application, kind or marker file')
    marker = root / marker_file
    with os.fdopen(os.open(marker, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= 128:
            raise ValueError('Invalid retained identity')
        if source.read(129) != ('homelab/' + app + '/' + kind + '/v1\n').encode():
            raise ValueError('Wrong retained identity')


if __name__ == '__main__':
    try:
        if not 3 <= len(sys.argv) <= 5:
            raise ValueError('Expected application, retained root, kind and marker file')
        validate(sys.argv[1], Path(sys.argv[2]), *sys.argv[3:])
    except (OSError, ValueError, RuntimeError):
        print('Retained state refused; recovery acceptance is required.', file=sys.stderr)
        raise SystemExit(1) from None
    print('Retained identity accepted.')
