"""Generate reviewable Git stages; never apply them or invent native identities."""
import argparse
import copy
import json
from pathlib import Path
import shutil
import yaml
from backup_reader import source_hold_policy
from render_storage import render, placement, WRITER

STAGES=('source-held','target-held','target-released')


def stage_values(original, stage, record=None, node=None):
    if stage not in STAGES:raise ValueError('Unknown reviewed stage')
    values=copy.deepcopy(original)
    controller=values['controllers']['main']
    controller['replicas']=0
    if stage=='source-held':return values
    render(record or {})  # No allocation intents or guessed filesystem identities.
    if not node or not all(node.get(k) for k in ('hostname','node_uid','smbios_uuid')):
        raise ValueError('Reviewed live worker generation required')
    controller['replicas']=int(stage=='target-released')
    controller['strategy']='Recreate'
    options=controller.setdefault('pod',{})
    options['labels']={WRITER:'jellyfin'}
    options['affinity']=placement(node)
    options.setdefault('nodeSelector',{})['storage.starktastic.net/iscsi-ready']='true'
    main=controller['containers']['main']
    for kind in ('requests','limits'):
        main.setdefault('resources',{}).setdefault(kind,{})['ephemeral-storage']='12Gi'
    # Use the same already pinned image; no additional mutable initializer image.
    controller['initContainers']={'disposable-dirs':{'image':copy.deepcopy(main['image']),
        'command':['/bin/sh','-ec','mkdir -p /disposable/cache /disposable/transcodes; chown 1000:1000 /disposable/cache /disposable/transcodes'],
        'securityContext':{'runAsUser':0}}}
    values['persistence']['jellyfin-config']['existingClaim']=record['pvc']
    values['persistence']['jellyfin-cache']['enabled']=False
    values['persistence']['disposable']={'enabled':True,'type':'emptyDir','sizeLimit':'10Gi',
        'advancedMounts':{'main':{'main':[{'path':'/config/cache','subPath':'cache'},
                                        {'path':'/config/data/transcodes','subPath':'transcodes'}],
                                  'disposable-dirs':[{'path':'/disposable'}]}}}
    return values


def validate_rollback(target_may_have_written, evidence):
    if evidence.get('quiescent') is not True:
        raise ValueError('Clean target unmount or exact fresh fence required before any rollback')
    if target_may_have_written:
        if (evidence.get('latest_target_restore_verified') is not True
                or not evidence.get('claim','').startswith('jellyfin-config-rollback-')
                or not evidence.get('path','').startswith('/mnt/apps/pv/media/jellyfin-rollback-')
                or '..' in Path(evidence['path']).parts):
            raise ValueError('Latest cold target state and a new retained NFS directory/claim required')
    elif evidence.get('claim')!='jellyfin-config':
        raise ValueError('Reviewed original source claim required')


def generate(repo, output, stage, record=None, node=None, passed=None, sealed_chap=None):
    repo=Path(repo);output=Path(output)
    if output.exists():raise ValueError('Use a new output directory; never overwrite a reviewed stage')
    source=repo/'services/media/jellyfin'
    values=stage_values(yaml.safe_load((source/'values.yaml').read_text()),stage,record,node)
    if stage!='source-held':
        if not passed or not all(passed.get(k) is True for k in ('files_verified','sqlite_verified','application_verified')) or len(passed.get('archive_sha256',''))!=64:
            raise ValueError('Independent full cold restore receipt required')
        if (not sealed_chap or sealed_chap.get('kind')!='SealedSecret'
                or sealed_chap.get('metadata',{}).get('name')!='retained-jellyfin-chap'
                or sealed_chap['metadata'].get('namespace')!='retained-iscsi'
                or not all(sealed_chap.get('spec',{}).get('encryptedData',{}).get(k) for k in ('node-db.node.session.auth.authmethod','node-db.node.session.auth.username','node-db.node.session.auth.password'))):
            raise ValueError('Actual correctly scoped sealed CHAP required')
    target=output/'services/media/jellyfin'
    shutil.copytree(source,target)
    (target/'values.yaml').write_text(yaml.safe_dump(values,sort_keys=False))
    app=yaml.safe_load((target/'app.yaml').read_text());app['ingress']['enabled']=False
    (target/'app.yaml').write_text(yaml.safe_dump(app,sort_keys=False))
    manifest=target/'manifests'
    job=yaml.safe_load((manifest/'ldap-library-sync.yaml').read_text());job['spec']['suspend']=True
    (manifest/'ldap-library-sync.yaml').write_text(yaml.safe_dump(job,sort_keys=False))
    objects=source_hold_policy()
    if stage!='source-held':objects+=render(record)+[sealed_chap]
    (manifest/'retained-storage.yaml').write_text(yaml.safe_dump_all(objects,sort_keys=False))
    kustomization=yaml.safe_load((manifest/'kustomization.yaml').read_text())
    if 'retained-storage.yaml' not in kustomization['resources']:kustomization['resources'].append('retained-storage.yaml')
    (manifest/'kustomization.yaml').write_text(yaml.safe_dump(kustomization,sort_keys=False))
    # Old PVC files and resources are deliberately copied intact through acceptance.
    return target


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',choices=STAGES);parser.add_argument('--repo',type=Path,default=Path.cwd())
    parser.add_argument('--output',type=Path,required=True)
    for name in ('record','node','passed','sealed-chap'):parser.add_argument('--'+name,type=Path)
    args=parser.parse_args()
    load=lambda path:yaml.safe_load(path.read_text()) if path else None
    print(generate(args.repo,args.output,args.stage,load(args.record),load(args.node),load(args.passed),load(args.sealed_chap)))


if __name__=='__main__':main()
