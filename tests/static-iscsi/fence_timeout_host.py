"""A timed-out, unauthenticated stop request must never count as a fence."""
import pathlib,json,sys,subprocess,ssl,urllib.request,urllib.error,time
base=pathlib.Path('/var/lib/vz/iscsi-lab-20260921-6c168a2e');sys.path.insert(0,str(base));from guard import owns_vm,vm_config
m=json.loads((base/'manifest.json').read_text());assert owns_vm(913,vm_config(913),m)
assert 'running' in subprocess.check_output(['qm','status','913'],text=True)
context=ssl.create_default_context(cafile='/etc/pve/pve-root-ca.pem');context.check_hostname=False;context.verify_flags &= ~ssl.VERIFY_X509_STRICT
request=urllib.request.Request('https://127.0.0.1:8006/api2/json/nodes/pve/qemu/913/status/stop',data=b'',method='POST')
try:
 urllib.request.urlopen(request,context=context,timeout=0.000000001)
except (TimeoutError,urllib.error.URLError) as error:
 reason=error.reason if isinstance(error,urllib.error.URLError) else error
 assert isinstance(reason,TimeoutError),type(reason).__name__
else:raise RuntimeError('Timeout injection did not occur')
assert owns_vm(913,vm_config(913),m) and 'running' in subprocess.check_output(['qm','status','913'],text=True)
print(json.dumps({'stop_request_timed_out':True,'vmid':913,'uuid':m['vms']['913']['uuid'],'power_off_confirmed':False,'still_running':True,'at':time.time()}))
