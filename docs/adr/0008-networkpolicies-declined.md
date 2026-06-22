# ADR 0008: Cluster-authored NetworkPolicies declined (for now)

- **Status:** Accepted
- **Date:** 2026-06-22

## Context

A zero-trust, default-deny NetworkPolicy rollout (per-namespace / per-service) was considered.
The CNI already enforces NetworkPolicy (see ADR 0007), so this was feasible on the current
stack without any CNI change.

## Decision

Do not author a cluster-wide default-deny / per-service NetworkPolicy set at this time. The
existing chart-shipped policies remain in effect.

## Rationale

- **A want, not a need:** No current security driver justifies the authoring and ongoing
  maintenance burden across ~60 services.
- **Maintenance cost:** A default-deny posture requires enumerating and maintaining allow
  rules for every legitimate flow; high churn for a single maintainer.
- **Reversible:** Can be adopted later; policies are CNI-portable (see ADR 0007).

## Consequences

- East-west traffic is not locked down beyond what individual charts ship.
- Reconsider alongside any change to the threat model or if ADR 0007's triggers move the
  cluster toward Cilium (where Hubble would ease safe authoring).
