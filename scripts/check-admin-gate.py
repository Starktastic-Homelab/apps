#!/usr/bin/env python3
"""Check the internal admin gate (ADR 0014); run from the repo root.

Renders what ArgoCD applies (the authentik manifests, both config charts, every app's manifests and every
ingress-chart app) and fails closed on anything that would open or bypass the gate:

  1. the gate middleware's forwardAuth target and options
  2. a forwardAuth address carrying ?app= (the outpost ignores it, so it only misleads; one temporary exemption)
  3. a gate outpost that isn't 1 replica with the Recreate strategy
  4. a gate outpost image other than ghcr.io/goauthentik/proxy at the ldap outpost's tag
  5. a gate-host route not on websec-int only
  6. a route through the gate middleware not on websec-int only, or with a non-.internal host
  7. a middleware reference that names a Middleware absent from the render
  8. AUTHENTIK_COOKIE_DOMAIN in authentik's values or any rendered workload env
  9. more than one route for the gate host

Missing entryPoints count as every entrypoint, and any kind: Ingress fails, since its middlewares hide in
annotations. Rules 1, 3, 4 and 9 are mandatory: a render without the gate middleware, outpost or route fails.
check-homepage-household.py guards the household page; this script doesn't repeat it. Output names objects
only: the render holds SealedSecrets.
"""

from __future__ import annotations

import glob
import os
import re
import subprocess
import sys
from urllib.parse import parse_qs, urlsplit

import yaml

GATE_MW = "authentik-internal-gate"
GATE_NS = "authentik"
GATE_ADDR = "http://ak-outpost-internal-gate.authentik:9000/outpost.goauthentik.io/auth/traefik"
GATE_OUTPOST = "ak-outpost-internal-gate"
LDAP_OUTPOST = "ak-outpost-ldap-outpost"
PROXY_IMAGE = "ghcr.io/goauthentik/proxy"
AUTH_HOST = "auth.internal.starktastic.net"
ADMIN_HOST = "admin.internal.starktastic.net"
INTERNAL = "internal.starktastic.net"
GATE_EP = ["websec-int"]
COOKIE_VAR = "AUTHENTIK_COOKIE_DOMAIN"
GATED: set[str] = {ADMIN_HOST}
# Temporary: the old admin middleware keeps ?app=admin-auth until Task 9 (PR 4) deletes it with
# middleware-admin.yaml; delete this exemption in that same change.
APP_PARAM_EXEMPT = ("authentik", "authentik-admin-middleware")

GLOBALS = "templates/globals.yaml"
AUTHENTIK_VALUES = "infrastructure/controllers/authentik/values.yaml"
HOST_RE = re.compile(r"Host(?:Regexp)?\(([^)]*)\)")
WORKLOADS = {"Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob", "Pod"}


def _id(doc: dict) -> str:
    meta = doc.get("metadata") or {}
    return f"{doc.get('kind')} {meta.get('namespace') or '-'}/{meta.get('name')}"


def _hosts(match: object) -> list[str] | None:
    """Host(`...`) values in a route match, lowercased; None if any host is a regexp or not a plain literal."""
    if not isinstance(match, str):
        return None
    hosts = []
    for call in HOST_RE.finditer(match):
        if call.group(0).startswith("HostRegexp"):
            return None
        literals = re.findall(r"`([^`]*)`", call.group(1))
        if not literals:
            return None
        hosts += [h.lower() for h in literals]
    return hosts


def _env_names(doc: dict) -> list[str]:
    names = []
    for key, value in _walk(doc.get("spec") or {}):
        if key in ("containers", "initContainers") and isinstance(value, list):
            names += [e.get("name") for c in value if isinstance(c, dict) for e in c.get("env") or []
                      if isinstance(e, dict)]
    return names


def _walk(node):
    if isinstance(node, dict):
        for key, value in node.items():
            yield key, value
            yield from _walk(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk(item)


def problems(docs: list[dict], gated: set[str]) -> list[str]:
    # gated: the hosts Task 6's per-host rules check; nothing in rules 1-9 reads it yet.
    found = []
    by_id = {}
    middlewares = set()
    gate_like = {(GATE_NS, GATE_MW)}  # also any copy that targets the gate outpost
    routes = []
    for doc in docs:
        kind, meta = doc.get("kind"), doc.get("metadata") or {}
        by_id[(kind, meta.get("namespace"), meta.get("name"))] = doc
        if kind == "Middleware":
            middlewares.add((meta.get("namespace"), meta.get("name")))
            address = ((doc.get("spec") or {}).get("forwardAuth") or {}).get("address")
            query = parse_qs(urlsplit(address).query, keep_blank_values=True) if isinstance(address, str) else {}
            if (address is not None and (meta.get("namespace"), meta.get("name")) != APP_PARAM_EXEMPT
                    and (not isinstance(address, str) or "app" in query)):
                found.append(f"rule 2: {_id(doc)} forwardAuth address carries ?app=")
            # Short name, .svc or FQDN: the first DNS label names the outpost Service.
            if isinstance(address, str) and (urlsplit(address).hostname or "").split(".")[0] == GATE_OUTPOST:
                gate_like.add((meta.get("namespace"), meta.get("name")))
        elif kind == "IngressRoute":
            routes.append(doc)
        elif kind == "Ingress":
            found.append(f"{_id(doc)}: kind Ingress is not allowed (use an IngressRoute)")
        if kind in WORKLOADS and COOKIE_VAR in _env_names(doc):
            found.append(f"rule 8: {_id(doc)} sets {COOKIE_VAR}")

    gate_mw = by_id.get(("Middleware", GATE_NS, GATE_MW))
    outpost = by_id.get(("Deployment", GATE_NS, GATE_OUTPOST))
    gate_routes = []
    for route in routes:
        spec = route.get("spec") or {}
        entry_points = spec.get("entryPoints")  # missing means every entrypoint
        ns = (route.get("metadata") or {}).get("namespace")
        uses_gate = False
        for rule in spec.get("routes") or []:
            hosts = _hosts(rule.get("match"))
            to_outpost = any((svc.get("namespace") or ns, svc.get("name")) == (GATE_NS, GATE_OUTPOST)
                             for svc in rule.get("services") or [] if isinstance(svc, dict))
            # A HostRegexp or unparsable match may serve the gate host: fail closed. Traefik v3 ranks routes by rule
            # length, not by Host, so a host-less match can win; the only ones (the PathPrefix(`/`) catch-alls on
            # web and web-int) redirect to api@internal. Any route to the outpost Service is a gate route.
            if hosts is None or AUTH_HOST in hosts or to_outpost:
                gate_routes.append(route)
                if entry_points != GATE_EP:
                    found.append(f"rule 5: {_id(route)} may serve {AUTH_HOST} on {entry_points or 'every entrypoint'}")
            for ref in rule.get("middlewares") or []:
                ref = ref if isinstance(ref, dict) else {}
                name, ref_ns = ref.get("name"), ref.get("namespace") or ns
                if (ref_ns, name) not in middlewares:
                    found.append(f"rule 7: {_id(route)} references missing Middleware {ref_ns}/{name}")
                if (ref_ns, name) in gate_like:
                    uses_gate = True
                    if not hosts or any(h != INTERNAL and not h.endswith("." + INTERNAL) for h in hosts):
                        found.append(f"rule 6: {_id(route)} sends a non-.internal host through {GATE_MW}")
        if uses_gate and entry_points != GATE_EP:
            found.append(f"rule 6: {_id(route)} uses {GATE_MW} on {entry_points or 'every entrypoint'}")

    fwd = ((gate_mw or {}).get("spec") or {}).get("forwardAuth") or {}
    if (fwd.get("address") != GATE_ADDR or fwd.get("trustForwardHeader") is not True
            or fwd.get("maxResponseBodySize") != 4194304 or "X-authentik-jwt" in (fwd.get("authResponseHeaders") or [])):
        found.append(f"rule 1: Middleware {GATE_NS}/{GATE_MW} is missing or its forwardAuth isn't the gate's")
    spec = (outpost or {}).get("spec") or {}
    if spec.get("replicas") != 1 or (spec.get("strategy") or {}).get("type") != "Recreate":
        found.append(f"rule 3: Deployment {GATE_NS}/{GATE_OUTPOST} is missing or not 1 replica with Recreate")
    images = [c.get("image") for c in (spec.get("template") or {}).get("spec", {}).get("containers") or []]
    ldap = (by_id.get(("Deployment", GATE_NS, LDAP_OUTPOST)) or {}).get("spec") or {}
    ldap_tags = {c.get("image", "").rpartition(":")[2] for c in ldap.get("template", {}).get("spec", {}).get(
        "containers") or []}
    if len(ldap_tags) != 1 or images != [f"{PROXY_IMAGE}:{next(iter(ldap_tags))}"]:
        found.append(f"rule 4: {GATE_OUTPOST} image {images} isn't {PROXY_IMAGE} at the ldap outpost's tag")
    if len(gate_routes) != 1:
        found.append(f"rule 9: {len(gate_routes)} IngressRoutes match {AUTH_HOST}, want exactly 1")
    return found


def values_problems(values: dict) -> list[str]:
    """Rule 8 on authentik's chart values: an env entry, or the chart's authentik.cookie_domain key."""
    for key, value in _walk(values):
        if (key == "name" and value == COOKIE_VAR) or key == "cookie_domain":
            return [f"rule 8: {AUTHENTIK_VALUES} sets {COOKIE_VAR}"]
    return []


# --- self-check fixtures -----------------------------------------------------------------------------------------


def _mw(name: str, address: str, ns: str = GATE_NS, **extra) -> dict:
    return {"kind": "Middleware", "metadata": {"name": name, "namespace": ns},
            "spec": {"forwardAuth": {"address": address, **extra}}}


def _deploy(name: str, image: str, replicas=1, strategy="Recreate", env=None) -> dict:
    return {"kind": "Deployment", "metadata": {"name": name, "namespace": GATE_NS},
            "spec": {"replicas": replicas, "strategy": {"type": strategy}, "template": {"spec": {
                "containers": [{"name": "c", "image": image, "env": env or []}]}}}}


def _route(name: str, match: str, middlewares=(), entry_points=("websec-int",), ns: str = "operations",
           service: str | None = None) -> dict:
    spec = {"routes": [{"match": match, "kind": "Rule", "middlewares": [dict(m) for m in middlewares],
                        "services": [{"name": service or name, "port": 3000}]}]}
    if entry_points is not None:
        spec["entryPoints"] = list(entry_points)
    return {"kind": "IngressRoute", "metadata": {"name": name, "namespace": ns}, "spec": spec}


def _valid() -> list[dict]:
    gate_ref = {"name": GATE_MW, "namespace": GATE_NS}
    return [
        _mw(GATE_MW, GATE_ADDR, trustForwardHeader=True, maxResponseBodySize=4194304,
            authResponseHeaders=["X-authentik-username", "X-authentik-groups"]),
        _mw("authentik-middleware", "http://authentik-server.authentik/outpost.goauthentik.io/auth/traefik"),
        _deploy(LDAP_OUTPOST, "ghcr.io/goauthentik/ldap:2026.8.5"),
        _deploy(GATE_OUTPOST, f"{PROXY_IMAGE}:2026.8.5"),
        _route("authentik-internal-gate-route",
               f"Host(`{AUTH_HOST}`) && PathPrefix(`/outpost.goauthentik.io/`)", ns=GATE_NS, service=GATE_OUTPOST),
        _route("homepage-admin", f"Host(`{ADMIN_HOST}`)", [gate_ref]),
        # An unqualified ref means the route's own namespace.
        _route("local", "Host(`x.starktastic.net`)", [{"name": "authentik-middleware"}], ["websecure"], GATE_NS),
    ]


def _replace(docs: list[dict], kind: str, name: str, new: dict) -> list[dict]:
    return [new if (d["kind"], d["metadata"]["name"]) == (kind, name) else d for d in docs]


def _bad_cases() -> dict[str, tuple[list[dict], str]]:
    valid = _valid()
    gate_ref = {"name": GATE_MW, "namespace": GATE_NS}
    return {  # name: (docs, text one problem must contain)
        "1 gate middleware with another address": (_replace(valid, "Middleware", GATE_MW, _mw(
            GATE_MW, "http://authentik-server.authentik/outpost.goauthentik.io/auth/traefik",
            trustForwardHeader=True, maxResponseBodySize=4194304)), "rule 1"),
        "1 gate middleware missing": ([d for d in valid if d["metadata"]["name"] != GATE_MW], "rule 1"),
        "3 every gate object missing": ([d for d in valid if d["metadata"]["name"] not in (
            GATE_MW, GATE_OUTPOST, "authentik-internal-gate-route")], "rule 3"),
        "2 forwardAuth address with ?app=": (valid + [_mw("x", GATE_ADDR + "?app=admin-auth")], "rule 2"),
        "2 exempt name in another namespace with ?app=": (valid + [_mw(
            APP_PARAM_EXEMPT[1], GATE_ADDR + "?app=admin-auth", ns="operations")], "rule 2"),
        "2 forwardAuth address with a blank ?app=": (valid + [_mw("x", GATE_ADDR + "?app=")], "rule 2"),
        "3 outpost with replicas: 2": (_replace(valid, "Deployment", GATE_OUTPOST, _deploy(
            GATE_OUTPOST, f"{PROXY_IMAGE}:2026.8.5", replicas=2)), "rule 3"),
        "4 outpost tag differs from ldap's": (_replace(valid, "Deployment", GATE_OUTPOST, _deploy(
            GATE_OUTPOST, f"{PROXY_IMAGE}:2026.8.4")), "rule 4"),
        "5 gate route on websecure": (_replace(valid, "IngressRoute", "authentik-internal-gate-route", _route(
            "authentik-internal-gate-route", f"Host(`{AUTH_HOST}`)", entry_points=["websecure"], ns=GATE_NS)),
            "rule 5"),
        "5 websecure route to the outpost Service": (valid + [_route(
            "outpost", "Host(`x.starktastic.net`)", entry_points=["websecure"], service=GATE_OUTPOST,
            ns=GATE_NS)], "rule 5"),
        "5 HostRegexp route on websecure": (valid + [_route(
            "regexp", "HostRegexp(`^.+\\.starktastic\\.net$`)", entry_points=["websecure"])], "rule 5"),
        "6 gate middleware route with no entryPoints": (valid + [_route(
            "open", "Host(`x.internal.starktastic.net`)", [gate_ref], entry_points=None)], "rule 6"),
        "6 gate-outpost copy on websecure": (valid + [_mw("copy", GATE_ADDR, ns="operations"), _route(
            "copied", "Host(`z.internal.starktastic.net`)", [{"name": "copy"}], ["websecure"])], "rule 6"),
        "6 short-name gate-outpost copy on websecure": (valid + [_mw(
            "short", f"http://{GATE_OUTPOST}:9000/outpost.goauthentik.io/auth/traefik", ns=GATE_NS), _route(
            "shorted", "Host(`z.internal.starktastic.net`)", [{"name": "short"}], ["websecure"], GATE_NS)],
            "rule 6"),
        "7 dangling middleware ref (own namespace)": (valid + [_route(
            "dangling", "Host(`y.starktastic.net`)", [{"name": "authentik-middleware"}], ["websecure"])], "rule 7"),
        "8 cookie domain in a Deployment env": (valid + [_deploy(
            "authentik-server", "x:1", env=[{"name": COOKIE_VAR, "value": "starktastic.net"}])], "rule 8"),
        "9 second route for the gate host": (valid + [_route(
            "second", f"Host(`{AUTH_HOST}`)", ns=GATE_NS)], "rule 9"),
        "Ingress kind": (valid + [{"kind": "Ingress", "metadata": {"name": "i", "namespace": "x"}}], "Ingress"),
    }


def self_check() -> None:
    found = problems(_valid(), GATED)
    assert found == [], f"self-check: valid set failed: {found}"
    for name, (docs, expected) in _bad_cases().items():
        found = problems(docs, GATED)
        assert any(expected in p for p in found), f"self-check: case {name!r} gave {found}"
    exempt = _mw(APP_PARAM_EXEMPT[1], "http://authentik-server.authentik/outpost.goauthentik.io/auth/traefik"
                 "?app=admin-auth", ns=APP_PARAM_EXEMPT[0])
    assert problems(_valid() + [exempt], GATED) == [], "self-check: the temporary ?app= exemption failed"
    assert values_problems({"global": {"env": [{"name": "X", "value": "1"}]}}) == []
    for bad in ({"server": {"env": [{"name": COOKIE_VAR, "value": "x"}]}},
                {"authentik": {"cookie_domain": "starktastic.net"}}):
        assert any("rule 8" in p for p in values_problems(bad)), f"self-check: values {bad} passed"
    print("self-check ok")


# --- render ------------------------------------------------------------------------------------------------------


def load_yaml(path: str) -> dict:
    with open(path) as handle:
        return yaml.safe_load(handle) or {}


def helm(*args: str) -> str:
    return subprocess.run(["helm", "template", *args], capture_output=True, text=True, check=True).stdout


def _docs(text: str, namespace: str | None) -> list[dict]:
    out = []
    for doc in yaml.safe_load_all(text):
        if isinstance(doc, dict) and doc.get("kind"):
            meta = doc.setdefault("metadata", {})
            if namespace and not meta.get("namespace"):
                meta["namespace"] = namespace  # ArgoCD's destination namespace
            out.append(doc)
    return out


def render() -> list[dict]:
    docs = []
    for chart in ("infrastructure/base-configs", "infrastructure/configs"):
        docs += _docs(helm("configs", chart, "-f", GLOBALS), None)

    # The same globs as cluster-apps.yaml: apps nest deeper than two levels (infrastructure/controllers/databases).
    paths = glob.glob("services/**/app.yaml", recursive=True) + glob.glob("infrastructure/**/app.yaml", recursive=True)
    apps = {os.path.dirname(p): load_yaml(p) for p in sorted(paths)}
    for path, app in apps.items():
        ns = app.get("namespace")
        manifests = f"{path}/manifests"
        if app.get("manifests"):
            if app.get("helmManifests"):
                docs += _docs(helm(app["name"], manifests, "-f", GLOBALS), ns)
            elif os.path.exists(f"{manifests}/kustomization.yaml"):
                kust = load_yaml(f"{manifests}/kustomization.yaml")
                for res in kust.get("resources") or []:
                    with open(f"{manifests}/{res}") as handle:  # a directory resource raises: fail closed
                        docs += _docs(handle.read(), kust.get("namespace") or ns)
            else:
                for file in sorted(glob.glob(f"{manifests}/*.yaml") + glob.glob(f"{manifests}/*.yml")):
                    with open(file) as handle:
                        docs += _docs(handle.read(), ns)
        if path.startswith("services/") and (app.get("ingress") or {}).get("enabled"):
            layers = ["-f", GLOBALS]
            if app.get("baseApp"):
                layers += ["-f", f"{app['baseApp']}/app.yaml"]
            docs += _docs(helm(app["name"], "templates/ingress-chart", *layers, "-f", f"{path}/app.yaml"), ns)
    return docs


def main() -> int:
    self_check()
    docs = render()
    found = problems(docs, GATED) + values_problems(load_yaml(AUTHENTIK_VALUES))
    if found:
        print(f"Internal admin gate FAILED ({len(found)} problems)")
        for problem in found:
            print(f"  {problem}")
        return 1
    print(f"Internal admin gate OK (ADR 0014): {len(docs)} documents")
    return 0


if __name__ == "__main__":
    sys.exit(main())
