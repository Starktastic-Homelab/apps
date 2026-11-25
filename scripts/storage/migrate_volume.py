#!/usr/bin/env python3
"""Migration-only copy tool for retained-volume cutovers (ADR 0017, Task 2.5). Deleted in Task 5.9.

  migrate_volume.py precheck <id> [--direction forward|reverse]
  migrate_volume.py render <id> --direction forward|reverse --out <dir>
  migrate_volume.py verify-teardown <id>

The source is the binding PV whose handle is vm-9999-<id>.raw (the rule id == x). Nothing outside the migration
imports, calls or renders this file, and no workflow runs it. It needs kubectl, gh and the lock root on one tool
host (D23, settled in Task 4.0 Step 7). It prints no Secret, token, nonce or kubeconfig content.
"""
import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
INVENTORY = 'infrastructure/base-configs/files/retained-volumes.json'
BINDINGS = 'infrastructure/base-configs/templates'
GLOBALS = 'templates/globals.yaml'
LOCK_ROOT = '/var/lib/homelab-maintenance'

LABEL = 'homelab.starktastic.net/migration'
STEP = 'homelab.starktastic.net/migration-step'  # gate.yaml holds two halves applied one after the other
SYNC = {'argocd.argoproj.io/sync-options': 'Prune=false,Delete=false'}
PROXMOX = 'csi.proxmox.sinextra.dev'
NODE_MANUAL = 'org.democratic-csi.node-manual'
# The copy and fsck image is the democratic-csi node plugin image, read from its values at render time (Renovate
# bumps it there), because the python guard image ships no e2fsprogs. It has dd, cmp, blockdev, e2fsck, tune2fs,
# dumpe2fs, resize2fs and python3.
CSI_VALUES = 'infrastructure/system/democratic-csi/manifests/values.yaml'
PY_IMAGE = 'python@sha256:8c9a3bf2d6dea60d60a2ae2a07c2b2fb1e7d8daed64b146b6792c74ae0d62ac4'
REBUILDS = {'packer': 'build.yml', 'terraform': 'apply.yml', 'ansible': 'deploy.yml'}
ACTIVE = {'queued', 'in_progress', 'waiting', 'requested', 'pending'}
TEARDOWN_TIMEOUT = 300
UNITS = {'Ki': 1 << 10, 'Mi': 1 << 20, 'Gi': 1 << 30, 'Ti': 1 << 40}


def old_handle(i):
    return f'homelab//k3s-block/9999/vm-9999-{i}.raw'


def to_bytes(q):
    m = re.fullmatch(r'([1-9][0-9]*)(Ki|Mi|Gi|Ti)', str(q))
    if not m:
        raise ValueError(f'unsupported quantity {q!r}')
    return int(m.group(1)) * UNITS[m.group(2)]


# ---------- repo inputs ----------

def load_entry(root, i):
    return next((e for e in json.loads((root / INVENTORY).read_text()) if e.get('id') == i), None)


def find_bindings(root, i):
    """Every binding PV in git whose handle is vm-9999-<i>.raw (files containing '{{' are templates, skipped)."""
    found = []
    for f in sorted((root / BINDINGS).rglob('*.y*ml')):
        text = f.read_text()
        if '{{' in text:
            continue
        for d in yaml.safe_load_all(text):
            if isinstance(d, dict) and d.get('kind') == 'PersistentVolume' and \
                    (d.get('spec', {}).get('csi') or {}).get('volumeHandle') == old_handle(i):
                found.append(d)
    return found


def copy_image(root):
    try:
        img = yaml.safe_load((root / CSI_VALUES).read_text())['node']['driver']['image']
        return f"{img['registry']}:{img['tag']}"
    except (OSError, yaml.YAMLError, KeyError, TypeError) as e:
        raise ValueError(f'cannot read node plugin image from {CSI_VALUES}: {e!r}')


def storage_target(root):
    n = yaml.safe_load((root / GLOBALS).read_text())['global']['network']
    return n['storagePortal'], n['storageTargetIqnPrefix']


# ---------- live helpers ----------

def by_kind(live, kind):
    return [o for o in live if o.get('kind') == kind]


def pv_handle(pv):
    return (pv.get('spec', {}).get('csi') or {}).get('volumeHandle')


def pod_spec(o):
    s = o.get('spec', {})
    if o['kind'] == 'Pod':
        return s
    if o['kind'] == 'CronJob':
        return s.get('jobTemplate', {}).get('spec', {}).get('template', {}).get('spec', {})
    return s.get('template', {}).get('spec', {})


def claim_volumes(o, claims):
    """Names of o's pod volumes that resolve to a claim in claims ({(namespace, name)})."""
    ns, spec = o['metadata'].get('namespace'), pod_spec(o)
    names = {v['name'] for v in spec.get('volumes', [])
             if (ns, (v.get('persistentVolumeClaim') or {}).get('claimName')) in claims}
    if o['kind'] == 'StatefulSet':  # a volumeClaimTemplates name t derives claims t-<sts>-<ordinal>
        sts = o['metadata']['name']
        for t in o['spec'].get('volumeClaimTemplates', []):
            n = t['metadata']['name']
            if any(c_ns == ns and re.fullmatch(re.escape(f'{n}-{sts}-') + r'[0-9]+', c) for c_ns, c in claims):
                names.add(n)
    return names


def pvc_volumes(o):
    """Names of every PVC-backed volume of o's pod template, volumeClaimTemplates included."""
    names = {v['name'] for v in pod_spec(o).get('volumes', []) if v.get('persistentVolumeClaim')}
    if o['kind'] == 'StatefulSet':
        names |= {t['metadata']['name'] for t in o['spec'].get('volumeClaimTemplates', [])}
    return names


def finished(job):
    return any(c.get('type') in ('Complete', 'Failed') and c.get('status') == 'True'
               for c in job.get('status', {}).get('conditions', []))


def writers(live, handles):
    """Everything that can write a volume carrying one of handles: matched by handle, never by a PV name alone."""
    pvs = [p for p in by_kind(live, 'PersistentVolume') if pv_handle(p) in handles]
    names = {p['metadata']['name'] for p in pvs}
    claims = {(c.get('namespace'), c.get('name')) for p in pvs for c in [p['spec'].get('claimRef') or {}] if c}
    claims |= {(c['metadata'].get('namespace'), c['metadata']['name']) for c in by_kind(live, 'PersistentVolumeClaim')
               if c.get('spec', {}).get('volumeName') in names}
    found = []
    for o in live:
        k, n = o.get('kind'), f"{o['metadata'].get('namespace')}/{o['metadata']['name']}"
        if k == 'VolumeAttachment':
            pv = o.get('spec', {}).get('source', {}).get('persistentVolumeName')
            if pv in names:
                found.append(f"VolumeAttachment {o['metadata']['name']} names PV {pv}")
            continue
        if k not in ('Pod', 'Job', 'CronJob', 'Deployment', 'StatefulSet') or not claim_volumes(o, claims):
            continue
        if k == 'Pod' and o.get('status', {}).get('phase') not in ('Succeeded', 'Failed'):
            found.append(f"Pod {n} ({o.get('status', {}).get('phase')})")
        elif k == 'Job' and not finished(o):
            found.append(f'Job {n} unfinished')
        elif k == 'CronJob' and not o['spec'].get('suspend'):
            found.append(f'CronJob {n} not suspended')
        elif k in ('Deployment', 'StatefulSet') and o['spec'].get('replicas', 1) > 0:
            found.append(f"{k} {n} replicas {o['spec'].get('replicas', 1)}")
    return found


# ---------- decide ----------

def lock_ids(lock):
    parts = str((lock or {}).get('operation', '')).split(':')
    return set(parts[1:]) if parts[0] == 'storage-cutover' and 2 <= len(parts) <= 3 else set()


def expected_handles(i, direction):
    src, dst = (old_handle(i), i) if direction == 'forward' else (i, old_handle(i))
    return {f'migrate-src-{i}': src, f'migrate-dst-{i}': dst, f'migrate-gate-{i}': i, f'migrate-guard-{i}': i}


def decide(i, entry, bindings, live, ci, lock, clone, direction):
    """Reasons ('<code>: <detail>') the copy of <i> must not run, in the order stale-clone, no-entry, handle, size,
    writer, rebuild, lock."""
    r = []
    if clone['head'] != clone['origin_main'] or clone['dirty']:
        r.append(f"stale-clone: HEAD {clone['head']} origin/main {clone['origin_main']} dirty {clone['dirty']}")
    if entry is None or entry.get('origin') != 'migrated':
        r.append(f'no-entry: {i} is not a migrated inventory entry')
    elif direction == 'forward' and 'copied' in entry:
        r.append(f"no-entry: {i} already copied {entry['copied']}")
    pvs = {p['metadata']['name']: p for p in by_kind(live, 'PersistentVolume')}
    if len(bindings) != 1:
        r.append(f'handle: {len(bindings)} binding PVs carry {old_handle(i)}')
    else:
        b = bindings[0]
        lp = pvs.get(b['metadata']['name'])
        if lp and (pv_handle(lp), (lp['spec'].get('csi') or {}).get('driver'), lp['spec'].get('capacity', {}).get('storage')) != \
                (old_handle(i), PROXMOX, b['spec']['capacity']['storage']):
            r.append(f"handle: live PV {b['metadata']['name']} differs from git in handle, driver or capacity")
    rp = pvs.get(i)
    if not rp or pv_handle(rp) != i or (rp['spec'].get('csi') or {}).get('driver') != NODE_MANUAL:
        r.append(f'handle: rendered PV {i} is missing or not node-manual with handle {i}')
    for name, want in expected_handles(i, direction).items():
        if name in pvs and pv_handle(pvs[name]) != want:
            r.append(f'handle: PV {name} has handle {pv_handle(pvs[name])}, {direction} needs {want}')
    if entry is not None and len(bindings) == 1:
        try:
            inv, cap = to_bytes(entry['size']), to_bytes(bindings[0]['spec']['capacity']['storage'])
        except ValueError as e:
            inv = cap = None
            r.append(f'size: {e}')
        if inv is not None and (direction == 'forward' and inv < cap) or (direction == 'reverse' and cap < inv):
            r.append(f"size: {direction} inventory {entry['size']} vs binding {bindings[0]['spec']['capacity']['storage']}")
    r += [f'writer: {w}' for w in writers(live, {old_handle(i), i})]
    for repo, wf in REBUILDS.items():
        if any(run.get('status') in ACTIVE for run in ci['runs'].get(repo, [])):
            r.append(f'rebuild: {repo} {wf} is running or queued')
        r += [f"rebuild: {repo} PR #{p.get('number')} has auto-merge" for p in ci['prs'].get(repo, [])
              if p.get('autoMergeRequest')]
    if i not in lock_ids(lock):
        r.append(f"lock: operation is {(lock or {}).get('operation')!r}, need storage-cutover:{i}")
    return r


# ---------- render ----------

def meta(name, i, step=None, ns=None, sync=False):
    m = {'name': name, 'labels': {LABEL: i, **({STEP: step} if step else {})}}
    if ns:
        m['namespace'] = ns
    if sync:
        m['annotations'] = dict(SYNC)
    return m


def node_manual_csi(i, target):
    portal, prefix = target
    return {'driver': NODE_MANUAL, 'volumeHandle': i, 'volumeAttributes': {
        'portal': portal, 'iqn': prefix + i, 'lun': '0',
        'node_attach_driver': 'iscsi', 'provisioner_driver': 'node-manual'}}


def pair(name, i, ns, csi, size, mode='Block', step=None, node_affinity=None, mount_options=None):
    pv = {'apiVersion': 'v1', 'kind': 'PersistentVolume', 'metadata': meta(name, i, step, sync=True), 'spec': {
        'capacity': {'storage': size}, 'accessModes': ['ReadWriteOncePod'], 'volumeMode': mode,
        'persistentVolumeReclaimPolicy': 'Retain', 'storageClassName': '',
        'claimRef': {'namespace': ns, 'name': name}, 'csi': csi}}
    if node_affinity:
        pv['spec']['nodeAffinity'] = node_affinity
    if mount_options:
        pv['spec']['mountOptions'] = mount_options
    pvc = {'apiVersion': 'v1', 'kind': 'PersistentVolumeClaim', 'metadata': meta(name, i, step, ns, sync=True),
           'spec': {'accessModes': ['ReadWriteOncePod'], 'volumeMode': mode, 'storageClassName': '',
                    'volumeName': name, 'resources': {'requests': {'storage': size}}}}
    return [pv, pvc]


def proxmox_csi(b):
    return {'driver': PROXMOX, 'volumeHandle': b['spec']['csi']['volumeHandle'],
            'volumeAttributes': dict(b['spec']['csi'].get('volumeAttributes', {}))}


def hardened(user=None):
    sc = {'allowPrivilegeEscalation': False, 'capabilities': {'drop': ['ALL']}, 'readOnlyRootFilesystem': True,
          'seccompProfile': {'type': 'RuntimeDefault'}}
    return {**sc, 'runAsUser': 0} if user is None else {**sc, 'runAsNonRoot': True, 'runAsUser': user}


def job(name, i, ns, pod, step=None):
    pod = {'restartPolicy': 'Never', 'nodeSelector': {'node-role.kubernetes.io/worker': 'true'}, **pod}
    return {'apiVersion': 'batch/v1', 'kind': 'Job', 'metadata': meta(name, i, step, ns), 'spec': {
        'backoffLimit': 0, 'activeDeadlineSeconds': 14400,
        'template': {'metadata': {'labels': {LABEL: i, **({STEP: step} if step else {})}}, 'spec': pod}}}


def script_cm(i, ns, step=None):
    return {'apiVersion': 'v1', 'kind': 'ConfigMap', 'metadata': meta(f'migrate-{i}', i, step, ns),
            'data': {'copy_volume.sh': (HERE / 'copy_volume.sh').read_text()}}


def copy_pod(i, args, devices, image):
    """devices: {device name under /dev: claim}."""
    return {'containers': [{
        'name': 'copy', 'image': image, 'command': ['sh', '/migrate/copy_volume.sh', *args],
        'securityContext': hardened(),
        'volumeDevices': [{'name': d, 'devicePath': f'/dev/{d}'} for d in devices],
        'volumeMounts': [{'name': 'script', 'mountPath': '/migrate', 'readOnly': True}]}],
        'volumes': [{'name': 'script', 'configMap': {'name': f'migrate-{i}'}}] +
                   [{'name': d, 'persistentVolumeClaim': {'claimName': c}} for d, c in devices.items()]}


def render_copy(i, entry, b, target, direction, image):
    ns, old = entry['namespace'], [proxmox_csi(b), b['spec']['capacity']['storage'], b['spec'].get('nodeAffinity')]
    new = [node_manual_csi(i, target), entry['size'], None]
    (s_csi, s_size, s_aff), (d_csi, d_size, d_aff) = (old, new) if direction == 'forward' else (new, old)
    pairs = pair(f'migrate-src-{i}', i, ns, s_csi, s_size, node_affinity=s_aff) + \
        pair(f'migrate-dst-{i}', i, ns, d_csi, d_size, node_affinity=d_aff)
    jobs = [script_cm(i, ns), job(f'migrate-{i}', i, ns, copy_pod(
        i, [direction, str(to_bytes(entry['size']))], {'migrate-src': f'migrate-src-{i}', 'migrate-dst': f'migrate-dst-{i}'}, image))]
    return pairs, jobs


def guard_template(live, entry):
    """(template object, claim volume name) of the one live pod template on the entry's new claim, else a reason."""
    claims = {(entry['namespace'], entry['claim'])}
    hits = [(o, claim_volumes(o, claims)) for o in live
            if o.get('kind') in ('Deployment', 'StatefulSet', 'CronJob', 'Job') and claim_volumes(o, claims)]
    if len(hits) != 1:
        return None, f"gate: {len(hits)} pod templates reference {entry['namespace']}/{entry['claim']}"
    o, vols = hits[0]
    if len(vols) != 1:
        return None, f"gate: {len(vols)} volumes of {o['metadata']['name']} name the claim"
    return (o, next(iter(vols))), None


def render_gate(i, entry, target, live, image):
    """gate.yaml objects, or (None, reason)."""
    found, why = guard_template(live, entry)
    if why:
        return None, why
    o, vol = found
    spec = pod_spec(o)
    inits = [c for c in spec.get('initContainers', []) if any(m['name'] == vol for m in c.get('volumeMounts', []))]
    if len(inits) != 1:
        return None, f"gate: {len(inits)} init containers of {o['metadata']['name']} mount the claim"
    guard = inits[0]
    others = {m['name'] for m in guard.get('volumeMounts', [])} & (pvc_volumes(o) - {vol})
    if others:
        return None, f"gate: guard init container {guard['name']} also mounts PVC volumes {sorted(others)}"
    ns, gate, gv = entry['namespace'], f'migrate-gate-{i}', f'migrate-guard-{i}'
    mounted = {m['name'] for m in guard.get('volumeMounts', [])}
    volumes = [v for v in spec.get('volumes', []) if v['name'] in mounted and v['name'] != vol]
    volumes.append({'name': vol, 'persistentVolumeClaim': {'claimName': gv, 'readOnly': True}})
    claim_mounts = [dict(m, readOnly=True) for m in guard['volumeMounts'] if m['name'] == vol]
    ro_check = ('import sys\nmounts = [l.split() for l in open("/proc/self/mounts")]\n'
                'for p in sys.argv[1:]:\n'
                '    if not any(f[1] == p and "ro" in f[3].split(",") for f in mounts):\n'
                '        sys.exit("refused: " + p + " is not mounted ro")\n'
                'print("mount-ro-ok", *sys.argv[1:])\n')
    guard_pod = {
        'initContainers': [
            {'name': 'mount-ro', 'image': PY_IMAGE, 'command': ['python3', '-I', '-c', ro_check,
                                                               *[m['mountPath'] for m in claim_mounts]],
             'securityContext': hardened(65534), 'volumeMounts': claim_mounts},
            guard],
        'containers': [{'name': 'ok', 'image': PY_IMAGE, 'securityContext': hardened(65534),
                        'command': ['python3', '-I', '-c', 'import sys; print("gate-guard-ok", sys.argv[1])', i]}],
        'volumes': volumes}
    if 'securityContext' in spec:
        guard_pod['securityContext'] = spec['securityContext']
    objs = [script_cm(i, ns, 'gate')]
    objs += pair(gate, i, ns, node_manual_csi(i, target), entry['size'], step='gate')
    objs.append(job(gate, i, ns, copy_pod(i, ['gate', i], {'migrate-src': gate}, image), step='gate'))
    guard_csi = dict(node_manual_csi(i, target), fsType='ext4')
    objs += pair(gv, i, ns, guard_csi, entry['size'], mode='Filesystem', step='guard', mount_options=['ro', 'noload'])
    objs.append(job(gv, i, ns, guard_pod, step='guard'))
    return objs, None


def gate_passed(log, i):
    lines = log.splitlines()
    first = {x: lines.index(x) for x in (f'gate-fsck-ok {i}', f'gate-guard-ok {i}') if x in lines}
    return len(first) == 2 and first[f'gate-fsck-ok {i}'] < first[f'gate-guard-ok {i}']


def dump(path, docs):
    path.write_text(yaml.safe_dump_all(docs, sort_keys=False))


# ---------- collectors (live, thin) ----------

def run_json(cmd):
    return json.loads(subprocess.run(cmd, check=True, capture_output=True, text=True).stdout)


def collect(repo, lock_root):
    live = run_json(['kubectl', 'get', 'pods,pv,pvc,volumeattachments,jobs,cronjobs,deployments,statefulsets',
                     '-A', '-o', 'json'])['items']
    ci = {'runs': {}, 'prs': {}}
    for r, wf in REBUILDS.items():
        ci['runs'][r] = run_json(['gh', 'run', 'list', '-R', f'Starktastic-Homelab/{r}', '--workflow', wf,
                                  '--json', 'status', '--limit', '20'])
        ci['prs'][r] = run_json(['gh', 'pr', 'list', '-R', f'Starktastic-Homelab/{r}', '--state', 'open',
                                 '--json', 'number,title,autoMergeRequest'])
    try:
        with open(Path(lock_root) / 'operation.json') as f:
            raw = json.load(f)
        lock = {k: raw.get(k) for k in ('operation', 'owner')}  # the nonce is never kept
    except FileNotFoundError:
        lock = None
    git = lambda *a: subprocess.run(['git', '-C', str(repo), *a], check=True, capture_output=True, text=True).stdout
    clone = {'head': git('rev-parse', 'HEAD').strip(), 'origin_main': git('rev-parse', 'origin/main').strip(),
             'dirty': bool(git('status', '--porcelain').strip())}
    return {'live': live, 'ci': ci, 'lock': lock, 'clone': clone}


def collect_labelled(i):
    sel = f'{LABEL}={i}'
    left = run_json(['kubectl', 'get', 'pv,pvc,pods,jobs,configmaps', '-A', '-l', sel, '-o', 'json'])['items']
    return left + run_json(['kubectl', 'get', 'volumeattachments', '-o', 'json'])['items']


def leftovers(live, i):
    left = [f"{o['kind']} {o['metadata'].get('namespace', '')}/{o['metadata']['name']}" for o in live
            if o.get('kind') != 'VolumeAttachment' and (o['metadata'].get('labels') or {}).get(LABEL) == i]
    ours = set(expected_handles(i, 'forward'))
    left += [f"VolumeAttachment {o['metadata']['name']} names {pv}" for o in by_kind(live, 'VolumeAttachment')
             for pv in [o.get('spec', {}).get('source', {}).get('persistentVolumeName')] if pv in ours]
    return left


# ---------- CLI ----------

def refuse(reasons):
    for x in reasons:
        print(f'refused: {x}')
    return 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    for name in ('precheck', 'render', 'verify-teardown'):
        p = sub.add_parser(name)
        p.add_argument('id')
        p.add_argument('--repo', type=Path, default=ROOT)
        p.add_argument('--lock-root', default=LOCK_ROOT)
        if name != 'verify-teardown':
            p.add_argument('--direction', choices=('forward', 'reverse'), default='forward' if name == 'precheck' else None,
                           required=name == 'render')
        if name == 'render':
            p.add_argument('--out', type=Path, required=True)
    a = ap.parse_args(argv)
    i, repo = a.id, a.repo.resolve()

    if a.cmd == 'verify-teardown':
        deadline = time.monotonic() + TEARDOWN_TIMEOUT
        while True:
            left = leftovers(collect_labelled(i), i)
            if not left:
                print(f'teardown-ok {i}')
                return 0
            if time.monotonic() >= deadline:
                return refuse([f'left: {x}' for x in left])
            time.sleep(5)

    if a.cmd == 'render':
        out = a.out.resolve()
        if out == repo or repo in out.parents:
            return refuse([f'out: {out} is inside the repo; Argo must never read the rendered set'])
    entry, bindings = load_entry(repo, i), find_bindings(repo, i)
    got = collect(repo, a.lock_root)
    reasons = decide(i, entry, bindings, got['live'], got['ci'], got['lock'], got['clone'], a.direction)
    if a.cmd == 'precheck':
        return refuse(reasons) if reasons else 0

    gate_log = out / 'gate.log'
    pass1 = a.direction == 'reverse' and not gate_log.exists()
    target = storage_target(repo)
    try:
        image = copy_image(repo)
    except ValueError as e:
        return refuse([f'image: {e}'])
    # The gate check runs whatever decide found, so a pass 1 before the hold still prints its gate line.
    if a.direction == 'reverse' and entry is not None:
        if pass1:
            objs, why = render_gate(i, entry, target, got['live'], image)
        else:
            why = None if gate_passed(gate_log.read_text(), i) else f'gate: {gate_log} lacks gate-fsck-ok and gate-guard-ok {i}'
            live_pvs = {p['metadata']['name'] for p in by_kind(got['live'], 'PersistentVolume')}
            reasons += [f'handle: gate PV {n} is still live' for n in (f'migrate-gate-{i}', f'migrate-guard-{i}')
                        if n in live_pvs]
        if why:
            reasons.append(why)
    if reasons:
        return refuse(reasons)

    out.mkdir(parents=True, exist_ok=True)
    b = bindings[0]
    record = {'id': i, 'direction': a.direction, 'pass': 'gate' if pass1 else 'copy', 'namespace': entry['namespace'],
              'handles': expected_handles(i, a.direction),
              'sizes': {'inventory': entry['size'], 'binding': b['spec']['capacity']['storage']},
              'claims': {'old': b['spec'].get('claimRef'), 'new': {'namespace': entry['namespace'],
                                                                   'name': entry['claim']}},
              'apps_head': got['clone']['head']}
    if pass1:
        dump(out / 'gate.yaml', objs)
    else:
        pairs, jobs = render_copy(i, entry, b, target, a.direction, image)
        dump(out / 'pairs.yaml', pairs)
        dump(out / 'job.yaml', jobs)
    (out / 'render.json').write_text(json.dumps(record, indent=2) + '\n')
    if pass1:
        print('gate-required')
    return 0


if __name__ == '__main__':
    sys.exit(main())
