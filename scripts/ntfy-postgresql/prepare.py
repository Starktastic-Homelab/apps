#!/usr/bin/env python3
"""Generate inactive ntfy runtime and append-only sealed enrollment inputs; never applies."""
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
ACCOUNT, SECRET = 'ntfy-postgres-completion', 'ntfy-postgres-secret'


def build_sources():
    resources, fragment = shared.enrollment.consumer_sources(argparse.Namespace(
        id='ntfy', database='ntfy', role='ntfy', app_namespace='operations', app_secret=SECRET, app_password_key='password'))
    old = resources[0]['metadata']['name']
    for obj in resources:
        obj['metadata']['name'] = ACCOUNT
        for subject in obj.get('subjects', []): subject['name'] = ACCOUNT
    inits, mounts = {}, {}
    for name, original in zip(('enrollment', 'database'), fragment['initContainers']):
        container = copy.deepcopy(original)
        container.pop('name')
        repository, digest = container.pop('image').split('@')
        container['image'] = {'repository': repository, 'digest': digest}
        for mount in container.pop('volumeMounts'):
            mounts.setdefault(mount['name'], {})[name] = [{'path': mount['mountPath'], 'readOnly': True}]
        inits[name] = container
    inits['database']['command'][-1] = ('export PGPASSWORD="$(cat /credentials/password)"; '
        'exec psql -XqAt -v ON_ERROR_STOP=1 -f /retained-startup/main.sql >/dev/null 2>&1')
    env = {'NTFY_DATABASE_URL': {'valueFrom': {'secretKeyRef': {'name': SECRET, 'key': 'database-url'}}}}
    guard = {'image': copy.deepcopy(inits['enrollment']['image']),
        'command': ['python3', '-I', '-B', '/retained-startup/guard.py', '/var/cache/ntfy', '/credentials'],
        'env': copy.deepcopy(env), 'securityContext': copy.deepcopy(inits['enrollment']['securityContext']),
        'resources': {'requests': {'cpu': '10m', 'memory': '32Mi'}, 'limits': {'cpu': '100m', 'memory': '64Mi'}}}
    inits['enrollment']['dependsOn'] = 'retained-state'
    inits['database']['dependsOn'] = 'enrollment'
    mounts['pg-completion-password']['retained-state'] = [{'path': '/credentials', 'readOnly': True}]
    persistence = {}
    for volume in fragment['volumes']:
        name = volume['name']
        if 'configMap' in volume:
            assert volume['configMap']['name'] == old
            item = {'type': 'configMap', 'name': ACCOUNT, 'defaultMode': 0o444}
        elif 'projected' in volume:
            item = {'type': 'custom', 'volumeSpec': {'projected': volume['projected']}}
        else:
            item = {'type': 'secret', 'name': SECRET, 'defaultMode': 0o444,
                'items': [{'key': 'password', 'path': 'password'}]}
        persistence[name] = dict(item, globalMounts=[], advancedMounts={'main': mounts[name]})
    persistence.update({'config': {'enabled': False},
        'cache': {'enabled': False},
        'ntfy-data': {'existingClaim': 'ntfy-data-block', 'globalMounts': [],
            'advancedMounts': {'main': {'main': [{'path': '/var/cache/ntfy'}],
                'retained-state': [{'path': '/var/cache/ntfy', 'readOnly': True}]}}},
        'retained-startup': {'type': 'configMap', 'name': 'ntfy-retained-startup-guard', 'defaultMode': 0o444,
            'globalMounts': [], 'advancedMounts': {'main': {
                'retained-state': [{'path': '/retained-startup', 'readOnly': True}],
                'database': [{'path': '/retained-startup', 'readOnly': True}]}}}})
    # A list replaces Helm's inherited map: null values still render empty env entries.
    effective_env = {}
    for path in ('templates/common.yaml', 'services/operations/ntfy/values.yaml'):
        layer = yaml.safe_load((ROOT / path).read_text())['controllers']['main']['containers']['main']['env']
        if isinstance(layer, list):
            layer = {item['name']: {k: v for k, v in item.items() if k != 'name'} for item in layer}
        effective_env.update(layer)
    for name in ('NTFY_AUTH_FILE', 'NTFY_CACHE_FILE', 'NTFY_WEB_PUSH_FILE'):
        effective_env.pop(name, None)
    effective_env.update(env)
    main_env = [{'name': name, **(value if isinstance(value, dict) else {'value': value})}
        for name, value in effective_env.items()]
    values = {'controllers': {'main': {'replicas': 1, 'strategy': 'Recreate',
        'serviceAccount': {'name': ACCOUNT}, 'pod': {'securityContext': {}, 'automountServiceAccountToken': False,
            'nodeSelector': {'node-role.kubernetes.io/worker': 'true'}},
        'containers': {'main': {'env': main_env}},
        'initContainers': {'retained-state': guard, **inits}}}, 'persistence': persistence}
    return resources, values


def write_sources():
    directory = HERE / 'production'
    directory.mkdir(exist_ok=True)
    resources, values = build_sources()
    documents = {'values.yaml': [values], 'consumer-gate.yaml': resources,
        'guard-configmap.yaml': [{'apiVersion': 'v1', 'kind': 'ConfigMap',
            'metadata': {'name': 'ntfy-retained-startup-guard', 'namespace': 'operations'},
            'data': {name: (HERE / name).read_text() for name in ('guard.py', 'main.sql')}}]}
    for name in ('pv.yaml', 'pvc.yaml'):
        obj = yaml.safe_load((ROOT / 'infrastructure/base-configs/templates/bazarr-block-storage' / name).read_text()
            .replace('bazarr-config-block', 'ntfy-data-block').replace('vm-9999-bazarr.raw', 'vm-9999-ntfy.raw')
            .replace('4Gi', '8Gi').replace('namespace: media', 'namespace: operations'))
        documents[name] = [obj]
    source = list(yaml.safe_load_all((ROOT / 'services/media/bazarr/manifests/source-hold.yaml').read_text()
        .replace('bazarr-source-hold', 'ntfy-source-hold').replace('Bazarr', 'ntfy')))
    source[0]['spec']['matchConditions'][0]['expression'] = ("has(object.spec.volumes) && object.spec.volumes.exists(v, "
        "(object.metadata.namespace == 'operations' && has(v.persistentVolumeClaim) && "
        "v.persistentVolumeClaim.claimName in ['ntfy-config', 'ntfy-cache']) || "
        "(has(v.nfs) && (v.nfs.path in ['/mnt/apps/pv/operations/ntfy-config', '/mnt/apps/pv/operations/ntfy-cache'] || "
        "v.nfs.path.startsWith('/mnt/apps/pv/operations/ntfy-config/') || "
        "v.nfs.path.startsWith('/mnt/apps/pv/operations/ntfy-cache/'))))")
    source[0]['spec']['validations'][0]['message'] = 'The preserved ntfy NFS sources are held; restore acceptance is required.'
    source[1]['spec']['policyName'] = 'ntfy-source-hold'
    documents['source-hold.yaml'] = source
    for name, objects in documents.items(): (directory / name).write_text(shared.source_yaml(objects))


def prepare_enrollment(output: Path):
    output.mkdir(mode=0o700)
    source = json.loads(yaml.safe_load((ROOT / 'infrastructure/controllers/databases/postgres/manifests/enrollment-configmap.yaml').read_text())['data']['config.json'])
    (output / 'source-config.json').write_text(json.dumps(source, indent=2) + '\n')
    args = [sys.executable, str(ROOT / 'scripts/postgres-enrollment/prepare.py'), 'new',
        '--config', str(output / 'source-config.json'), '--id', 'ntfy', '--database', 'ntfy', '--role', 'ntfy',
        '--password-key', 'ntfy-password', '--app-namespace', 'operations', '--app-secret', SECRET,
        '--app-password-key', 'password', '--app-url-key', 'database-url',
        '--aggregate-secret', str(ROOT / 'infrastructure/controllers/databases/postgres/manifests/enrollment-secret.yaml'),
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
        print('ntfy preparation refused; no credentials printed.', file=sys.stderr)
        raise SystemExit(1) from None
