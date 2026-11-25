#!/usr/bin/env python3
"""CI check for infrastructure/base-configs/files/retained-volumes.json (ADR 0017).

Rejects, against the base ref: bad ids, a claim not named after its id, changed class/origin, size decreases,
duplicates, malformed sizes, entries over a VG's usable size (from terraform main), and more than 2 removals unless
the PR carries the override label (env PR_LABELS, comma separated).
check_bindings() then checks how app values bind the head inventory's claims (the switch to a storage-VM volume), and
check_removed() refuses removing an entry whose claim git still binds.
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

import yaml

PATH = 'infrastructure/base-configs/files/retained-volumes.json'
# Must equal ansible roles/storage_vm/files/homelab_storage/inventory.py ID_PATTERN; test_id_pattern_tripwire pins
# the literal so a change here is deliberate and goes in with that one.
ID_PATTERN = r'^(?!snapshot|pvmove)[a-z0-9][a-z0-9-]{0,62}$'
SIZE_PATTERN = r'^([1-9][0-9]*)(Gi|Mi)$'
FIELDS = {'id', 'namespace', 'claim', 'size', 'class', 'origin'}
OPTIONAL = {'copied'}  # YYYY-MM-DD, set by the switch PR on a migrated entry
CLASSES = {'retained', 'regenerable'}
ORIGINS = {'migrated', 'new'}
MAX_REMOVALS = 2
MIB = 1024 * 1024
# terraform owns the storage VM's data disks; their serial is the VG name. Growth merges terraform first.
STORAGE_TFVARS = 'https://raw.githubusercontent.com/Starktastic-Homelab/terraform/main/storage/terraform.tfvars'
VG_FOR = {'retained': 'retained', 'regenerable': 'regen'}  # class -> VG, as ansible inventory.vg_for
RESERVE_MIN_DIVISOR = 10


def size_bytes(text):
    m = re.fullmatch(SIZE_PATTERN, text) if isinstance(text, str) else None
    if not m:
        raise ValueError(f'bad size {text!r}')
    n = int(m.group(1)) * (1024 * MIB if m.group(2) == 'Gi' else MIB)
    if n % (4 * MIB):
        raise ValueError(f'size {text} is not a multiple of 4Mi')
    return n


def valid_date(text):
    if not isinstance(text, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', text):
        return False
    try:
        datetime.date.fromisoformat(text)
    except ValueError:
        return False
    return True


def validate(entries, label):
    """Return (errors, {id: entry})."""
    errors, by_id, claims = [], {}, set()
    if not isinstance(entries, list):
        return [f'{label}: inventory must be a JSON array'], {}
    for e in entries:
        if not isinstance(e, dict) or not FIELDS <= set(e) <= FIELDS | OPTIONAL:
            errors.append(f'{label}: entry must have exactly {sorted(FIELDS)} plus optional {sorted(OPTIONAL)}: {e!r}')
            continue
        i = e['id']
        if not isinstance(i, str) or not re.fullmatch(ID_PATTERN, i):
            errors.append(f'{label}: bad id {i!r}')
            continue
        if i in by_id:
            errors.append(f'{label}: duplicate id {i}')
        by_id[i] = e
        if not isinstance(e['class'], str) or e['class'] not in CLASSES:
            errors.append(f'{label}: {i}: bad class {e["class"]!r}')
        if not isinstance(e['origin'], str) or e['origin'] not in ORIGINS:
            errors.append(f'{label}: {i}: bad origin {e["origin"]!r}')
        try:
            size_bytes(e['size'])
        except ValueError as exc:
            errors.append(f'{label}: {i}: {exc}')
        if 'copied' in e:
            if e['origin'] != 'migrated':
                errors.append(f'{label}: {i}: copied is only allowed on origin migrated')
            elif not valid_date(e['copied']):
                errors.append(f'{label}: {i}: bad copied {e["copied"]!r}: want YYYY-MM-DD')
        if not isinstance(e['namespace'], str) or not e['namespace']:
            errors.append(f'{label}: {i}: bad namespace')
        claims_ok = {f'{i}-iscsi'} | {f'{i}-iscsi-{sts}-0' for sts in KPS_STS.values()}
        if not isinstance(e['claim'], str) or e['claim'] not in claims_ok:
            errors.append(f'{label}: {i}: claim must be {i}-iscsi (or {i}-iscsi-<sts>-0 for a kube-prometheus-stack '
                          f'StatefulSet), not {e["claim"]!r}')
        elif not isinstance(e['namespace'], str):
            pass  # reported above
        elif (e['namespace'], e['claim']) in claims:
            errors.append(f'{label}: {i}: duplicate namespace/claim')
        else:
            claims.add((e['namespace'], e['claim']))
    return errors, by_id


def check(base, head, override=False, vg_bytes=None):
    errors, base_ids = validate(base, 'base')
    errs, head_ids = validate(head, 'head')
    errors += errs
    if errors:
        return errors
    # An id change is a removal plus a new entry (a new claim too): check_removed() refuses it while git still binds
    # the old claim.
    removed = sorted(set(base_ids) - set(head_ids))
    for i in set(base_ids) & set(head_ids):
        b, h = base_ids[i], head_ids[i]
        for k in ('class', 'origin'):
            if b[k] != h[k]:
                errors.append(f'{i}: {k} changed {b[k]} -> {h[k]}')
        if size_bytes(h['size']) < size_bytes(b['size']):
            errors.append(f'{i}: size decreased {b["size"]} -> {h["size"]}')
    if len(removed) > MAX_REMOVALS and not override:
        errors.append(f'{len(removed)} removals ({", ".join(removed)}) need the override label')
    for vg, usable in (vg_bytes or {}).items():
        sizes = [size_bytes(e['size']) for e in head if VG_FOR[e['class']] == vg]
        total = sum(sizes)
        # Keep one LVM snapshot of the largest LV possible (deferred storage-VM backup path, Ben 2026-11-22).
        reserve = max(max(sizes, default=0), usable // RESERVE_MIN_DIVISOR)
        if total > usable:
            errors.append(f'VG {vg}: entries sum to {total} bytes, more than its {usable} usable bytes')
        elif usable - total < reserve:
            errors.append(f'VG {vg}: {usable - total} bytes free, less than the snapshot reserve of {reserve} bytes')
    return errors


TOKEN = re.compile(r'"(?:\\.|[^"\\])*"|/\*.*?\*/|#[^\n]*|//[^\n]*|[\[\]{}]', re.S)


def _top_level(text, start, close):
    """Yield (open bracket, body) for each top-level {...} in text[start:] up to the matching close; comments are
    already blanked. Raises ValueError on unbalanced input or anything but blocks, commas and space between them."""
    depth, pos, out = 0, start, []
    for m in TOKEN.finditer(text, start):
        tok = m.group()
        if tok[0] == '"':
            continue
        if tok in '{[':
            if depth == 0:
                if tok != '{' or text[pos:m.start()].strip(' \t\r\n,'):
                    raise ValueError('data_disks must be a list of { ... } blocks')
                begin = m.end()
            depth += 1
        else:
            if depth == 0:
                if tok != close or text[pos:m.start()].strip(' \t\r\n,'):
                    raise ValueError('data_disks must be a list of { ... } blocks')
                return out
            depth -= 1
            if depth == 0:
                out.append(text[begin:m.start()])
                pos = m.end()
    raise ValueError('unbalanced data_disks list')


def vg_bytes_from_tfvars(text):
    """{vg: usable bytes} from terraform storage/terraform.tfvars data_disks; usable = <size> GiB - 4 MiB
    (1 MiB pe_start, rest rounded down to 4 MiB extents). Each disk has one literal size (GiB) and serial (= VG)."""
    clean = TOKEN.sub(lambda m: m.group() if m.group()[0] in '"[]{}' else ' ', text)  # blank comments, keep strings
    found = list(re.finditer(r'(?m)^\s*data_disks\s*=\s*\[', clean))
    if len(found) != 1:
        raise ValueError(f'want exactly one data_disks list, found {len(found)}')
    m = found[0]
    sizes = {}
    for block in _top_level(clean, m.end(), ']'):
        flat = block
        while re.search(r'\{[^{}]*\}', flat):  # drop nested objects: only the disk's own attributes count
            flat = re.sub(r'\{[^{}]*\}', '', flat)
        size = re.findall(r'(?<![\w.])size\s*=\s*([^\s,}]+)', flat)
        serial = re.findall(r'(?<![\w.])serial\s*=\s*"([^"]*)"', flat)
        if len(size) != 1 or len(serial) != 1 or not re.fullmatch(r'[1-9][0-9]*', size[0]) or serial[0] in sizes:
            raise ValueError(f'want one literal size and one unique serial per data disk: {block.strip()!r}')
        sizes[serial[0]] = int(size[0])
    if set(sizes) != set(VG_FOR.values()):
        raise ValueError(f'want data disks with serials exactly {sorted(VG_FOR.values())}, got {sorted(sizes)}')
    return {vg: gib * 1024 * MIB - 4 * MIB for vg, gib in sizes.items()}


def read_tfvars(source):
    if source.startswith('https://'):
        with urllib.request.urlopen(source, timeout=30) as r:
            return r.read().decode()
    return Path(source).read_text()


def load_yaml(path):
    return yaml.safe_load(path.read_text()) or {}


def merge(base, over):
    """Helm values layering: maps merge, everything else (lists too) replaces."""
    if isinstance(base, dict) and isinstance(over, dict):
        return {**base, **{k: merge(base.get(k), v) for k, v in over.items()}}
    return over


def effective_values(root, app_yaml, used=None):
    """The app's merged Helm values, layered as bootstrap/appsets/cluster-apps.yaml does (globals.yaml carries none).

    Each layer file read is added to the set `used`, when given.
    """
    app = load_yaml(app_yaml)
    own = app_yaml.parent.relative_to(root)
    service = own.parts[0] == 'services'
    if not service and not app.get('chart'):
        return app, {}
    base = app.get('baseApp') if service else None
    layers = (['templates/common.yaml'] if service else []) + list(app.get('commonValuesExtras') or [])
    layers.append(f'{base or own}/values.yaml')
    if base and app.get('valuesOverride'):
        layers.append(f'{own}/values.yaml')
    values = {}
    for layer in layers:
        if (root / layer).exists():
            values = merge(values, load_yaml(root / layer))
            if used is not None:
                used.add((root / layer).resolve())
    return app, values


def dig(node, *keys):
    for k in keys:
        node = node.get(k) if isinstance(node, dict) else None
    return node


def as_list(node):
    return node if isinstance(node, list) else []


def mounted_by_init(inits, volume):
    """True if a plain Kubernetes init container list mounts the named volume."""
    return any(m.get('name') == volume for c in as_list(inits) for m in as_list(c.get('volumeMounts')))


# shortcut: STS names are chart-derived; re-check on a kube-prometheus-stack major
KPS_STS = {
    ('prometheus', 'prometheusSpec', 'storageSpec'): 'prometheus-kube-prometheus-stack-prometheus',
    ('alertmanager', 'alertmanagerSpec', 'storage'): 'alertmanager-kube-prometheus-stack-alertmanager',
}


def resolve(values):
    """Yield (path, kind, claim or volume name, guard mounted, derived STS claim or None, pod) per volume binding.

    pod is (pod-like {initContainers, volumes}, the claim's volume) for check-retained-guards.py's guard_errors(),
    or None for app-template, whose pods it renders.
    """
    controllers = values.get('controllers') or {}
    for key, p in (values.get('persistence') or {}).items():  # app-template
        if isinstance(p, dict) and isinstance(p.get('existingClaim'), str):
            guarded = any(set(mounts or {}) & set(dig(controllers, ctrl, 'initContainers') or {})
                          for ctrl, mounts in (p.get('advancedMounts') or {}).items())
            yield ('persistence', key, 'existingClaim'), 'claim', p['existingClaim'], guarded, None, None
    sb = values.get('singleBinary') or {}  # loki
    for n, v in enumerate(as_list(sb.get('extraVolumes'))):
        claim = dig(v, 'persistentVolumeClaim', 'claimName')
        if isinstance(claim, str):
            path = ('singleBinary', 'extraVolumes', n, 'persistentVolumeClaim', 'claimName')
            pod = {'initContainers': as_list(sb.get('initContainers')), 'volumes': as_list(sb.get('extraVolumes'))}
            yield path, 'claim', claim, mounted_by_init(sb.get('initContainers'), v.get('name')), None, (pod, v)
    for path, sts in KPS_STS.items():  # kube-prometheus-stack operator StatefulSets
        vct = dig(values, *path, 'volumeClaimTemplate')
        template = dig(vct, 'metadata', 'name')
        if not isinstance(template, str):
            continue
        guarded = mounted_by_init(dig(values, *path[:2], 'initContainers'), template)
        pod = ({'initContainers': as_list(dig(values, *path[:2], 'initContainers')),
                'volumes': as_list(dig(values, *path[:2], 'volumes'))}, {'name': template})
        derived = f'{template}-{sts}-0'
        # The STS adopts an existing PVC by this name whether or not volumeName is set.
        yield path + ('volumeClaimTemplate', 'metadata', 'name'), 'claim', derived, guarded, None, pod
        name = dig(vct, 'spec', 'volumeName')
        if isinstance(name, str):
            yield path + ('volumeClaimTemplate', 'spec', 'volumeName'), 'volume', name, guarded, derived, pod


def strings(node, path=()):
    if isinstance(node, str):
        yield path, node
    elif isinstance(node, dict):
        for k, v in node.items():
            yield from strings(v, path + (k,))
    elif isinstance(node, list):
        for n, v in enumerate(node):
            yield from strings(v, path + (n,))


def static_claims(root):
    """(namespace, name) of every PersistentVolumeClaim committed as plain YAML (templated files skipped)."""
    found = set()
    for top in ('infrastructure', 'services'):
        for path in sorted((root / top).rglob('*.y*ml')):
            text = path.read_text()
            if '{{' in text or 'PersistentVolumeClaim' not in text:  # also skips Authentik blueprints' custom tags
                continue
            for doc in yaml.safe_load_all(text):
                if isinstance(doc, dict) and doc.get('kind') == 'PersistentVolumeClaim':
                    found.add((dig(doc, 'metadata', 'namespace'), dig(doc, 'metadata', 'name')))
    return found


def check_bindings(entries, root):
    """Errors in how app values bind the inventory's claims. See ADR 0017 and the migration plan's Task 2.6."""
    errors = []
    by_claim = {(e['namespace'], e['claim']): e for e in entries}
    by_id = {e['id']: e for e in entries}
    static = static_claims(root)
    for (ns, claim), e in sorted(by_claim.items()):
        # A PVC without metadata.namespace lands in its app's namespace: match it on name alone (fail closed).
        if (ns, claim) in static or (None, claim) in static:
            errors.append(f'{e["id"]}: claim {ns}/{claim} is a static PVC already; use a new claim')
    users = {}
    for app_yaml in sorted([*(root / 'services').rglob('app.yaml'), *(root / 'infrastructure').rglob('app.yaml')]):
        app, values = effective_values(root, app_yaml)
        name, ns = app.get('name', app_yaml.parent.name), app.get('namespace')
        consumed, seen = set(), set()
        for path, kind, ref, guarded, derived, _ in resolve(values):
            e = by_claim.get((ns, ref)) if kind == 'claim' else by_id.get(ref)
            if not e:
                continue
            consumed.add(path)
            if (path[:3], e['id']) in seen:  # a kps claim and its volumeName naming one entry: report once
                continue
            seen.add((path[:3], e['id']))
            if derived and (e['namespace'], e['claim']) != (ns, derived):
                errors.append(f'{name}: volumeName {ref} needs inventory claim {ns}/{derived}, '
                              f'not {e["namespace"]}/{e["claim"]}')
            if e['origin'] == 'migrated' and 'copied' not in e:
                errors.append(f'{name}: binds {e["id"]} (migrated) but the entry has no copied date')
            if not guarded:
                errors.append(f'{name}: no init container mounts {e["id"]} at {".".join(map(str, path))}')
            users.setdefault((e['namespace'], e['claim']), set()).add(name)
        claims = {c for n, c in by_claim if n == ns}
        for path, text in strings(values):
            if text in claims and path not in consumed:
                errors.append(f'{name}: {".".join(map(str, path))} names inventory claim {text} '
                              'in a style no resolver exists for')
    for (ns, claim), apps in sorted(users.items()):
        if len(apps) > 1:
            errors.append(f'{ns}/{claim} is bound by more than one app ({", ".join(sorted(apps))}): one RWOP claim')
    return errors


def check_removed(removed, root):
    """Errors for removed entries whose (namespace, claim) git still binds: expiry would delete a volume in use.

    Layered app values are matched by namespace (any string, plus resolve()'s derived STS claims and volumeName ids).
    Other committed YAML (an unlayered values.yaml too) under infrastructure/ and services/ is matched on any string equal to the claim, in the entry's namespace or
    with none set; a templated file, which cannot be parsed, on the claim as a whole word (fail closed).
    """
    errors, layered = [], set()
    for app_yaml in sorted([*(root / 'services').rglob('app.yaml'), *(root / 'infrastructure').rglob('app.yaml')]):
        app, values = effective_values(root, app_yaml, layered)
        name, ns = app.get('name', app_yaml.parent.name), app.get('namespace')
        refs = {text for _, text in strings(values)}
        refs |= {ref for _, kind, ref, *_ in resolve(values) if kind == 'claim'}
        volumes = {ref for _, kind, ref, *_ in resolve(values) if kind == 'volume'}
        for e in removed:
            if e['namespace'] == ns and (e['claim'] in refs or e['id'] in volumes):
                errors.append(f'{e["id"]}: removed, but {name} still binds {ns}/{e["claim"]}; remove the binding first')
    for top in ('infrastructure', 'services'):
        for path in sorted((root / top).rglob('*.y*ml')):
            if path.resolve() in layered:  # matched per namespace above
                continue
            text = path.read_text()
            for e in removed:
                if e['claim'] not in text:
                    continue
                if '{{' in text:
                    hit = re.search(rf'(?<![\w.-]){re.escape(e["claim"])}(?![\w.-])', text)
                else:
                    hit = any(dig(d, 'metadata', 'namespace') in (None, e['namespace'])
                              and any(t == e['claim'] for _, t in strings(d))
                              for d in yaml.safe_load_all(text) if isinstance(d, dict))
                if hit:
                    errors.append(f'{e["id"]}: removed, but {path.relative_to(root)} still names claim {e["claim"]}')
    return errors


def load_base(ref):
    # An unresolvable ref must fail closed: an empty base would skip every base check.
    if subprocess.run(['git', 'rev-parse', '--verify', '--quiet', f'{ref}^{{commit}}'], capture_output=True).returncode:
        sys.exit(f'ERROR: base ref {ref} does not resolve (shallow checkout?)')
    r = subprocess.run(['git', 'cat-file', '-e', f'{ref}:{PATH}'], capture_output=True)
    if r.returncode:  # file absent on base: the first inventory PR
        return []
    return json.loads(subprocess.check_output(['git', 'show', f'{ref}:{PATH}']))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', required=True)
    ap.add_argument('--override-label', required=True)
    ap.add_argument('--inventory', default=PATH)
    ap.add_argument('--storage-tfvars', default=STORAGE_TFVARS, help='URL or path; tests and offline runs pass a file')
    a = ap.parse_args(argv)
    labels = [x for x in os.environ.get('PR_LABELS', '').split(',') if x]
    with open(a.inventory) as f:
        head = json.load(f)
    base = load_base(a.base)
    vg_bytes = None
    if head != base:  # only an inventory change depends on terraform main (and on raw.githubusercontent.com)
        try:  # fail closed: a missing, unreachable or malformed source is an error, never a skip
            vg_bytes = vg_bytes_from_tfvars(read_tfvars(a.storage_tfvars))
        except (OSError, ValueError) as exc:
            print(f'ERROR: VG sizes from {a.storage_tfvars}: {exc}', file=sys.stderr)
            return 1
    errors = check(base, head, a.override_label in labels, vg_bytes)
    if not errors:  # both inventories valid; the override label never covers a removal still bound
        head_ids = {e['id'] for e in head}
        errors += check_removed([e for e in base if e['id'] not in head_ids], Path('.'))
    if not validate(head, 'head')[0]:  # check_bindings expects a valid head inventory
        errors += check_bindings(head, Path('.'))
    for e in errors:
        print(f'ERROR: {e}', file=sys.stderr)
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
