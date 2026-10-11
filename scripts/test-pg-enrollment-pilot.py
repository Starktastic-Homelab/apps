#!/usr/bin/env python3
"""Exercise the canary's real SQL on an isolated, bounded PG18 server."""
import pathlib
import subprocess
import time
import uuid

import yaml


def run(args, data=None, check=True):
    result = subprocess.run(args, input=data, text=True, capture_output=True, timeout=45)
    if check and result.returncode:
        raise AssertionError('Synthetic canary command failed; private output suppressed')
    return result


def main():
    path = pathlib.Path('services/operations/postgres-enrollment-pilot/manifests/canary.yaml')
    assert path.exists(), 'Canary SQL not integrated yet'
    sql = yaml.safe_load(path.read_text())['data']['canary.sql']
    command = yaml.safe_load(pathlib.Path('services/operations/postgres-enrollment-pilot/values.yaml').read_text())['controllers']['main']['containers']['main']['command']
    image = yaml.safe_load(pathlib.Path('scripts/postgres-enrollment/job.yaml').read_text())['spec']['template']['spec']['containers'][0]['image']
    name = 'pg-enrollment-canary-' + uuid.uuid4().hex[:16]
    created = False
    try:
        run(['docker', 'run', '-d', '--name', name, '--network', 'none',
             '--memory', '256m', '--cpus', '1', '--pids-limit', '128',
             '--log-opt', 'max-size=1m', '--log-opt', 'max-file=1',
             '--tmpfs', '/var/lib/postgresql:rw,size=128m',
             '-e', 'PGDATA=/var/lib/postgresql/data',
             '-e', 'POSTGRES_HOST_AUTH_METHOD=reject',
             '-e', 'POSTGRES_PASSWORD=synthetic-local-only', image])
        created = True
        for _ in range(60):
            # The entrypoint's temporary initialization server listens only on
            # the Unix socket. Wait for the final TCP server before SQL.
            if run(['docker', 'exec', name, 'pg_isready', '-h', '127.0.0.1', '-U', 'postgres'], check=False).returncode == 0:
                break
            time.sleep(1)
        else:
            raise AssertionError('Synthetic PG18 startup timed out')
        admin = ['docker', 'exec', '-i', name, 'psql', '-XqAt', '-v', 'ON_ERROR_STOP=1', '-U', 'postgres', '-d', 'postgres']
        run(admin, 'CREATE ROLE homelab_enrollment_pilot LOGIN;\nCREATE DATABASE homelab_enrollment_pilot OWNER homelab_enrollment_pilot;\n')
        client = ['docker', 'exec', '-i', name, 'psql', '-XqAt', '-v', 'ON_ERROR_STOP=1', '-U', 'homelab_enrollment_pilot', '-d', 'homelab_enrollment_pilot']
        run(client, sql)
        run(client, sql)
        assert run(client, 'SELECT count(*), min(payload) FROM public.enrollment_canary;').stdout.strip() == '1|pg-enrollment-pilot-v1'
        # emptyDir persists across main-container restarts. A previous readiness
        # marker must disappear while a repeat SQL validation waits on a lock.
        run(['docker', 'exec', '-i', name, 'sh', '-ec',
             'mkdir -p /credentials /canary; printf synthetic-local-only > /credentials/password; cat > /canary/canary.sql; touch /tmp/enrollment-ready'], sql)
        lock = subprocess.Popen(client, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True)
        lock.stdin.write('BEGIN; LOCK TABLE public.enrollment_canary IN ACCESS EXCLUSIVE MODE; SELECT pg_sleep(5); COMMIT;\n')
        lock.stdin.close()
        admin_db = ['docker', 'exec', '-i', name, 'psql', '-XqAt', '-v', 'ON_ERROR_STOP=1', '-U', 'postgres', '-d', 'homelab_enrollment_pilot']
        for _ in range(30):
            if run(admin_db, "SELECT count(*) FROM pg_locks WHERE relation='public.enrollment_canary'::regclass AND mode='AccessExclusiveLock' AND granted;").stdout.strip() == '1':
                break
            time.sleep(0.1)
        else:
            raise AssertionError('Synthetic sentinel lock not acquired')
        run(['docker', 'exec', '-d', '-e', 'PGHOST=', '-e', 'PGUSER=homelab_enrollment_pilot', '-e', 'PGDATABASE=homelab_enrollment_pilot', name, *command])
        time.sleep(0.5)
        assert run(['docker', 'exec', name, 'test', '-f', '/tmp/enrollment-ready'], check=False).returncode != 0, 'Stale readiness survived a blocked restart'
        assert lock.wait(timeout=15) == 0
        for _ in range(30):
            if run(['docker', 'exec', name, 'test', '-f', '/tmp/enrollment-ready'], check=False).returncode == 0:
                break
            time.sleep(0.1)
        else:
            raise AssertionError('Successful repeat verification did not restore readiness')
        run(client, "UPDATE public.enrollment_canary SET payload='unexpected';")
        assert run(client, sql, check=False).returncode != 0, 'Canary overwrote or accepted a mismatched sentinel'
        assert run(client, 'SELECT payload FROM public.enrollment_canary;').stdout.strip() == 'unexpected'
        print('PASS: first/repeat start, readiness reset during blocked restart and mismatched sentinel rejection; one retained row.')
    finally:
        if created:
            run(['docker', 'rm', '-f', name])


if __name__ == '__main__':
    main()
