# Homepage new dashboards (sub-project 4): implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

## Context

Ben picked a new design for both Homepage dashboards on 2026-11-07: "Liquid glass" with an alarm mode, an admin
Pulse board and a phone-first household page. Sub-project 3 (apps#1590) built the engine that renders both pages
from `homepage/catalog.yaml` into staged ConfigMaps. This plan fills the catalog and the visuals, adds a CI
render check, and cuts each page over to live. Ben approved the design in four sections on 2026-11-13.

**Goal:** both pages show the picked design, rendered from the catalog and cut over, with a render check in CI.

**Architecture:** the existing generator stays the only writer of the ConfigMaps. It gains static CSS and mount
checks. A new render check promotes the prototype kit: it runs the deployed Homepage image against a mock
upstream and asserts on the DOM. Delivery is three PRs: content and check (staged), household cut-over, admin
cut-over.

**Tech stack:** Python 3 (stdlib, PyYAML 6.0.3, Playwright for Python in the render check only), Node from the
Homepage image (mock), Docker, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-11-13-homepage-new-dashboards-design.md` (read it first; this plan argues
from it). ADR: `docs/adr/0020-homepage-dashboards-stable-hooks.md`. Engine: ADR 0019.

**Reviewed:** a fresh reader checked the spec, and a second one checked this plan against the generator, the
guards, the workflow and the prototype kit. Their findings are folded in below.

**After approval:** this file is saved as `docs/superpowers/plans/2026-11-13-homepage-new-dashboards.md` and
committed with the spec and ADR 0020, both updated with the amendments below.

## Spec amendments (applied to the spec and ADR 0020 in the first commit)

None needs a decision from Ben, but the first changes something Ben was told.

1. **The household Internet chip cannot turn amber.** Homepage's header chips have no highlight, and CSS cannot
   read text. The chip reads `Down ⚠` in the normal text colour (the mark is part of the remapped text). On admin
   the same outage is red on the Edge & WAN card.
2. **Credentials land in PR 2 at the earliest.** The generator requires referenced names to equal sealed names in
   both directions, staged pages included, so the Calibre switch and the Jellyfin tiles cannot be staged in PR 1.
   PR 2 carries that content, its mock data and CSS, and Ben's browser test covers it there.
3. **Per-tab rules select through a common ancestor**
   (`#inner_wrapper:has(#<Tab>-tab[aria-selected="true"]) #layout-groups …`; checked in Homepage's source), so
   the lint bans `+` and `~` outside the no-hook block.
4. **Renames are not merges.** Latest Alert is renamed Notifications and stays its own Pulse tile; the `ntfy`
   launcher stays in Apps > Send. Cluster Health, Edge & Certs and News are renamed. The merges are Downloads
   into qBittorrent (both), Recipe Box into Mealie and Deployments into Argo CD. Now Playing holds Streaming Now
   and a new admin tile, Listening Now, which takes today's Navidrome now-playing widget; the Navidrome launcher
   stays in Media > Listen.
5. **No separate diff file.** The generated ConfigMap is a committed file, so the PR's "Files changed" view is its
   complete diff. Both cut-overs may pass the preview's 64 KB cap; each PR body adds the rendered Deployment mount
   diff, and the render check's screenshots show the result.
6. **The hook list gains Homepage's bookmark classes** (`bookmark`, `bookmark-group-name`, `bookmark-group-icon`,
   `bookmark-icon`, `bookmark-text`, `bookmark-name`, `bookmark-description`; read in the v2.7.0 source).
7. **The render check also fails** when an image or icon served by the page returns an error, and when a link or
   button on the household phone page is smaller than 44×44 px (the kit's tap audit). It lives in
   `scripts/homepage/rendercheck/`, not `render/`, so it cannot shadow `render.py`.

## Global Constraints

- Work in `~/Projects/homelab/.worktrees/apps-homepage-dashboards`. PR 1 is branch `feat/homepage-new-dashboards`.
- Ask Ben before every push, PR, merge and live cluster command. Local commits need no ask.
- Commit as Ben (name and address from the session brief, passed with `git -c`), ending with
  `Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>`.
- Secrets by name only. Never print a `secrets.yaml`; the generator's `sealed_names()` gives the names.
- Tools: `PY=~/.cache/claude-homelab-live/venv/bin/python` (PyYAML, yamllint); helm is
  `~/.cache/claude-household-boundary/bin/helm`. Docker cannot mount from the worktree here: copy what a
  container needs into a directory under `~/.cache/claude-homepage-dashboards/` or the scratchpad first.
- The picked design is the kit in `~/.cache/claude-homepage-proto/proto-violet-20261107T1912Z.tgz` (`proto/`):
  household is `directions/d1-glass/household` and `src/{core,household}.css`; admin is
  `directions/d1-violet/admin` and `src/admin.css` with d1-violet's three `--d1-acc*` tokens; images are
  `directions/d1-violet/images`. If the tarball is missing, stop and ask.
- Engine rules that bind content (ADR 0019): tile names unique per page; one placement per page; every household
  tile is on admin; a calendar `ref` target has exactly one widget on that page; referenced `HOMEPAGE_VAR_*`
  names equal the page's sealed names in both directions; no `{{` or `}}` in CSS or images.
- Every widget and host on today's pages stays (spec §1, §2), so both sealed-name sets stay fully referenced.
- No `cluster.local` names. New YAML passes `yamllint`. Prettier and pre-commit are not installed here: run
  `npx prettier@3.9.10 --check <changed yaml and json>`, or let the Format bot commit and pull before pushing
  again. Playwright is not installed either: `$PY -m pip install -r scripts/homepage/rendercheck/requirements.txt`
  into the cache venv, and point `HP_CHROME` at `~/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome`.
- Proof rule for every new admin query (spec §2): a catalog comment names the rule, probe, tile or scraped
  component that proves each metric. No proof, no query in v1.
- Thresholds come from spec §3, in displayed units, danger rule first.
- Hook rule for CSS: spec §5 plus amendments 3 and 6. Anything outside those lists is a spec change: ask Ben.

## Review Focus

1. A widget whose mock data is missing must fail the render check, not pass as a `-` block. (Task 2: strict mock.)
2. Household's `hideErrors: true` would hide a broken widget from the check. (Task 2: the test config forces `false`.)
3. A selector inside a desktop-only `@media` block must count as matched when only desktop runs match it.
   (Task 2: union across runs.)
4. A tile id renamed in the catalog but still used in CSS must fail without a browser. (Task 1: static id check.)
5. An image mount with a missing key or a wrong path stops the pod or blanks the page. (Task 1: mount check on
   cut-over pages; Task 2: the check serves the images and fails on a missing one.)

## Files

| Path | Change |
|---|---|
| `scripts/homepage/catalog.py`, `render.py`, `generate.py` | fix, shared CSS, CSS and mount checks, drop `--compare` |
| `scripts/homepage/compare.py`, `tests/test_compare.py` | delete |
| `scripts/homepage/tests/{fixture,test_catalog,test_render,test_output}.py`, new `test_render_check.py` | tests |
| `scripts/homepage/rendercheck/` (`render_check.py`, `requirements.txt`, `mock/server.js`, `mock/data/`, `mock/alarm/`) | new |
| `homepage/catalog.yaml`, `homepage/pages/shared.css`, `homepage/pages/{household,admin}/{settings.yaml,custom.css,files/}` | content |
| `homepage/staged/**` | regenerated; deleted page by page at cut-over |
| `.github/workflows/validate-and-diff.yml`, `.prettierignore`, `.pre-commit-config.yaml` | CI |
| `services/operations/homepage{,-admin}/manifests/templates/{configmap,secrets}.yaml`, `values.yaml` | cut-overs only |
| `docs/adr/0020-*.md`, `docs/adr/README.md`, `docs/adr/0018-*.md`, `CLAUDE.md`, the spec | docs |

---

## PR 1: content and render check (nothing live changes)

### Task 1: Engine changes

**Files:** modify `scripts/homepage/{catalog,render,generate}.py`, `tests/{fixture,test_catalog,test_render,
test_output}.py`, `.github/workflows/validate-and-diff.yml:90-92`, `CLAUDE.md:29,64-65`; delete
`scripts/homepage/compare.py`, `tests/test_compare.py`; empty both `homepage/pages/*/custom.css`.

**Interfaces (produces):**
- `homepage/pages/shared.css` (optional): `build_page` emits `custom.css` = shared text, a newline, the page's text.
- `render.check_css(css: str, page: str, ids: set[str], tabs: list[str], where: str) -> None`, called by
  `build_page` on the combined CSS; raises `CatalogError`.
- `render.check_mounts(repo: Path, page: str, data: dict) -> None`, called by `generate.render_all` only for pages
  not in `STAGED`; raises `CatalogError`.
- Mount convention, asserted by `check_mounts` and used by the render check: generated keys at
  `/app/config/<key>`, `favicon.svg` at `/app/public/icons/favicon.svg`, every other `files/` key at
  `/app/public/images/<key>`.
- `generate.py` has no `--compare`.

- [ ] **Step 1: tests first.**
  - `fixture.make_repo` also writes each page's `values.yaml` with a `persistence.<configmap name>.globalMounts`
    list that follows the convention for the generated keys and the page's `files/`.
  - Every test that depends on `STAGED` patches `generate.STAGED` itself (today `test_output.py:115-116` assumes
    both pages are staged), so the constant can change at each cut-over without touching tests.
  - `test_subgroup_name_not_a_string`: `items: [{"name": ["x"], "items": ["a"]}]` raises `CatalogError` matching
    `group has no name` (today: `TypeError` at `catalog.py:257`).
  - `test_shared_css_prepended`: shared `.service-card{}` and page `.service-block{}` give
    `data["custom.css"] == ".service-card{}\n.service-block{}"`.
  - `test_css_unknown_class`: `.bg-rose-500{}` raises, matching `not a Homepage hook`.
  - `test_css_positional`: `.service-card > div:first-child{}` raises matching `position`; the same rule between
    `/* no-hook:start */` and `/* no-hook:end */` passes; `#tabs ~ #layout-groups{}` raises.
  - `test_css_ids`: `#nope{}` raises matching `not a Homepage id, a tab or a tile`; `#a{}` (a placed tile),
    `#Main-tab{}` and `#layout-groups{}` pass.
  - `test_mounts` (with `STAGED` patched to empty): a `subPath: x.svg` that is no data key raises matching
    `x.svg`; a `files/y.svg` with no mount raises matching `y.svg`; `y.svg` mounted at `/app/config/y.svg` raises
    matching `/app/public/images/y.svg`; a matching set passes.
- [ ] **Step 2:** run `$PY -m unittest discover -s scripts/homepage/tests -v`; the new tests fail.
- [ ] **Step 3: implement.**
  - `catalog.py:257`: only test the layout-key collision when `item.get("name")` is a `str`; the recursive
    `group()` call then raises the existing "group has no name".
  - `check_css`: strip comments (keeping the no-hook markers' positions), drop declaration bodies, then check
    every selector. Allowed ids, classes and attributes are constants copied from spec §5 rule 1 and amendment 6;
    ids also allow `<Tab>-tab` for the page's tabs and the page's placed tile and bookmark ids. Outside the
    no-hook block, reject `:nth-*`, `:first-child`, `:last-child`, `:only-child`, `:first-of-type`,
    `:last-of-type` and the `+` and `~` combinators. Inside it, only the id and class allowlists apply.
  - `check_mounts`: read `<page dir>/values.yaml`, take `persistence.<configmap name>.globalMounts[]`; every
    `subPath` is a data key, every `files/` key is mounted, and every `path` follows the convention.
  - Remove `--compare`, `run_compare` and the `compare` import; delete the two files.
  - Workflow: delete line 92 (`generate.py --compare`); keep the rest of the rehearsal step.
  - `CLAUDE.md:29`: `[--check|--inventory]`. Lines 64-65: "Homepage pages come from homepage/catalog.yaml
    (ADR 0019, 0020). A staged page's live ConfigMap is frozen: change the catalog. Only a new app's tile goes in
    both. After cut-over, never edit the ConfigMap by hand."
  - Empty both `custom.css` files (their Tailwind selectors fail `check_css`; Tasks 3 and 4 replace them) and
    run `$PY scripts/homepage/generate.py`.
- [ ] **Step 4:** unit tests pass; `generate.py --check` exits 0; `generate.py --compare` exits 2.
- [ ] **Step 5:** commit `feat(homepage): CSS hook and mount checks, shared stylesheet; drop --compare`, together
  with the spec, ADR 0020 (amended) and this plan.

### Task 2: Render check

**Files:** create `scripts/homepage/rendercheck/render_check.py`, `requirements.txt`
(`playwright==<current release>`), `mock/server.js`, `mock/data/**`, `mock/alarm/**`; create
`scripts/homepage/tests/test_render_check.py`; modify `.prettierignore` and the `check-json` and `prettier` hooks
in `.pre-commit-config.yaml` to skip `scripts/homepage/rendercheck/mock/` (19 of the kit's data files are
templated and not valid JSON).

**Interfaces (produces):**
- `mock_slug(url: str) -> str`: `http://sonarr.media:8989/x` gives `sonarr-media-8989`. Mock data lives in
  `mock/data/<slug>/<request path>`, so no host table exists.
- `build_config(data: dict, down: set[str]) -> dict[str, str]`: file name to file text for one page, from
  `render.build_page()`'s output (as `generate.inventory()` uses it; `--check` already proves the committed
  ConfigMap equals it). It replaces every placeholder with `mock`; rewrites every `url` (widgets, info widgets,
  calendar integrations, `proxmox.yaml`) to `http://mock:8080/<slug><path and query>`; rewrites each
  `siteMonitor` to `http://mock:8080/up/<tile id>`, or `/down/<tile id>` for ids in `down`; sets
  `hideErrors: false`, `disableUpdateCheck: true` and `kubernetes.yaml` to `mode: disabled`; drops `namespace`,
  `app`, `podSelector`, `proxmoxNode` and `proxmoxVMID` from tiles. The `files/` keys come back unchanged, to be
  placed by the mount convention of Task 1.
- `failures(inventory_page: dict, runs: list[dict], page: str) -> list[str]`: one line per failure. A run is
  `{"tab", "viewport", "scenario", "ok": bool, "ids": [...], "groups": [...], "errors": int, "missing": [urls],
  "small": [descriptions], "selectors": {sel: bool}}`. `ok` is false when the page shows Homepage's config error
  panel (`#information-widgets` and `#myTab` missing). `missing` lists same-origin image and icon requests that
  failed. `small` lists links and buttons under 44×44 px; it fails only for household at 390 px.
- CLI: `render_check.py [--pages household,admin] [--out DIR] [--serve [--scenario calm|alarm]]`. Exit 1 on any
  failure. `--serve` leaves household on `127.0.0.1:3401` and admin on `:3402` and prints the URLs.
- Mock: the kit's `mock/server.js` plus two env switches. `MOCK_SCENARIO=alarm` looks in `mock/alarm/` before
  `mock/data/`. `MOCK_STRICT=1` answers 500 to a PromQL query with no value (today it returns an empty vector).

- [ ] **Step 1: failing tests** in `test_render_check.py` (no Docker, no browser; import Playwright lazily):
  - `test_mock_slug` with the value above and `https://10.9.9.20:8006/api2` giving `10-9-9-20-8006`.
  - `test_build_config_rewrites`: page data with one tile (`siteMonitor`, a `key` placeholder, a calendar with
    one iCal `url`) and one info `customapi`; assert both urls start `http://mock:8080/`, the query string
    survives, the key is `mock`, `hideErrors` is false, `kubernetes.yaml` is `mode: disabled`, `namespace` is gone.
  - `test_down_tiles`: `down={"t"}` gives `http://mock:8080/down/t`.
  - `test_failures_missing_tile`: inventory tile `x` on tab `A`, runs without `x`, gives a line naming `x`.
  - `test_failures_wrong_tab`: `x` present only in tab `B`'s run fails.
  - `test_failures_selector_union`: a selector false at 390 and true at 1440 passes; false everywhere fails; a
    selector on the allowlist passes.
  - `test_failures_error_box`: a run with `errors: 1` fails and names the tab and scenario.
  - `test_failures_missing_image`: a run with `missing: ["/images/aurora-still.svg"]` fails and names it.
  - `test_failures_small_target`: `small: ["a 30x30"]` fails for household at 390 and passes for admin.
- [ ] **Step 2:** run the tests; they fail.
- [ ] **Step 3: implement.**
  - Copy `mock/server.js` and `mock/data/` from the kit; rename each data directory to its upstream's slug, taken
    from the URLs in today's `--inventory`; delete data no catalog widget calls; add the two env switches;
    make the kit's Prometheus special case apply to any slug whose directory holds a `values.json`.
  - Runtime: copy the mock, the built config directories and each page's images into a temp directory, then
    start the mock and one Homepage container per page on one Docker network (image digest read from
    `services/operations/homepage-admin/values.yaml`; files mounted by the Task 1 convention; aliases
    `api.open-meteo.com` and `finnhub.io` on the mock; `NODE_TLS_REJECT_UNAUTHORIZED=0`;
    `HOMEPAGE_ALLOWED_HOSTS` for the mapped port), as the kit's `bin/*.sh` do.
  - Browser: Playwright Chromium with `channel="chrome"`, or the executable in `HP_CHROME`. For each scenario,
    viewport (390×844, 1440×900) and tab (`/#<slug>`): wait until `#layout-groups` exists and no block is still
    loading, capped at 20 s; never wait on the icon CDN. Save a screenshot to `--out`, then evaluate in the page:
    element ids present; `.service-group-name` and `.bookmark-group-name` texts; error boxes
    (`li.service details`, `.information-widget-error`); the kit's tap audit (`src/taps.js`); and for every
    style rule of the `/api/config/custom.css` sheet (walk `cssRules` through `@media` and `@supports`), whether
    `document.querySelector` finds its selector with pseudo-elements and `:hover`, `:focus*`, `:active` removed.
    Record failed same-origin image and icon responses.
  - Read the allowlists (selector states the mock cannot make; known small targets) from constants with one
    reason per entry.
- [ ] **Step 4:** unit tests pass. Smoke test on today's content:
  `$PY scripts/homepage/rendercheck/render_check.py --out <tmp>/shots`; fix slugs and data until no widget shows
  an error box on either page (admin's `kubernetes` header widget is the one expected error; Task 4 removes it;
  small-target failures are expected until Task 3's CSS). Look at two screenshots.
- [ ] **Step 5:** commit `feat(homepage): render check on the deployed image with a mock upstream`.

### Task 3: Household page

**Files:** modify `homepage/catalog.yaml` (household pages block, shared tiles, `info`), create
`homepage/pages/shared.css`, modify `homepage/pages/household/{settings.yaml,custom.css}`, add
`homepage/pages/household/files/*`, mock data as needed; regenerate `homepage/staged/**`.

**Interfaces (consumes):** Task 1's `check_css` and mount convention; Task 2's CLI.

- [ ] **Step 1: catalog.** Household tabs and groups exactly as spec §1's table, in that order. Calendar widget
  (household-only) with the agenda settings and feed windows of spec §1; movies in a non-red colour. `info`:
  logo (`/icons/favicon.svg`), `greeting: Starktastic` (household-only), the Internet `customapi` (audience
  `household`, URL and remap from spec §1, with `"0"` mapped to `Down ⚠`), search (today's), `openmeteo` (today's
  coordinates, label `Home`), `datetime` (`en-GB`, weekday short, day, month short, 24 h, no year). The
  household-only "Welcome home" greeting goes. My Account and GitHub stay bookmarks in a Links group on Tools.
- [ ] **Step 2: settings and images.** `settings.yaml` from the kit's household file minus `layout`,
  `hideErrors` and `disableUpdateCheck`; keep today's `language`, `disableIndexing`, `quicklaunch` provider and
  `favicon: /icons/favicon.svg`; `background: /images/aurora-still.svg`. `files/`: `favicon.svg` (the household
  mark), `aurora-still.svg`, `aurora-live.svg`, `grain.svg`, `glyph-watch.svg`, `glyph-library.svg`,
  `glyph-tools.svg`.
- [ ] **Step 3: CSS.** `shared.css` from the kit's `core.css`; household `custom.css` from `household.css`. Apply
  spec §5: tiles by id, not `data-name`; per-tab rules in the ancestor form of amendment 3; `> div:first-child`
  chains become `.service-title`, `.service-icon`, `.service-name`, `.service-description`,
  `.service-group-name`; bookmarks by their classes (amendment 6); the Jellyfin `nth-child` labels go (the lists
  become tiles in Task 6); list rows, agenda, search button and inline-style overrides move into the no-hook
  block; no alarm rules on household. A rule whose anchor tile is not on the page goes; the generator rejects it.
- [ ] **Step 4: verify.** `generate.py`, unit tests, `--check`. Rehearsal: copy the tree to a temp directory,
  copy `homepage/staged/services` over it, run `check-homepage-coverage.py`, `check-homepage-household.py` and
  `check-jellyfin-compat.py` there with helm on `PATH`; all three print their OK line. `yamllint`.
  `render_check.py --pages household` exits 0, tap sizes included.
- [ ] **Step 5: look.** Compare the Watch, Library and Tools screenshots at 390×844 and 1440×900 with the kit's
  renders (the session's `household-todays-credentials.png` shows the expected Watch tab). Differences are
  allowed only where content differs; a label that lost its colour or weight means a selector stopped applying.
  Fix and re-run until they match. Send Ben the three phone screenshots.
- [ ] **Step 6:** commit `feat(homepage): household page in the new design (staged)`.

### Task 4: Admin page

**Files:** modify `homepage/catalog.yaml` (admin pages block, tiles, `info`), `homepage/pages/admin/{settings.yaml,
custom.css}`, add `homepage/pages/admin/files/*`, `scripts/homepage/rendercheck/mock/{data,alarm}/**`; regenerate.

- [ ] **Step 1: structure.** Admin tabs and groups exactly as spec §2's table. Place today's tiles by group
  name; apply the renames and merges of amendment 4 (in a merge the launcher keeps its id and gains the readout's
  widget; the readout tile is deleted). The Pulse Jellyfin tile stays `streaming-now`; add `listening-now`. The
  calendar's five `ref` targets (`sonarr`, `sonarr-ru`, `radarr`, `radarr-ru`, `lidarr`) keep exactly one widget.
- [ ] **Step 2: Pulse board and header.** Add the cards of spec §2's table. Take each widget from the kit's
  `directions/d1-violet/admin/config/services.yaml` (`Needs Attention`, `Health`) and `widgets.yaml`, with real
  URLs: Prometheus as today, Alertmanager `http://kube-prometheus-stack-alertmanager.monitoring:9093`. Changes
  from the kit: Notifications has the `alerts` topic only; Backups has no Proxmox widget; Edge & WAN's metrics are
  Internet, Admin gate (`min(probe_success{tier=~"gate|gate-negative"})`), Alert path and Failed probes (today's
  query); thresholds are spec §3's, not the kit's; CronJob names and namespaces are read from the repo. Every new
  query gets its proof comment; drop any that has none and tell Ben. `info`: Alerts, CPU and Memory chips
  (admin), `greeting: Starktastic Admin` (admin); remove the `kubernetes` and `stocks` info entries; add the
  Markets tile (`stocks` service widget, today's watchlist) and rename News to Hacker News. Add the thresholds of
  spec §3 for Traefik, Argo CD and the *arr tiles.
- [ ] **Step 3: settings, images, CSS.** As Task 3 Steps 2 and 3, from the kit's admin files: `color: violet`,
  `font: plexData`, `fullWidth: true`, `providers.finnhub` as today, title `Starktastic Admin`; `files/`: the
  admin mark as `favicon.svg`, both auroras, `grain.svg`, the six tab glyphs (Apps uses the tools glyph).
  `custom.css` from `admin.css` with d1-violet's `--d1-acc*` values. The kit's positional rules for Alerts, ntfy,
  Volumes, Pipeline and Media Jellyfin go, and so do board rules anchored on tiles v1 lacks (apps commits,
  Controllers, Volumes, Pipeline); reorder fields instead where the layout needs it. Alarm rules stay
  (`.service-card:has(.service-block[data-highlight-level="danger"])`, the page-edge tint, `order`). The
  Calendar and Markets cards rescope Tailwind's red and rose colour tokens, as the kit does for the calendar, so
  only alarms are red.
- [ ] **Step 4: alarm scenario.** `mock/alarm/`: values that put each highlighted metric of spec §3 into warn or
  danger, one critical alert in the Alertmanager list, `down` for one tile, Internet `0`. The check's `down` set
  and both scenarios cover both pages.
- [ ] **Step 5: verify.** As Task 3 Step 4 for both pages; `render_check.py` exits 0 with the alarm selectors
  matched. Each allowlist is empty or every entry has a reason.
- [ ] **Step 6: look.** Compare all six tabs at 1440×900, calm and alarm, with the kit's renders
  (`admin-pulse-as-picked.png` shows Pulse). Check that nothing is red in the calm run. Send Ben Pulse calm,
  Pulse alarm and one other tab.
- [ ] **Step 7:** commit `feat(homepage): admin page with the Pulse board (staged)`.

### Task 5: CI job, docs, PR 1 hand-off

**Files:** modify `.github/workflows/validate-and-diff.yml`, `docs/adr/0020-*.md` (Status: Accepted),
`docs/adr/README.md`.

- [ ] **Step 1:** add job `homepage-render` (name `Homepage render`, `ubuntu-latest`, 15 min) after `validate`.
  Steps: checkout with `fetch-depth: 2`; a `changed` step that sets `run=true` when
  `git diff --name-only HEAD^1 HEAD` lists `homepage/`, `scripts/homepage/` or
  `services/operations/homepage{,-admin}/`; then, each with `if: steps.changed.outputs.run == 'true'`:
  setup-python as in `validate`, `pip install -r scripts/homepage/requirements.txt -r
  scripts/homepage/rendercheck/requirements.txt`, `python3 scripts/homepage/rendercheck/render_check.py --out
  "$RUNNER_TEMP/shots"`, and `actions/upload-artifact@v7` of the shots with `if: always() && …`. The job always
  runs and passes when nothing relevant changed, so it can be a required check.
- [ ] **Step 2:** full local pass: unit tests, `--check`, rehearsal guards, `yamllint .`, the Prettier check from
  Global Constraints, `render_check.py`. Report each command and result.
- [ ] **Step 3:** request a fresh whole-branch review (superpowers:requesting-code-review); fix what it finds.
- [ ] **Step 4:** commit `ci(homepage): render check job; ADR 0020 accepted`. Give Ben `render_check.py --serve`
  to test both pages in a browser, calm and alarm.
- [ ] **Step 5 (Ben):** go-ahead to push and open PR 1. The body states: nothing deploys; **both live pages are
  frozen from merge until their cut-over, except that a PR adding an app edits the live page and the catalog**;
  the `--inventory` counts; the render check's screenshots are in the run's artifacts. Expect the diff preview to
  report no changes. After merge, Ben adds `Homepage render` to the required checks.

---

## PR 2: household cut-over

### Task 6: Cut over household, with any sealed credentials

**Files:** modify `scripts/homepage/generate.py:14`, `services/operations/homepage/values.yaml`,
`services/operations/homepage/manifests/templates/configmap.yaml` (generated); delete
`homepage/staged/services/operations/homepage/`. With credentials: `homepage/catalog.yaml`,
`services/operations/homepage{,-admin}/manifests/templates/secrets.yaml`, `docs/adr/0018-*.md`,
`infrastructure/controllers/authentik/manifests/blueprints/invitation-flow.yaml:204-206`, mock data, CSS.

- [ ] **Step 1:** after PR 1 merges, fetch and branch `feat/homepage-household-cutover` from `origin/main`.
- [ ] **Step 2 (Ben, any time before this; see "Ben's credential steps"):** sealed lines for Calibre and
  Jellyfin. If they are not there, skip Steps 3 and 4 and do them later as their own PR.
- [ ] **Step 3: Calibre.** Calibre-Web has one widget today, shared by both pages. Make it admin-only (it keeps
  `CALIBRE_USER/_PASS`) and add a `household-only` twin on `CALIBRE_HOUSEHOLD_USER/_PASS`. Merge the two
  `encryptedData` lines into household `secrets.yaml` in alphabetical order and delete
  `HOMEPAGE_VAR_CALIBRE_USER` and `_PASS` from it.
- [ ] **Step 4: Jellyfin.** Merge `HOMEPAGE_VAR_JELLYFIN_HOUSEHOLD_TOKEN` into both `secrets.yaml` files. Add to
  the catalog, with the header and URLs of spec §1 (host `http://jellyfin-main.media:8096`): a household-only
  `Items/Counts` widget on `jellyfin`; tiles `new-movies` and `new-episodes` (audience `household`, no `href`,
  one widget each, audience `household`), placed in Watch on household and Media > Watch on admin. Add mock data
  and CSS for the hero. Add the `JELLYFIN_HOUSEHOLD_TOKEN` row to ADR 0018's table ("access token of local
  non-admin user `homepage-household`; library counts and latest items; also sealed on admin for the same
  lists"). With Ben's OK for the shared blueprint, add `"homepage-household"` to the `reserved` set and extend
  its comment.
- [ ] **Step 5: cut over.** Remove `"household"` from `STAGED`; add one `globalMounts` entry per new
  `files/` key to household `values.yaml` (`/app/public/images/<name>`, `readOnly: true`); run `generate.py`;
  delete the staged household directory.
- [ ] **Step 6: verify.** Unit tests; `--check` (now including `check_mounts`); the three guards directly on the
  tree for household and through the rehearsal for admin; `helm template` of the household chart with the real
  value layers renders; `render_check.py` exits 0; `yamllint`.
- [ ] **Step 7:** commit `feat(homepage): cut the household page over to the catalog (ADR 0020)`. Ben tests on
  `--serve` (this is the first time the Jellyfin hero and the Calibre switch are on screen), then gives the
  go-ahead to push and open PR 2. The PR body carries the rendered Deployment mount diff. Review the diff preview
  with Ben: only `homepage-config`, the household Deployment's mounts and, with credentials, the two SealedSecrets
  change.
- [ ] **Step 8 (Ben, after merge):** open starktastic.net on a phone and a desktop; every tile and widget shows.

### Ben's credential steps (no values pass through Claude)

1. Calibre-Web: Admin, add user `homepage-household`, every role off, a strong password.
2. Jellyfin: Dashboard, Users, add `homepage-household`: not an administrator; library access to the five
   non-admin libraries (or fewer); media playback, deletion and remote control off. Then get its token:

   ```bash
   read -rs PW && curl -s https://benplus.app/Users/AuthenticateByName -H 'Content-Type: application/json' -H 'Authorization: MediaBrowser Client="Homepage", Device="homepage-household", DeviceId="homepage-household", Version="1"' -d "{\"Username\":\"homepage-household\",\"Pw\":\"$PW\"}" | jq -r .AccessToken
   ```

3. Seal, from a directory outside the repo (`mkdir -p ~/.cache/claude-homepage-dashboards/seal && cd` there):
   run `<worktree>/scripts/seal.sh homepage-secrets operations` and enter
   `HOMEPAGE_VAR_CALIBRE_HOUSEHOLD_USER=homepage-household`, `HOMEPAGE_VAR_CALIBRE_HOUSEHOLD_PASS=…` and
   `HOMEPAGE_VAR_JELLYFIN_HOUSEHOLD_TOKEN=…`, then Ctrl+D. Run it again as
   `seal.sh homepage-admin-secrets operations` with the token line only. Tell Claude the two files are there;
   they hold ciphertext only.

---

## PR 3: admin cut-over

### Task 7: Cut over admin and remove the rehearsal

**Files:** modify `scripts/homepage/generate.py:14`, `services/operations/homepage-admin/values.yaml`,
`services/operations/homepage-admin/manifests/templates/configmap.yaml` (generated),
`.github/workflows/validate-and-diff.yml` (delete the "Rehearse staged Homepage pages" step); delete
`homepage/staged/`.

- [ ] **Step 1:** after PR 2 merges, branch `feat/homepage-admin-cutover` from `origin/main`.
- [ ] **Step 2:** `STAGED = set()`; add the admin image mounts to `values.yaml`; `generate.py`; delete
  `homepage/staged/`; delete the rehearsal step. Check household's mounts are unchanged (household disables
  admin's `persistence` block and has its own).
- [ ] **Step 3: verify.** As Task 6 Step 6, all guards directly on the tree, plus `check-admin-gate.py`.
- [ ] **Step 4:** commit `feat(homepage): cut the admin page over to the catalog (ADR 0020)`. Ben tests on
  `--serve`, including the animated aurora's smoothness on the desktop, then gives the go-ahead to push and open
  PR 3. The PR body carries the rendered Deployment mount diff (`helm template` before and after). Review the
  diff preview and the ConfigMap's "Files changed" diff with Ben.
- [ ] **Step 5 (Ben, after merge):** open admin.internal.starktastic.net; every card shows data. A new query
  that reads `-` or errors is fixed forward in the catalog. Then stop the session's prototype containers.

## Verification (end to end)

- `python3 -m unittest discover -s scripts/homepage/tests -v` and `generate.py --check` pass at every commit.
- `render_check.py` exits 0 on both pages, calm and alarm, phone and desktop, locally and in CI.
- The coverage, household, Jellyfin and admin-gate guards print their OK lines on the cut-over pages.
- Each PR's ArgoCD diff preview is reviewed with Ben; PR 1's is empty.
- Ben has opened both pages on `--serve` before each cut-over and on the live hosts after it.

## Not in this plan

Spec §8's later PRs (extra widgets per tab, further credentials). I will propose them as follow-ups once PR 3
has merged.
