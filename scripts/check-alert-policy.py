#!/usr/bin/env python3
"""Check alert policy with Helm, Docker, PyYAML, and promtool (or a command prefix)."""

from pathlib import Path
import json
import subprocess
import sys

import yaml


ROOT = Path(__file__).resolve().parents[1]


def load(path):
    return yaml.safe_load((ROOT / path).read_text())


job = load("services/media/jellyfin/manifests/ldap-library-sync.yaml")
assert job["spec"]["jobTemplate"]["spec"].get("ttlSecondsAfterFinished") == 86400, (
    "Jellyfin sync Jobs must expire after 24 hours"
)

image = load("services/media/flaresolverr/values.yaml")["controllers"]["main"]["containers"]["main"]["image"]
assert "@sha256:" in image["tag"], "The FlareSolverr exception requires an immutable image pin"
manifests = json.loads(subprocess.check_output(
    ["docker", "manifest", "inspect", "--verbose", image["repository"] + ":" + image["tag"]],
    text=True,
))
amd64 = next(
    manifest for manifest in manifests
    if manifest["Descriptor"]["platform"] == {"architecture": "amd64", "os": "linux"}
)
config = (amd64.get("OCIManifest") or amd64["SchemaV2Manifest"])["config"]["digest"]
expected = {
    "k8s.ns.name": "media",
    "container.image.repository": image["repository"],
    "container.image.tag": config.removeprefix("sha256:"),
    "proc.exepath": "/app/chromedriver",
    "proc.pname": "python",
    "proc.aname[2]": "dumb-init",
    "user.uid": 1000,
}
falco = load("infrastructure/system/falco/values.yaml")
assert {
    "/etc/falco/falco_rules.yaml",
    "/etc/falco/falco-incubating_rules.yaml",
    "/etc/falco/rules.d",
} <= set(falco["falco"]["rules_files"]), "Preserve base, incubating, and custom rules"
override = yaml.safe_load(falco["customRules"]["flaresolverr-chromedriver.yaml"])
assert len(override) == 1
rule = override[0]
rule_name = "Drop and execute new binary in container"
assert set(rule) == {"rule", "override", "exceptions"}, "Do not alter the base rule"
assert rule["rule"] == rule_name
assert rule["override"] == {"exceptions": "append"}, "Preserve other exceptions"
assert len(rule["exceptions"]) == 1
exception = rule["exceptions"][0]
assert set(exception) == {"name", "fields", "comps", "values"}
fields = exception["fields"]
assert len(fields) == len(expected) and set(fields) == set(expected)
assert exception["comps"] == ["="] * len(fields), "Require exact equality"
assert exception["values"] == [[expected[field] for field in fields]], (
    "The exception must match only the pinned image and expected execution context"
)


def is_exempt(event, event_rule=rule_name):
    return event_rule == rule["rule"] and all(
        field in event and event[field] == value
        for field, value in zip(fields, exception["values"][0])
    )


assert is_exempt(expected)
for field in expected:
    changed = {**expected, field: 0 if field == "user.uid" else "different"}
    assert not is_exempt(changed), f"Changed {field} must not be exempt"
    missing = {key: value for key, value in expected.items() if key != field}
    assert not is_exempt(missing), f"Missing {field} must not be exempt"
assert not is_exempt(expected, "Other Falco rule")

chart = load("infrastructure/system/metallb/app.yaml")["chart"]
rendered = subprocess.check_output(
    [
        "helm", "template", "metallb", chart["name"],
        "--repo", chart["repo"], "--version", chart["version"],
        "--namespace", "metallb-system",
        "-f", str(ROOT / "infrastructure/system/metallb/values.yaml"),
    ],
    text=True,
)
rules = {
    rule["alert"]: rule
    for document in yaml.safe_load_all(rendered)
    if document and document.get("kind") == "PrometheusRule"
    for group in document["spec"]["groups"]
    for rule in group["rules"]
}
assert "KubeServiceLoadBalancerPending" in rules, (
    "A LoadBalancer without an ingress address must still alert"
)
assert rules["KubeServiceLoadBalancerPending"]["for"] == "10m"
assert {"MetalLBStaleConfig", "MetalLBConfigNotLoaded", "MetalLBBGPSessionDown"} <= rules.keys()

inputs = []
for pool, used, capacity in [
    ("homelab", 5, 5),
    ("dynamic-full", 2, 2),
    ("dynamic-spare", 1, 2),
    ("", 0, 0),
]:
    for metric, value in [
        ("metallb_allocator_addresses_in_use_total", used),
        ("metallb_allocator_addresses_total", capacity),
    ]:
        inputs.append({
            "series": f'{metric}{{pool="{pool}"}}',
            "values": f"{value}+0x20",
        })

for namespace, service, service_type in [
    ("media", "ready", "LoadBalancer"),
    ("other", "ready", "LoadBalancer"),
    ("media", "pending", "LoadBalancer"),
    ("media", "internal", "ClusterIP"),
]:
    inputs.append({
        "series": (
            f'kube_service_spec_type{{namespace="{namespace}",'
            f'service="{service}",type="{service_type}"}}'
        ),
        "values": "1+0x20",
    })
inputs.append({
    "series": 'kube_service_status_load_balancer_ingress{namespace="media",service="ready",ip="192.0.2.1"}',
    "values": "1+0x20",
})

checks = []
for name, value in [
    ("MetalLBAddressPoolExhausted", 2),
    ("MetalLBAddressPoolUsage75Percent", 100),
    ("MetalLBAddressPoolUsage85Percent", 100),
    ("MetalLBAddressPoolUsage95Percent", 100),
]:
    checks.append({
        "expr": rules[name]["expr"],
        "eval_time": "15m",
        "exp_samples": [{"labels": '{pool="dynamic-full"}', "value": value}],
    })
checks.append({
    "expr": rules["KubeServiceLoadBalancerPending"]["expr"],
    "eval_time": "15m",
    "exp_samples": [
        {"labels": '{namespace="media",service="pending"}', "value": 1},
        {"labels": '{namespace="other",service="ready"}', "value": 1},
    ],
})

subprocess.run(
    [*(sys.argv[1:] or ["promtool"]), "test", "rules", "/dev/stdin"],
    input=yaml.safe_dump({
        "evaluation_interval": "1m",
        "tests": [{
            "interval": "1m",
            "input_series": inputs,
            "promql_expr_test": checks,
        }],
    }),
    text=True,
    check=True,
)
print("Alert policy checks passed.")
