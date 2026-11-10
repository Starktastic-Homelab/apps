# ADR 0018: Household Homepage boundary

- **Status:** Accepted
- **Date:** 2026-11-09

## Context

The household dashboard (`services/operations/homepage`, starktastic.net) sits behind the wildcard Authentik login,
which every account passes, invited media users included. Homepage reads no identity, so every account can do
whatever the household pod can do. Read in Homepage v2.7.0 (tag `2e5f1013`), not checked live:

- `/api/services/proxy` serves every route of every widget type on the page and returns the upstream's raw body
  (`src/pages/api/services/proxy.js`). Display flags only change what renders, so Jellyfin's Pause is forwarded even
  with `enableMediaControl: false`. `prometheusmetric` takes its PromQL from the browser.
- Tile-level fields (`href`, `siteMonitor`, `description`) reach every browser verbatim, while a widget's `url`, `key`,
  `username`, `password`, `token` and `headers` stay on the server. Calendar feed URLs are stripped only when
  `integrations` is a list (`src/utils/config/service-helpers.js`).
- `hideErrors` only skips rendering (`src/components/services/widget/container.jsx`). The error JSON still reaches the
  browser, with the hostname, an in-cluster IP and the upstream's error body (`src/utils/proxy/http.js`).
- `/api/kubernetes/status/<namespace>/<app>` takes its namespace and pod selector from the browser. On household only
  `kubernetes.yaml`'s `mode: disabled` stops it, while the pod mounts a token bound to a cluster-wide read ClusterRole.
- Homepage always admits `Host: localhost:3000` (`src/utils/auth.js`), so a pod that reaches household on port 3000
  skips both Authentik and `HOMEPAGE_ALLOWED_HOSTS`.

On main, 17 of household's 18 sealed names hold admin's values (#479, #833) and six are unused. Through its widgets any
account can list every Jellyfin session with its user, IP and device and pause any of them (On TV runs on an API key,
which Jellyfin always makes Administrator), see who is listening to what on Navidrome, read per-user Immich storage, and
read the Karakeep key owner's stats.

## Decision

Household shows aggregates (counts, new arrivals, the calendar), never per-account activity. Its credentials are the
boundary: each app limits what household's credential can see or do, on every route the proxy serves.

1. **Credentials.** Each household widget runs on a credential minted for household alone, at the narrowest scope its
   app offers (a dedicated non-admin user or a scoped key), with `_HOUSEHOLD` in its name, as in
   `HOMEPAGE_VAR_CALIBRE_HOUSEHOLD_USER`. Apps that offer nothing narrower are the exception and share their one key
   with admin on purpose: Seerr has a single global key per instance, and the Sonarr and Radarr iCal feeds take only the
   full API key. Service users made for household get a reserved name (ADR 0015). The table records every household
   credential, without its value or the `HOMEPAGE_VAR_` prefix:

   | Credential                                         | Minted as                                     | Household reaches        |
   | -------------------------------------------------- | --------------------------------------------- | ------------------------ |
   | `SEERR_KEY`, `SEERR_RU_KEY`                        | Each instance's global key, shared with admin | Request and issue counts |
   | `SONARR_KEY`, `RADARR_KEY`                         | Each instance's API key, shared with admin    | The two iCal feeds       |
   | `CALIBRE_HOUSEHOLD_USER`, `CALIBRE_HOUSEHOLD_PASS` | A Calibre-Web local user with no roles        | `/opds/stats`            |

2. **Widgets.** Any widget type and tile key, except three that no credential can scope: `prometheusmetric` (the browser
   picks the PromQL and Prometheus has no login; a `customapi` with a fixed query renders the same tile), `prometheus`
   (it returns every scrape target) and `navidrome` (its only route is now-playing, which shows other users' listening
   to any Navidrome account).
3. **Fetched URLs.** Every URL the pod fetches (widget `url`s, iCal feeds, `siteMonitor`, `suggestionUrl`) is an
   in-cluster `<service>.<namespace>`, with a namespace some `app.yaml` declares, or a public `https://` name. That
   shape rules out IP literals, however they are written, and internal or LAN names. Search suggestions may use
   SearXNG's in-cluster autocompleter (`http://searxng.operations:8080/autocompleter?q=`).
4. **Errors and secrets.** Household sets `hideErrors: true`; admin keeps `false`. A `{{HOMEPAGE_VAR_*}}` placeholder
   appears only inside a service's widget block, never in a tile-level field, settings, bookmarks or info widgets, and
   calendar `integrations` is always a list.
5. **Pod.** No Kubernetes access: `automountServiceAccountToken: false`, a ServiceAccount of its own with nothing bound
   to it, and `mode: disabled` in `kubernetes.yaml`. Household restates its own access fields (`host`, `domainType`,
   `auth`, `authAdmin`, `HOMEPAGE_ALLOWED_HOSTS`) instead of inheriting admin's through `baseApp`, including any field
   the admin gate adds. No NetworkPolicy: ADR 0008 holds, because a pod that drives household reaches only what every
   account already reaches.
6. **Enforcement.** `scripts/check-homepage-household.py`, a step in the Validate job of `validate-and-diff.yml`,
   renders the household chart and fails on 2, 3 and the placeholder and `integrations` rules in 4. It first checks
   that one bad snippet per rule fails. Credentials, `hideErrors` and the pod settings are config and review.

Applied to today's page: On TV and Music Playing go, and with them the Now Playing group. Immich and Karakeep keep their
link and status dot but lose their widgets. Calibre-Web moves to its household user. Seerr, Seerr RU and the calendar
stay as they are. `homepage-secrets` drops from 18 names to the six in the table, and `check-jellyfin-compat.py`
checks admin only.

## Rationale

- A Homepage release can add a route (a POST, a browser-chosen parameter) to any widget type, and the bump's diff shows
  only the new tag. An allowlist of reviewed native types would need each allowed type's routes re-read on every bump.
  Allowing only fixed-URL widgets (`customapi` and iCal) with a reviewed URL list avoids that, but gives up most of
  Homepage's widgets. A scoped credential bounds every route of every type, in this release and the next.
- The type denylist is not the boundary, since a denylist fails open. It keeps out only the three types no credential
  can scope.
- The URL rule keeps the pod's error output to in-cluster names, and keeps the pod off the LAN: the Proxmox host,
  OPNsense, TrueNAS, and ser2net, which drops its connected client when probed.
- CI checks only what no credential can contain and a reviewer can easily miss: a secret shipped to every browser, an
  open PromQL console, a fetch aimed at the LAN. Credentials stay with review, because Git can't show a credential's
  scope, and kubeseal encrypts every value differently, so a copied admin key looks like a new one.
- Anonymous activity ("3 streams now") would need a service of our own that holds admin keys and strips names and IPs,
  because the proxy passes the whole upstream body to the browser, whatever the tile shows. Aggregates need nothing
  extra.
- The guard is its own script and reads only the rendered ConfigMap, so it keeps working while
  `check-homepage-coverage.py` changes, and whether the dashboards are written by hand or generated.

## Consequences

- The boundary is only as good as each household credential's scope. Copying an admin-only key onto household still
  passes CI, as in #479. The table and review are the check.
- Seerr's native widget runs every route Homepage adds to it with the instance's global key, which acts as the original
  admin. When a Homepage release changes that widget, re-check its routes.
- Jellyfin makes every API key an Administrator, and the native Jellyfin widget keeps V1 routes that put the credential
  in the URL as `api_key`. Any viewer can call one, and on an HTTP error Homepage logs the full URL
  (`src/widgets/jellyfin/proxy.js`), which Alloy ships to Loki. A household Jellyfin widget therefore runs on a
  non-admin user's token, never an API key.
- A failure only household sees, such as a revoked household token, renders as a blank tile.
- The error JSON still reaches devtools, naming in-cluster hosts and IPs and quoting the upstream's error body.
- If search suggestions are turned on, each typed prefix lands in Traefik's access log, which keeps query strings, and
  SearXNG may pass it on to its autocomplete backend.
- Kubernetes annotation discovery can't serve household, because it needs the token and cluster mode.
- Navidrome's NetworkPolicy (ADR 0013) still admits household, for the Navidrome tile's status dot.
- Never set `LOG_LEVEL: debug` on household: the calendar then logs a failing feed's URL, key included.
- Removing household's copies of admin keys revokes nothing. Whether to rotate `JELLYFIN_KEY`, which the V1 log leak
  may have put in Loki, is an admin decision.
- Weather (`openmeteo`) and Homepage's built-in search providers send browser-chosen input to fixed public hosts, so
  any account can use the pod for those lookups.
- New household content adds its credentials, or a new reach for one already listed, to the table.
