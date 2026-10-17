#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
: "${OPERATIONS_HOME_RENDERS:?Set a private render output directory}"
mkdir -p "$OPERATIONS_HOME_RENDERS"
chart="${APP_TEMPLATE_CHART:?Set the pinned app-template chart directory}"
for app in karakeep bytestash convertx home-assistant; do
  category=operations
  [[ $app != home-assistant ]] || category=home-automation
  layers=(-f templates/globals.yaml -f templates/common.yaml -f "services/$category/$app/values.yaml")
  helm template "$app" "$chart" --namespace "$category" --kube-version 1.37.0 "${layers[@]}" >"$OPERATIONS_HOME_RENDERS/$app-before.yaml"
  helm template "$app" "$chart" --namespace "$category" --kube-version 1.37.0 "${layers[@]}" -f "scripts/operations-home-retained/production/$app-values.yaml" >"$OPERATIONS_HOME_RENDERS/$app.yaml"
done
helm template excalidash "$chart" --namespace operations --kube-version 1.37.0 -f templates/globals.yaml -f templates/common.yaml -f services/operations/excalidash/values.yaml >"$OPERATIONS_HOME_RENDERS/excalidash-before.yaml"
helm template excalidash "$chart" --namespace operations --kube-version 1.37.0 -f templates/globals.yaml -f templates/common.yaml -f services/operations/excalidash/values.yaml -f scripts/operations-home-retained/production/excalidash-values.yaml >"$OPERATIONS_HOME_RENDERS/excalidash.yaml"
: "${CROWDSEC_CHART:?Set the pinned CrowdSec chart directory}"
helm template crowdsec "$CROWDSEC_CHART" --namespace crowdsec -f templates/globals.yaml -f infrastructure/system/crowdsec/values.yaml >"$OPERATIONS_HOME_RENDERS/crowdsec-before.yaml"
crowdsec_layers=(-f templates/globals.yaml -f infrastructure/system/crowdsec/values.yaml)
if ! python3 -c 'import yaml; v=yaml.safe_load(open("infrastructure/system/crowdsec/values.yaml")); c=yaml.safe_load(v.get("config",{}).get("config.yaml.local","{}")); raise SystemExit(0 if c.get("db_config",{}).get("type")=="postgresql" else 1)'; then
  crowdsec_layers+=(-f scripts/operations-home-retained/production/crowdsec-values.yaml)
fi
helm template crowdsec "$CROWDSEC_CHART" --namespace crowdsec "${crowdsec_layers[@]}" >"$OPERATIONS_HOME_RENDERS/crowdsec.yaml"
kubeconform -strict -summary -ignore-missing-schemas "$OPERATIONS_HOME_RENDERS"/*.yaml scripts/operations-home-retained/production/*-bindings.yaml scripts/operations-home-retained/production/*-source-hold.yaml scripts/operations-home-retained/production/guard-*.yaml scripts/operations-home-retained/production/*-postgresql/*.yaml scripts/operations-home-retained/production/postgres-enrollment/*.yaml
python3 scripts/test-operations-home-retained.py
python3 scripts/test-operations-home-postgresql.py
