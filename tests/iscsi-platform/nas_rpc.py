"""JSON-RPC management over pinned TLS through the loopback SSH tunnel."""
import hashlib
import json
import pathlib
import ssl
import websocket

PRIVATE=pathlib.Path(__file__).parent/'.runtime'

class NAS:
    def __init__(self):
        cert=PRIVATE/'ca.pem'
        leaf=PRIVATE/'nas.pem'
        self.ws=websocket.create_connection('wss://127.0.0.1:18443/api/current',timeout=30,
            sslopt={'cert_reqs':ssl.CERT_REQUIRED,'ca_certs':str(cert),'check_hostname':True})
        expected=hashlib.sha256(ssl.PEM_cert_to_DER_cert(leaf.read_text())).digest()
        assert hashlib.sha256(self.ws.sock.getpeercert(binary_form=True)).digest()==expected
        self.sequence=0
        result=self.call('auth.login_ex',{'mechanism':'PASSWORD_PLAIN','username':'truenas_admin',
            'password':(PRIVATE/'nas-password').read_text(),'login_options':{'user_info':False}})
        assert result['response_type']=='SUCCESS', 'Lab NAS authentication failed'
        version=self.call('system.version')
        assert version == 'TrueNAS-25.10.6', repr(version)

    def call(self,method,*params):
        self.sequence+=1
        self.ws.send(json.dumps({'jsonrpc':'2.0','id':self.sequence,'method':method,'params':list(params)}))
        while True:
            response=json.loads(self.ws.recv())
            if response.get('id')==self.sequence:
                if 'error' in response:
                    # Never echo request arguments, which can contain a key or password.
                    raise RuntimeError(method+': '+str(response['error'].get('message','RPC error')))
                return response.get('result')

if __name__=='__main__':
    nas=NAS()
    disks=nas.call('disk.query')
    print(json.dumps({'version':nas.call('system.version'),'disks':[{k:d.get(k) for k in ('name','serial','size','pool')} for d in disks],'boot_disks':nas.call('boot.get_disks')},indent=2))
