"""Configure an owned Debian open-iscsi node using private stdin, never argv."""
import json
import os
from pathlib import Path
import stat
import sys


def node_path(root, iqn, portal):
    if not iqn.startswith('iqn.') or any(c in iqn for c in '/\\\n\r'):
        raise ValueError('Invalid target identity')
    host, port = portal.rsplit(':', 1)
    if not host or any(c in host for c in '/\\\n\r') or not port.isdigit():
        raise ValueError('Invalid portal')
    directory = root / iqn
    if directory.is_symlink():
        raise ValueError('Node directory is a symlink')
    return directory / (host + ',' + port)


def check_new(root, iqn, portal):
    node = node_path(root, iqn, portal)
    if node.parent.exists() and any(node.parent.iterdir()):
        raise ValueError('Existing node requires reconciliation before probe')


def configure(root, iqn, portal, chap):
    node = node_path(root, iqn, portal)
    if node.is_symlink() or not node.is_file() or list(node.parent.iterdir()) != [node]:
        raise ValueError('Expected one owned Debian node record')
    changes = {'node.session.auth.authmethod': 'CHAP',
               'node.session.auth.username': chap['user'],
               'node.session.auth.password': chap['secret'], 'node.startup': 'manual'}
    if any(not isinstance(v, str) or not v or any(c in v for c in '\r\n\0') for v in changes.values()):
        raise ValueError('Invalid private node configuration')
    descriptor = os.open(node, os.O_RDWR | os.O_NOFOLLOW)
    with os.fdopen(descriptor, 'r+') as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError('Invalid node record type')
        lines = stream.read().splitlines()
        for key, value in changes.items():
            matches = [i for i, line in enumerate(lines) if line.startswith(key + ' = ')]
            if len(matches) > 1:
                raise ValueError('Ambiguous node configuration')
            if matches:
                lines[matches[0]] = key + ' = ' + value
            elif key in ('node.session.auth.username', 'node.session.auth.password'):
                lines.append(key + ' = ' + value)
            else:
                raise ValueError('Missing node configuration field')
        os.fchmod(stream.fileno(), 0o600)
        stream.seek(0); stream.write('\n'.join(lines) + '\n'); stream.truncate()
        stream.flush(); os.fsync(stream.fileno())


if __name__ == '__main__':
    root = Path('/var/lib/iscsi/nodes')
    operation, iqn, portal = sys.argv[1:]
    if operation == 'check':
        check_new(root, iqn, portal)
    elif operation == 'configure':
        configure(root, iqn, portal, json.load(sys.stdin))
    else:
        raise ValueError('Unknown node operation')
