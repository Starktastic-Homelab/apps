#!/usr/bin/env python3
"""Check the household Homepage boundary (ADR 0018); run from the repo root.

Every Authentik account reaches the household dashboard (starktastic.net), and Homepage proxies for whoever loads it.
This renders the household manifests chart and fails on what no scoped credential can contain:

  * a widget type no credential can scope: prometheusmetric, prometheus, navidrome
  * a fetched URL (widget url, iCal feed, siteMonitor, suggestionUrl) that isn't an in-cluster
    <service>.<namespace> or a public https name, so no IP literal and no internal or LAN name
  * a {{HOMEPAGE_VAR_*}} placeholder outside a service widget block (those fields reach every browser)
  * calendar integrations that aren't a list (Homepage strips feed URLs only from the list form)

It is separate from check-homepage-coverage.py and reads only the rendered ConfigMap, so it holds however that
ConfigMap is written.
"""

from __future__ import annotations

import glob
import re
import subprocess
import sys
from urllib.parse import urlsplit

import yaml

CHART = "services/operations/homepage/manifests"
CONFIGMAP = "homepage-config"
BANNED_TYPES = {"prometheusmetric", "prometheus", "navidrome"}
URL_KEYS = {"url", "siteMonitor", "suggestionUrl"}
LABEL = r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?"
NOT_PUBLIC_TLDS = {
    "arpa", "corp", "example", "home", "internal", "intranet", "invalid", "lan", "local",
    "localdomain", "localhost", "private", "svc", "test",
}
PLACEHOLDER_RE = re.compile(r"\{\{(HOMEPAGE_VAR_[A-Z0-9_]+)\}\}")
NAME_RE = re.compile(r"HOMEPAGE_VAR_[A-Z0-9_]+")

NS, INTERNAL = {"media", "monitoring", "operations"}, "internal.starktastic.net"
URL_OK = [
    "http://sonarr.media:8989/feed/v3/calendar/Sonarr.ics?apikey=HOMEPAGE_VAR_SONARR_KEY",
    "https://search.starktastic.net/search?q=",
    "http://searxng.operations:8080/autocompleter?q=",
]
URL_BAD = [
    True, "", "/#pulse", "ftp://x.media", "https://10.9.9.20:8006", "http://0x0a090914", "http://167772161",
    "http://012.011.010.024", "http://[::1]:3000", "http://localhost:3000", "http://sonarr:8989",
    "http://sonarr.nosuch:8989", "http://sonarr.media:99999", "http://search.starktastic.net",
    "https://truenas.internal.starktastic.net", "https://pve.mgmt.arpa", "https://nas.lan",
    "https://argocd-server.argocd.svc.cluster.local:443", "http://HOMEPAGE_VAR_HOST:80", "https://user:pw@10.9.9.1",
]
GOOD = {
    "services.yaml": """\
- G:
    - T:
        href: https://books.benplus.app
        siteMonitor: http://calibre-web.media:8083/opds
        widget:
          type: calendar
          integrations:
            - type: ical
              url: http://sonarr.media:8989/feed.ics?apikey={{HOMEPAGE_VAR_K}}
""",
    "settings.yaml": "title: T\n",
    "widgets.yaml": """\
- search:
    provider: custom
    url: https://search.starktastic.net/search?q=
    suggestionUrl: http://searxng.operations:8080/autocompleter?q=
""",
}
BAD = {  # name: (files that replace GOOD's, None deletes one; text one problem must contain)
    "banned type in a widgets list": ({"services.yaml": "- G:\n    - T:\n        widgets:\n"
        "          - type: prometheusmetric\n            url: http://prometheus.monitoring:9090\n"},
        "banned widget type prometheusmetric"),
    "LAN siteMonitor in a nested group": ({"services.yaml": "- G:\n    - Sub:\n        - T:\n"
        "            siteMonitor: https://10.9.9.20:8006\n"}, "siteMonitor is not"),
    "non-string siteMonitor": ({"services.yaml": "- G:\n    - T:\n        siteMonitor: true\n"}, "siteMonitor is not"),
    "placeholder in a tile field": ({"services.yaml": "- G:\n    - T:\n"
        "        href: https://x.starktastic.net/?k={{HOMEPAGE_VAR_K}}\n"},
        "placeholder outside a service widget block: HOMEPAGE_VAR_K"),
    "placeholder in settings.yaml": ({"settings.yaml": "title: {{HOMEPAGE_VAR_K}}\n"},
        "placeholder outside a service widget block: HOMEPAGE_VAR_K"),
    "LAN suggestionUrl in settings.yaml": ({"settings.yaml": "quicklaunch:\n"
        "  suggestionUrl: http://10.9.9.1:3000/complete?q=\n"}, "suggestionUrl is not"),
    "integrations as a mapping": ({"services.yaml": "- G:\n    - T:\n        widget:\n          type: calendar\n"
        "          integrations:\n            tv:\n              type: ical\n"
        "              url: http://sonarr.media:8989/x\n"}, "integrations must be a list"),
    "missing services.yaml": ({"services.yaml": None}, "missing services.yaml"),
}


def url_ok(url: object, namespaces: set[str], internal: str) -> bool:
    """True for http(s)://<service>.<namespace> (declared namespace) or a public https name."""
    if not isinstance(url, str):
        return False
    try:
        parts = urlsplit(url)
        parts.port  # raises ValueError for a port out of range
    except ValueError:
        return False
    host = parts.hostname or ""
    if parts.scheme not in ("http", "https"):
        return False
    match = re.fullmatch(rf"{LABEL}\.({LABEL})", host)
    if match and match.group(1) in namespaces:
        return True
    # An alphabetic TLD rules out every IPv4 spelling; brackets rule out IPv6.
    return (
        parts.scheme == "https"
        and re.fullmatch(rf"(?:{LABEL}\.)+[a-z]{{2,63}}", host) is not None
        and host.rsplit(".", 1)[1] not in NOT_PUBLIC_TLDS
        and host != internal
        and not host.endswith("." + internal)
    )


def walk(node, skip=frozenset()):
    """Yield (key, value) for every mapping entry, not descending into values whose key is in skip."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield key, value
            if key not in skip:
                yield from walk(value, skip)
    elif isinstance(node, list):
        for item in node:
            yield from walk(item, skip)


def problems(data: dict[str, str], namespaces: set[str], internal: str) -> list[str]:
    found = []
    parsed = {}
    for name in ("services.yaml", "settings.yaml", "widgets.yaml"):
        if name not in data:
            found.append(f"missing {name}")
        else:
            # Strip the braces so {{...}} doesn't parse as a YAML flow mapping.
            parsed[name] = yaml.safe_load(PLACEHOLDER_RE.sub(r"\1", data[name])) or []
    services = parsed.get("services.yaml", [])

    for key, value in walk(services):
        if key == "type" and value in BANNED_TYPES:
            found.append(f"services.yaml: banned widget type {value}")
        if key == "integrations" and not isinstance(value, list):
            found.append("services.yaml: integrations must be a list")
    for name, keys in (("services.yaml", URL_KEYS), ("widgets.yaml", URL_KEYS), ("settings.yaml", {"suggestionUrl"})):
        for key, value in walk(parsed.get(name, [])):
            if key in keys and not url_ok(value, namespaces, internal):
                found.append(f"{name}: {key} is not <service>.<namespace> or a public https name: {value!r}")

    for _, value in walk(services, skip={"widget", "widgets"}):
        if isinstance(value, str):
            found += [f"services.yaml: placeholder outside a service widget block: {n}" for n in NAME_RE.findall(value)]
    for name, text in data.items():
        if name != "services.yaml":
            found += [f"{name}: placeholder outside a service widget block: {n}" for n in PLACEHOLDER_RE.findall(text)]
    return found


def namespaces() -> set[str]:
    found = set()
    for path in glob.glob("services/**/app.yaml", recursive=True) + glob.glob("infrastructure/**/app.yaml", recursive=True):
        with open(path) as handle:
            namespace = (yaml.safe_load(handle) or {}).get("namespace")
        if namespace:
            found.add(namespace)
    return found


def internal_domain() -> str:
    with open("templates/globals.yaml") as handle:
        return yaml.safe_load(handle)["global"]["domains"]["internal"]


def rendered_data() -> dict[str, str]:
    out = subprocess.run(["helm", "template", "homepage", CHART], capture_output=True, text=True, check=True).stdout
    for doc in yaml.safe_load_all(out):
        if doc and doc.get("kind") == "ConfigMap" and doc["metadata"]["name"] == CONFIGMAP:
            return doc.get("data") or {}
    raise SystemExit(f"no ConfigMap {CONFIGMAP} in {CHART}")


def self_check() -> None:
    for url in URL_OK:
        assert url_ok(url, NS, INTERNAL), f"self-check: url_ok rejected {url!r}"
    for url in URL_BAD:
        assert not url_ok(url, NS, INTERNAL), f"self-check: url_ok accepted {url!r}"
    assert problems(GOOD, NS, INTERNAL) == [], f"self-check: GOOD failed: {problems(GOOD, NS, INTERNAL)}"
    for name, (files, expected) in BAD.items():
        data = {k: v for k, v in {**GOOD, **files}.items() if v is not None}
        found = problems(data, NS, INTERNAL)
        assert any(expected in p for p in found), f"self-check: fixture {name!r} gave {found}"


def main() -> int:
    self_check()
    found = problems(rendered_data(), namespaces(), internal_domain())
    if found:
        print(f"Household Homepage boundary FAILED ({len(found)} problems)")
        for problem in found:
            print(f"  {problem}")
        return 1
    print("Household Homepage boundary OK (ADR 0018)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
