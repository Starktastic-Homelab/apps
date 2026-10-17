#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
: "${UTILITY_HOME_RENDERS:?Set a private render directory}"
: "${APP_TEMPLATE_CHART:?Set the pinned app-template chart directory}"
mkdir -p "$UTILITY_HOME_RENDERS"
for app in qbittorrent qbittorrent-ru changedetection stirling-pdf microbin lingarr mosquitto zigbee2mqtt; do
  category=operations
  case "$app" in
    qbittorrent | qbittorrent-ru | lingarr) category=media ;;
    mosquitto | zigbee2mqtt) category=home-automation ;;
  esac
  layers=(-f templates/globals.yaml -f templates/common.yaml)
  if [[ $app == qbittorrent-ru ]]; then layers+=(-f services/media/qbittorrent/values.yaml); fi
  layers+=(-f "services/$category/$app/values.yaml")
  helm template "$app" "$APP_TEMPLATE_CHART" --namespace "$category" --kube-version 1.37.0 "${layers[@]}" >"$UTILITY_HOME_RENDERS/$app-before.yaml"
  if [[ $app == qbittorrent-ru ]]; then layers+=(-f scripts/utility-home-retained/production/qbittorrent-values.yaml); fi
  helm template "$app" "$APP_TEMPLATE_CHART" --namespace "$category" --kube-version 1.37.0 "${layers[@]}" -f "scripts/utility-home-retained/production/$app-values.yaml" >"$UTILITY_HOME_RENDERS/$app.yaml"
  if [[ $app == mosquitto ]]; then printf '\n---\n' >>"$UTILITY_HOME_RENDERS/$app.yaml"; cat scripts/utility-home-retained/production/mosquitto-configmap.yaml >>"$UTILITY_HOME_RENDERS/$app.yaml"; fi
done
kubeconform -strict -summary -ignore-missing-schemas "$UTILITY_HOME_RENDERS"/*.yaml scripts/utility-home-retained/production/*-bindings.yaml scripts/utility-home-retained/production/*-source-hold.yaml scripts/utility-home-retained/production/guard-*.yaml
python3 scripts/test-utility-home-retained.py
