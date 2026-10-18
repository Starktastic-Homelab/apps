"""Disposable exact-image synthetic qualification. No production mounts/secrets."""
import argparse
import contextlib
import hashlib
import json
import subprocess
import sys
import time
import uuid
from pathlib import Path

REDIS = 'registry-1.docker.io/bitnami/redis@sha256:f4797b37502e6db910d3653368fcfadc171ef605586917774de125ddd05b3e62'
PYTHON = 'ghcr.io/paperless-ngx/paperless-ngx:3.1.3@sha256:aa810a36942c63d4ee70d00eda7236cd3d6acfb7eb3f7987fb568ed14df8817a'
IMMICH_SERVER = 'ghcr.io/immich-app/immich-server:v3.2.2@sha256:79cc1623323d5894922686d8743b4780181428f98eecbfb58ce12c41ef02d1ea'
ROOT = Path(__file__).resolve().parent
PASSWORD = 'synthetic-fixture-only'


def docker(*args, check=True, input=None, timeout=180):
    result = subprocess.run(['docker', *map(str, args)], input=input, text=True,
                            capture_output=True, timeout=timeout)
    if check and result.returncode:
        raise RuntimeError(f'Docker {args[0]} failed: {result.stderr[-2000:]} {result.stdout[-2000:]}')
    return result


class Owned:
    def __init__(self):
        self.identity = 'redis-immich-fixture-' + uuid.uuid4().hex
        self.label = 'homelab.synthetic=' + self.identity
        self.containers = []
        self.volumes = []

    def volume(self, suffix):
        name = self.identity + '-' + suffix
        docker('volume', 'create', '--label', self.label, name)
        self.volumes.append(name)
        return name

    def run(self, image, *args, network='none', mounts=(), user='1001:0', detached=False):
        name = self.identity + '-' + str(len(self.containers))
        self.containers.append(name)
        options = ['run', '--name', name, '--label', self.label, '--network', network,
                   '--read-only', '--tmpfs', '/tmp:rw,nosuid,nodev', '--user', user]
        for mount in mounts:
            options += ['--mount', mount]
        if detached:
            options.append('-d')
        else:
            options.append('-i')
        result = docker(*options, '--entrypoint', args[0], image, *args[1:], check=False)
        if not detached:
            docker('rm', '-f', name)
        if result.returncode:
            raise RuntimeError('Synthetic container failed: ' + result.stdout[-2000:] + result.stderr[-2000:])
        return name if detached else result.stdout

    def shell(self, script, mounts=(), user='1001:0'):
        return self.run(REDIS, '/bin/bash', '-euc', script, mounts=mounts, user=user)

    def initialize(self, volume):
        self.shell('chown 1001:0 /data; chmod 0770 /data', [f'type=volume,src={volume},dst=/data'], user='0:0')

    def copy(self, source, target):
        self.shell('cd /src; tar cpf - . | (cd /dst; tar xpf -)',
                   [f'type=volume,src={source},dst=/src,readonly', f'type=volume,src={target},dst=/dst'], user='0:0')

    def server(self, volume, aof=True, expect_refusal=False):
        name = self.run(REDIS, '/opt/bitnami/redis/bin/redis-server',
                        '/opt/bitnami/redis/etc/redis.conf', '--daemonize', 'no', '--pidfile', '/tmp/redis.pid',
                        '--dir', '/data', '--bind', '127.0.0.1',
                        '--port', '6379', '--save', '', '--appendonly', 'yes' if aof else 'no',
                        '--appendfsync', 'everysec', '--requirepass', PASSWORD,
                        mounts=[f'type=volume,src={volume},dst=/data'], detached=True)
        for _ in range(60):
            result = docker('exec', '-e', 'REDISCLI_AUTH=' + PASSWORD, name,
                            '/opt/bitnami/redis/bin/redis-cli', 'PING', check=False)
            if result.stdout.strip() == 'PONG':
                if expect_refusal:
                    raise AssertionError('Corrupt AOF unexpectedly reached readiness')
                return name
            if expect_refusal:
                status = json.loads(docker('inspect', name).stdout)[0]['State']
                if not status['Running'] and status['ExitCode'] != 0:
                    return name
            time.sleep(.1)
        raise RuntimeError('Synthetic Redis did not become ready: ' + docker('logs', name).stdout[-2000:])

    def worker(self, server, volume, action):
        return json.loads(self.run(PYTHON, 'python3', '/work/fixtures.py', '--redis-worker', action,
            network='container:' + server,
            mounts=[f'type=bind,src={ROOT},dst=/work,readonly', f'type=volume,src={volume},dst=/data']))

    def bullmq(self, server, action):
        return json.loads(self.run(IMMICH_SERVER, 'node', '/work/redis_queues.cjs', action,
            network='container:' + server, mounts=[f'type=bind,src={ROOT},dst=/work,readonly']))

    def stop(self, server, abrupt=False):
        docker('kill', '--signal', 'KILL' if abrupt else 'TERM', server)
        docker('wait', server)
        if not abrupt and json.loads(docker('inspect', server).stdout)[0]['State']['ExitCode'] != 0:
            raise RuntimeError('Redis shutdown was not clean')

    def guard(self, volume):
        # Independently hash data bytes plus ownership/modes before/after.
        mounts = [f'type=bind,src={ROOT},dst=/work,readonly', f'type=volume,src={volume},dst=/data,readonly']
        def digest():
            return self.run(PYTHON, 'python3', '-c',
                "import os,hashlib,json; from pathlib import Path; "
                "print(hashlib.sha256(repr([(str(p),p.lstat().st_mode,p.lstat().st_uid,p.lstat().st_gid,"
                "os.readlink(p) if p.is_symlink() else hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else '' ) "
                "for p in sorted(Path('/data').rglob('*'))]).encode()).hexdigest())", mounts=mounts, user='0:0').strip()
        before = digest()
        output = self.run(REDIS, '/bin/bash', '-c', 'bash /work/redis-guard.sh >/tmp/guard.log 2>&1; echo $?', mounts=mounts)
        after = digest()
        if before != after:
            raise RuntimeError('Guard mutated retained data')
        self.last_guard_output = output
        return output.strip().splitlines()[-1] == '0'

    def close(self):
        existing = set(docker('ps', '-a', '--filter', 'label=' + self.label, '--format', '{{.Names}}').stdout.splitlines())
        for name in reversed(self.containers):
            if name not in existing:
                continue
            result = docker('inspect', name, check=False)
            if result.returncode == 0:
                labels = json.loads(result.stdout)[0]['Config'].get('Labels', {})
                if labels.get('homelab.synthetic') != self.identity:
                    raise RuntimeError('Container ownership changed')
                docker('rm', '-f', name)
        for name in reversed(self.volumes):
            labels = json.loads(docker('volume', 'inspect', name).stdout)[0].get('Labels', {})
            if labels.get('homelab.synthetic') != self.identity:
                raise RuntimeError('Volume ownership changed')
            docker('volume', 'rm', name)
        if docker('ps', '-aq', '--filter', 'label=' + self.label).stdout.strip():
            raise RuntimeError('Fixture container cleanup incomplete')
        if docker('volume', 'ls', '-q', '--filter', 'label=' + self.label).stdout.strip():
            raise RuntimeError('Fixture volume cleanup incomplete')


def redis_worker(action):
    import redis
    import redis_checkpoint as state
    assert redis.__version__ == '5.2.1'
    client = redis.Redis(host='127.0.0.1', password=PASSWORD, decode_responses=False, single_connection_client=True)
    checkpoint = Path('/data/checkpoint.synthetic.json')
    if action == 'celery-seed':
        import os
        from kombu import Connection
        connection = Connection('redis://:' + PASSWORD + '@127.0.0.1:6379/4')
        queue = connection.SimpleQueue('synthetic-retained-celery')
        queue.put({'id': 'active', 'payload': '\u0000שלום'})
        queue.put({'id': 'pending', 'payload': 'pending'})
        message = queue.get(block=False)
        assert message.payload['id'] == 'active'
        client.execute_command('SELECT', 4)
        assert client.hlen('unacked') == 1
        print(json.dumps({'seeded': True}), flush=True)
        # Simulate a lost worker; normal interpreter cleanup would requeue it.
        os._exit(0)
    if action == 'celery-recover':
        from kombu import Connection
        with Connection('redis://:' + PASSWORD + '@127.0.0.1:6379/4', transport_options={'visibility_timeout': 0}) as connection:
            queue = connection.SimpleQueue('synthetic-retained-celery')
            queue.channel.qos.restore_visible(num=100, interval=1)
            recovered = {}
            for _ in range(2):
                message = queue.get(block=False)
                recovered[message.payload['id']] = message.payload['payload']
                message.ack()
            assert recovered == {'active': '\u0000שלום', 'pending': 'pending'}
            queue.close()
        return {'recovered': True}
    if action == 'checkpoint':
        checkpoint.write_text(state.dumps(state.capture(client, state.source_time_ms(client))))
        return {'captured': True}
    if action == 'seed-stale':
        client.set(b'historical-only', b'not-current-memory')
        client.bgrewriteaof()
        wait_persistence(client)
        client.config_set('appendonly', 'no')
        client.delete(b'historical-only')
        client.set(b'\xff\x00job', b'\x00payload\xff')
        client.rpush(b'list', b'a', b'a', b'\xff')
        client.sadd(b'set', b'b', b'a')
        client.hset(b'hash', mapping={b'\xff': b'\x00', b'field': b'value'})
        client.zadd(b'zset', {b'\xff': 1.25, b'a': -2.5})
        client.xadd(b'stream', {b'binary': b'\xff\x00'}, id='1-0')
        client.xgroup_create(b'stream', b'workers', id='0-0')
        client.xreadgroup(b'workers', b'consumer-1', {b'stream': b'>'}, count=1)
        client.set(b'expires', b'cache', px=600000)
        client.execute_command('SELECT', 4)
        client.rpush(b'celery-shaped-pending', b'\xff\x00message')
        client.execute_command('SELECT', 0)
        before = state.capture(client, state.source_time_ms(client))
        # Duplicate SCAN entries must not duplicate a logical record.
        original_scan = client.scan_iter
        client.scan_iter = lambda **kw: (k for key in original_scan(**kw) for k in (key, key))
        duplicate = state.capture(client, state.source_time_ms(client))
        state.compare(before, duplicate, state.source_time_ms(client))
        client.scan_iter = original_scan
        checkpoint.write_text(state.dumps(before))
        # Native hash-field expiry is explicitly unsupported, never discarded.
        client.hset(b'expiring-fields', b'f', b'v')
        client.execute_command('HPEXPIRE', b'expiring-fields', 600000, 'FIELDS', 1, b'f')
        try:
            state.capture(client, state.source_time_ms(client))
        except ValueError:
            pass
        else:
            raise AssertionError('Hash-field TTL was silently accepted')
        client.delete(b'expiring-fields')
        client.execute_command('JSON.SET', b'unsupported-module', '$', '{"key":1}')
        try:
            state.capture(client, state.source_time_ms(client))
        except ValueError:
            pass
        else:
            raise AssertionError('Unknown module type was silently accepted')
        client.delete(b'unsupported-module')
        return {'seeded': True, 'duplicate_scan_preserved': True, 'field_ttl_refused': True}
    if action == 'compare':
        before = state.loads(checkpoint.read_text())
        actual = state.capture(client, state.source_time_ms(client))
        return state.compare(before, actual, state.source_time_ms(client))
    if action == 'enable-aof':
        client.config_set('appendonly', 'yes')
        wait_persistence(client)
        return {'enabled': True}
    raise ValueError('Unknown fixture action')


def wait_persistence(client):
    for _ in range(300):
        info = client.info('persistence')
        if not info['aof_rewrite_in_progress'] and not info['aof_rewrite_scheduled']:
            if not info['aof_enabled'] or info['aof_last_bgrewrite_status'] != 'ok' or info['aof_last_write_status'] != 'ok':
                raise RuntimeError('AOF persistence unhealthy')
            return
        time.sleep(.1)
    raise RuntimeError('AOF rewrite timed out')


def run_redis():
    owned = Owned()
    result = {}
    try:
        source, stale, memory, target = [owned.volume(n) for n in ('source', 'stale', 'memory', 'target')]
        owned.initialize(source)
        server = owned.server(source)
        owned.worker(server, source, 'seed-stale')
        owned.worker(server, source, 'celery-seed')
        owned.bullmq(server, 'seed')
        owned.worker(server, source, 'checkpoint')
        owned.copy(source, stale)
        disk = owned.server(stale)
        try:
            owned.worker(disk, stale, 'compare')
        except RuntimeError as exc:
            if 'Unexpected key' not in str(exc) and 'Unexplained missing key' not in str(exc):
                raise
            result['stale_disk_rejected'] = True
        else:
            raise AssertionError('Historical AOF was mistaken for current memory')
        owned.stop(disk)
        docker('exec', '-e', 'REDISCLI_AUTH=' + PASSWORD, server, '/opt/bitnami/redis/bin/redis-cli', '--rdb', '/data/memory.synthetic.rdb')
        docker('exec', server, '/opt/bitnami/redis/bin/redis-check-rdb', '/data/memory.synthetic.rdb')
        owned.initialize(memory)
        owned.shell('cp -p /src/memory.synthetic.rdb /data/dump.rdb; cp -p /src/checkpoint.synthetic.json /data/',
                    [f'type=volume,src={source},dst=/src,readonly', f'type=volume,src={memory},dst=/data'])
        restored = owned.server(memory, aof=False)
        owned.worker(restored, memory, 'compare')
        result['memory_restore_preserved'] = True
        owned.stop(restored)
        owned.worker(server, source, 'enable-aof')
        owned.stop(server)
        owned.shell("printf 'homelab/redis/data/v1\\n' > /data/.homelab-redis-data", [f'type=volume,src={source},dst=/data'])
        owned.copy(source, target)
        assert owned.guard(target), 'Valid retained state refused: ' + owned.last_guard_output
        current = owned.server(target)
        owned.worker(current, target, 'compare')
        owned.stop(current, abrupt=True)
        assert owned.guard(target), 'Complete AOF after abrupt termination refused'
        current = owned.server(target)
        owned.worker(current, target, 'compare')
        owned.stop(current)
        # Recover through the native app clients only after the final full-state
        # comparison. These writes are confined to this synthetic target.
        current = owned.server(target)
        owned.worker(current, target, 'celery-recover')
        owned.bullmq(current, 'recover')
        owned.stop(current)
        result.update(aof_restore_preserved=True, guard_read_only=True, abrupt_recovery_preserved=True,
                      celery_pending_recovered=True, bullmq_pending_recovered=True)
        # Corrupt and missing media must refuse without touching any byte.
        for case, mutation in {
            'missing-marker': 'rm /data/.homelab-redis-data',
            'wrong-marker': "printf 'other\\n' > /data/.homelab-redis-data",
            'linked-marker': 'mv /data/.homelab-redis-data /data/marker; ln -s marker /data/.homelab-redis-data',
            'missing-manifest': 'rm /data/appendonlydir/appendonly.aof.manifest',
            'path-escape': "printf 'file ../../escape seq 1 type b\\n' > /data/appendonlydir/appendonly.aof.manifest",
            'missing-base': 'rm /data/appendonlydir/*.base.rdb',
            'unreadable-base': 'chmod 000 /data/appendonlydir/*.base.rdb',
            'linked-increment': 'files=(/data/appendonlydir/*.incr.aof); file=${files[0]}; mv "$file" /data/increment; ln -s /data/increment "$file"',
            'corrupt-base': "printf 'corrupt' > /data/appendonlydir/*.base.rdb",
        }.items():
            volume = owned.volume(case)
            owned.copy(target, volume)
            owned.shell(mutation, [f'type=volume,src={volume},dst=/data'])
            assert not owned.guard(volume), case + ' unexpectedly accepted'
        empty = owned.volume('empty')
        owned.initialize(empty)
        assert not owned.guard(empty), 'Empty disk accepted'
        empty_server = owned.server(empty)
        owned.stop(empty_server)
        owned.shell("printf 'homelab/redis/data/v1\\n' > /data/.homelab-redis-data; test ! -s /data/appendonlydir/*.incr.aof",
                    [f'type=volume,src={empty},dst=/data'])
        assert owned.guard(empty), 'Valid empty dataset / zero-byte increment refused'
        result['negative_cases_refused'] = 10
        result['empty_dataset_preserved'] = True
    finally:
        owned.close()
    result['cleanup_verified'] = True
    return result



def run_redis_case(case):
    owned = Owned()
    try:
        volume = owned.volume(case)
        owned.initialize(volume)
        server = owned.server(volume)
        if case in ('torn-tail', 'corrupt-increment'):
            docker('exec', '-e', 'REDISCLI_AUTH=' + PASSWORD, server, '/opt/bitnami/redis/bin/redis-cli', 'SET', 'accepted-complete', 'preserved-complete')
        owned.stop(server)
        owned.shell("printf 'homelab/redis/data/v1\\n' > /data/.homelab-redis-data", [f'type=volume,src={volume},dst=/data'])
        if case == 'history':
            owned.shell("printf 'file appendonly.aof.42.incr.aof seq 42 type h\\n' >> /data/appendonlydir/appendonly.aof.manifest", [f'type=volume,src={volume},dst=/data'])
            accepted = owned.guard(volume)
            result = {'accepted': accepted}
        elif case == 'torn-tail':
            owned.shell("printf '*3\\r\\n$3\\r\\nSET\\r\\n$6\\r\\nbroken\\r\\n$8\\r\\npar' >> /data/appendonlydir/*.incr.aof", [f'type=volume,src={volume},dst=/data'])
            refused = not owned.guard(volume)
            before = int(owned.shell('stat -c %s /data/appendonlydir/*.incr.aof', [f'type=volume,src={volume},dst=/data,readonly']).strip())
            recovered = owned.server(volume)
            value = docker('exec', '-e', 'REDISCLI_AUTH=' + PASSWORD, recovered, '/opt/bitnami/redis/bin/redis-cli', 'GET', 'accepted-complete').stdout.strip()
            missing = docker('exec', '-e', 'REDISCLI_AUTH=' + PASSWORD, recovered, '/opt/bitnami/redis/bin/redis-cli', 'EXISTS', 'broken').stdout.strip()
            assert value == 'preserved-complete' and missing == '0'
            owned.stop(recovered)
            after = int(owned.shell('stat -c %s /data/appendonlydir/*.incr.aof', [f'type=volume,src={volume},dst=/data,readonly']).strip())
            assert after < before, 'Stock Redis did not truncate the synthetic incomplete tail'
            assert owned.guard(volume), 'Recovered native AOF failed integrity check'
            result = {'guard_refused': refused, 'guard_read_only': True, 'stock_recovery_preserved': True,
                      'native_truncates': True, 'before_bytes': before, 'after_bytes': after}
        elif case == 'corrupt-increment':
            owned.shell("printf 'not-resp\\r\\n' > /data/appendonlydir/*.incr.aof", [f'type=volume,src={volume},dst=/data'])
            owned.guard(volume)
            failed = owned.server(volume, expect_refusal=True)
            status = json.loads(docker('inspect', failed).stdout)[0]['State']
            result = {'native_refused': not status['Running'] and status['ExitCode'] != 0, 'guard_read_only': True}
        else:
            raise ValueError('Unknown native Redis case')
    finally:
        owned.close()
    result['cleanup_verified'] = True
    return result

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--redis-worker')
    parser.add_argument('--app', choices=['redis', 'immich'])
    parser.add_argument('--receipt', type=Path)
    args = parser.parse_args()
    if args.redis_worker:
        print(json.dumps(redis_worker(args.redis_worker)))
    else:
        if args.app != 'redis':
            parser.error('Select an implemented app fixture')
        receipt = run_redis()
        if args.receipt:
            args.receipt.write_text(json.dumps(receipt, indent=2) + '\n')
        print(json.dumps(receipt))
