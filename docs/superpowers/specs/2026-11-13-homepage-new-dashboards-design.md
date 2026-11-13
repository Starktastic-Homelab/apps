# Homepage new dashboards (sub-project 4)

Status: sections A–D approved by Ben on 2026-11-13 (second pass, after the re-evaluation was redone from the
original inputs); Ben approved this file and the plan on 2026-11-13. It replaces an earlier draft of the same day, and it
includes seven amendments from the spec and plan reviews (listed in the plan).

Basis: apps main `7e2a10c7`; Homepage v2.7.0 (tag `2e5f1013`, source read with `gh api`); the picked prototype
(`~/.cache/claude-homepage-proto/proto-violet-20261107T1912Z.tgz`), run locally on 2026-11-13 and looked at.
Engine: ADR 0019 and `2026-11-13-homepage-one-source-design.md`. Boundary: ADR 0018. Gate: ADR 0014.
Research: `~/Projects/homelab/homepage-redesign-research-2026-11-07.md` (§3–§6).

## Outcome

Both Homepage pages show the design Ben picked on 2026-11-07 ("Liquid glass" with the alarm mode), rendered
from `homepage/catalog.yaml` and cut over to live one page per PR. A CI render check runs the deployed Homepage
image on the generated pages, so a Homepage bump or a catalog edit that breaks a tile, a tab or a CSS hook
fails before merge.

Done means: both pages cut over, CI green, each ArgoCD diff preview reviewed, Ben has tested both in a browser.

## Why it is not a reskin

The prototype Ben picked is a board with content, not only a look: the admin Pulse tab leads with an alert
list and six health cards, and the household Watch tab leads with a Jellyfin hero. Shipping today's tiles in
glass would deliver the material without the page. So v1 builds the Pulse board, limited to data the repo
already proves, and lets the rest arrive in small PRs after the cut-over.

## Ben's decisions

Carried from earlier sub-projects:

- Two instances; admin shows everything household shows, plus more; nothing inherits an audience (ADR 0019).
- Household: every Authentik account, phone-first, aggregates only, the credential is the boundary (ADR 0018).
  Admin: Ben only, desktop-first, `admin.internal.starktastic.net` (ADR 0014).
- Look: d1 "Liquid glass" plus d3's alarm mode. Admin accent violet. Red only for alarms. No grid or circuit
  background.
- Update risk: stable hooks plus a CI check; no `custom.js`.

Made 2026-11-13 in this sub-project:

- **A. Content.** v1 builds the Pulse board, with every new query proven from Git (§2). Household keeps its 21
  tiles under the prototype's tabs. Richer widgets on the other tabs follow after the cut-over (§8).
- **B. Visuals.** Keep the prototype's stylesheet and all its images. Fix the position-based selectors. Keep
  a small marked block of selectors where Homepage has no hook, guarded by the render check (§5).
- **C. Alarms.** Thresholds mirror the alert rules in Git: red where a critical rule would fire, amber where a
  warning rule would (§3). Household has no alarm mode.
- **D. Delivery.** Three PRs (§7). Both live pages freeze from PR 1's merge until their cut-over; a PR that
  adds a new app during the freeze edits the live page and the catalog. Household Calibre moves to its own
  user here (the old "household PR 2" is folded in). Ben creates the Calibre and Jellyfin household
  credentials before the household cut-over; neither blocks it (§9).

## Approaches considered

| Question | Options | Picked |
|---|---|---|
| Content scope | (1) today's tiles regrouped; (2) the Pulse board on Git-proven data, the rest in waves; (3) everything in the prototype at once | 2. Option 1 drops most of the picked board. Option 3 puts about a hundred unproven endpoints into one cut-over. |
| CSS | (1) rewrite on hooks only; (2) keep the prototype's stylesheet, fix position-based selectors, mark and guard the no-hook ones; (3) keep as is | 2. Measured: no Tailwind-class selectors; 105 of 130 household and 150 of 174 admin selectors already sit on stable hooks. Option 1 loses the phone rows and search button. |
| Render check | (1) a new Python mock; (2) promote the prototype kit (mock, data files, screenshot script) | 2. It exists, it already renders both pages, and it runs on the Homepage image's own Node. |

## 1 Household page (starktastic.net)

Title `Starktastic`, `color: slate`, three tabs:

| Tab | Groups (items) |
|---|---|
| Watch | Watch (Jellyfin) · Coming Up (Calendar) · Requests (Seerr, Seerr RU) |
| Library | Listen (Navidrome, Audiobookshelf) · Read (Calibre-Web, Shelfmark) · Photos (Immich) |
| Tools | Create (Excalidash, MicroBin) · Convert (ConvertX, Stirling PDF, MeTube, CyberChef) · Find & Keep (SearXNG, Karakeep, Mealie) · Send (PairDrop, ntfy, Listmonk) · Links bookmarks (My Account, GitHub) |

All 21 of today's household tiles stay. Widgets in v1:

- **Calendar:** the two iCal feeds (Sonarr, Radarr; ADR 0018's shared keys) in `agenda` view: `maxEvents: 12`,
  `previousDays: 0`, `showTime`, `params.showName`; Sonarr `pastDays=30&futureDays=14`, Radarr
  `releaseTypes=digitalRelease&pastDays=60&futureDays=90`, so a feed is never empty (research b03).
- **Seerr, Seerr RU:** unchanged.
- **Calibre-Web:** `calibreweb`, on `CALIBRE_HOUSEHOLD_USER/_PASS` once sealed (§9), on today's names until then.
- **Jellyfin, once its token is sealed (§9):** `customapi` only, never a `jellyfin`-type widget, with the header
  `Authorization: MediaBrowser Token="{{HOMEPAGE_VAR_JELLYFIN_HOUSEHOLD_TOKEN}}"`:
  - on the Jellyfin tile, `Items/Counts` (Movies, Series, Episodes), hourly;
  - two tiles in the Watch group, **New movies** and **New episodes**, each one `Items/Latest` dynamic-list
    (limit 6, every 15 min). They are tiles of their own because a label attached to "the third widget" is
    position-based (§5). Their audience is `household`, so admin shows them too (Media > Watch), on the same
    token, sealed in both Secrets.
- Every other tile: link plus status dot.

Header: mark, wordmark (`greeting: Starktastic`), **Internet** chip, search, weather, date and time.

- The Internet chip is an info `customapi` on
  `http://kube-prometheus-stack-prometheus.monitoring:9090/api/v1/query?query=min(probe_success%7Btier%3D%22external%22%7D)`
  remapped `"1"` → Online, `"0"` → `Down ⚠`, anything else → Unknown. The probes are in
  `prometheus-blackbox-exporter/manifests/probe-external.yaml`. It holds no credential, the query is fixed on the
  server, and `check-homepage-household.py` accepts the URL, so ADR 0018's table gains no row for it.
- Search is today's SearXNG setup; weather is today's `openmeteo` at today's coordinates; the date reads
  `Fri 13 Nov, 18:54` (`en-GB`, 24 h, no year).
- Household has no alarm mode: no highlight rules, no alarm CSS. The chip cannot change colour (header chips
  have no highlight, and CSS cannot read text), so the warning mark is part of its text.

## 2 Admin page (admin.internal.starktastic.net)

Title `Starktastic Admin`, `color: violet`, six tabs:

| Tab | Groups |
|---|---|
| Pulse | Needs Attention · Health · Now Playing · Coming Up · Out There |
| Media | Watch · Listen · Read · Photos · Requests |
| Pipeline | Acquire · Index · Download · Subtitles |
| Apps | Create · Convert · Find & Keep · Documents · Send · Home |
| Platform | Ship · Edge · Guard · Observe · Core · Code bookmarks |
| Iron | Compute · Network · Storage · Reference and Accounts bookmarks |

**What stays.** Every host, every bookmark and every widget on today's admin page, with today's URLs, keys and
queries. Three readout-and-launcher twins merge into one tile per app: Downloads into qBittorrent (both),
Recipe Box into Mealie, Deployments into Argo CD. Four tiles are renamed and stay their own tiles: Latest Alert
becomes Notifications (the `ntfy` launcher stays in Apps > Send), Cluster Health becomes Cluster, Edge & Certs
becomes Edge & WAN (its cert, request and latency metrics go to the Traefik tile), News becomes Hacker News.
Stocks leave the header for a Markets tile in Out There. Names are unique and a tile sits in one place per page,
so Now Playing holds Streaming Now (today's Pulse Jellyfin tile) and a new admin tile, Listening Now, which takes
today's Navidrome now-playing widget; the Navidrome launcher stays in Media > Listen.

**What is new: the Pulse board.**

| Card | Shows | Source |
|---|---|---|
| Alerts | The firing, unsilenced alerts routed to ntfy (name and age, up to 6) and how many are critical; then firing alerts, rules alive, failed notifications in 24 h and silences | Alertmanager `/api/v2/alerts?active=true&silenced=false&inhibited=false&receiver=ntfy` for the list and the critical count (`customapi`, keyless, in-cluster), so a silence ends alarm mode; Prometheus for the rest |
| Notifications | Latest push on the `alerts` topic | today's `ntfy` widget and token |
| Cluster | Nodes ready, unhealthy pods, restarts in 1 h | today's queries plus `kube_pod_container_status_restarts_total` |
| Edge & WAN | Internet, admin gate, alert path, failed probes | `probe_success` by `tier` |
| Security | Local bans, Falco events, 4xx/5xx in 1 h | today's queries |
| Memory | Containers near limit, OOM kills, top container, node free | `ALERTS` for the two memory rules; the rule's own expression; `node_memory_MemAvailable_bytes` |
| Capacity | CSI slots free, tightest worker, fullest volume, TSDB use | `homelab:proxmox_csi_slots_free:count`; today's volume query; `prometheus_tsdb_*` |
| Backups | Age of the last Postgres dump and cert backup, stale jobs | `kube_cronjob_status_last_successful_time` |

Header: mark, wordmark, **Alerts**, **Internet**, **CPU** and **Memory** chips (info `customapi` on Alertmanager
and Prometheus, 30–60 s), search, weather, date and time. The chips replace the `kubernetes` info widget, which
polls the API server every 1.5 s. `kubernetes.yaml` stays `mode: cluster` (generator-owned) for the pod dots.

**The proof rule.** A new query ships in v1 only if every metric in it is either used by a rule, probe or tile
already in the repo, or is a core metric of a component whose scrape `kube-prometheus-stack/values.yaml`
enables (node-exporter, kube-state-metrics, kubelet, Alertmanager, Prometheus itself). Each new query carries
a catalog comment naming its proof. Anything else waits for §8. Not proven today, so not in v1: sealed-secrets,
Reloader, MetalLB, the Postgres and Redis exporters, Loki, Tempo, Alloy and Unpackerr metrics; the `ops` ntfy
topic (needs an ACL grant); the last-vzdump row (a new call on the Proxmox token).

## 3 Alarm mode and thresholds (admin only)

A card holding a `danger` block is outlined red and moves first in its group; while one is on screen the page
edge takes a red tint. `warn` is amber. No other red appears on the page: calendar colours and markets avoid it.

Rule: a block is red exactly where a critical alert rule in Git would fire, and amber where a warning rule
would. Where no rule exists, the list below decides. Rules are written danger first; values are in displayed
units.

| Card | Metric | Amber | Red | Mirrors |
|---|---|---|---|---|
| Alerts | Critical | | > 0 | severity `critical` |
| Alerts | Firing | > 0 | | every alert the routes send to ntfy |
| Alerts | Rules alive | | = 0 | Watchdog missing |
| Alerts | Notify fails 24 h | > 0 | | ntfy or the Watchdog heartbeat could not be reached |
| Cluster | Nodes ready | | < 3 | Ben, 2026-11-13 |
| Cluster | Unhealthy pods | > 0 | | Ben; leftover Failed pods keep it amber until cleaned |
| Cluster | Restarts 1 h | ≥ 3 | | |
| Edge & WAN | Internet | | down | `BlackboxExternalDepDown` |
| Edge & WAN | Admin gate | | failing | `AdminGateDown`, `AdminGatePublicAnswer` |
| Edge & WAN | Alert path, failed probes | > 0 failing | | `BlackboxProbeFailed` (warning) |
| Memory | Near limit | > 0 | | `ContainerMemoryNearLimit` |
| Memory | OOM killed | | > 0 | `ContainerOOMKilled` |
| Memory | Top container | ≥ 90% | | the same rule's threshold |
| Capacity | Fullest volume | ≥ 90% | ≥ 95% | `PVCSpaceLow`, `PVCSpaceCritical` |
| Capacity | CSI slots free | < 10 | = 0 | the two cluster CSI rules |
| Capacity | Tightest worker | ≤ 3 | | `ProxmoxCSINodeAttachmentHeadroomLow` |
| Backups | Dump and cert backup age | > 26 h | | `CronJobNotSucceededRecently` |
| Traefik | Cert expiry | < 10 days | < 3 days | both cert rules warn at 10 days; red at 3 is an addition, because HSTS turns an expired cert into an outage |
| Argo CD | Out of sync | > 0 | | `ArgoCDAppOutOfSync` |
| Argo CD | Unhealthy | | > 0 | Ben, 2026-11-13 |
| *arr tiles | Queue depth | ≥ 20 | ≥ 50 | today's rules, kept |

Falco's count gets no highlight until its baseline is known (it ran near 100 events a minute on 11-06).

## 4 Visual system

The prototype's design, unchanged in intent (`directions/d1-glass` for household, `directions/d1-violet` for
admin; its `NOTES.md` records palette, type and contrast measurements):

- Settings: `theme: dark`, `cardBlur: xl`, `headerStyle: boxedWidgets`, `cardStyle: hairline`,
  `blockStyle: refined`, `statusStyle: dot`, `disableCollapse: true`, `font: plexData` and `fullWidth` on admin,
  `quicklaunch.mobileButtonPosition: bottom-right`.
- Glass cards over an aurora background on brand navy; household accent brand blue, admin violet.
- Household phone: app-style header, grouped list rows, a 2-up launcher grid on Tools, a floating tab bar with
  glyphs and a search button at the thumb.
- Admin desktop: a per-tab board from 1280 px; Pulse puts alerts beside health.
- Accessibility carried over from the prototype's checks: 44 px targets on the household phone, no text below
  WCAG AA on the aurora, `prefers-reduced-motion` stops motion. The animated aurora loads only from 1024 px
  with motion allowed; phones get the still one.
- All 15 images stay (27 KB in total) as `files/` entries: per page a mark, a still and a live aurora, grain
  and its tab glyphs. Their `values.yaml` mounts land in each page's cut-over PR, never earlier: a mount whose
  key the live ConfigMap lacks stops the pod from starting.

## 5 Hook rule

1. Selectors use Homepage's ids (`#layout-groups`, `#myTab`, `#<Tab>-tab`, `#tabs`, `#information-widgets`,
   `#information-widgets-right`, `#widgets-wrap`, `#background`, `#inner_wrapper`, `#footer`), its named classes
   (`service`, `service-card`, `service-title`, `service-title-text`, `service-name`, `service-description`,
   `service-icon`, `service-tag`, `service-site-monitor`, `site-monitor-status`, `service-container`,
   `service-block`, `service-block-value`, `service-block-label`, `services-group`, `subgroup`,
   `service-group-name`, `service-group-icon`, `information-widget-<type>`, and for bookmarks `bookmark`,
   `bookmark-group-name`, `bookmark-group-icon`, `bookmark-icon`, `bookmark-text`, `bookmark-name`,
   `bookmark-description`), its attributes (`data-name`,
   `data-highlight-level`, `role`, `aria-selected`) and catalog tile ids. All were read in the v2.7.0 source.
   A tile is addressed by its id, not its `data-name`, from here on.
2. No Tailwind utility class anywhere.
3. No selector carries meaning by position. Where the prototype labelled or paired things by `:nth-child`,
   the content changes instead (a tile of its own, a different field order) or the flourish goes. Per-tab rules
   select through a common ancestor (`#inner_wrapper:has(#<Tab>-tab[aria-selected="true"]) #layout-groups …`),
   so the `+` and `~` combinators are banned too.
4. Where Homepage offers no hook (rows inside list widgets, the calendar agenda, the phone search button,
   icon sizing under inline styles), structural selectors are allowed between `/* no-hook:start */` and
   `/* no-hook:end */`, one such block per file. If one breaks, the damage is cosmetic and the render check
   fails. Nested rules and at-rules the lint cannot see into (`@scope`, `@starting-style`) are rejected.

## 6 Render check

`scripts/homepage/rendercheck/`: the prototype kit's mock (`server.js`, run with the Homepage image's own Node, so no
second image), its data files trimmed to the routes the catalog's widgets call, and `render_check.py`.

1. Build a config directory per page from the generator's page data (`--check` already proves the committed
   ConfigMap equals it). Place the page's images where the pod mounts them. Point every widget `url`,
   feed and `siteMonitor` at the mock, replace every placeholder with `mock`, set `kubernetes.yaml` to
   `mode: disabled` and drop the pod and Proxmox status keys, since CI has no cluster.
2. Start the Homepage image at the digest in `homepage-admin/values.yaml` with the mock on one Docker network.
   Two scenarios: **calm** (good values, monitors up) and **alarm** (warn and danger values on admin, one
   monitor down, Internet Down).
3. Load every tab of both pages at 390×844 and 1440×900 in both scenarios with Playwright for Python (pinned;
   the runner's Chrome).
4. Fail when:
   - a tile id, tab or group from `--inventory` is missing from the DOM, or a tile is on the wrong tab;
   - a widget shows Homepage's error box, a block never gets a value, the mock is asked for something it has
     no answer for, or a page shows the config error panel;
   - a block is red in the calm scenario;
   - `custom.css` is not found as a stylesheet, or one of its selectors matches nothing in every run (an
     allowlist names the states the mock can't make);
   - an image or icon the page serves returns an error;
   - a link or button on the household phone page is smaller than 44×44 px (the kit's tap audit).

   The static half of §5 (a class, id or attribute outside the lists; a positional or sibling selector outside
   the `/* no-hook */` block; a tile id that is not on the page) is checked by the generator itself, so it fails
   `--check` without a browser. The generator also checks, for a cut-over page, that every `values.yaml` mount
   names a key the ConfigMap has, at the path the page expects.
5. Upload the screenshots as a workflow artifact (mock data only).

`--serve` leaves both pages running on `127.0.0.1` for Ben's browser test. `--inventory` gains whatever fields
the check needs. CI: one job, `homepage-render`, in `validate-and-diff.yml` on `ubuntu-latest`, run when
`homepage/**`, `scripts/homepage/**` or a homepage `values.yaml` changes (the image tag lives there) and
skipped otherwise, which GitHub counts as passing. Ben adds it to the required checks. Homepage bumps stay
hand-merged (#1552); the check guards them and every catalog edit.

## 7 Delivery

| PR | Contents | Live effect |
|---|---|---|
| 1 | `isinstance(name, str)` check for subgroup names in `catalog.py` (raises `CatalogError`; one test). The v1 catalog and pass-through files for both pages, staged. The render check and its CI job. `--compare` removed from the generator, its module, its tests and the rehearsal step. ADR 0020, this spec, the plan, the apps `CLAUDE.md` gotcha line | None. **Both live pages are frozen from this merge until their cut-over.** The PR body says so |
| 2 | Household cut-over: `household` out of `STAGED`, regenerate over `services/operations/homepage/manifests/templates/configmap.yaml`, delete its staged copy, add the image mounts to household `values.yaml`. The Calibre and Jellyfin credentials if sealed (§9), with ADR 0018's table rows | Household changes; Reloader restarts the pod |
| 3 | Admin cut-over, same steps; delete the rehearsal step | Admin changes |

- Iteration happens on the branch before PR 1 merges, and PRs 2 and 3 follow as soon as Ben has tested each
  page on `--serve`, so the freeze stays short.
- Freeze exception: coverage runs on the live ConfigMaps, so a PR that adds an app during the freeze adds its
  tile to the live page and to the catalog. Every other change waits for the cut-over.
- Until the last cut-over the rehearsal step keeps running the coverage, household and Jellyfin guards on the
  staged pages.
- Credentials land in PR 2 at the earliest: the generator requires referenced names to equal sealed names in
  both directions, staged pages included. PR 2 therefore carries that content with its mock data and CSS.
- Each cut-over PR's diff preview is reviewed. Either may pass the preview's 64 KB cap. The generated ConfigMap
  is a committed file, so the PR's "Files changed" view is its complete diff; the PR body adds the rendered
  Deployment mount diff, and the render check's screenshots show the result.
- Ben tests each page on `--serve` before its cut-over and on the live host after it.

## 8 After the cut-over (not part of Done)

Small PRs, each checked on the live admin page after merge, in this order:

1. Media and Pipeline: the research's extra widgets on existing admin keys (*arr health lists, Jellyfin system
   and playback, Audiobookshelf sessions, Immich queues, download speeds).
2. Apps, then Platform and Iron: the same for those tabs; Platform metrics the proof rule held back, after one
   read-only query batch from the runner with Ben's OK.
3. Cards that need a new credential, as Ben mints each: household Audiobookshelf, Navidrome, Immich storage,
   Shelfmark and Mealie; admin `ops` topic, Cleanuparr, Lingarr, Listmonk, Excalidash, healthchecks.

## 9 Ben's tasks

None blocks PR 1. The plan gives exact commands; values never pass through Claude.

1. **Calibre-Web:** create local user `homepage-household` with every role off; seal
   `HOMEPAGE_VAR_CALIBRE_HOUSEHOLD_USER` and `_PASS` into `homepage-secrets`.
2. **Jellyfin:** create local non-admin user `homepage-household` with library access to the five non-admin
   libraries (fewer if Ben prefers) and playback, deletion and remote control off; sign in once through the API
   to get its access token; seal `HOMEPAGE_VAR_JELLYFIN_HOUSEHOLD_TOKEN` into `homepage-secrets` and
   `homepage-admin-secrets`.
3. OK one line in the shared Authentik blueprint that reserves the name `homepage-household` (ADR 0015).
4. Add `homepage-render` to the required status checks after PR 1 merges.
5. Browser tests, and the go-ahead for each push, PR and merge.

If a credential isn't sealed when the household cut-over is otherwise ready, household cuts over without it
(Calibre on today's login, Jellyfin as a link) and the switch follows as its own PR.

## 10 Non-goals

- Anything in §8; backup state beyond the two CronJob ages; any live query before the cut-over.
- Changes to the guards' rules, the admin gate, NetworkPolicies, or the Secret and ConfigMap names.
- Household-only tiles (ADR 0019's open question stays open); search suggestions; RTL, Hebrew date, an
  announcements channel; turning Renovate automerge back on for Homepage.

## 11 Calls I made (for Ben to check)

- Jellyfin's two lists are tiles of their own, shown on both pages on the household token.
- Listening Now is a new admin tile for Navidrome's now-playing widget.
- The household Internet chip marks an outage in its text (`Down ⚠`), not by colour.
- The admin header's CPU and Memory chips replace the `kubernetes` info widget.
- Twin tiles merge into one tile per app (list in §2).
- Dates read `en-GB`, 24 h, no year, as in the prototype.
- Calendar movie dots are not red on either page (red is reserved for alarms).
- Cert expiry turns red under 3 days although no rule does.
- Falco's count has no highlight yet.
- My Account and GitHub stay bookmarks on household, styled as launcher tiles.

Left to the builder: exact CSS and copy, group order within a tab, mock data, the render-check allowlist,
how images are mounted (one mount per file or one projected directory), the inventory fields added.

## 12 Risks

- The mock proves rendering and hooks, not live data. A v1 query that is proven from Git can still show `-`
  live; it is fixed forward in the catalog after the cut-over.
- The animated aurora's frame rate under about 25 blurred cards is unmeasured. Ben checks it on the desktop in
  the browser test; the fallback is the still image.
- A Homepage bump that changes a widget's routes or markup fails the render check until the mock or CSS is
  updated in the bump PR.
- The freeze: a live fix needed in the window goes into the catalog and waits, or the cut-over is pulled forward.
- The household Jellyfin token is revoked by a password change or a new sign-in with the same device id; the
  tiles then render blank on household (`hideErrors: true`) and show an error on admin.
- Prometheus and Alertmanager have no NetworkPolicy today; if one is added, both pages need an allow rule.
