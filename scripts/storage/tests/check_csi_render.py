"""Check actual chart output, not value-file key guesses."""
import base64
from pathlib import Path
import sys
import yaml
objects=[o for o in yaml.safe_load_all(Path(sys.argv[1]).read_text()) if o]
assert not any(o['kind'] in ('StorageClass','Deployment','StatefulSet') for o in objects)
driver=next(o for o in objects if o['kind']=='CSIDriver')
assert driver['metadata']['name']=='org.democratic-csi.retained'
assert driver['spec']['attachRequired'] is False
pods=[o for o in objects if o['kind']=='DaemonSet'];assert len(pods)==1
spec=pods[0]['spec']['template']['spec']
assert spec['nodeSelector']['storage.starktastic.net/iscsi-ready']=='true'
assert spec['nodeSelector']['node-role.kubernetes.io/worker']=='true'
assert all('@sha256:' in c['image'] for c in spec['containers'])
secret=next(o for o in objects if o['kind']=='Secret')
configs=[yaml.safe_load(base64.b64decode(v)) for v in secret.get('data',{}).values()]
configs += [yaml.safe_load(v) for v in secret.get('stringData',{}).values()]
config=next(c for c in configs if isinstance(c,dict) and 'driver' in c)
assert config['driver']=='node-manual'
assert config['node']['format']['ext4']['customOptions']==['-n']
assert config['node']['mount']['checkFilesystem']['ext4']['enabled'] is False
assert 'httpConnection' not in config
print('CSI rendered schema/placement/image/format checks passed')
