#!/usr/bin/env python3
"""Render the selected apps using the ApplicationSet's actual value cascade."""
import argparse
import json
import os
from pathlib import Path
import subprocess

import yaml

ROOT = Path(__file__).resolve().parents[2]


def render(output):
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    defaults = yaml.safe_load((ROOT / 'bootstrap/appsets/cluster-apps.yaml').read_text())['spec']['generators'][0]['matrix']['generators'][0]['list']['elements']
    defaults = {v['category']:v for v in defaults}
    definitions = {}
    for parent in ('services','infrastructure'):
        for path in (ROOT / parent).rglob('app.yaml'):
            app = yaml.safe_load(path.read_text())
            definitions.setdefault(app['name'],[]).append((path.parent,app))
    rows=json.loads((ROOT / 'infrastructure/base-configs/files/ordinary-file-volumes.json').read_text())
    for row in rows:
        name='kube-prometheus-stack' if row['app']=='grafana' else row['app']
        matches=definitions[name]
        if len(matches)!=1:raise ValueError('Ambiguous app definition: '+name)
        directory,app=matches[0]
        category=directory.relative_to(ROOT).parts[0]
        default=defaults[category]
        chart=app.get('chart',{'repo':default['defaultChartRepo'],'name':default['defaultChartName'],'version':default['defaultChartVersion']})
        cache=output/'charts'/(chart['name']+'-'+chart['version'])
        cached=cache/chart['name']
        if not cached.exists():
            cache.mkdir(parents=True,exist_ok=True)
            subprocess.run(['helm','pull',chart['name'],'--repo',chart['repo'],'--version',chart['version'],'--untar','--untardir',str(cache)],check=True)
        if yaml.safe_load((cached/'Chart.yaml').read_text())['version']!=chart['version']:
            raise ValueError('Wrong cached chart version')
        layers=['templates/globals.yaml']
        common=app.get('commonValues',default['commonValues'])
        if common:layers.append(common)
        layers.extend(app.get('commonValuesExtras',[]))
        base=ROOT/app.get('baseApp',str(directory.relative_to(ROOT)))
        layers.append(str((base/'values.yaml').relative_to(ROOT)))
        if app.get('baseApp') and app.get('valuesOverride'):layers.append(str((directory/'values.yaml').relative_to(ROOT)))
        args=['helm','template',name,str(cached),'--namespace',row['namespace'],'--kube-version','1.37.0']
        for layer in layers:args.extend(['-f',str(ROOT/layer)])
        def claim_paths(value,prefix=()):
            if not isinstance(value,dict):return []
            found=[]
            for key,item in value.items():
                path=(*prefix,key)
                if key=='existingClaim' and item==row['claim']:found.append('.'.join(path))
                found.extend(claim_paths(item,path))
            return found
        overrides=set()
        for layer in layers:overrides.update(claim_paths(yaml.safe_load((ROOT/layer).read_text())))
        if len(overrides)!=1:raise ValueError('Ambiguous target claim value path')
        with (output/(row['app']+'.yaml')).open('w') as f:subprocess.run(args,check=True,stdout=f)
        with (output/(row['app']+'-before.yaml')).open('w') as f:
            subprocess.run([*args,'--set-string',next(iter(overrides))+'='+row['sourceClaim']],check=True,stdout=f)


if __name__=='__main__':
    os.umask(0o077)
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    render(parser.parse_args().output)
