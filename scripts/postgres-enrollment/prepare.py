#!/usr/bin/env python3
"""Prepare reviewable encrypted inputs once. Never contacts PostgreSQL or applies resources."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import quote

import yaml

from completion_gate import generation, hook_name

ROOT = Path(__file__).resolve().parent
NAME = re.compile(r'[a-z][a-z0-9_]{0,62}', re.ASCII)
KEY = re.compile(r'[a-z][a-z0-9_-]{0,62}', re.ASCII)
KUBE_NAME = re.compile(r'[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?', re.ASCII)
AGGREGATE = 'postgres-enrollment-credentials'


def validate_config(config: dict) -> None:
    if (not isinstance(config, dict) or set(config) != {'version', 'expectedSystemIdentifier', 'entries'}
            or type(config['version']) is not int or config['version'] != 1
            or not isinstance(config['expectedSystemIdentifier'], str)
            or not re.fullmatch(r'[0-9]+', config['expectedSystemIdentifier'], re.ASCII)
            or not isinstance(config['entries'], list)):
        raise ValueError('Invalid enrollment config')
    seen = {key: set() for key in ('id', 'database', 'role', 'passwordKey')}
    for entry in config['entries']:
        if not isinstance(entry, dict) or set(entry) != {'id', 'database', 'role', 'mode', 'passwordKey'}:
            raise ValueError('Invalid enrollment entry')
        if entry['mode'] not in ('new', 'adopt'):
            raise ValueError('Invalid enrollment mode')
        for key in seen:
            value = entry[key]
            pattern = NAME if key in ('database', 'role') else KEY
            if not isinstance(value, str) or not pattern.fullmatch(value) or value in seen[key]:
                raise ValueError('Invalid or duplicate enrollment identity')
            seen[key].add(value)
        if (entry['role'] == 'postgres' or entry['role'].startswith('pg_')
                or entry['database'] in ('postgres', 'template0', 'template1')):
            raise ValueError('Reserved PostgreSQL identity')


def render_configmap(config: dict, encrypted_data=None) -> dict:
    validate_config(config)
    result = {'apiVersion': 'v1', 'kind': 'ConfigMap',
            'metadata': {'name': 'postgres-enrollment-config', 'namespace': 'databases',
                         'annotations': {'argocd.argoproj.io/sync-wave': '-1'}},
            'data': {'config.json': json.dumps(config, indent=2) + '\n',
                     **{name: (ROOT / 'runtime' / name).read_text()
                        for name in ('enroll.sh', 'enroll.sql', 'schema.sql')}}}

    if encrypted_data is not None:
        data = result['data']
        data.update({'completion-protocol-version': '1',
                     'completion_gate.py': (ROOT / 'completion_gate.py').read_text(),
                     'encrypted-inputs-sha256': hashlib.sha256(json.dumps(
                         encrypted_data, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
                     'job-template.json': json.dumps(yaml.safe_load((ROOT / 'job.yaml').read_text()),
                                                     sort_keys=True, separators=(',', ':'))})
        data['acceptance-generation'] = generation(data)
    return result


def consumer_sources(options) -> tuple[list[dict], dict]:
    # Include the enrollment ID: several credentials may share an application Secret.
    suffix = hashlib.sha256(json.dumps([options.id, options.app_namespace, options.app_secret]).encode()).hexdigest()[:20]
    name = 'pg-enrollment-' + suffix
    metadata = {'name': name, 'namespace': options.app_namespace,
                'annotations': {'argocd.argoproj.io/sync-wave': '-1'}}
    resources = [{'apiVersion': 'v1', 'kind': 'ServiceAccount', 'metadata': metadata,
                  'automountServiceAccountToken': False},
                 {'apiVersion': 'v1', 'kind': 'ConfigMap', 'metadata': metadata,
                  'data': {'completion_gate.py': (ROOT / 'completion_gate.py').read_text()}}]
    for namespace in ('argocd', 'databases'):
        resources.append({'apiVersion': 'rbac.authorization.k8s.io/v1', 'kind': 'RoleBinding',
                          'metadata': {**metadata, 'namespace': namespace},
                          'roleRef': {'apiGroup': 'rbac.authorization.k8s.io', 'kind': 'Role',
                                      'name': 'postgres-enrollment-completion-reader'},
                          'subjects': [{'kind': 'ServiceAccount', 'name': name,
                                        'namespace': options.app_namespace}]})
    security = {'runAsNonRoot': True, 'runAsUser': 1001, 'runAsGroup': 1001,
                'allowPrivilegeEscalation': False, 'readOnlyRootFilesystem': True,
                'capabilities': {'drop': ['ALL']}, 'seccompProfile': {'type': 'RuntimeDefault'}}
    def mount(volume, path):
        return {'name': volume, 'mountPath': path, 'readOnly': True}
    fragment = {
        'serviceAccountName': name, 'automountServiceAccountToken': False,
        'initContainers': [
            {'name': 'postgres-enrollment-acceptance',
             'image': 'python@sha256:a11116e648ddd8a05e1120014c8e6ac259f718040b67e2dcd6a7c0b7bab3ff2c',
             'command': ['python3', '-B', '/gate/completion_gate.py'],
             'args': ['--id', options.id, '--database', options.database, '--role', options.role],
             'securityContext': security,
             'resources': {'requests': {'cpu': '25m', 'memory': '32Mi'}, 'limits': {'cpu': '100m', 'memory': '64Mi'}},
             'volumeMounts': [mount('pg-completion-script', '/gate'), mount('pg-completion-api', '/gate-api')]},
            {'name': 'postgres-canonical-login',
             'image': yaml.safe_load((ROOT / 'job.yaml').read_text())['spec']['template']['spec']['containers'][0]['image'],
             'command': ['/bin/sh', '-ec',
                         'export PGPASSWORD="$(cat /credentials/password)"; '
                         'exec psql -XqAt -v ON_ERROR_STOP=1 -c "SELECT 1" >/dev/null 2>&1'],
             'env': [{'name': k, 'value': v} for k, v in {
                 'PGHOST': 'postgres-postgresql.databases', 'PGPORT': '5432',
                 'PGUSER': options.role, 'PGDATABASE': options.database, 'PGCONNECT_TIMEOUT': '10'}.items()],
             'securityContext': security,
             'resources': {'requests': {'cpu': '10m', 'memory': '16Mi'}, 'limits': {'cpu': '100m', 'memory': '32Mi'}},
             'volumeMounts': [mount('pg-completion-password', '/credentials')]}],
        'volumes': [
            {'name': 'pg-completion-script', 'configMap': {'name': name, 'defaultMode': 0o444}},
            {'name': 'pg-completion-api', 'projected': {'defaultMode': 0o444, 'sources': [
                {'serviceAccountToken': {'path': 'token', 'expirationSeconds': 600}},
                {'configMap': {'name': 'kube-root-ca.crt', 'items': [{'key': 'ca.crt', 'path': 'ca.crt'}]}}]}},
            {'name': 'pg-completion-password', 'secret': {'secretName': options.app_secret,
                'defaultMode': 0o444, 'items': [{'key': options.app_password_key, 'path': 'password'}]}}]}
    return resources, fragment


def validate_sealed(obj, name, namespace):
    try:
        if obj['apiVersion'] != 'bitnami.com/v1alpha1' or obj['kind'] != 'SealedSecret':
            raise ValueError('Expected SealedSecret')
        for metadata in (obj['metadata'], obj['spec']['template']['metadata']):
            if metadata['name'] != name or metadata['namespace'] != namespace:
                raise ValueError('SealedSecret identity/scope mismatch')
            annotations = metadata.get('annotations', {})
            if any(annotations.get('sealedsecrets.bitnami.com/' + scope) not in (None, 'false')
                   for scope in ('cluster-wide', 'namespace-wide')):
                raise ValueError('Strict sealing scope required')
        if (obj['spec']['template'].get('type', 'Opaque') != 'Opaque'
                or 'data' in obj['spec']['template'] or 'stringData' in obj['spec']['template']
                or 'data' in obj or 'stringData' in obj
                or not isinstance(obj['spec']['encryptedData'], dict)
                or not all(isinstance(k, str) and isinstance(v, str) and v
                           for k, v in obj['spec']['encryptedData'].items())):
            raise ValueError('Invalid sealed payload')
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError('Invalid SealedSecret shape') from error


def existing(path, name, namespace, new_keys):
    if path is None:
        return None
    obj = yaml.safe_load(Path(path).read_text())
    validate_sealed(obj, name, namespace)
    if set(new_keys) & set(obj['spec']['encryptedData']):
        raise ValueError('Credential key already sealed; refusing replacement')
    return obj


def seal(stage, name, namespace, values, previous):
    # seal.sh invokes kubectl --dry-run=client and kubeseal with the repository public certificate.
    # Plaintext streams privately through stdin; there are no plaintext temporary files.
    try:
        subprocess.run([str(ROOT.parent / 'seal.sh'), name, namespace],
                       input=''.join(key + '=' + value + '\n' for key, value in values.items()),
                       text=True, capture_output=True, check=True, cwd=stage, timeout=30)
        obj = yaml.safe_load((stage / (name + '.yaml')).read_text())
        validate_sealed(obj, name, namespace)
        if set(obj['spec']['encryptedData']) != set(values):
            raise ValueError('Unexpected sealing output keys')
    except (subprocess.SubprocessError, OSError, yaml.YAMLError) as error:
        # Subprocess exceptions may contain private stderr/stdin: never chain them to CLI logs.
        raise ValueError('Credential sealing failed; no bundle published') from None
    if previous is not None:
        merged = copy.deepcopy(previous)
        merged['spec']['encryptedData'].update(obj['spec']['encryptedData'])
        obj = merged
    obj['metadata'].setdefault('annotations', {})['argocd.argoproj.io/sync-wave'] = '-1'
    return obj


def prepare_bundle(options: argparse.Namespace) -> Path:
    output = Path(options.output_dir)
    if output.exists():
        raise ValueError('Output already exists; refusing regeneration or overwrite')
    config = json.loads(Path(options.config).read_text())
    validate_config(config)
    entry = {'id': options.id, 'database': options.database, 'role': options.role,
             'mode': options.mode, 'passwordKey': options.password_key}
    config['entries'].append(entry)
    validate_config(config)
    for name in (options.app_namespace, options.app_secret):
        if not KUBE_NAME.fullmatch(name):
            raise ValueError('Invalid Kubernetes identity')
    if options.app_namespace == 'databases' and options.app_secret in (AGGREGATE, 'postgres-admin-secret'):
        raise ValueError('Application Secret conflicts with enrollment or administrator credentials')
    app_keys = [options.app_password_key]
    if options.app_url_key is not None:
        app_keys.append(options.app_url_key)
    if len(set(app_keys)) != len(app_keys) or any(not KEY.fullmatch(k) for k in app_keys):
        raise ValueError('Invalid or duplicate application credential key')
    aggregate = existing(options.aggregate_secret, AGGREGATE, 'databases', [options.password_key])
    app = existing(options.app_sealed_secret, options.app_secret, options.app_namespace, app_keys)
    # Once config has other declarations, their ciphertext must be provided and retained.
    prior_keys = {e['passwordKey'] for e in config['entries'][:-1]}
    if prior_keys and (aggregate is None or not prior_keys <= set(aggregate['spec']['encryptedData'])):
        raise ValueError('Existing aggregate ciphertext is required for prior declarations')
    password = secrets.token_urlsafe(48) if options.mode == 'new' else sys.stdin.read()
    if not password or len(password.encode()) > 4096 or any(c in password for c in '\x00\r\n'):
        raise ValueError('Password must be nonempty UTF-8 without NUL/CR/LF, at most 4096 bytes')
    values = {options.app_password_key: password}
    if options.app_url_key:
        values[options.app_url_key] = ('postgresql://' + options.role + ':' + quote(password, safe='')
                                       + '@postgres-postgresql.databases:5432/' + options.database)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.pg-enrollment-', dir=output.parent) as directory:
        stage = Path(directory)
        stage.chmod(0o700)
        # Separate cwd directories avoid filename collision when both Secrets share a name.
        a, b = stage / 'aggregate', stage / 'application'
        a.mkdir(mode=0o700); b.mkdir(mode=0o700)
        encrypted = seal(a, AGGREGATE, 'databases', {options.password_key: password}, aggregate)
        client = seal(b, options.app_secret, options.app_namespace, values, app)
        configmap = render_configmap(config, encrypted['spec']['encryptedData'])
        job = json.loads(configmap['data']['job-template.json'])
        job['metadata']['name'] = hook_name(configmap['data']['acceptance-generation'])
        consumer, init = consumer_sources(options)
        documents = {'enrollment-job.yaml': yaml.safe_dump(job, sort_keys=False),
                     'consumer-gate.yaml': yaml.safe_dump_all(consumer, sort_keys=False),
                     'consumer-init.yaml': yaml.safe_dump(init, sort_keys=False),
                     'config.json': json.dumps(config, indent=2) + '\n',
                     'enrollment-configmap.yaml': yaml.safe_dump(configmap, sort_keys=False),
                     'enrollment-secret.yaml': yaml.safe_dump(encrypted, sort_keys=False),
                     'application-secret.yaml': yaml.safe_dump(client, sort_keys=False)}
        # Exclusive reservation: concurrent/repeated runs cannot replace another bundle.
        try:
            output.mkdir(mode=0o700)
        except FileExistsError:
            raise ValueError('Output already exists; refusing replacement') from None
        try:
            for name, text in documents.items():
                target = output / name
                with target.open('x') as stream:
                    os.chmod(target, 0o600)
                    stream.write(text)
        except Exception:
            shutil.rmtree(output)
            raise
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('new', 'adopt'))
    for arg in ('config', 'id', 'database', 'role', 'password-key', 'app-namespace', 'app-secret',
                'app-password-key', 'output-dir'):
        parser.add_argument('--' + arg, required=True)
    for arg in ('app-url-key', 'aggregate-secret', 'app-sealed-secret'):
        parser.add_argument('--' + arg)
    options = parser.parse_args()
    try:
        print('Prepared encrypted bundle:', prepare_bundle(options))
    except (ValueError, OSError, yaml.YAMLError):
        print('Preparation failed; inputs or sealing rejected. No credentials printed.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
