#!/usr/bin/env python3
"""Cold-file transfer rejections and retained NFS binding contract."""
import importlib.util
import copy as deepcopy_module
import json
import os
from pathlib import Path
import tempfile
import struct
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('cold_copy', ROOT / 'scripts/ordinary-file-storage/copy_files.py')
copy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(copy)


class ColdCopyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source, self.target = self.base / 'source', self.base / 'target'
        self.source.mkdir()
        self.target.mkdir()
        (self.source / '.identity').write_text('fixture/v1\n')

    def transfer(self):
        return copy.copy_files(self.source, self.target, '.identity', 'fixture/v1\n')

    def test_only_kernel_posix_mode_acl_projection_is_accepted(self):
        def encode(entries):
            raw = struct.pack('>I',len(entries))
            for typ, flags, mask, who in entries:
                name=who.encode()
                raw+=struct.pack('>IIII',typ,flags,mask,len(name))+name+b'\0'*((-len(name))%4)
            return raw
        simple=[(0,0,0x160187,'OWNER@'),(0,0,0x120081,'GROUP@'),(0,0,0x120080,'EVERYONE@')]
        copy.check_mode_acl(encode(simple),0o100640)
        with self.assertRaises(ValueError): copy.check_mode_acl(encode(simple),0o100600)
        for change in ([*simple,(0,0,1,'named@example.invalid')],
                       [(0,1,0x160187,'OWNER@'),*simple[1:]],
                       [(0,0,0x1f01ff,'OWNER@'),*simple[1:]]):
            with self.assertRaises(ValueError): copy.check_mode_acl(encode(change),0o100640)
        with self.assertRaises(ValueError): copy.check_mode_acl(encode(simple)[:-1],0o100640)
        # Non-monotonic POSIX mode needs explicit owner and group DENY entries.
        unusual=[(1,0,7,'OWNER@'),(0,0,0x160180,'OWNER@'),
                 (0,0,0x120080,'GROUP@'),(1,0,7,'GROUP@'),(0,0,0x120087,'EVERYONE@')]
        copy.check_mode_acl(encode(unusual),0o100006)

    def test_complete_bytes_metadata_links_and_empty_directories(self):
        (self.source / 'empty').mkdir()
        (self.source / 'unicode שלום').write_bytes(bytes(range(256)))
        (self.source / 'zero').touch()
        os.chmod(self.source / 'unicode שלום', 0o640)
        os.utime(self.source / 'unicode שלום', ns=(1234567890123456789,1234567890123456789))
        os.link(self.source / 'unicode שלום', self.source / 'hardlink')
        (self.source / 'link').symlink_to('unicode שלום')
        (self.source / 'lost+found').mkdir()
        before = copy.inventory(self.source)
        result = self.transfer()
        self.assertTrue(result['bytesAndPosixMetadataEqual'])
        self.assertEqual(copy.inventory(self.source), before)
        self.assertEqual(copy.inventory(self.target), before)
        self.assertFalse((self.target / 'lost+found').exists())
        self.assertEqual((self.target / 'hardlink').stat().st_ino, (self.target / 'unicode שלום').stat().st_ino)

    @unittest.skipIf(os.geteuid()==0,'root bypasses directory permission denial')
    def test_unreadable_subdirectory_is_rejected_before_writes(self):
        private=self.source/'private'
        private.mkdir()
        (private/'preserve').write_text('must not disappear')
        private.chmod(0)
        try:
            with self.assertRaises(PermissionError):self.transfer()
            self.assertEqual(list(self.target.iterdir()),[])
        finally:
            private.chmod(0o700)

    def test_existing_target_and_wrong_identity_are_rejected_before_writes(self):
        (self.target / 'existing').write_text('preserve')
        with self.assertRaises(ValueError): self.transfer()
        self.assertEqual((self.target / 'existing').read_text(), 'preserve')
        (self.target / 'existing').unlink()
        (self.source / '.identity').write_text('wrong')
        with self.assertRaises(ValueError): self.transfer()
        self.assertEqual(list(self.target.iterdir()), [])

    def test_linked_parent_and_overlapping_roots_are_rejected_before_writes(self):
        alias = self.base / 'alias'
        alias.symlink_to(self.base, target_is_directory=True)
        with self.assertRaises(ValueError):
            copy.copy_files(alias / 'source', self.target, '.identity', 'fixture/v1\n')
        with self.assertRaises(ValueError):
            copy.copy_files(self.source, self.source, '.identity', 'fixture/v1\n')
        self.assertEqual(list(self.target.iterdir()), [])

    def test_special_files_external_links_and_recovery_data_require_decision(self):
        os.mkfifo(self.source / 'fifo')
        with self.assertRaises(ValueError): self.transfer()
        (self.source / 'fifo').unlink()
        os.link(self.source / '.identity', self.base / 'outside-link')
        with self.assertRaises(ValueError): self.transfer()
        (self.base / 'outside-link').unlink()
        (self.source / 'lost+found').mkdir()
        (self.source / 'lost+found/recovered').write_text('preserve')
        with self.assertRaises(ValueError): self.transfer()
        self.assertEqual(list(self.target.iterdir()), [])


class BindingTests(unittest.TestCase):
    def test_single_contract_has_unique_private_paths_and_preserved_identities(self):
        rows = json.loads((ROOT / 'infrastructure/base-configs/files/ordinary-file-volumes.json').read_text())
        self.assertEqual(len(rows),10)
        self.assertEqual(len({v['claim'] for v in rows}),len(rows))
        for v in rows:
            self.assertNotEqual(v['sourceClaim'],v['claim'])
            self.assertTrue(v['sourceClaim'].endswith('-block'))
            self.assertEqual(v['claim'],v['app']+'-files')
            self.assertTrue(v['identity'].startswith('homelab/'+v['app']+'/'))
            self.assertEqual(Path(v['marker']).name,v['marker'])

    @unittest.skipUnless(os.environ.get('ORDINARY_FILE_RENDER'),'actual base-configs render required')
    def test_rendered_bindings_are_static_retained_and_never_dynamic(self):
        rows=json.loads((ROOT / 'infrastructure/base-configs/files/ordinary-file-volumes.json').read_text())
        objects=[v for v in yaml.safe_load_all(Path(os.environ['ORDINARY_FILE_RENDER']).read_text()) if v]
        for row in rows:
            pv=next(v for v in objects if v['kind']=='PersistentVolume' and v['metadata']['name']==row['claim'])
            pvc=next(v for v in objects if v['kind']=='PersistentVolumeClaim' and v['metadata']['name']==row['claim'])
            self.assertEqual(pv['spec']['nfs'],{'server':'10.9.8.30','path':'/mnt/apps/pv/'+row['namespace']+'/'+row['claim']})
            self.assertEqual(pv['spec']['persistentVolumeReclaimPolicy'],'Retain')
            self.assertEqual(pv['spec']['claimRef'],{'name':row['claim'],'namespace':row['namespace']})
            self.assertEqual(pv['spec']['storageClassName'],'')
            self.assertEqual(pvc['spec']['storageClassName'],'')
            self.assertEqual(pvc['spec']['volumeName'],row['claim'])
            self.assertEqual(pvc['metadata']['namespace'],row['namespace'])
            self.assertEqual(pvc['spec']['accessModes'],['ReadWriteOnce'])
            self.assertIn('hard',pv['spec']['mountOptions'])
            for obj in (pv,pvc):
                self.assertEqual(obj['metadata']['annotations']['argocd.argoproj.io/sync-options'],'Prune=false,Delete=false')

    @unittest.skipUnless(os.environ.get('ORDINARY_FILE_RENDER'),'actual base-configs render required')
    def test_retired_csi_hold_is_scoped_to_exact_old_claims(self):
        rows=json.loads((ROOT / 'infrastructure/base-configs/files/ordinary-file-volumes.json').read_text())
        objects=[v for v in yaml.safe_load_all(Path(os.environ['ORDINARY_FILE_RENDER']).read_text()) if v]
        policy=next(v for v in objects if v['kind']=='ValidatingAdmissionPolicy' and v['metadata']['name']=='ordinary-file-retired-csi-hold')
        binding=next(v for v in objects if v['kind']=='ValidatingAdmissionPolicyBinding' and v['metadata']['name']==policy['metadata']['name'])
        self.assertEqual(policy['spec']['failurePolicy'],'Fail')
        self.assertEqual(policy['spec']['matchConstraints']['resourceRules'],[{'apiGroups':[''],'apiVersions':['v1'],'operations':['CREATE'],'resources':['pods'],'scope':'Namespaced'}])
        expression=policy['spec']['matchConditions'][0]['expression']
        self.assertEqual(expression.count('v.persistentVolumeClaim.claimName =='),len(rows))
        for row in rows:
            self.assertIn("object.metadata.namespace == '"+row['namespace']+"' && v.persistentVolumeClaim.claimName == '"+row['sourceClaim']+"'", expression)
            self.assertNotIn("claimName == '"+row['claim']+"'",expression)
        self.assertEqual(policy['spec']['validations'][0]['expression'],'false')
        self.assertEqual(binding['spec'],{'policyName':policy['metadata']['name'],'validationActions':['Deny']})


@unittest.skipUnless(os.environ.get('ORDINARY_FILE_RUNTIME_RENDERS'),'actual app renders required')
class RuntimeTests(unittest.TestCase):
    def test_all_ten_deployments_use_only_their_populated_target(self):
        rows=json.loads((ROOT / 'infrastructure/base-configs/files/ordinary-file-volumes.json').read_text())
        folder=Path(os.environ['ORDINARY_FILE_RUNTIME_RENDERS'])
        for row in rows:
            with self.subTest(app=row['app']):
                objects=[v for v in yaml.safe_load_all((folder/(row['app']+'.yaml')).read_text()) if v]
                deployments=[v for v in objects if v['kind']=='Deployment' and any(w.get('persistentVolumeClaim',{}).get('claimName')==row['claim'] for w in v['spec']['template']['spec'].get('volumes',[]))]
                self.assertEqual(len(deployments),1)
                d=deployments[0]
                self.assertEqual(d['spec']['replicas'],1)
                self.assertEqual(d['spec']['strategy']['type'],'Recreate')
                pod=d['spec']['template']['spec']
                before=[v for v in yaml.safe_load_all((folder/(row['app']+'-before.yaml')).read_text()) if v]
                old=next(v for v in before if v['kind']=='Deployment' and v['metadata']['name']==d['metadata']['name'])
                expected=deepcopy_module.deepcopy(old['spec']['template']['spec'])
                replaced=0
                for volume in expected.get('volumes',[]):
                    if volume.get('persistentVolumeClaim',{}).get('claimName')==row['sourceClaim']:
                        volume['persistentVolumeClaim']['claimName']=row['claim'];replaced+=1
                self.assertEqual(replaced,1)
                self.assertEqual(pod,expected,'Storage activation must preserve every other Pod setting')
                self.assertGreaterEqual(len(pod.get('initContainers',[])),1)
                self.assertFalse(any(w.get('persistentVolumeClaim',{}).get('claimName')==row['sourceClaim'] for w in pod['volumes']))
                self.assertFalse(any(v['kind']=='PersistentVolumeClaim' and v['metadata']['name']==row['claim'] for v in objects),'Targets must be the separately prebound static claims')


if __name__=='__main__':unittest.main()
