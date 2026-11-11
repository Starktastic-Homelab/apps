# ADR 0014: Gate *.internal with a dedicated admin outpost

- **Status:** Accepted
- **Date:** 2026-11-10

## Context

The admin Homepage (`homepage-admin`) is public at `admin.starktastic.net`. Its route uses `authentik-admin-middleware`
and is meant to admit only `authentik Admins`. A read-only check of the live config on 2026-11-07 showed that it admits
every account:

- The middleware adds `?app=admin-auth`, but Authentik's 2026.8 Rust proxy outpost never reads `app`. It picks a
  provider from the host alone: first an exact match on the external host, then the longest forward_domain cookie
  domain that the host ends with.
- "Admin Auth Provider" has the same external host as "Wildcard Proxy Provider" (`https://auth.starktastic.net`).
  The outpost keeps one provider per host and loads them in name order, so Wildcard replaces Admin Auth on every load.
  The admin-only binding on `admin-auth` is never consulted. Renaming a provider so that Admin Auth sorts last would
  instead give every forward-auth host to an admins-only app. This is the "rename trap".
- The Wildcard app's expression policy "Internal vs External Logic" is meant to make `*.internal` superuser-only. It
  only runs at OAuth authorize, where the host is always `auth.starktastic.net`, so it always allows. The
  forward_domain cookie covers all of `starktastic.net`, so one login opens every forward-auth host.

So any account can open the admin page and, from the home network, the 17 forward-auth hosts on `*.internal`. The
Homepage redesign moves the admin page to `admin.internal.starktastic.net` (home network and WireGuard only) and needs
a real admin-only gate there.

## Decision

Add a second, Git-deployed Authentik proxy outpost that admits only `authentik Admins` and gates `*.internal`.

- **Outpost.** `ak-outpost-internal-gate` in `infrastructure/controllers/authentik/manifests/`, following the LDAP
  outpost pattern. It runs `ghcr.io/goauthentik/proxy` at the chart's version, with 1 replica, the `Recreate`
  strategy, startup and readiness probes on `/outpost.goauthentik.io/ping`, and no liveness probe. The token comes
  from a SealedSecret. A NetworkPolicy admits only Traefik on port 9000 and Prometheus on port 9300.
- **Authentik objects.** These are created in the UI, as ADR 0016 does for applications and providers:
  - Provider "Internal Gate Provider": forward auth (domain level). Its external host and Authentication URL are both
    `https://auth.internal.starktastic.net`. Cookie domain `internal.starktastic.net`. Access token validity
    `hours=24`. Unauthenticated URLs/Paths and both federation lists are empty.
  - Application `internal-gate`, with launch URL `https://admin.internal.starktastic.net/`.
  - Outpost `internal-gate`. It has no integration, holds this one application, and is never added to the embedded
    outpost.
  - Its only binding is `authentik Admins`, kept in `blueprints/app-access.yaml` (ADR 0016).
- **Routing.**
  - A new middleware, `authentik-internal-gate`, sends forwardAuth to the outpost's Service with no `?app=`.
  - An IngressRoute on `websec-int` only sends `auth.internal.starktastic.net/outpost.goauthentik.io/` to the outpost.
  - In the ingress chart, `authAdmin: true` now selects `authentik-internal-gate`.
- **Admin page.**
  - `homepage-admin` moves to `domainType: internal` on `admin.internal.starktastic.net`. Its allowed host and probe
    hosts change to match.
  - A NetworkPolicy admits only Traefik.
  - `admin.starktastic.net` stops existing.
- **Core cookie.** `AUTHENTIK_COOKIE_DOMAIN` is removed first, so `authentik_session` is host-only on
  `auth.starktastic.net`.
- **Cleanup.** `admin-auth` and its provider are deleted (application first) to remove the rename trap. Then
  `middleware-admin.yaml` is deleted. MicroBin `/admin` moves to `authentik-middleware`, because its own sealed
  password (#1561) is now the admin check.
- **Other internal apps** move to the gate in batches, but only after a check that nobody in the household uses them.
  The order is pgAdmin, the Traefik dashboard and Falco; then Grafana; then zigbee2mqtt and changedetection; then the
  media apps. The `-ru` variants set `authAdmin` explicitly.
  - Done in one PR on 2026-11-11: all 17 forward-auth `.internal` hosts. Over the previous 31 days only `benf` had
    used them (Authentik authorize events, Traefik access logs). The `helmarr-api` account isn't an Admin, so
    Helmarr lost bazarr, prowlarr, qBittorrent, Radarr and Sonarr (Ben accepted). Apps with their own sign-in
    (`auth: false`) and Home Assistant stay as they are.
- **Guards.**
  - `scripts/check-admin-gate.py` runs in the required Validate job and renders like ArgoCD. It asserts:
    - the middleware target, and that no forwardAuth address carries `?app=`;
    - 1 replica, with an image tag equal to the chart's;
    - that every gated route is on `websec-int` only, with `.internal` hosts only;
    - the single homepage-admin route and its exact allowed host;
    - that `AUTHENTIK_COOKIE_DOMAIN` is absent;
    - that every referenced middleware exists.

    `scripts/check-homepage-household.py` (ADR 0018) already guards the household page, so this script doesn't
    repeat those checks.
  - A blackbox canary requires a logged-out 302 to the authorize URL with the callback on `auth.internal`, and 404s
    for `admin.starktastic.net` and for `auth.internal` on the public LB. The alerts are `AdminGateOpen`,
    `AdminGateWrongProvider`, `AdminGateDown` and `AdminGateCanaryMissing`, all sent to ntfy.
  - Renovate does not automerge the authentik group (`automerge: false` in `renovate.json`), so a gate bump gets a human check.
- **No IP allowlist.** The boundary is the entrypoint plus the login. Internal routes exist only on `websec-int`
  (10.9.9.90:443 to 8444), and the public LB has no port to it.

## Rationale

- **A separate outpost fails closed.** A host it can't match is handled by its only application, so login and the
  admin check still apply. A detached provider leaves it with no apps, so it returns 400. If it is down, Traefik
  returns 500. The same provider in the embedded outpost would fall back to the open Wildcard provider in each of
  these cases.
- **Why not one provider per host?** Domain level covers every internal host with one provider, so moving an app is a
  one-line `authAdmin` change.
- **Why MicroBin isn't in the gate.** A second application would end the single-app fallback, and the gate would have
  to serve a public host. MicroBin's own password is a smaller change.
- **Why the UI for objects and the blueprint for the binding.** That is ADR 0016's split. A blueprint does not restore
  a binding deleted in the UI, so the binding is covered by the post-change test and the flag flip below, not by
  self-healing.
- **Why 1 replica.** A standalone outpost stores sessions as files in its own `/dev/shm`, so a second replica would
  split them.
- **Why drop the core cookie domain.** It sends `authentik_session` to every `*.starktastic.net` backend. The gate's
  integrity depends on that session.

## Consequences

- **Lost binding fails open.** If the gate's binding is deleted or disabled, every account is admitted, and the
  logged-out canary can't see it. Until every app is bound and "Allow application access with no policies" is
  switched off (Home Assistant is bound since 2026-11-11; the open-on-purpose apps then need an explicit binding
  first), Ben runs a non-admin test after every Authentik change. After the
  switch, a lost binding denies everyone. `/if/admin` stays reachable.
- **Federation fails open.** Listing the gate provider in another provider's federation lists would let that
  provider's tokens through. Never do it.
- **Restarts sign everyone out.** A gate restart (a Renovate bump or a pod move) ends all gate sessions. Signing back
  in is silent while the core session lasts. A restart is also the emergency logout.
- **Removing an admin** leaves them up to 24h of access. To end it at once: revoke their sessions, restart the gate
  pod, and rotate the MicroBin admin password.
- **The gate can stall deploys.** It lives in the `authentik` app (controllers phase), so a gate that never goes
  Ready stalls the services phase. Check the gate is healthy before PR 3. Reverting PR 2 deploys even when the gate
  is unhealthy.
- **Fix forward after cleanup.** Once `middleware-admin.yaml` is deleted, a revert of the admin-page move references a
  missing middleware and fails closed.
- **Same-node bypass.** The NetworkPolicies are defence in depth. A hostNetwork pod on the same node (Home Assistant)
  bypasses them, as ADR 0013 records. Both policies are exceptions to ADR 0008.
- **Session fixation.** The outpost keeps the pre-login session id at the callback, so a gate cookie planted from
  another `*.starktastic.net` origin could share a session. Ben chose (2026-11-11) not to report it upstream.
  - HSTS (2026-11-11): Traefik sends `Strict-Transport-Security: max-age=31536000; includeSubDomains` on websecure
    and websec-int, so a network attacker can't plant cookies over plain HTTP. Every name under these domains must
    keep valid TLS.
  - Inventory of apps serving user HTML (2026-11-11): MicroBin was the one real path. Anyone could `POST /upload` an
    HTML or SVG file and have `/file/{id}?preview=true` serve it inline. The create POST is now behind Authentik, and
    uploaded content is served under `Content-Security-Policy: sandbox`. Every other app on `starktastic.net` or
    `internal.starktastic.net` is low or none: writers are Admins only, or content is served as an attachment or
    under a sandbox.
- **Never rename `authentik Admins`.** The gate binding follows the group, but ansible's ArgoCD RBAC matches its name.
- **Household members lose access** to each internal app as it moves, by design.
- **Configuration-error mail (checked 2026-11-11).** An email transport exists, but every default notification rule
  has no destination group and doesn't notify the event user, so nobody gets mail and a bad-port Host can't flood
  anyone. No configuration-error event had been recorded.
