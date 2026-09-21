#!/usr/bin/env python3
"""Fixed reviewed operations on the external maintenance runner."""
import argparse
import base64
from contextlib import nullcontext
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
from maintenance import require_maintenance
from nas_rpc import NAS
from nfs_sync import inspect, apply_standard, reconcile
from onboard import onboard, reconcile_onboarding, snapshot_policy, read_chap
from verify import verify_existing
from initiator_probe import probe_filesystem, SSHRunner
from render_storage import render, record_hash, STAMP
from release import authorize, hold

ROOT = Path('/maintenance/operations/jellyfin')
PRIVATE = Path('/maintenance/private')


def kube(*arguments, data=None):
    result = subprocess.run(['kubectl'] + list(arguments), input=json.dumps(data) if data is not None else None,
                            capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise RuntimeError('Kubernetes observation/mutation failed; remain held')
    return json.loads(result.stdout) if result.stdout.strip() else None


def mutate_kube(*arguments, data=None):
    require_maintenance()
    return kube(*arguments, data=data)


def runner(node):
    return SSHRunner(node['ssh_host'], PRIVATE/'worker-key', PRIVATE/'worker-known-hosts')


def observe_release(nas, record):
    """Construct release evidence from live reads, never from a supplied passed=true JSON."""
    require_maintenance()
    ns = kube('get', 'namespace', record['namespace'], '-o', 'json')
    placement = json.loads((ROOT/'placement.json').read_text())
    node = placement['next']
    live = kube('get', 'node', node['hostname'], '-o', 'json')
    labels = live['metadata']['labels']
    if (live['metadata']['uid'] != node['node_uid'] or live['status']['nodeInfo']['systemUUID'].lower() != node['smbios_uuid']
            or labels.get('storage.starktastic.net/generation') != node['smbios_uuid']
            or labels.get('storage.starktastic.net/node-uid') != node['node_uid']
            or labels.get('storage.starktastic.net/iscsi-ready') != 'true'):
        raise ValueError('Selected worker generation/labels changed')
    deployment = kube('-n', record['namespace'], 'get', 'deployment', 'jellyfin', '-o', 'json')
    job = kube('-n', record['namespace'], 'get', 'cronjob', 'jellyfin-ldap-library-sync', '-o', 'json')
    jobs = kube('-n', record['namespace'], 'get', 'jobs', '-o', 'json')['items']
    if deployment['spec']['replicas'] != 0 or job['spec'].get('suspend') is not True or any(
            j.get('status', {}).get('active', 0) and any(o.get('name') == job['metadata']['name'] for o in j['metadata'].get('ownerReferences', [])) for j in jobs):
        raise ValueError('Jellyfin or its API jobs are not held')
    pods = kube('-n', record['namespace'], 'get', 'pods', '-o', 'json')['items']
    if any(v.get('persistentVolumeClaim', {}).get('claimName') in ('jellyfin-config', record['pvc'])
           for p in pods for v in p['spec'].get('volumes', [])):
        raise ValueError('A config consumer still exists; do not replace an uncertain writer')
    authorization = kube('-n', record['namespace'], 'get', 'configmap', 'retained-jellyfin-authorization', '-o', 'json')
    if authorization.get('data', {}).get('released') != 'false':
        raise ValueError('Placement changes require an existing closed authorization')
    chap = kube('-n', 'retained-iscsi', 'get', 'secret', 'retained-jellyfin-chap', '-o', 'json')
    if not all(chap.get('data', {}).get(k) for k in ('node.session.auth.username', 'node.session.auth.password')):
        raise ValueError('Sealed CHAP has not recovered')
    expected_chap = read_chap()
    if any(base64.b64decode(chap['data'][key]).decode() != expected_chap[field]
           for key, field in [('node.session.auth.username', 'user'), ('node.session.auth.password', 'secret')]):
        raise ValueError('Recovered CHAP differs from the verified target credential')
    previous = placement['previous']
    old_runner = runner(previous)
    if placement['old_writer_mode'] == 'clean-unmount':
        # Verify the SSH destination is the reviewed old generation before trusting
        # its absence of mounts/sessions. An unreachable worker requires fencing.
        identity = old_runner.run(['cat', '/sys/class/dmi/id/product_uuid'])
        if identity.returncode or identity.stdout.strip().lower() != previous['smbios_uuid']:
            raise ValueError('Old worker SSH generation mismatch')
        sessions = old_runner.run(['iscsiadm', '-m', 'session'])
        path = '/dev/disk/by-path/ip-' + record['portal'] + '-iscsi-' + record['iqn'] + '-lun-' + str(record['lun'])
        mounts = old_runner.run(['findmnt', '-rn', '-S', path])
        if sessions.returncode not in (0, 21) or (sessions.returncode == 0 and record['iqn'] in sessions.stdout.split()) or mounts.returncode != 1:
            raise ValueError('Old worker still owns the target or cannot prove clean unmount')
        old = dict(kind='clean-unmount', verified=True, mounts=0, sessions=0)
    elif placement['old_writer_mode'] == 'fenced':
        from proxmox_fence import PVE, verify_vm
        receipt = json.loads((ROOT/'previous-fence.json').read_text())
        expected = {k: previous[k] for k in ('node', 'vmid', 'name', 'smbios_uuid')}
        if receipt.get('expected') != expected or receipt.get('verified') is not True:
            raise ValueError('Fence receipt belongs to a different generation')
        status = verify_vm(PVE(PRIVATE/'pve-fence.json', PRIVATE/'pve-ca.pem', PRIVATE/'pve-leaf.sha256'), expected)
        if status['status'] != 'stopped':
            raise ValueError('Previously fenced VM is no longer stopped')
        old = dict(kind='fenced', verified=True, current_status='stopped', generation_matches=True)
    else:
        raise ValueError('Explicit old-writer proof is required')
    old['observed_at'] = datetime.now(timezone.utc).isoformat()
    current_runner = runner(node)
    identity = current_runner.run(['cat', '/sys/class/dmi/id/product_uuid'])
    if identity.returncode or identity.stdout.strip().lower() != node['smbios_uuid']:
        raise ValueError('New worker SSH generation mismatch')
    disk = current_runner.run(['python3', '-c', "import os,json;s=os.statvfs('/');print(json.dumps({'free':s.f_bavail*s.f_frsize,'total':s.f_blocks*s.f_frsize}))"])
    if disk.returncode:
        raise ValueError('Worker disk space observation failed')
    space = json.loads(disk.stdout)
    config = kube('get', '--raw', '/api/v1/nodes/' + node['hostname'] + '/proxy/configz')['kubeletconfig']
    hard = config['evictionHard']
    # This pilot requires percentage disk thresholds so remaining headroom can be
    # checked without guessing units; other configurations need explicit review.
    for key in ('nodefs.available', 'imagefs.available'):
        threshold = hard.get(key, '')
        if not threshold.endswith('%') or space['free'] - 12 * 1024**3 <= space['total'] * float(threshold[:-1]) / 100:
            raise ValueError('Disposable cache budget conflicts with eviction headroom')
    result = verify_existing(nas, record)
    result.update(probe_filesystem(record, current_runner))
    generation = {k: node[k] for k in ('hostname', 'node_uid', 'smbios_uuid')}
    result.update(record_hash=record_hash(record), namespace_uid=ns['metadata']['uid'], node=generation,
                  held=True, chap_present=True, free_bytes=space['free'], eviction_checked=True,
                  observed_at=datetime.now(timezone.utc).isoformat(), old_writer=old)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['inspect', 'nfs-inspect', 'nfs-apply', 'nfs-reconcile', 'onboard',
        'reconcile-onboarding', 'snapshot', 'snapshot-reconcile', 'hold', 'verify', 'release', 'render'])
    args = parser.parse_args()
    record_path = ROOT/'record.json'
    if args.operation not in ('inspect', 'nfs-inspect', 'reconcile-onboarding', 'render'):
        require_maintenance()
    with NAS(PRIVATE/'nas.credentials', PRIVATE/'nas-ca.pem', PRIVATE/'nas-leaf.sha256') if args.operation not in ('hold', 'render') else nullcontext() as nas:
        if args.operation.startswith('nfs-'):
            policy = json.loads(Path(__file__).with_name('nfs-sync.json').read_text())
            journal = Path('/maintenance/operations/nfs-standard.jsonl')
            if args.operation == 'nfs-inspect': result = inspect(nas, policy)
            elif args.operation == 'nfs-reconcile': result = reconcile(nas, policy, journal)
            else: result = apply_standard(nas, policy, json.loads(Path('/maintenance/operations/nfs-backup-coverage.json').read_text()), journal)
        elif args.operation in ('onboard', 'reconcile-onboarding'):
            if args.operation == 'onboard':
                intent = json.loads((Path(__file__).resolve().parents[2]/'storage/services/jellyfin.json').read_text())
                result = onboard(nas, intent, ROOT/'onboarding.jsonl')
            else: result = reconcile_onboarding(nas, ROOT/'onboarding.jsonl')
            # Do not publish an unfinished native-only record as a deployable filesystem record.
            from maintenance_lock import _write
            _write(ROOT/'native-record.json', result)
        elif args.operation in ('snapshot', 'snapshot-reconcile'):
            result = snapshot_policy(nas, ROOT/'snapshot-intent.jsonl', reconcile=args.operation.endswith('reconcile'))
        else:
            source = record_path if record_path.exists() or args.operation != 'hold' else Path(__file__).resolve().parents[2]/'storage/services/jellyfin.json'
            record = json.loads(source.read_text())
            if args.operation == 'inspect': result = verify_existing(nas, record)
            elif args.operation == 'render': result = {'apiVersion': 'v1', 'kind': 'List', 'items': render(record)}
            elif args.operation == 'hold':
                result = mutate_kube('apply', '-f', '-', '-o', 'json', data=hold(record))
            else:
                verification = observe_release(nas, record)
                if args.operation == 'release':
                    cm = authorize(record, verification, verification['namespace_uid'], verification['node'])
                    mutate_kube('annotate', 'namespace', record['namespace'], STAMP+'='+verification['namespace_uid'], '--overwrite', '-o', 'json')
                    result = mutate_kube('apply', '-f', '-', '-o', 'json', data=cm)
                else: result = verification
    print(json.dumps(result))


if __name__ == '__main__':
    main()
