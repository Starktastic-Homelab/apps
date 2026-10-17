#!/usr/bin/env python3
"""Fail before the upstream registration hook unless retained identities unseal."""
import base64
import binascii
import json
import os
from pathlib import Path
import ssl
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPSHandler, HTTPRedirectHandler, ProxyHandler, Request, build_opener

IDENTITIES = {'crowdsec-capi-credentials': {'online_api_credentials.yaml'},
              'crowdsec-lapi-secrets': {'csLapiSecret', 'registrationToken'}}


def accepted(sealed, secret, name, keys, namespace='crowdsec'):
    try:
        for resource in (sealed, secret):
            if resource['metadata']['name'] != name or resource['metadata']['namespace'] != namespace:
                return False
        if (sealed['status']['observedGeneration'] != sealed['metadata']['generation']
                or not any(c['type'] == 'Synced' and c['status'] == 'True'
                           for c in sealed['status']['conditions'])
                or secret['metadata'].get('ownerReferences')
                or secret['type'] != 'Opaque' or set(secret['data']) != keys):
            return False
        return all(0 < len(base64.b64decode(v, validate=True)) <= 65536 for v in secret['data'].values())
    except (KeyError, TypeError, ValueError, binascii.Error):
        return False


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def main():
    namespace = os.environ['POD_NAMESPACE']
    root = Path('/var/run/secrets/kubernetes.io/serviceaccount')
    token = root.joinpath('token').read_text().strip()
    context = ssl.create_default_context(cafile=str(root / 'ca.crt'))
    opener = build_opener(ProxyHandler({}), HTTPSHandler(context=context), NoRedirect())
    def fetch(path):
        request = Request('https://kubernetes.default.svc' + path,
                          headers={'Authorization': 'Bearer ' + token})
        with opener.open(request, timeout=10) as response:
            body = response.read(1024 * 1024 + 1)
            if len(body) > 1024 * 1024:
                raise ValueError('Oversized credential metadata')
            return json.loads(body)
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        try:
            if all(accepted(fetch('/apis/bitnami.com/v1alpha1/namespaces/' + namespace + '/sealedsecrets/' + name),
                            fetch('/api/v1/namespaces/' + namespace + '/secrets/' + name), name, keys, namespace)
                   for name, keys in IDENTITIES.items()):
                print('Retained CrowdSec identities restored before registration.')
                return
        except (HTTPError, URLError, OSError, ValueError, KeyError, TypeError):
            pass
        time.sleep(2)
    raise SystemExit('Retained credential restore not accepted; registration remains blocked.')


if __name__ == '__main__':
    main()
