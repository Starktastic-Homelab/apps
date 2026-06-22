# ADR 0002: GitOps via ArgoCD app-of-apps (ApplicationSet + RollingSync)

- **Status:** Accepted
- **Date:** 2026-06-22

## Context

The cluster's workloads and infrastructure must be deployed declaratively and in a
dependency-aware order (CRDs before the controllers that need them, foundational services
before the apps that depend on them).

## Decision

Use ArgoCD with an app-of-apps pattern: a single bootstrap `ApplicationSet` (`cluster-apps`)
generates one Argo `Application` per discovered `app.yaml`, and a `RollingSync` strategy
orders rollout by a `deploy-phase` label.

## Rationale

- **One entry point:** New apps are added by committing an `app.yaml`; the ApplicationSet
  discovers and renders them — no per-app Application boilerplate.
- **Ordered rollout:** `RollingSync` steps process phases in order:
  `crds → foundation → controllers → services`, so dependencies come up before dependents.
- **Declarative & auditable:** All state lives in Git and is reconciled by Argo.

## Consequences

- A stuck/failed app in an early phase **blocks** later phases until resolved — ordering
  guarantees come at the cost of a global rollout dependency.
- Each app must declare its `deployPhase` (a default applies per category).
