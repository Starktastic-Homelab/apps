#!/usr/bin/env python3
"""Actual layered render contracts for inactive retained storage candidates."""
import copy
import os
import shlex
import sys
import unittest
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'scripts/redis-immich-retained'
PRODUCTION = PACKAGE / 'production'
REDIS = 'registry-1.docker.io/bitnami/redis@sha256:f4797b37502e6db910d3653368fcfadc171ef605586917774de125ddd05b3e62'
EXPORTER = 'registry-1.docker.io/bitnami/redis-exporter@sha256:a7144e7e82d7dc5dc5ce5b78e096fe74d9508379a1b8eef07a197adda6d964ad'
PG = 'ghcr.io/immich-app/postgres:17-vectorchord0.4.3-pgvector0.8.1@sha256:79b95b795f0911e95ffa4d092a2162c4d81a984d5629bc8f786afe0bc0657671'
CONTRACTS = [('redis', 'databases', 'redis-data-block', 'redis-data', '2Gi'),
             ('immich-postgres', 'media', 'immich-postgres-block', 'immich-postgres', '10Gi')]


def docs(path):
    return [x for x in yaml.safe_load_all(path.read_text()) if x]


def keyed(path):
    return {(x['kind'], x['metadata']['name']): x for x in docs(path)}


class Manifests(unittest.TestCase):
    def test_static_bindings_cannot_allocate_or_adopt_other_media(self):
        for app, namespace, claim, image, size in CONTRACTS:
            path = PRODUCTION / (app + '-bindings.yaml')
            self.assertTrue(path.is_file(), 'Inactive retained bindings missing: ' + app)
            pv, pvc = docs(path)
            self.assertEqual((pv['kind'], pvc['kind']), ('PersistentVolume', 'PersistentVolumeClaim'))
            self.assertEqual(pv['metadata']['name'], claim)
            self.assertEqual(pvc['metadata']['name'], claim)
            self.assertEqual(pvc['metadata']['namespace'], namespace)
            for item in (pv, pvc):
                self.assertEqual(item['metadata']['annotations']['argocd.argoproj.io/sync-options'], 'Prune=false,Delete=false')
                self.assertEqual(item['spec']['accessModes'], ['ReadWriteOncePod'])
                self.assertEqual(item['spec']['storageClassName'], 'proxmox-retained')
                self.assertEqual(item['spec']['volumeMode'], 'Filesystem')
            self.assertEqual(pv['spec']['persistentVolumeReclaimPolicy'], 'Retain')
            self.assertEqual(pv['spec']['capacity']['storage'], size)
            self.assertEqual(pvc['spec']['resources']['requests']['storage'], size)
            self.assertEqual(pv['spec']['claimRef'], {'name': claim, 'namespace': namespace})
            self.assertEqual(pvc['spec']['volumeName'], claim)
            self.assertEqual(pv['spec']['csi'], {'driver': 'csi.proxmox.sinextra.dev', 'fsType': 'ext4',
                'volumeHandle': 'homelab//k3s-block/9999/vm-9999-' + image + '.raw',
                'volumeAttributes': {'storage': 'k3s-block', 'cache': 'none'}})
            expressions = pv['spec']['nodeAffinity']['required']['nodeSelectorTerms'][0]['matchExpressions']
            self.assertEqual({x['key']: (x['operator'], x['values']) for x in expressions}, {
                'topology.kubernetes.io/region': ('In', ['homelab']), 'topology.kubernetes.io/zone': ('In', ['pve'])})

    def test_guard_maps_are_exact_qualified_sources(self):
        for app, namespace, _, _, _ in CONTRACTS:
            path = PRODUCTION / (('redis' if app == 'redis' else 'immich') + '-guard-configmap.yaml')
            self.assertTrue(path.is_file(), 'Qualified guard ConfigMap missing')
            config = docs(path)[0]
            script = 'redis-guard.sh' if app == 'redis' else 'postgres-guard.sh'
            self.assertEqual(config['data'], {'guard.sh': (PACKAGE / script).read_text()})
            self.assertEqual(config['metadata']['namespace'], namespace)

    def render(self, name):
        path = Path(os.environ.get('REDIS_IMMICH_RENDERS', '/tmp/redis-immich-renders')) / (name + '.yaml')
        self.assertTrue(path.exists(), 'Missing actual layered render: ' + name)
        return keyed(path)

    def guard(self, pod, image, claim, uid):
        self.assertIsNone(pod.get('securityContext', {}).get('fsGroup'))
        self.assertFalse(pod.get('automountServiceAccountToken', True))
        self.assertEqual(pod['nodeSelector'], {'kubernetes.io/os': 'linux', 'node-role.kubernetes.io/worker': 'true'})
        self.assertEqual(pod['tolerations'], [
            {'key': 'node.kubernetes.io/not-ready', 'operator': 'Exists', 'effect': 'NoExecute'},
            {'key': 'node.kubernetes.io/unreachable', 'operator': 'Exists', 'effect': 'NoExecute'}])
        self.assertEqual(len(pod['initContainers']), 1)
        guard = pod['initContainers'][0]
        self.assertEqual(guard['name'], 'verify-retained-data')
        self.assertEqual(guard['image'], image)
        self.assertEqual(guard['securityContext']['runAsUser'], uid)
        self.assertTrue(guard['securityContext']['readOnlyRootFilesystem'])
        self.assertFalse(guard['securityContext']['allowPrivilegeEscalation'])
        self.assertEqual(guard['securityContext']['capabilities']['drop'], ['ALL'])
        self.assertNotIn('envFrom', guard)
        self.assertEqual({x['mountPath'] for x in guard['volumeMounts']}, {'/data', '/tmp', '/retained-startup'})
        self.assertTrue(next(x for x in guard['volumeMounts'] if x['mountPath'] == '/data')['readOnly'])
        self.assertTrue(next(x for x in guard['volumeMounts'] if x['mountPath'] == '/retained-startup')['readOnly'])
        volumes = {x['name']: x for x in pod['volumes']}
        mount = next(x for x in guard['volumeMounts'] if x['mountPath'] == '/data')
        self.assertEqual(volumes[mount['name']]['persistentVolumeClaim'], {'claimName': claim})
        for mount in guard['volumeMounts']:
            self.assertNotIn('secret', volumes[mount['name']])
        return guard

    def test_native_fixture_uses_the_actual_candidate_configuration(self):
        sys.path.insert(0, str(PACKAGE))
        import fixtures
        rendered = self.render('redis')[('ConfigMap', 'redis-configuration')]['data']
        def directives(text):
            return [shlex.split(line, comments=True) for line in text.splitlines() if shlex.split(line, comments=True)]
        self.assertEqual(directives(fixtures.REDIS_FIXTURE_CONFIG), directives(rendered['redis.conf'] + '\n' + rendered['master.conf']))

    def test_redis_preserves_containers_services_config_and_auth(self):
        before, after = self.render('redis-before'), self.render('redis')
        a, b = before[('StatefulSet', 'redis-master')], after[('StatefulSet', 'redis-master')]
        guard = self.guard(b['spec']['template']['spec'], REDIS, 'redis-data-block', 1001)
        self.assertFalse(guard.get('env'))
        self.assertNotIn('volumeClaimTemplates', b['spec'])
        self.assertFalse(any(x['kind'] == 'PersistentVolumeClaim' for x in after.values()))
        ac = a['spec']['template']['spec']['containers']
        bc = b['spec']['template']['spec']['containers']
        self.assertEqual([x['name'] for x in ac], [x['name'] for x in bc])
        for source, target in zip(ac, bc):
            expected = copy.deepcopy(source)
            expected['image'] = REDIS if source['name'] == 'redis' else EXPORTER
            self.assertEqual(target, expected)
        # Compare the whole StatefulSet after removing only the independently
        # checked storage, guard, digest, ownership and placement differences.
        aa, bb = copy.deepcopy(a), copy.deepcopy(b)
        aa['spec'].pop('volumeClaimTemplates', None)
        for obj in (aa, bb):
            spec = obj['spec']['template']['spec']
            spec.pop('initContainers', None)
            spec.pop('nodeSelector', None)
            spec.pop('tolerations', None)
            spec.get('securityContext', {}).pop('fsGroup', None)
            spec['volumes'] = [v for v in spec['volumes'] if v['name'] not in ('redis-data','retained-startup','retained-scratch')]
            for container in spec['containers']:
                container.pop('image')
            obj['spec']['template']['metadata'].get('annotations', {}).pop('checksum/configmap', None)
        self.assertEqual(aa, bb)
        for key, item in before.items():
            if key == ('StatefulSet', 'redis-master'):
                continue
            expected = copy.deepcopy(item)
            if key == ('ConfigMap', 'redis-configuration'):
                conf = expected['data']['redis.conf']
                expected['data']['redis.conf'] = conf.replace('save ""', 'save ""\nappendfsync everysec')
            self.assertEqual(after[key], expected, str(key))

    def test_immich_changes_only_postgres_storage_guard_and_placement(self):
        before, after = self.render('immich-before'), self.render('immich')
        key = ('Deployment', 'immich-postgres')
        for identifier, item in before.items():
            if identifier != key:
                self.assertEqual(after[identifier], item, str(identifier))
        a, b = before[key], after[key]
        guard = self.guard(b['spec']['template']['spec'], PG, 'immich-postgres-block', 999)
        self.assertEqual(guard['env'], [{'name': 'EXPECTED_SYSTEM_IDENTIFIER', 'value': '7614955115223928876'}])
        self.assertEqual(b['spec']['strategy']['type'], 'Recreate')
        source = copy.deepcopy(a['spec']['template']['spec']['containers'])
        target = b['spec']['template']['spec']['containers']
        self.assertEqual(len(target), 1)
        source[0]['securityContext'] = target[0]['securityContext']
        self.assertEqual(source, target)
        self.assertEqual(target[0]['securityContext']['runAsUser'], 999)
        self.assertEqual(target[0]['securityContext']['runAsGroup'], 999)
        self.assertTrue(target[0]['securityContext']['runAsNonRoot'])
        self.assertFalse(target[0]['securityContext']['allowPrivilegeEscalation'])
        self.assertEqual(target[0]['securityContext']['capabilities']['drop'], ['ALL'])
        aa, bb = copy.deepcopy(a), copy.deepcopy(b)
        for obj in (aa, bb):
            obj['spec'].pop('strategy', None)
            spec = obj['spec']['template']['spec']
            spec.pop('initContainers', None)
            spec.pop('nodeSelector', None)
            spec.pop('tolerations', None)
            spec.get('securityContext', {}).pop('fsGroup', None)
            if not spec.get('securityContext'):
                spec.pop('securityContext', None)
            for container in spec['containers']:
                container.pop('securityContext', None)
            spec['volumes'] = [v for v in spec['volumes'] if v['name'] not in ('pgdata','retained-startup','retained-scratch')]
        self.assertEqual(aa, bb)

    def test_retired_source_policies_are_scoped_and_durable(self):
        for app, namespace, claim, path in [
            ('redis', 'databases', 'redis-data-redis-master-0', '/mnt/apps/pv/databases/redis-data-redis-master-0'),
            ('immich', 'media', 'immich-pgdata', '/mnt/apps/pv/media/immich-pgdata')]:
            policy, binding = docs(PRODUCTION / (app + '-source-hold.yaml'))
            self.assertEqual(policy['spec']['failurePolicy'], 'Fail')
            self.assertEqual(policy['spec']['validations'], [{'expression': 'false', 'message': 'Preserved ' + app + ' NFS state is retired; verified recovery is required.'}])
            self.assertEqual(policy['spec']['matchConstraints']['resourceRules'], [{'apiGroups': [''], 'apiVersions': ['v1'], 'operations': ['CREATE','UPDATE'], 'resources': ['pods']}])
            expected = 'has(object.spec.volumes) && object.spec.volumes.exists(v, (object.metadata.namespace == "' + namespace + '" && has(v.persistentVolumeClaim) && v.persistentVolumeClaim.claimName == "' + claim + '") || (has(v.nfs) && v.nfs.server in ["10.9.8.30", "10.9.9.30"] && (v.nfs.path == "' + path + '" || v.nfs.path.startsWith("' + path + '/"))))'
            self.assertEqual(policy['spec']['matchConditions'], [{'name':'held-source','expression':expected}])
            self.assertEqual(binding['spec'], {'policyName':app+'-source-hold','validationActions':['Deny']})
            for resource in (policy, binding):
                self.assertEqual(resource['metadata']['annotations']['argocd.argoproj.io/sync-options'], 'Prune=false,Delete=false')



if __name__ == '__main__':
    unittest.main()
