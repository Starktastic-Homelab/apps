import json,pathlib,sys,subprocess,time
base=pathlib.Path('/var/lib/vz/iscsi-lab-20260921-6c168a2e');sys.path.insert(0,str(base));from guard import owns_vm,vm_config
m=json.loads((base/'manifest.json').read_text());c=vm_config(913);assert owns_vm(913,c,m)
assert 'bridge=ilabctl0' in c['net0'] and 'bridge=ilabstor0' in c['net1'] and 'link_down' not in c['net0']
(base/'partition-net0-before').write_text(c['net0'])
subprocess.run(['qm','set','913','--net0',c['net0']+',link_down=1'],check=True)
print(json.dumps({'vmid':913,'control_disconnected':True,'storage_nic_unchanged':vm_config(913)['net1']==c['net1'],'at':time.time()}))
