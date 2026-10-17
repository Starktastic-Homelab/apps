#!/usr/bin/env python3
"""An absent identity or native store must never bootstrap a new application."""
import hashlib
import copy
import base64
import importlib.util
import json
import yaml
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
LAYOUTS = {
    'karakeep': ('db.db', 'queue.db'),
    'karakeep-meilisearch': ('.version_marker', 'data.ms/VERSION'),
    'bytestash': ('snippets.db',),
    'convertx': ('mydb.sqlite',),
    'home-assistant': ('home-assistant_v2.db', '.storage/core.uuid', '.storage/core.config_entries', 'configuration.yaml'),
    'home-assistant-matter': ('config/driver.json', 'certificates/driver.json'),
}

class RetainedState(unittest.TestCase):
    def check(self, app, alteration=None, accepted=False):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'retained'; root.mkdir()
            marker = root / ('.homelab-' + app + '-data')
            marker.write_text('homelab/' + app + '/data/v1\n')
            for name in LAYOUTS[app]:
                p = root / name; p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(b'SQLite format 3\0' + b'x' * 100 if p.suffix in ('.db', '.sqlite') else b'preserved identity')
            if app == 'karakeep-meilisearch':
                (root / '.version_marker').write_text('meilisearch 1.55.0\n')
                (root / 'data.ms/VERSION').write_text('1.55.0')
            if alteration: alteration(root, marker)
            def snapshot():
                return {str(p.relative_to(root)): (p.lstat().st_mode, hashlib.sha256(p.read_bytes()).hexdigest())
                        for p in root.rglob('*') if p.is_file() and not p.is_symlink()}
            before = snapshot()
            result = subprocess.run([sys.executable, '-I', '-B', str(ROOT / 'scripts/operations-home-retained/guard.py'), app, str(root)], capture_output=True, timeout=3)
            self.assertEqual(result.returncode == 0, accepted, result.stderr.decode())
            self.assertEqual(snapshot(), before)

    def test_complete_stores_are_read_only(self):
        for app in LAYOUTS:
            with self.subTest(app=app): self.check(app, accepted=True)

    def test_every_required_file_is_required(self):
        for app, names in LAYOUTS.items():
            for name in names:
                with self.subTest(app=app, path=name): self.check(app, lambda r,m: (r/name).unlink())

    def test_empty_wrong_oversized_and_linked_markers_refuse(self):
        for app in LAYOUTS:
            for value in ('', 'homelab/wrong/data/v1\n', 'x'*129): self.check(app, lambda r,m: m.write_text(value))
            self.check(app, lambda r,m: m.unlink())
            def link(r,m):
                other=r.parent/'marker'; other.write_bytes(m.read_bytes());m.unlink();m.symlink_to(other)
            self.check(app, link)

    def test_no_follow_for_native_files_or_parents(self):
        def link(r,m):
            p=r/'config';other=r.parent/'config';p.rename(other);p.symlink_to(other,target_is_directory=True)
        self.check('home-assistant-matter',link)
        def native(r,m):
            p=r/'db.db';other=r.parent/'db';p.rename(other);p.symlink_to(other)
        self.check('karakeep',native)

    def test_bad_sqlite_header_and_fifo_refuse(self):
        self.check('bytestash',lambda r,m:(r/'snippets.db').write_bytes(b'not a database'))
        def fifo(r,m):
            p=r/'mydb.sqlite';p.unlink();os.mkfifo(p)
        self.check('convertx',fifo)

    def test_search_version_mismatch_never_reindexes(self):
        for name in LAYOUTS['karakeep-meilisearch']:
            for value in ('', '1.56.0', 'meilisearch 1.56.0\n'):
                self.check('karakeep-meilisearch',lambda r,m:(r/name).write_text(value))

class ManifestContracts(unittest.TestCase):
    def test_search_engine_updates_require_retained_format_review(self):
        rules=json.loads((ROOT/'renovate.json').read_text())['packageRules']
        self.assertTrue(any(r.get('automerge') is False and 'getmeili/meilisearch' in r.get('matchPackageNames',[]) and 'services/operations/karakeep/values.yaml' in r.get('matchFileNames',[]) for r in rules))

    def test_embedded_guards_are_exact_and_prior_guard_is_unchanged(self):
        for ns in ('operations', 'home-automation'):
            cm = yaml.safe_load((ROOT/'scripts/operations-home-retained/production'/('guard-'+ns+'.yaml')).read_text())
            self.assertEqual(cm['metadata']['namespace'], ns)
            for name in ('guard.py','base.py'):
                self.assertEqual(cm['data'][name], (ROOT/'scripts/operations-home-retained'/name).read_text())
        self.assertEqual((ROOT/'scripts/operations-home-retained/base.py').read_bytes(),(ROOT/'scripts/media-retained/guard.py').read_bytes())

    @unittest.skipUnless(os.environ.get('OPERATIONS_HOME_RENDERS'), 'Actual Helm render directory not supplied')
    def test_actual_render_preserves_stock_contracts_and_all_guards(self):
        rendered=Path(os.environ['OPERATIONS_HOME_RENDERS'])
        profiles={'karakeep':{'data':('main',0,0),'meilisearch':('meilisearch',0,0)},'bytestash':{'data':('main',0,0)},'convertx':{'convertx-data':('main',0,0)},'home-assistant':{'home-assistant-config':('main',0,0),'matter-server-data':('matter-server',1000,1000)}}
        total=0
        for app,stores in profiles.items():
            with self.subTest(app=app):
                before=next(v for v in yaml.safe_load_all((rendered/(app+'-before.yaml')).read_text()) if v and v['kind']=='Deployment')
                after=next(v for v in yaml.safe_load_all((rendered/(app+'.yaml')).read_text()) if v and v['kind']=='Deployment')
                b=before['spec']['template']['spec'];a=after['spec']['template']['spec']
                self.assertEqual(after['spec']['replicas'],1);self.assertEqual(after['spec']['strategy']['type'],'Recreate')
                self.assertFalse(a['automountServiceAccountToken']);self.assertEqual(a['nodeSelector']['node-role.kubernetes.io/worker'],'true')
                self.assertEqual(a.get('hostNetwork'),b.get('hostNetwork'));self.assertEqual(a.get('dnsPolicy'),b.get('dnsPolicy'))
                self.assertNotIn('fsGroup',a.get('securityContext',{}),'CSI must not recursively rewrite preserved file ownership')
                prior=b.get('securityContext',{})
                groups=prior.get('supplementalGroups',[]) + ([prior['fsGroup']] if 'fsGroup' in prior else [])
                self.assertTrue(set(groups)<=set(a.get('securityContext',{}).get('supplementalGroups',[])))
                for old,new in zip(b['containers'],a['containers']):
                    self.assertEqual(old['name'],new['name'])
                    for key in ('image','env','envFrom','resources','livenessProbe','readinessProbe','startupProbe','securityContext'):
                        self.assertEqual(old.get(key),new.get(key),(app,new['name'],key))
                    if app!='karakeep' or not new['name'].endswith('meilisearch'):
                        self.assertEqual(old.get('command'),new.get('command'));self.assertEqual(old.get('args'),new.get('args'))
                    else:
                        self.assertNotIn('find ',str(new.get('args')));self.assertIn('exec meilisearch',str(new.get('args')))
                        self.assertEqual(new['image'].split('@',1)[0].rsplit(':',1)[1],'v1.55.0','Qualify retained search-format migration before changing this pin')
                claims={v['name']:v['persistentVolumeClaim']['claimName'] for v in a['volumes'] if 'persistentVolumeClaim' in v}
                self.assertEqual(len(claims),len(stores));self.assertTrue(all(c.endswith('-block') for c in claims.values()))
                for key,(container,uid,gid) in stores.items():
                    init=next(x for x in a['initContainers'] if x['name']=='retained-'+key)
                    self.assertEqual(init['securityContext']['runAsUser'],uid);self.assertEqual(init['securityContext']['runAsGroup'],gid)
                    self.assertEqual([v['mountPath'] for v in init['volumeMounts']],['/retained','/retained-startup'])
                    self.assertTrue(all(v['readOnly'] for v in init['volumeMounts']))
                docs=list(yaml.safe_load_all((ROOT/'scripts/operations-home-retained/production'/(app+'-bindings.yaml')).read_text()))
                for pv in (v for v in docs if v['kind']=='PersistentVolume'):
                    self.assertEqual(pv['spec']['accessModes'],['ReadWriteOncePod']);self.assertEqual(pv['spec']['persistentVolumeReclaimPolicy'],'Retain');self.assertEqual(pv['spec']['csi']['fsType'],'ext4')
                    total+=int(pv['spec']['capacity']['storage'][:-2])
        self.assertEqual(total,20)

class SQLManifestContracts(unittest.TestCase):
    def test_yaml_formatting_preserves_native_completion_code_and_generation(self):
        root=ROOT/'scripts/operations-home-retained/production'
        module=ROOT/'scripts/postgres-enrollment/completion_gate.py'
        spec=importlib.util.spec_from_file_location('completion_protocol',module);protocol=importlib.util.module_from_spec(spec);spec.loader.exec_module(protocol)
        for app in ('excalidash','crowdsec'):
            docs=list(yaml.safe_load_all((root/(app+'-postgresql/consumer-gate.yaml')).read_text()))
            cm=next(v for v in docs if v['kind']=='ConfigMap')
            with self.subTest(app=app):self.assertEqual(cm['data']['completion_gate.py'],module.read_text())
        cm=yaml.safe_load((root/'postgres-enrollment/enrollment-configmap.yaml').read_text())
        self.assertEqual(cm['data']['acceptance-generation'],protocol.generation(cm['data']))

    def test_identity_hook_precedes_unmodified_native_registration(self):
        root=ROOT/'scripts/operations-home-retained/production/crowdsec-postgresql'
        docs=list(yaml.safe_load_all((root/'identity-gate.yaml').read_text()))
        job=next(v for v in docs if v['kind']=='Job')
        self.assertEqual(job['metadata']['annotations']['argocd.argoproj.io/sync-wave'],'-4')
        self.assertEqual(job['spec']['template']['spec']['containers'][0]['command'][-1],(ROOT/'scripts/operations-home-retained/identity_gate.py').read_text())
        role=next(v for v in docs if v['kind']=='Role')
        self.assertTrue(all(r['verbs']==['get'] and set(r['resourceNames'])=={'crowdsec-capi-credentials','crowdsec-lapi-secrets'} for r in role['rules']))
        for name in ('crowdsec-capi-credentials','crowdsec-lapi-secrets'):
            sealed=yaml.safe_load((root/(name+'.yaml')).read_text())
            self.assertEqual(sealed['metadata']['annotations']['argocd.argoproj.io/sync-wave'],'-5')
            self.assertEqual(sealed['spec']['template']['metadata']['annotations']['sealedsecrets.bitnami.com/skip-set-owner-references'],'true')
            self.assertNotIn('data',sealed['spec']['template'])
        self.assertEqual(set(yaml.safe_load((root/'crowdsec-capi-credentials.yaml').read_text())['spec']['encryptedData']),{'online_api_credentials.yaml'})

    @unittest.skipUnless(os.environ.get('OPERATIONS_HOME_RENDERS'), 'Actual Helm render directory not supplied')
    def test_both_sql_apps_have_no_pvc_and_wait_for_enrollment_and_native_state(self):
        rendered=Path(os.environ['OPERATIONS_HOME_RENDERS'])
        for app in ('excalidash','crowdsec'):
            after=[v for v in yaml.safe_load_all((rendered/(app+'.yaml')).read_text()) if v]
            self.assertFalse(any(v['kind']=='PersistentVolumeClaim' for v in after))
            deployment=next(v for v in after if v['kind']=='Deployment' and (app!='crowdsec' or v['metadata']['name']=='crowdsec-lapi'))
            spec=deployment['spec']['template']['spec']
            self.assertFalse(any('persistentVolumeClaim' in v for v in spec.get('volumes',[])))
            self.assertEqual([v['name'] for v in spec['initContainers']],['postgres-enrollment-acceptance','retained-database'])
            self.assertIn('/retained-database/main.sql',spec['initContainers'][-1]['command'][-1])
            main=next(v for v in spec['containers'] if v['name']==('backend' if app=='excalidash' else 'crowdsec-lapi'))
            env={v['name']:v for v in main['env']}
            if app=='excalidash':
                self.assertEqual(env['DATABASE_PROVIDER']['value'],'postgresql')
                for key in ('DATABASE_URL','JWT_SECRET','CSRF_SECRET'):self.assertIn('secretKeyRef',env[key]['valueFrom'])
            else:
                self.assertEqual(env['CROWDSEC_BYPASS_DB_VOLUME_CHECK']['value'],'true')
                self.assertEqual(env['CS_LAPI_SECRET']['valueFrom']['secretKeyRef']['name'],'crowdsec-lapi-secrets')
                self.assertIn('CROWDSEC_POSTGRES_PASSWORD',env)
            before=[v for v in yaml.safe_load_all((rendered/(app+'-before.yaml')).read_text()) if v]
            old=next(v for v in before if v['kind']=='Deployment' and v['metadata']['name']==deployment['metadata']['name'])
            for a,b in zip(old['spec']['template']['spec']['containers'],spec['containers']):
                for key in ('image','resources','livenessProbe','readinessProbe','startupProbe','securityContext'):
                    old,new=a.get(key),b.get(key)
                    if key=='image' and app=='crowdsec' and old!=new:
                        self.assertEqual(new,old+'@sha256:0f2523fa61ef507f15d953045cface490cc880670c62f2755ced17524107f71a')
                    else:self.assertEqual(old,new,(app,a['name'],key))

class IdentityGate(unittest.TestCase):
    def test_only_current_unsealed_generation_without_gc_ownership_passes(self):
        p=ROOT/'scripts/operations-home-retained/identity_gate.py'
        self.assertTrue(p.exists(), 'Native credential gate is not implemented')
        spec=importlib.util.spec_from_file_location('identity_gate',p);gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
        sealed={'metadata':{'name':'crowdsec-capi-credentials','namespace':'crowdsec','generation':2},'status':{'observedGeneration':2,'conditions':[{'type':'Synced','status':'True'}]}}
        secret={'metadata':{'name':'crowdsec-capi-credentials','namespace':'crowdsec'},'type':'Opaque','data':{'online_api_credentials.yaml':base64.b64encode(b'login: synthetic\npassword: synthetic\n').decode()}}
        self.assertTrue(gate.accepted(sealed,secret,'crowdsec-capi-credentials',{'online_api_credentials.yaml'}))
        for which,alter in [('sealed',lambda s:s['status'].update(observedGeneration=1)),('sealed',lambda s:s['status']['conditions'][0].update(status='False')),('secret',lambda s:s['metadata'].update(ownerReferences=[{'uid':'old-hook'}])),('secret',lambda s:s['metadata'].update(namespace='other')),('secret',lambda s:s['data'].update(extra='eA==')),('secret',lambda s:s['data'].update({'online_api_credentials.yaml':''})),('secret',lambda s:s['data'].update({'online_api_credentials.yaml':'invalid'}))]:
            a,b=copy.deepcopy(sealed),copy.deepcopy(secret);alter(a if which=='sealed' else b)
            self.assertFalse(gate.accepted(a,b,'crowdsec-capi-credentials',{'online_api_credentials.yaml'}))

if __name__ == '__main__': unittest.main()
