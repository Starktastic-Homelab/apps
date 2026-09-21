"""TrueNAS JSON-RPC with CA verification and an independent leaf pin before auth."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import ssl
import stat
import time
from urllib.parse import urlsplit
import websocket


class NAS:
    def __init__(self, credentials: Path, ca: Path, leaf_pin: Path, timeout=25):
        fd = os.open(credentials, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd) as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_uid != os.getuid():
                raise ValueError('Credentials must be a private, owned regular file')
            lines = stream.read().splitlines()
        if len(lines) != 3 or not all(lines):
            raise ValueError('Credentials file requires HTTPS origin, username, password on separate lines')
        origin, username, password = lines
        url = urlsplit(origin)
        if url.scheme != 'https' or not url.hostname or url.username or url.password or url.path not in ('', '/') or url.query or url.fragment:
            raise ValueError('Expected an HTTPS origin without URL credentials')
        pin = leaf_pin.read_text().strip().lower()
        if not re.fullmatch('[0-9a-f]{64}', pin) or not 0 < timeout <= 60:
            raise ValueError('Invalid leaf fingerprint or timeout')
        self.sequence = 0
        self.timeout = timeout
        self.ws = None
        try:
            self.ws = websocket.create_connection('wss://' + url.netloc + '/api/current', timeout=timeout,
                sslopt={'cert_reqs': ssl.CERT_REQUIRED, 'ca_certs': str(ca),
                        # NAS IP is absent from SAN; the independently obtained exact pin
                        # supplies endpoint identity in addition to CA chain validation.
                        'check_hostname': False})
            actual = hashlib.sha256(self.ws.sock.getpeercert(binary_form=True)).hexdigest()
            if not hmac.compare_digest(actual, pin):
                raise ValueError('NAS certificate fingerprint mismatch')
            auth = self.call('auth.login_ex', {'mechanism': 'PASSWORD_PLAIN', 'username': username,
                             'password': password, 'login_options': {'user_info': False}})
            if auth.get('response_type') != 'SUCCESS':
                raise RuntimeError('NAS authentication failed')
        except ValueError:
            self.close()
            raise ValueError('NAS certificate identity check failed') from None
        except Exception:
            self.close()
            raise RuntimeError('NAS connection or authentication failed; no retry') from None

    def call(self, method, *params):
        self.sequence += 1
        deadline = time.monotonic() + self.timeout
        try:
            self.ws.settimeout(self.timeout)
            self.ws.send(json.dumps({'jsonrpc': '2.0', 'id': self.sequence, 'method': method, 'params': list(params)}))
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError()
                self.ws.settimeout(remaining)
                response = json.loads(self.ws.recv())
                if response.get('id') != self.sequence:
                    continue
                if 'error' in response or 'result' not in response:
                    raise RuntimeError()
                return response['result']
        except (TimeoutError, websocket.WebSocketTimeoutException):
            raise TimeoutError('NAS RPC timed out; outcome unknown, reconcile before further mutation') from None
        except Exception:
            # Error payloads can echo credentials, including an auth/CHAP request.
            raise RuntimeError('NAS RPC failed; outcome unknown, inspect without retry') from None

    def close(self):
        if self.ws is not None:
            try:
                self.ws.close()
            except Exception:
                pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
