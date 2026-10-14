#!/usr/bin/env python3
"""Generate inactive Bazarr sources and existing enrollment bundles; never applies or contacts SQL."""
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
ACCOUNT, SECRET = 'bazarr-postgres-completion', 'bazarr-postgres-secret'


def build_sources() -> tuple[list[dict], dict]:
    resources, fragment = shared.enrollment.consumer_sources(argparse.Namespace(
        id='bazarr', database='bazarr', role='bazarr', app_namespace='media', app_secret=SECRET, app_password_key='password'))
    old = resources[0]['metadata']['name']
    for obj in resources:
        obj['metadata']['name'] = ACCOUNT
        for subject in obj.get('subjects', []):
            subject['name'] = ACCOUNT
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
    env = {'POSTGRES_ENABLED': 'true', 'POSTGRES_HOST': 'postgres-postgresql.databases',
           'POSTGRES_PORT': '5432', 'POSTGRES_DATABASE': 'bazarr', 'POSTGRES_USERNAME': 'bazarr',
           'POSTGRES_PASSWORD': {'valueFrom': {'secretKeyRef': {'name': SECRET, 'key': 'password'}}}}
    image = yaml.safe_load((ROOT / 'services/media/bazarr/values.yaml').read_text())['controllers']['main']['containers']['main']['image']
    security = copy.deepcopy(inits['enrollment']['securityContext'])
    security.update(runAsUser=1000, runAsGroup=1000)
    guard = {'image': image, 'command': ['/lsiopy/bin/python3', '-I', '-B', '/retained-startup/guard.py', '/config'],
             'env': copy.deepcopy(env), 'envFrom': [{'secretRef': {'name': 'bazarr-secret'}}],
             'securityContext': security,
             'resources': {'requests': {'cpu': '10m', 'memory': '32Mi'}, 'limits': {'cpu': '100m', 'memory': '64Mi'}}}
    inits['enrollment']['dependsOn'] = 'retained-state'
    inits['database']['dependsOn'] = 'enrollment'
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
        'bazarr-config': {'existingClaim': 'bazarr-config-block', 'globalMounts': [],
            'advancedMounts': {'main': {'main': [{'path': '/config'}],
                'retained-state': [{'path': '/config', 'readOnly': True}]}}},
        'retained-startup': {'type': 'configMap', 'name': 'bazarr-retained-startup-guard', 'defaultMode': 0o444,
            'globalMounts': [], 'advancedMounts': {'main': {
                'retained-state': [{'path': '/retained-startup', 'readOnly': True}],
                'database': [{'path': '/retained-startup', 'readOnly': True}]}}}})
    values = {'controllers': {'main': {'replicas': 1, 'strategy': 'Recreate',
        'serviceAccount': {'name': ACCOUNT}, 'pod': {'securityContext': {},
            'automountServiceAccountToken': False, 'nodeSelector': {'node-role.kubernetes.io/worker': 'true'}},
        'containers': {'main': {'env': env}}, 'initContainers': {'retained-state': guard, **inits}}}, 'persistence': persistence}
    return resources, values


def write_sources():
    directory = HERE / 'production'
    directory.mkdir(exist_ok=True)
    resources, values = build_sources()
    documents = {'values.yaml': [values], 'consumer-gate.yaml': resources,
        'guard-configmap.yaml': [{'apiVersion': 'v1', 'kind': 'ConfigMap',
            'metadata': {'name': 'bazarr-retained-startup-guard', 'namespace': 'media'},
            'data': {name: (HERE / name).read_text() for name in ('guard.py', 'main.sql')}}]}
    for name in ('pv.yaml', 'pvc.yaml'):
        obj = yaml.safe_load((ROOT / 'infrastructure/base-configs/templates/autobrr-block-storage' / name).read_text())
        documents[name] = [yaml.safe_load(yaml.safe_dump(obj, sort_keys=False).replace('autobrr', 'bazarr').replace('1Gi', '4Gi'))]
    documents['source-hold.yaml'] = list(yaml.safe_load_all((ROOT / 'services/media/autobrr/manifests/source-hold.yaml').read_text().replace('autobrr', 'bazarr').replace('Autobrr', 'Bazarr')))
    for name, objects in documents.items():
        (directory / name).write_text(shared.source_yaml(objects))


def prepare_enrollment(output: Path):
    output.mkdir(mode=0o700)
    source = json.loads(yaml.safe_load((ROOT / 'infrastructure/controllers/databases/postgres/manifests/enrollment-configmap.yaml').read_text())['data']['config.json'])
    (output / 'source-config.json').write_text(json.dumps(source, indent=2) + '\n')
    arguments = [sys.executable, str(ROOT / 'scripts/postgres-enrollment/prepare.py'), 'new',
        '--config', str(output / 'source-config.json'), '--id', 'bazarr', '--database', 'bazarr', '--role', 'bazarr',
        '--password-key', 'bazarr-password', '--app-namespace', 'media', '--app-secret', SECRET,
        '--app-password-key', 'password', '--aggregate-secret', str(ROOT / 'infrastructure/controllers/databases/postgres/manifests/enrollment-secret.yaml'),
        '--output-dir', str(output / 'bundle')]
    result = subprocess.run(arguments, capture_output=True, text=True, timeout=90)
    if result.returncode:
        raise ValueError('Inspect preserved enrollment output; never regenerate after partial preparation')
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
        if args.command == 'sources':
            write_sources()
        elif args.output:
            prepare_enrollment(args.output.resolve())
        else:
            raise ValueError('Exclusive output required')
    except (ValueError, OSError, yaml.YAMLError, subprocess.SubprocessError):
        print('Bazarr preparation refused; no credentials printed.', file=sys.stderr)
        raise SystemExit(1) from None
