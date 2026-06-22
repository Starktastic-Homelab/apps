# ADR 0001: Use Debian + K3s over Talos

- **Status:** Accepted
- **Date:** 2026-06-22

## Context

The cluster needs a node OS and Kubernetes distribution. Two broad options were weighed:
an immutable, API-driven appliance OS (Talos) versus a general-purpose Linux (Debian) running
a lightweight Kubernetes distribution (K3s). The homelab runs GPU workloads (SR-IOV) and some
non-Kubernetes / device-attached needs, and is operated hands-on by a single maintainer.

## Decision

Run Debian (current: trixie) on the nodes with K3s as the Kubernetes distribution.

## Rationale

- **GPU SR-IOV and device flexibility:** DKMS/kernel-pinned drivers and direct device access
  are well-supported on Debian; the equivalent is harder on an immutable appliance OS that
  relies on system extensions.
- **Operability:** Full SSH/apt access and a battle-tested ecosystem suit hands-on
  maintenance and debugging.
- **Low friction:** K3s is a single, lightweight distribution with sane defaults (it bundles
  flannel, a service LB, traefik — we selectively disable what we replace).

Talos's smaller, immutable attack surface and declarative `talosctl` config are real
benefits, but do not outweigh GPU/device flexibility and familiarity for this homelab.

## Consequences

- Larger attack surface than an immutable OS; mitigated by keeping nodes patched and minimal.
- Node config is managed declaratively via Packer + cloud-init + Ansible rather than a single
  appliance API.
- Revisit if GPU/device needs disappear or immutability becomes a priority.
