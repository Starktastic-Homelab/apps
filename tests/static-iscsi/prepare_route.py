from pathlib import Path
import sys
sys.path.insert(0,str(__import__('pathlib').Path(__file__).resolve().parent))
from ssh import ssh
unit='''[Unit]
Description=Isolated lab dummy route required by air-gapped K3s
Before=k3s.service k3s-agent.service
After=network.target
[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/sh -c 'ip link show labdummy0 >/dev/null 2>&1 || ip link add labdummy0 type dummy; ip link set labdummy0 up; ip addr replace 203.0.113.254/31 dev labdummy0; ip route replace default via 203.0.113.255 dev labdummy0 metric 1000'
[Install]
WantedBy=multi-user.target
'''
for port in (19111,19112,19113):
 ssh(port,'sudo install -m 644 /dev/stdin /etc/systemd/system/lab-airgap-route.service',input=unit.encode())
 ssh(port,'sudo systemctl daemon-reload && sudo systemctl enable --now lab-airgap-route.service',capture_output=True)
print('Isolated dummy route persists across lab guest reboots; no real gateway added.')
