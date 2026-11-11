# ADR 0016: Bind admin-only Authentik apps with a blueprint

- **Status:** Accepted
- **Date:** 2026-11-08

## Context

Authentik admits every account to an application that has no policy, group or user binding. A read on 2026-11-07 found
13 OAuth2 applications, the Jellyfin LDAP application and the MeTube and Navidrome proxy applications unbound. Several
are admin tools with no forward auth in front, so their own SSO login is the only gate: any account, invited media users
included, could sign in. Until now every Authentik application, provider and binding was created in the UI.

## Decision

Add an instantiated blueprint, `Application Access`, mounted from the `authentik-app-access-blueprint` ConfigMap
(`infrastructure/controllers/authentik/manifests/blueprints/app-access.yaml`). It binds the applications that are not
for everyone to the `authentik Admins` group: autobrr, bytestash, cleanuparr, filebrowser, grafana, listmonk,
paperless-ngx and vaultwarden. Applications and providers stay UI-managed.

From 2026-11-11 the applications meant for every account (jellyfin, navidrome, calibre-web-automated, shelfmark,
karakeep, excalidash, metube) are bound to the expression policy `Any account` (`return True`). Once a live read shows
no application without a binding, the tenant flag `core_default_app_access` ("Applications with no policies bound can
be accessed by any user") is switched off, and an unbound application denies everyone, LDAP binds included. The flag
isn't blueprint-managed (Authentik keeps tenants out of blueprints), so it is set by hand in the admin settings.

Two in-app settings go with it:

- MeTube stays open to every account, so `DELETE_FILE_ON_TRASHCAN` and `CREATE_CUSTOM_DIRS` are now `"false"`: the UI no
  longer deletes files from disk or creates folders.
- Vaultwarden sets `SSO_SIGNUPS_ALLOWED: "false"`. SSO sign-up is gated by this, not `SIGNUPS_ALLOWED`; invited users
  still link through SSO.

## Rationale

- `authentik Admins` is the group argo-cd's binding already uses.
- The branding, invitation and recovery blueprints already use the same pattern.
- Listmonk's subscriber pages (unsubscribe, preferences, opt-in, form, archive) need no login, so binding the admin
  login doesn't affect subscribers.
- Vaultwarden's master password still guards the vault, so SSO decides only who can sign in and create an account.

## Consequences

- The import is atomic: one unknown slug fails the whole blueprint, shows as an error on the `Application Access`
  blueprint instance, and changes nothing.
- Authentik applies the file only when it is created or changes, so a binding deleted in the UI stays deleted until the
  next change to the file. Once the flag is off, a lost binding fails closed: nobody gets in.
- Removing an entry from the file leaves its binding in place. Set the entry to `state: absent` and let it apply first.
- Adding the ConfigMap restarts the authentik worker; blueprints are mounted only there.
- Once the flag is off, a new application denies everyone until it gets a binding, here or in the UI. Bind
  `Any account` to open it.
- Jellyfin's `ldapservice` lookups go through the Jellyfin application's check, so they depend on its binding too.
- Only `authentik Admins` can use Vaultwarden's SSO login, and since 2026-11-11 it is the only login
  (`SSO_ONLY: "true"`; the one account was already SSO-linked). An invited user without an Admins account can't
  sign in.
- home-assistant admits `authentik Admins` and `home-assistant-users` (2026-11-11). The blueprint creates the group
  but leaves its members to the UI; Home Assistant's own local logins don't go through Authentik.
