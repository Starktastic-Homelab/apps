"""Host-side resource guard; can stop only the manifest's four lab identities."""
import argparse
import json
import pathlib
import subprocess
import threading
import time

GIB = 1024**3
LAB_IDS = (913, 912, 911, 910)


def owns_vm(vmid, config, manifest):
    expected = manifest.get('vms', {}).get(str(vmid))
    if vmid not in LAB_IDS or not expected:
        return False
    fields = dict(x.split('=', 1) for x in config.get('smbios1', '').split(',') if '=' in x)
    return (config.get('name') == expected['name']
            and fields.get('uuid') == expected['uuid']
            and manifest['marker'] in config.get('tags', '').split(';'))


class ShutdownGate:
    def __init__(self, oom_kills):
        self.oom_kills = oom_kills
        self.low_since = None

    def update(self, now, available, oom_kills, production_ok, monitor_age):
        if oom_kills > self.oom_kills:
            return 'host-oom'
        if production_ok is False:
            return 'production-health'
        if monitor_age > 90:
            return 'monitor-stale'
        if available >= 6*GIB:
            self.low_since = None
        elif self.low_since is None:
            self.low_since = now
        if self.low_since is not None and now-self.low_since >= 30:
            return 'host-memory'
        return None


def run(args, timeout=15):
    return subprocess.check_output(args, text=True, timeout=timeout)


def counters(text):
    return {line.split()[0].rstrip(':'): int(line.split()[1])
            for line in text.splitlines() if len(line.split()) >= 2}


def host_sample():
    memory = counters(pathlib.Path('/proc/meminfo').read_text())
    vm = counters(pathlib.Path('/proc/vmstat').read_text())
    return memory['MemAvailable']*1024, vm['oom_kill']


def guest_exec(vmid, args):
    reply = json.loads(run(['qm', 'guest', 'exec', str(vmid), '--']+args))
    if reply.get('exitcode') != 0:
        raise RuntimeError('guest monitor did not complete')
    return reply.get('out-data', '')


def production_monitor(manifest, health):
    original_oom = {}
    while True:
        try:
            nodes = json.loads(guest_exec(200, ['k3s', 'kubectl', 'get', 'nodes', '-o', 'json', '--request-timeout=5s']))['items']
            expected = manifest['production_node_uids']
            healthy = {n['metadata']['name']: n['metadata']['uid'] for n in nodes} == expected
            for node in nodes:
                conditions = {x['type']: x['status'] for x in node['status']['conditions']}
                healthy &= conditions.get('Ready') == 'True' and all(
                    conditions.get(x) == 'False' for x in ('MemoryPressure', 'DiskPressure', 'PIDPressure'))
            for vmid in (200, 201, 202):
                sample = counters(guest_exec(vmid, ['cat', '/proc/meminfo', '/proc/vmstat']))
                original_oom.setdefault(vmid, sample['oom_kill'])
                healthy &= sample['oom_kill'] == original_oom[vmid] and sample['MemAvailable'] >= 2*1024**2
            health.update(ok=healthy, sampled=time.monotonic())
        except Exception as error:
            print(json.dumps({'monitor_error': type(error).__name__}), flush=True)
            health.update(ok=False, sampled=time.monotonic())
        time.sleep(15)


def vm_config(vmid):
    path = pathlib.Path(f'/etc/pve/qemu-server/{vmid}.conf')
    if not path.exists():
        return None
    return dict(line.split(': ', 1) for line in path.read_text().split('\n[', 1)[0].splitlines() if ': ' in line)


def stop_owned(manifest):
    for vmid in LAB_IDS:
        config = vm_config(vmid)
        if config is None:
            continue
        if not owns_vm(vmid, config, manifest):
            print(json.dumps({'vmid': vmid, 'action': 'refuse-foreign-identity'}), flush=True)
            continue
        if 'stopped' in run(['qm', 'status', str(vmid)]):
            continue
        print(json.dumps({'vmid': vmid, 'action': 'shutdown'}), flush=True)
        try:
            run(['qm', 'shutdown', str(vmid), '--timeout', '10'], timeout=15)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            pass
        if 'running' in run(['qm', 'status', str(vmid)]):
            if not owns_vm(vmid, vm_config(vmid) or {}, manifest):
                raise RuntimeError('VM identity changed before forced stop')
            run(['qm', 'stop', str(vmid)], timeout=20)
        if 'stopped' not in run(['qm', 'status', str(vmid)]):
            raise RuntimeError('Lab guest failed to stop')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('manifest', type=pathlib.Path)
    parser.add_argument('--stop', action='store_true')
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    if set(manifest['vms']) != {str(x) for x in LAB_IDS}:
        raise SystemExit('Manifest must contain exactly the four lab VM IDs')
    if args.stop:
        stop_owned(manifest)
        return
    health = {'ok': None, 'sampled': time.monotonic()}
    threading.Thread(target=production_monitor, args=(manifest, health), daemon=True).start()
    gate = ShutdownGate(host_sample()[1])
    heartbeat = args.manifest.with_name('guard-status.json')
    try:
        while True:
            available, oom = host_sample()
            reason = gate.update(time.monotonic(), available, oom, health['ok'], time.monotonic()-health['sampled'])
            snapshot = {'at': time.time(), 'available': available, 'production_ok': health['ok'], 'stop_reason': reason}
            heartbeat.write_text(json.dumps(snapshot)+'\n')
            if reason:
                print(json.dumps(snapshot), flush=True)
                stop_owned(manifest)
                return
            time.sleep(5)
    except BaseException:
        stop_owned(manifest)
        raise


if __name__ == '__main__':
    main()
