#!/usr/bin/env python3
"""Exercise the shipped capacity rules with promtool; no cluster access."""
from pathlib import Path
import subprocess
import sys
import tempfile

import yaml

ROOT = Path(__file__).resolve().parents[1]
RULE = ROOT / "services/operations/kube-prometheus-stack/manifests/proxmox-csi-capacity.yaml"
groups = yaml.safe_load(RULE.read_text())["spec"]["groups"]
alerts = {rule["alert"]: rule for group in groups for rule in group["rules"] if "alert" in rule}
NODE = "ProxmoxCSINodeAttachmentHeadroomLow"
LOW = "ProxmoxCSIClusterAttachmentHeadroomLow"
FULL = "ProxmoxCSIClusterAttachmentCapacityExhausted"


def fixture(counts, *, duplicate=False, cordoned=(), unready=()):
    series = []
    for node, count in counts.items():
        for metric, value in (
            (f'kube_node_role{{node="{node}",role="worker"}}', 1),
            (f'kube_node_status_condition{{node="{node}",condition="Ready",status="true"}}', int(node not in unready)),
            (f'kube_node_spec_unschedulable{{node="{node}"}}', int(node in cordoned)),
        ):
            series.append({"series": metric, "values": f"{value}+0x40"})
        for i in range(count):
            for exporter in (("a", "b") if duplicate else ("a",)):
                series.append({
                    "series": f'kube_volumeattachment_info{{node="{node}",volumeattachment="{node}-{i}",attacher="csi.proxmox.sinextra.dev",instance="{exporter}"}}',
                    "values": "1+0x40",
                })
    # Other storage drivers must not consume the Proxmox budget.
    series.append({"series": 'kube_volumeattachment_info{node="w1",volumeattachment="foreign",attacher="other"}', "values": "1+0x40"})
    return series


def expected(name, node=None):
    rule = alerts[name]
    labels = dict(rule["labels"])
    annotations = dict(rule["annotations"])
    if node:
        labels["node"] = node
        annotations = {key: value.replace("{{ $labels.node }}", node) for key, value in annotations.items()}
    return {"exp_labels": labels, "exp_annotations": annotations}


def scenario(name, counts, free, firing=(), **options):
    checks = []
    for alert in alerts:
        expected_alerts = [expected(alert, node) for candidate, node in firing if candidate == alert]
        checks.append({"eval_time": "40m", "alertname": alert, "exp_alerts": expected_alerts})
        checks.append({"eval_time": "0m", "alertname": alert, "exp_alerts": []})
    return {
        "name": name,
        "interval": "1m",
        "input_series": fixture(counts, **options),
        "alert_rule_test": checks,
        "promql_expr_test": [{
            "expr": "homelab:proxmox_csi_slots_free:count",
            "eval_time": "40m",
            "exp_samples": [{"labels": f'homelab:proxmox_csi_slots_free:count{{node="{node}"}}', "value": value} for node, value in free.items()],
        }],
    }


tests = [
    scenario("current occupancy and duplicate scrapes", {"w1": 17, "w2": 24}, {"w1": 12, "w2": 5}, duplicate=True),
    scenario("empty workers retain all slots", {"w1": 0, "w2": 0}, {"w1": 29, "w2": 29}),
    scenario("node warning before exhaustion", {"w1": 26, "w2": 15}, {"w1": 3, "w2": 14}, [(NODE, "w1")]),
    scenario("cluster warning before node warning", {"w1": 25, "w2": 25}, {"w1": 4, "w2": 4}, [(LOW, None)]),
    scenario("full cluster", {"w1": 29, "w2": 29}, {"w1": 0, "w2": 0}, [(NODE, "w1"), (NODE, "w2"), (LOW, None), (FULL, None)]),
    scenario("full worker with spare elsewhere", {"w1": 29, "w2": 0}, {"w1": 0, "w2": 29}, [(NODE, "w1")]),
    scenario("pending attachments cannot cancel other free slots", {"w1": 35, "w2": 15}, {"w1": -6, "w2": 14}, [(NODE, "w1")]),
    scenario("cordoned worker contributes no available capacity", {"w1": 20, "w2": 0}, {"w1": 9}, [(LOW, None)], cordoned=("w2",)),
    scenario("unready worker contributes no available capacity", {"w1": 20, "w2": 0}, {"w1": 9}, [(LOW, None)], unready=("w2",)),
    scenario("no Ready workers", {"w1": 0, "w2": 0}, {}, [(LOW, None), (FULL, None)], unready=("w1", "w2")),
]
# Actual hold times and recovery: a brief 26-volume peak must not page.
transient = scenario("transient occupancy and recovery", {"w1": 26}, {"w1": 29})
for series in transient["input_series"]:
    if series["series"].startswith("kube_volumeattachment_info{") and 'attacher="csi.proxmox.sinextra.dev"' in series["series"]:
        series["values"] = "1+0x9 stale _x30"
transient["alert_rule_test"] = [
    {"eval_time": time, "alertname": name, "exp_alerts": []}
    for time in ("4m", "9m", "14m", "40m") for name in alerts
]
tests.append(transient)
recovery = scenario("firing alerts clear after attachments retire", {"w1": 29}, {"w1": 29})
for series in recovery["input_series"]:
    if series["series"].startswith("kube_volumeattachment_info{") and 'attacher="csi.proxmox.sinextra.dev"' in series["series"]:
        series["values"] = "1+0x20 stale _x19"
recovery["alert_rule_test"] = [
    {"eval_time": time, "alertname": alert, "exp_alerts": ([expected(alert, "w1" if alert == NODE else None)] if fires else [])}
    for time, fired in (("4m", ()), ("5m", (FULL,)), ("14m", (FULL,)), ("15m", (NODE, FULL)), ("21m", ()), ("40m", ()))
    for alert in alerts for fires in (alert in fired,)
]
tests.append(recovery)

with tempfile.TemporaryDirectory(prefix="proxmox-csi-promtool-") as directory:
    work = Path(directory)
    (work / "rules.yaml").write_text(yaml.safe_dump({"groups": groups}))
    (work / "tests.yaml").write_text(yaml.safe_dump({"rule_files": ["rules.yaml"], "evaluation_interval": "1m", "tests": tests}))
    command = sys.argv[1:] or ["promtool"]
    subprocess.run([*command, "check", "rules", str(work / "rules.yaml")], check=True)
    subprocess.run([*command, "test", "rules", str(work / "tests.yaml")], check=True)
print(f"Proxmox CSI capacity: {len(tests)} native Prometheus scenarios passed")
