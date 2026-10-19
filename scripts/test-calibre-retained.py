#!/usr/bin/env python3
"""Retained CWA identity/header rejection tests; native recovery runs separately."""
import base64
import importlib.util
import os
from pathlib import Path
import sqlite3
import yaml
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
GUARD=ROOT/'scripts/calibre-retained/guard.py'

class GuardTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(GUARD.is_file(),'Retained CWA guard must exist')
        spec=importlib.util.spec_from_file_location('calibre_guard',GUARD)
        self.guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.guard)
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.base=Path(tmp.name);self.root=self.base/'state';self.root.mkdir()
        (self.root/'.homelab-calibre-web-data').write_text('homelab/calibre-web/data/v1\n')
        for name in ('config/app.db','config/gdrive.db','config/cwa.db','library/metadata.db','library/.calnotes/notes.db'):
            p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True)
            with sqlite3.connect(p)as c:c.execute('CREATE TABLE native_fixture(id INTEGER PRIMARY KEY)')
            c.close()
        (self.root/'config/.key').write_bytes(base64.urlsafe_b64encode(b'K'*32))

    def test_valid_layout_is_read_only(self):
        before={str(p.relative_to(self.root)):(p.read_bytes(),p.stat().st_mtime_ns)for p in self.root.rglob('*')if p.is_file()}
        self.guard.validate(self.root)
        self.assertEqual(before,{str(p.relative_to(self.root)):(p.read_bytes(),p.stat().st_mtime_ns)for p in self.root.rglob('*')if p.is_file()})

    def test_missing_or_wrong_identity_is_refused(self):
        marker=self.root/'.homelab-calibre-web-data'
        for value in ('','homelab/another/data/v1\n'):
            marker.write_text(value)
            with self.assertRaises((ValueError,OSError)):self.guard.validate(self.root)
        marker.unlink()
        with self.assertRaises((ValueError,OSError)):self.guard.validate(self.root)

    def test_every_database_requires_native_header_and_body(self):
        for name in ('config/app.db','config/gdrive.db','config/cwa.db','library/metadata.db','library/.calnotes/notes.db'):
            p=self.root/name;old=p.read_bytes()
            for invalid in (b'',b'SQLite format 3\0',b'wrong database'+bytes(100)):
                p.write_bytes(invalid)
                with self.subTest(name=name),self.assertRaises((ValueError,OSError)):self.guard.validate(self.root)
            p.write_bytes(old)
            p.rename(self.base/'missing')
            with self.assertRaises((ValueError,OSError)):self.guard.validate(self.root)
            (self.base/'missing').rename(p)

    def test_preserved_encryption_key_is_required(self):
        p=self.root/'config/.key'
        for raw in (b'',b'not a native key',base64.urlsafe_b64encode(b'K'*31)):
            p.write_bytes(raw)
            with self.assertRaises((ValueError,OSError)):self.guard.validate(self.root)

    def test_redirected_parents_files_and_special_files_are_refused(self):
        alias=self.base/'alias';alias.symlink_to(self.root,target_is_directory=True)
        with self.assertRaises((ValueError,OSError)):self.guard.validate(alias)
        p=self.root/'library/metadata.db';p.rename(self.base/'outside');p.symlink_to(self.base/'outside')
        with self.assertRaises((ValueError,OSError)):self.guard.validate(self.root)
        p.unlink();os.mkfifo(p)
        with self.assertRaises((ValueError,OSError)):self.guard.validate(self.root)
        p.unlink();(self.base/'outside').rename(p)
        (self.root/'library/.calnotes').rename(self.base/'outside-notes');(self.root/'library/.calnotes').symlink_to(self.base/'outside-notes',target_is_directory=True)
        with self.assertRaises((ValueError,OSError)):self.guard.validate(self.root)

class SourceTests(unittest.TestCase):
    def test_guard_and_static_bindings_are_canonical(self):
        cm=yaml.safe_load((ROOT/'services/media/calibre-web/manifests/retained-startup-guard.yaml').read_text())
        self.assertEqual(cm['data']['guard.py'],GUARD.read_text())
        objects=list(yaml.safe_load_all((ROOT/'scripts/calibre-retained/production/bindings.yaml').read_text()))
        for obj in objects:
            name='pv.yaml'if obj['kind']=='PersistentVolume'else'pvc.yaml'
            self.assertEqual(obj,yaml.safe_load((ROOT/'infrastructure/base-configs/templates/calibre-web-block-storage'/name).read_text()))
            self.assertEqual(obj['metadata']['annotations']['argocd.argoproj.io/sync-options'],'Prune=false,Delete=false')
            self.assertEqual(obj['spec']['accessModes'],['ReadWriteOncePod'])
        pv,pvc=objects
        self.assertEqual(pv['spec']['persistentVolumeReclaimPolicy'],'Retain')
        self.assertEqual(pv['spec']['csi']['volumeHandle'],'homelab//k3s-block/9999/vm-9999-calibre-web.raw')
        self.assertEqual(pv['spec']['claimRef'],{'name':'calibre-web-block','namespace':'media'})
        self.assertEqual(pvc['spec']['volumeName'],'calibre-web-block')
        self.assertEqual(pvc['spec']['resources']['requests']['storage'],'1Gi')

    def test_source_retention_and_active_phase_agree(self):
        current=yaml.safe_load((ROOT/'services/media/calibre-web/values.yaml').read_text())
        active=current['persistence'].get('retained-data',{}).get('existingClaim')=='calibre-web-block'
        for name in('source-pvc.yaml','source-hold.yaml'):
            path=ROOT/'services/media/calibre-web/manifests'/name
            self.assertEqual(path.is_file(),active)
            if active:self.assertEqual(next(yaml.safe_load_all(path.read_text())),next(yaml.safe_load_all((ROOT/'scripts/calibre-retained/production'/name).read_text())))
        source=yaml.safe_load((ROOT/'scripts/calibre-retained/production/source-pvc.yaml').read_text())
        self.assertEqual(source['metadata']['annotations']['argocd.argoproj.io/sync-options'],'Prune=false,Delete=false')
        self.assertEqual(source['spec']['accessModes'],['ReadWriteMany'])
        self.assertEqual(source['spec']['storageClassName'],'nfs-pv')
        self.assertEqual(source['spec']['resources']['requests']['storage'],'2Gi')
        policy=next(yaml.safe_load_all((ROOT/'scripts/calibre-retained/production/source-hold.yaml').read_text()))
        self.assertTrue(any('UPDATE'in r['operations']and'pods/ephemeralcontainers'in r['resources']for r in policy['spec']['matchConstraints']['resourceRules']))


@unittest.skipUnless(all(os.environ.get(v)for v in('CALIBRE_BEFORE_RENDER','CALIBRE_PREPARATION_RENDER','CALIBRE_RETAINED_RENDER')),'actual chart layers required')
class RenderTests(unittest.TestCase):
    def test_preparation_preserves_pod_and_retained_layout_preserves_native_settings(self):
        def objects(flag):return[v for v in yaml.safe_load_all(Path(os.environ[flag]).read_text())if v]
        def deployment(flag):return next(v for v in objects(flag)if v['kind']=='Deployment')
        before=deployment('CALIBRE_BEFORE_RENDER');prepared=deployment('CALIBRE_PREPARATION_RENDER');after=deployment('CALIBRE_RETAINED_RENDER')
        # The inactive preparation must not restart the NFS app.
        self.assertEqual(before['spec']['template'],prepared['spec']['template'])
        pod=after['spec']['template']['spec']
        self.assertEqual(after['spec']['replicas'],1);self.assertEqual(after['spec']['strategy']['type'],'Recreate')
        self.assertFalse(pod['automountServiceAccountToken']);self.assertNotIn('fsGroup',pod.get('securityContext')or{})
        self.assertEqual(pod['nodeSelector'],{'node-role.kubernetes.io/worker':'true'})
        self.assertEqual(pod['tolerations'],[{'key':k,'operator':'Exists','effect':'NoExecute'}for k in('node.kubernetes.io/not-ready','node.kubernetes.io/unreachable')])
        main=dict(pod['containers'][0]);old=dict(before['spec']['template']['spec']['containers'][0]);old.pop('volumeMounts');mounts={m['mountPath']:m for m in main.pop('volumeMounts')};self.assertEqual(main,old)
        self.assertEqual(set(mounts),{'/config','/calibre-library','/calibre-books','/cwa-book-ingest'})
        volumes={v['name']:v for v in pod['volumes']}
        for path,sub in(('/config','config'),('/calibre-library','library')):
            m=mounts[path];self.assertEqual(m['subPath'],sub);self.assertEqual(volumes[m['name']]['persistentVolumeClaim']['claimName'],'calibre-web-block')
        book=mounts['/calibre-books'];self.assertEqual(book['subPath'],'library/books');self.assertEqual(volumes[book['name']]['persistentVolumeClaim']['claimName'],'media-library-pvc')
        self.assertEqual(volumes[mounts['/cwa-book-ingest']['name']]['persistentVolumeClaim']['claimName'],'cwa-book-ingest')
        self.assertEqual(len(pod['initContainers']),1);guard=pod['initContainers'][0]
        self.assertEqual(guard['name'],'retained-state');self.assertEqual(len(guard['volumeMounts']),2);self.assertTrue(all(m.get('readOnly')for m in guard['volumeMounts']))
        self.assertFalse(guard.get('envFrom'));self.assertEqual(guard['securityContext']['capabilities']['drop'],['ALL'])


if __name__=='__main__':unittest.main()
