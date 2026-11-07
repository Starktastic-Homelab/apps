# ADR 0012: Restrict pgAdmin ingress with one NetworkPolicy

- **Status:** Accepted
- **Date:** 2026-11-07

## Context

pgAdmin uses webserver authentication: it logs in whichever existing pgAdmin user the `X-authentik-email` request header
names, with no password. Traefik's `authentik-middleware` sets that header for `pgadmin.internal`. The pgAdmin pod
itself trusts any sender, though, and every pod in the cluster could reach `pgadmin-pgadmin4.databases:80`. The admin
user's email is `env.email` in this public repository. `MASTER_PASSWORD_REQUIRED` is off, so a forged login also gets the
saved connection to the primary Postgres. `WEBSERVER_AUTO_CREATE_USER` is off, so only existing users can be claimed.
ADR 0008 declined a cluster-wide NetworkPolicy set because there was no security driver. This exposure is one, as
ADR 0011 found for Loki.

## Decision

Add one ingress-only NetworkPolicy, `pgadmin-ingress` in `infrastructure/controllers/databases/pgadmin/manifests/`. It
selects the pgAdmin pod and admits only Traefik (`traefik-system`) and homepage-admin (`operations`), whose
`siteMonitor` polls the Service directly. ADR 0008 still holds for everything else.

## Rationale

- kube-router (ADR 0007) enforces NetworkPolicy and accepts traffic from the pod's own node, so kubelet probes still
  pass. The Loki policy (ADR 0011) has the same shape.
- Turning off webserver authentication would drop SSO. An Authentik proxy outpost in front of pgAdmin would add a
  component, and pgAdmin would still trust the header from whatever reaches it.
- Traefik now strips client-sent `X-authentik-*` headers at its entrypoints, so the remaining path was other pods.
- Ingress-only and without port lists, so pgAdmin's egress to Postgres doesn't change.

## Consequences

- A new pgAdmin client (another dashboard monitor, a second ingress controller) must be added to the policy.
- A Traefik or Homepage chart change that renames `app.kubernetes.io/name` or `app.kubernetes.io/instance` cuts that
  client off: pgadmin.internal then times out, or Homepage shows pgAdmin as down.
- homepage-admin can still send the header. That pod is now the only path other than Traefik.
