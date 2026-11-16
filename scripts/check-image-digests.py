#!/usr/bin/env python3
"""Catch image pins whose tag moved while their digest stayed behind.

Renovate's helm-values manager reads only `repository` and `tag`. A digest kept in a
sibling `digest:` or `sha:` key is invisible to it, so a tag bump leaves the old
digest in place and the old image keeps running under the new tag (#1425 Loki,
#1495 and #1573 Alertmanager). `tag: <version>@sha256:<digest>` strings are safe:
Renovate rewrites both halves together.

  check-image-digests.py --base <git-ref>   offline, CI: fail when a pin's tag differs
                                            from <git-ref> but its digest does not
  check-image-digests.py --registry         by hand: resolve every pinned tag (docker
                                            buildx) and list digests that differ from it

Rolling tags (`latest`, `18.6-alpine`) are pinned to an older build on purpose, so
--registry lists them too; only a versioned tag with a stale digest is mislabelled.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOTS = ('infrastructure', 'services')
REF = re.compile(r'^(?P<name>[\w.\-/:]+?):(?P<tag>[\w.\-]+)@(?P<digest>sha256:[0-9a-f]{64})$')


def walk(node, path=''):
    if isinstance(node, dict):
        yield path, node
        for key, value in node.items():
            yield from walk(value, f'{path}.{key}')
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from walk(value, f'{path}[{i}]')
    else:
        yield path, node


def pins(text):
    """{where: (image, tag, digest)} for each tag+digest pin in one YAML file."""
    found = {}
    for n, doc in enumerate(yaml.safe_load_all(text)):
        for where, node in walk(doc, f'#{n}'):
            if isinstance(node, str):
                m = REF.match(node.strip())
                if m:
                    found[where] = (m['name'], m['tag'], m['digest'])
                continue
            if not isinstance(node, dict) or not isinstance(node.get('repository'), str):
                continue
            tag = node.get('tag')
            if not isinstance(tag, (str, int, float)):
                continue
            tag = str(tag)
            image = '/'.join(filter(None, (node.get('registry'), node['repository'])))
            split = node.get('digest') or node.get('sha')
            if split:
                split = str(split)
                found[where] = (image, tag, split if split.startswith('sha256:') else 'sha256:' + split)
            elif '@sha256:' in tag:
                tag, digest = tag.split('@', 1)
                found[where] = (image, tag, digest)
    return found


def stale(base, head):
    """Locations whose tag changed while the digest stayed the same."""
    return [
        (where, base[where][1], tag)
        for where, (image, tag, digest) in head.items()
        if where in base and base[where][0] == image and base[where][1] != tag and base[where][2] == digest
    ]


def against_base(ref):
    problems = []
    for file in sorted(f for root in ROOTS for f in Path(root).rglob('values.yaml')):
        old = subprocess.run(['git', 'show', f'{ref}:{file}'], capture_output=True, text=True)
        if old.returncode:
            continue  # new file: nothing to compare against
        for where, was, now in stale(pins(old.stdout), pins(file.read_text())):
            problems.append(f'{file}: {where.lstrip("#0")}: tag {was} -> {now} but the digest did not change')
    for line in problems:
        print(line)
    if problems:
        print('Set the digest to the new tag\'s index digest '
              '(docker buildx imagetools inspect <image>:<tag>), or move the tag back.')
    else:
        print('No tag moved without its digest')
    return 1 if problems else 0


def registry_digests(ref):
    """Index digest plus every child manifest digest of ref."""
    out = subprocess.run(
        ['docker', 'buildx', 'imagetools', 'inspect', ref, '--format', '{{json .Manifest}}'],
        capture_output=True, text=True, timeout=120,
    )
    if out.returncode:
        raise RuntimeError((out.stderr.strip().splitlines() or ['inspect failed'])[-1])
    manifest = json.loads(out.stdout)
    return manifest['digest'], {m['digest'] for m in manifest.get('manifests') or ()}


def against_registry():
    users = {}
    for file in sorted(f for root in ROOTS for f in Path(root).rglob('values.yaml')):
        for where, (image, tag, digest) in pins(file.read_text()).items():
            users.setdefault(f'{image}:{tag}', []).append((f'{file}: {where.lstrip("#0")}', digest))
    problems = []
    for ref, pinned in sorted(users.items()):
        try:
            index, children = registry_digests(ref)
        except (RuntimeError, subprocess.TimeoutExpired) as error:
            problems.append(f'{ref}: lookup failed: {error}')
            continue
        for where, digest in pinned:
            if digest != index and digest not in children:
                problems.append(f'{where}: {ref} is pinned to {digest}, the tag is now {index}')
    for line in problems:
        print(line)
    print(f'{len(users)} tags checked, {len(problems)} problems')
    return 1 if problems else 0


def self_check():
    d = {c: 'sha256:' + c * 64 for c in 'abcd'}
    base = pins(
        f'a: {{repository: x/y, tag: "1@{d["a"]}"}}\n'
        f'b: {{registry: quay.io, repository: p/am, tag: v1, sha: {d["b"][7:]}}}\n'
        f'c: {{repository: python, digest: {d["c"]}}}\n'
        f'e: "ghcr.io/o/i:2.0@{d["d"]}"\n'
    )
    assert base == {
        '#0.a': ('x/y', '1', d['a']), '#0.b': ('quay.io/p/am', 'v1', d['b']), '#0.e': ('ghcr.io/o/i', '2.0', d['d']),
    }, base
    head = dict(base)
    head['#0.a'] = ('x/y', '2', d['c'])  # tag and digest moved together: fine
    head['#0.b'] = ('quay.io/p/am', 'v2', d['b'])  # the #1573 shape
    assert stale(base, head) == [('#0.b', 'v1', 'v2')], stale(base, head)


if __name__ == '__main__':
    self_check()
    if sys.argv[1:2] == ['--base'] and len(sys.argv) == 3:
        sys.exit(against_base(sys.argv[2]))
    if sys.argv[1:] == ['--registry']:
        sys.exit(against_registry())
    sys.exit(__doc__)
