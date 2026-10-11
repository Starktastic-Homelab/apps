"""Change only the two synthetic Git-managed writer replica counts."""
import sys,yaml
from lab import PRIVATE
replicas=int(sys.argv[1]);assert replicas in [0,1]
for name in ['service-a','service-b']:
    path=PRIVATE/'repo/manifests'/(name+'.yaml')
    objects=[o for o in yaml.safe_load_all(path.read_text()) if o]
    for obj in objects:
        if obj['kind']=='StatefulSet':obj['spec']['replicas']=replicas
    path.write_text(yaml.safe_dump_all(objects,sort_keys=False))
