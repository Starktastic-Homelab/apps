import json,pathlib,sys,subprocess,time
base=pathlib.Path('/var/lib/vz/iscsi-lab-20260921-6c168a2e');sys.path.insert(0,str(base));from guard import owns_vm,vm_config
m=json.loads((base/'manifest.json').read_text());assert owns_vm(913,vm_config(913),m)
subprocess.run(['qm','stop','913'],check=True,timeout=30)
assert owns_vm(913,vm_config(913),m)
assert 'stopped' in subprocess.check_output(['qm','status','913'],text=True)
print(json.dumps({'vmid':913,'uuid':m['vms']['913']['uuid'],'power_off_confirmed':True,'at':time.time()}))
