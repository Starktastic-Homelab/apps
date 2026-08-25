# Cleanuparr Authentik OIDC integration

Date: 2026-08-14
Status: Implemented (2026-08-25)

## Problem

Cleanuparr was deployed in PR #1051 and is reachable at
`cleanuparr.internal.starktastic.net`. It is currently protected only by the
Traefik `authentik-middleware` forward-auth middleware, applied because
`services/media/cleanuparr/app.yaml` sets `ingress.auth: true`.

That arrangement authenticates the request but tells Cleanuparr nothing. The
application still runs with its own local username/password account, and that
account remains a valid second way in. Cleanuparr supports OpenID Connect
natively, so the local account can be removed from the picture entirely and
Authentik can become the single source of identity — matching the pattern
already used by autobrr, vikunja, karakeep, shelfmark, mealie, paperless-ngx
and excalidash.

## Constraint that shapes the whole design

Cleanuparr's OIDC settings are **not configurable through the environment**.
`OidcConfig` is an Entity Framework `[ComplexType]` persisted in
`/config/users.db`, and the only environment variables Cleanuparr reads are
`PORT`, `BIND_ADDRESS`, `BASE_PATH`, `PUID`, `PGID`, `UMASK`, `TZ`, the
`POSTGRES_*` family and two non-Docker path overrides.

Two consequences follow:

- Unlike autobrr, **no SealedSecret is added to this repository**. The client
  secret is entered in the Cleanuparr UI and stored in its database.
- The repository change is a single line. The substance of the work is UI
  configuration in Authentik and Cleanuparr, so this spec records the exact
  values and the order they must be applied in.

## Goals

1. Authentik becomes the only way to authenticate to Cleanuparr.
2. The local username/password login is disabled.
3. Exactly one Authentik identity is authorised, because Cleanuparr has a
   single admin user and any identity that signs in becomes that admin.
4. No step in the rollout leaves the service either locked out or unprotected.

## Non-goals

- Declaring the Authentik provider as a blueprint. This repository manages only
  flows and branding declaratively
  (`infrastructure/controllers/authentik/manifests/blueprints/`); every
  application and provider is created in the Authentik UI. This change follows
  that existing convention rather than introducing a new one.
- Migrating Cleanuparr from SQLite to PostgreSQL.

## Design

### Repository change

```yaml
# services/media/cleanuparr/app.yaml
auth: false # was: true
```

Dropping `ingress.auth` removes the `authentik-middleware` reference from the
generated IngressRoute, leaving `rate-limit-strong` in place. The resulting
`app.yaml` matches the shape of `services/media/autobrr/app.yaml`.

No `manifests: true` key is added, because there is no secret to seal.

There is no monitoring impact. `templates/ingress-chart/templates/probe.yaml`
selects the `http_auth` or `http_2xx` blackbox module based on `ingress.auth`,
but it only renders a `Probe` when `ingress.probe` is set, and Cleanuparr does
not set it.

### Authentik

Create an OAuth2/OpenID provider and its application with slug `cleanuparr`,
as a **confidential** client. Register both redirect URIs; Cleanuparr uses a
separate callback for account linking, and Authentik matches these strictly:

```
https://cleanuparr.internal.starktastic.net/api/auth/oidc/callback
https://cleanuparr.internal.starktastic.net/api/account/oidc/link/callback
```

### Cleanuparr

Settings → Account → OIDC Settings:

| Field         | Value                                                  |
| ------------- | ------------------------------------------------------ |
| Enable OIDC   | on                                                     |
| Provider Name | `Authentik`                                            |
| Issuer URL    | `https://auth.starktastic.net/application/o/cleanuparr/` |
| Client ID     | from Authentik                                         |
| Client Secret | from Authentik                                         |
| Scopes        | `openid profile email`                                 |
| Redirect URL  | `https://cleanuparr.internal.starktastic.net`           |

`Redirect URL` is the base URL only; Cleanuparr appends the callback paths
itself. It is set explicitly rather than left to auto-detection because
Cleanuparr sits behind Traefik.

### Rollout order

The order matters more than any individual setting, because two of the steps
can strand the operator. Forward-auth is kept until OIDC is proven, and
passwords are disabled only after OIDC has been proven without forward-auth in
the request path.

1. Create the Authentik provider and application. Nothing changes for
   Cleanuparr yet; forward-auth is still guarding it.
2. Enter the OIDC settings in Cleanuparr and use **Link Account** to bind the
   single authorised identity. Cleanuparr is still reached through
   forward-auth at this point, so an existing Authentik session covers the
   callback.
3. Merge the `auth: false` change and let Argo CD sync it.
4. Verify OIDC login end to end in a fresh private window.
5. Only now enable **Exclusive Mode**, which disables username/password and
   Plex login.

Step 5 is last because it is the only step that cannot be undone from the
Cleanuparr UI once it goes wrong.

Step 2's **Link Account** is load-bearing, not tidiness. `OidcConfig.Validate()`
only checks that `Enabled` is set before allowing `ExclusiveMode`, despite the
upstream doc comment claiming exclusive mode "requires OIDC to be fully
configured with an authorized subject". With an empty `AuthorizedSubject`,
Cleanuparr accepts *any* Authentik identity that can reach the application and
signs it in as the admin. Enabling Exclusive Mode before linking therefore
widens access rather than narrowing it.

### Rollback

Either of these restores access:

- Revert `auth: false` in `app.yaml`, restoring forward-auth. Note this alone
  does **not** cure an Exclusive Mode lockout: forward-auth authenticates the
  request to Traefik, not the user to Cleanuparr.
- Clear Exclusive Mode. `AuthController.Login` rejects credential logins with
  HTTP 403 only while `oidc_exclusive_mode` is set, so clearing it re-enables
  the local password.

**Preferred: clear it over the API.** API-key authentication is independent of
Exclusive Mode, so no database access is needed. Verified 2026-08-25: with
Exclusive Mode on, password login returned `403` while `X-Api-Key` requests
still returned `200`. `PUT /api/account/oidc` with the current object and
`exclusiveMode: false` is sufficient; the masked client secret (`••••••••`) is
preserved server-side by `OidcConfig.IsPlaceholder()`. See the plan's Rollback
section for the exact command.

Only if the API key is also lost is a database edit required. The Cleanuparr
image does not ship `sqlite3`, so that needs a rescue pod. The `cleanuparr` PVC
is `RWX`, but the deployment is still scaled down first so nothing writes to the
SQLite WAL concurrently:

```bash
kubectl -n media scale deploy/cleanuparr --replicas=0

kubectl -n media run cleanuparr-rescue --rm -it --restart=Never \
  --image=alpine:3.20 \
  --overrides='{"spec":{"containers":[{"name":"cleanuparr-rescue","image":"alpine:3.20","stdin":true,"tty":true,"command":["sh"],"volumeMounts":[{"name":"config","mountPath":"/config"}]}],"volumes":[{"name":"config","persistentVolumeClaim":{"claimName":"cleanuparr"}}]}}'

# inside the rescue pod:
apk add --no-cache sqlite
sqlite3 /config/users.db "UPDATE users SET oidc_exclusive_mode = 0;"
exit

kubectl -n media scale deploy/cleanuparr --replicas=1
```

The relevant columns on the `users` table are `oidc_enabled`,
`oidc_exclusive_mode`, `oidc_issuer_url`, `oidc_client_id`,
`oidc_client_secret`, `oidc_scopes`, `oidc_provider_name`,
`oidc_redirect_url` and `oidc_authorized_subject`.

### Rejected: local address auth bypass

Cleanuparr's `GeneralConfig.Auth.DisableAuthForLocalAddresses` combined with
`TrustedNetworks` is its built-in break-glass, and it is deliberately left
off. With `ingress.auth: false` there would be no forward-auth in front of it,
so enabling it would leave Cleanuparr fully unauthenticated to any client on a
trusted network. The database rollback above provides the same escape hatch
without the standing exposure.

## Verification

1. `https://cleanuparr.internal.starktastic.net` presents Cleanuparr's own
   login screen, not an Authentik forward-auth redirect.
2. The login screen offers a "Sign in with Authentik" button.
3. Signing in with the linked identity succeeds.
4. After Exclusive Mode is enabled, `POST /api/auth/login` returns HTTP 403.
5. `kubectl -n media get ingressroute cleanuparr -o yaml` lists only the
   `rate-limit-strong` middleware.
