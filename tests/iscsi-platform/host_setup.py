"""Prepare only the fixture's two private bridges and scoped firewall table."""
import ipaddress
import json
import pathlib
import re
import subprocess
import sys
import time

manifest_path = pathlib.Path(sys.argv[1])
manifest = json.loads(manifest_path.read_text())
marker = manifest['marker']
assert re.fullmatch(r'iscsi-lab-\d{8}-[a-f0-9]{8}', marker)
assert manifest['bridges'] == {'control': 'ilabctl0', 'storage': 'ilabstor0'}
status = json.loads(manifest_path.with_name('guard-status.json').read_text())
assert status['production_ok'] is True and status['stop_reason'] is None
assert time.time()-status['at'] < 20 and status['available'] >= 20*1024**3
subprocess.run(['systemctl', 'is-active', '--quiet', marker+'-guard'], check=True)
networks = [('ilabctl0', '172.30.90.1/24'), ('ilabstor0', '172.30.91.1/24')]
existing = json.loads(subprocess.check_output(['ip', '-j', 'route'], text=True))
for bridge, address in networks:
    assert not pathlib.Path('/sys/class/net', bridge).exists(), 'Bridge already exists'
    network = ipaddress.ip_interface(address).network
    assert not any(network.overlaps(ipaddress.ip_network(r['dst'], strict=False))
                   for r in existing if r.get('dst') not in (None, 'default'))
table = marker.replace('-', '_')
rules = f'''table inet {table} {{
 chain input {{ type filter hook input priority -50; policy accept;
  iifname {{ "ilabctl0", "ilabstor0" }} ct state established,related accept
  iifname {{ "ilabctl0", "ilabstor0" }} counter drop
 }}
 chain forward {{ type filter hook forward priority -50; policy accept;
  iifname {{ "ilabctl0", "ilabstor0" }} counter drop
  oifname {{ "ilabctl0", "ilabstor0" }} counter drop
 }}
}}
'''
subprocess.run(['nft', '--check', '-f', '-'], input=rules, text=True, check=True)
subprocess.run(['nft', '-f', '-'], input=rules, text=True, check=True)
for bridge, address in networks:
    subprocess.run(['ip', 'link', 'add', bridge, 'type', 'bridge'], check=True)
    subprocess.run(['ip', 'link', 'set', 'dev', bridge, 'alias', marker], check=True)
    subprocess.run(['sysctl', '-q', '-w', f'net.ipv6.conf.{bridge}.disable_ipv6=1'], check=True)
    subprocess.run(['ip', 'addr', 'add', address, 'dev', bridge], check=True)
    subprocess.run(['ip', 'link', 'set', bridge, 'up'], check=True)
manifest_path.with_name('network.nft').write_text(rules)
print(json.dumps({'private_bridges': networks, 'nft_table': table, 'production_network_modified': False}))
