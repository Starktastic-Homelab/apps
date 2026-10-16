#!/usr/bin/env python3
"""Generate inactive pgAdmin runtime and append-only enrollment sources; never applies."""
import argparse
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
spec = importlib.util.spec_from_file_location('shared_pg_preparation', ROOT / 'scripts/prowlarr-postgresql/prepare.py')
shared = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shared)
ACCOUNT, SECRET = 'pgadmin-postgres-completion', 'pgadmin-postgres-secret'
IMAGE_DIGEST = 'sha256:c332c5f6dfba995d9ebc4af261d93506d6876085d712eaaa3defc8dd1a3f26de'
DATABASE_ENV = {'PGADMIN_CONFIG_CONFIG_DATABASE_URI_FILE': '/etc/pgadmin-postgres/uri',
    'PGADMIN_CONFIG_SQLALCHEMY_ENGINE_OPTIONS': "{'pool_size': 2, 'max_overflow': 1, 'pool_recycle': 300, 'pool_pre_ping': True}"}


def build_sources():
    resources, fragment = shared.enrollment.consumer_sources(argparse.Namespace(
        id='pgadmin', database='pgadmin', role='pgadmin', app_namespace='databases', app_secret=SECRET, app_password_key='password'))
    old = resources[0]['metadata']['name']
    for obj in resources:
        obj['metadata']['name'] = ACCOUNT
        for subject in obj.get('subjects', []): subject['name'] = ACCOUNT
    volumes = copy.deepcopy(fragment['volumes'])
    for volume in volumes:
        if 'configMap' in volume and volume['configMap']['name'] == old:
            volume['configMap']['name'] = ACCOUNT
        if volume['name'] == 'pg-completion-password':
            volume['secret']['items'].append({'key': 'uri', 'path': 'uri'})
    volumes.append({'name': 'retained-startup', 'configMap': {'name': 'pgadmin-retained-startup-guard', 'defaultMode': 0o444}})
    inits = copy.deepcopy(fragment['initContainers'])
    inits[-1]['command'][-1] = ('export PGPASSWORD="$(cat /credentials/password)"; '
        'exec psql -XqAt -v ON_ERROR_STOP=1 -f /retained-startup/main.sql >/dev/null 2>&1')
    inits[-1]['volumeMounts'].append({'name': 'retained-startup', 'mountPath': '/retained-startup', 'readOnly': True})
    security = dict(inits[0]['securityContext'], runAsUser=5050, runAsGroup=5050)
    guard = {'name': 'pgadmin-retained-state', 'image': inits[0]['image'],
        'command': ['python3', '-I', '-B', '/retained-startup/guard.py', '/var/lib/pgadmin', '/etc/pgadmin-postgres'],
        'securityContext': security,
        'env': [{'name': k, 'value': v} for k, v in DATABASE_ENV.items()],
        'volumeMounts': [{'name': 'pgadmin-data', 'mountPath': '/var/lib/pgadmin', 'readOnly': True},
            {'name': 'retained-startup', 'mountPath': '/retained-startup', 'readOnly': True},
            {'name': 'pg-completion-password', 'mountPath': '/etc/pgadmin-postgres', 'readOnly': True}],
        'resources': {'requests': {'cpu': '10m', 'memory': '32Mi'}, 'limits': {'cpu': '100m', 'memory': '64Mi'}}}
    auth = yaml.safe_load((ROOT / 'infrastructure/controllers/databases/pgadmin/values.yaml').read_text())['envVarsExtra']
    # After activation those values also contain DATABASE_ENV; keep generation stable.
    auth = [item for item in auth if item['name'] not in DATABASE_ENV]
    values = {'replicaCount': 1, 'strategy': {'type': 'Recreate'},
        'image': {'tag': '9.18@' + IMAGE_DIGEST},
        'securityContext': {'fsGroup': None, 'runAsUser': 5050, 'runAsGroup': 5050},
        'VolumePermissions': {'enabled': False},
        'nodeSelector': {'node-role.kubernetes.io/worker': 'true'},
        'serviceAccount': {'create': False, 'name': ACCOUNT, 'automountServiceAccountToken': False},
        'persistentVolume': {'enabled': True, 'existingClaim': 'pgadmin-data-block', 'size': '1Gi', 'storageClass': 'proxmox-retained'},
        'envVarsExtra': auth + [{'name': k, 'value': v} for k, v in DATABASE_ENV.items()],
        'extraInitContainers': yaml.safe_dump([guard, *inits], sort_keys=False),
        'extraVolumes': volumes,
        'extraVolumeMounts': [{'name': 'pg-completion-password', 'mountPath': '/etc/pgadmin-postgres', 'readOnly': True}]}
    return resources, values


def write_sources():
    directory = HERE / 'production'
    directory.mkdir(exist_ok=True)
    resources, values = build_sources()
    documents = {'values.yaml': [values], 'consumer-gate.yaml': resources,
        'guard-configmap.yaml': [{'apiVersion': 'v1', 'kind': 'ConfigMap',
            'metadata': {'name': 'pgadmin-retained-startup-guard', 'namespace': 'databases'},
            'data': {name: (HERE / name).read_text() for name in ('guard.py', 'main.sql')}}]}
    for name in ('pv.yaml', 'pvc.yaml'):
        obj = yaml.safe_load((ROOT / 'scripts/grafana-postgresql/production' / name).read_text()
            .replace('grafana', 'pgadmin').replace('2Gi', '1Gi').replace('namespace: monitoring', 'namespace: databases'))
        documents[name] = [obj]
    source = list(yaml.safe_load_all((ROOT / 'scripts/grafana-postgresql/production/source-hold.yaml').read_text()
        .replace('grafana', 'pgadmin').replace('Grafana', 'pgAdmin')))
    source[0]['spec']['matchConditions'][0]['expression'] = (
        "has(object.spec.volumes) && object.spec.volumes.exists(v, "
        "(object.metadata.namespace == 'databases' && has(v.persistentVolumeClaim) && "
        "v.persistentVolumeClaim.claimName == 'pgadmin-pgadmin4') || "
        "(has(v.nfs) && (v.nfs.path == '/mnt/apps/pv/databases/pgadmin-pgadmin4' || "
        "v.nfs.path.startsWith('/mnt/apps/pv/databases/pgadmin-pgadmin4/'))))")
    documents['source-hold.yaml'] = source
    for name, objects in documents.items():
        if name == 'values.yaml': objects[0]['extraInitContainers'] = shared.Literal(objects[0]['extraInitContainers'])
        (directory / name).write_text(shared.source_yaml(objects))


def prepare_enrollment(output):
    # Reserve first; partial ciphertext is a recoverable generation, never regenerated.
    import secrets
    import os
    from urllib.parse import quote
    output.mkdir(mode=0o700)
    config = json.loads(yaml.safe_load((ROOT / 'infrastructure/controllers/databases/postgres/manifests/enrollment-configmap.yaml').read_text())['data']['config.json'])
    shared.enrollment.validate_config(config)
    config['entries'].append({'id': 'pgadmin', 'database': 'pgadmin', 'role': 'pgadmin', 'mode': 'new', 'passwordKey': 'pgadmin-password'})
    shared.enrollment.validate_config(config)
    aggregate = shared.enrollment.existing(str(ROOT / 'infrastructure/controllers/databases/postgres/manifests/enrollment-secret.yaml'), shared.enrollment.AGGREGATE, 'databases', ['pgadmin-password'])
    assert {e['passwordKey'] for e in config['entries'][:-1]} <= set(aggregate['spec']['encryptedData'])
    password = secrets.token_urlsafe(48)
    a, b = output / 'aggregate', output / 'application'
    a.mkdir(mode=0o700); b.mkdir(mode=0o700)
    encrypted = shared.enrollment.seal(a, shared.enrollment.AGGREGATE, 'databases', {'pgadmin-password': password}, aggregate)
    client = shared.enrollment.seal(b, SECRET, 'databases', {'password': password,
        'uri': repr('postgresql://pgadmin:' + quote(password, safe='') + '@postgres-postgresql.databases:5432/pgadmin')}, None)
    configmap = shared.enrollment.render_configmap(config, encrypted['spec']['encryptedData'])
    job = json.loads(configmap['data']['job-template.json'])
    job['metadata']['name'] = shared.enrollment.hook_name(configmap['data']['acceptance-generation'])
    directory = HERE / 'production/enrollment'
    directory.mkdir(exist_ok=True)
    documents = {'enrollment-configmap.yaml': configmap, 'enrollment-job.yaml': job,
                 'enrollment-secret.yaml': encrypted, 'application-secret.yaml': client}
    for name, obj in documents.items():
        text = shared.source_yaml([obj])
        with open(output / name, 'x', opener=lambda p, f: os.open(p, f, 0o600)) as stream: stream.write(text)
        (directory / name).write_text(text)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('sources', 'enrollment'))
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'sources': write_sources()
        elif args.output: prepare_enrollment(args.output.resolve())
        else: raise ValueError('Exclusive output required')
    except (ValueError, OSError, yaml.YAMLError, subprocess.SubprocessError):
        print('pgAdmin preparation refused; no credentials printed.', file=sys.stderr)
        raise SystemExit(1) from None
