# ADR 0015: Reserve app-local usernames in the invitation flow

- **Status:** Accepted
- **Date:** 2026-11-08

## Context

Invitees choose their own Authentik username in the invitation flow. "Invite - Unique Username" checks only Authentik's
users, so a name can be free in Authentik and still belong to an account inside an app. Three apps link an SSO login to
an existing local account with the same username: Calibre-Web-Automated v4.0.8 (exact match), Navidrome 0.64.2 (ignoring
case) and Shelfmark v1.6.1 (accounts linked to OIDC). An invitee who signs up with such a name inherits that account.
CWA ships two local accounts of its own, `admin` and `Guest` (anonymous browsing). Deleting an Authentik user frees
their name too, while their app accounts stay behind. CWA's fallback match by email is not a route: invitees activate
only through a link mailed to their address.

## Decision

- "Invite - Valid Username" (`infrastructure/controllers/authentik/manifests/blueprints/invitation-flow.yaml`) rejects a
  reserved set, compared lowercased, with "This username is reserved.": `admin`, `administrator`, `akadmin`, `guest` and
  `root`. A one-time account review adds, in lowercase, any app-local account name that isn't an Authentik username and
  can't be renamed or removed. Since 2026-11-14 the set also holds `homepage-household`, the household dashboard's
  local user in Calibre-Web and Jellyfin (ADR 0018).
- App-local accounts in those apps carry their owner's Authentik username, or their name is on the reserved set.
- Authentik users are deactivated, not deleted. The uniqueness check (`ak_user_by`) counts inactive users, so the name
  stays taken.

## Rationale

- One expression policy in a blueprint that Git already manages: no app settings, flows or stages change.
- Linking by Authentik's stable user ID instead (CWA's `username_mapper`, Navidrome's user header) would give new app
  accounts opaque names and stop existing ones matching.
- Authentik can't see the apps' user tables, so a one-time account review covers the names already there.

## Consequences

- A local account made outside SSO (an app's setup admin, a service account) needs a matching Authentik user or a
  reserved-set entry.
- Deleting an Authentik user anyway means deleting their app accounts or reserving the name. The brand keeps no
  unenrollment flow, which would let users delete themselves.
- The check runs at sign-up only. "Allow users to change username" and "Allow users to change email" (System →
  Settings) stay off, and no brand, group or user attribute sets `goauthentik.io/user/can-change-username` or
  `goauthentik.io/user/can-change-email` to true. Otherwise users could rename into a reserved name, or change their
  email to take over an account that an app links by email (CWA's fallback, pgAdmin, Karakeep).
- Authentik applies the edit when blueprint discovery sees the changed file, after ArgoCD syncs `authentik`.
