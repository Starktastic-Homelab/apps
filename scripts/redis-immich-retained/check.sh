#!/usr/bin/env bash
set -euo pipefail
umask 077
cd "$(dirname "$0")/../.."
: "${REDIS_CHART:?Set the exact Redis chart directory}"
: "${APP_TEMPLATE_CHART:?Set the exact app-template chart directory}"
: "${REDIS_IMMICH_RENDERS:?Set a private output directory}"
mkdir -p "$REDIS_IMMICH_RENDERS/desired-values" "$REDIS_IMMICH_RENDERS/rules"
python3 - "$REDIS_CHART" "$APP_TEMPLATE_CHART" "$REDIS_IMMICH_RENDERS" <<'PY'
import sys, os
from pathlib import Path
import yaml
redis,app,out=map(Path,sys.argv[1:])
assert not out.is_symlink() and out.stat().st_uid==os.getuid() and out.stat().st_mode&0o077==0, 'Use a private 0700 render directory'
assert yaml.safe_load((redis/'Chart.yaml').read_text())['version']=='28.3.1'
assert yaml.safe_load((app/'Chart.yaml').read_text())['version']=='5.3.0'
redis_app=yaml.safe_load(Path('infrastructure/controllers/databases/redis/app.yaml').read_text())
assert redis_app['chart']['version']=='28.3.1' and redis_app['namespace']=='databases'
appset=yaml.safe_load(Path('bootstrap/appsets/cluster-apps.yaml').read_text())
categories=appset['spec']['generators'][0]['matrix']['generators'][0]['list']['elements']
services=next(x for x in categories if x['category']=='services')
infra=next(x for x in categories if x['category']=='infrastructure')
immich_app=yaml.safe_load(Path('services/media/immich/app.yaml').read_text())
assert (immich_app.get('chart',{}).get('version') or services['defaultChartVersion'])=='5.3.0'
assert services['commonValues']=='templates/common.yaml' and infra['commonValues']==''
# Helm cannot remove these service-defined keys with null: the upstream schema
# forbids null fsGroup. Materialize only the three intended deletions before
# applying the inactive overlay through the normal values cascade.
source=yaml.safe_load(Path('services/media/immich/values.yaml').read_text())
pg=source['controllers']['postgres']
pg['pod']['securityContext'].pop('fsGroup',None)
pg.get('initContainers',{}).pop('rm-postmaster-lock',None)
source['persistence']['pgdata']['advancedMounts']['postgres'].pop('rm-postmaster-lock',None)
rule=yaml.safe_load(Path('scripts/redis-immich-retained/production/redis-prometheus-rules.yaml').read_text())
(out/'rules/redis-aof.yaml').write_text(yaml.safe_dump(rule['spec'],sort_keys=False))
(out/'rules/tests.yaml').write_text(Path('scripts/redis-immich-retained/prometheus-tests.yaml').read_text())
(out/'desired-values/immich-base.yaml').write_text(yaml.safe_dump(source,sort_keys=False))
PY
helm template redis "$REDIS_CHART" --namespace databases --kube-version 1.37.0 -f templates/globals.yaml -f infrastructure/controllers/databases/redis/values.yaml >"$REDIS_IMMICH_RENDERS/redis-before.yaml"
helm template redis "$REDIS_CHART" --namespace databases --kube-version 1.37.0 -f templates/globals.yaml -f infrastructure/controllers/databases/redis/values.yaml -f scripts/redis-immich-retained/production/redis-values.yaml >"$REDIS_IMMICH_RENDERS/redis.yaml"
helm template immich "$APP_TEMPLATE_CHART" --namespace media --kube-version 1.37.0 -f templates/globals.yaml -f templates/common.yaml -f services/media/immich/values.yaml >"$REDIS_IMMICH_RENDERS/immich-before.yaml"
helm template immich "$APP_TEMPLATE_CHART" --namespace media --kube-version 1.37.0 -f templates/globals.yaml -f templates/common.yaml -f "$REDIS_IMMICH_RENDERS/desired-values/immich-base.yaml" -f scripts/redis-immich-retained/production/immich-values.yaml >"$REDIS_IMMICH_RENDERS/immich.yaml"
kubeconform -strict -summary -ignore-missing-schemas -schema-location default -schema-location 'https://raw.githubusercontent.com/datreeio/CRDs-catalog/main/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json' "$REDIS_IMMICH_RENDERS"/*.yaml scripts/redis-immich-retained/production/*-bindings.yaml scripts/redis-immich-retained/production/*-source-hold.yaml scripts/redis-immich-retained/production/*-guard-configmap.yaml scripts/redis-immich-retained/production/redis-prometheus-rules.yaml
python3 scripts/test-redis-immich-manifests.py
if command -v promtool >/dev/null; then
  (cd "$REDIS_IMMICH_RENDERS/rules" && promtool test rules tests.yaml)
else
  # Validation tool only, matching the repository's current promtool version.
  tool_image=${PROMTOOL_IMAGE:-prom/prometheus:v3.15.0@sha256:efd719c99d83b060d9daefdcf00360461adf279f45ef5391f8d111892118753e}
  docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges --tmpfs /tmp \
    --user "$(id -u):$(id -g)" --mount "type=bind,src=$REDIS_IMMICH_RENDERS/rules,dst=/rules,readonly" \
    --workdir /rules --entrypoint /bin/promtool "$tool_image" test rules tests.yaml
fi
