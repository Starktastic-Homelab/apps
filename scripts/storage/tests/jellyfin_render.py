"""Actual layered app-template render checks; fixtures never become Git bindings."""
import argparse
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import yaml
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from jellyfin_stages import stage_values
from test_render_storage import RECORD,NODE

parser=argparse.ArgumentParser();parser.add_argument('--chart',required=True);args=parser.parse_args()
root=Path(__file__).resolve().parents[3]
original=yaml.safe_load((root/'services/media/jellyfin/values.yaml').read_text())
def render(values):
    with tempfile.NamedTemporaryFile(mode='w',suffix='.yaml') as f:
        yaml.safe_dump(values,f);f.flush()
        result=subprocess.check_output(['helm','template','jellyfin',args.chart,'--namespace','media',
            '-f',str(root/'templates/globals.yaml'),'-f',str(root/'templates/common.yaml'),'-f',f.name],text=True)
    deployment=next(o for o in yaml.safe_load_all(result) if o and o['kind']=='Deployment')
    return deployment
baseline=render(original)
for stage in ('source-held','target-held','target-released'):
    deployment=render(stage_values(original,stage,RECORD,NODE))
    assert deployment['spec']['replicas']==int(stage=='target-released')
    pod=deployment['spec']['template'];main=next(c for c in pod['spec']['containers'] if c['name']=='main')
    base=next(c for c in baseline['spec']['template']['spec']['containers'] if c['name']=='main')
    for key in ('image','livenessProbe','readinessProbe','startupProbe'):
        assert main[key]==base[key],key
    assert main['resources']['limits']['gpu.intel.com/i915']==base['resources']['limits']['gpu.intel.com/i915']
    volumes={v['name']:v for v in pod['spec']['volumes']}
    assert volumes['media']==next(v for v in baseline['spec']['template']['spec']['volumes'] if v['name']=='media')
    if stage!='source-held':
        assert deployment['spec']['strategy']=={'type':'Recreate'}
        assert volumes['jellyfin-config']['persistentVolumeClaim']['claimName']==RECORD['pvc']
        assert 'jellyfin-cache' not in volumes
        assert volumes['disposable']['emptyDir']=={'sizeLimit':'10Gi'}
        for kind in ('requests','limits'):assert main['resources'][kind]['ephemeral-storage']=='12Gi'
        mounts=[m for m in main['volumeMounts'] if m['name']=='disposable']
        assert {(m['mountPath'],m['subPath']) for m in mounts}=={('/config/cache','cache'),('/config/data/transcodes','transcodes')}
        init=pod['spec']['initContainers'][0]
        assert init['name']=='disposable-dirs' and init['image']==main['image']
        assert {'name':'disposable','mountPath':'/disposable'} in init['volumeMounts']
        assert 'chown 1000:1000' in init['command'][-1]
        assert pod['metadata']['labels']['storage.starktastic.net/writer']=='jellyfin'
        terms=pod['spec']['affinity']['nodeAffinity']['requiredDuringSchedulingIgnoredDuringExecution']['nodeSelectorTerms']
        assert len(terms)==1 and len(terms[0]['matchExpressions'])==3
        assert pod['spec']['nodeSelector']['storage.starktastic.net/iscsi-ready']=='true'
    print('PASS layered '+stage)
