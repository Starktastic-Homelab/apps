# ADR 0005: MetalLB in L2 mode for LoadBalancer IPs

- **Status:** Accepted
- **Date:** 2026-06-22

## Context

Bare-metal Kubernetes has no cloud load-balancer. `Service` type `LoadBalancer` needs an
implementation to assign and announce external IPs on the home LAN. (K3s's bundled servicelb
is disabled.)

## Decision

Use **MetalLB** in **L2 (ARP) mode** with a single `IPAddressPool` covering the LAN addresses
used by ingress and a few directly-exposed services (external, internal, Home Assistant, and
two qBittorrent endpoints).

## Rationale

- **Simplicity:** L2/ARP needs no BGP-capable router or extra network config — it just answers
  ARP for the pool addresses. Appropriate for a flat home network.
- **Sufficient scale:** A handful of LoadBalancer services; no need for ECMP/BGP throughput.

## Consequences

- L2 mode funnels traffic for a given IP through one elected node (failover, not load
  spreading) — acceptable at homelab scale.
- Pool addresses must stay outside the DHCP range to avoid conflicts.
- Revisit BGP mode only if multi-node ingress throughput becomes a constraint.
