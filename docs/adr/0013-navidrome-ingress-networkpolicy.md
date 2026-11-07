# ADR 0013: Restrict Navidrome ingress with one NetworkPolicy

- **Status:** Accepted
- **Date:** 2026-11-07

## Context

Navidrome's reverse-proxy login trusts `X-authentik-username` from any peer in `ND_EXTAUTH_TRUSTEDSOURCES`
(`10.42.0.0/16`, the whole pod CIDR) and skips the password check, Subsonic API included. apps#1527 strips client-sent
`X-authentik-*` headers at Traefik's `websecure` and `websec-int` entrypoints, which closed the public path through
`music.benplus.app/rest/`. Every pod could still reach `navidrome.media:4533` directly and claim any user. Narrowing
`ND_EXTAUTH_TRUSTEDSOURCES` to Traefik does not work: Traefik is a DaemonSet whose pod IPs change on every restart, and
any CIDR that covers them also covers the other pods on those nodes. ADR 0008 declined a cluster-wide NetworkPolicy set
for lack of a security driver; this is one, as in ADR 0011 (Loki) and ADR 0012 (pgAdmin).

## Decision

Add one ingress-only NetworkPolicy, `navidrome-ingress` in `services/media/navidrome/manifests/`. It selects the
Navidrome pod and admits only Traefik (`traefik-system`) and the two Homepage instances, `homepage` and
`homepage-admin` (`operations`), whose navidrome widget and `siteMonitor` call the Service directly. No other policy
selects the pod. ADR 0008 still holds for everything else.

## Rationale

- kube-router (ADR 0007) enforces NetworkPolicy and accepts traffic from the pod's own node, so the kubelet TCP probes
  still pass. ADR 0011 and ADR 0012 use the same shape.
- Turning off reverse-proxy auth would drop SSO for the web UI. Traefik is the only path that sets the header, and it
  now strips client copies first.
- Ingress-only and without port lists, so Navidrome's egress (Last.fm, artwork lookups) doesn't change.

## Consequences

- A new in-cluster Navidrome client (a scrobbler, Music Assistant, another dashboard) must be added to the policy.
  kube-router rejects the rest, so they fail fast with connection refused.
- A Traefik or Homepage chart change, or an ArgoCD Application rename, that changes `app.kubernetes.io/name` or
  `app.kubernetes.io/instance` cuts that client off: `music.benplus.app` then returns 502, or Homepage shows Navidrome
  as down. Renaming the `navidrome` Application unselects its pod, which silently removes the protection.
- Any other NetworkPolicy in `media` that selects Navidrome (including `podSelector: {}`) adds to this one and voids it.
  On changes there, check the diff preview for new NetworkPolicies in `media`.
- kube-router accepts node-local sources ahead of every policy, so hostNetwork pods on Navidrome's node (Home Assistant
  shares a worker with it about half the time, plus node-level DaemonSets) can still reach it.
- Both Homepage pods can still send the header. Apart from Traefik and those node-local sources, they are the remaining
  path.
