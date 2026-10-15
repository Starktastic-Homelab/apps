#!/usr/bin/env python3
"""Generate inactive Grafana runtime and append-only enrollment sources; never applies."""
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
ACCOUNT, SECRET, SERVICE_ACCOUNT = 'grafana-postgres-completion', 'grafana-postgres-secret', 'kube-prometheus-stack-grafana'


def build_sources():
    resources, fragment = shared.enrollment.consumer_sources(argparse.Namespace(
        id='grafana', database='grafana', role='grafana', app_namespace='monitoring', app_secret=SECRET, app_password_key='password'))
    old = resources[0]['metadata']['name']
    resources = [r for r in resources if r['kind'] != 'ServiceAccount']
    for obj in resources:
        obj['metadata']['name'] = ACCOUNT
        for subject in obj.get('subjects', []): subject['name'] = SERVICE_ACCOUNT
    volumes = copy.deepcopy(fragment['volumes'])
    for volume in volumes:
        if 'configMap' in volume and volume['configMap']['name'] == old:
            volume['configMap']['name'] = ACCOUNT
    volumes.append({'name': 'retained-startup', 'configMap': {'name': 'grafana-retained-startup-guard', 'defaultMode': 0o444}})
    inits = copy.deepcopy(fragment['initContainers'])
    inits[-1]['command'][-1] = ('export PGPASSWORD="$(cat /credentials/password)"; '
        'exec psql -XqAt -v ON_ERROR_STOP=1 -f /retained-startup/main.sql >/dev/null 2>&1')
    inits[-1]['volumeMounts'].append({'name': 'retained-startup', 'mountPath': '/retained-startup', 'readOnly': True})
    env = {'GF_DATABASE_TYPE': 'postgres', 'GF_DATABASE_HOST': 'postgres-postgresql.databases:5432',
           'GF_DATABASE_NAME': 'grafana', 'GF_DATABASE_USER': 'grafana', 'GF_DATABASE_SSL_MODE': 'disable',
           'GF_DATABASE_MAX_OPEN_CONN': '5', 'GF_DATABASE_MAX_IDLE_CONN': '2'}
    password = {'secretKeyRef': {'name': SECRET, 'key': 'password'}}
    security = dict(inits[0]['securityContext'], runAsUser=472, runAsGroup=472)
    guard = {'name': 'grafana-retained-state', 'image': inits[0]['image'],
        'command': ['python3', '-I', '-B', '/retained-startup/guard.py', '/var/lib/grafana', '/credentials'],
        'securityContext': security,
        'env': [{'name': k, 'value': v} for k, v in env.items()] + [{'name': 'GF_DATABASE_PASSWORD', 'valueFrom': password}],
        'volumeMounts': [{'name': 'storage', 'mountPath': '/var/lib/grafana', 'readOnly': True},
            {'name': 'retained-startup', 'mountPath': '/retained-startup', 'readOnly': True},
            {'name': 'pg-completion-password', 'mountPath': '/credentials', 'readOnly': True}],
        'resources': {'requests': {'cpu': '10m', 'memory': '32Mi'}, 'limits': {'cpu': '100m', 'memory': '64Mi'}}}
    values = {'grafana': {'replicas': 1, 'deploymentStrategy': {'type': 'Recreate'},
        'image': {'sha': '202e5d5b3f8499e70ccac7991eea6d7da72d2790eb2e0597e7987acf724e7180'},
        'securityContext': {'fsGroup': None}, 'nodeSelector': {'node-role.kubernetes.io/worker': 'true'},
        'persistence': {'enabled': True, 'existingClaim': 'grafana-data-block'},
        'env': env, 'envValueFrom': {'GF_DATABASE_PASSWORD': password},
        'extraInitContainers': [guard, *inits], 'extraContainerVolumes': volumes,
        'sidecar': {'dashboards': {'initDashboards': True, 'restartPolicy': 'Always',
            'startupProbe': {'httpGet': {'path': '/healthz', 'port': 8080}, 'periodSeconds': 2, 'failureThreshold': 60}},
            'datasources': {'initDatasources': True, 'restartPolicy': 'Always',
                'startupProbe': {'httpGet': {'path': '/healthz', 'port': 8081}, 'periodSeconds': 2, 'failureThreshold': 60}}}}}
    return resources, values


def write_sources():
    directory = HERE / 'production'
    directory.mkdir(exist_ok=True)
    resources, values = build_sources()
    documents = {'values.yaml': [values], 'consumer-gate.yaml': resources,
        'guard-configmap.yaml': [{'apiVersion': 'v1', 'kind': 'ConfigMap',
            'metadata': {'name': 'grafana-retained-startup-guard', 'namespace': 'monitoring'},
            'data': {name: (HERE / name).read_text() for name in ('guard.py', 'main.sql')}}]}
    for name in ('pv.yaml', 'pvc.yaml'):
        obj = yaml.safe_load((ROOT / 'scripts/ntfy-postgresql/production' / name).read_text()
            .replace('ntfy-data-block', 'grafana-data-block').replace('vm-9999-ntfy.raw', 'vm-9999-grafana.raw')
            .replace('8Gi', '2Gi').replace('namespace: operations', 'namespace: monitoring'))
        documents[name] = [obj]
    source = list(yaml.safe_load_all((ROOT / 'scripts/ntfy-postgresql/production/source-hold.yaml').read_text()
        .replace('ntfy-source-hold', 'grafana-source-hold')))
    source[0]['spec']['matchConditions'][0]['expression'] = (
        "has(object.spec.volumes) && object.spec.volumes.exists(v, "
        "(object.metadata.namespace == 'monitoring' && has(v.persistentVolumeClaim) && "
        "v.persistentVolumeClaim.claimName == 'kube-prometheus-stack-grafana') || "
        "(has(v.nfs) && (v.nfs.path == '/mnt/apps/pv/monitoring/kube-prometheus-stack-grafana' || "
        "v.nfs.path.startsWith('/mnt/apps/pv/monitoring/kube-prometheus-stack-grafana/'))))")
    source[0]['spec']['validations'][0]['message'] = 'The preserved Grafana NFS source is held; restore acceptance is required.'
    documents['source-hold.yaml'] = source
    for name, objects in documents.items(): (directory / name).write_text(shared.source_yaml(objects))


def prepare_enrollment(output):
    output.mkdir(mode=0o700)
    source = json.loads(yaml.safe_load((ROOT / 'infrastructure/controllers/databases/postgres/manifests/enrollment-configmap.yaml').read_text())['data']['config.json'])
    (output / 'source-config.json').write_text(json.dumps(source, indent=2) + '\n')
    args = [sys.executable, str(ROOT / 'scripts/postgres-enrollment/prepare.py'), 'new',
        '--config', str(output / 'source-config.json'), '--id', 'grafana', '--database', 'grafana', '--role', 'grafana',
        '--password-key', 'grafana-password', '--app-namespace', 'monitoring', '--app-secret', SECRET,
        '--app-password-key', 'password', '--aggregate-secret', str(ROOT / 'infrastructure/controllers/databases/postgres/manifests/enrollment-secret.yaml'),
        '--output-dir', str(output / 'bundle')]
    result = subprocess.run(args, capture_output=True, text=True, timeout=90)
    if result.returncode: raise ValueError('Preserve partial preparation; do not regenerate credentials')
    directory = HERE / 'production/enrollment'
    directory.mkdir(exist_ok=True)
    for name in ('enrollment-configmap.yaml', 'enrollment-job.yaml', 'enrollment-secret.yaml', 'application-secret.yaml'):
        (directory / name).write_text(shared.source_yaml([yaml.safe_load((output / 'bundle' / name).read_text())]))


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
        print('Grafana preparation refused; no credentials printed.', file=sys.stderr)
        raise SystemExit(1) from None
