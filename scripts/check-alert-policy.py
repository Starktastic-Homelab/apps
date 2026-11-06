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

argocd = {
    rule["alert"]: rule
    for group in load("services/operations/kube-prometheus-stack/manifests/custom-rules.yaml")["spec"]["groups"]
    for rule in group["rules"]
}
app = 'namespace="argocd",project="default"'
for name, sync_status, phase in [
    ("drifted", "OutOfSync", "Failed"),
    ("unknown", "Unknown", "Succeeded"),
    ("health-error", "Synced", "Succeeded"),
    ("both", "Unknown", ""),
    ("fine", "Synced", ""),
]:
    inputs.append({
        "series": f'argocd_app_info{{{app},name="{name}",sync_status="{sync_status}",phase="{phase}"}}',
        "values": "1+0x20",
    })
for name in ["health-error", "both"]:
    inputs.append({
        "series": f'argocd_app_condition{{{app},name="{name}",condition="ComparisonError"}}',
        "values": "1+0x20",
    })
# No phase label in the output: a sync attempt must not split or reset an alert.
checks.append({
    "expr": argocd["ArgoCDAppOutOfSync"]["expr"],
    "eval_time": "15m",
    "exp_samples": [{"labels": f'{{{app},name="drifted"}}', "value": 1}],
})
checks.append({
    "expr": argocd["ArgoCDAppComparisonFailing"]["expr"],
    "eval_time": "15m",
    "exp_samples": [
        {"labels": f'{{{app},name="{name}"}}', "value": 1}
        for name in ["unknown", "health-error", "both"]
    ],
})
for trigger, succeeded, values in [
    ("on-sync-failed", "false", "0+1x80"),
    ("on-health-degraded", "false", "3+0x80"),  # old failures only
    ("on-sync-failed", "true", "0+5x80"),
]:
    inputs.append({
        "series": (
            'argocd_notifications_deliveries_total{namespace="argocd",pod="notifications-0",'
            f'service="ntfy",trigger="{trigger}",succeeded="{succeeded}"}}'
        ),
        "values": values,
    })
checks.append({
    "expr": argocd["ArgoCDNotificationDeliveryFailing"]["expr"],
    "eval_time": "75m",
    "exp_samples": [{"labels": '{namespace="argocd",service="ntfy",trigger="on-sync-failed"}', "value": 60}],
})

crowdsec = {
    rule["alert"]: rule["expr"]
    for group in load("infrastructure/system/crowdsec/manifests/prometheus-rules.yaml")["spec"]["groups"]
    for rule in group["rules"]
}
lapi = 'instance="10.42.1.5:6060",job="crowdsec-service",namespace="crowdsec"'
lapi_up = f"up{{{lapi}}}"
lapi_absent = '{job="crowdsec-service",namespace="crowdsec"}'
crowdsec_tests = []
# The LAPI drops cs_active_decisions rather than exporting 0, and a vanished target leaves no up
# series, so each case tells an empty result (no alert) from a 0 sample. Agent up=0 must not count.
for up, decisions, lapi_down, no_decisions in [
    ("1x20", "15000x20", [], []),  # healthy, community blocklist loaded
    ("1x20", "15000x5 stale", [], [(lapi_up, 1)]),  # LAPI up, no decisions left
    ("1x5 0x15", "15000x5 stale", [(lapi_up, 0)], []),  # scrapes failing
    ("1x5 stale", "15000x5 stale", [(lapi_absent, 1)], []),  # scrape target gone
]:
    crowdsec_tests.append({
        "interval": "1m",
        "input_series": [
            {"series": lapi_up, "values": up},
            {"series": f'cs_active_decisions{{{lapi},action="ban",origin="CAPI",reason="http:scan"}}',
             "values": decisions},
            {"series": 'up{job="crowdsec-agent-service",namespace="crowdsec"}', "values": "0x20"},
        ],
        "promql_expr_test": [
            {
                "expr": crowdsec[name],
                "eval_time": "15m",
                "exp_samples": [{"labels": labels, "value": value} for labels, value in expected],
            }
            for name, expected in [("CrowdSecLAPIDown", lapi_down), ("CrowdSecNoActiveDecisions", no_decisions)]
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
        }, *crowdsec_tests],
    }),
    text=True,
    check=True,
)
print("Alert policy checks passed.")
