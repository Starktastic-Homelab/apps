#!/usr/bin/env python3
"""Check retained monitoring identity and native paths without changing data.

Native block/WAL parsing belongs to the exact application images and qualified
recovery checks. This guard prevents missing-volume bootstrap; it is not a backup
integrity checker and does not repair any file.
"""
import os
from pathlib import Path
import stat
import sys

LAYOUTS = {
    'prometheus': (('prometheus-db', 'prometheus-db/wal'), ()),
    'alertmanager': (('alertmanager-db',), ('alertmanager-db/silences', 'alertmanager-db/nflog')),
    'loki': (('wal', 'chunks', 'tsdb-shipper-active', 'compactor'), ()),
    'tempo': (('wal', 'traces'), ()),
}


def validate(app, root):
    if app not in LAYOUTS or root.absolute() != root.resolve(strict=True) or not root.is_dir():
        raise ValueError('Invalid retained root or application')
    marker = root / ('.homelab-' + app + '-data')
    fd = os.open(marker, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as file:
        info = os.fstat(file.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= 128:
            raise ValueError('Invalid retained identity file')
        if file.read(129) != ('homelab/' + app + '/data/v1\n').encode():
            raise ValueError('Wrong retained identity')
    directories, files = LAYOUTS[app]
    for name in directories:
        path = root
        for part in Path(name).parts:
            path = path / part
            if not stat.S_ISDIR(path.lstat().st_mode):
                raise ValueError('Missing native retained directory')
    for name in files:
        path = root / name
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode):
            raise ValueError('Missing native retained file')


if __name__ == '__main__':
    try:
        if len(sys.argv) != 3:
            raise ValueError('Expected application and retained root')
        validate(sys.argv[1], Path(sys.argv[2]))
    except (OSError, ValueError, RuntimeError):
        print('Retained monitoring state refused; recovery acceptance is required.', file=sys.stderr)
        raise SystemExit(1) from None
    print('Retained monitoring identity and native paths accepted.')
