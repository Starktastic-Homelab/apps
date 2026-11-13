# Architecture Decision Records (ADRs)

This directory records significant technical decisions for the homelab — *why* the stack is
the way it is. Each ADR is a short, immutable record: when a decision changes, add a new ADR
that supersedes the old one (don't rewrite history).

## How to add an ADR

1. Copy `template.md` to `NNNN-kebab-title.md` (next free number).
2. Fill in Status, Context, Decision, Rationale, Consequences.
3. Add a row to the index below.

## Index

| #    | Decision                                              | Status   |
| ---- | ----------------------------------------------------- | -------- |
| 0001 | [Use K3s over Talos](0001-use-k3s-over-talos.md)      | Accepted |
| 0002 | [ArgoCD app-of-apps](0002-argocd-app-of-apps.md)      | Accepted |
| 0003 | [bjw-s app-template for services](0003-bjw-s-app-template.md) | Accepted |
| 0004 | [sealed-secrets for secret management](0004-sealed-secrets.md) | Accepted |
| 0005 | [MetalLB (L2) for LoadBalancer IPs](0005-metallb-l2.md) | Accepted |
| 0006 | [kube-vip for the control-plane VIP](0006-kube-vip-control-plane-vip.md) | Accepted |
| 0007 | [CNI: Flannel + kube-router; defer Cilium](0007-cni-flannel-kube-router.md) | Accepted |
| 0008 | [NetworkPolicies declined](0008-networkpolicies-declined.md) | Accepted |
| 0009 | [Explicit `storageClassName` over a default class](0009-explicit-storageclass-over-default.md) | Accepted |
| 0010 | [Karakeep search index is rebuildable](0010-karakeep-search-index-rebuildable.md) | Accepted |
| 0011 | [Restrict Loki ingress with one NetworkPolicy](0011-loki-ingress-networkpolicy.md) | Accepted |
| 0012 | [Restrict pgAdmin ingress with one NetworkPolicy](0012-pgadmin-ingress-networkpolicy.md) | Accepted |
| 0013 | [Restrict Navidrome ingress with one NetworkPolicy](0013-navidrome-ingress-networkpolicy.md) | Accepted |
| 0014 | [Gate *.internal with a dedicated admin outpost](0014-internal-admin-gate.md) | Accepted |
| 0015 | [Reserve app-local usernames in the invitation flow](0015-reserve-app-local-usernames.md) | Accepted |
| 0016 | [Bind admin-only Authentik apps with a blueprint](0016-authentik-app-access-blueprint.md) | Accepted |
| 0018 | [Household Homepage boundary](0018-household-homepage-boundary.md) | Accepted |
| 0019 | [Homepage catalog generator](0019-homepage-catalog-generator.md) | Accepted |
| 0020 | [Homepage dashboards on stable hooks with a render check](0020-homepage-dashboards-stable-hooks.md) | Proposed |
