"""Pure release decision fed by fresh external observations, never a Git release flag."""
from datetime import datetime, timezone
from maintenance import require_maintenance
from render_storage import record_hash, render


def _fresh(value):
    try:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(value)).total_seconds()
        return 0 <= age <= 300
    except (TypeError, ValueError):
        return False


def hold(record):
    require_maintenance()
    return {'apiVersion': 'v1', 'kind': 'ConfigMap',
            'metadata': {'namespace': record['namespace'], 'name': 'retained-jellyfin-authorization'},
            'data': {'released': 'false', 'recordHash': record_hash(record)}}


def authorize(record, verification, namespace_uid, node_generation):
    require_maintenance()
    render(record)  # Reject incomplete native/filesystem identity before authorization.
    v = verification
    old = v.get('old_writer', {})
    clean = old.get('kind') == 'clean-unmount' and old.get('mounts') == 0 and old.get('sessions') == 0
    fenced = old.get('kind') == 'fenced' and old.get('current_status') == 'stopped' and old.get('generation_matches') is True
    if not (namespace_uid and v.get('namespace_uid') == namespace_uid and v.get('node') == node_generation
            and all(node_generation.get(k) for k in ('hostname', 'node_uid', 'smbios_uuid'))
            and v.get('record_hash') == record_hash(record)
            and all(v.get(k) is True for k in ('held', 'native_verified', 'filesystem_verified', 'chap_present', 'eviction_checked'))
            and v.get('filesystem_uuid') == record['filesystem_uuid'] and v.get('marker') == record['marker']
            and v.get('free_bytes', 0) >= 25 * 1024**3 and _fresh(v.get('observed_at'))
            and old.get('verified') is True and _fresh(old.get('observed_at')) and (clean or fenced)):
        raise ValueError('Release verification incomplete, stale or mismatched; writer remains held')
    result = hold(record)
    result['data'].update(released='true', namespaceUID=namespace_uid, hostname=node_generation['hostname'],
                          nodeUID=node_generation['node_uid'], smbiosUUID=node_generation['smbios_uuid'])
    return result
