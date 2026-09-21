"""Git/binding checks and durable conservative rollback boundary."""
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import re
from maintenance import require_maintenance
from jellyfin_backup import write_json, _sync
from render_storage import render, record_hash


def quantity(value):
    match=re.fullmatch(r'([0-9]+(?:\.[0-9]+)?)([KMGTPE]i|[kMGTPE])?',str(value))
    if not match:raise ValueError('Unsupported capacity quantity')
    suffix=match[2] or ''
    factor=1024**('KMGTPE'.index(suffix[0])+1) if suffix.endswith('i') else 1000**('kMGTPE'.index(suffix)+1) if suffix else 1
    return Decimal(match[1])*factor


def verify_target_hold(record, stages, app, pv, pvc):
    sync=app.get('status',{}).get('sync',{})
    revision=stages.get('target-held','')
    if not re.fullmatch('[0-9a-f]{40}',revision) or sync.get('status')!='Synced' or revision not in sync.get('revisions',[])+[sync.get('revision','')]:
        raise ValueError('Reviewed target-held revision is not reconciled')
    expected_pv,expected_pvc=render(record)[:2]
    for live,expected in ((pv,expected_pv),(pvc,expected_pvc)):
        if live.get('metadata',{}).get('name')!=expected['metadata']['name'] or live.get('status',{}).get('phase')!='Bound':
            raise ValueError('Reviewed binding is not Bound')
    for key in ('csi','accessModes','persistentVolumeReclaimPolicy','volumeMode'):
        if pv['spec'].get(key)!=expected_pv['spec'][key]:raise ValueError('PV identity changed: '+key)
    if (pv['spec'].get('storageClassName','')!='' or quantity(pv['spec']['capacity']['storage'])!=record['bytes']
            or any(pv['spec']['claimRef'].get(k)!=record[v] for k,v in [('name','pvc'),('namespace','namespace')])):
        raise ValueError('PV capacity or claim changed')
    for key in ('storageClassName','volumeName','accessModes','volumeMode'):
        if pvc['spec'].get(key)!=expected_pvc['spec'][key]:raise ValueError('PVC binding changed: '+key)
    if pvc['metadata'].get('namespace')!=record['namespace'] or quantity(pvc['spec']['resources']['requests']['storage'])!=record['bytes']:
        raise ValueError('PVC capacity or namespace changed')


def mark_possible_write(record, path):
    require_maintenance();path=Path(path)
    if path.is_symlink():raise ValueError('Invalid first-write receipt')
    if path.exists():
        old=json.loads(path.read_text())
        if old.get('record_hash')!=record_hash(record) or old.get('target_may_have_written') is not True:
            raise ValueError('First-write receipt belongs to a different target')
        return
    write_json(path,{'target_may_have_written':True,'record_hash':record_hash(record),
                     'recorded_at':datetime.now(timezone.utc).isoformat()})
    _sync(path.parent)
