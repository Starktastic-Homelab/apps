#!/usr/bin/env python3
"""Read native retained state before any stock process can initialize or migrate it."""
import importlib.util
import os
from pathlib import Path
import sys

spec = importlib.util.spec_from_file_location('retained_base', Path(__file__).with_name('base.py'))
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
base.LAYOUTS = {
    'karakeep': ('db.db', 'queue.db'),
    'karakeep-meilisearch': ('.version_marker', 'data.ms/VERSION'),
    'bytestash': ('snippets.db',),
    'convertx': ('mydb.sqlite',),
    'home-assistant': ('home-assistant_v2.db', '.storage/core.uuid', '.storage/core.config_entries', 'configuration.yaml'),
    'home-assistant-matter': ('config/driver.json', 'certificates/driver.json'),
}


def validate(app, root):
    base.validate(app, root)
    if app == 'karakeep-meilisearch':
        for name, expected in (('.version_marker', b'meilisearch 1.55.0\n'), ('data.ms/VERSION', b'1.55.0')):
            with os.fdopen(os.open(root / name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as source:
                if source.read(129) != expected:
                    raise ValueError('Retained search engine version refused')


if __name__ == '__main__':
    try:
        if len(sys.argv) != 3:
            raise ValueError('Expected application and retained root')
        validate(sys.argv[1], Path(sys.argv[2]))
    except (OSError, ValueError, RuntimeError):
        print('Retained application state refused; recovery acceptance is required.', file=sys.stderr)
        raise SystemExit(1) from None
    print('Retained identity, native paths and engine accepted.')
