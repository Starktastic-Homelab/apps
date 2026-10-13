#!/usr/bin/env python3
"""Qualify inactive Seerr retained startup and instance composition."""
import copy
import hashlib
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import uuid

import yaml

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'scripts/seerr-postgresql'
TABLES = ('blocklist', 'discover_slider', 'issue', 'issue_comment', 'media', 'media_request',
          'override_rule', 'season', 'season_request', 'session', 'user',
          'user_push_subscription', 'user_settings', 'watchlist')


class RetainedConfigTests(unittest.TestCase):
    def check(self, alter=None, env_change=None, accepted=False, instance='seerr'):
        self.assertTrue((PACKAGE / 'guard.py').is_file(), 'Retained Seerr guard not implemented')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'config'; root.mkdir()
            (root / '.homelab-seerr-config').write_text(f'homelab/{instance}/config/v1\n')
            settings = {'main': {'apiKey': 'fixture-api-secret'}, 'sessionSecret': 'fixture-session-secret',
                        'clientId': 'fixture-client', 'vapidPublic': 'fixture-public', 'vapidPrivate': 'fixture-private'}
            (root / 'settings.json').write_text(json.dumps(settings))
            env = dict(os.environ, NODE_ENV='production', DB_TYPE='postgres', DB_HOST='postgres-postgresql.databases',
                       DB_PORT='5432', DB_NAME=instance.replace('-', '_'), DB_USER=instance.replace('-', '_'),
                       DB_POOL_SIZE='3', DB_PASS='fixture-db-secret')
            for key in ('DB_SOCKET_PATH', 'CONFIG_DIRECTORY', 'API_KEY'):
                env.pop(key, None)
            if env_change:env_change(env)
            if alter:alter(root)
            def snapshot():
                return {str(p.relative_to(root.parent)): hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in root.parent.rglob('*') if p.is_file()}
            before = snapshot()
            result = subprocess.run([sys.executable, '-I', '-B', str(PACKAGE / 'guard.py'), str(root), instance],
                                    env=env, capture_output=True, timeout=10)
            self.assertEqual(result.returncode == 0, accepted, result.stderr.decode())
            self.assertEqual(before, snapshot(), 'Guard wrote retained state')
            for secret in ('fixture-api-secret', 'fixture-session-secret', 'fixture-db-secret', 'fixture-private'):
                self.assertNotIn(secret.encode(), result.stdout + result.stderr)

    def test_preserved_instances_are_accepted_without_writes(self):
        for instance in ('seerr', 'seerr-ru'):self.check(accepted=True, instance=instance)

    def test_missing_wrong_or_oversized_marker_is_rejected(self):
        self.check(lambda p: (p / '.homelab-seerr-config').unlink())
        for value in ('homelab/seerr-ru/config/v1\n', 'x' * 131073):
            self.check(lambda p: (p / '.homelab-seerr-config').write_text(value))

    def test_invalid_missing_or_duplicate_settings_are_rejected(self):
        self.check(lambda p: (p / 'settings.json').unlink())
        for value in ('{', '[]', 'null', '{"main":{"apiKey":"x","apiKey":"y"}}', 'x' * 131073):
            self.check(lambda p: (p / 'settings.json').write_text(value))

    def test_missing_or_invalid_preserved_identifiers_are_rejected(self):
        for key in ('apiKey', 'sessionSecret', 'clientId', 'vapidPublic', 'vapidPrivate'):
            for value in (None, '', ' ', 1, [], {}):
                def alter(p):
                    settings = json.loads((p / 'settings.json').read_text())
                    (settings['main'] if key == 'apiKey' else settings)[key] = value
                    (p / 'settings.json').write_text(json.dumps(settings))
                self.check(alter)
        self.check(lambda p: (p / 'settings.json').write_text('{"main":null}'))

    def test_symlinked_retained_paths_are_rejected(self):
        for name in ('.homelab-seerr-config', 'settings.json'):
            def alter(p):
                (p / name).rename(p / (name + '.real')); (p / name).symlink_to(name + '.real')
            self.check(alter)
        self.check(lambda p: (p / 'db').symlink_to('missing', target_is_directory=True))
        def root_link(p):
            p.rename(p.parent / 'real'); p.symlink_to('real', target_is_directory=True)
        self.check(root_link)

    def test_sqlite_main_and_sidecars_including_dangling_links_are_rejected(self):
        for suffix in ('', '-wal', '-shm', '-journal'):
            for linked in (False, True):
                def alter(p):
                    (p / 'db').mkdir(); target = p / 'db' / ('db.sqlite3' + suffix)
                    target.symlink_to('missing') if linked else target.write_bytes(b'fixture')
                self.check(alter)
        self.check(lambda p: (p / 'db').mkdir(), accepted=True)

    def test_wrong_database_or_environment_is_rejected(self):
        for key in ('NODE_ENV', 'DB_TYPE', 'DB_HOST', 'DB_PORT', 'DB_NAME', 'DB_USER', 'DB_POOL_SIZE'):
            self.check(env_change=lambda e: e.pop(key))
            self.check(env_change=lambda e: e.update({key: 'wrong'}))
        for key,value in (('DB_SOCKET_PATH','/tmp/socket'),('CONFIG_DIRECTORY','/other'),('API_KEY','replacement')):
            self.check(env_change=lambda e: e.update({key:value}))
        self.check(env_change=lambda e: e.pop('DB_PASS'))
        for value in ('', ' ' * 4, 'x' * 4097, 'x\n'):
            self.check(env_change=lambda e: e.update(DB_PASS=value))
        self.check(env_change=lambda e: e.update(CONFIG_DIRECTORY='/app/config', API_KEY='fixture-api-secret'), accepted=True)


@unittest.skipUnless(os.environ.get('SEERR_SQL_TEST'), 'Enable disposable local SQL qualification')
class NativeDatabaseTests(unittest.TestCase):
    def test_empty_wrong_and_incomplete_state_is_rejected_then_canonical_data_passes(self):
        self.assertTrue((PACKAGE / 'main.sql').is_file(), 'Retained SQL not implemented')
        name = 'seerr-retained-check-' + uuid.uuid4().hex[:12]
        def command(args, data=None, check=True):
            r = subprocess.run(args, input=data, text=True, capture_output=True, timeout=60)
            if check and r.returncode:raise AssertionError('Synthetic SQL fixture failed; details suppressed')
            return r
        image = yaml.safe_load((ROOT / 'scripts/postgres-enrollment/job.yaml').read_text())['spec']['template']['spec']['containers'][0]['image']
        command(['docker','run','-d','--name',name,'--network','none','--memory','256m','--cpus','1','--pids-limit','128',
                 '--tmpfs','/var/lib/postgresql:rw,size=128m','-e','PGDATA=/var/lib/postgresql/data',
                 '-e','POSTGRES_PASSWORD=fixture-admin','-e','POSTGRES_INITDB_ARGS=--auth-host=scram-sha-256 --auth-local=trust', image])
        self.addCleanup(lambda: command(['docker','rm','-f',name]))
        for _ in range(100):
            if command(['docker','exec',name,'pg_isready','-h127.0.0.1','-Upostgres'],check=False).returncode==0:break
            time.sleep(.2)
        else:self.fail('Synthetic SQL readiness deadline')
        def sql(q,db='postgres'):
            return command(['docker','exec','-i',name,'psql','-XqAt','-vON_ERROR_STOP=1','-Upostgres','-d'+db],q).stdout
        def gate(db,user=None,password='fixture-password'):
            return command(['docker','exec','-i','-e','PGPASSWORD='+password,name,'psql','-XqAt','-vON_ERROR_STOP=1',
                            '-h127.0.0.1','-U'+(user or db),'-d'+db], (PACKAGE/'main.sql').read_text(),check=False)
        sql("CREATE ROLE seerr LOGIN PASSWORD 'fixture-password'; CREATE ROLE seerr_ru LOGIN PASSWORD 'fixture-password';")
        for db in ('seerr','seerr_ru'):
            sql(f'CREATE DATABASE {db} OWNER {db};')
            self.assertNotEqual(gate(db).returncode,0)
            sql(''.join(f'CREATE TABLE "{t}" (id integer); ALTER TABLE "{t}" OWNER TO {db};' for t in TABLES)
                + f'CREATE TABLE migrations (id integer,timestamp bigint,name text); ALTER TABLE migrations OWNER TO {db};'
                + "INSERT INTO migrations SELECT n,n,'fixture' FROM generate_series(1,18) n;"
                + "INSERT INTO migrations VALUES (19,1781732098511,'AddIgnoreQuotaToMediaRequest1781732098511');",db)
            self.assertNotEqual(gate(db).returncode,0,'Empty user data accepted')
            sql('INSERT INTO "user" VALUES (1);',db)
            before = sql('SELECT * FROM "user"; SELECT * FROM migrations ORDER BY id;',db)
            self.assertEqual(gate(db).returncode,0)
            self.assertEqual(before,sql('SELECT * FROM "user"; SELECT * FROM migrations ORDER BY id;',db))
            self.assertNotEqual(gate(db,password='wrong').returncode,0)
            self.assertNotEqual(gate(db,user='postgres',password='fixture-admin').returncode,0)
            self.assertNotEqual(gate(db,user='seerr_ru' if db=='seerr' else 'seerr').returncode,0)
            sql('ALTER TABLE media RENAME TO hidden_media;',db); self.assertNotEqual(gate(db).returncode,0)
            sql('ALTER TABLE hidden_media RENAME TO media; DELETE FROM migrations WHERE id=19;',db)
            self.assertNotEqual(gate(db).returncode,0)


class PackageTests(unittest.TestCase):
    def prepare(self):
        self.assertTrue((PACKAGE/'prepare.py').is_file(), 'Seerr preparation adapter not implemented')
        import importlib.util
        spec=importlib.util.spec_from_file_location('seerr_prepare',PACKAGE/'prepare.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

    def test_instance_composition_binds_its_own_gate_database_and_secret(self):
        prepare=self.prepare()
        for instance,db in (('seerr','seerr'),('seerr-ru','seerr_ru')):
            resources,values=prepare.build_sources(instance)
            main=values['controllers']['main'];inits=main['initContainers']
            self.assertEqual(inits['enrollment']['dependsOn'],'retained-state')
            self.assertEqual(inits['database']['dependsOn'],'enrollment')
            self.assertEqual(inits['enrollment']['args'],['--id',instance,'--database',db,'--role',db])
            self.assertEqual(main['serviceAccount']['name'],instance+'-postgres-completion')
            self.assertEqual(inits['retained-state']['command'][-1],instance)
            env=main['containers']['main']['env']
            self.assertEqual(env['DB_NAME'],db);self.assertEqual(env['DB_USER'],db)
            self.assertEqual(env['DB_PASS'],{'valueFrom':{'secretKeyRef':{'name':instance+'-postgres-secret','key':'password'}}})
            self.assertEqual(inits['retained-state']['env'],env)
            self.assertEqual(values['persistence']['seerr-config']['existingClaim'],instance+'-config-block')
            bindings=[r for r in resources if r['kind']=='RoleBinding'];self.assertEqual(len(bindings),2)
            self.assertEqual({r['metadata']['namespace'] for r in bindings},{'argocd','databases'})
            self.assertTrue(all(r['roleRef']['name']=='postgres-enrollment-completion-reader' for r in bindings))
            self.assertTrue(all(r['subjects']==[{'kind':'ServiceAccount','name':instance+'-postgres-completion','namespace':'media'}] for r in bindings))

    def test_static_binding_and_discovery_patches_are_inactive_and_distinct(self):
        for instance in ('seerr','seerr-ru'):
            folder=PACKAGE/'production'/instance
            self.assertTrue((folder/'pv.yaml').is_file(), 'Inactive binding not generated')
            pv=yaml.safe_load((folder/'pv.yaml').read_text());pvc=yaml.safe_load((folder/'pvc.yaml').read_text())
            self.assertEqual(pv['spec']['capacity']['storage'],'4Gi');self.assertEqual(pvc['spec']['resources']['requests']['storage'],'4Gi')
            self.assertEqual(pv['spec']['csi']['volumeHandle'],'homelab//k3s-block/9999/vm-9999-'+instance+'.raw')
            self.assertEqual(pv['spec']['persistentVolumeReclaimPolicy'],'Retain')
            self.assertEqual(pv['spec']['claimRef'],{'name':instance+'-config-block','namespace':'media'})
            self.assertEqual(pvc['spec']['volumeName'],pv['metadata']['name'])
            for obj in (pv,pvc):
                self.assertEqual(obj['spec']['accessModes'],['ReadWriteOncePod'])
                self.assertEqual(obj['metadata']['annotations']['argocd.argoproj.io/sync-options'],'Prune=false,Delete=false')
            metadata=yaml.safe_load((folder/'app-metadata.yaml').read_text())
            self.assertTrue(metadata['manifests'])
            if instance=='seerr-ru':self.assertTrue(metadata['valuesOverride'])
            policy,binding=yaml.safe_load_all((folder/'source-hold.yaml').read_text())
            self.assertIn("claimName == '"+instance+"'",policy['spec']['matchConditions'][0]['expression'])
            self.assertEqual(binding['spec']['policyName'],instance+'-source-hold')
        self.assertFalse(list(PACKAGE.rglob('app.yaml')))
        self.assertFalse(yaml.safe_load((ROOT/'services/media/seerr/app.yaml').read_text()).get('manifests',False))
        self.assertFalse(yaml.safe_load((ROOT/'services/media/seerr-ru/app.yaml').read_text()).get('valuesOverride',False))

    def test_existing_private_output_is_refused_without_replacement(self):
        prepare=self.prepare()
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);(root/'sentinel').write_bytes(b'original')
            with self.assertRaises(FileExistsError):prepare.prepare_enrollment(root)
            self.assertEqual(list(root.iterdir()),[root/'sentinel']);self.assertEqual((root/'sentinel').read_bytes(),b'original')

    def test_encrypted_inputs_preserve_previous_declarations_and_accept_current_hook(self):
        path=PACKAGE/'production/enrollment/enrollment-configmap.yaml'
        self.assertTrue(path.is_file(), 'Encrypted preparation not published')
        cm=yaml.safe_load(path.read_text());config=json.loads(cm['data']['config.json'])
        prior=json.loads(yaml.safe_load((ROOT/'infrastructure/controllers/databases/postgres/manifests/enrollment-configmap.yaml').read_text())['data']['config.json'])
        self.assertEqual(config['entries'][:-2],prior['entries']);self.assertEqual(config['expectedSystemIdentifier'],prior['expectedSystemIdentifier'])
        for instance,db,entry in zip(('seerr','seerr-ru'),('seerr','seerr_ru'),config['entries'][-2:]):
            self.assertEqual(entry,{'id':instance,'database':db,'role':db,'mode':'new','passwordKey':instance+'-password'})
            app=yaml.safe_load((PACKAGE/'production/enrollment'/(instance+'-application-secret.yaml')).read_text())
            self.assertEqual(app['metadata']['name'],instance+'-postgres-secret');self.assertEqual(app['metadata']['namespace'],'media')
            self.assertEqual(set(app['spec']['encryptedData']),{'password'});self.assertNotIn('stringData',app['spec']['template']);self.assertNotIn('data',app['spec']['template'])
        aggregate=yaml.safe_load((PACKAGE/'production/enrollment/enrollment-secret.yaml').read_text())
        existing=yaml.safe_load((ROOT/'infrastructure/controllers/databases/postgres/manifests/enrollment-secret.yaml').read_text())
        for key,value in existing['spec']['encryptedData'].items():self.assertEqual(aggregate['spec']['encryptedData'][key],value)
        sys.path.insert(0,str(ROOT/'scripts/postgres-enrollment'));import completion_gate
        self.assertEqual(cm['data']['acceptance-generation'],completion_gate.generation(cm['data']))
        job=yaml.safe_load((PACKAGE/'production/enrollment/enrollment-job.yaml').read_text());self.assertEqual(job['metadata']['name'],completion_gate.hook_name(cm['data']['acceptance-generation']))
        app={'metadata':{'name':'postgres','namespace':'argocd'},'status':{'sync':{'status':'Synced','revisions':['fixture-revision']},'health':{'status':'Healthy'},'operationState':{'phase':'Succeeded','operation':{'sync':{}},'syncResult':{'revisions':['fixture-revision'],'resources':[{'group':'batch','kind':'Job','namespace':'databases','name':job['metadata']['name'],'hookType':'Sync','hookPhase':'Succeeded'}]}}}}
        for instance,db in (('seerr','seerr'),('seerr-ru','seerr_ru')):
            identity={'id':instance,'database':db,'role':db};self.assertTrue(completion_gate.accepted(cm,app,identity))
            failed=copy.deepcopy(app);failed['status']['operationState']['syncResult']['resources'][0]['hookPhase']='Failed';self.assertFalse(completion_gate.accepted(cm,failed,identity))
            stale=copy.deepcopy(cm);stale['data']['encrypted-inputs-sha256']='new-input';self.assertFalse(completion_gate.accepted(stale,app,identity))


class RenderTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('SEERR_RETAINED_RENDER') and os.environ.get('SEERR_RU_RETAINED_RENDER'), 'Actual layered Helm renders required')
    def test_both_pods_mount_only_their_bound_state_and_credentials(self):
        for instance,db,flag in (('seerr','seerr','SEERR_RETAINED_RENDER'),('seerr-ru','seerr_ru','SEERR_RU_RETAINED_RENDER')):
            objects=list(yaml.safe_load_all(Path(os.environ[flag]).read_text()))
            deployment=next(x for x in objects if x.get('kind')=='Deployment');pod=deployment['spec']['template']['spec']
            self.assertEqual(deployment['spec']['replicas'],1);self.assertEqual(deployment['spec']['strategy']['type'],'Recreate')
            self.assertEqual(pod['nodeSelector'],{'node-role.kubernetes.io/worker':'true'})
            self.assertFalse(pod['automountServiceAccountToken']);self.assertNotIn('fsGroup',pod.get('securityContext',{}))
            self.assertEqual(pod['serviceAccountName'],instance+'-postgres-completion')
            volumes={v['name']:v for v in pod['volumes']}
            self.assertEqual([v['persistentVolumeClaim']['claimName'] for v in volumes.values() if 'persistentVolumeClaim' in v],[instance+'-config-block'])
            inits=pod['initContainers'];self.assertEqual([c['name'] for c in inits],['retained-state','enrollment','database'])
            self.assertEqual(inits[1]['args'],['--id',instance,'--database',db,'--role',db])
            self.assertEqual(inits[0]['command'][-1],instance)
            for container in [*inits,*pod['containers']]:
                mounts={m['mountPath']:m for m in container.get('volumeMounts',[])}
                if '/gate-api' in mounts:
                    self.assertEqual(container['name'],'enrollment')
                    self.assertIn('projected',volumes[mounts['/gate-api']['name']])
                if '/credentials' in mounts:
                    self.assertEqual(container['name'],'database')
                    self.assertEqual(volumes[mounts['/credentials']['name']]['secret']['secretName'],instance+'-postgres-secret')
                if container['name'] in ('main','retained-state'):
                    self.assertIn('/app/config',mounts)
                    self.assertEqual(mounts['/app/config'].get('readOnly',False),container['name']=='retained-state')
                    self.assertEqual(container['securityContext']['runAsUser'],1000);self.assertEqual(container['securityContext']['runAsGroup'],1000)
                    env={v['name']:v for v in container['env']}
                    for key,want in {'NODE_ENV':'production','DB_TYPE':'postgres','DB_HOST':'postgres-postgresql.databases','DB_PORT':'5432','DB_NAME':db,'DB_USER':db,'DB_POOL_SIZE':'3'}.items():self.assertEqual(env[key]['value'],want)
                    self.assertEqual(env['DB_PASS']['valueFrom']['secretKeyRef'],{'name':instance+'-postgres-secret','key':'password'})
                else:self.assertNotIn('/app/config',mounts)
                if container['name']!='enrollment':self.assertNotIn('/gate-api',mounts)
                if container['name']!='database':self.assertNotIn('/credentials',mounts)
            main=next(c for c in pod['containers'] if c['name']=='main')
            self.assertEqual(main['image'],'ghcr.io/seerr-team/seerr:v3.4.1@sha256:f4768de5f616248d723e05891f3345a1402123775d03bf0890dbfedc0831bda1')
            for name in ('livenessProbe','readinessProbe','startupProbe'):self.assertEqual(main[name]['httpGet']['path'],'/api/v1/status/appdata')
            self.assertFalse(any(x.get('kind')=='PersistentVolumeClaim' for x in objects),'Dynamic claim remains')

    @unittest.skipUnless(os.environ.get('SEERR_RETAINED_RENDER'), 'Actual preparation renders required')
    def test_future_base_config_bindings_render_without_dynamic_provisioning(self):
        with tempfile.TemporaryDirectory() as temporary:
            chart=Path(temporary)/'base-configs';shutil.copytree(ROOT/'infrastructure/base-configs',chart)
            for instance in ('seerr','seerr-ru'):
                folder=chart/'templates'/(instance+'-block-storage');folder.mkdir()
                for name in ('pv.yaml','pvc.yaml'):shutil.copyfile(PACKAGE/'production'/instance/name,folder/name)
            r=subprocess.run(['helm','template','base-configs',str(chart),'-f',str(ROOT/'templates/globals.yaml')],capture_output=True,text=True,timeout=30)
            self.assertEqual(r.returncode,0,r.stderr)
            objects=[x for x in yaml.safe_load_all(r.stdout) if x]
            for instance in ('seerr','seerr-ru'):
                pv=next(x for x in objects if x['kind']=='PersistentVolume' and x['metadata']['name']==instance+'-config-block')
                pvc=next(x for x in objects if x['kind']=='PersistentVolumeClaim' and x['metadata']['name']==instance+'-config-block')
                self.assertEqual(pv['spec']['claimRef'],{'namespace':'media','name':instance+'-config-block'})
                self.assertEqual(pvc['spec']['volumeName'],pv['metadata']['name'])
                self.assertEqual(pv['spec']['csi']['volumeHandle'],'homelab//k3s-block/9999/vm-9999-'+instance+'.raw')

    def test_embedded_guard_and_gate_bytes_match_qualified_source(self):
        guard=yaml.safe_load((PACKAGE/'production/guard-configmap.yaml').read_text())
        for name in ('guard.py','main.sql'):self.assertEqual(guard['data'][name],(PACKAGE/name).read_text())
        for instance in ('seerr','seerr-ru'):
            resources=list(yaml.safe_load_all((PACKAGE/'production'/instance/'consumer-gate.yaml').read_text()))
            cm=next(x for x in resources if x['kind']=='ConfigMap')
            self.assertEqual(cm['data']['completion_gate.py'],(ROOT/'scripts/postgres-enrollment/completion_gate.py').read_text())


if __name__ == '__main__':unittest.main()
