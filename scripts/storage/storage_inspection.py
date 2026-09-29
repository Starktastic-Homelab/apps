"""Local-only diagnostics. Reports are observations, never release evidence."""
from contextlib import contextmanager
from datetime import datetime
import json
import os
from pathlib import Path
import re
import stat

from render_storage import record_hash, render

LIMIT = 1024**2
DIRECTORY = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


@contextmanager
def _open_path(root, relative=''):
    """Walk every component with no-follow descriptors, including root parents."""
    root = Path(root)
    if not root.is_absolute() or '..' in root.parts:
        raise ValueError('Invalid root')
    parts = root.parts[1:] + Path(relative).parts
    fd = os.open('/', DIRECTORY)
    try:
        for index, part in enumerate(parts):
            flags = DIRECTORY if index < len(parts)-1 or not relative else os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
            next_fd = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        yield fd
    finally:
        os.close(fd)


def _signature(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


class _Snapshot:
    def __init__(self, root):
        self.root = root
        self.seen = {}

    def read(self, name, *, content=True):
        try:
            with _open_path(self.root, name) as fd:
                info = os.fstat(fd)
                self.seen[name] = _signature(info)
                if not stat.S_ISREG(info.st_mode) or info.st_size > LIMIT:
                    raise ValueError('Unsafe file')
                data = b''
                if content:
                    while len(data) <= LIMIT:
                        chunk = os.read(fd, min(65536, LIMIT+1-len(data)))
                        if not chunk:
                            break
                        data += chunk
                    if len(data) > LIMIT:
                        raise ValueError('Oversized file')
                return data, info
        except FileNotFoundError:
            self.seen[name] = None
            raise

    def stable(self):
        for name, expected in self.seen.items():
            try:
                with _open_path(self.root, name) as fd:
                    current = _signature(os.fstat(fd))
            except FileNotFoundError:
                current = None
            except (OSError, ValueError):
                return False
            if current != expected:
                return False
        return True


def _check(report, name, status, message, **details):
    report['checks'].append(dict(id=name, status=status, message=message, details=details))


def _object(data):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate key')
            result[key] = value
        return result
    result = json.loads(data, object_pairs_hook=pairs)
    if not isinstance(result, dict):
        raise ValueError('Expected object')
    return result


def _age(timestamp, now):
    observed = datetime.fromisoformat(timestamp)
    if observed.tzinfo is None or observed > now:
        raise ValueError('Unusable timestamp')
    return int((now-observed).total_seconds())


def _strings(data, keys):
    return all(isinstance(data.get(key), str) and data[key] for key in keys)


def inspect_state(root: Path, service: str, *, now: datetime) -> dict:
    report = dict(schema=1, command='status', service='jellyfin' if service == 'jellyfin' else 'unsupported',
                  scope='local-only', observed_at=now.isoformat(), checks=[],
                  live_verified=False, release_authorized=False)
    if service != 'jellyfin':
        _check(report, 'service', 'fail', 'Unsupported service.')
        return report
    snapshot = _Snapshot(root)
    try:
        with _open_path(root) as fd:
            root_identity = _signature(os.fstat(fd))[:2]
    except FileNotFoundError:
        _check(report, 'state_root', 'unknown', 'State root is missing.')
        return report
    except (OSError, ValueError):
        _check(report, 'state_root', 'fail', 'State root is unsafe or inaccessible.')
        return report
    _check(report, 'state_root', 'pass', 'State root opened without symlinks.')
    data = {}
    prefix = 'operations/jellyfin/'
    files = dict(runner='runner-instance', ownership='operation.json', record=prefix+'record.json',
                 stages=prefix+'stages.json', placement=prefix+'placement.json',
                 first_write=prefix+'target-may-have-written.json')
    ages = {}
    for name, path in files.items():
        try:
            raw, info = snapshot.read(path)
            data[name] = raw.decode().strip() if name == 'runner' else _object(raw)
            ages[name] = max(0, int(now.timestamp()-info.st_mtime)) if info.st_mtime <= now.timestamp() else None
        except FileNotFoundError:
            _check(report, name, 'unknown', 'Required state is missing.')
        except (OSError, ValueError, UnicodeError, RecursionError):
            _check(report, name, 'fail', 'State is malformed, unsafe or inaccessible.')

    for name, value in data.items():
        try:
            details = dict(file_age_seconds=ages[name])
            if name == 'runner':
                valid = bool(re.fullmatch(r'[a-zA-Z0-9-]{1,128}', value))
            elif name == 'ownership':
                valid = (type(value.get('schema')) is int and value['schema'] == 1 and
                         _strings(value, ('owner', 'nonce', 'operation', 'instance', 'stage', 'created_at')) and
                         value['instance'] == data.get('runner') and
                         bool(re.fullmatch(r'[a-z][a-z0-9-]{0,63}', value['stage'])))
                if valid:
                    details['stage'] = value['stage']
            elif name == 'record':
                valid = value.get('service') == service
                if valid:
                    render(value)
                    details['record_hash'] = record_hash(value)
            elif name == 'stages':
                valid = bool(value) and 'target-held' in value and all(
                    isinstance(v, str) and re.fullmatch(r'[0-9a-f]{40}', v) and
                    re.fullmatch(r'[a-z][a-z0-9-]{0,63}', k) for k, v in value.items())
            elif name == 'placement':
                valid = value.get('old_writer_mode') in ('clean-unmount', 'fenced') and all(
                    isinstance(value.get(k), dict) and _strings(value[k], ('hostname', 'node_uid', 'smbios_uuid', 'ssh_host'))
                    for k in ('previous', 'next'))
                if valid and value['old_writer_mode'] == 'fenced':
                    old = value['previous']
                    valid = _strings(old, ('node', 'name')) and type(old.get('vmid')) is int and old['vmid'] > 0
            else:
                valid = (value.get('target_may_have_written') is True and 'record' in data and
                         value.get('record_hash') == record_hash(data['record']))
            if not valid:
                _check(report, name, 'fail', 'State is invalid or contradictory.')
                continue
            timestamp = value.get('created_at' if name == 'ownership' else 'recorded_at') if name in ('ownership', 'first_write') else None
            if name in ('ownership', 'first_write'):
                try:
                    details['evidence_age_seconds'] = _age(timestamp, now)
                except (ValueError, TypeError, OverflowError):
                    _check(report, name, 'unknown', 'Evidence timestamp is missing, naive or in the future.')
                    continue
            if ages[name] is None:
                _check(report, name, 'unknown', 'File timestamp is in the future.')
            else:
                _check(report, name, 'pass', 'Local state structure is consistent; live identity is unverified.', **details)
        except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
            _check(report, name, 'fail', 'State is malformed or contradictory.')

    for name, filename in [('onboarding_journal', 'onboarding.jsonl'), ('snapshot_journal', 'snapshot-intent.jsonl')]:
        try:
            _, info = snapshot.read(prefix+filename, content=False)
            age = int(now.timestamp()-info.st_mtime)
            _check(report, name, 'unknown', 'Journal exists; completion requires separate reconciliation.',
                   file_age_seconds=age if age >= 0 else None)
        except FileNotFoundError:
            _check(report, name, 'not_checked', 'No journal present.')
        except (OSError, ValueError):
            _check(report, name, 'fail', 'Journal is unsafe or inaccessible.')
    stable = snapshot.stable()
    try:
        with _open_path(root) as fd:
            stable = stable and _signature(os.fstat(fd))[:2] == root_identity
    except (OSError, ValueError):
        stable = False
    _check(report, 'snapshot', 'pass' if stable else 'unknown',
           'No observed file changes; this is not a transaction.' if stable else 'State changed during inspection; repeat the observation.')
    _check(report, 'runtime_evidence', 'not_checked', 'Legacy state does not establish installed runtime revisions.')
    _check(report, 'live', 'not_checked', 'Live identity, bindings and writer authorization were not checked.')
    return report
