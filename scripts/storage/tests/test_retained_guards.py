"""Tests for templates/retained-guard.yaml (the one-flag guard layer) and scripts/check-retained-guards.py.

The render tests need helm. Offline, set CHART_CACHE to a directory holding app-template-5.3.0.tgz (and any other
<chart>-<version>.tgz a test renders); without it the check pulls each chart once from its repo, as CI does.
"""
import contextlib
import copy
import importlib.util
import io
import json
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]


def module(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


chk = module('check_retained_guards', 'scripts/check-retained-guards.py')
inv = module('check_retained', 'scripts/check-retained-inventory.py')

APPSET = 'bootstrap/appsets/cluster-apps.yaml'
IMAGE = {'repository': 'nginx', 'tag': '1'}
PYTHON = 'python@sha256:8c9a3bf2d6dea60d60a2ae2a07c2b2fb1e7d8daed64b146b6792c74ae0d62ac4'


def entry(i='f1-flagged', namespace='media', claim=None, origin='new', **kw):
    e = {'id': i, 'namespace': namespace, 'claim': claim or f'{i}-iscsi', 'size': '1Gi', 'class': 'retained',
         'origin': origin}
    e.update(kw)
    return e


def flagged(name='f1', namespace='media', rid='f1-flagged', values=None, **app):
    """An app-template service that opts in with one app.yaml line; values only name an image."""
    v = {'controllers': {'main': {'containers': {'main': {'image': IMAGE}}}}}
    return f'services/{namespace}/{name}', ({'name': name, 'namespace': namespace, 'retained': rid, **app},
                                            inv.merge(v, values or {}))


def guard_container(app='f1-canary', root='/data', name='guard', claim_vol='data', ro=True, cm=True):
    mounts = [{'name': claim_vol, 'mountPath': root, 'readOnly': ro}]
    if cm:
        mounts.append({'name': 'guard', 'mountPath': '/retained-startup', 'readOnly': True})
    return {'name': name, 'image': PYTHON, 'command': ['python3', '-I', '-B', '/retained-startup/guard.py', app, root],
            'volumeMounts': mounts}


def plain(name='f1-canary', namespace='democratic-csi', claim='f1-canary', inits=None):
    """A hand-wired plain Deployment under a kustomize manifests/ dir: the F1 canary's shape."""
    inits = [guard_container()] if inits is None else inits
    deploy = {
        'apiVersion': 'apps/v1', 'kind': 'Deployment', 'metadata': {'name': name},
        'spec': {'template': {'spec': {
            'initContainers': inits,
            'containers': [{'name': 'main', 'image': 'busybox', 'volumeMounts': [{'name': 'data', 'mountPath': '/data'}]}],
            'volumes': [{'name': 'data', 'persistentVolumeClaim': {'claimName': claim}},
                        {'name': 'guard', 'configMap': {'name': 'retained-startup-guard', 'defaultMode': 292}}]}}}}
    rel = f'infrastructure/system/{name}'
    return rel, ({'name': name, 'namespace': namespace, 'manifests': True},
                 {'manifests/kustomization.yaml': {'resources': ['deployment.yaml']},
                  'manifests/deployment.yaml': deploy})


def handwritten(claim='abs-iscsi'):
    """audiobookshelf's hand-written app-template guard, on an iSCSI claim."""
    values = yaml.safe_load((ROOT / 'services/media/audiobookshelf/values.yaml').read_text())
    values['persistence']['retained-config']['existingClaim'] = claim
    return 'services/media/audiobookshelf', (
        yaml.safe_load((ROOT / 'services/media/audiobookshelf/app.yaml').read_text()), values)


def dump(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data if isinstance(data, str) else yaml.safe_dump(data))


def tree(base, apps, appset=None):
    """A repo tree: the real templates/ and AppSet (or an edited AppSet text) plus fixture apps.

    apps maps an app dir to (app.yaml, values.yaml or {relative file: content} for manifests apps).
    """
    d = tempfile.mkdtemp(dir=base)  # a fresh tree per call, so one test can check several
    shutil.copytree(ROOT / 'templates', Path(d, 'templates'))
    dump(Path(d, APPSET), appset if appset is not None else (ROOT / APPSET).read_text())
    for rel, (app, files) in apps.items():
        dump(Path(d, rel, 'app.yaml'), app)
        if app.get('manifests'):
            for name, content in files.items():
                dump(Path(d, rel, name), content)
        elif files is not None:
            dump(Path(d, rel, 'values.yaml'), files)
    return Path(d)


def without_layer():
    """The AppSet with its retained branches removed: no layer file and no retained.id parameter."""
    text = (ROOT / APPSET).read_text()
    edited = re.sub(r'\n *\{\{- if \$retained \}\}.*?\{\{- end \}\}', '', text, flags=re.S)
    assert 'retained-guard.yaml' in text and 'retained-guard.yaml' not in edited, 'no retained branch to drop'
    return edited


class Base(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.dir = d.name

    def check(self, entries, apps, appset=None):
        root = tree(self.dir, dict(apps), appset)
        return chk.check(entries, root)

    def errs_with(self, errors, *words):
        self.assertTrue(any(all(w in e for w in words) for e in errors), errors)

    def render(self, apps, name, appset=None, parameters=True):
        """The rendered docs of one app's chart source, layered from the AppSet as the check does."""
        root = tree(self.dir, dict(apps), appset)
        app = next(a for a in chk.appset_apps(root) if a['name'] == name)
        source = next(s for s in app['sources'] if 'chart' in s)
        if not parameters:
            source = {**source, 'helm': {k: v for k, v in source['helm'].items() if k != 'parameters'}}
        return [d for d in yaml.safe_load_all(chk.render_source(root, app, source)) if d]


def deployment(docs):
    return next(d for d in docs if d['kind'] == 'Deployment')


def mounts(container):
    return {m['name']: (m['mountPath'], m.get('readOnly', False)) for m in container.get('volumeMounts', [])}


class LayerRender(Base):
    def test_flag_renders_guard_first(self):
        dep = deployment(self.render([flagged()], 'f1'))
        pod = dep['spec']['template']['spec']
        guard = pod['initContainers'][0]
        self.assertEqual(guard['name'], '0-retained-guard')
        self.assertEqual(guard['command'], ['python3', '-I', '-B', '/retained-startup/guard.py', 'f1-flagged', '/retained'])
        self.assertNotIn('args', guard)
        self.assertNotIn('env', guard)
        self.assertEqual(guard['image'], PYTHON)
        volumes = {v['name']: v for v in pod['volumes']}
        claim = [n for n, v in volumes.items() if v.get('persistentVolumeClaim')]
        self.assertEqual([volumes[n]['persistentVolumeClaim']['claimName'] for n in claim], ['f1-flagged-iscsi'])
        cm = next(n for n, v in volumes.items() if v.get('configMap'))
        self.assertEqual(volumes[cm]['configMap'], {'name': 'retained-startup-guard', 'defaultMode': 292})
        self.assertEqual(mounts(guard), {claim[0]: ('/retained', True), cm: ('/retained-startup', True)})
        main = pod['containers'][0]
        self.assertEqual(mounts(main), {claim[0]: ('/config', False)})
        self.assertEqual(dep['spec']['strategy'], {'type': 'Recreate'})
        self.assertFalse([d for d in self.render([flagged()], 'f1') if d['kind'] == 'PersistentVolumeClaim'])
        sec = guard['securityContext']
        self.assertEqual((sec['runAsNonRoot'], sec['runAsUser'], sec['runAsGroup']), (True, 1000, 1000))
        self.assertEqual((sec['allowPrivilegeEscalation'], sec['readOnlyRootFilesystem']), (False, True))
        self.assertEqual((sec['capabilities'], sec['seccompProfile']), ({'drop': ['ALL']}, {'type': 'RuntimeDefault'}))

    def test_guard_runs_before_app_init_containers(self):
        values = {'controllers': {'main': {'initContainers': {'aaa-init': {'image': IMAGE}}}},
                  'persistence': {'retained': {'advancedMounts': {'main': {'aaa-init': [{'path': '/seed'}]}}}}}
        pod = deployment(self.render([flagged(values=values)], 'f1'))['spec']['template']['spec']
        self.assertEqual([c['name'] for c in pod['initContainers']], ['0-retained-guard', 'aaa-init'])

    def test_empty_id_fails(self):
        with self.assertRaises(chk.RenderError) as cm:
            self.render([flagged()], 'f1', parameters=False)
        self.assertIn('retained.id is required', str(cm.exception))

    def test_custom_mounts_replace_default(self):
        values = {'persistence': {'retained': {'advancedMounts': {'main': {'main': [{'path': '/data'}]}}}}}
        main = deployment(self.render([flagged(values=values)], 'f1'))['spec']['template']['spec']['containers'][0]
        self.assertEqual([m['mountPath'] for m in main['volumeMounts']], ['/data'])

    def test_unflagged_app_gets_no_layer(self):
        rel, (app, values) = flagged()
        del app['retained']
        root = tree(self.dir, {rel: (app, values)})
        src = next(s for s in chk.appset_apps(root)[0]['sources'] if 'chart' in s)
        self.assertNotIn(chk.LAYER, ' '.join(src['helm']['valueFiles']))
        self.assertNotIn('parameters', src['helm'])


class Coverage(Base):
    def test_flagged_app_passes(self):
        self.assertEqual(self.check([entry()], [flagged()]), [])

    def test_layer_missing_fails(self):
        values = {'persistence': {'retained': {'advancedMounts': {'main': {'main': [{'path': '/data'}]}}}}}
        self.errs_with(self.check([entry()], [flagged(values=values)], without_layer()), 'f1', 'render')

    def test_check_reads_appset_layering(self):
        errors = self.check([entry()], [flagged()], without_layer())
        self.errs_with(errors, 'f1-flagged', 'no consumer')
        self.errs_with(errors, 'f1', 'no guard layer')

    def test_consumer_matched_by_namespace_and_claim(self):
        e = entry(namespace='media')
        for app in (flagged(namespace='tools'),
                    plain(name='hand', namespace='tools', claim='f1-flagged-iscsi',
                          inits=[guard_container(app='f1-flagged')])):
            with self.subTest(app=app[0]):
                errors = self.check([e], [app])
                self.errs_with(errors, 'f1-flagged', 'no consumer')
                self.errs_with(errors, 'tools/f1-flagged-iscsi', 'not in the inventory')
        self.assertEqual(self.check([e], [flagged(namespace='media')]), [])

    def test_new_or_copied_needs_exactly_one_consumer(self):
        hand = plain(name='hand', namespace='media', claim='f1-flagged-iscsi', inits=[guard_container(app='f1-flagged')])
        copied = entry(origin='migrated', copied='2026-12-01')
        for e in (entry(), copied):
            with self.subTest(origin=e['origin']):
                self.errs_with(self.check([e], []), 'f1-flagged', 'no consumer')
                self.errs_with(self.check([e], [hand, plain(name='hand2', namespace='media', claim='f1-flagged-iscsi',
                                                             inits=[guard_container(app='f1-flagged')])]),
                               'f1-flagged', '2 consumers')
                self.assertEqual(self.check([e], [hand]), [])

    def test_migrated_without_copied_needs_none(self):
        e = entry(origin='migrated')
        self.assertEqual(self.check([e], []), [])
        hand = plain(name='hand', namespace='media', claim='f1-flagged-iscsi')
        self.errs_with(self.check([e], [hand]), 'f1-flagged', 'no copied date')

    def test_bad_guard_shapes_fail(self):
        seed = {'name': 'seed', 'image': 'busybox', 'volumeMounts': [{'name': 'data', 'mountPath': '/seed'}]}
        cases = {
            'no guard': [],
            'read-only': [guard_container(ro=False)],
            'first': [seed, guard_container()],
            'retained-startup-guard': [guard_container(cm=False)],
        }
        for word, inits in cases.items():
            with self.subTest(case=word):
                errors = self.check([entry('f1-canary', namespace='democratic-csi', claim='f1-canary')],
                                    [plain(inits=inits)])
                self.errs_with(errors, 'f1-canary', word)

    def test_new_guard_must_name_the_entry(self):
        errors = self.check([entry('f1-canary', namespace='democratic-csi', claim='f1-canary')],
                            [plain(inits=[guard_container(app='other')])])
        self.errs_with(errors, 'f1-canary', 'other')

    def test_new_id_the_guard_refuses_fails(self):
        errors = self.check([entry('x-', namespace='democratic-csi', claim='x')],
                            [plain(claim='x', inits=[guard_container(app='x-')])])
        self.errs_with(errors, 'x-', 'guard.py')

    def test_flag_rules(self):
        cases = [
            ('<id>-iscsi', [entry(claim='f1-flagged-data')], [flagged()]),
            ('migrated', [entry(origin='migrated', copied='2026-12-01')], [flagged()]),
            ('not in the inventory', [], [flagged()]),
            ('non-empty string', [], [flagged(rid='')]),
            ('no guard layer', [entry('f1-canary', namespace='democratic-csi', claim='f1-canary')],
             [(lambda rel, a: (rel, ({**a[0], 'retained': 'f1-canary'}, a[1])))(*plain())]),
        ]
        for word, entries, apps in cases:
            with self.subTest(case=word):
                self.errs_with(self.check(entries, apps), word)

    def test_variant_of_flagged_base_gets_no_layer(self):
        base_rel, base = flagged()
        variant = {'name': 'f1-ru', 'namespace': 'media', 'baseApp': base_rel}
        root = tree(self.dir, {base_rel: base, 'services/media/f1-ru': (variant, None)})
        by_name = {a['name']: a for a in chk.appset_apps(root)}
        src = next(s for s in by_name['f1-ru']['sources'] if 'chart' in s)
        self.assertNotIn(chk.LAYER, ' '.join(src['helm']['valueFiles']))
        self.assertEqual(chk.check([entry()], root), [])  # the variant mounts the NFS /config claim, not the entry

    def test_flagged_app_invisible_to_check_bindings(self):
        root = tree(self.dir, dict([flagged()]))
        self.assertEqual(inv.check_bindings([entry()], root), [])
        self.assertEqual(chk.check([entry()], root), [])

    def test_handwritten_guards_pass(self):
        abs_entry = entry('audiobookshelf', namespace='media', claim='abs-iscsi', origin='migrated', copied='2026-12-01')
        self.assertEqual(self.check([abs_entry], [handwritten()]), [])
        self.assertEqual(self.check([entry('f1-canary', namespace='democratic-csi', claim='f1-canary')], [plain()]), [])

    def test_static_resolver_consumer(self):
        """Charts that are not rendered (loki here) are read through check-retained-inventory.py's resolvers."""
        values = yaml.safe_load((ROOT / 'services/operations/loki/values.yaml').read_text())
        vol = next(v for v in values['singleBinary']['extraVolumes'] if v['name'] == 'retained-data')
        vol['persistentVolumeClaim']['claimName'] = 'loki-iscsi'
        app = yaml.safe_load((ROOT / 'services/operations/loki/app.yaml').read_text())
        del app['manifests']  # the fixture tree has no loki manifests dir
        loki = ('services/operations/loki', (app, values))
        e = entry('loki', namespace='monitoring', claim='loki-iscsi', origin='migrated', copied='2026-12-01')
        self.assertEqual(self.check([e], [loki]), [])
        unguarded = copy.deepcopy(loki)
        init = next(c for c in unguarded[1][1]['singleBinary']['initContainers'] if c['name'] == 'retained-state')
        init['volumeMounts'] = [m for m in init['volumeMounts'] if m['name'] != 'retained-data']
        self.errs_with(self.check([e], [unguarded]), 'loki', 'no guard')

    def test_static_resolver_runs_guard_rules(self):
        """The statically resolved consumers get the full guard rule: guard.py on a read-only claim mount."""
        def loki():
            values = yaml.safe_load((ROOT / 'services/operations/loki/values.yaml').read_text())
            vol = next(v for v in values['singleBinary']['extraVolumes'] if v['name'] == 'retained-data')
            vol['persistentVolumeClaim']['claimName'] = 'loki-iscsi'
            app = yaml.safe_load((ROOT / 'services/operations/loki/app.yaml').read_text())
            app.pop('manifests', None)
            init = next(c for c in values['singleBinary']['initContainers'] if c['name'] == 'retained-state')
            return ('services/operations/loki', (app, values)), init, 'retained-data', entry(
                'loki', namespace='monitoring', claim='loki-iscsi', origin='migrated', copied='2026-12-01')

        def kps(part):
            rel = 'services/operations/kube-prometheus-stack'
            values = yaml.safe_load((ROOT / rel / 'values.yaml').read_text())
            spec = values[part][f'{part}Spec']
            vct = spec['storageSpec' if part == 'prometheus' else 'storage']['volumeClaimTemplate']
            old, vct['metadata']['name'] = vct['metadata']['name'], f'{part}-iscsi'
            init = next(c for c in spec['initContainers'] if c['name'] == 'retained-state')
            next(m for m in init['volumeMounts'] if m['name'] == old)['name'] = f'{part}-iscsi'
            app = yaml.safe_load((ROOT / rel / 'app.yaml').read_text())
            app.pop('manifests', None)
            claim = f'{part}-iscsi-{part}-kube-prometheus-stack-{part}-0'
            return (rel, (app, values)), init, f'{part}-iscsi', entry(
                part, namespace='monitoring', claim=claim, origin='migrated', copied='2026-12-01')

        def chown(init, vol):
            init['command'] = ['sh', '-c', 'chown -R 10001 /data']

        def writable(init, vol):
            next(m for m in init['volumeMounts'] if m['name'] == vol).pop('readOnly')

        def wrong_root(init, vol):
            init['command'][-1] = '/elsewhere'

        for make in (loki, lambda: kps('prometheus'), lambda: kps('alertmanager')):
            app, _, _, e = make()
            with self.subTest(e['id']):
                self.assertEqual(self.check([e], [app]), [])
            for mutate, words in [(chown, ('guard.py',)), (writable, ('read-only',)), (wrong_root, ('not on the claim',))]:
                app, init, vol, e = make()
                mutate(init, vol)
                with self.subTest(e['id'], mutation=mutate.__name__):
                    self.errs_with(self.check([e], [app]), e['id'], *words)

    def test_static_consumer_without_pod_spec_fails(self):
        """A statically read binding whose resolver gives no pod spec cannot be checked: fail closed."""
        app = {'name': 'db', 'namespace': 'databases', 'chart': {'repo': 'https://example.invalid', 'name': 'other',
                                                                 'version': '1.0.0'}}
        values = {'controllers': {'main': {'initContainers': {'guard': {}}}},
                  'persistence': {'data': {'existingClaim': 'db-iscsi', 'advancedMounts': {'main': {'guard': []}}}}}
        e = entry('db', namespace='databases', claim='db-iscsi')
        self.errs_with(self.check([e], [('services/data/db', (app, values))]), 'db-iscsi', 'cannot be checked')


LIVE = 'homelab.starktastic.net/live-secret-data'
# The chart Secrets whose data must go live, by the app that renders them (ADR 0017 genericity audit, finding 4).
LIVE_SECRETS = {'kube-prometheus-stack': 'alertmanager-kube-prometheus-stack-alertmanager', 'authentik': 'authentik',
                'falco': 'falco-falcosidekick', 'democratic-csi': 'democratic-csi-driver-config'}
# The name fallbacks, each for a chart whose Secret template has no annotations key (democratic-csi 0.15.1).
FALLBACKS = {'democratic-csi-driver-config'}


class LiveSecrets(unittest.TestCase):
    def expression(self):
        appset = yaml.safe_load((ROOT / APPSET).read_text())
        rules = [r for r in appset['spec']['template']['spec']['ignoreDifferences'] if r['kind'] == 'Secret']
        self.assertEqual(len(rules), 1, rules)
        [expr] = rules[0]['jqPathExpressions']
        return expr

    def test_live_secret_annotation(self):
        expr = self.expression()
        self.assertIn(f'select(.metadata.annotations["{LIVE}"] != "true"', expr)
        named = set(re.findall(r'\.metadata\.name != "([^"]+)"', expr))
        self.assertEqual(named, FALLBACKS)
        text = (ROOT / APPSET).read_text()
        for app, secret in LIVE_SECRETS.items():
            with self.subTest(secret=secret):
                if secret in FALLBACKS:  # the comment names the chart key that is missing
                    self.assertRegex(text, rf'# - {re.escape(secret)}: [^\n]*has no annotations key',
                                     'undocumented name fallback')
                    continue
                apps = {a['name']: a for a in chk.appset_apps(ROOT)}
                source = next(s for s in apps[app]['sources'] if 'chart' in s)
                cache = Path(os.environ.get('CHART_CACHE', '/nonexistent'))
                wanted = f'{source["chart"]}-{source["targetRevision"]}.tgz'
                if os.environ.get('CHART_CACHE') and not (cache / wanted).is_file():
                    self.skipTest(f'offline and {wanted} is not in CHART_CACHE')
                docs = yaml.safe_load_all(chk.render_source(ROOT, apps[app], source))
                found = [d for d in docs if d and d['kind'] == 'Secret' and d['metadata']['name'] == secret]
                self.assertEqual(len(found), 1, secret)
                self.assertEqual((found[0]['metadata'].get('annotations') or {}).get(LIVE), 'true')


class Cli(Base):
    def test_cli_reads_the_inventory(self):
        root = tree(self.dir, dict([flagged()]))
        inventory = root / inv.PATH
        dump(inventory, json.dumps([entry()]))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(chk.main(['--root', str(root)]), 0)
        dump(inventory, json.dumps([]))
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(chk.main(['--root', str(root)]), 1)
        self.assertIn('not in the inventory', err.getvalue())


if __name__ == '__main__':
    unittest.main()
