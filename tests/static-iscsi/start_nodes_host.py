import pathlib,json,subprocess,sys,time
base=pathlib.Path('/var/lib/vz/iscsi-lab-20260921-6c168a2e');sys.path.insert(0,str(base))
from guard import owns_vm,vm_config,host_sample
m=json.loads((base/'manifest.json').read_text())
for vmid in (911,912,913):
 v=m['vms'][str(vmid)];cfg=vm_config(vmid)
 assert owns_vm(vmid,cfg,m) and cfg['onboot']=='0' and int(cfg['memory'])==v['memory']
 assert 'bridge=ilabctl0' in cfg['net0'] and 'bridge=ilabstor0' in cfg['net1'] and 'net2' not in cfg
 assert not any(k.startswith('hostpci') for k in cfg)
 assert cfg['virtio0'].startswith(f'vm-pool:vm-{vmid}-') and 'size=6G' in cfg['virtio0']
 s=json.loads((base/'guard-status.json').read_text());assert s['production_ok'] is True and s['stop_reason'] is None and time.time()-s['at']<20
 vms=json.loads(subprocess.check_output(['pvesh','get','/nodes/pve/qemu','--output-format','json'],text=True))
 resident=sum(x.get('mem',0) for x in vms if x['vmid'] in (910,911,912,913))
 assert host_sample()[0] >= 20*1024**3-resident
 subprocess.run(['systemctl','is-active','--quiet',m['marker']+'-guard'],check=True)
 subprocess.run(['qm','start',str(vmid)],check=True)
 print(json.dumps({'vmid':vmid,'started':True,'host_available_gib':round(host_sample()[0]/1024**3,2)}),flush=True)
