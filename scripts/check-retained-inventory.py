#!/usr/bin/env python3
"""CI check for infrastructure/base-configs/files/retained-volumes.json (ADR 0017).

Rejects, against the base ref: bad ids, changed id/class/origin, size decreases, duplicates, malformed sizes,
and more than 2 removals unless the PR carries the override label (env PR_LABELS, comma separated).
"""
import argparse
import json
import os
import re
import subprocess
import sys

PATH = 'infrastructure/base-configs/files/retained-volumes.json'
# Must equal the ansible storage role's pattern (pinned by test_regex_matches_ansible).
ID_PATTERN = r'^(?!snapshot|pvmove)[a-z0-9][a-z0-9-]{0,62}$'
SIZE_PATTERN = r'^([1-9][0-9]*)(Gi|Mi)$'
FIELDS = {'id', 'namespace', 'claim', 'size', 'class', 'origin'}
CLASSES = {'retained', 'regenerable'}
ORIGINS = {'migrated', 'new'}
MAX_REMOVALS = 2
MIB = 1024 * 1024


def size_bytes(text):
    m = re.fullmatch(SIZE_PATTERN, text) if isinstance(text, str) else None
    if not m:
        raise ValueError(f'bad size {text!r}')
    n = int(m.group(1)) * (1024 * MIB if m.group(2) == 'Gi' else MIB)
    if n % (4 * MIB):
        raise ValueError(f'size {text} is not a multiple of 4Mi')
    return n


def validate(entries, label):
    """Return (errors, {id: entry})."""
    errors, by_id, claims = [], {}, set()
    if not isinstance(entries, list):
        return [f'{label}: inventory must be a JSON array'], {}
    for e in entries:
        if not isinstance(e, dict) or set(e) != FIELDS:
            errors.append(f'{label}: entry must have exactly {sorted(FIELDS)}: {e!r}')
            continue
        i = e['id']
        if not isinstance(i, str) or not re.fullmatch(ID_PATTERN, i):
            errors.append(f'{label}: bad id {i!r}')
            continue
        if i in by_id:
            errors.append(f'{label}: duplicate id {i}')
        by_id[i] = e
        if e['class'] not in CLASSES:
            errors.append(f'{label}: {i}: bad class {e["class"]!r}')
        if e['origin'] not in ORIGINS:
            errors.append(f'{label}: {i}: bad origin {e["origin"]!r}')
        try:
            size_bytes(e['size'])
        except ValueError as exc:
            errors.append(f'{label}: {i}: {exc}')
        for k in ('namespace', 'claim'):
            if not isinstance(e[k], str) or not e[k]:
                errors.append(f'{label}: {i}: bad {k}')
        if (e['namespace'], e['claim']) in claims:
            errors.append(f'{label}: {i}: duplicate namespace/claim')
        claims.add((e['namespace'], e['claim']))
    return errors, by_id


def check(base, head, override=False):
    errors, base_ids = validate(base, 'base')
    errs, head_ids = validate(head, 'head')
    errors += errs
    if errors:
        return errors
    removed = sorted(set(base_ids) - set(head_ids))
    added = set(head_ids) - set(base_ids)
    for i in removed:
        for j in added:
            if (base_ids[i]['namespace'], base_ids[i]['claim']) == (head_ids[j]['namespace'], head_ids[j]['claim']):
                errors.append(f'id changed {i} -> {j}: ids are immutable (a move is a new id plus a copy)')
    for i in set(base_ids) & set(head_ids):
        b, h = base_ids[i], head_ids[i]
        for k in ('class', 'origin'):
            if b[k] != h[k]:
                errors.append(f'{i}: {k} changed {b[k]} -> {h[k]}')
        if size_bytes(h['size']) < size_bytes(b['size']):
            errors.append(f'{i}: size decreased {b["size"]} -> {h["size"]}')
    if len(removed) > MAX_REMOVALS and not override:
        errors.append(f'{len(removed)} removals ({", ".join(removed)}) need the override label')
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
    a = ap.parse_args(argv)
    labels = [x for x in os.environ.get('PR_LABELS', '').split(',') if x]
    with open(a.inventory) as f:
        head = json.load(f)
    errors = check(load_base(a.base), head, a.override_label in labels)
    for e in errors:
        print(f'ERROR: {e}', file=sys.stderr)
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
