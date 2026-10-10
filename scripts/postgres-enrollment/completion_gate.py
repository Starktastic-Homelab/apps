#!/usr/bin/env python3
"""Read-only, fail-closed native Argo enrollment acceptance for consumer init."""
import argparse
import hashlib
from http.client import HTTPException
import json
from pathlib import Path
import ssl
import time
from urllib.request import HTTPSHandler, HTTPRedirectHandler, ProxyHandler, Request, build_opener

CONFIG_PATH = '/api/v1/namespaces/databases/configmaps/postgres-enrollment-config'
APPLICATION_PATH = '/apis/argoproj.io/v1alpha1/namespaces/argocd/applications/postgres'
MAX_RESPONSE = 1024 * 1024
REQUIRED_DATA = {'config.json', 'enroll.sh', 'enroll.sql', 'schema.sql', 'completion_gate.py',
                 'completion-protocol-version', 'encrypted-inputs-sha256', 'job-template.json'}


def generation(data: dict) -> str:
    inputs = {key: value for key, value in data.items() if key != 'acceptance-generation'}
    return hashlib.sha256(json.dumps(inputs, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def hook_name(value: str) -> str:
    return 'postgres-enrollment-' + value[:32]


def accepted(configmap: dict, application: dict, identity: dict) -> bool:
    try:
        if (configmap['metadata']['name'] != 'postgres-enrollment-config'
                or configmap['metadata']['namespace'] != 'databases'
                or application['metadata']['name'] != 'postgres'
                or application['metadata']['namespace'] != 'argocd'
                or application.get('operation') is not None):
            return False
        data = configmap['data']
        if (not REQUIRED_DATA <= set(data) or not all(isinstance(v, str) for v in data.values())
                or data['completion-protocol-version'] != '1'
                or data['acceptance-generation'] != generation(data)):
            return False
        config = json.loads(data['config.json'])
        if type(config['version']) is not int or config['version'] != 1:
            return False
        entries = [entry for entry in config['entries'] if entry['id'] == identity['id']]
        if len(entries) != 1 or any(entries[0][key] != identity[key] for key in ('database', 'role')):
            return False
        status = application['status']
        state = status['operationState']
        sync = state['operation']['sync']
        revisions = (status['sync']['revisions'], state['syncResult']['revisions'])
        if (state['phase'] != 'Succeeded' or status['sync']['status'] != 'Synced'
                or status['health']['status'] != 'Healthy'
                or sync.get('resources') is not None or sync.get('dryRun') is True
                or 'apply' in sync.get('syncStrategy', {})
                or any(not isinstance(values, list) or not values
                       or not all(isinstance(v, str) and v for v in values) for values in revisions)):
            return False
        # A newer unrelated Git commit can be Synced without a new operation.
        # The current input fingerprint, rather than repository SHA, binds acceptance.
        hooks = [resource for resource in state['syncResult']['resources']
                 if resource.get('group') == 'batch' and resource.get('kind') == 'Job'
                 and resource.get('namespace') == 'databases'
                 and resource.get('name') == hook_name(data['acceptance-generation'])]
        return (len(hooks) == 1 and hooks[0].get('hookType') == 'Sync'
                and hooks[0].get('hookPhase') == 'Succeeded')
    except (KeyError, TypeError, ValueError, AttributeError):
        return False


def check_once(get, identity: dict) -> bool:
    try:
        before = get(CONFIG_PATH)
        application = get(APPLICATION_PATH)
        after = get(CONFIG_PATH)
        # ResourceVersion catches updates even if the configuration changes back.
        for key in ('uid', 'resourceVersion'):
            if not before['metadata'][key] or before['metadata'][key] != after['metadata'][key]:
                return False
        return before['data'] == after['data'] and accepted(after, application, identity)
    except (OSError, HTTPException, KeyError, TypeError, ValueError, AttributeError):
        return False


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise OSError('Kubernetes API redirect refused')


class APIReader:
    def __init__(self):
        directory = Path('/gate-api')
        self.token = lambda: (directory / 'token').read_text().strip()
        self.opener = build_opener(ProxyHandler({}), NoRedirect(),
                                   HTTPSHandler(context=ssl.create_default_context(cafile=str(directory / 'ca.crt'))))

    def get(self, path: str) -> dict:
        if path not in (CONFIG_PATH, APPLICATION_PATH):
            raise ValueError('Unexpected Kubernetes resource')
        request = Request('https://kubernetes.default.svc' + path,
                          headers={'Authorization': 'Bearer ' + self.token(), 'Accept': 'application/json'})
        with self.opener.open(request, timeout=10) as response:
            payload = response.read(MAX_RESPONSE + 1)
        if len(payload) > MAX_RESPONSE:
            raise ValueError('Kubernetes response exceeds limit')
        result = json.loads(payload)
        if not isinstance(result, dict):
            raise ValueError('Expected Kubernetes object')
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('id', 'database', 'role'):
        parser.add_argument('--' + key, required=True)
    args = parser.parse_args()
    deadline = time.monotonic() + 600
    print('Waiting for current PostgreSQL enrollment acceptance', flush=True)
    while time.monotonic() < deadline:
        try:
            if check_once(APIReader().get, vars(args)):
                print('Current PostgreSQL enrollment accepted', flush=True)
                return 0
        except (OSError, HTTPException, ValueError):
            pass
        time.sleep(5)
    print('PostgreSQL enrollment acceptance unavailable; startup remains blocked', flush=True)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
