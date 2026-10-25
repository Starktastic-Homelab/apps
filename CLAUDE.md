# apps

GitOps source for the cluster: ApplicationSets in `bootstrap/appsets/` deploy every `app.yaml` under
`infrastructure/**` and `services/**`. Stage 4 of packer → terraform → ansible → apps (Ansible installs
ArgoCD with a root app watching `bootstrap/`); the system overview is `../CLAUDE.md`.

## What runs live

- ArgoCD deploys from `main`. `refresh.yaml` (push to `main`) only runs `argocd app get --refresh` for
  the apps a commit touched; it never syncs. A `[skip ci]` direct push also skips the refresh.
- cluster-apps use RollingSync (CRDs → foundation → controllers → services), which turns autosync and
  self-heal off, so drift doesn't heal by itself. base-configs and infra-configs keep autosync.
- Every Application has `prune: true` plus the resources finalizer: deleting or renaming an app dir, or
  changing its `name`, deletes its resources; deleting an ApplicationSet file cascades to all its apps.
  Storage objects survive only through their `Prune=false,Delete=false` sync-option annotations.
- Renovate automerges minor/patch/digest updates after 3 days (rules in `renovate.json`): that's a deploy.
- `format.yaml` and `diagrams.yml` push commits to PR branches; pull before pushing.

## Commands

`validate-and-diff.yml` has the full list (~40 retained-storage steps): copy a step, don't improvise.

```sh
pre-commit run --files <changed files>
YAMLLINT_CONFIG_FILE=.github/yamllint.yaml yamllint .
# kubeconform: copy the "Validate static manifests" step (fetches schemas)
python3 scripts/check-homepage-coverage.py    # PyYAML + helm
python3 scripts/check-jellyfin-compat.py      # PyYAML + helm + curl
python3 scripts/check-alert-policy.py docker run --rm -i --network none --entrypoint promtool prom/prometheus:<ver>
node scripts/check-linuxserver-tags.mjs       # offline assertion on renovate.json
python3 scripts/check-readme-images.py
helm template configs infrastructure/configs -f templates/globals.yaml
bash scripts/render-diagrams.sh [--check]
```

Seal secrets offline with `scripts/seal.sh <name> <namespace> [--cluster-wide]`; never commit plaintext.

## Safe vs ask first

- Safe: everything under Commands, `helm template`, `kubeconform`, `scripts/test-*.py` (some need Docker).
- Ask first: `kubectl`, `argocd`, `helm install/upgrade/uninstall` against the cluster (live ops run from
  VM300, never this workstation), pushing to `main`, merging PRs, `gh workflow run`.

## Before calling a change done

Run yamllint, the CI steps for what you touched, and render changed charts with the real value layers.
Report what ran. The PR's ArgoCD diff preview is the review of record; renders don't qualify storage.

## Gotchas and past decisions

- Service values layer `templates/globals.yaml` → `templates/common.yaml` → extras → base or own
  `values.yaml` → variant `values.yaml` only with `valuesOverride: true` (`bootstrap/appsets/cluster-apps.yaml`).
  `common.yaml` reaches only `services/**`.
- An app's `name` must equal its directory (refresh scoping). Keep the `argocd-diff-preview/watch-pattern`
  annotations, or the diff preview comes back empty.
- Set `storageClass` explicitly (ADR 0009): local-path stays default; app-template ignores `global.storageClass`.
- No `*.svc.cluster.local` names (ndots leak; CI greps): use `service` or `service.namespace`.
- `templates/ingress-chart` picks entrypoints and middlewares from `domainType`. Every ingress host goes on
  homepage-admin, non-internal ones on homepage too (`check-homepage-coverage.py`).
- Retained storage (`infrastructure/system/proxmox-csi/README.md`, `docs/runbooks/`): prebind PVs; grow the
  PVC, verify, then update the Git PV; never force-detach, recreate images, drop RWOP or prune protection,
  or fake markers to pass a guard. Each volume takes one of 29 slots per worker; change that with ansible.
- Maintenance holds are an operation-owned AppProject deny window; toggling autosync is not a hold.
- Only PostgreSQL and TLS certs are backed up. FlareSolverr image changes need the Falco exception (README).
- Record decisions as ADRs (`docs/adr/`). `docs/superpowers/`, `docs/handoffs/`, `BACKLOG.md` are history.

## Contracts

Changing a contract means changing both sides together; see `../CLAUDE.md`.

- ← ansible: root app, ArgoCD settings, org secret `KUBECONFIG_RAW` (used by `refresh.yaml`). apps owns
  `infrastructure/configs/templates/argocd/` (notifications ConfigMap and Secret).
- ↔ ansible: `scripts/sealed-secrets-cert.pem` (ansible seeds the key and pins this file by SHA), worker
  labels, CSI topology and slots (`infrastructure/system/proxmox-csi/`,
  `services/operations/kube-prometheus-stack/manifests/proxmox-csi-capacity.yaml`), the
  `infrastructure/base-configs/templates/cert-backup` layout, NFS in `templates/globals.yaml`.

## Git

Commit only in this repo. Never push or open PRs unless asked. Never commit secrets or unsealed values.
