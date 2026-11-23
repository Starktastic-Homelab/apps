#!/usr/bin/env python3
"""Check alert policy with Helm, Docker, PyYAML, and promtool (or a command prefix)."""

from pathlib import Path
import json
import re
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
# Chart 0.16.2 dropped on(pool) (metallb#3047): the >= filter keeps the left-hand series name.
for name, metric, value in [
    ("MetalLBAddressPoolExhausted", "metallb_allocator_addresses_in_use_total", 2),
    ("MetalLBAddressPoolUsage75Percent", "", 100),
    ("MetalLBAddressPoolUsage85Percent", "", 100),
    ("MetalLBAddressPoolUsage95Percent", "", 100),
]:
    checks.append({
        "expr": rules[name]["expr"],
        "eval_time": "15m",
        "exp_samples": [{"labels": metric + '{pool="dynamic-full"}', "value": value}],
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

# kube-state-metrics exports every reason per pod, 0 unless it applies; only Evicted counts.
for pod, reason, value in [
    ("evicted", "Evicted", 1), ("evicted", "NodeLost", 0),
    ("lost", "Evicted", 0), ("lost", "NodeLost", 1),
    ("running", "Evicted", 0), ("running", "NodeLost", 0),
]:
    inputs.append({
        "series": f'kube_pod_status_reason{{namespace="media",pod="{pod}",reason="{reason}",uid="u"}}',
        "values": f"{value}+0x20",
    })
checks.append({
    "expr": argocd["PodEvicted"]["expr"],
    "eval_time": "15m",
    "exp_samples": [{"labels": '{namespace="media",pod="evicted"}', "value": 1}],
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

gate = {
    rule["alert"]: rule["expr"]
    for group in load("services/operations/prometheus-blackbox-exporter/manifests/prometheus-rules.yaml")["spec"]["groups"]
    if group["name"] == "admin-gate"
    for rule in group["rules"]
}
gate_labels = 'service="homepage-admin",tier="gate",vhost="admin.internal.starktastic.net"'
admin_gate_tests = []
# Each case is its own test so absent() sees only that case's series. A 200 means the gate is open;
# the regex failing means a 302 that does not lead to the internal-gate provider.
for series, expected in [
    # healthy: 302 to the internal provider
    (
        {"probe_success": 1, "probe_http_status_code": 302, "probe_failed_due_to_regex": 0},
        {},
    ),
    (
        {"probe_success": 0, "probe_http_status_code": 200, "probe_failed_due_to_regex": 0},
        {
            "AdminGateOpen": [(f'{{__name__="probe_http_status_code",{gate_labels}}}', 200)],
            "AdminGateDown": [(f'{{__name__="probe_success",{gate_labels}}}', 0)],
        },
    ),
    (
        {"probe_success": 0, "probe_http_status_code": 302, "probe_failed_due_to_regex": 1},
        {
            "AdminGateWrongProvider": [(f'{{__name__="probe_failed_due_to_regex",{gate_labels}}}', 1)],
            "AdminGateDown": [(f'{{__name__="probe_success",{gate_labels}}}', 0)],
        },
    ),
    ({}, {"AdminGateCanaryMissing": [('{tier="gate"}', 1)]}),
]:
    admin_gate_tests.append({
        "interval": "1m",
        "input_series": [
            {"series": f"{metric}{{{gate_labels}}}", "values": f"{value}x20"}
            for metric, value in series.items()
        ],
        "promql_expr_test": [
            {
                "expr": gate[name],
                "eval_time": "15m",
                "exp_samples": [
                    {"labels": labels, "value": value} for labels, value in expected.get(name, [])
                ],
            }
            for name in ["AdminGateOpen", "AdminGateWrongProvider", "AdminGateDown", "AdminGateCanaryMissing",
                         "AdminGatePublicAnswer"]
        ],
    })

blackbox_failed = next(
    rule["expr"]
    for group in load("services/operations/prometheus-blackbox-exporter/manifests/prometheus-rules.yaml")["spec"]["groups"]
    for rule in group["rules"]
    if rule.get("alert") == "BlackboxProbeFailed"
)
neg = 'service="homepage-admin",tier="gate-negative",vhost="admin.starktastic.net"'
neg_ok = 'service="homepage-admin",tier="gate-negative",vhost="auth.internal.starktastic.net"'
# Public-negative probes: one vhost answering publicly fires AdminGatePublicAnswer only (not the generic
# BlackboxProbeFailed); with no series at all, the negative canary is missing.
for series, expected in [
    ([(neg, "0x20"), (neg_ok, "1x20")], {"AdminGatePublicAnswer": [(f'{{__name__="probe_success",{neg}}}', 0)]}),
    ([], {"AdminGateNegativeCanaryMissing": [('{tier="gate-negative"}', 1)]}),
]:
    admin_gate_tests.append({
        "interval": "1m",
        "input_series": [{"series": f"probe_success{{{labels}}}", "values": values} for labels, values in series],
        "promql_expr_test": [
            {"expr": expr, "eval_time": "15m",
             "exp_samples": [{"labels": labels, "value": value} for labels, value in expected.get(name, [])]}
            for name, expr in [("AdminGatePublicAnswer", gate["AdminGatePublicAnswer"]),
                               ("AdminGateNegativeCanaryMissing", gate["AdminGateNegativeCanaryMissing"]),
                               ("BlackboxProbeFailed", blackbox_failed)]
        ],
    })

# Tempo only creates the counter on the first poll error; a recovered tenant must clear.
for tenant, values in [("failing", "0+1x40"), ("recovered", "0+1x10 10+0x30"), ("fine", "0+0x40")]:
    inputs.append({
        "series": f'tempodb_blocklist_tenant_index_errors_total{{namespace="monitoring",pod="tempo-0",tenant="{tenant}"}}',
        "values": values,
    })
checks.append({
    "expr": argocd["TempoBlocklistPollFailing"]["expr"],
    "eval_time": "30m",
    "exp_samples": [{"labels": '{namespace="monitoring",pod="tempo-0",tenant="failing"}', "value": 15}],
})

storage_docs = list(yaml.safe_load_all(
    (ROOT / "services/operations/kube-prometheus-stack/manifests/storage-vm.yaml").read_text()
))
scrape = next(d for d in storage_docs if d["kind"] == "ScrapeConfig")
storage_rule_groups = next(d for d in storage_docs if d["kind"] == "PrometheusRule")["spec"]["groups"]
storage = {rule["alert"]: rule for group in storage_rule_groups for rule in group["rules"]}
assert scrape["metadata"]["labels"]["release"] == "kube-prometheus-stack"
# Every job matcher must name the ScrapeConfig job, or the alert never sees a series.
for rule in storage.values():
    assert set(re.findall(r'job="([^"]*)"', rule["expr"])) <= {scrape["spec"]["jobName"]}, rule["alert"]
assert scrape["spec"]["staticConfigs"][0]["targets"] == [
    load("templates/globals.yaml")["global"]["network"]["storagePortal"].rsplit(":", 1)[0] + ":9100"
], "ScrapeConfig host must match global.network.storagePortal"

S = 'job="storage-vm"'
FENCER_FILE = f'{{{S},file="/var/lib/prometheus/node-exporter/storage-fencer.prom"}}'
storage_tests = []
# Each case is its own promtool group, so absent() sees only that case's series. Series values are
# per minute and the check runs at 30m (2h cases at 150m).
for alert, series, at, expected in [
    ("StorageVMDown", [(f"up{{{S}}}", "0x30")], "30m",
     [(f'{{__name__="up",{S}}}', 0)]),
    ("StorageReconcileFailing", [(f"storage_last_reconcile_success_timestamp_seconds{{{S}}}", "0x150")], "150m",
     [(f'{{{S}}}', 9000)]),
    ("StorageTargetMissing", [(f'storage_target_missing{{{S},id="grafana"}}', "1x30")], "30m",
     [(f'{{__name__="storage_target_missing",{S},id="grafana"}}', 1)]),
    ("StorageVGLowSpace",
     [(f'storage_vg_free_bytes{{{S},vg="retained"}}', "10x30"), (f'storage_vg_size_bytes{{{S},vg="retained"}}', "100x30"),
      (f'storage_vg_free_bytes{{{S},vg="regen"}}', "50x30"), (f'storage_vg_size_bytes{{{S},vg="regen"}}', "100x30")],
     "30m", [(f'{{{S},vg="retained"}}', 0.1)]),
    ("StoragePendingDelete", [(f'storage_pending_delete{{{S},id="old",since="1"}}', "1x30")], "30m",
     [(f'{{__name__="storage_pending_delete",{S},id="old",since="1"}}', 1)]),
    ("StorageHoldCreate", [(f"storage_hold_create{{{S}}}", "1x30")], "30m",
     [(f'{{__name__="storage_hold_create",{S}}}', 1)]),
    ("StorageWorkerFenced", [(f'storage_fence_active{{{S},node="worker-01"}}', "1x30")], "30m",
     [(f'{{__name__="storage_fence_active",{S},node="worker-01"}}', 1)]),
    ("StorageFenceFailed", [(f"storage_fence_failures_total{{{S}}}", "0+1x30")], "30m",
     [(f'{{{S}}}', 10)]),
    # Draining: a start over 120 s old fires (worker-01 idle at 0 stays quiet); 60 s old, exactly 120 s old (strict),
    # and a fresh start every minute (repeated failed proofs) do not.
    ("StorageFenceDraining",
     [(f'storage_fence_acl_delete_started_timestamp_seconds{{{S},node="worker-02"}}', "60x30"),
      (f'storage_fence_acl_delete_started_timestamp_seconds{{{S},node="worker-01"}}', "0x30")], "30m",
     [(f'{{__name__="storage_fence_acl_delete_started_timestamp_seconds",{S},node="worker-02"}}', 60)]),
    ("StorageFenceDraining",
     [(f'storage_fence_acl_delete_started_timestamp_seconds{{{S},node="worker-02"}}', "1740x30")], "30m", []),
    ("StorageFenceDraining",
     [(f'storage_fence_acl_delete_started_timestamp_seconds{{{S},node="worker-02"}}', "1680x30")], "30m", []),
    ("StorageFenceDraining",
     [(f'storage_fence_acl_delete_started_timestamp_seconds{{{S},node="worker-02"}}', "0+60x30")], "30m", []),
    # Blind, one case per cause: bad credentials, API unreachable, stale textfile.
    ("StorageFencerBlind",
     [(f"storage_fencer_last_api_success_timestamp_seconds{{{S}}}", "0x30"),
      (f'storage_fencer_api_errors_total{{{S},code="auth"}}', "0+1x30"),
      (f"node_textfile_mtime_seconds{FENCER_FILE}", "1799x30")], "30m",
     [(f'{{{S}}}', 1800)]),
    ("StorageFencerBlind",
     [(f"storage_fencer_last_api_success_timestamp_seconds{{{S}}}", "0x30"),
      (f'storage_fencer_api_errors_total{{{S},code="unreachable"}}', "0+1x30"),
      (f"node_textfile_mtime_seconds{FENCER_FILE}", "1799x30")], "30m",
     [(f'{{{S}}}', 1800)]),
    ("StorageFencerBlind",
     [(f"storage_fencer_last_api_success_timestamp_seconds{{{S}}}", "1799x30"),
      (f"node_textfile_mtime_seconds{FENCER_FILE}", "0x30")], "30m",
     [(f'{{{S},file="/var/lib/prometheus/node-exporter/storage-fencer.prom"}}', 1800)]),
    # Boot check: a failed check, a check that has not run since the boot (timestamp 100 < boot 200), a passing one.
    ("StorageBootCheckFailed", [(f"storage_boot_check_ok{{{S}}}", "0x30")], "30m",
     [(f'{{__name__="storage_boot_check_ok",{S}}}', 0)]),
    ("StorageBootCheckFailed",
     [(f"storage_boot_check_ok{{{S}}}", "1x30"), (f"storage_boot_check_timestamp_seconds{{{S}}}", "100x30"),
      (f"node_boot_time_seconds{{{S}}}", "200x30")], "30m",
     [(f'{{{S}}}', 100)]),
    ("StorageBootCheckFailed",
     [(f"storage_boot_check_ok{{{S}}}", "1x30"), (f"storage_boot_check_timestamp_seconds{{{S}}}", "300x30"),
      (f"node_boot_time_seconds{{{S}}}", "200x30")], "30m", []),
    ("StorageBootCheckFailed", [(f"node_boot_time_seconds{{{S}}}", "200x30")], "30m", [(f'{{{S}}}', 1)]),  # never wrote
    # Dataset (floor 20 GiB): 19 GiB free fires; a write over 3 h old fires; 21 GiB free and fresh, or 2 h old (one
    # failed hourly write), stays quiet.
    ("StorageDatasetLow",
     [(f'storage_dataset_avail_bytes{{{S},dataset="apps/k3s-block"}}', f"{19 * 2**30}x30"),
      (f"storage_dataset_timestamp_seconds{{{S}}}", "0+60x30")], "30m",
     [(f'{{__name__="storage_dataset_avail_bytes",{S},dataset="apps/k3s-block"}}', 19 * 2**30)]),
    ("StorageDatasetLow",
     [(f'storage_dataset_avail_bytes{{{S},dataset="apps/k3s-block"}}', f"{21 * 2**30}x200"),
      (f"storage_dataset_timestamp_seconds{{{S}}}", "0x200")], "200m",
     [(f'{{{S}}}', 12000)]),
    ("StorageDatasetLow",
     [(f'storage_dataset_avail_bytes{{{S},dataset="apps/k3s-block"}}', f"{21 * 2**30}x30"),
      (f"storage_dataset_timestamp_seconds{{{S}}}", "0+60x30")], "30m", []),
    ("StorageDatasetLow",
     [(f'storage_dataset_avail_bytes{{{S},dataset="apps/k3s-block"}}', f"{21 * 2**30}x150"),
      (f"storage_dataset_timestamp_seconds{{{S}}}", "1800x150")], "150m", []),
    # Never written (the gauges step failed from its first run): the absent leg fires. It also covers
    # MaintenanceLockStale, whose series is written in the same file.
    ("StorageDatasetLow", [(f"node_boot_time_seconds{{{S}}}", "200x30")], "30m", [(f'{{{S}}}', 1)]),
    # Lock (eval at 450m = 27000 s): taken 7 h ago fires, 1 h ago or free (0) stays quiet.
    ("MaintenanceLockStale",
     [(f'storage_maintenance_lock_created_timestamp_seconds{{{S},operation="ansible-deploy"}}', "1800x450")], "450m",
     [(f'{{__name__="storage_maintenance_lock_created_timestamp_seconds",{S},operation="ansible-deploy"}}', 1800)]),
    ("MaintenanceLockStale",
     [(f'storage_maintenance_lock_created_timestamp_seconds{{{S},operation="ansible-deploy"}}', "23400x450")], "450m",
     []),
    ("MaintenanceLockStale",
     [(f'storage_maintenance_lock_created_timestamp_seconds{{{S},operation=""}}', "0x450")], "450m", []),
    ("NodeOutOfServiceTaintStuck",
     [('kube_node_spec_taint{node="worker-01",key="node.kubernetes.io/out-of-service",value="nodeshutdown",effect="NoExecute"}', "1x30")],
     "30m",
     [('{__name__="kube_node_spec_taint",node="worker-01",key="node.kubernetes.io/out-of-service",value="nodeshutdown",effect="NoExecute"}', 1)]),
]:
    storage_tests.append({
        "interval": "1m",
        "input_series": [{"series": name, "values": values} for name, values in series],
        "promql_expr_test": [{
            "expr": storage[alert]["expr"],
            "eval_time": at,
            "exp_samples": [{"labels": labels, "value": value} for labels, value in expected],
        }],
    })

subprocess.run(
    [*(sys.argv[1:] or ["promtool"]), "test", "rules", "/dev/stdin"],
    input=yaml.safe_dump({
        "evaluation_interval": "1m",
        "tests": [{
            "interval": "1m",
            "input_series": inputs,
            "promql_expr_test": checks,
        }, *crowdsec_tests, *admin_gate_tests, *storage_tests],
    }),
    text=True,
    check=True,
)
print("Alert policy checks passed.")
