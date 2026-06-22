# ADR 0003: Use the bjw-s app-template chart for services

- **Status:** Accepted
- **Date:** 2026-06-22

## Context

The cluster runs ~60 services, most of which are simple "one Deployment + Service + optional
Ingress/PVC" workloads. Hand-writing manifests or a bespoke chart per service would be
repetitive and inconsistent.

## Decision

Render services from the common `app-template` chart (`bjw-s-labs`, version `5.0.1`,
`https://bjw-s-labs.github.io/helm-charts`), configured through a layered value cascade
(`templates/globals.yaml` → `templates/common.yaml` → per-family extras → service `values.yaml`).

## Rationale

- **DRY:** One well-maintained chart expresses controllers/containers/services/ingress/PVCs
  for the whole fleet; per-service files carry only what differs.
- **Consistent defaults:** Shared `common.yaml` applies cluster-wide conventions uniformly.
- **Pinned:** A single chart version (`5.0.1`) is upgraded deliberately in one place.

## Consequences

- Services inherit the chart's structure (`controllers.main.containers.main`...); unusual
  workloads may need raw manifests (supported via `manifests: true`).
- `infrastructure/**` apps intentionally do **not** consume `common.yaml`.
