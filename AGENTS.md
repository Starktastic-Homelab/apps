# Repository Guidelines

## Purpose and layout

This repository defines the ArgoCD-managed application layer of the homelab.
Read `README.md` for architecture and `.github/workflows/validate-and-diff.yml`
for the current validation procedure.

- `bootstrap/appsets/`: ApplicationSet discovery, source composition, and rollout phases.
- `infrastructure/`: cluster controllers, shared configuration, and storage.
- `services/{home-automation,media,operations}/`: application definitions.
- `templates/`: shared values and the reusable ingress Helm chart.
- `scripts/`: scaffolding, secret sealing, and policy checks.
- `docs/diagrams/`: D2 sources and rendered documentation assets.

## Editing conventions

Follow nearby `app.yaml` and `values.yaml` examples. Preserve the ApplicationSet
value cascade and `baseApp` inheritance; variants should contain only overrides.
Keep cluster-wide settings in `templates/globals.yaml` and shared defaults in
`templates/common.yaml`. Preserve rollout dependencies: CRDs, foundation,
controllers, then services. Shared templates can affect many applications.

Use `templates/ingress-chart/` conventions for ingress. Keep Renovate annotations
and image pins intact. FlareSolverr image changes also require checking the scoped
Falco exception documented in `README.md`. Use `scripts/seal.sh` for SealedSecret
creation; never commit plaintext credentials or private sealing keys.

## Validation

Run from the repository root, selecting checks relevant to the change:

- `pre-commit run --files <changed-files>`: configured formatting and lint hooks.
- `yamllint -c .github/yamllint.yaml .`: YAML validation.
- `python3 scripts/check-homepage-coverage.py`: dashboard coverage.
- `python3 scripts/check-jellyfin-compat.py`: Jellyfin integration compatibility.
- `python3 scripts/check-alert-policy.py`: rendered alert/Falco policy; requires Helm, Docker, PyYAML, and promtool as documented in the README.
- `node scripts/check-linuxserver-tags.mjs`: registry-backed image-tag checks.
- `python3 scripts/check-readme-images.py`: documentation image references.

For schema validation, follow the workflow's kubeconform invocation and exclusions:
raw manifests only, excluding blueprints, Helm templates, and Chart metadata.
Render Helm changes with their actual value layers before evaluating the result.
Diagram edits use `bash scripts/render-diagrams.sh` and include the regenerated assets.

## Delivery

ArgoCD reconciliation and pushes to `main` can change live workloads. Keep live
syncs or imperative cluster changes within the user's requested deployment scope.
Describe affected apps, validation results, and any checks blocked by missing
tools or access. Do not treat successful local linting as a successful rollout.
