#!/usr/bin/env python3
"""Prepare reviewable encrypted inputs once. Never contacts PostgreSQL or applies resources."""
import argparse
import copy
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


def render_configmap(config: dict) -> dict:
    validate_config(config)
    return {'apiVersion': 'v1', 'kind': 'ConfigMap',
            'metadata': {'name': 'postgres-enrollment-config', 'namespace': 'databases',
                         'annotations': {'argocd.argoproj.io/sync-wave': '-1'}},
            'data': {'config.json': json.dumps(config, indent=2) + '\n',
                     **{name: (ROOT / 'runtime' / name).read_text()
                        for name in ('enroll.sh', 'enroll.sql', 'schema.sql')}}}


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
        if (obj['spec']['template'].get('type') != 'Opaque'
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
        documents = {'config.json': json.dumps(config, indent=2) + '\n',
                     'enrollment-configmap.yaml': yaml.safe_dump(render_configmap(config), sort_keys=False),
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
