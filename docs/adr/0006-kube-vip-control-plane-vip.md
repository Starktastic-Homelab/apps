# ADR 0006: kube-vip for the control-plane VIP

- **Status:** Accepted
- **Date:** 2026-06-22

## Context

The Kubernetes API should be reachable at a single, stable address that survives the loss of
any individual control-plane node, rather than pinning clients to one node IP.

## Decision

Run **kube-vip** as a DaemonSet to provide a virtual IP (`10.9.9.99`) for the control plane,
elected via Kubernetes leases. K3s is installed with this VIP in its `--tls-san`.

## Rationale

- **HA API endpoint:** The VIP floats to a healthy control-plane node, so kubeconfig and
  in-cluster API traffic don't depend on one host.
- **Lease-based election:** Uses Kubernetes leader-election (no extra VRRP/keepalived stack).
- **Cert validity:** Including the VIP in `--tls-san` keeps the API certificate valid for the
  VIP address.

## Consequences

- The VIP must be a free, static LAN address outside DHCP.
- Distinct from service LoadBalancer IPs (MetalLB, ADR 0005) — kube-vip here covers only the
  control-plane endpoint.
