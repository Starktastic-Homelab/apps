# ADR 0007: CNI — keep Flannel + kube-router; defer Cilium

- **Status:** Accepted
- **Date:** 2026-06-22

## Context

A migration to Cilium was considered (for L7/DNS policy, Hubble observability, kube-proxy
replacement, and to consolidate MetalLB). A prior assumption held that Flannel cannot enforce
NetworkPolicy and that a CNI change was therefore required. Investigation disproved this: K3s
ships Flannel **and** an embedded kube-router NetworkPolicy controller, and the cluster does
**not** pass `--disable-network-policy` — so standard `networking.k8s.io/v1` NetworkPolicies
are already enforced (confirmed by chart-shipped policies in effect today).

## Decision

Stay on **Flannel + embedded kube-router** (and MetalLB + kube-vip + Traefik as-is). Do not
migrate to Cilium at this time.

## Rationale

- **No concrete need:** Interest in Cilium is curiosity / "best practice," not a missing
  capability.
- **The forcing premise was false:** NetworkPolicy is already enforced; nothing is blocked by
  the current CNI.
- **Migration risk outweighs benefit:** An in-place CNI swap on a running cluster (removing
  Flannel + kube-proxy, possibly MetalLB) carries real downtime risk; the cluster is relied
  upon day-to-day.
- **Portability protects the option:** Standard NetworkPolicies are CNI-portable; Cilium
  implements the same API, so a future migration is re-test, not rewrite.

## Revisit triggers

Re-open (toward Cilium) if any become true:

1. L7/DNS-aware policy is needed (e.g. egress allow-lists by hostname).
2. Observability gaps make "what talks to what" painful and Hubble would clearly help.
3. The cluster is being rebuilt anyway (near-zero marginal cost).
4. A deliberate goal to consolidate Flannel + kube-proxy + MetalLB into one platform.
5. A NetworkPolicy edge case kube-router cannot satisfy.

## Consequences

- No code or runtime change.
- A future hands-on Cilium evaluation, if desired, should run on a disposable VM/cluster, not
  the live cluster.
