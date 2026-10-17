#!/usr/bin/env bash
# Render actual base/variant layers plus inactive retained overrides.
set -euo pipefail
cd "$(dirname "$0")/../.."
: "${MEDIA_RETAINED_RENDERS:?Set a private render output directory}"
mkdir -p "$MEDIA_RETAINED_RENDERS"
chart_version=$(python3 -c 'import yaml; a=yaml.safe_load(open("bootstrap/appsets/cluster-apps.yaml")); print(next(x["defaultChartVersion"] for x in a["spec"]["generators"][0]["matrix"]["generators"][0]["list"]["elements"] if x["category"]=="services"))')
if [[ ! -d "$MEDIA_RETAINED_RENDERS/chart/app-template" ]]; then
  mkdir -p "$MEDIA_RETAINED_RENDERS/chart"
  helm pull app-template --repo https://bjw-s-labs.github.io/helm-charts \
    --version "$chart_version" --untar --untardir "$MEDIA_RETAINED_RENDERS/chart"
fi
for app in sonarr sonarr-ru radarr radarr-ru lidarr cleanuparr navidrome audiobookshelf shelfmark cineplete; do
  base="${app%-ru}"
  layers=(-f templates/globals.yaml -f templates/common.yaml)
  case "$base" in sonarr|radarr|lidarr) layers+=(-f templates/media-arr-common.yaml) ;; esac
  layers+=(-f "services/media/$base/values.yaml")
  if [[ "$base" != "$app" && -f "services/media/$app/values.yaml" ]]; then
    layers+=(-f "services/media/$app/values.yaml")
  fi
  helm template "$app" "$MEDIA_RETAINED_RENDERS/chart/app-template" --namespace media \
    --kube-version 1.37.0 "${layers[@]}" > "$MEDIA_RETAINED_RENDERS/$app-before.yaml"
  layers+=(-f "scripts/media-retained/production/$base-values.yaml")
  if [[ "$base" != "$app" ]]; then layers+=(-f "scripts/media-retained/production/$app-values.yaml"); fi
  helm template "$app" "$MEDIA_RETAINED_RENDERS/chart/app-template" --namespace media \
    --kube-version 1.37.0 "${layers[@]}" > "$MEDIA_RETAINED_RENDERS/$app.yaml"
done
kubeconform -strict -summary -ignore-missing-schemas "$MEDIA_RETAINED_RENDERS"/*.yaml \
  scripts/media-retained/production/*-bindings.yaml \
  scripts/media-retained/production/*-source-hold.yaml \
  scripts/media-retained/production/guard-configmap.yaml \
  scripts/media-retained/production/cleanuparr-postgresql/*.yaml \
  scripts/media-retained/production/cleanuparr-postgresql/enrollment/*.yaml
python3 scripts/test-media-retained.py
