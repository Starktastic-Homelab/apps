import sys,pathlib,secrets,json,importlib.util
spec=importlib.util.spec_from_file_location('labssh',str(pathlib.Path(__file__).with_name('ssh.py')));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
p=m.p
if not (p/'k3s-token').exists():
 (p/'k3s-token').write_text(secrets.token_hex(32));(p/'k3s-token').chmod(0o600)
for port in map(int,sys.argv[1:]):
 address='172.30.90.'+str(port-19100)
 config={'token-file':'/etc/rancher/k3s/token','node-ip':address,'flannel-iface':'eth0','kubelet-arg':['eviction-hard=memory.available<80Mi,nodefs.available<5%,imagefs.available<5%']}
 if port==19111:config.update({'cluster-init':True,'cluster-cidr':'10.62.0.0/16','service-cidr':'10.63.0.0/16','disable':['traefik','servicelb','local-storage'],'tls-san':['127.0.0.1'],'node-taint':['node-role.kubernetes.io/control-plane=true:NoSchedule']})
 else:config['server']='https://172.30.90.11:6443'
 m.ssh(port,'sudo install -m 600 /dev/stdin /etc/rancher/k3s/token',input=(p/'k3s-token').read_bytes())
 m.ssh(port,'sudo install -m 600 /dev/stdin /etc/rancher/k3s/config.yaml',input=json.dumps(config).encode())
 m.ssh(port,'sudo install -m 700 /dev/stdin /root/install-k3s.sh',input=pathlib.Path('/tmp/static-iscsi-inputs/install-k3s.sh').read_bytes())
 # Dummy default is required by K3s but cannot forward packets to a real network.
 m.ssh(port,'sudo ip link add labdummy0 type dummy && sudo ip link set labdummy0 up && sudo ip addr add 203.0.113.254/31 dev labdummy0 && sudo ip route add default via 203.0.113.255 dev labdummy0 metric 1000')
 m.ssh(port,'sudo cp /mnt/iscsi-seed/*.tar /var/lib/rancher/k3s/agent/images/ && sudo env INSTALL_K3S_SKIP_DOWNLOAD=true INSTALL_K3S_EXEC='+('server' if port==19111 else 'agent')+' sh /root/install-k3s.sh')
 print('Configured owned lab node',port,flush=True)
