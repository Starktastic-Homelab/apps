"""Pinned TrueNAS installer RPC. Credentials stay in the private run directory."""
import json
import pathlib
import sys
import secrets
import websocket

private=pathlib.Path(__file__).parent/'.runtime'
ws=websocket.create_connection('ws://127.0.0.1:18080/ws',timeout=30)
sequence=0

def call(method, params=None):
    global sequence
    sequence+=1
    request={'jsonrpc':'2.0','id':sequence,'method':method}
    if params is not None: request['params']=[params]
    ws.send(json.dumps(request))
    while True:
        answer=json.loads(ws.recv())
        if answer.get('id')==sequence:
            if 'error' in answer: raise RuntimeError(str(answer['error']))
            return answer.get('result')
        if answer.get('method')=='installation_progress':
            print(json.dumps({'progress':answer.get('params')}),flush=True)

key=private/'installer-key'
if key.exists(): call('authenticate',key.read_text())
else:
    assert call('is_adopted') is False
    value=call('adopt');key.write_text(value);key.chmod(0o600)
info=call('system_info');assert info['version']=='25.10.7',info
disks=call('list_disks');interfaces=call('list_network_interfaces')
if '--install' in sys.argv:
    assert not info['installation_running'] and not info['installation_completed']
    assert len(disks)==1 and disks[0]['name']=='sda' and disks[0]['size']==16*1024**3 and not disks[0]['zfs_members'], 'Boot disk is not uniquely identified'
    assert {x['name'] for x in interfaces}=={'enp6s18','enp6s19'}
    password=private/'nas-password'
    if not password.exists():
        password.write_text(secrets.token_urlsafe(32));password.chmod(0o600)
    ws.settimeout(900)
    call('install',{'disks':['sda'],'wipe_disks':[],'set_pmbr':False,
        'authentication':{'username':'truenas_admin','password':password.read_text()},
        'post_install':{'network_interfaces':[
            {'name':'enp6s18','ipv4_dhcp':False,'ipv6_auto':False,'aliases':[{'type':'INET','address':'172.30.90.10','netmask':24}]},
            {'name':'enp6s19','ipv4_dhcp':False,'ipv6_auto':False,'aliases':[{'type':'INET','address':'172.30.91.10','netmask':24}]}]}})
    print(json.dumps({'installation':call('system_info')}))
else:
    print(json.dumps({'info':info,'disks':disks,'interfaces':interfaces},indent=2))
ws.close()
