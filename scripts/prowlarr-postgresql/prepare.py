#!/usr/bin/env python3
"""Generate inactive Prowlarr sources; never contacts SQL or applies Kubernetes resources."""
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
sys.path.insert(0, str(ENROLLMENT))
spec = importlib.util.spec_from_file_location('enrollment_prepare', ENROLLMENT / 'prepare.py')
enrollment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(enrollment)
ACCOUNT = 'prowlarr-postgres-completion'
SECRET = 'prowlarr-postgres-secret'


def build_sources() -> tuple[list[dict], dict]:
    declarations = {}
    for kind in ('main', 'log'):
        declarations[kind] = enrollment.consumer_sources(argparse.Namespace(
            id='prowlarr-' + kind, database='prowlarr_' + kind, role='prowlarr_' + kind,
            app_namespace='media', app_secret=SECRET, app_password_key=kind + '-password'))
    resources, main = declarations['main']
    old_name = resources[0]['metadata']['name']
    for obj in resources:
        obj['metadata']['name'] = ACCOUNT
        for subject in obj.get('subjects', []):
            subject['name'] = ACCOUNT
    inits = {}
    mounts = {}
    for kind, (_, fragment) in declarations.items():
        for init in fragment['initContainers']:
            name = ('enrollment-' if 'acceptance' in init['name'] else 'database-') + kind
            container = {k: copy.deepcopy(v) for k, v in init.items() if k not in ('name', 'volumeMounts')}
            image = container.pop('image')
            container['image'] = {'repository': image.split('@')[0], 'digest': image.split('@')[1]}
            inits[name] = container
            for mount in init['volumeMounts']:
                volume = mount['name']
                if volume == 'pg-completion-password':
                    volume = 'pg-' + kind + '-password'
                mounts.setdefault(volume, {})[name] = [{'path': mount['mountPath'], 'readOnly': True}]
    # Native psql returns success only for retained populated main state.
    inits['database-main']['command'][-1] = (
        'export PGPASSWORD="$(cat /credentials/password)"; '
        'exec psql -XqAt -v ON_ERROR_STOP=1 -f /retained-startup/main.sql >/dev/null 2>&1')
    security = copy.deepcopy(inits['enrollment-main']['securityContext'])
    security.update(runAsUser=1000, runAsGroup=1000)
    guard = {'image': copy.deepcopy(inits['enrollment-main']['image']),
             'command': ['python3', '-I', '-B', '/retained-startup/guard.py', '/config', '/retained-credentials'],
             'securityContext': security,
             'resources': {'requests': {'cpu': '10m', 'memory': '32Mi'}, 'limits': {'cpu': '100m', 'memory': '64Mi'}}}
    predecessor = 'retained-state'
    for name, container in inits.items():
        container['dependsOn'] = predecessor
        predecessor = name
    persistence = {}
    for volume in main['volumes']:
        name = volume['name']
        if name == 'pg-completion-password':
            continue
        if 'configMap' in volume:
            assert volume['configMap']['name'] == old_name
            item = {'type': 'configMap', 'name': ACCOUNT, 'defaultMode': 0o444}
        else:
            item = {'type': 'custom', 'volumeSpec': {'projected': volume['projected']}}
        persistence[name] = dict(item, globalMounts=[], advancedMounts={'main': mounts[name]})
    for kind in ('main', 'log'):
        name = 'pg-' + kind + '-password'
        persistence[name] = {'type': 'secret', 'name': SECRET, 'defaultMode': 0o444,
            'items': [{'key': kind + '-password', 'path': 'password'}], 'globalMounts': [],
            'advancedMounts': {'main': mounts[name]}}
    persistence.update({
        'config': {'enabled': False}, 'media': {'enabled': False},
        'prowlarr-config': {'existingClaim': 'prowlarr-config-block', 'globalMounts': [],
            'advancedMounts': {'main': {'main': [{'path': '/config'}],
                                      'retained-state': [{'path': '/config', 'readOnly': True}]}}},
        'retained-startup': {'type': 'configMap', 'name': 'prowlarr-retained-startup-guard',
            'defaultMode': 0o444, 'globalMounts': [], 'advancedMounts': {'main': {
                'retained-state': [{'path': '/retained-startup', 'readOnly': True}],
                'database-main': [{'path': '/retained-startup', 'readOnly': True}]}}},
        'retained-credentials': {'type': 'secret', 'name': SECRET, 'defaultMode': 0o444,
            'items': [{'key': k + '-password', 'path': k + '-password'} for k in ('main', 'log')],
            'globalMounts': [], 'advancedMounts': {'main': {
                'retained-state': [{'path': '/retained-credentials', 'readOnly': True}]}}}})
    values = {'controllers': {'main': {'replicas': 1, 'strategy': 'Recreate',
        'serviceAccount': {'name': ACCOUNT}, 'pod': {'securityContext': {},
            'automountServiceAccountToken': False, 'nodeSelector': {'node-role.kubernetes.io/worker': 'true'}},
        'initContainers': {'retained-state': guard, **inits}}}, 'persistence': persistence}
    return resources, values


def write_sources() -> None:
    directory = HERE / 'production'
    directory.mkdir(exist_ok=True)
    resources, values = build_sources()
    guard = {'apiVersion': 'v1', 'kind': 'ConfigMap',
             'metadata': {'name': 'prowlarr-retained-startup-guard', 'namespace': 'media'},
             'data': {name: (HERE / name).read_text() for name in ('guard.py', 'main.sql')}}
    documents = {'values.yaml': [values], 'consumer-gate.yaml': resources, 'guard-configmap.yaml': [guard]}
    for name in ('pv.yaml', 'pvc.yaml'):
        obj = yaml.safe_load((ROOT / 'infrastructure/base-configs/templates/autobrr-block-storage' / name).read_text())
        text = yaml.safe_dump(obj, sort_keys=False).replace('autobrr', 'prowlarr').replace('1Gi', '4Gi')
        documents[name] = [yaml.safe_load(text)]
    text = (ROOT / 'services/media/autobrr/manifests/source-hold.yaml').read_text().replace('autobrr', 'prowlarr').replace('Autobrr', 'Prowlarr')
    documents['source-hold.yaml'] = list(yaml.safe_load_all(text))
    for name, objects in documents.items():
        (directory / name).write_text(yaml.safe_dump_all(objects, sort_keys=False, width=120))


def prepare_enrollment(output: Path) -> None:
    # Preserve intermediate ciphertext on failure. A repeated output is refused;
    # inspect and resume from those exact bundles rather than generating again.
    output.mkdir(mode=0o700)
    config = json.loads(yaml.safe_load((ROOT / 'infrastructure/controllers/databases/postgres/manifests/enrollment-configmap.yaml').read_text())['data']['config.json'])
    (output / 'source-config.json').write_text(json.dumps(config, indent=2) + '\n')
    aggregate = ROOT / 'infrastructure/controllers/databases/postgres/manifests/enrollment-secret.yaml'
    previous = None
    for kind in ('main', 'log'):
        arguments = [sys.executable, str(ENROLLMENT / 'prepare.py'), 'new',
            '--config', str(output / ('source-config.json' if kind == 'main' else 'main/config.json')),
            '--id', 'prowlarr-' + kind, '--database', 'prowlarr_' + kind, '--role', 'prowlarr_' + kind,
            '--password-key', 'prowlarr-' + kind + '-password', '--app-namespace', 'media',
            '--app-secret', SECRET, '--app-password-key', kind + '-password',
            '--aggregate-secret', str(aggregate), '--output-dir', str(output / kind)]
        if previous:
            arguments += ['--app-sealed-secret', str(previous)]
        result = subprocess.run(arguments, capture_output=True, text=True, timeout=90)
        if result.returncode:
            raise ValueError('Enrollment preparation failed; inspect exact intermediate bundle, do not regenerate')
        aggregate = output / kind / 'enrollment-secret.yaml'
        previous = output / kind / 'application-secret.yaml'


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
        print('Prowlarr preparation refused; no credential data printed.', file=sys.stderr)
        raise SystemExit(1) from None
