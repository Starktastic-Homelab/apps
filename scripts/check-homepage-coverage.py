#!/usr/bin/env python3
"""Verify both Homepage dashboards list every service that has an ingress.

The two Homepage instances are configured by hand-written ConfigMaps. Nothing
otherwise connects a new service's IngressRoute to those ConfigMaps, so a
service can be deployed and reachable while remaining invisible on every
dashboard. This check closes that gap.

Hosts are discovered from three places, mirroring how the cluster actually
defines them:

  * ``app.yaml`` files consumed by ``templates/ingress-chart`` (the common case,
    including variants that inherit ``domainType`` from a ``baseApp``)
  * the ``infrastructure/configs`` chart, which templates its hostnames through
    ``templates/globals.yaml``
  * standalone IngressRoute manifests that hard-code a ``Host()`` rule

Dashboard coverage is read by rendering each Homepage manifests chart and
walking the embedded ``services.yaml`` and ``bookmarks.yaml`` for ``href``
values. Rendering also proves the embedded YAML still parses, which is easy to
break because it is YAML nested inside a Helm-escaped ConfigMap.

Run with no arguments from the repository root.
"""

from __future__ import annotations

import glob
import re
import subprocess
import sys

import yaml

GLOBALS = "templates/globals.yaml"
CONFIGS_CHART = "infrastructure/configs"
DASHBOARDS = {
    "admin": "services/operations/homepage-admin/manifests",
    "user": "services/operations/homepage/manifests",
}

# Neither dashboard lists itself as a service.
EXCLUDED_HOSTS = {"starktastic.net", "admin.starktastic.net"}

HOST_RE = re.compile(r"Host\(`([^`]+)`\)")
VAR_RE = re.compile(r"\{\{HOMEPAGE_VAR_[A-Z0-9_]+\}\}")


def load_yaml(path: str) -> dict:
    with open(path) as handle:
        return yaml.safe_load(handle) or {}


def domains() -> dict[str, str]:
    return load_yaml(GLOBALS)["global"]["domains"]


def fqdn(host: str, domain_type: str, doms: dict[str, str]) -> str:
    domain = doms[domain_type]
    return domain if not host else f"{host}.{domain}"


def app_yaml_hosts(doms: dict[str, str]) -> dict[str, str]:
    """Map FQDN -> app.yaml path for every ingress-enabled app."""
    apps = {}
    for path in glob.glob("services/*/*/app.yaml") + glob.glob("infrastructure/*/*/app.yaml"):
        apps[path] = load_yaml(path)

    found = {}
    for path, app in apps.items():
        ingress = app.get("ingress") or {}
        if not ingress.get("enabled"):
            continue
        domain_type = ingress.get("domainType")
        if domain_type is None:
            # Variants (e.g. radarr-ru) inherit every ingress field but `host`
            # from the app they are based on.
            base = app.get("baseApp")
            base_ingress = (apps.get(f"{base}/app.yaml") or {}).get("ingress") or {}
            domain_type = base_ingress.get("domainType")
            if domain_type is None:
                raise ValueError(
                    f"{path}: cannot determine domainType; baseApp={base!r} "
                    "not found or has no ingress.domainType"
                )
        found[fqdn(ingress.get("host", ""), domain_type, doms)] = path
    return found


def rendered_hosts() -> dict[str, str]:
    """Hostnames templated by the infrastructure/configs chart."""
    out = subprocess.run(
        ["helm", "template", "configs", CONFIGS_CHART, "-f", GLOBALS],
        capture_output=True, text=True, check=True,
    ).stdout
    return {host: CONFIGS_CHART for host in HOST_RE.findall(out)}


def static_hosts() -> dict[str, str]:
    """Hostnames hard-coded in standalone IngressRoute manifests."""
    found = {}
    for path in glob.glob("services/*/*/manifests/**/*.yaml", recursive=True) + glob.glob(
        "infrastructure/*/*/manifests/**/*.yaml", recursive=True
    ):
        with open(path) as handle:
            text = handle.read()
        if "IngressRoute" not in text:
            continue
        for host in HOST_RE.findall(text):
            if "{{" not in host:
                found[host] = path
    return found


def hrefs(node) -> list[str]:
    """Every href value anywhere in a parsed services.yaml or bookmarks.yaml."""
    if isinstance(node, dict):
        out = []
        for key, value in node.items():
            if key == "href" and isinstance(value, str):
                out.append(value)
            else:
                out.extend(hrefs(value))
        return out
    if isinstance(node, list):
        return [href for item in node for href in hrefs(item)]
    return []


def all_urls(node) -> list[str]:
    """Every href, siteMonitor, and widget url value in a parsed YAML tree."""
    if isinstance(node, dict):
        out = []
        for key, value in node.items():
            if key in ("href", "siteMonitor") and isinstance(value, str):
                out.append(value)
            elif key == "url" and isinstance(value, str):
                out.append(value)
            else:
                out.extend(all_urls(value))
        return out
    if isinstance(node, list):
        return [url for item in node for url in all_urls(item)]
    return []


def is_internal_host(host: str, internal_domain: str) -> bool:
    """True when host is exactly the internal domain or a subdomain of it."""
    return host == internal_domain or host.endswith("." + internal_domain)


def dashboard_hosts(chart: str) -> tuple[set[str], set[str]]:
    """Render a Homepage chart and collect hosts for coverage and leak checks.

    Returns (coverage_hosts, all_url_hosts) where coverage_hosts contains only
    href-derived hosts (used for coverage), and all_url_hosts is the union of
    href, siteMonitor, and widget.url hosts (used for the internal-leak check).

    Also asserts that the embedded YAML parses; a syntax error here fails the
    check rather than silently shipping a blank dashboard.
    """
    out = subprocess.run(
        ["helm", "template", "homepage", chart],
        capture_output=True, text=True, check=True,
    ).stdout

    coverage: set[str] = set()
    all_url_hosts: set[str] = set()
    found_expected_keys = False
    for doc in yaml.safe_load_all(out):
        if not doc or doc.get("kind") != "ConfigMap":
            continue
        for name, body in (doc.get("data") or {}).items():
            if not name.endswith(".yaml") or not body.strip():
                continue
            parsed = yaml.safe_load(VAR_RE.sub("x", body))
            if name in ("services.yaml", "bookmarks.yaml"):
                found_expected_keys = True
                for href in hrefs(parsed):
                    match = re.match(r"https?://([^/]+)", href)
                    if match:
                        coverage.add(match.group(1))
                for url in all_urls(parsed):
                    match = re.match(r"https?://([^/]+)", url)
                    if match:
                        all_url_hosts.add(match.group(1))
    if not found_expected_keys:
        print(
            "ERROR: %s/templates/configmap.yaml missing expected keys: "
            "services.yaml and/or bookmarks.yaml" % chart,
            file=sys.stderr,
        )
    return coverage, all_url_hosts


def check_secrets(chart_label: str, chart_path: str) -> list[str]:
    """Return failure messages for any HOMEPAGE_VAR_* referenced but not sealed."""
    configmap_path = f"{chart_path}/templates/configmap.yaml"
    secrets_path = f"{chart_path}/templates/secrets.yaml"

    with open(configmap_path) as fh:
        referenced = set(re.findall(r"HOMEPAGE_VAR_[A-Z0-9_]+", fh.read()))

    try:
        sealed = set((load_yaml(secrets_path).get("spec") or {}).get("encryptedData") or {})
    except FileNotFoundError:
        sealed = set()

    missing = sorted(referenced - sealed)
    return [
        f"secret not sealed ({chart_label}): {var}" for var in missing
    ]


def main() -> int:
    doms = domains()
    internal = doms["internal"]

    all_hosts = {**app_yaml_hosts(doms), **rendered_hosts(), **static_hosts()}
    all_hosts = {h: src for h, src in all_hosts.items() if h not in EXCLUDED_HOSTS}

    admin, admin_all = dashboard_hosts(DASHBOARDS["admin"])
    user, user_all = dashboard_hosts(DASHBOARDS["user"])

    failures: list[str] = []

    for chart_label, chart_path in DASHBOARDS.items():
        failures.extend(check_secrets(chart_label, chart_path))

    for host, source in sorted(all_hosts.items()):
        if host not in admin:
            failures.append(f"missing from admin dashboard: {host}  ({source})")

    for host, source in sorted(all_hosts.items()):
        if is_internal_host(host, internal):
            continue
        if host not in user:
            failures.append(f"missing from user dashboard: {host}  ({source})")

    for host in sorted(user_all):
        if is_internal_host(host, internal):
            failures.append(f"internal host leaked onto user dashboard: {host}")

    if failures:
        print(f"Homepage coverage check FAILED ({len(failures)} problems)\n")
        for failure in failures:
            print(f"  {failure}")
        return 1

    print(f"Homepage coverage OK: {len(all_hosts)} hosts, both dashboards consistent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
