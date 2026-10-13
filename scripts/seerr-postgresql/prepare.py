#!/usr/bin/env python3
"""Prepare inactive Seerr sources and ciphertext; never applies resources or contacts SQL."""
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
ENROLLMENT = ROOT / 'scripts/postgres-enrollment'
# Reuse the qualified serializer and enrollment adapter; neither import writes files.
spec = importlib.util.spec_from_file_location('prowlarr_prepare', ROOT / 'scripts/prowlarr-postgresql/prepare.py')
shared = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shared)
enrollment = shared.enrollment
source_yaml = shared.source_yaml


def build_sources(instance: str) -> tuple[list[dict], dict]:
    if instance not in ('seerr', 'seerr-ru'):
        raise ValueError('Unknown instance')
    database = instance.replace('-', '_')
    account, secret = instance + '-postgres-completion', instance + '-postgres-secret'
    resources, fragment = enrollment.consumer_sources(argparse.Namespace(
        id=instance, database=database, role=database, app_namespace='media', app_secret=secret, app_password_key='password'))
    old = resources[0]['metadata']['name']
    for obj in resources:
        obj['metadata']['name'] = account
        for subject in obj.get('subjects', []):
            subject['name'] = account
    inits, mounts = {}, {}
    for name, original in zip(('enrollment', 'database'), fragment['initContainers']):
        container = copy.deepcopy(original)
        container.pop('name')
        image = container.pop('image')
        container['image'] = {'repository': image.split('@')[0], 'digest': image.split('@')[1]}
        for mount in container.pop('volumeMounts'):
            mounts.setdefault(mount['name'], {})[name] = [{'path': mount['mountPath'], 'readOnly': True}]
        inits[name] = container
    inits['database']['command'][-1] = ('export PGPASSWORD="$(cat /credentials/password)"; '
        'exec psql -XqAt -v ON_ERROR_STOP=1 -f /retained-startup/main.sql >/dev/null 2>&1')
    env = {'NODE_ENV': 'production', 'DB_TYPE': 'postgres', 'DB_HOST': 'postgres-postgresql.databases',
           'DB_PORT': '5432', 'DB_USER': database, 'DB_NAME': database, 'DB_POOL_SIZE': '3',
           'DB_PASS': {'valueFrom': {'secretKeyRef': {'name': secret, 'key': 'password'}}}}
    security = copy.deepcopy(inits['enrollment']['securityContext'])
    security.update(runAsUser=1000, runAsGroup=1000)
    guard = {'image': copy.deepcopy(inits['enrollment']['image']),
        'command': ['python3', '-I', '-B', '/retained-startup/guard.py', '/app/config', instance],
        'env': copy.deepcopy(env), 'securityContext': security,
        'resources': {'requests': {'cpu': '10m', 'memory': '32Mi'}, 'limits': {'cpu': '100m', 'memory': '64Mi'}}}
    inits['enrollment']['dependsOn'] = 'retained-state'
    inits['database']['dependsOn'] = 'enrollment'
    persistence = {}
    for volume in fragment['volumes']:
        name = volume['name']
        if 'configMap' in volume:
            assert volume['configMap']['name'] == old
            item = {'type': 'configMap', 'name': account, 'defaultMode': 0o444}
        elif 'projected' in volume:
            item = {'type': 'custom', 'volumeSpec': {'projected': volume['projected']}}
        else:
            item = {'type': 'secret', 'name': secret, 'defaultMode': 0o444,
                    'items': [{'key': 'password', 'path': 'password'}]}
        persistence[name] = dict(item, globalMounts=[], advancedMounts={'main': mounts[name]})
    persistence.update({
        'config': {'enabled': False}, 'media': {'enabled': False},
        'seerr-config': {'existingClaim': instance + '-config-block', 'globalMounts': [],
            'advancedMounts': {'main': {'main': [{'path': '/app/config'}],
                'retained-state': [{'path': '/app/config', 'readOnly': True}]}}},
        'retained-startup': {'type': 'configMap', 'name': 'seerr-retained-startup-guard',
            'defaultMode': 0o444, 'globalMounts': [], 'advancedMounts': {'main': {
                'retained-state': [{'path': '/retained-startup', 'readOnly': True}],
                'database': [{'path': '/retained-startup', 'readOnly': True}]}}}})
    values = {'controllers': {'main': {'replicas': 1, 'strategy': 'Recreate',
        'serviceAccount': {'name': account}, 'pod': {'securityContext': {},
            'automountServiceAccountToken': False, 'nodeSelector': {'node-role.kubernetes.io/worker': 'true'}},
        'containers': {'main': {'env': env, 'probes': {name: {'path': '/api/v1/status/appdata'}
            for name in ('liveness', 'readiness', 'startup')}}},
        'initContainers': {'retained-state': guard, **inits}}}, 'persistence': persistence}
    return resources, values


def overrides(base: dict, variant: dict) -> dict:
    result = {}
    for key, value in variant.items():
        if value == base.get(key):
            continue
        result[key] = overrides(base[key], value) if isinstance(value, dict) and isinstance(base.get(key), dict) else value
    return result


def write_sources() -> None:
    directory = HERE / 'production'
    directory.mkdir(exist_ok=True)
    base = build_sources('seerr')[1]
    guard = {'apiVersion': 'v1', 'kind': 'ConfigMap',
        'metadata': {'name': 'seerr-retained-startup-guard', 'namespace': 'media'},
        'data': {name: (HERE / name).read_text() for name in ('guard.py', 'main.sql')}}
    (directory / 'values.yaml').write_text(source_yaml([base]))
    (directory / 'guard-configmap.yaml').write_text(source_yaml([guard]))
    for instance in ('seerr', 'seerr-ru'):
        folder = directory / instance
        folder.mkdir(exist_ok=True)
        resources, values = build_sources(instance)
        metadata = {'manifests': True}
        if instance == 'seerr-ru':
            metadata['valuesOverride'] = True
            (folder / 'values.yaml').write_text(source_yaml([overrides(base, values)]))
        documents = {'app-metadata.yaml': [metadata], 'consumer-gate.yaml': resources}
        for name in ('pv.yaml', 'pvc.yaml'):
            text = (ROOT / 'infrastructure/base-configs/templates/prowlarr-block-storage' / name).read_text().replace('prowlarr', instance)
            documents[name] = [yaml.safe_load(text)]
        text = (ROOT / 'services/media/prowlarr/manifests/source-hold.yaml').read_text().replace('prowlarr', instance).replace('Prowlarr', instance)
        documents['source-hold.yaml'] = list(yaml.safe_load_all(text))
        for name, objects in documents.items():
            (folder / name).write_text(source_yaml(objects))


def prepare_enrollment(output: Path) -> None:
    output.mkdir(mode=0o700)  # Exclusive reservation precedes any credential generation.
    config = json.loads(yaml.safe_load((ROOT / 'infrastructure/controllers/databases/postgres/manifests/enrollment-configmap.yaml').read_text())['data']['config.json'])
    (output / 'source-config.json').write_text(json.dumps(config, indent=2) + '\n')
    aggregate = ROOT / 'infrastructure/controllers/databases/postgres/manifests/enrollment-secret.yaml'
    for instance in ('seerr', 'seerr-ru'):
        args = [sys.executable, str(ENROLLMENT / 'prepare.py'), 'new',
            '--config', str(output / ('source-config.json' if instance == 'seerr' else 'seerr/config.json')),
            '--id', instance, '--database', instance.replace('-', '_'), '--role', instance.replace('-', '_'),
            '--password-key', instance + '-password', '--app-namespace', 'media',
            '--app-secret', instance + '-postgres-secret', '--app-password-key', 'password',
            '--aggregate-secret', str(aggregate), '--output-dir', str(output / instance)]
        result = subprocess.run(args, capture_output=True, text=True, timeout=90)
        if result.returncode:
            raise ValueError('Enrollment preparation failed; preserve exact intermediate bundle')
        aggregate = output / instance / 'enrollment-secret.yaml'
    publish_enrollment(output)


def publish_enrollment(output: Path) -> None:
    directory = HERE / 'production/enrollment'
    directory.mkdir(exist_ok=True)
    for name in ('enrollment-configmap.yaml', 'enrollment-job.yaml', 'enrollment-secret.yaml'):
        (directory / name).write_text(source_yaml([yaml.safe_load((output / 'seerr-ru' / name).read_text())]))
    for instance in ('seerr', 'seerr-ru'):
        (directory / (instance + '-application-secret.yaml')).write_text(
            source_yaml([yaml.safe_load((output / instance / 'application-secret.yaml').read_text())]))


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
        print('Seerr preparation refused; private data suppressed.', file=sys.stderr)
        raise SystemExit(1) from None
