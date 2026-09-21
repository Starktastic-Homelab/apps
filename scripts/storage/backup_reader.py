"""Owned read-only source reader. All pod mutations run on the locked external runner."""
import json
from pathlib import Path
import uuid
from maintenance import require_maintenance
from jellyfin_backup import write_json
from render_storage import _policy

READER_IMAGE='python:3.14-slim-trixie@sha256:caaf356f40667c496d405780745b9ac25771c189a51dfcc42430d531ea09f8a2'


def reader_pod(name, owner):
    return {'apiVersion':'v1','kind':'Pod','metadata':{'name':name,'namespace':'media',
            'labels':{'storage.starktastic.net/reader':'true'},'annotations':{'storage.starktastic.net/owner':owner}},
            'spec':{'restartPolicy':'Never','serviceAccountName':'jellyfin-backup-reader','automountServiceAccountToken':False,
            'containers':[{'name':'reader','image':READER_IMAGE,'command':['sleep','infinity'],
                           'securityContext':{'readOnlyRootFilesystem':True,'allowPrivilegeEscalation':False},
                           'resources':{'requests':{'cpu':'100m','memory':'128Mi'},'limits':{'memory':'512Mi'}},
                           'volumeMounts':[{'name':'config','mountPath':'/config','readOnly':True}]}],
            'volumes':[{'name':'config','persistentVolumeClaim':{'claimName':'jellyfin-config','readOnly':True}}]}}


def source_hold_policy():
    match="object.metadata.namespace == 'media' && has(object.spec.volumes) && object.spec.volumes.exists(v, has(v.persistentVolumeClaim) && v.persistentVolumeClaim.claimName == 'jellyfin-config')"
    checks=["object.metadata.name.startsWith('jellyfin-backup-reader-') && object.spec.serviceAccountName == 'jellyfin-backup-reader' && has(object.spec.automountServiceAccountToken) && !object.spec.automountServiceAccountToken",
            "object.spec.volumes.size() == 1 && object.spec.volumes[0].persistentVolumeClaim.readOnly == true",
            "object.spec.containers.size() == 1 && object.spec.containers[0].image == "+json.dumps(READER_IMAGE)+" && object.spec.containers[0].command == ['sleep','infinity'] && object.spec.containers[0].volumeMounts.size() == 1 && object.spec.containers[0].volumeMounts[0].readOnly == true",
            "!has(object.spec.initContainers) && !has(object.spec.ephemeralContainers)"]
    return _policy('jellyfin-source-maintenance-hold','pods',match,checks)+[
        {'apiVersion':'v1','kind':'ServiceAccount','metadata':{'name':'jellyfin-backup-reader','namespace':'media'},'automountServiceAccountToken':False}]


def prepare_reader(api, root, owner):
    require_maintenance()
    root=Path(root)
    stages=json.loads((root/'stages.json').read_text())
    app=api('-n','argocd','get','application','jellyfin','-o','json')
    sync=app.get('status',{}).get('sync',{})
    if sync.get('status')!='Synced' or stages['source-held'] not in sync.get('revisions',[])+[sync.get('revision','')]:
        raise ValueError('Reviewed source-held Git revision is not synced')
    deployment=api('-n','media','get','deployment','jellyfin','-o','json')
    job=api('-n','media','get','cronjob','jellyfin-ldap-library-sync','-o','json')
    jobs=api('-n','media','get','jobs','-o','json')['items']
    if deployment['spec']['replicas']!=0 or job['spec'].get('suspend') is not True or any(
        j.get('status',{}).get('active',0) and any(o.get('name')==job['metadata']['name'] for o in j['metadata'].get('ownerReferences',[])) for j in jobs):
        raise ValueError('Source app or API writer is not stopped')
    pods=api('-n','media','get','pods','-o','json')['items']
    if any(v.get('persistentVolumeClaim',{}).get('claimName') in ('jellyfin-config','jellyfin-config-iscsi') for p in pods for v in p['spec'].get('volumes',[])):
        raise ValueError('An old configuration consumer still exists')
    name='jellyfin-backup-reader-'+uuid.uuid4().hex[:12]
    write_json(root/'reader-intent.json',{'name':name,'owner':owner})
    require_maintenance()
    created=api('create','-f','-','-o','json',data=reader_pod(name,owner))
    record={'name':name,'namespace':'media','uid':created['metadata']['uid'],'owner':owner}
    write_json(root/'reader.json',record)
    return record


def delete_reader(api, receipt):
    require_maintenance()
    record=json.loads(Path(receipt).read_text())
    live=api('-n','media','get','pod',record['name'],'-o','json')
    if live['metadata']['uid']!=record['uid']:
        raise ValueError('Reader name was reused; refuse cleanup')
    require_maintenance()
    return api('delete','--raw','/api/v1/namespaces/media/pods/'+record['name'],'-f','-',
               data={'apiVersion':'v1','kind':'DeleteOptions','preconditions':{'uid':record['uid']}})
