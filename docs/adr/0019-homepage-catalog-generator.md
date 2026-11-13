# ADR 0019: Homepage catalog generator

- **Status:** Accepted
- **Date:** 2026-11-13

## Context

The household and admin dashboards (`services/operations/homepage{,-admin}`) are two hand-kept ConfigMaps that list
mostly the same apps. Every change goes in twice, and the copies drift: names, hrefs, monitors and widgets differ by
accident, and an app's host or port change reaches neither page. The new dashboards (sub-project 4) need one source
that can express both pages. Design: [docs/superpowers/specs/2026-11-13-homepage-one-source-design.md](../superpowers/specs/2026-11-13-homepage-one-source-design.md).

## Decision

Both pages are generated from one catalog by `scripts/homepage/generate.py` (stdlib plus pinned PyYAML; no Helm, no
cluster), and the generated ConfigMaps are committed.

1. **Catalog.** `homepage/catalog.yaml` holds `tiles` and `bookmarks` keyed by id (emitted as Homepage `id`), an
   ordered `info` list and `pages.{household,admin}` with tabs, groups and ordered `items`. Hand-written settings,
   CSS, `proxmox.yaml` and favicons are pass-through files in `homepage/pages/<page>/`.
2. **Audiences.** `household` shows on both pages, `admin` (the default) on admin only, and `household-only` on
   household only, for widgets, bookmarks and info but never tiles, so admin stays a superset of household's tiles.
   Nothing inherits an audience.
3. **Derivation.** `source: services/<area>/<app>` derives `href`, `siteMonitor` and, on admin, `namespace` and
   `app` from the app's `app.yaml`, mirroring the ingress chart. An explicit copy of a derived value fails.
4. **Generator-owned keys.** `hideErrors`, `layout`, `pwa.shortcuts`, `kubernetes.yaml`, `docker.yaml` and an empty
   `custom.js`; household never gets `namespace`, `app`, `podSelector` or `proxmox*`. Every placeholder must be a
   `{{HOMEPAGE_VAR_*}}` name, and the page's names must equal its sealed key names in both directions.
5. **Staged until cut-over.** Output goes to `homepage/staged/`, outside the AppSet globs, the diff gate and the watch
   pattern, so nothing deploys. Sub-project 4 cuts over one page per PR by removing it from `STAGED` and regenerating
   over today's ConfigMap.
6. **CI.** The Validate job runs the unit tests and `--check` (committed output is current), then a rehearsal that
   runs `--compare` (staged pages match the live ones) and the coverage, household and Jellyfin guards unmodified on
   a scratch tree with the staged pages copied in.

## Rationale

Ben's decisions (2026-11-13):

- The catalog is modelled for the new design, with no byte-identical step: today's pages are the proof content,
  which sub-project 4 replaces.
- Engine only: catalog format, generator, `--check`, the `--inventory` export, tests and this ADR. Sub-project 4
  owns content, visuals, a render check and the cut-over.
- One catalog file, not per-app blocks in `app.yaml`: tab and group order is a page property, and one file shows
  both pages side by side.
- A Python generator that writes committed ConfigMaps, not Helm templating: the output stays reviewable in Git and
  readable by the existing guards, and a run needs no cluster.

## Consequences

- **Double entry until cut-over.** While a page is staged, a change to its live ConfigMap must go into the catalog
  in the same PR; `--compare` fails CI otherwise, so the cut-over cannot silently revert a fix. Keep the window short.
- **The guards stay independent.** No guard imports the generator or is edited for it (ADR 0018); they run on the
  output. ADR 0018's URL and type rules and the host coverage rules are not duplicated in the generator.
- A PR that changes a sourced `app.yaml`'s host, domainType, port, serviceName, name or namespace, the
  `globals.yaml` domains, or a sealed key set must regenerate, or `--check` fails.
- `custom.js` stays empty; no catalog-only key (`audience`, `source`, `override`, `ref`, `monitorPath`) reaches
  the output.
- **Sub-project 4 may change** all catalog content (tabs, groups, nesting, ids, names, audiences, widgets,
  thresholds, refresh intervals), the pass-through files and images, the tile-key allowlist, the `--inventory`
  schema, and the cut-over order and timing. It deletes `--compare` in its first PR that changes content on purpose,
  and the rehearsal step after the last cut-over.
- **Sub-project 4 keeps**, unless Ben or a new ADR says otherwise: admin as a superset of household with no
  inherited audience; the generator-owned keys; the placeholder rules and the two-way sealed-name check; an empty
  `custom.js` and no catalog-only key in the output; ADR 0018's guard separate from the generator; and two
  instances with today's ConfigMap, Application and SealedSecret names (the NetworkPolicies select on instance
  labels).
- Homepage v2.7.0 behaviour the generator relies on (DOM `id`, tab slugs, nested layout, `service_group`) was read
  in the source, not run; a Homepage upgrade re-reads it.
- PyYAML is pinned in `scripts/homepage/requirements.txt`, because a dump-format change breaks `--check`.
