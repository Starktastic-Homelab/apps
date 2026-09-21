"""Explicit one-time target allocation. Re-entry only inspects; never retries creates."""
import json
import os
from pathlib import Path
import stat
import uuid
from maintenance import require_maintenance
from nfs_sync import journal_event
from identity import verify_native
from verify import read_state


def read_chap():
    path = Path(os.environ['STORAGE_CHAP_FILE'])
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd) as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_uid != os.getuid():
            raise ValueError('CHAP file must be private and owned')
        data = json.load(stream)
    if not data.get('user') or not 12 <= len(data.get('secret', '')) <= 16:
        raise ValueError('CHAP requires a user and a 12–16 character secret')
    return data


def _one(rows, key, value):
    matches = [r for r in rows if r.get(key) == value]
    if len(matches) != 1:
        raise ValueError('Missing or ambiguous native object')
    return matches[0]


def _pool(nas, guid):
    if nas.call('system.version') != 'TrueNAS-25.10.7':
        raise ValueError('NAS version mismatch')
    pool = _one(nas.call('pool.query'), 'name', 'apps')
    if str(pool['guid']) != guid or pool['status'] != 'ONLINE':
        raise ValueError('Pool identity or health changed')


def _record(nas, intent, marker, serial, chap_user):
    dataset = _one(nas.call('pool.dataset.query', [['id', '=', intent['dataset']]],
                          {'extra': {'properties': ['guid', 'volsize', 'sync', 'volblocksize']}}), 'id', intent['dataset'])
    extent = _one(nas.call('iscsi.extent.query'), 'disk', 'zvol/' + intent['dataset'])
    target = _one(nas.call('iscsi.target.query'), 'name', intent['service'])
    if extent['serial'] != serial:
        raise ValueError('Extent does not match onboarding intent')
    result = dict(intent, marker=marker, zvol_guid=str(dataset['guid']['value']),
                  extent_id=extent['id'], serial=serial, naa=extent['naa'], target_id=target['id'],
                  iqn=nas.call('iscsi.global.config')['basename'] + ':' + target['name'], lun=0,
                  group=target['groups'][0], chap_user=chap_user)
    verify_native(result, read_state(nas))
    return result


def onboard(nas, intent, journal):
    if os.path.lexists(journal):
        # Collect current native state for operator reconciliation without allocating.
        read_state(nas)
        raise FileExistsError('Existing intent; inspect/reconcile without repeating creation')
    require_maintenance()
    if (intent['dataset'] != 'apps/iscsi/jellyfin-config' or intent['service'] != 'jellyfin'
            or intent['bytes'] != 64 * 1024**3 or intent['sync'] != 'STANDARD'
            or intent['auth_networks'] != ['10.9.8.0/24'] or intent['portal'] != '10.9.8.30:3260'
            or intent['portal_id'] != 1 or len(set(intent['initiators'])) != 2):
        raise ValueError('Unreviewed pilot allocation intent')
    _pool(nas, intent['pool_guid'])
    pool_dataset = _one(nas.call('pool.dataset.query', [['id', '=', 'apps']],
                             {'extra': {'properties': ['available']}}), 'id', 'apps')
    if pool_dataset['available']['parsed'] < intent['bytes'] + 16 * 1024**3:
        raise ValueError('Insufficient pool headroom')
    portal = _one(nas.call('iscsi.portal.query'), 'id', 1)
    if portal['listen'] != [{'ip': '10.9.8.30', 'port': 3260}]:
        raise ValueError('Reviewed portal listener changed')
    if nas.call('pool.dataset.query', [['id', '=', intent['dataset']]]):
        raise ValueError('Existing service dataset: use verification, never onboarding')
    targets = nas.call('iscsi.target.query')
    if any(t['name'] == intent['service'] for t in targets):
        raise ValueError('Target name already exists')
    if any(e['name'] == intent['service'] or e['disk'] == 'zvol/' + intent['dataset'] for e in nas.call('iscsi.extent.query')):
        raise ValueError('Extent already exists')
    if any(a['tag'] == intent['chap_tag'] for a in nas.call('iscsi.auth.query', [], {'select': ['tag', 'user']})):
        raise ValueError('CHAP group already exists')
    service = _one(nas.call('service.query'), 'service', 'iscsitarget')
    if targets and service['state'] != 'RUNNING':
        raise ValueError('Starting existing unrelated exports needs separate review')
    parent = nas.call('pool.dataset.query', [['id', '=', 'apps/iscsi']], {'extra': {'properties': ['sync']}})
    if parent and (len(parent) != 1 or parent[0]['sync']['value'] != 'STANDARD'
                   or parent[0]['sync']['source'] != 'LOCAL'):
        raise ValueError('Existing iSCSI parent durability differs')
    chap = read_chap()
    marker, serial = str(uuid.uuid4()), uuid.uuid4().hex[:16]
    basename = nas.call('iscsi.global.config')['basename']
    journal_event(journal, dict(state='intent', intent=intent, marker=marker, serial=serial,
                               basename=basename, chap_user=chap['user']), create=True)

    def once(method, *args):
        require_maintenance()
        journal_event(journal, {'state': 'mutation-intent', 'method': method})
        result = nas.call(method, *args)
        journal_event(journal, {'state': 'responded', 'method': method,
                               'id': result.get('id') if isinstance(result, dict) else None})
        return result

    try:
        if not parent:
            once('pool.dataset.create', {'name': 'apps/iscsi', 'type': 'FILESYSTEM', 'sync': 'STANDARD'})
        once('pool.dataset.create', {'name': intent['dataset'], 'type': 'VOLUME', 'volsize': intent['bytes'],
                                   'volblocksize': '16K', 'sparse': False, 'sync': 'STANDARD'})
        initiator = once('iscsi.initiator.create', {'initiators': intent['initiators'], 'comment': marker})
        once('iscsi.auth.create', {'tag': intent['chap_tag'], 'user': chap['user'], 'secret': chap['secret']})
        extent = once('iscsi.extent.create', {'name': intent['service'], 'type': 'DISK', 'disk': 'zvol/' + intent['dataset'],
                                            'serial': serial, 'blocksize': 512, 'insecure_tpc': False,
                                            'enabled': True, 'ro': False, 'comment': marker})
        target = once('iscsi.target.create', {'name': intent['service'], 'groups': [dict(portal=1, initiator=initiator['id'],
                                             authmethod='CHAP', auth=intent['chap_tag'])], 'auth_networks': intent['auth_networks']})
        once('iscsi.targetextent.create', {'target': target['id'], 'extent': extent['id'], 'lunid': 0})
        if not service['enable']:
            once('service.update', 'iscsitarget', {'enable': True})
        if service['state'] != 'RUNNING':
            once('service.start', 'iscsitarget')
        result = _record(nas, intent, marker, serial, chap['user'])
        if not result['iqn'].startswith(basename + ':'):
            raise ValueError('Global basename changed during allocation')
        journal_event(journal, {'state': 'native-verified', 'record': result})
        return result
    except Exception:
        journal_event(journal, {'state': 'needs-reconciliation'})
        raise


def reconcile_onboarding(nas, journal):
    first = json.loads(Path(journal).read_text().splitlines()[0])
    if first.get('state') != 'intent':
        raise ValueError('Missing original allocation intent')
    result = _record(nas, first['intent'], first['marker'], first['serial'], first['chap_user'])
    if result['iqn'] != first['basename'] + ':' + first['intent']['service']:
        raise ValueError('Basename no longer matches allocation intent')
    return result


def snapshot_policy(nas, journal, *, reconcile=False, pool_guid='9917900421692286909'):
    _pool(nas, pool_guid)
    tasks = nas.call('pool.snapshottask.query')
    if os.path.lexists(journal):
        if not reconcile:
            raise FileExistsError('Snapshot intent exists; explicit reconciliation required')
        desired = json.loads(Path(journal).read_text().splitlines()[0])['snapshot_intent']
    else:
        source = _one(tasks, 'dataset', 'apps/pv')
        desired = dict(dataset='apps/iscsi', recursive=True, lifetime_value=1, lifetime_unit='WEEK',
                       schedule=source['schedule'], naming_schema=source['naming_schema'], enabled=True, exclude=[])
    if desired['dataset'] != 'apps/iscsi':
        raise ValueError('Wrong snapshot dataset')
    matches = [t for t in tasks if t['dataset'] == desired['dataset']]
    if matches:
        if len(matches) != 1 or any(matches[0].get(k) != v for k, v in desired.items()):
            raise ValueError('Conflicting snapshot policy requires review')
        return {'verified': True, 'id': matches[0]['id']}
    if reconcile:
        raise ValueError('Snapshot create outcome missing; do not retry allocation')
    require_maintenance()
    journal_event(journal, {'state': 'intent', 'snapshot_intent': desired}, create=True)
    nas.call('pool.snapshottask.create', desired)
    return snapshot_policy(nas, journal, reconcile=True, pool_guid=pool_guid)
