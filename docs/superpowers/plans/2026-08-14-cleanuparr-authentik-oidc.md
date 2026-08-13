# Cleanuparr Authentik OIDC Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Authentik the only way to authenticate to Cleanuparr, replacing the Traefik forward-auth middleware with Cleanuparr's native OIDC client.

**Architecture:** Cleanuparr stores its OIDC settings in `/config/users.db`, not in environment variables, so this is one line of YAML plus configuration entered in two web UIs. The rollout order is the load-bearing part: forward-auth stays up until OIDC is proven, and password login is disabled only after OIDC has been proven with forward-auth already removed.

**Tech Stack:** Kubernetes (k3s), Argo CD, Traefik IngressRoute, bjw-s app-template, Authentik, Cleanuparr 2.10.5, SQLite.

## Global Constraints

- Cleanuparr host: `https://cleanuparr.internal.starktastic.net`
- Authentik host: `https://auth.starktastic.net`
- Authentik application slug: `cleanuparr` (the issuer URL derives from this — do not vary it)
- Issuer URL: `https://auth.starktastic.net/application/o/cleanuparr/`
- Scopes: `openid profile email`
- Client type: **confidential**
- Branch: `MrStarktastic/cleanuparr-authentik-oidc` (already exists, already holds the spec commit)
- `DisableAuthForLocalAddresses` stays **off** — see the spec's "Rejected" section
- Tasks 1, 2 and 4 are performed by a human in a browser. The agent cannot click these UIs. The agent's job in those tasks is to run the verification commands and confirm the observable result before the next task starts.

## File Structure

Only one repository file changes:

- `services/media/cleanuparr/app.yaml` — flip `ingress.auth` from `true` to `false`, removing the `authentik-middleware` reference from the generated IngressRoute.

Everything else is state held outside the repository: the Authentik provider/application objects, and the `users` table in Cleanuparr's `/config/users.db`.

---

### Task 1: Create the Authentik provider and application

**Files:**

- No repository files. This task creates objects in Authentik's UI at `https://auth.starktastic.net`.

**Interfaces:**

- Consumes: nothing.
- Produces: a Client ID and Client Secret consumed by Task 2, and a discovery document at `https://auth.starktastic.net/application/o/cleanuparr/.well-known/openid-configuration`.

- [ ] **Step 1: Confirm the issuer does not resolve yet**

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  https://auth.starktastic.net/application/o/cleanuparr/.well-known/openid-configuration
```

Expected: `404`. Anything else means an application with slug `cleanuparr` already exists — stop and inspect it before creating a duplicate.

- [ ] **Step 2: Create the OAuth2/OpenID provider**

In Authentik: **Applications → Providers → Create → OAuth2/OpenID Provider**.

| Setting            | Value                                                                                                                                |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------ |
| Name               | `cleanuparr`                                                                                                                         |
| Authorization flow | `default-provider-authorization-implicit-consent` (Authentik's built-in), or the same flow the other applications here use |
| Client type        | `Confidential`                                                                                                                       |
| Redirect URIs      | `https://cleanuparr.internal.starktastic.net/api/auth/oidc/callback`<br/>`https://cleanuparr.internal.starktastic.net/api/account/oidc/link/callback` |
| Scopes             | `openid`, `profile`, `email`                                                                                                         |

Both redirect URIs are required. Cleanuparr uses a separate callback for account linking (`GET /api/account/oidc/link/callback`), and Authentik matches redirect URIs strictly — omitting the second one makes Task 2 Step 5 fail.

- [ ] **Step 3: Create the application**

In Authentik: **Applications → Applications → Create**.

| Setting  | Value        |
| -------- | ------------ |
| Name     | `Cleanuparr` |
| Slug     | `cleanuparr` |
| Provider | `cleanuparr` |

The slug must be exactly `cleanuparr` — the issuer URL in Task 2 is derived from it.

- [ ] **Step 4: Verify the discovery document**

```bash
curl -s https://auth.starktastic.net/application/o/cleanuparr/.well-known/openid-configuration \
  | jq '{issuer, authorization_endpoint, token_endpoint}'
```

Expected: `issuer` is exactly `https://auth.starktastic.net/application/o/cleanuparr/`, and both endpoints are populated. If `issuer` differs from that string by even a trailing slash, use the returned value in Task 2 instead — Cleanuparr validates the issuer against the discovery document.

- [ ] **Step 5: Record the credentials**

Copy the Client ID and Client Secret from **Providers → cleanuparr**. These go into Task 2.

Do not commit them. They belong in Cleanuparr's database, not this repository.

---

### Task 2: Configure OIDC in Cleanuparr and link the account

**Files:**

- No repository files. This task writes to `/config/users.db` via the Cleanuparr UI at `https://cleanuparr.internal.starktastic.net`.

**Interfaces:**

- Consumes: the Client ID and Client Secret from Task 1.
- Produces: `oidc_enabled = 1` and a non-empty `oidc_authorized_subject` in the `users` table, both asserted by Task 3 and Task 4.

Cleanuparr is still behind forward-auth for this entire task, so reaching it requires an Authentik session. That is intentional — it is the safety net while OIDC is unproven.

- [ ] **Step 1: Confirm OIDC is currently off**

```bash
kubectl -n media port-forward svc/cleanuparr 11011:11011 >/dev/null 2>&1 &
echo $! > /tmp/cleanuparr-pf.pid
sleep 3
curl -s http://localhost:11011/api/auth/status | jq
```

Expected: `"OidcEnabled": false` and `"OidcExclusiveMode": false`.

Port-forwarding is required because the ingress still has forward-auth in front of it. `GET /api/auth/status` is `[AllowAnonymous]`, so no credentials are needed.

Leave the port-forward running; Step 4 reuses it.

- [ ] **Step 2: Enter the OIDC settings**

In Cleanuparr: **Settings → Account → OIDC Settings**.

| Field         | Value                                                    |
| ------------- | -------------------------------------------------------- |
| Enable OIDC   | on                                                       |
| Provider Name | `Authentik`                                              |
| Issuer URL    | `https://auth.starktastic.net/application/o/cleanuparr/` |
| Client ID     | from Task 1 Step 5                                       |
| Client Secret | from Task 1 Step 5                                       |
| Scopes        | `openid profile email`                                   |
| Redirect URL  | `https://cleanuparr.internal.starktastic.net`            |

Leave **Exclusive Mode** off. It is enabled in Task 4, after OIDC is proven.

`Redirect URL` is the base URL only — Cleanuparr appends `/api/auth/oidc/callback` itself. It is set explicitly rather than auto-detected because Cleanuparr sits behind Traefik and would otherwise infer the URL from proxied request headers.

- [ ] **Step 3: Save**

Click **Save OIDC Settings**.

Expected: a success message. A validation error here means `OidcConfig.Validate()` rejected the input — it requires a non-empty Issuer URL, a non-empty Client ID, a non-empty Provider Name, and an Issuer URL that is absolute and HTTPS.

- [ ] **Step 4: Verify the settings persisted**

```bash
curl -s http://localhost:11011/api/auth/status | jq
```

Expected: `"OidcEnabled": true` and `"OidcProviderName": "Authentik"`.

`AuthController.Status` only reports `OidcEnabled: true` when `Enabled` is set **and** `IssuerUrl` and `ClientId` are both non-empty, so this single assertion covers all three.

- [ ] **Step 5: Link the account**

Click **Link Account**, sign in with Authentik when prompted, and confirm the redirect back to Cleanuparr reports success.

This writes `oidc_authorized_subject`. Until it is set, any Authentik identity permitted on the application could sign in as the Cleanuparr admin.

- [ ] **Step 6: Stop the port-forward**

```bash
kill "$(cat /tmp/cleanuparr-pf.pid)" && rm -f /tmp/cleanuparr-pf.pid
```

---

### Task 3: Remove the forward-auth middleware

**Files:**

- Modify: `services/media/cleanuparr/app.yaml:10`

**Interfaces:**

- Consumes: a working OIDC configuration from Task 2.
- Produces: an IngressRoute whose only middleware is `rate-limit-strong`, asserted in Step 6.

- [ ] **Step 1: Confirm the middleware is currently applied**

```bash
kubectl -n media get ingressroute cleanuparr \
  -o jsonpath='{.spec.routes[0].middlewares}' | jq
```

Expected: two entries — `rate-limit-strong` in `traefik-system` and `authentik-middleware` in `authentik`.

- [ ] **Step 2: Make the change**

```bash
cd /home/ben/Developer/homelab/apps
git checkout MrStarktastic/cleanuparr-authentik-oidc
```

In `services/media/cleanuparr/app.yaml`, change:

```yaml
auth: true
```

to:

```yaml
auth: false
```

The resulting file:

```yaml
name: cleanuparr
namespace: media
deployPhase: services

ingress:
  enabled: true
  host: cleanuparr
  domainType: "internal"
  port: 11011
  auth: false
  rateLimit: true
```

- [ ] **Step 3: Verify the rendered manifest drops the middleware**

```bash
cd /home/ben/Developer/homelab/apps
helm template cleanuparr templates/ingress-chart \
  -f services/media/cleanuparr/app.yaml \
  -f globals.yaml \
  | grep -A6 'middlewares:'
```

Expected: only `rate-limit-strong` appears. `authentik-middleware` must be absent.

If `helm template` errors on missing values, skip this step — Step 6 asserts the same property against the live cluster, which is the assertion that actually matters.

- [ ] **Step 4: Run the repository checks**

```bash
cd /home/ben/Developer/homelab/apps
pre-commit run --files services/media/cleanuparr/app.yaml
python3 scripts/check-homepage-coverage.py
```

Expected: all hooks pass, and the coverage script reports OK. Cleanuparr already has a homepage-admin entry from PR #1051, so coverage should be unchanged.

- [ ] **Step 5: Commit and open the PR**

```bash
cd /home/ben/Developer/homelab/apps
git add services/media/cleanuparr/app.yaml
git commit -m "feat(cleanuparr): authenticate via Authentik OIDC instead of forward-auth

Cleanuparr now holds its own OIDC client configuration, so the Traefik
authentik-middleware is redundant and would force a second sign-in. This
matches autobrr, vikunja, karakeep and shelfmark, which all set auth: false
alongside native OIDC.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
git push -u origin MrStarktastic/cleanuparr-authentik-oidc
gh pr create --fill
```

Then wait for CI and merge:

```bash
gh pr checks --watch
gh pr merge --squash
```

- [ ] **Step 6: Verify the live IngressRoute after Argo CD syncs**

```bash
kubectl -n media get ingressroute cleanuparr \
  -o jsonpath='{.spec.routes[0].middlewares}' | jq
```

Expected: exactly one entry, `rate-limit-strong` in `traefik-system`.

If it still shows two, Argo CD has not synced yet. Check with:

```bash
kubectl -n argocd get application cleanuparr \
  -o jsonpath='{.status.sync.status}{"\n"}'
```

- [ ] **Step 7: Verify OIDC login end to end**

Open `https://cleanuparr.internal.starktastic.net` in a **fresh private window**.

Expected, in order:

1. Cleanuparr's own login screen appears — not an Authentik forward-auth redirect.
2. A **Sign in with Authentik** button is present.
3. Clicking it, authenticating, and being returned lands you logged in.

A private window matters: an existing Authentik forward-auth cookie would mask a failure here.

Do not proceed to Task 4 until this passes. Task 4 removes the password fallback.

---

### Task 4: Enable Exclusive Mode

**Files:**

- No repository files. This task sets `oidc_exclusive_mode` in `/config/users.db` via the Cleanuparr UI.

**Interfaces:**

- Consumes: a verified end-to-end OIDC login from Task 3 Step 7.
- Produces: `POST /api/auth/login` returning HTTP 403.

This is the only step that cannot be undone from the Cleanuparr UI if it goes wrong. Step 1 is the gate.

- [ ] **Step 1: Confirm the prerequisite**

Confirm Task 3 Step 7 passed in a fresh private window. If it did not, stop.

- [ ] **Step 2: Enable Exclusive Mode**

In Cleanuparr: **Settings → Account → OIDC Settings → Exclusive Mode**, then save.

- [ ] **Step 3: Verify the status endpoint reports it**

```bash
curl -s https://cleanuparr.internal.starktastic.net/api/auth/status | jq
```

Expected: `"OidcEnabled": true`, `"OidcExclusiveMode": true`, `"AuthBypassActive": false`.

No port-forward is needed now — forward-auth is gone and `GET /api/auth/status` is `[AllowAnonymous]`.

`AuthBypassActive: false` confirms `DisableAuthForLocalAddresses` was left off, as the spec requires.

- [ ] **Step 4: Verify password login is actually refused**

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  -X POST https://cleanuparr.internal.starktastic.net/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"wrong"}'
```

Expected: `403`.

`403` proves the Exclusive Mode branch in `AuthController.Login` fired. A `401` would mean the request reached normal credential checking and Exclusive Mode is **not** active — in that case re-check Step 2.

- [ ] **Step 5: Confirm OIDC login still works**

Sign in once more from a fresh private window.

This is the last point at which the recovery procedure is cheap. If login fails here, use the rescue-pod rollback in the spec to clear `oidc_exclusive_mode`.

- [ ] **Step 6: Update the spec status**

```bash
cd /home/ben/Developer/homelab/apps
git checkout main && git pull
```

In `docs/superpowers/specs/2026-08-14-cleanuparr-authentik-oidc-design.md`, change:

```markdown
Status: Approved, not yet implemented
```

to:

```markdown
Status: Implemented
```

Then:

```bash
git add docs/superpowers/specs/2026-08-14-cleanuparr-authentik-oidc-design.md
git commit -m "docs(cleanuparr): mark Authentik OIDC design implemented

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
git push
```

---

## Rollback

If Exclusive Mode locks you out, reverting `auth: false` does **not** help — forward-auth authenticates the request to Traefik, not the user to Cleanuparr. Clear the flag in the database instead. The Cleanuparr image has no `sqlite3`, so this needs a rescue pod:

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

The deployment is scaled to zero first so nothing writes to the SQLite WAL while the rescue pod holds the file, even though the `cleanuparr` PVC is `RWX` and would permit a concurrent mount.
