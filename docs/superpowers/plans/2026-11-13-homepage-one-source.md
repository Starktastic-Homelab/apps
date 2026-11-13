# Homepage one source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate both Homepage ConfigMaps from one catalog, prove it on today's pages in a staged copy, and gate it in CI, without deploying anything.

**Architecture:** `homepage/catalog.yaml` plus per-page pass-through files feed `scripts/homepage/generate.py`. The generator validates the catalog (19 rules), builds each page's data keys, dumps a ConfigMap and writes it under `homepage/staged/` while the page is in `STAGED`. `--check` byte-compares, `--compare` matches the staged pages against today's hand-written ones, and a rehearsal runs the unmodified guards on the staged pages.

**Tech Stack:** Python 3 stdlib, PyYAML 6.0.3, unittest, GitHub Actions (Validate job).

**Spec:** `docs/superpowers/specs/2026-11-13-homepage-one-source-design.md` (commits 45d11493, f0da8e3d). Upstream and repo facts: `~/.cache/claude-homelab-live/onesource/{upstream-facts,repo-facts}.md`.

## Global Constraints

- Work in `/home/benf/Projects/homelab/.worktrees/apps-homepage-one-source`, branch `docs/homepage-one-source`. Never push, open a PR or touch the cluster.
- Commits: `git -c user.name="Ben Faingold" -c user.email=benfaingold@gmail.com commit`, message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Never read or print SealedSecret ciphertext; read `encryptedData` key names only.
- Nothing under `services/` changes. `homepage/` never gets an `app.yaml`.
- Local Python: `PY=~/.cache/claude-homelab-live/venv/bin/python` (3.14, PyYAML 6.0.3). CI uses 3.15. Local helm: `PATH=~/.cache/claude-household-boundary/bin:$PATH`.
- Pin `PyYAML==6.0.3` in `scripts/homepage/requirements.txt`.
- The generator finds the repo as `ROOT = Path(__file__).resolve().parents[2]`; every function that touches files takes `repo: Path` so tests pass a temp dir.
- Errors: raise `CatalogError(message)`; the message starts with the catalog path of the offending entry, e.g. `tiles.sonarr.widgets[0]: ...`. The CLI prints it and exits 1.
- Audience values: `household`, `admin` (default), `household-only` (widgets, bookmarks, info only).
- Tile allowlist: `name, href, icon, description, siteMonitor, namespace, app, podSelector, proxmoxNode, proxmoxVMID` plus catalog-only `audience, source, monitorPath, override, widgets`. Bookmark allowlist: `name, abbr, href, icon, description, target, audience`. Group keys: `name, items, style, columns, icon, header, initiallyCollapsed, useEqualHeights`.
- Never emitted: `audience, source, override, ref, monitorPath`. `id` (the catalog key) is emitted first on every tile and bookmark.
- Page constants: household → ConfigMap `homepage-config`, dir `services/operations/homepage`, secrets `<dir>/manifests/templates/secrets.yaml`; admin → `homepage-admin-config`, `services/operations/homepage-admin`. Namespace `operations`.
- Data key order: admin `proxmox.yaml` first; then every `files/*` (sorted), `docker.yaml`, `custom.js`, `custom.css`, `kubernetes.yaml`, `settings.yaml`, `widgets.yaml`, `services.yaml`, `bookmarks.yaml`.
- Style in catalog and fixtures: block style only.

## Review Focus

1. Prettier rewriting `catalog.yaml` or pass-through YAML (double quotes, re-indented lists) must not change generated output. Test in Task 1.
2. A standalone placeholder dumps single-quoted; after Helm unescape the page must parse to the same data as the catalog. Test in Task 5.
3. Non-ASCII text (`·`, Hebrew, accents) must dump as UTF-8, and a second run must be byte-identical. Test in Task 5.
4. A `-ru` variant that sets neither `port` nor `serviceName` must take the base app's port and fall back to its own `name`. Test in Task 2.
5. Running the CLI from a directory other than the repo root must give the same result. Test in Task 5.

---

### Task 1: Loader and test scaffolding (rules 1-2)

**Files:**
- Create: `scripts/homepage/catalog.py`, `scripts/homepage/requirements.txt`, `scripts/homepage/tests/fixture.py`, `scripts/homepage/tests/test_load.py`

**Interfaces:**
- Produces: `class CatalogError(Exception)`; `class UniqueLoader(yaml.SafeLoader)`; `load_yaml(path: Path) -> Any` (returns `{}` for an empty file); `loads_yaml(text: str, where: str) -> Any`.
- Produces (tests): `fixture.make_repo(root: Path, catalog: dict | str, apps: dict[str, dict] = {}, sealed: dict[str, list[str]] = {}, pages: dict[str, dict[str, str]] = {}) -> Path`. It writes `templates/globals.yaml` (domains `public: starktastic.net`, `internal: internal.starktastic.net`, `media: benplus.app`), each `apps[rel]` as `<rel>/app.yaml`, a `manifests/templates/secrets.yaml` for both pages with `spec.encryptedData` holding `sealed.get(page, [])` names and dummy values, `homepage/catalog.yaml` (dumped dict or raw text), and `pages[page][name]` under `homepage/pages/<page>/`. Default pages give a minimal valid `settings.yaml` (`title: T`) and `custom.css` (empty). `fixture.MIN_CATALOG` is a valid one-tile catalog (tile `a`, `audience: household`, explicit href, placed on both pages in tab `Main`, group `G`). Tests import with `sys.path.insert(0, str(Path(__file__).resolve().parents[1]))`, as `scripts/storage/tests/test_nas_rpc.py:9-10` does.

- [ ] **Step 1: Write the failing tests** in `test_load.py`:
  - `test_rule01_duplicate_key`: `loads_yaml("a: 1\na: 2\n", "x")` raises `CatalogError` naming `a`. Merge keys `<<:` stay allowed.
  - `test_rule02_unquoted_truthy`: each of `k: yes`, `k: No`, `k: on`, `k: OFF` raises; `k: "yes"`, `k: true`, `k: yesterday` load.
  - `test_prettier_form_equal`: the same mapping written with single quotes and 2-space lists, and with double quotes and 4-space indented lists, loads equal.
- [ ] **Step 2: Run** `$PY -m unittest discover -s scripts/homepage/tests -v`. Expected: FAIL, `ModuleNotFoundError: catalog`.
- [ ] **Step 3: Implement** `UniqueLoader` as a `compose_mapping_node` override (copy the shape of `check-homepage-coverage.py:51-68`, skipping `tag:yaml.org,2002:merge`) plus a `compose_node` hook that rejects plain-style (`style is None`) scalars resolved as `tag:yaml.org,2002:bool` whose lowercased value is `yes`, `no`, `on` or `off`. Wrap `yaml.YAMLError` in `CatalogError(f"{where}: {err}")`. Write `requirements.txt` with `PyYAML==6.0.3`.
- [ ] **Step 4: Run** the same command. Expected: 3 tests OK.
- [ ] **Step 5: Commit** `feat(homepage): catalog loader with duplicate-key and truthy checks`.

### Task 2: Derivation from `source` (rules 3-4)

**Files:**
- Modify: `scripts/homepage/catalog.py`
- Create: `scripts/homepage/tests/test_derive.py`

**Interfaces:**
- Consumes: `load_yaml`, `CatalogError`.
- Produces: `derive(repo: Path, source: str) -> dict[str, str]` returning `href`, `siteMonitor` (no monitorPath), `namespace`, `app`; `resolve_tile(repo: Path, tid: str, tile: dict) -> dict` returning the tile with derived keys applied (explicit wins, `null` drops the key, `monitorPath` appended to the derived `siteMonitor`), catalog-only keys still present.

- [ ] **Step 1: Write the failing tests:**
  - `test_rule03_derive_basic`: app `services/media/sonarr` (`name: sonarr`, `namespace: media`, `ingress: {enabled: true, host: sonarr, port: 8989}`) gives `href == "https://sonarr.internal.starktastic.net"`, `siteMonitor == "http://sonarr.media:8989"`, `namespace == "media"`, `app == "sonarr"`.
  - `test_rule03_domain_and_service`: `domainType: media`, `serviceName: web`, no port, empty host gives `href == "https://benplus.app"` and `siteMonitor == "http://web.<ns>:80"`.
  - `test_rule03_variant_merge` (Review Focus 4): `services/media/sonarr-ru` with `baseApp: services/media/sonarr`, `name: sonarr-ru`, `ingress: {enabled: true, host: sonarr-ru}` gives `siteMonitor == "http://sonarr-ru.media:8989"` and `app == "sonarr-ru"`.
  - `test_rule04_explicit_equal_fails`: an explicit `href` equal to the derived one raises, naming the key.
  - `test_rule04_null_drops_and_explicit_wins`: `siteMonitor: null` removes the key; `app: grafana` replaces `app`; `monitorPath: /ping` gives `http://sonarr.media:8989/ping`.
  - `test_rule04_no_ingress_fails`: `source` on an app with `ingress.enabled: false` raises.
- [ ] **Step 2: Run** the test file. Expected: FAIL on missing `derive`.
- [ ] **Step 3: Implement** per spec rule 3: deep-merge `<baseApp>/app.yaml` under the variant (mappings merge recursively, the variant wins), defaults `domainType: internal`, `port: 80`, `host: ""`, service `ingress.serviceName or name`, fqdn `domain if not host else f"{host}.{domain}"` with domains from `templates/globals.yaml` `global.domains`. `namespace` is the variant's app.yaml `namespace`.
- [ ] **Step 4: Run.** Expected: 6 OK, Task 1 tests still OK.
- [ ] **Step 5: Commit** `feat(homepage): derive href, siteMonitor and namespace/app from app.yaml`.

### Task 3: Catalog validation and placement (rules 5-6, allowlists)

**Files:**
- Modify: `scripts/homepage/catalog.py`
- Create: `scripts/homepage/tests/test_catalog.py`

**Interfaces:**
- Consumes: `load_yaml`, `resolve_tile`.
- Produces: `load_catalog(repo: Path) -> dict` with keys `tiles` (resolved), `bookmarks`, `info`, `pages`; `audience(entry: dict) -> str`; `shown_on(aud: str, page: str) -> bool` (`household` → both, `admin` → admin, `household-only` → household); `slug(tab: str) -> str` (`name.replace` of `\s+` with `-`, lowercased, then `urllib.parse.quote(..., safe="")`); `walk_groups(page: dict) -> Iterator[tuple[str, dict, list[str]]]` yielding `(tab_name, group, parent_names)` in order, subgroups after their parent's position in `items`.

- [ ] **Step 1: Write the failing tests:**
  - `test_rule05_tile_placement`: a `household` tile missing from household raises; placed twice on admin raises; an `admin` tile on household raises.
  - `test_rule05_bookmark_audiences`: a `household-only` bookmark placed only on household loads; the same bookmark on admin raises; an `admin` bookmark on household raises.
  - `test_rule05_tile_household_only_rejected`: `audience: household-only` on a tile raises.
  - `test_rule06_unique_names_after_override`: two tiles whose household names collide after `override.household.name` raise on household only.
  - `test_rule06_unknown_id`: an `items` id with no tile or bookmark raises.
  - `test_rule06_ids_disjoint`: a tile and a bookmark sharing an id raises. Name uniqueness is case-sensitive (admin has tile `Apps` and bookmark `apps`).
  - `test_rule06_tab_names_and_slug`: `slug("Pulse") == "pulse"`, `slug("Home Lab") == "home-lab"`; a tab named `Café` raises (pattern `[A-Za-z0-9 ]+`); duplicate group names on one page raise, across nesting levels too.
  - `test_allowlists`: an unknown tile key, unknown bookmark key, unknown group key, `override.household.audience` and `override.admin.widgets` each raise; a group mixing a tile and a bookmark raises; flow-style YAML is not tested (yamllint owns it).
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement** `load_catalog` and helpers. Apply `override.<page>` before name checks. A subgroup in `items` is a mapping with `name` and `items`.
- [ ] **Step 4: Run.** Expected: all OK.
- [ ] **Step 5: Commit** `feat(homepage): validate catalog audiences, placement and keys`.

### Task 4: Page build (rules 7-15, pass-through)

**Files:**
- Create: `scripts/homepage/render.py`, `scripts/homepage/tests/test_render.py`

**Interfaces:**
- Consumes: `load_catalog`, `shown_on`, `slug`, `walk_groups`, `load_yaml`.
- Produces: `PAGES: dict[str, dict[str, str]]` (Global Constraints values, keys `configmap`, `dir`); `build_page(repo: Path, cat: dict, page: str) -> dict[str, Any]` mapping data key → parsed object (YAML keys) or `str` (CSS, `files/*`, `custom.js`, `docker.yaml`), in the Global Constraints order.

- [ ] **Step 1: Write the failing tests:**
  - `test_rule07_widget_forms`: one matching widget emits `widget:`; two emit `widgets:`; none emits neither; a `household-only` widget is absent on admin.
  - `test_rule08_calendar_ref`: `{ref: sonarr, color: blue}` on admin becomes `{type: sonarr, service_group: <sonarr's immediate group>, service_name: <sonarr's admin name>, color: blue}`; a ref to a tile not on that page raises; a target with two widgets on that page raises; `integrations` not a list raises.
  - `test_rule09_layout_and_pwa`: `settings.yaml.layout` lists groups in order with `tab`; a subgroup nests under its parent without `tab`; no layout value is `None`; `pwa.shortcuts == [{"name": "Pulse", "url": "/#pulse"}, ...]` merged into a pass-through `pwa: {icons: [...]}` that keeps `icons`.
  - `test_rule10_css_data_name`: `custom.css` with `data-name="Nope"` raises; `data-name="Calendar"` with a Calendar tile on that page passes.
  - `test_rule11_to_14_generator_owned`: household `hideErrors is True`, admin `False`; `kubernetes.yaml == {"mode": "disabled"}` / `{"mode": "cluster"}`; `docker.yaml == ""`, `custom.js == ""`; pass-through `settings.yaml` containing `hideErrors`, `layout` or `pwa.shortcuts` raises; a `homepage/pages/<page>/custom.js` file raises.
  - `test_rule15_household_admin_keys`: a household tile with explicit `namespace`, `app`, `podSelector` and `proxmoxNode` emits them on admin and none of them on household.
  - `test_passthrough_files`: `files/favicon.svg` appears verbatim as data key `favicon.svg`; admin `proxmox.yaml` is parsed and re-dumped (comments dropped); household has no `proxmox.yaml` key; info entries filter by audience and keep list order; bookmarks emit as `[{Group: [{Name: [{id, abbr, href}]}]}]` and services as `[{Group: [{Name: {id, ...}}]}]` with `id` first and `widget`/`widgets` last.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement** `build_page`. Settings key order: pass-through keys as written except `pwa`, then `hideErrors`, then `pwa` (its pass-through keys in order, then `shortcuts`), then `layout`. `proxmox.yaml` is optional: absent means no data key.
- [ ] **Step 4: Run.** Expected: all OK.
- [ ] **Step 5: Commit** `feat(homepage): build page data from the catalog`.

### Task 5: Output, placeholders and CLI (rules 16-19, `--check`, `--inventory`)

**Files:**
- Modify: `scripts/homepage/render.py`
- Create: `scripts/homepage/generate.py`, `scripts/homepage/tests/test_output.py`

**Interfaces:**
- Consumes: `build_page`, `PAGES`, `load_catalog`.
- Produces: `dump_page(page: str, data: dict) -> str` (unescaped ConfigMap text); `check_placeholders(repo: Path, page: str, text: str) -> None`; `helm_escape(text: str) -> str`; in `generate.py`: `STAGED = {"household", "admin"}`, `output_path(repo: Path, page: str) -> Path` (`homepage/staged/<dir>/manifests/templates/configmap.yaml` while staged, else `<dir>/manifests/templates/configmap.yaml`), `render_all(repo: Path) -> dict[Path, str]`, `inventory(repo: Path) -> dict`, `main(argv: list[str] | None = None, repo: Path = ROOT) -> int`.

- [ ] **Step 1: Write the failing tests:**
  - `test_rule16_braces`: a tile description containing `{{ x }}` raises; `}}` alone raises; CSS `a { b }` and `pull/{number}` pass.
  - `test_rule17_sealed_names_both_ways`: referenced `HOMEPAGE_VAR_A` not sealed raises; sealed `HOMEPAGE_VAR_B` not referenced raises; a name used only in pass-through `settings.yaml` counts as referenced.
  - `test_rule18_wrapper`: output starts with `# Generated by scripts/homepage/generate.py from homepage/catalog.yaml. Do not edit.\napiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: homepage-config\n  namespace: operations\ndata:\n`; empty values are `  docker.yaml: ""`; others are `  <key>: |` with the body indented 4 and ending in one newline; a second run is byte-identical; `·` stays a literal character (Review Focus 3).
  - `test_rule19_escape_roundtrip` (Review Focus 2): `helm_escape` turns `{{HOMEPAGE_VAR_X}}` into `{{ "{{" }}HOMEPAGE_VAR_X{{ "}}" }}`; replacing those back and parsing each data key gives the same objects `build_page` produced, for a standalone placeholder and one inside a URL.
  - `test_check_and_write`: `main([], repo)` writes the staged files; `main(["--check"], repo)` returns 0; after editing a description it returns 1 and prints `python3 scripts/homepage/generate.py`.
  - `test_cwd_independent` (Review Focus 5): `main(["--check"], repo)` from `os.chdir(tempdir)` returns 0.
  - `test_inventory`: `inventory(repo)["household"]` has `tabs` (name and slug), `groups`, `tiles` (`id`, `name`, `group`, `href`, `widgets` types, `urls` fetched by widgets, `highlight`, `refreshInterval`), `bookmarks`, `info`.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.** Dump each YAML value with `yaml.dump(v, Dumper=NoAliasDumper, sort_keys=False, allow_unicode=True, width=float("inf"), default_flow_style=False)`, where `class NoAliasDumper(yaml.SafeDumper)` has `ignore_aliases` returning True (`yaml.safe_dump` rejects a `Dumper` argument). Build the wrapper as text, not with PyYAML: header and fixed metadata, then per key `f"  {k}: |\n" + textwrap.indent(body, "    ")`, or `f'  {k}: ""\n'` when the body is empty. Normalise CSS and file values to end with exactly one `\n`. Run `check_placeholders` on the unescaped text, then `helm_escape` with one `re.sub(r"\{\{(HOMEPAGE_VAR_[A-Z0-9_]+)\}\}", ...)`. Sealed names come from `<dir>/manifests/templates/secrets.yaml` `spec.encryptedData` keys; a missing file raises `CatalogError`. `--check`, `--inventory` and `--compare` are mutually exclusive (`argparse`); `--inventory` prints `json.dumps(..., indent=2, ensure_ascii=False)`.
- [ ] **Step 4: Run** all tests. Expected: all OK.
- [ ] **Step 5: Commit** `feat(homepage): write, check and inventory generated pages`.

### Task 6: `--compare`

**Files:**
- Create: `scripts/homepage/compare.py`, `scripts/homepage/tests/test_compare.py`
- Modify: `scripts/homepage/generate.py` (wire `--compare`)

**Interfaces:**
- Consumes: `UniqueLoader`, `PAGES`. compare.py never imports generate.py: `generate.main` reads the live and staged texts via `output_path` and calls `compare.diff(compare.facts(compare.parse_configmap(live)), compare.facts(compare.parse_configmap(staged)))`.
- Produces: `parse_configmap(text: str) -> dict[str, Any]` (undo `{{ "{{" }}`/`{{ "}}" }}`, replace `{{HOMEPAGE_VAR_X}}` with `HOMEPAGE_VAR_X`, parse the ConfigMap, then parse each `*.yaml` data key); `facts(data: dict) -> dict`; `diff(live: dict, staged: dict) -> list[str]`.

- [ ] **Step 1: Write the failing tests** with two small hand-written ConfigMap texts:
  - `test_equal_ignores_ids_quotes_anchors`: pages differing only in `id`, quoting, comments and an anchor/alias give `diff == []`.
  - `test_detects_each_fact`: changing in turn the tile set, a tile's tab, group, position, `href`, `siteMonitor`, `namespace`, `app`, `description`, widget type, a widget's placeholder names, a bookmark href, and an info widget type each gives one message naming the page and the tile or entry.
  - `test_cli_compare`: the test copies the staged output to `<dir>/manifests/templates/configmap.yaml` (expect `main(["--compare"], repo) == 0`), then edits one description in it (expect 1); only pages in `STAGED` are compared.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.** Facts per page: per tile name `(tab, group, index)`, `href`, `siteMonitor`, `namespace`, `app`, `description`, sorted widget types, sorted placeholder names per widget (placeholders are `HOMEPAGE_VAR_` tokens after stripping); bookmarks `name → href`; info widget types in order. Tabs come from `settings.yaml.layout`.
- [ ] **Step 4: Run** all tests. Expected: all OK.
- [ ] **Step 5: Commit** `feat(homepage): compare staged pages with the live ones`.

### Task 7: Catalog of today's pages (the proof content)

**Files:**
- Create: `homepage/catalog.yaml`, `homepage/pages/household/{settings.yaml,custom.css,files/favicon.svg}`, `homepage/pages/admin/{settings.yaml,custom.css,proxmox.yaml,files/favicon.svg}`, `homepage/staged/services/operations/homepage{,-admin}/manifests/templates/configmap.yaml` (generated)

**Interfaces:**
- Consumes: the CLI from Tasks 5-6.

- [ ] **Step 1: Draft with a throwaway converter** at `~/.cache/claude-homelab-live/onesource/convert.py` (never committed). It reads both live ConfigMaps with `compare.parse_configmap` and writes a draft catalog: tiles keyed by a kebab-case id of the admin name, one entry per tile across pages, groups and `items` per page in each page's own order, bookmarks, info, and pass-through files (settings without `hideErrors`, `layout` and `pwa.shortcuts`). Bookmark ids are `bm-<kebab name>`. `parse_configmap` strips placeholder braces, so the converter puts them back on every string with `re.sub(r"\bHOMEPAGE_VAR_[A-Z0-9_]+", r"{{\g<0>}}", s)` before writing.
- [ ] **Step 2: Hand-finish the catalog** to the spec §5 content list:
  - `audience: household` on the 21 shared tiles and on the logo, search, openmeteo and datetime info entries; both household bookmarks and the greeting `household-only`; kubernetes and stocks info admin (default).
  - `source:` on every derivable tile, deleting the values it derives; `monitorPath` on the nine tiles; the kube-prometheus-stack tiles per spec §5, with Prometheus also taking explicit `href: https://grafana.internal.starktastic.net/explore` and `siteMonitor: http://kube-prometheus-stack-prometheus.monitoring:9090/-/healthy`; explicit values for the rest of the spec §5 list.
  - `override.household.description` on Calendar, Seerr RU and MicroBin.
  - Widget variants per spec §5; admin calendar integrations as `ref:`.
  - The `&queue_depth` and `&github_prs` anchors restored at the places A:819 and A:1026 used them.
  - Placeholders always double-quoted; block style throughout.
- [ ] **Step 3: Generate and prove.** Run `$PY scripts/homepage/generate.py && $PY scripts/homepage/generate.py --check && $PY scripts/homepage/generate.py --compare`. Expected: exit 0 each; `--compare` prints nothing.
- [ ] **Step 4: Check counts.** Run `$PY scripts/homepage/generate.py --inventory` and count. Expected: household 21 tiles, 2 bookmarks, 3 tabs, 12 groups; admin 70 tiles, 10 bookmarks, 5 tabs, 26 groups. Check placeholders: 6/6 and 38/38 (rule 17 passed in Step 3).
- [ ] **Step 5: Lint.** Run `~/.cache/claude-homelab-live/venv/bin/yamllint -c .github/yamllint.yaml homepage/`. Expected: no output. Confirm `git status` shows no change under `services/`.
- [ ] **Step 6: Commit** `feat(homepage): catalog of today's pages, staged output`.

### Task 8: CI, ADR and docs

**Files:**
- Modify: `.github/workflows/validate-and-diff.yml` (insert after the "Check Jellyfin compatibility" step, `:81-82`), `docs/adr/README.md` (index row), `CLAUDE.md` (Commands, Gotchas)
- Create: `docs/adr/0019-homepage-catalog-generator.md`

- [ ] **Step 1: Add the two CI steps** exactly as spec §4 shows (three guards in the rehearsal, no admin-gate).
- [ ] **Step 2: Rehearse locally.** In a scratch copy (`T=$(mktemp -d -p /tmp/claude-1000) && cp -a . "$T/hp" && cp -r homepage/staged/services "$T/hp/"`), with the helm wrapper first on `PATH` and the venv Python, run `check-homepage-coverage.py`, `check-homepage-household.py` and `check-jellyfin-compat.py`. Expected: each exits 0. Record the wall time of the three; if over 3 minutes, note it in the PR body (spec risk 6).
- [ ] **Step 3: Write ADR 0019** from `docs/adr/template.md`: Status Accepted, Date 2026-11-13. Context: two hand-kept pages drift. Decision: spec §1-4 in short (catalog, audiences, generator-owned keys, staged until cut-over, `--check` in Validate). Rationale: Ben's four decisions. Consequences: double entry until cut-over; the guards stay independent; `custom.js` stays empty; sub-project 4 owns content and cut-over. Add the index row `| 0019 | [Homepage catalog generator](0019-homepage-catalog-generator.md) | Accepted |`.
- [ ] **Step 4: Add the CLAUDE.md lines.** Commands: `python3 scripts/homepage/generate.py [--check|--compare|--inventory]   # PyYAML: pages from homepage/catalog.yaml (ADR 0019)`. Gotchas: `Homepage pages come from homepage/catalog.yaml (ADR 0019). Until a page is cut over, change its live ConfigMap and the catalog together: --compare fails CI otherwise.`
- [ ] **Step 5: Verify all.** Run the unit tests, `--check`, `--compare`, yamllint on the repo (`YAMLLINT_CONFIG_FILE=.github/yamllint.yaml yamllint .` via the venv) and `python3 scripts/check-readme-images.py`. Expected: all pass. Confirm `git diff --name-only origin/main...` matches neither the diff gate (`validate-and-diff.yml:11`) nor the watch pattern (`cluster-apps.yaml:79`), so the preview is empty (acceptance 6).
- [ ] **Step 6: Commit** `ci(homepage): check generated pages and rehearse the staged ones` and `docs(adr): 0019 Homepage catalog generator`.

The PR (only when Ben asks) lists the `--inventory` counts and the rehearsal time in its body.
