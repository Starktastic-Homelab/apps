import pathlib,json,sys,ssl,urllib.request,urllib.error,subprocess,time
base=pathlib.Path('/var/lib/vz/iscsi-lab-20260921-6c168a2e');sys.path.insert(0,str(base))
from guard import owns_vm,vm_config
m=json.loads((base/'manifest.json').read_text());vmid=913;c=vm_config(vmid);assert owns_vm(vmid,c,m)
bad=json.loads(json.dumps(m));bad['vms'][str(vmid)]['uuid']='00000000-0000-0000-0000-000000000000'
assert not owns_vm(vmid,c,bad)
assert 'running' in subprocess.check_output(['qm','status',str(vmid)],text=True)
context=ssl.create_default_context(cafile='/etc/pve/pve-root-ca.pem');context.check_hostname=False;context.verify_flags &= ~ssl.VERIFY_X509_STRICT
request=urllib.request.Request(f'https://127.0.0.1:8006/api2/json/nodes/pve/qemu/{vmid}/status/stop',data=b'',method='POST')
try:
 urllib.request.urlopen(request,context=context,timeout=10)
 raise RuntimeError('Unauthenticated fence unexpectedly accepted')
except urllib.error.HTTPError as error:
 assert error.code==401,error.code
assert owns_vm(vmid,vm_config(vmid),m)
assert 'running' in subprocess.check_output(['qm','status',str(vmid)],text=True)
print(json.dumps({'vmid':vmid,'stale_uuid_rejected':True,'unauthenticated_stop_http_status':401,'still_running':True,'at':time.time()}))
