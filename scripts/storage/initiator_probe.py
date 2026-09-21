"""Inspect an existing ext4 target without repairing it or disturbing CSI sessions."""
import json
import os
from pathlib import Path
import shlex
import subprocess
from maintenance import require_maintenance
from onboard import read_chap

# Executed on the selected worker against a read-only mount. SQLite opens only
# private DB+WAL copies, never the mounted source.
SQLITE_COPY_CHECK = r'''
import json, pathlib, shutil, sqlite3, sys, tempfile
root=pathlib.Path(sys.argv[1]); record=json.loads(sys.argv[2])
marker=json.loads((root/'.retained-volume.json').read_text())
if marker != {k:record[k] for k in ('service','marker','filesystem_uuid')}:
    raise ValueError('Service marker mismatch')
if not (root/'data/data/jellyfin.db').is_file():
    raise ValueError('Existing Jellyfin database required')
checked=0
for db in root.rglob('*.db'):
    if db.is_symlink() or not db.resolve().is_relative_to(root.resolve()):
        raise ValueError('Database link escapes retained source')
    with db.open('rb') as stream:
        if stream.read(16) != b'SQLite format 3\x00':
            continue
    with tempfile.TemporaryDirectory(prefix='retained-sqlite-', dir='/var/tmp') as scratch:
        copy=pathlib.Path(scratch)/db.name
        shutil.copyfile(db,copy)
        wal=pathlib.Path(str(db)+'-wal')
        if wal.exists():
            if wal.is_symlink(): raise ValueError('Unexpected WAL link')
            shutil.copyfile(wal,str(copy)+'-wal')
        with sqlite3.connect(copy.as_uri()+'?mode=rw',uri=True) as connection:
            if connection.execute('pragma integrity_check').fetchall()!=[('ok',)]:
                raise ValueError('Private SQLite copy is corrupt')
        checked+=1
if not checked: raise ValueError('No SQLite database verified')
print(json.dumps({'sqlite_verified':True,'marker_verified':True}))
'''


class SSHRunner:
    """Use reviewed worker SSH identity and pinned host keys, never ambient config."""
    def __init__(self, host, key, known_hosts):
        if not host or host.startswith('-') or any(c.isspace() for c in host):
            raise ValueError('Invalid reviewed SSH destination')
        self.prefix = ['ssh', '-F', '/dev/null', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
                       '-o', 'UserKnownHostsFile=' + str(known_hosts), '-i', str(key), host]

    def run(self, args, **kwargs):
        return subprocess.run(self.prefix + [shlex.join(['sudo', '-n', '--'] + args)],
                              text=True, capture_output=True, timeout=120, **kwargs)


def probe_filesystem(record, runner):
    require_maintenance()
    if not record.get('filesystem_uuid') or not record.get('marker'):
        raise ValueError('Existing filesystem UUID and service marker are required')

    def run(args, allowed=(0,), mutation=False):
        if mutation:
            require_maintenance()
        result = runner.run(args)
        if result.returncode not in allowed:
            # Never log iscsiadm auth arguments or remote stderr.
            raise RuntimeError('Retained probe command failed: ' + args[0])
        return result

    sessions = run(['iscsiadm', '-m', 'session'], allowed=(0, 21))
    if sessions.returncode == 0 and record['iqn'] in sessions.stdout.split():
        raise RuntimeError('Existing target session: do not update or disconnect a CSI owner')
    bypath = '/dev/disk/by-path/ip-' + record['portal'] + '-iscsi-' + record['iqn'] + '-lun-' + str(record['lun'])
    if run(['findmnt', '-rn', '-S', bypath], allowed=(0, 1)).returncode != 1:
        raise RuntimeError('Existing mount prevents probe node-record changes')
    base = ['iscsiadm', '-m', 'node', '-T', record['iqn'], '-p', record['portal']]
    chap = read_chap()
    run(base + ['--op', 'new'], mutation=True)
    for key, value in [('node.session.auth.authmethod', 'CHAP'), ('node.session.auth.username', chap['user']),
                       ('node.session.auth.password', chap['secret']), ('node.startup', 'manual')]:
        run(base + ['--op', 'update', '-n', key, '-v', value], mutation=True)
    # Exit 15 means an existing session, not ownership. Never logout after it.
    run(base + ['--login'], mutation=True)
    mounted = False
    directory = None
    try:
        run(['udevadm', 'settle', '--timeout=30'])
        device = run(['readlink', '-e', bypath]).stdout.strip()
        if not device.startswith('/dev/'):
            raise RuntimeError('No verified block device')
        props = dict(line.split('=', 1) for line in run(['udevadm', 'info', '--query=property', '--name', device]).stdout.splitlines() if '=' in line)
        if props.get('ID_SCSI_SERIAL') != record['serial'] or props.get('ID_WWN_WITH_EXTENSION') != record['naa']:
            raise RuntimeError('Exported device identity mismatch')
        if int(run(['blockdev', '--getsize64', device]).stdout) != record['bytes']:
            raise RuntimeError('Device capacity mismatch')
        if json.loads(run(['lsblk', '-J', '-o', 'NAME,TYPE', device]).stdout)['blockdevices'][0].get('children'):
            raise RuntimeError('Partitioned target refused')
        if run(['findmnt', '-rn', '-S', device], allowed=(0, 1)).returncode != 1:
            raise RuntimeError('Target already mounted')
        fs = dict(line.split('=', 1) for line in run(['blkid', '-p', '-o', 'export', device], allowed=(0, 2)).stdout.splitlines() if '=' in line)
        if fs.get('TYPE') != 'ext4' or fs.get('UUID') != record['filesystem_uuid']:
            raise RuntimeError('Blank or foreign filesystem refused')
        header = run(['dumpe2fs', '-h', device]).stdout
        state = next((line.split(':', 1)[1].strip() for line in header.splitlines() if line.startswith('Filesystem state:')), '')
        if state != 'clean' or 'needs_recovery' in header:
            raise RuntimeError('Filesystem needs explicit recovery; no automatic fsck or journal replay')
        directory = run(['mktemp', '-d', '/var/tmp/retained-probe.XXXXXXXX'], mutation=True).stdout.strip()
        if not directory.startswith('/var/tmp/retained-probe.'):
            raise RuntimeError('Invalid private probe directory')
        run(['mount', '-t', 'ext4', '-o', 'ro,noload', device, directory], mutation=True)
        mounted = True
        result = json.loads(run(['python3', '-c', SQLITE_COPY_CHECK, directory,
                                  json.dumps({k: record[k] for k in ('service', 'marker', 'filesystem_uuid')})]).stdout)
        if result != {'sqlite_verified': True, 'marker_verified': True}:
            raise RuntimeError('Incomplete private-copy integrity verification')
        return {'filesystem_verified': True, 'filesystem_uuid': fs['UUID'], 'marker': record['marker']}
    finally:
        if mounted:
            # An unmount failure intentionally prevents logout beneath a live mount.
            run(['umount', directory], mutation=True)
            mounted = False
        if directory:
            run(['rmdir', directory], mutation=True)
        run(base + ['--logout'], mutation=True)
