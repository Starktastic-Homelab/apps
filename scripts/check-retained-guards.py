#!/usr/bin/env python3
"""CI check that every retained volume's consumer runs the marker guard first (ADR 0017, Guards). Run from the repo
root; needs helm.

Consumers are matched to inventory entries by (namespace, claim). Each app's sources and value files come from
bootstrap/appsets/cluster-apps.yaml's templatePatch, evaluated by helm, never from a second copy of the layering.
App-template charts (the AppSet's default chart) are rendered; plain and kustomize manifests are read as committed;
other charts go through check-retained-inventory.py's static resolvers.

  - an origin: new entry, or a migrated one with copied, has exactly one consumer; any other entry has none
  - in a rendered or committed pod, the first init container that mounts the claim is the guard: it mounts the claim
    read-only and ConfigMap retained-startup-guard, and runs guard.py on that mount (an origin: new guard with the
    entry's id as <app>, an id guard.py accepts)
  - a claim named like an inventory claim but mounted in another namespace is not in the inventory
  - `retained: <id>` in app.yaml (the one-flag guard layer) names an origin: new entry in the app's namespace whose
    claim is <id>-iscsi, on an app the AppSet layers it onto

Set CHART_CACHE to a directory of <chart>-<version>.tgz files to render offline; otherwise each chart is pulled once.
"""
import argparse
import atexit
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
APPSET = 'bootstrap/appsets/cluster-apps.yaml'
LAYER = 'templates/retained-guard.yaml'
CONFIGMAP = 'retained-startup-guard'


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


inv = module('check_retained_inventory', HERE / 'check-retained-inventory.py')
guard_py = module('retained_guard', HERE.parent / 'infrastructure/base-configs/files/retained-startup/guard.py')


class RenderError(Exception):
    pass


def helm(root, *args):
    r = subprocess.run(['helm', *map(str, args)], cwd=root, capture_output=True, text=True)
    if r.returncode:
        raise RenderError(r.stderr.strip())
    return r.stdout


def flag_refused(e):
    """Why `retained:` may not name this entry, or None. Task 5.12 lifts the migrated refusal (with copied set)."""
    return None if e['origin'] == 'new' else f'{e["id"]} is origin {e["origin"]}; the flag is for origin: new only'


def app_params(root, appset):
    """The generator parameters of every app: its list element, its app.yaml keys and the git generator's .path."""
    generators = appset['spec']['generators'][0]['matrix']['generators']
    elements = [e for g in generators if 'list' in g for e in g['list']['elements']]
    for el in elements:
        for app_yaml in sorted(root.glob(el['pathPattern'])):
            rel = app_yaml.parent.relative_to(root)
            path = {'path': str(rel), 'basename': rel.name, 'filename': app_yaml.name,
                    'basenameNormalized': rel.name, 'filenameNormalized': app_yaml.name, 'segments': list(rel.parts)}
            yield {**el, **inv.load_yaml(app_yaml), 'path': path}


def appset_apps(root):
    """[{name, namespace, params, sources}] with sources as the AppSet's templatePatch renders them for each app.

    shortcut: helm evaluates the patch with Helm's missingkey=zero, not Argo's missingkey=error; a missing key
    renders empty here instead of failing the AppSet.
    """
    appset = inv.load_yaml(root / APPSET)
    params = list(app_params(root, appset))
    patch = appset['spec']['templatePatch']
    namespace = appset['spec']['template']['spec']['destination']['namespace']
    with tempfile.TemporaryDirectory() as tmp:
        dump = Path(tmp, 'patch')
        (dump / 'templates').mkdir(parents=True)
        (dump / 'Chart.yaml').write_text('apiVersion: v2\nname: patch\nversion: 0.0.0\n')
        (dump / 'templates/patch.yaml').write_text(
            '{{- range $i, $app := .Values.apps }}{{ with $app }}\n---\n'
            f'index: {{{{ $i }}}}\nnamespace: "{namespace}"\n{patch}\n{{{{- end }}}}{{{{ end }}}}\n')
        (dump / 'values.yaml').write_text(json.dumps({'apps': params}, default=str))
        out = helm(root, 'template', 'patch', dump)
    apps = []
    for doc in yaml.safe_load_all(out):
        if doc:
            p = params[doc['index']]
            apps.append({'name': p['name'], 'namespace': doc['namespace'], 'params': p,
                         'sources': doc['spec']['sources'], 'default_chart': (p['defaultChartRepo'], p['defaultChartName'])})
    return apps


def value_files(source):
    return [f.removeprefix('$values/') for f in source['helm']['valueFiles']]


_charts = {}


def chart(repo, name, version):
    """A local tarball of the chart: from CHART_CACHE, else pulled once per run."""
    key = (repo, name, version)
    if key not in _charts:
        tmp = tempfile.mkdtemp(prefix='retained-guards-')
        atexit.register(shutil.rmtree, tmp, True)
        cached = Path(os.environ.get('CHART_CACHE', '/nonexistent'), f'{name}-{version}.tgz')
        if cached.is_file():
            shutil.copy(cached, tmp)  # the offline helm wrapper only sees /tmp and the working directory
        else:
            helm('.', 'pull', name, '--repo', repo, '--version', version, '-d', tmp)
        _charts[key] = next(Path(tmp).glob('*.tgz'))
    return _charts[key]


def render_source(root, app, source):
    """helm template of one chart source, with its value files and parameters, as Argo renders it."""
    args = ['template', app['name'], chart(source['repoURL'], source['chart'], str(source['targetRevision'])),
            '--namespace', app['namespace']]
    for f in value_files(source):
        args += ['-f', f]
    for p in source['helm'].get('parameters') or []:
        args += ['--set-string' if p.get('forceString') else '--set', f'{p["name"]}={p["value"]}']
    return helm(root, *args)


def pod_specs(node):
    """Every pod spec (a mapping with a containers list) in a manifest."""
    if isinstance(node, dict):
        if isinstance(node.get('containers'), list):
            yield node
        else:
            for v in node.values():
                yield from pod_specs(v)
    elif isinstance(node, list):
        for v in node:
            yield from pod_specs(v)


def manifest_docs(path):
    """Committed pod manifests under a source path. As static_claims does, templated files (helmManifests) and files
    without the kind of object sought (pods; also Authentik blueprints' custom tags) are skipped."""
    for f in sorted(path.rglob('*.y*ml')):
        text = f.read_text()
        if '{{' not in text and 'containers' in text and f.name not in ('kustomization.yaml', 'values.yaml'):
            yield from (d for d in yaml.safe_load_all(text) if isinstance(d, dict))


def workloads(root, app):
    """(label, namespace, pod spec or None, claim, guarded) for every claim an app's pods mount.

    guarded is set only for statically resolved charts, whose pods are not rendered.
    """
    for source in app['sources']:
        if 'chart' in source:
            if (source['repoURL'], source['chart']) == app['default_chart']:
                docs = list(yaml.safe_load_all(render_source(root, app, source)))
            else:
                values = {}
                for f in value_files(source):
                    if (root / f).exists():
                        values = inv.merge(values, inv.load_yaml(root / f))
                for path, kind, ref, guarded, _ in inv.resolve(values):
                    if kind == 'claim':
                        yield app['name'], app['namespace'], None, ref, guarded
                continue
        elif source.get('path') and 'helm' not in source:  # a helm path source is templated (ingress chart, helmManifests)
            docs = list(manifest_docs(root / source['path']))
        else:
            continue
        for doc in docs:
            if not isinstance(doc, dict):
                continue
            ns = (doc.get('metadata') or {}).get('namespace') or app['namespace']
            for pod in pod_specs(doc):
                for v in pod.get('volumes') or []:
                    claim = inv.dig(v, 'persistentVolumeClaim', 'claimName')
                    if claim:
                        yield f'{app["name"]}/{doc.get("kind")}/{inv.dig(doc, "metadata", "name")}', ns, (pod, v), claim, None


def guard_errors(label, e, pod, volume):
    """Errors in the guard of one pod that mounts the entry's claim through `volume`."""
    vol = volume['name']
    volumes = {v.get('name'): v for v in pod.get('volumes') or []}
    inits = pod.get('initContainers') or []
    first = next((c for c in inits if any(m.get('name') == vol for m in c.get('volumeMounts') or [])), None)
    where = f'{label}: claim {e["namespace"]}/{e["claim"]} ({e["id"]})'
    if first is None:
        return [f'{where}: no guard init container mounts it']
    errors = []
    claim_mounts = [m for m in first['volumeMounts'] if m.get('name') == vol]
    cm_mounts = [m for m in first['volumeMounts'] if inv.dig(volumes.get(m.get('name')), 'configMap', 'name') == CONFIGMAP]
    argv = [str(a) for a in (first.get('command') or []) + (first.get('args') or [])]
    scripts = [i for i, a in enumerate(argv) if any(a == f'{m["mountPath"]}/guard.py' for m in cm_mounts)]
    if not cm_mounts:
        errors.append(f'{where}: the first init container mounting it, {first["name"]}, does not mount ConfigMap '
                      f'{CONFIGMAP}')
    elif len(scripts) != 1 or len(argv) < scripts[0] + 3:
        errors.append(f'{where}: the first init container mounting it, {first["name"]}, does not run guard.py '
                      '<app> <root>')
    else:
        app, root = argv[scripts[0] + 1:scripts[0] + 3]
        if root not in [m['mountPath'] for m in claim_mounts]:
            errors.append(f'{where}: {first["name"]} runs guard.py on {root}, not on the claim mount')
        if e['origin'] == 'new' and app != e['id']:
            errors.append(f'{where}: {first["name"]} runs guard.py for {app}, not for {e["id"]}')
    if not all(m.get('readOnly') is True for m in claim_mounts):
        errors.append(f'{where}: {first["name"]} mounts it without read-only')
    return errors


def flag_errors(app, by_id):
    """Errors in an app's `retained:` flag."""
    if 'retained' not in app['params']:
        return []
    rid = app['params']['retained']
    name = app['name']
    if not isinstance(rid, str) or not rid:
        return [f'{name}: retained must be a non-empty string, not {rid!r}']
    errors = []
    if not any(LAYER in value_files(s) for s in app['sources'] if 'chart' in s):
        errors.append(f'{name}: retained: {rid} but the AppSet adds no guard layer to this app (app-template '
                      'services only; a baseApp variant sets its own)')
    e = by_id.get(rid)
    if e is None:
        return errors + [f'{name}: retained: {rid} is not in the inventory']
    refused = flag_refused(e)
    if refused:
        errors.append(f'{name}: retained: {refused}')
    if e['claim'] != f'{rid}-iscsi':
        errors.append(f'{name}: retained: {rid} needs inventory claim {rid}-iscsi (<id>-iscsi), not {e["claim"]}')
    if e['namespace'] != app['namespace']:
        errors.append(f'{name}: retained: {rid} is in namespace {e["namespace"]}, the app in {app["namespace"]}')
    return errors


def check(entries, root):
    """All errors for a valid inventory and the repo tree at root."""
    root = Path(root)
    by_claim = {(e['namespace'], e['claim']): e for e in entries}
    by_id = {e['id']: e for e in entries}
    names = {e['claim']: e for e in entries}
    errors = [f'{e["id"]}: guard.py refuses this id; an origin: new entry needs one it accepts'
              for e in entries if e['origin'] == 'new' and not re.fullmatch(guard_py.NAME, e['id'])]
    found = {}
    for app in appset_apps(root):
        errors += flag_errors(app, by_id)
        try:
            mounted = list(workloads(root, app))
        except RenderError as exc:
            errors.append(f'{app["name"]}: render failed: {exc}')
            continue
        for label, ns, pod, claim, guarded in mounted:
            e = by_claim.get((ns, claim))
            if e is None:
                if claim in names:
                    errors.append(f'{label}: claim {ns}/{claim} is not in the inventory '
                                  f'(it has {names[claim]["namespace"]}/{claim})')
                continue
            found.setdefault(e['id'], []).append(label)
            if pod is None:
                if not guarded:
                    errors.append(f'{label}: claim {ns}/{claim} ({e["id"]}): no guard init container mounts it')
            else:
                errors += guard_errors(label, e, *pod)
    for e in entries:
        users = found.get(e['id'], [])
        if e['origin'] == 'new' or 'copied' in e:
            if len(users) != 1:
                errors.append(f'{e["id"]}: needs exactly one consumer, found '
                              + (f'{len(users)} consumers ({", ".join(users)})' if users else 'no consumer'))
        elif users:
            errors.append(f'{e["id"]}: migrated with no copied date, so nothing may mount it yet; '
                          f'mounted by {", ".join(users)}')
    return errors


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default='.')
    ap.add_argument('--inventory', default=inv.PATH, help='relative to --root')
    a = ap.parse_args(argv)
    root = Path(a.root)
    entries = json.loads((root / a.inventory).read_text())
    errors, _ = inv.validate(entries, 'head')  # check-retained-inventory.py reports these in full
    if not errors:
        errors = check(entries, root)
    for e in errors:
        print(f'ERROR: {e}', file=sys.stderr)
    if not errors:
        print(f'Retained guards OK: {len(entries)} inventory entries')
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
