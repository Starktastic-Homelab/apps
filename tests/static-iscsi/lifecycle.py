"""Small fail-closed helpers for the isolated retained-volume rehearsal."""
import copy
import pathlib
import sqlite3

DRIVER = 'org.democratic-csi.iscsi-lab'
ATTRIBUTES = {'iqn', 'lun', 'portal', 'portals', 'interface', 'node_attach_driver',
              'provisioner_driver', 'provisioner_driver_instance_id', 'storage.kubernetes.io/csiProvisionerIdentity'}
CSI_FIELDS = {'driver', 'volumeHandle', 'fsType', 'volumeAttributes', 'nodeStageSecretRef',
              'nodePublishSecretRef', 'controllerExpandSecretRef', 'nodeExpandSecretRef',
              'controllerPublishSecretRef', 'readOnly'}


def export_pv(pv):
    spec = pv['spec']
    csi = spec['csi']
    if (csi['driver'] != DRIVER or spec['persistentVolumeReclaimPolicy'] != 'Retain'
            or spec['accessModes'] != ['ReadWriteOncePod'] or not csi['volumeHandle']):
        raise ValueError('Unexpected retained volume identity or policy')
    if set(csi) - CSI_FIELDS or set(csi.get('volumeAttributes', {})) - ATTRIBUTES:
        raise ValueError('Unrecognized CSI fields; reconcile before exporting')
    result = {'apiVersion': 'v1', 'kind': 'PersistentVolume', 'metadata': {
        'name': pv['metadata']['name'], 'annotations': {
            'argocd.argoproj.io/sync-options': 'Prune=false,Delete=false'}}, 'spec': {
        key: copy.deepcopy(spec[key]) for key in ('capacity', 'accessModes', 'storageClassName',
        'persistentVolumeReclaimPolicy', 'csi')}}
    result['spec']['claimRef'] = {key: spec['claimRef'][key] for key in ('name', 'namespace')}
    for key in ('mountOptions', 'volumeMode'):
        if key in spec:
            result['spec'][key] = copy.deepcopy(spec[key])
    return result


def verify_database(path, marker):
    path = pathlib.Path(path)
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError('Missing database; startup cannot initialize')
    connection = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
    try:
        if connection.execute('select marker from identity').fetchall() != [(marker,)]:
            raise ValueError('Wrong service identity')
        if connection.execute('pragma integrity_check').fetchall() != [('ok',)]:
            raise ValueError('Database integrity failure')
    finally:
        connection.close()


def verify_backend(record, datasets, extents, targets, mappings, basename):
    expected = record['backend']
    def one(items, predicate):
        matches = [item for item in items if predicate(item)]
        if len(matches) != 1:
            raise ValueError('Missing, ambiguous or redirected retained backend')
        return matches[0]
    dataset = one(datasets, lambda d: d['id'] == expected['dataset']
                  and d['guid']['value'] == expected['guid'])
    one(extents, lambda e: e['id'] == expected['extent_id']
        and e['disk'] == 'zvol/' + expected['dataset']
        and e['serial'] == expected['serial'] and e['naa'] == expected['naa'])
    target = one(targets, lambda t: t['id'] == expected['target_id'])
    one(mappings, lambda m: m['extent'] == expected['extent_id']
        and m['target'] == expected['target_id'] and m['lunid'] == expected['lun'])
    attributes = record['pv']['spec']['csi']['volumeAttributes']
    if (basename + ':' + target['name'] != attributes['iqn']
            or str(expected['lun']) != attributes['lun']):
        raise ValueError('CSI target identity mismatch')
    return dataset['volsize']['parsed']
