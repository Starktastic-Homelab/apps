"""Explicit root publication of historical reconciliation; never writer authority."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import uuid

import storage_inspection as inspection
from storage_inspection import _Snapshot, _object, _open_path, _age, _protected_directory

INPUTS = ('record.json', 'onboarding.jsonl', 'snapshot-intent.jsonl')
READS = frozenset(('system.version', 'pool.query', 'pool.dataset.query', 'pool.snapshottask.query',
                  'iscsi.global.config', 'iscsi.extent.query', 'iscsi.target.query',
                  'iscsi.targetextent.query', 'iscsi.portal.query', 'iscsi.initiator.query', 'iscsi.auth.query'))


class ReadOnlyNAS:
    def __init__(self, nas): self.nas = nas

    def call(self, method, *params):
        if method not in READS: raise ValueError('Non-read-only NAS RPC refused')
        return self.nas.call(method, *params)


def generate(root, nas, *, now):
    from onboard import reconcile_onboarding, snapshot_policy
    snapshot = _Snapshot(Path(root)); prefix = 'operations/jellyfin/'
    raw = {name:snapshot.read(prefix+name)[0] for name in INPUTS}
    runner = snapshot.read('runner-instance')[0].decode().strip()
    record = _object(raw['record.json']); _age(now.isoformat(), now)
    read = ReadOnlyNAS(nas)
    # Validators consume private copies of the exact captured journal bytes.
    with tempfile.TemporaryDirectory(prefix='reconciliation-') as directory:
        path = Path(directory)
        for name in INPUTS: (path/name).write_bytes(raw[name])
        native = reconcile_onboarding(read, path/'onboarding.jsonl')
        if any(k not in record or record[k] != v for k,v in native.items()) or set(record)-set(native) not in (set(), {'filesystem_uuid'}):
            raise ValueError('Saved record conflicts with native allocation intent')
        verified = snapshot_policy(read, path/'snapshot-intent.jsonl', reconcile=True)
        if verified.get('verified') is not True: raise ValueError('Snapshot verification missing')
    if not snapshot.stable(): raise ValueError('Input evidence changed during reconciliation')
    return dict(schema=1, service='jellyfin', runner_instance=runner,
                scope='historical-native-reconciliation', observed_at=now.isoformat(),
                inputs={n:hashlib.sha256(raw[n]).hexdigest() for n in INPUTS},
                results={'onboarding':'verified', 'snapshot':'verified'})


def publish(root, nas, *, now):
    if os.geteuid() != 0: raise PermissionError('Receipt publication requires root')
    root = Path(root)
    with _protected_directory(inspection.RECONCILIATION_ROOT) as directory:
        info = os.fstat(directory)
        if info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError('Receipt directory must be root-owned and not group/other writable')
        try:
            os.stat('jellyfin-reconciliation.json', dir_fd=directory, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise FileExistsError('Receipt exists; preserve it and review explicit refresh separately')
        with _open_path(root, 'operations/jellyfin') as state_directory:
            state_info = os.fstat(state_directory)
            if state_info.st_uid != 0 or state_info.st_mode & 0o022:
                raise ValueError('Diagnostic directory is not protected')
        receipt = generate(root, nas, now=now)
        temporary = '.reconciliation-'+str(uuid.uuid4())+'.json'
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o640, dir_fd=directory)
        with os.fdopen(fd, 'w') as stream:
            os.fchown(stream.fileno(), 0, state_info.st_gid); os.fchmod(stream.fileno(), 0o640)
            json.dump(receipt, stream, sort_keys=True); stream.flush(); os.fsync(stream.fileno())
        os.link(temporary, 'jellyfin-reconciliation.json', src_dir_fd=directory, dst_dir_fd=directory, follow_symlinks=False)
        os.unlink(temporary, dir_fd=directory); os.fsync(directory)
        with _protected_directory(inspection.RECONCILIATION_ROOT) as current:
            fresh = os.fstat(current)
            if (fresh.st_dev, fresh.st_ino) != (info.st_dev, info.st_ino):
                raise ValueError('Receipt directory identity changed')
    return receipt


def runtime_imports():
    """Use only the active root-controlled installation, without PYTHONPATH."""
    with _protected_directory(inspection.RECONCILIATION_ROOT):
        raw, info = _Snapshot(inspection.RECONCILIATION_ROOT).read('installation.json')
    if info.st_uid != 0 or info.st_mode & 0o022: raise ValueError('Untrusted installation reference')
    installed = _object(raw); manifest_path = Path(installed['manifest'])
    release = Path(__file__).resolve().parents[3]
    if manifest_path != release/'manifest.json': raise ValueError('Producer is not the active runtime')
    helpers = release/'ansible/scripts'
    with _protected_directory(helpers):
        for name in ('maintenance_executor.py', 'maintenance_requests.py', 'maintenance_lock.py'):
            _, info = _Snapshot(helpers).read(name)
            if info.st_uid != 0 or info.st_mode & 0o022: raise ValueError('Untrusted runtime helper')
    sys.path.insert(0, str(helpers))
    from maintenance_executor import manifest
    from maintenance_requests import digest
    data = manifest(manifest_path)
    if data['schema'] != 2 or digest(data) != installed['runtime_id']: raise ValueError('Runtime identity mismatch')
    wheels = list((release/'dependencies/python').glob('*.whl'))
    if len(wheels) != 1: raise ValueError('Verified transport wheel unavailable')
    sys.path.insert(0, str(wheels[0]))
    return data


def bind_state(data, root):
    """Bind the execution guard to the installed manifest and runner identity."""
    root = Path(root)
    if root != Path(data['state_root']):
        raise ValueError('State directory differs from installed runtime')
    runner = _Snapshot(root).read('runner-instance')[0].decode().strip()
    if runner != data['runner_instance']:
        raise ValueError('Runner identity differs from installed runtime')
    return root


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('state-root', 'credentials', 'ca', 'leaf-pin'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--stage', required=True)
    args = parser.parse_args()
    if os.geteuid() != 0: raise PermissionError('Receipt publication requires root')
    credentials = _object(sys.stdin.buffer.read(4097))
    if set(credentials) != {'owner', 'nonce'}: raise ValueError('Expected original ownership credentials on private stdin')
    data = runtime_imports()
    root = bind_state(data, args.state_root)
    from maintenance_lock import execution
    from nas_rpc import NAS
    os.environ['HOMELAB_RUNNER_INSTANCE'] = data['runner_instance']
    with execution(root, credentials['owner'], credentials['nonce'], args.stage):
        with NAS(args.credentials, args.ca, args.leaf_pin) as nas:
            receipt = publish(root, nas, now=datetime.now(timezone.utc))
    print(json.dumps(receipt))


if __name__ == '__main__': main()
