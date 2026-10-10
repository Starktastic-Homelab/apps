#!/usr/bin/env python3
"""Read-only startup checks against actual PG18 control files; Docker fixtures only."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'scripts/postgres-retained-startup'
SERVER = 'registry-1.docker.io/bitnami/postgresql:latest@sha256:b74b23f091dcc87041bcae557d840c36458af46b955279cb13aedec4c32d7f71'
RECEIPTS = []


def docker(*args):
    return subprocess.run(['docker', *args], capture_output=True, text=True, timeout=60)


class GuardTests(unittest.TestCase):
    def test_real_control_file_and_rejected_data_are_unchanged(self):
        # Break caught: accepting empty/wrong/corrupt/recovery data, or modifying it.
        self.assertTrue((SOURCE / 'guard.sh').is_file(), 'Retained startup guard is missing')
        name = 'pg-startup-' + secrets.token_hex(6)
        volume = name + '-data'
        self.assertEqual(docker('volume', 'create', '--label', 'homelab.test=pg-retained-startup', volume).returncode, 0)
        clients = []
        def run(command, *, user='1001:1001', readonly=False, expected=None):
            client = name + '-' + str(len(clients)); clients.append(client)
            args = ['run', '--rm', '--name', client, '--network', 'none', '--memory', '256m', '--cpus', '0.5',
                    '--user', user, '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
                    '--tmpfs', '/tmp:rw,noexec,nosuid,size=16m', '-v', volume + ':/bitnami/postgresql' + (':ro' if readonly else ''),
                    '-v', str(SOURCE.resolve()) + ':/guard:ro', '--entrypoint', '/bin/bash']
            if expected is not None:
                args += ['-e', 'EXPECTED_SYSTEM_IDENTIFIER=' + expected]
            if user == '0:0':
                args += ['--cap-add', 'CHOWN', '--cap-add', 'FOWNER', '--cap-add', 'DAC_OVERRIDE']
            return docker(*args, SERVER, '-ec', command)
        def modify(command):
            result = run(command)
            self.assertEqual(result.returncode, 0, 'Synthetic data mutation failed: ' + result.stderr)
        def snapshot():
            r = run('find /bitnami/postgresql -type f -exec sha256sum {} + | sort', readonly=True, user='0:0')
            self.assertEqual(r.returncode, 0)
            return r.stdout
        cases = []
        def check(label, expected, accepted):
            before = snapshot()
            r = run('/bin/bash /guard/guard.sh', readonly=True, expected=expected)
            self.assertEqual(r.returncode == 0, accepted, label + ': ' + r.stdout + r.stderr)
            self.assertEqual(snapshot(), before, label + ': guard modified retained data')
            cases.append({'case': label, 'accepted': accepted, 'dataUnchanged': True})
        try:
            self.assertEqual(run('mkdir -p /bitnami/postgresql/data; chown 1001:1001 /bitnami/postgresql /bitnami/postgresql/data', user='0:0').returncode, 0)
            modify('. /opt/bitnami/scripts/libpostgresql.sh; . /opt/bitnami/scripts/postgresql-env.sh; postgresql_enable_nss_wrapper; /opt/bitnami/postgresql/bin/initdb -D /bitnami/postgresql/data --auth-local=trust --auth-host=reject --no-sync >/dev/null')
            result = run('/opt/bitnami/postgresql/bin/pg_controldata /bitnami/postgresql/data', readonly=True)
            self.assertEqual(result.returncode, 0)
            identity = next(line.split(':')[1].strip() for line in result.stdout.splitlines() if line.startswith('Database system identifier:'))
            check('valid', identity, True)
            for directory in ('base', 'pg_wal'):
                modify('chmod 000 /bitnami/postgresql/data/' + directory)
                check('unreadable directory ' + directory, identity, False)
                modify('chmod 400 /bitnami/postgresql/data/' + directory)
                check('unsearchable directory ' + directory, identity, False)
                modify('chmod 700 /bitnami/postgresql/data/' + directory)
            check('wrong identity', str(int(identity) + 1), False)
            for bad in ('', '0', '01', 'bad', identity + '\n', '18446744073709551616'):
                check('invalid expected identifier', bad, False)
            for marker in ('postmaster.pid', 'standby.signal', 'recovery.signal'):
                modify('printf stale > /bitnami/postgresql/data/' + marker)
                check(marker, identity, marker == 'postmaster.pid')
                modify('rm /bitnami/postgresql/data/' + marker)
            for marker in ('standby.signal', 'recovery.signal'):
                modify('ln -s /missing-synthetic-target /bitnami/postgresql/data/' + marker)
                check('dangling ' + marker, identity, False)
                modify('rm /bitnami/postgresql/data/' + marker)
            modify('mv /bitnami/postgresql/data/PG_VERSION /bitnami/postgresql/saved-version; printf "17\\n" > /bitnami/postgresql/data/PG_VERSION')
            check('wrong major', identity, False)
            modify('rm /bitnami/postgresql/data/PG_VERSION; mv /bitnami/postgresql/saved-version /bitnami/postgresql/data/PG_VERSION')
            for path in ('global/pg_control', 'PG_VERSION', 'base', 'pg_wal'):
                modify('mv /bitnami/postgresql/data/' + path + ' /bitnami/postgresql/saved')
                check('missing ' + path, identity, False)
                modify('ln -s /bitnami/postgresql/saved /bitnami/postgresql/data/' + path)
                check('symlink ' + path, identity, False)
                modify('rm /bitnami/postgresql/data/' + path + '; mv /bitnami/postgresql/saved /bitnami/postgresql/data/' + path)
            modify('chmod 000 /bitnami/postgresql/data/global/pg_control')
            check('unreadable control', identity, False)
            modify('chmod 600 /bitnami/postgresql/data/global/pg_control; cp /bitnami/postgresql/data/global/pg_control /bitnami/postgresql/saved-control; printf X | dd of=/bitnami/postgresql/data/global/pg_control bs=1 seek=100 count=1 conv=notrunc status=none')
            # pg_controldata may exit0 on CRC failure: stderr must also be checked.
            damaged = run('/opt/bitnami/postgresql/bin/pg_controldata /bitnami/postgresql/data', readonly=True)
            self.assertIn('CRC', damaged.stderr, 'Native corrupt-control fixture did not warn')
            check('control CRC mismatch', identity, False)
            modify('mv /bitnami/postgresql/saved-control /bitnami/postgresql/data/global/pg_control; cp /bitnami/postgresql/data/global/pg_control /bitnami/postgresql/saved-control; truncate -s 1024 /bitnami/postgresql/data/global/pg_control')
            check('truncated control', identity, False)
            modify('mv /bitnami/postgresql/saved-control /bitnami/postgresql/data/global/pg_control; mv /bitnami/postgresql/data /bitnami/postgresql/saved-data; mkdir /bitnami/postgresql/data')
            check('empty data', identity, False)
            modify('rmdir /bitnami/postgresql/data')
            check('missing data', identity, False)
        finally:
            for client in clients:
                if docker('container', 'inspect', client).returncode == 0:
                    self.assertEqual(docker('rm', '-f', client).returncode, 0)
            self.assertEqual(docker('volume', 'rm', volume).returncode, 0, 'Owned fixture cleanup failed')
            self.assertNotEqual(docker('volume', 'inspect', volume).returncode, 0)
            RECEIPTS.append({'volume': volume, 'cases': cases, 'cleanupVerified': True})

    @unittest.skipUnless(os.environ.get('PG_STARTUP_RENDER'), 'Set PG_STARTUP_RENDER to an actual chart render')
    def test_rendered_chart_guard_precedes_main_without_ownership_mutation(self):
        import yaml
        docs = list(yaml.safe_load_all(Path(os.environ['PG_STARTUP_RENDER']).read_text()))
        pod = next(x['spec']['template']['spec'] for x in docs if x and x['kind'] == 'StatefulSet')
        self.assertEqual([x['name'] for x in pod['initContainers']], ['verify-retained-data'])
        self.assertNotIn('fsGroup', pod['securityContext'])
        self.assertFalse(pod['automountServiceAccountToken'])
        guard = pod['initContainers'][0]
        server = next(x for x in pod['containers'] if x['name'] == 'postgresql')
        self.assertEqual(guard['image'], server['image'])
        self.assertTrue(next(x for x in guard['volumeMounts'] if x['name'] == 'data')['readOnly'])
        self.assertEqual({x['name'] for x in guard['volumeMounts']}, {'data', 'retained-startup-guard', 'retained-startup-scratch'})
        self.assertEqual({x['name'] for x in guard['env']}, {'EXPECTED_SYSTEM_IDENTIFIER'})

    def test_inactive_chart_values_use_readonly_nonroot_guard(self):
        import yaml
        self.assertTrue((SOURCE / 'values.yaml').is_file(), 'Inactive guard values are missing')
        values = yaml.safe_load((SOURCE / 'values.yaml').read_text())
        init = values['primary']['initContainers']
        self.assertEqual(len(init), 1)
        guard = init[0]
        self.assertEqual(guard['image'], SERVER)
        self.assertEqual(guard['command'], ['/bin/bash', '/retained-startup/guard.sh'])
        self.assertEqual(guard['securityContext']['runAsUser'], 1001)
        self.assertTrue(guard['securityContext']['readOnlyRootFilesystem'])
        self.assertFalse(guard['securityContext']['allowPrivilegeEscalation'])
        self.assertEqual(guard['securityContext']['capabilities']['drop'], ['ALL'])
        mounts = {m['name']: m for m in guard['volumeMounts']}
        self.assertTrue(mounts['data']['readOnly'])
        self.assertTrue(mounts['retained-startup-guard']['readOnly'])
        self.assertFalse(values['volumePermissions']['enabled'])
        self.assertEqual(guard['env'][0]['value'], 'REPLACE_WITH_VERIFIED_SYSTEM_IDENTIFIER')
        self.assertFalse((SOURCE / 'app.yaml').exists())


if __name__ == '__main__':
    if '--manifests-only' in sys.argv:
        suite = unittest.TestSuite([GuardTests('test_inactive_chart_values_use_readonly_nonroot_guard'), GuardTests('test_rendered_chart_guard_precedes_main_without_ownership_mutation')])
    elif '--native-only' in sys.argv:
        suite = unittest.TestSuite([GuardTests('test_real_control_file_and_rejected_data_are_unchanged')])
    else:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(GuardTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if os.environ.get('PG_STARTUP_TEST_RECEIPT'):
        Path(os.environ['PG_STARTUP_TEST_RECEIPT']).write_text(json.dumps({'successful': result.wasSuccessful(), 'testsRun': result.testsRun, 'image': SERVER, 'resources': RECEIPTS}, indent=2) + '\n')
    sys.exit(not result.wasSuccessful())
