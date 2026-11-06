#!/usr/bin/env python3
"""Render every ArgoCD notification webhook body with a hostile sync message; each must be valid JSON.

Run from the repo root; needs helm and PyYAML. ntfy rejects an unparseable JSON body with HTTP 400,
which loses the notification. Helm's text/template + sprig stand in for notifications-engine's
(sprig.TxtFuncMap() minus env and expandenv).
"""

import json
from pathlib import Path
import subprocess
import sys
import tempfile

import yaml

# Quotes, a backslash, a newline and HTML characters, as real Kubernetes sync errors carry.
MESSAGE = 'Deployment.apps "web" is invalid: spec.template: Invalid value: "C:\\data"\n<&> retried 5 times'


def helm(*args):
    return subprocess.run(["helm", *args], check=True, stdout=subprocess.PIPE, text=True).stdout


data = yaml.safe_load(helm(
    "template", "configs", "infrastructure/configs", "-f", "templates/globals.yaml",
    "--show-only", "templates/argocd/notifications.yaml",
))["data"]
bodies = {
    f"{key}/{service}": webhook["body"]
    for key, value in data.items() if key.startswith("template.")
    for service, webhook in (yaml.safe_load(value).get("webhook") or {}).items()
}
template_vars = {
    "context": yaml.safe_load(data["context"]),
    "app": {"metadata": {"name": "web"}, "status": {
        "health": {"status": "Degraded"},
        "operationState": {"phase": "Failed", "message": MESSAGE},
    }},
}

with tempfile.TemporaryDirectory() as chart:
    Path(chart, "templates").mkdir()
    Path(chart, "Chart.yaml").write_text("apiVersion: v2\nname: check\nversion: 0.0.0\n")
    Path(chart, "values.yaml").write_text(json.dumps({"bodies": bodies, "vars": template_vars}))
    Path(chart, "templates/bodies.yaml").write_text(
        "{{- $out := dict }}{{- range $key, $body := .Values.bodies }}"
        "{{- $_ := set $out $key (tpl $body $.Values.vars) }}{{- end }}{{ toYaml $out }}\n"
    )
    rendered = yaml.safe_load(helm("template", chart)) or {}

failures = [] if bodies else ["no webhook bodies found in argocd-notifications-cm"]
for key, body in sorted(rendered.items()):
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as error:
        failures.append(f"{key}: invalid JSON ({error})\n{body}")
        continue
    if key == "template.app-sync-failed/ntfy" and parsed.get("message") != f"Reason: {MESSAGE}":
        failures.append(f"{key}: sync message did not survive: {parsed.get('message')!r}")

if failures:
    print(f"ArgoCD notification check FAILED ({len(failures)} problems)\n")
    print("\n".join(failures))
    sys.exit(1)
print(f"ArgoCD notification bodies OK: {len(rendered)} render as valid JSON")
