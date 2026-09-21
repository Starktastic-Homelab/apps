"""One-way NFS durability correction. An unknown outcome requires reconciliation."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import stat


def inspect(nas, expected):
    if expected['sync'] != 'STANDARD' or nas.call('system.version') != expected['version']:
        raise ValueError('Unexpected NAS version or requested policy')
    pools = nas.call('pool.query', [['name', '=', expected['pool']]])
    if len(pools) != 1 or pools[0]['name'] != expected['pool'] or str(pools[0]['guid']) != expected['pool_guid'] or pools[0]['status'] != 'ONLINE':
        raise ValueError('Pool identity or health mismatch')
    rows = nas.call('pool.dataset.query', [['id', '=', expected['dataset']]],
                    {'extra': {'properties': ['guid', 'sync']}})
    if len(rows) != 1:
        raise ValueError('Dataset missing or ambiguous')
    row = rows[0]
    if row['id'] != expected['dataset'] or str(row['guid']['value']) != expected['dataset_guid']:
        raise ValueError('Dataset identity mismatch')
    if row.get('children') or row['sync']['source'] != 'LOCAL':
        raise ValueError('Dataset hierarchy or sync inheritance changed; review required')
    return {'dataset_guid': expected['dataset_guid'], 'sync': row['sync']['value']}


def check_backup(receipt, expected):
    """Validate evidence coverage, not the truth of an operator's restore report."""
    try:
        captured = datetime.fromisoformat(receipt['captured_at'])
        age = (datetime.now(timezone.utc) - captured).total_seconds()
        apps = receipt['critical_applications']
        archives = receipt['archives']
        valid = (0 <= age <= 86400 and receipt['dataset_guid'] == expected['dataset_guid']
                 and bool(receipt['coverage_reviewed_by'].strip()) and bool(apps)
                 and 'postgresql' in apps and len(set(apps)) == len(apps)
                 and isinstance(archives, list) and bool(archives))
        covered = set()
        for item in archives:
            valid = valid and (type(item['bytes']) is int and item['bytes'] > 0
                    and bool(re.fullmatch('[0-9a-f]{64}', item['sha256']))
                    and item['integrity'] == item['restore'] == 'passed'
                    and item['consistency'] in ('cold', 'database-native')
                    and bool(item['evidence'].strip()))
            covered.add(item['application'])
        if not valid or not set(apps).issubset(covered):
            raise ValueError()
    except (KeyError, TypeError, ValueError, AttributeError):
        raise ValueError('Missing, invalid, stale or incomplete backup/restore evidence') from None


def journal_event(path, event, *, create=False):
    flags = os.O_WRONLY | os.O_NOFOLLOW | (os.O_CREAT | os.O_EXCL if create else os.O_APPEND)
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, 'a') as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError('Journal must be a regular file')
        stream.write(json.dumps(event, sort_keys=True) + '\n')
        stream.flush()
        os.fsync(stream.fileno())
    directory = os.open(Path(path).parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def apply_standard(nas, expected, backup_receipt, journal):
    # Even STANDARD after a lost response must take the explicit reconciliation path.
    if os.path.lexists(journal):
        raise FileExistsError('Existing intent: inspect and reconcile; never retry allocation/update')
    before = inspect(nas, expected)
    if before['sync'] == 'STANDARD':
        return {'changed': False, 'verified': True}
    if before['sync'] != 'DISABLED':
        raise ValueError('Unexpected current sync policy')
    check_backup(backup_receipt, expected)
    journal_event(journal, {'state': 'intent', 'expected': expected,
                  'started_at': datetime.now(timezone.utc).isoformat(),
                  'backup': backup_receipt}, create=True)
    try:
        nas.call('pool.dataset.update', expected['dataset'], {'sync': 'STANDARD'})
        if inspect(nas, expected)['sync'] != 'STANDARD':
            raise RuntimeError('Sync readback did not confirm STANDARD')
    except Exception:
        journal_event(journal, {'state': 'needs-reconciliation'})
        raise
    journal_event(journal, {'state': 'verified'})
    return {'changed': True, 'verified': True}


def reconcile(nas, expected, journal):
    fd = os.open(journal, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd) as stream:
        events = [json.loads(line) for line in stream]
    if not events or events[0].get('state') != 'intent' or events[0].get('expected') != expected:
        raise ValueError('Journal does not match the reviewed intent')
    if inspect(nas, expected)['sync'] != 'STANDARD':
        raise RuntimeError('Not STANDARD; remain held for operator inspection, no retry')
    journal_event(journal, {'state': 'verified', 'reconciled': True})
    return {'verified': True, 'reconciled': True}


def main():
    from nas_rpc import NAS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['inspect', 'apply-standard', 'reconcile'])
    parser.add_argument('--policy', type=Path, default=Path(__file__).with_name('nfs-sync.json'))
    parser.add_argument('--credentials', required=True, type=Path)
    parser.add_argument('--ca', required=True, type=Path)
    parser.add_argument('--leaf-pin', required=True, type=Path)
    parser.add_argument('--backup-receipt', type=Path)
    parser.add_argument('--journal', type=Path)
    args = parser.parse_args()
    if args.operation != 'inspect' and not args.journal:
        parser.error('--journal required for apply/reconcile')
    if args.operation == 'apply-standard' and not args.backup_receipt:
        parser.error('--backup-receipt required for apply')
    expected = json.loads(args.policy.read_text())
    with NAS(args.credentials, args.ca, args.leaf_pin) as nas:
        if args.operation == 'inspect':
            result = inspect(nas, expected)
        elif args.operation == 'reconcile':
            result = reconcile(nas, expected, args.journal)
        else:
            result = apply_standard(nas, expected, json.loads(args.backup_receipt.read_text()), args.journal)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
