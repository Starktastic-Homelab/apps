# Homepage one source: catalog and generator (sub-project 3)

Status: design approved by Ben in sections on 2026-11-13; this file awaits his review.
Facts are cited at `origin/main` `44ca29a1`. H and A mean the household and admin
`services/operations/homepage{,-admin}/manifests/templates/configmap.yaml`.

## Outcome

Both Homepage pages are generated from one hand-written catalog by a Python script,
and CI proves the generated output is committed and current. Sub-project 3 builds the
engine only and proves it on today's 91 tile placements; nothing it writes is deployed.
Sub-project 4 (new dashboards) is handed to a Fable 5.2 session, which re-evaluates it,
then owns the content, the visuals, a render check and the cut-over.

Ben's decisions (2026-11-13):

- The catalog is modelled for the new design. There is no byte-identical step.
- Engine only: catalog format, generator, `--check`, the inventory export, tests and an ADR.
- One catalog file, not per-app blocks in `app.yaml`.
- A Python generator that writes committed ConfigMaps.

Out of scope: any change to what either live page shows, the `values.yaml` mounts, the
guards, the SealedSecrets, and the household credential split (household PR 2, Task 5).

## 1 Catalog format

`homepage/catalog.yaml` has four top-level keys:

- `tiles` and `bookmarks`: mappings keyed by id. The id is the same on both pages and is
  emitted as Homepage `id`, so CSS hooks key on it.
- `info`: an ordered list of info widgets.
- `pages.household` and `pages.admin`: `tabs[]`, each with `groups[]`. A group has a
  `name`, Homepage group layout keys (`style`, `columns`, `icon`, ...) and one ordered
  `items:` list. An `items` entry is either an id string or a subgroup: a mapping with
  `name`, the layout keys and its own `items`. A group holds tiles or bookmarks, never both.

**Audience.**

- `household`: the entry appears on both pages.
- `admin`: the default; the entry appears on admin only.
- `household-only`: allowed on widgets, bookmarks and info entries, not on tiles, so admin
  stays a superset of household's tiles.
- Nothing inherits an audience: a household tile's widgets are admin unless marked.

**Derivation.** `source: services/<area>/<app>` derives `href`, `siteMonitor` and, on
admin, `namespace` and `app` (§2 rule 3). `monitorPath` appends to the derived
`siteMonitor`.

**Per-page differences.** `override.<page>` sets any emitted tile key except `id`,
`audience` and `widgets`. It is applied before rules 6, 8 and 10.

**Widgets.** One `widgets:` list per tile; each entry may carry an `audience`. Calendar
integrations name a tile with `ref:`; the generator fills `type`, `service_group` and
`service_name` for that page.

**Emitted keys.** `audience`, `source`, `override`, `ref` and `monitorPath` are never
emitted. Every other tile key must be on an allowlist (`name, href, icon, description,
siteMonitor, namespace, app, podSelector, proxmoxNode, proxmoxVMID`, plus `id`) and is
emitted verbatim.

**Style.** Block style only: Prettier rewrites flow mappings to `{ a: b }`, which
yamllint's `braces` rule rejects. YAML anchors are allowed and are expanded on load;
`highlight` and `refreshInterval` are plain widget keys, so shared alarm thresholds are
anchors.

```yaml
tiles:
  calibre-web:
    name: Calibre-Web
    audience: household
    source: services/media/calibre-web
    monitorPath: /opds
    icon: calibre-web.png
    description: E-book library
    widgets:
      - audience: household-only
        type: calibreweb
        url: http://calibre-web.media:8083
        username: "{{HOMEPAGE_VAR_CALIBRE_USER}}"   # becomes _HOUSEHOLD in Task 5
        password: "{{HOMEPAGE_VAR_CALIBRE_PASS}}"
      - type: calibreweb
        url: http://calibre-web.media:8083
        username: "{{HOMEPAGE_VAR_CALIBRE_USER}}"
        password: "{{HOMEPAGE_VAR_CALIBRE_PASS}}"
  calendar:
    name: Calendar
    audience: household
    description: TV blue · Movies red · Music green · RU lighter
    override:
      household:
        description: Blue = TV · Red = Movies
    widgets:
      - audience: household-only
        type: calendar
        view: monthly
        integrations:
          - type: ical
            name: TV
            color: blue
            url: "http://sonarr.media:8989/feed/v3/calendar/Sonarr.ics?apikey={{HOMEPAGE_VAR_SONARR_KEY}}"
      - type: calendar
        view: monthly
        integrations:
          - ref: sonarr
            color: blue
bookmarks:
  my-account:
    name: My Account
    audience: household-only
    abbr: AC
    href: https://auth.starktastic.net
info:
  - audience: household-only
    greeting:
      text: Welcome home
pages:
  household:
    tabs:
      - name: Pulse
        groups:
          - name: Coming Up
            style: row
            columns: 1
            items:
              - calendar
```

**Pass-through files** (hand-written, not catalog-owned), in `homepage/pages/<page>/`:

- `settings.yaml` (visual settings) and, on admin, `proxmox.yaml`. Both are parsed and
  re-dumped, so the Format bot's reformatting cannot break `--check`; their comments are
  dropped.
- `custom.css`, copied verbatim.
- `files/*`, each copied verbatim into a ConfigMap key of the same name (today: the
  favicon, H:7 and A:12). The `values.yaml` subPath mounts stay hand-written.

There is no `custom.js` input; the generator always emits it empty.

**Open question, not built:** household-only tiles (for example the poster launcher
tiles a new design might want). If chosen, the narrowest change is to check the
admin superset by `source`/`href` instead of by tile id.

## 2 Generator

`scripts/homepage/generate.py`, stdlib plus pinned PyYAML. No Helm, no cluster.

**Load**

1. A duplicate-key loader rejects repeated keys (the pattern at
   `check-homepage-coverage.py:51-68`).
2. Unquoted `yes`, `no`, `on` and `off` fail, checked at compose level. PyYAML reads them
   as booleans where Homepage's js-yaml keeps strings, and yamllint has `truthy: disable`.

**Derive from `source`**

3. Host logic mirrors the ingress chart (`cluster-apps.yaml:177-188`,
   `templates/ingress-chart/values.yaml:6-14`: `domainType` defaults to `internal`, `port` to
   80, `serviceName` to `name`). It is reimplemented, not imported from coverage
   (`check-homepage-coverage.py:85-109`, which raises where the chart defaults), so coverage
   stays an independent check. A variant app with `baseApp`
   (the `-ru` apps) deep-merges the base `ingress` under its own, as the ingress chart
   does; `serviceName|name` comes from the merged result and `name` from the variant.
   - `href = https://<fqdn>`, with the domain from `templates/globals.yaml`.
   - `siteMonitor = http://<ingress.serviceName|name>.<namespace>:<ingress.port><monitorPath>`.
   - Admin only: `namespace` = app.yaml `namespace`, `app` = app.yaml `name` (the variant's).
4. An explicit value wins, and `null` drops the key. An explicit value equal to the
   derived one fails, so stale copies cannot hide later `app.yaml` changes. `source` on an
   app without `ingress.enabled` fails.

**Place and emit**

5. Every tile and every `admin` or `household` bookmark is placed exactly once on admin.
   Every `household` or `household-only` entry is placed exactly once on household. An
   `admin` entry on household fails, and a `household-only` entry on admin fails.
6. Names (after `override`) and tab slugs are unique per page, and every referenced id
   exists. A tab slug is Homepage v2.7.0's `encodeURIComponent(name.replace(/\s+/g, "-")
   .toLowerCase())` (`src/components/tab.jsx:6-12`); today's tabs give `pulse`, `play`,
   `make`, `run` and `iron`. Tab names must match `[A-Za-z0-9 ]+`, because the page compares
   the raw hash. Group names are unique per page, since calendar lookups search all levels.
7. Per page, the matching widgets decide the key: one gives `widget:`, several give
   `widgets:`, none gives no key, never both.
8. A calendar `ref` becomes `type`, `service_group` (the tile's immediate group) and
   `service_name` on that page. `type` is the type of the target tile's single widget on
   that page; zero or several fail (Homepage returns `widgets[<calendar index>]` for a list,
   `service-helpers.js:806`). The target must be placed on that page, on any tab.
   `integrations` must be a list.
9. Every group goes into `settings.layout` in order, with its `tab`, so no group can render
   on every tab. Subgroups nest under their parent and carry no `tab`. No layout value is
   ever `null` (Homepage treats any object, `null` included, as a subgroup). No tile key
   `weight` exists, so YAML order is display order (`api-response.js:18-24`).
   `pwa.shortcuts` is generated as one `{name, url: "/#<slug>"}` per tab and merged into
   the pass-through `pwa` block.
10. Each `data-name="X"` in a page's CSS must name a tile on that page (H:32,37,86 and
    A:37,42,101, all `Calendar`).

**Generator-owned** (setting them in pass-through fails):

11. `hideErrors`: `true` on household (H:132), `false` on admin (A:146).
12. `layout` and `pwa.shortcuts`.
13. `kubernetes.yaml`: `mode: disabled` on household (H:121), `mode: cluster` on admin (A:136).
14. `docker.yaml: ""` and `custom.js: ""`.
15. Household never gets `namespace`, `app`, `podSelector` or `proxmox*`: the generator emits
    these keys, derived or explicit, on admin only. Today's household page has none; the
    household page has no Kubernetes or Proxmox access.

**Placeholders and secrets**, checked over the whole rendered page, pass-through included:

16. Checked on the unescaped render, before rule 19: every `{{`...`}}` must be exactly
    `{{HOMEPAGE_VAR_[A-Z0-9_]+}}`, and a lone `{{` or `}}` fails. Single braces (CSS, the
    customapi `{number}` at A:1039,1051,1063,1075) are not checked.
17. The referenced names equal the page's `secrets.yaml` `encryptedData` key names, in both
    directions (today 6 and 38; coverage's `check_secrets` at `:218-234` checks one direction). Names only.
    `FINNHUB_KEY` appears only in admin `settings.yaml`; `PROXMOX_USER` and `PROXMOX_PASS`
    appear in `proxmox.yaml` and in the Proxmox VE tile (A:10-11, A:1085-1086).

**Output**

18. `safe_dump(sort_keys=False, allow_unicode=True, width=inf)` with aliases off, inside a
    fixed ConfigMap wrapper (`homepage-config` or `homepage-admin-config`, namespace
    `operations`), `|` blocks, and a generated-file header naming the command.
19. One regex pass Helm-escapes the braces into today's form (H:250).

**Flags**

- `--check`: render in memory and byte-compare with the committed files. On failure,
  print a short diff and the command to run.
- `--inventory`: JSON to stdout, per page: tabs and slugs, groups, tiles (id, name, group,
  href, widget types, fetch URLs, `highlight`, `refreshInterval`), bookmarks, info.
- `--compare`: temporary, see §5.

ADR 0018's URL and type rules and the host coverage rules stay in the guards, which run on
the output; the generator does not duplicate them.

## 3 Paths

| What | Path |
|---|---|
| Catalog | `homepage/catalog.yaml` |
| Pass-through | `homepage/pages/{household,admin}/{settings.yaml,custom.css,proxmox.yaml,files/}` |
| Generator | `scripts/homepage/generate.py` |
| Tests | `scripts/homepage/tests/` (unittest, like `scripts/storage/tests`) |
| PyYAML pin | `scripts/homepage/requirements.txt` |
| Staged output | `homepage/staged/services/operations/homepage{,-admin}/manifests/templates/configmap.yaml` |
| Output after cut-over | today's `services/operations/homepage{,-admin}/manifests/templates/configmap.yaml` |

**Staging is inert.**

- It sits outside the AppSet globs (`cluster-apps.yaml:21-30`): no Application, sync or
  prune. `homepage/` must never get an `app.yaml`.
- It matches neither the diff gate (`:11`) nor the watch pattern (`:79`), so the preview
  stays empty and the `MAX_DIFF_LENGTH=65536` cap (`validate-and-diff.yml:265`) is
  untouched. `refresh.yaml:123` ignores it.
- kubeconform excludes `*/manifests/templates/*` (`validate-and-diff.yml:53-56`); yamllint
  and Prettier skip `templates/`. The catalog and pass-through YAML do get yamllint and the
  Format bot (`format.yaml:25`), which is harmless because output depends on parsed data.

**Cut-over** (sub-project 4, one page per PR): remove the page from the generator constant
`STAGED = {"household", "admin"}`, regenerate over the hand-written file, and delete the
staged copy. The ConfigMap name, namespace and Application are unchanged, so Argo updates in
place with no prune; Reloader restarts the pod. The household guard keeps reading
`homepage/manifests` and `homepage-config` (`check-homepage-household.py:27-28`).

## 4 CI

Two plain `run:` steps in the required Validate job, after "Check Jellyfin compatibility"
(`validate-and-diff.yml:81-82`), like the neighbouring guards:

```yaml
- name: Check generated Homepage pages
  run: |
    pip install -r scripts/homepage/requirements.txt
    python3 -m unittest discover -s scripts/homepage/tests -v
    python3 scripts/homepage/generate.py --check
- name: Rehearse staged Homepage pages   # Fable deletes this at the cut-over
  run: |
    python3 scripts/homepage/generate.py --compare
    cp -a . "$RUNNER_TEMP/hp" && cp -r homepage/staged/services "$RUNNER_TEMP/hp/"
    cd "$RUNNER_TEMP/hp"
    python3 scripts/check-homepage-coverage.py
    python3 scripts/check-homepage-household.py
    python3 scripts/check-jellyfin-compat.py
```

- `check-admin-gate.py` is left out of the rehearsal: it reads no ConfigMap content, and
  the generator writes none of its inputs.
- PyYAML is pinned because the workflow's install (`:67`) is unpinned and a dump-format
  change would break `--check`. Renovate bumps then show up in their own PR.
- A PR that changes a sourced `app.yaml`'s host, domainType, port, serviceName, name or
  namespace, the `globals.yaml` domains, or a sealed key set must regenerate. Renovate's
  `chart:` edits are never read.
- No guard is edited or imports the generator (ADR 0018:89-90). The rehearsal runs them
  unmodified on a scratch tree, and the household guard's `helm template`
  (`check-homepage-household.py:176`) proves the escaping.

## 5 Proof on today's 91 tiles

The proof PR touches only `homepage/`, `scripts/homepage/`, `validate-and-diff.yml`,
`docs/adr/0019-homepage-catalog-generator.md` plus its line in `docs/adr/README.md`, and
one line each in the apps `CLAUDE.md` Commands and Gotchas. Nothing under `services/`
changes.

**Catalog content** (today's pages, in the new structure):

- 70 tiles: 21 `household`, 49 admin-only; 91 placements in all.
- 2 household bookmarks (both `household-only`) and 10 admin bookmarks; today's info widgets.
- Tabs Pulse, Play and Make on household, plus Run and Iron on admin.
- 12 groups on household and 26 on admin, bookmark groups included, with each page's
  columns and order.
- Three description overrides: Calendar, Seerr RU and MicroBin.
- Widget variants:
  - Calendar: household-only iCal, native integrations on admin.
  - Seerr and Seerr RU: one shared household widget each; ADR 0018 shares those keys on purpose.
  - Calibre-Web: one shared widget until household PR 2.
  - Navidrome, Audiobookshelf, Immich and Karakeep: admin-only widgets.
- The `&github_prs` and `&queue_depth` anchors become catalog anchors.
- Today's CSS, settings, `proxmox.yaml` and favicons go into the pass-through files.
- Explicit values only where derivation cannot reach:
  - the kube-prometheus-stack tiles take `source` and an explicit `app`: Grafana
    `app: grafana` (href, siteMonitor and namespace derive), Prometheus `app: prometheus`, and
    Cluster Health and Security `app: prometheus` with `siteMonitor: null`;
  - Navidrome and MicroBin (`ingress.enabled: false`);
  - Authentik, Falco, Argo CD, Deployments, Edge & Certs, Traefik and pgAdmin (hosts outside
    `services/*/app.yaml`);
  - Calendar (no href);
  - off-cluster tiles: TrueNAS, Proxmox VE and the three node tiles, OPNsense, AdGuard Home,
    the four GitHub PR tiles, News.
- Nine tiles carry a `monitorPath`: Calibre-Web `/opds`; Radarr, Radarr RU, Sonarr, Sonarr RU,
  Lidarr and Prowlarr `/ping`; Cleanuparr `/health`; Grafana `/api/health`.
- Each page keeps its own `items` order (Convert lists MeTube first on household, CyberChef
  first on admin).

**`--compare`** fails CI while it exists. It parses the live hand-written ConfigMaps
(Helm-unescape, then strip the placeholder braces, as `check-homepage-household.py:138`
does) and the staged ones. Per page and per tile name it requires equality of:

- the tile set;
- tab, group and position;
- `href`, `siteMonitor`, `namespace`/`app` and `description`;
- widget types and the placeholder names each widget uses.

Bookmarks compare name and href; info widgets compare type. Ids, quoting, comments and
anchors are ignored. While both exist, a fix made only to a live page fails CI until the
catalog gets the same change, so the cut-over cannot silently revert it.

**Acceptance**

1. Unit tests pass, with one fixture per §2 rule.
2. `--check` passes.
3. `--compare` passes.
4. The rehearsal passes coverage, the ADR 0018 household guard and jellyfin-compat
   (admin keeps `version: 2`, A:447).
5. The placeholder names equal the sealed names: 6/6 on household, 38/38 on admin.
6. The diff preview reports no changes.
7. The PR body lists the `--inventory` counts: 21/70 tiles, 2/10 bookmarks, 3/5 tabs,
   12/26 groups.

The format targets the new design; the proof content is today's pages, which Fable replaces.

## 6 Handoff to sub-project 4 (Fable 5.2)

**Fable gets** ADR 0019, the generator with its flags and tests, the catalog with today's
content, the pass-through and staged files, the rehearsal step, and the open facts in §7.

**Fable may change:**

- all catalog content: tabs, groups, nesting, ids, names, audiences, widgets, thresholds
  and refresh intervals;
- all pass-through files and images;
- the tile-key allowlist;
- the `--inventory` schema and the render check built on it;
- `--compare`, deleted in Fable's first PR that changes content on purpose;
- the cut-over order and timing. Recommended: iterate while staged (GitHub shows staged
  diffs in full; the preview is capped), switch household, then admin, then delete the
  rehearsal.

**Fable keeps, unless Ben or a new ADR says otherwise:**

- admin is a superset of household, and nothing inherits an audience;
- the generator-owned keys (§2 rules 11-15);
- the placeholder rules and the two-way sealed-name check;
- an empty `custom.js`, and no catalog-only key in the output;
- ADR 0018's household guard stays separate from the generator;
- two instances, with today's ConfigMap, Application and SealedSecret names (the
  NetworkPolicies select on instance labels).

## 7 Risks and open questions

1. **Homepage v2.7.0 behaviour was read in the source** (tag commit `2e5f1013`, notes in
   `~/.cache/claude-homelab-live/onesource/upstream-facts.md`) but not run: `id` is the DOM
   id of the service `<li>`; the slug rule above; nested layout entries ignore `tab`;
   `service_group` is the immediate group; `widget` and `widgets` together break the widget
   proxy. A Homepage upgrade re-reads these.
2. **Calibre credentials:** ADR 0018:46,69 names `CALIBRE_HOUSEHOLD_*`; H:284-285 still uses
   `CALIBRE_USER/PASS`. The generator does not lint credential names (ADR 0018 leaves that to
   review). The proof uses what is sealed; household PR 2 changes the catalog in the same PR,
   which `--compare` enforces.
3. **Quoting:** PyYAML single-quotes a standalone placeholder, so a sealed value containing `'`
   would break; today's unquoted form breaks on `: ` or ` #` instead. Neither is checkable from
   Git.
4. **Double entry until the cut-over**, enforced by CI. Keep the window short.
5. **The admin cut-over diff likely exceeds the preview cap:** about 84 KB (A is 42,864 B;
   inferred, not measured). Review of that PR relies on the staged history and `--compare`.
6. **Validate's 15-minute budget** (`:12`): the rehearsal's run time is unmeasured. If too slow,
   copy only the directories the guards read.
7. **The coverage zone rule** (`check-homepage-coverage.py:264-268`) puts every public host on
   household. An admin-only public tile needs that rule changed first.
8. **ADR number:** 0019 assumes 0017 stays reserved for the CSI ADR. The work touches CI, so the
   implementation plan runs in plan mode.
