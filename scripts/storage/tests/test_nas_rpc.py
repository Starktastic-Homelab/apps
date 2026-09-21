import hashlib
import json
from pathlib import Path
import ssl
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from nas_rpc import NAS

class Socket:
    def getpeercert(self,binary_form): return b'certificate'

class WS:
    def __init__(self): self.sock=Socket(); self.sent=[];self.closed=False;self.error=None
    def send(self,data): self.sent.append(json.loads(data))
    def settimeout(self,value): self.timeout=value
    def recv(self):
        r={'id':self.sent[-1]['id'],'jsonrpc':'2.0'}
        if self.error: r['error']={'message':self.error}
        else: r['result']={'response_type':'SUCCESS'}
        return json.dumps(r)
    def close(self): self.closed=True

class TransportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        d=Path(self.tmp.name);self.creds=d/'credentials';self.ca=d/'ca';self.pin=d/'pin'
        self.creds.write_text('https://nas.example\noperator\nsuper-secret\n');self.creds.chmod(0o600)
        self.pin.write_text(hashlib.sha256(b'certificate').hexdigest());self.ca.write_text('test')
        self.ws=WS();self.connection=patch('websocket.create_connection',return_value=self.ws).start()
        self.addCleanup(patch.stopall)

    def test_tls_and_pin_before_authentication(self):
        with NAS(self.creds,self.ca,self.pin): pass
        opts=self.connection.call_args.kwargs['sslopt']
        self.assertEqual(opts['cert_reqs'],ssl.CERT_REQUIRED)
        self.assertEqual(opts['ca_certs'],str(self.ca))
        self.assertEqual(self.ws.sent[0]['method'],'auth.login_ex');self.assertTrue(self.ws.closed)

    def test_bad_pin_sends_no_password(self):
        self.pin.write_text('0'*64)
        with self.assertRaises(ValueError): NAS(self.creds,self.ca,self.pin)
        self.assertEqual(self.ws.sent,[]);self.assertTrue(self.ws.closed)

    def test_insecure_credentials_refused_before_connection(self):
        self.creds.chmod(0o644)
        with self.assertRaises(ValueError): NAS(self.creds,self.ca,self.pin)
        self.connection.assert_not_called()

    def test_insecure_origin_refused(self):
        self.creds.write_text('http://nas.example\noperator\nsuper-secret')
        with self.assertRaises(ValueError): NAS(self.creds,self.ca,self.pin)
        self.connection.assert_not_called()

    def test_server_errors_redacted_and_not_retried(self):
        with NAS(self.creds,self.ca,self.pin) as nas:
            self.ws.error='CHAP super-secret leaked'
            with self.assertRaises(RuntimeError) as caught: nas.call('iscsi.auth.create',{'secret':'super-secret'})
            self.assertNotIn('super-secret',str(caught.exception))
            self.assertEqual(len(self.ws.sent),2)

    def test_socket_errors_redacted_and_not_retried(self):
        with NAS(self.creds,self.ca,self.pin) as nas:
            self.ws.recv=lambda: (_ for _ in ()).throw(TimeoutError('super-secret'))
            with self.assertRaises(TimeoutError) as caught: nas.call('pool.dataset.update','test',{})
            self.assertNotIn('super-secret',str(caught.exception));self.assertEqual(len(self.ws.sent),2)

    def test_wrong_response_id_is_bounded(self):
        with NAS(self.creds,self.ca,self.pin) as nas:
            self.ws.recv=lambda: json.dumps({'id':999})
            with patch('nas_rpc.time.monotonic',side_effect=[0,0,100]):
                with self.assertRaises(TimeoutError): nas.call('system.version')

if __name__=='__main__': unittest.main()
