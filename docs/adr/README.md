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
