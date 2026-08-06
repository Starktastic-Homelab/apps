# Homepage Dashboard Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite both Homepage ConfigMaps around intent-verb sections, cover every ingress and every headless workload, add every applicable widget, and add a CI check that keeps the dashboards honest.

**Architecture:** Both dashboards are plain ConfigMaps rendered by a Helm chart under `services/operations/homepage{,-admin}/manifests`. The redesign is entirely a data change to `configmap.yaml` plus new `SealedSecret` keys. A new `scripts/check-homepage-coverage.py` reads the cluster's real ingress inventory from `app.yaml` files, the `infrastructure/configs` chart and standalone IngressRoute manifests, then renders both Homepage charts and asserts every host appears on the admin dashboard, every public host appears on the user dashboard, and no internal host leaks onto the user dashboard. That script is written first and acts as the failing test the remaining tasks progressively satisfy.

**Tech Stack:** Kubernetes, Helm 3, Argo CD, Sealed Secrets, Traefik IngressRoute, gethomepage/homepage v1.13.2, Python 3 + PyYAML, GitHub Actions.

## Global Constraints

- Homepage version is pinned to **v1.13.2**. Only widgets and settings keys that exist in that release may be used.
- Both ConfigMaps are Helm templates. Every literal `{{` that Homepage must see at runtime is escaped as `{{ "{{" }}` and every literal `}}` as `{{ "}}" }}`. A Homepage variable therefore reads `{{ "{{" }}HOMEPAGE_VAR_NAME{{ "}}" }}`.
- Secrets are **never** written in plaintext. New values are sealed with `./scripts/seal.sh` and pasted into the existing `SealedSecret` under `spec.encryptedData`.
- Service icons must be a real file in `homarr-labs/dashboard-icons` (referenced as `name.png`) or a real Material Design icon (referenced as `mdi-name`). Verified fallbacks are listed in the File Structure section.
- In-cluster URLs always use the form `http://<service>.<namespace>.svc.cluster.local:<port>`. They are used for `widget.url` and `siteMonitor`; the public FQDN is used for `href`.
- `columns` for a layout section equals the number of services in that section, capped at **4** on the admin instance and **3** on the user instance, with a floor of **2**.
- Every **self-hosted** service on the **user** instance that has an `href` must also have a `siteMonitor`, so it shows a status dot under `statusStyle: dot`. Purely external destinations (for example the Hacker News tile) are exempt: health-polling a third-party site would generate pointless outbound traffic, so they intentionally show no dot.
- The user instance must contain **no** `*.internal.starktastic.net` URL anywhere, including `siteMonitor` and `widget.url`. Its `kubernetes.yaml` stays `mode: disabled`.
- Section names are globally unique within one instance's `layout`.
- Repeated widget blocks are shared with **YAML anchors** rather than copied. Homepage v1.13.2 parses with `js-yaml` v4 and the coverage script uses PyYAML; both resolve anchors, aliases and `<<:` merge keys. An anchor must be defined before its first alias in document order, so transcribe anchored blocks verbatim and do not reorder the services around them. `<<:` merges only top-level keys, so a nested map that differs per service (such as `mappings`) is restated in full.
- Domains come from `templates/globals.yaml`: public `starktastic.net`, internal `internal.starktastic.net`, media `benplus.app`.
- Every task ends with a commit. Commit messages follow Conventional Commits and include the trailers:

  ```
  Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
  Copilot-Session: 14065d41-0039-4ae2-a1f0-d2e6eedddd0b
  ```

## File Structure

| Path | Responsibility |
| --- | --- |
| `scripts/check-homepage-coverage.py` | **New.** Cross-checks the ingress inventory against both rendered dashboards. Also proves the embedded YAML parses. |
| `services/operations/homepage-admin/manifests/templates/configmap.yaml` | **Rewritten.** Admin dashboard: five tabs, all 47 hosts, all headless workloads, PromQL cards. |
| `services/operations/homepage-admin/manifests/templates/secrets.yaml` | **Modified.** Adds up to seven `HOMEPAGE_VAR_*` keys. |
| `services/operations/homepage/manifests/templates/configmap.yaml` | **Rewritten.** User dashboard: three tabs, public hosts only, status dots. |
| `services/operations/homepage/manifests/templates/secrets.yaml` | **Modified.** Adds `HOMEPAGE_VAR_HASS_KEY`. |
| `.github/workflows/validate-and-diff.yml` | **Modified.** Runs the coverage script in the existing `validate` job. |

Verified icon names used below. Anything not in this table must be checked against `https://github.com/homarr-labs/dashboard-icons/tree/main/png` before use.

| Service | Icon | Service | Icon |
| --- | --- | --- | --- |
| Argo CD | `argo-cd.png` | Changedetection | `changedetection.png` |
| Falco | `mdi-shield-search` | Intel Device Operator | `mdi-chip` |
| NFS provisioner | `mdi-nas` | Sealed Secrets | `mdi-lock-check` |
| Subgen | `mdi-subtitles` | Lingarr | `mdi-translate` |
| Cineplete | `mdi-movie-open-check` | Shelfmark | `mdi-bookshelf` |
| News | `mdi-newspaper-variant` | Calendar | `mdi-calendar-month` |
| PostgreSQL | `postgres.png` | Redis | `redis.png` |

> `argocd.png` and `changedetection-io.png` are used by the current config and **do not exist**. The rewrite must use `argo-cd.png` and `changedetection.png`.

---

### Task 1: Coverage check script

The script is written before any dashboard change so that it starts red on a real, known gap (Falco has an ingress and is on neither dashboard) and turns green as the later tasks land.

**Files:**
- Create: `scripts/check-homepage-coverage.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `python3 scripts/check-homepage-coverage.py`, run from the repository root. Exits `0` when both dashboards are consistent with the ingress inventory, `1` otherwise, printing one line per problem. Task 8 wires it into CI; Tasks 4-7 use it as their acceptance test.

- [ ] **Step 1: Confirm the tools the script needs are present**

Run:

```bash
python3 -c "import yaml; print(yaml.__version__)" && helm version --short
```

Expected: a PyYAML version (e.g. `6.0.1`) and a Helm v3 version (e.g. `v3.16.2+g...`). If PyYAML is missing, install it with `pip install --user pyyaml`.

- [ ] **Step 2: Write the script**

Create `scripts/check-homepage-coverage.py` with exactly this content:

```python
#!/usr/bin/env python3
"""Verify both Homepage dashboards list every service that has an ingress.

The two Homepage instances are configured by hand-written ConfigMaps. Nothing
otherwise connects a new service's IngressRoute to those ConfigMaps, so a
service can be deployed and reachable while remaining invisible on every
dashboard. This check closes that gap.

Hosts are discovered from three places, mirroring how the cluster actually
defines them:

  * ``app.yaml`` files consumed by ``templates/ingress-chart`` (the common case,
    including variants that inherit ``domainType`` from a ``baseApp``)
  * the ``infrastructure/configs`` chart, which templates its hostnames through
    ``templates/globals.yaml``
  * standalone IngressRoute manifests that hard-code a ``Host()`` rule

Dashboard coverage is read by rendering each Homepage manifests chart and
walking the embedded ``services.yaml`` and ``bookmarks.yaml`` for ``href``
values. Rendering also proves the embedded YAML still parses, which is easy to
break because it is YAML nested inside a Helm-escaped ConfigMap.

Run with no arguments from the repository root.
"""

from __future__ import annotations

import glob
import re
import subprocess
import sys

import yaml

GLOBALS = "templates/globals.yaml"
CONFIGS_CHART = "infrastructure/configs"
DASHBOARDS = {
    "admin": "services/operations/homepage-admin/manifests",
    "user": "services/operations/homepage/manifests",
}

# Neither dashboard lists itself as a service.
EXCLUDED_HOSTS = {"starktastic.net", "admin.starktastic.net"}

HOST_RE = re.compile(r"Host\(`([^`]+)`\)")
VAR_RE = re.compile(r"\{\{HOMEPAGE_VAR_[A-Z0-9_]+\}\}")


def load_yaml(path: str) -> dict:
    with open(path) as handle:
        return yaml.safe_load(handle) or {}


def domains() -> dict[str, str]:
    return load_yaml(GLOBALS)["global"]["domains"]


def fqdn(host: str, domain_type: str, doms: dict[str, str]) -> str:
    domain = doms[domain_type]
    return domain if not host else f"{host}.{domain}"


def app_yaml_hosts(doms: dict[str, str]) -> dict[str, str]:
    """Map FQDN -> app.yaml path for every ingress-enabled app."""
    apps = {}
    for path in glob.glob("services/*/*/app.yaml") + glob.glob("infrastructure/*/*/app.yaml"):
        apps[path] = load_yaml(path)

    found = {}
    for path, app in apps.items():
        ingress = app.get("ingress") or {}
        if not ingress.get("enabled"):
            continue
        domain_type = ingress.get("domainType")
        if domain_type is None:
            # Variants (e.g. radarr-ru) inherit every ingress field but `host`
            # from the app they are based on.
            base = app.get("baseApp")
            base_ingress = (apps.get(f"{base}/app.yaml") or {}).get("ingress") or {}
            domain_type = base_ingress.get("domainType", "internal")
        found[fqdn(ingress.get("host", ""), domain_type, doms)] = path
    return found


def rendered_hosts() -> dict[str, str]:
    """Hostnames templated by the infrastructure/configs chart."""
    out = subprocess.run(
        ["helm", "template", "configs", CONFIGS_CHART, "-f", GLOBALS],
        capture_output=True, text=True, check=True,
    ).stdout
    return {host: CONFIGS_CHART for host in HOST_RE.findall(out)}


def static_hosts() -> dict[str, str]:
    """Hostnames hard-coded in standalone IngressRoute manifests."""
    found = {}
    for path in glob.glob("services/*/*/manifests/**/*.yaml", recursive=True) + glob.glob(
        "infrastructure/*/*/manifests/**/*.yaml", recursive=True
    ):
        with open(path) as handle:
            text = handle.read()
        if "IngressRoute" not in text:
            continue
        for host in HOST_RE.findall(text):
            if "{{" not in host:
                found[host] = path
    return found


def hrefs(node) -> list[str]:
    """Every href value anywhere in a parsed services.yaml or bookmarks.yaml."""
    if isinstance(node, dict):
        out = []
        for key, value in node.items():
            if key == "href" and isinstance(value, str):
                out.append(value)
            else:
                out.extend(hrefs(value))
        return out
    if isinstance(node, list):
        return [href for item in node for href in hrefs(item)]
    return []


def dashboard_hosts(chart: str) -> set[str]:
    """Render a Homepage chart and collect every host it links to.

    Also asserts that the embedded YAML parses; a syntax error here fails the
    check rather than silently shipping a blank dashboard.
    """
    out = subprocess.run(
        ["helm", "template", "homepage", chart],
        capture_output=True, text=True, check=True,
    ).stdout

    hosts: set[str] = set()
    for doc in yaml.safe_load_all(out):
        if not doc or doc.get("kind") != "ConfigMap":
            continue
        for name, body in (doc.get("data") or {}).items():
            if not name.endswith(".yaml") or not body.strip():
                continue
            parsed = yaml.safe_load(VAR_RE.sub("x", body))
            if name in ("services.yaml", "bookmarks.yaml"):
                for href in hrefs(parsed):
                    match = re.match(r"https?://([^/]+)", href)
                    if match:
                        hosts.add(match.group(1))
    return hosts


def main() -> int:
    doms = domains()
    internal = doms["internal"]

    all_hosts = {**app_yaml_hosts(doms), **rendered_hosts(), **static_hosts()}
    all_hosts = {h: src for h, src in all_hosts.items() if h not in EXCLUDED_HOSTS}

    admin = dashboard_hosts(DASHBOARDS["admin"])
    user = dashboard_hosts(DASHBOARDS["user"])

    failures: list[str] = []

    for host, source in sorted(all_hosts.items()):
        if host not in admin:
            failures.append(f"missing from admin dashboard: {host}  ({source})")

    for host, source in sorted(all_hosts.items()):
        if host.endswith(internal):
            continue
        if host not in user:
            failures.append(f"missing from user dashboard: {host}  ({source})")

    for host in sorted(user):
        if host.endswith(internal):
            failures.append(f"internal host leaked onto user dashboard: {host}")

    if failures:
        print(f"Homepage coverage check FAILED ({len(failures)} problems)\n")
        for failure in failures:
            print(f"  {failure}")
        return 1

    print(f"Homepage coverage OK: {len(all_hosts)} hosts, both dashboards consistent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Run it and confirm it fails on the one real gap**

Run: `python3 scripts/check-homepage-coverage.py; echo "exit=$?"`

Expected, exactly:

```
Homepage coverage check FAILED (1 problems)

  missing from admin dashboard: falco.internal.starktastic.net  (infrastructure/system/falco/manifests/ingressroute.yaml)
exit=1
```

If the output lists more or fewer hosts, the discovery logic is wrong — stop and fix the script, do not adjust the dashboards to match.

- [ ] **Step 4: Confirm the leak detector works**

Temporarily break the user dashboard so the third failure class fires:

```bash
sed -i 's|href: https://microbin.starktastic.net|href: https://microbin.internal.starktastic.net|' \
  services/operations/homepage/manifests/templates/configmap.yaml
python3 scripts/check-homepage-coverage.py; echo "exit=$?"
```

Expected: 3 problems — `missing from admin`, `missing from user dashboard: microbin.starktastic.net`, and `internal host leaked onto user dashboard: microbin.internal.starktastic.net`.

Revert it:

```bash
git checkout -- services/operations/homepage/manifests/templates/configmap.yaml
python3 scripts/check-homepage-coverage.py; echo "exit=$?"
```

Expected: back to 1 problem, `exit=1`.

- [ ] **Step 5: Make it executable and lint it**

```bash
chmod +x scripts/check-homepage-coverage.py
python3 -m py_compile scripts/check-homepage-coverage.py && echo "compiles"
```

Expected: `compiles`.

- [ ] **Step 6: Commit**

```bash
git add scripts/check-homepage-coverage.py
git commit -m "$(cat <<'MSG'
feat(homepage): add dashboard coverage check script

Cross-references every ingress host against both rendered Homepage
dashboards so a newly deployed service cannot stay invisible. Currently
fails on falco.internal.starktastic.net, which is on neither dashboard.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
Copilot-Session: 14065d41-0039-4ae2-a1f0-d2e6eedddd0b
MSG
)"
```

---

### Task 2: Seal the new Homepage secrets

> **Owner-operated — not executed by an implementer subagent.** These values require interactive logins to ntfy, Finnhub, Dispatcharr and Filebrowser that only the repository owner can perform, so this task is done by hand before the branch merges. Tasks 3-7 still reference the variable names below as planned. Nothing validates `HOMEPAGE_VAR_*` against `spec.encryptedData`, so the branch builds and CI passes without this task; until it is done the seven affected widgets render without credentials and fail closed, and the rest of both dashboards is unaffected.

**Files:**
- Modify: `services/operations/homepage-admin/manifests/templates/secrets.yaml`
- Modify: `services/operations/homepage/manifests/templates/secrets.yaml`

**Interfaces:**
- Consumes: nothing.
- Produces: the following `HOMEPAGE_VAR_*` names, referenced by Tasks 3-7 as `{{ "{{" }}NAME{{ "}}" }}`:
  - admin: `HOMEPAGE_VAR_NTFY_TOKEN`, `HOMEPAGE_VAR_FINNHUB_KEY`, `HOMEPAGE_VAR_DISPATCHARR_USER`, `HOMEPAGE_VAR_DISPATCHARR_PASS`, `HOMEPAGE_VAR_FILEBROWSER_USER`, `HOMEPAGE_VAR_FILEBROWSER_PASS`
  - user: `HOMEPAGE_VAR_HASS_KEY`

`HOMEPAGE_VAR_CROWDSEC_USER` / `_PASS` are deliberately **not** part of this task. The CrowdSec LAPI in this cluster runs TLS-only and rejects password auth (see the comment in `infrastructure/system/crowdsec/values.yaml`), so the `crowdsec` widget is expected to be unusable. CrowdSec is covered by the PromQL *Security* card in Task 4 instead.

- [ ] **Step 1: Gather the six admin values**

These come from the running services, not from this repository:

| Variable | Where to get it |
| --- | --- |
| `HOMEPAGE_VAR_NTFY_TOKEN` | `https://ntfy.starktastic.net` → account → access tokens → create a token with read access to the `alerts` topic. Starts with `tk_`. |
| `HOMEPAGE_VAR_FINNHUB_KEY` | Free API key from `https://finnhub.io/register`. |
| `HOMEPAGE_VAR_DISPATCHARR_USER` / `_PASS` | Dispatcharr login at `https://dispatcharr.internal.starktastic.net`. |
| `HOMEPAGE_VAR_FILEBROWSER_USER` / `_PASS` | Filebrowser login at `https://files.internal.starktastic.net`. |

- [ ] **Step 2: Seal the admin values**

`scripts/seal.sh` reads `KEY=VALUE` lines on stdin, uses `kubectl --dry-run=client` and `kubeseal --cert`, so it works without cluster access. Run from the repository root and press `Ctrl+D` after the last line:

```bash
./scripts/seal.sh homepage-admin-secrets operations
```

Type (substituting real values):

```
HOMEPAGE_VAR_NTFY_TOKEN=tk_replace_me
HOMEPAGE_VAR_FINNHUB_KEY=replace_me
HOMEPAGE_VAR_DISPATCHARR_USER=replace_me
HOMEPAGE_VAR_DISPATCHARR_PASS=replace_me
HOMEPAGE_VAR_FILEBROWSER_USER=replace_me
HOMEPAGE_VAR_FILEBROWSER_PASS=replace_me
```

Expected: `✅ Done! Saved homepage-admin-secrets.yaml` in the current directory.

- [ ] **Step 3: Merge the six ciphertexts into the existing SealedSecret**

`homepage-admin-secrets.yaml` is a complete SealedSecret containing only the new keys. Copy the six `spec.encryptedData` lines out of it and paste them into the existing block in `services/operations/homepage-admin/manifests/templates/secrets.yaml`, keeping the existing keys. Do **not** replace the file — it holds 36 other keys.

```bash
sed -n '/encryptedData/,/^  template:/p' homepage-admin-secrets.yaml | grep '^    HOMEPAGE_VAR_'
```

Paste that output immediately after the `  encryptedData:` line in `services/operations/homepage-admin/manifests/templates/secrets.yaml`.

- [ ] **Step 4: Seal and merge the user value**

```bash
./scripts/seal.sh homepage-secrets operations
```

Type:

```
HOMEPAGE_VAR_HASS_KEY=replace_me
```

The Home Assistant long-lived access token is created at `https://ha.internal.starktastic.net` → profile → security → long-lived access tokens. Use a **separate** token from the admin instance's so it can be revoked independently.

Then merge its single `HOMEPAGE_VAR_HASS_KEY` line into `services/operations/homepage/manifests/templates/secrets.yaml`.

- [ ] **Step 5: Delete the scratch files and verify**

```bash
rm -f homepage-admin-secrets.yaml homepage-secrets.yaml
git status --short
```

Expected: only the two `secrets.yaml` files are modified; no stray `*-secrets.yaml` in the repository root.

- [ ] **Step 6: Verify both files still render and contain the new keys**

```bash
helm template hp services/operations/homepage-admin/manifests | grep -c 'HOMEPAGE_VAR_' && \
helm template hp services/operations/homepage/manifests | grep -c 'HOMEPAGE_VAR_'
```

Expected: the admin count is 6 higher than before this task and the user count is 1 higher.

```bash
grep -c 'HOMEPAGE_VAR_' services/operations/homepage-admin/manifests/templates/secrets.yaml
```

Expected: `42` (36 existing + 6 new).

```bash
grep -c 'HOMEPAGE_VAR_' services/operations/homepage/manifests/templates/secrets.yaml
```

Expected: `19` (18 existing + 1 new).

- [ ] **Step 7: Commit**

```bash
git add services/operations/homepage-admin/manifests/templates/secrets.yaml \
        services/operations/homepage/manifests/templates/secrets.yaml
git commit -m "$(cat <<'MSG'
feat(homepage): seal secrets for new dashboard widgets

Adds ntfy, Finnhub, Dispatcharr and Filebrowser credentials to the admin
instance and a dedicated Home Assistant token to the user instance.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
Copilot-Session: 14065d41-0039-4ae2-a1f0-d2e6eedddd0b
MSG
)"
```

---

### Task 3: Admin settings and header widgets

Rewrites the `settings.yaml` and `widgets.yaml` keys of the admin ConfigMap. After this task the dashboard renders five empty tabs; `services.yaml` is replaced in Tasks 4-6.

**Files:**
- Modify: `services/operations/homepage-admin/manifests/templates/configmap.yaml`

**Interfaces:**
- Consumes: `HOMEPAGE_VAR_FINNHUB_KEY` from Task 2.
- Produces: the admin `layout` section names that Tasks 4-6 must match **exactly**, in this order — `At a Glance`, `In Flight`, `Coming Up`, `Out There`, `Watch`, `Listen`, `Read`, `Look Back`, `Ask For It`, `Create`, `Convert`, `Find`, `Organise`, `Send`, `Acquire`, `Refine`, `Home`, `Observe`, `Guard`, `Ship`, `Compute`, `Network`, `Storage`, `Data`. A group in `services.yaml` whose name is not in this list renders in an untabbed section at the bottom of every tab.

- [ ] **Step 1: Replace the `settings.yaml` key**

In `services/operations/homepage-admin/manifests/templates/configmap.yaml`, replace everything from the line `  settings.yaml: |` up to (but not including) the line `  widgets.yaml: |` with:

```yaml
  settings.yaml: |
    title: Starktastic Services
    headerStyle: boxedWidgets
    statusStyle: dot
    useEqualHeights: true
    hideVersion: true
    hideErrors: false
    disableCollapse: false
    disableIndexing: true
    iconStyle: theme
    favicon: /icons/favicon.svg
    providers:
      finnhub: {{ "{{" }}HOMEPAGE_VAR_FINNHUB_KEY{{ "}}" }}
    quicklaunch:
      searchDescriptions: true
      hideInternetSearch: false
      showSearchSuggestions: false
      provider: custom
      url: https://search.starktastic.net/search?q=
    pwa:
      shortcuts:
        - name: Pulse
          url: "/#pulse"
        - name: Play
          url: "/#play"
        - name: Make
          url: "/#make"
        - name: Run
          url: "/#run"
        - name: Iron
          url: "/#iron"
    layout:
      # -- Pulse: is everything OK? --
      At a Glance:
        tab: Pulse
        style: row
        columns: 3
        icon: mdi-heart-pulse
      In Flight:
        tab: Pulse
        style: row
        columns: 4
        icon: mdi-airplane-takeoff
      Coming Up:
        tab: Pulse
        style: row
        columns: 3
        icon: mdi-calendar-month
      Out There:
        tab: Pulse
        style: row
        columns: 2
        icon: mdi-newspaper-variant
      # -- Play: consume something --
      Watch:
        tab: Play
        style: row
        columns: 4
        icon: jellyfin.png
      Listen:
        tab: Play
        style: row
        columns: 2
        icon: navidrome.png
      Read:
        tab: Play
        style: row
        columns: 2
        icon: calibre-web.png
      Look Back:
        tab: Play
        style: row
        columns: 2
        icon: immich.png
      Ask For It:
        tab: Play
        style: row
        columns: 3
        icon: overseerr.png
      # -- Make: produce something --
      Create:
        tab: Make
        style: row
        columns: 3
        icon: excalidraw.png
      Convert:
        tab: Make
        style: row
        columns: 4
        icon: convertx.png
      Find:
        tab: Make
        style: row
        columns: 3
        icon: searxng.png
      Organise:
        tab: Make
        style: row
        columns: 4
        icon: paperless-ngx.png
      Send:
        tab: Make
        style: row
        columns: 3
        icon: ntfy.png
      # -- Run: keep the machine fed --
      Acquire:
        tab: Run
        style: row
        columns: 4
        icon: radarr.png
      Refine:
        tab: Run
        style: row
        columns: 4
        icon: bazarr.png
      Home:
        tab: Run
        style: row
        columns: 3
        icon: home-assistant.png
      Observe:
        tab: Run
        style: row
        columns: 4
        icon: grafana.png
      Guard:
        tab: Run
        style: row
        columns: 4
        icon: authentik.png
      Ship:
        tab: Run
        style: row
        columns: 4
        icon: argo-cd.png
      # -- Iron: the metal underneath --
      Compute:
        tab: Iron
        style: row
        columns: 4
        icon: proxmox.png
      Network:
        tab: Iron
        style: row
        columns: 4
        icon: opnsense.png
      Storage:
        tab: Iron
        style: row
        columns: 2
        icon: truenas.png
      Data:
        tab: Iron
        style: row
        columns: 3
        icon: postgres.png
```

Note `hideErrors: false` — a broken PromQL query or an unreachable widget must be visible on the admin page during rollout. This is the opposite of the user instance.

- [ ] **Step 2: Replace the `widgets.yaml` key**

Replace everything from `  widgets.yaml: |` up to (but not including) `  services.yaml: |` with:

```yaml
  widgets.yaml: |
    - logo:
        icon: /icons/favicon.svg
    - kubernetes:
        cluster:
          show: true
          cpu: true
          memory: true
          showLabel: true
          label: "cluster"
        nodes:
          show: true
          cpu: true
          memory: true
          showLabel: true
    - search:
        provider: custom
        url: https://search.starktastic.net/search?q=
        target: _blank
    - openmeteo:
        label: Weather
        latitude: 32.08
        longitude: 34.78
        timezone: Asia/Jerusalem
        units: metric
    - stocks:
        provider: finnhub
        color: true
        cache: 5
        watchlist:
          - NVDA
          - AMD
          - INTC
          - MSFT
          - GOOGL
          - AAPL
          - TSM
    - datetime:
        text_size: xl
        format:
          dateStyle: long
          timeStyle: short
          hourCycle: h23
```

The `stocks` watchlist is capped at 8 entries by Homepage; seven are used. `cache: 5` keeps the free Finnhub tier well inside its rate limit.

- [ ] **Step 3: Verify the chart still renders and the YAML parses**

```bash
helm template hp services/operations/homepage-admin/manifests | python3 -c "
import re, sys, yaml
docs = [d for d in yaml.safe_load_all(sys.stdin) if d and d.get('kind') == 'ConfigMap']
for d in docs:
    for name, body in (d.get('data') or {}).items():
        if name.endswith('.yaml') and body.strip():
            yaml.safe_load(re.sub(r'\{\{HOMEPAGE_VAR_[A-Z0-9_]+\}\}', 'x', body))
            print('ok', name)
"
```

Expected: `ok` for each of `proxmox.yaml`, `kubernetes.yaml`, `settings.yaml`, `widgets.yaml`, `services.yaml`, `bookmarks.yaml`.

- [ ] **Step 4: Verify the tab names and the layout key count**

```bash
helm template hp services/operations/homepage-admin/manifests \
  | python3 -c "
import re, sys, yaml
for d in yaml.safe_load_all(sys.stdin):
    if d and d.get('kind') == 'ConfigMap':
        s = yaml.safe_load(re.sub(r'\{\{HOMEPAGE_VAR_[A-Z0-9_]+\}\}', 'x', d['data']['settings.yaml']))
        print(len(s['layout']), 'sections')
        print(sorted({v['tab'] for v in s['layout'].values()}))
"
```

Expected:

```
24 sections
['Iron', 'Make', 'Play', 'Pulse', 'Run']
```

- [ ] **Step 5: Lint**

```bash
yamllint services/operations/homepage-admin/manifests/templates/configmap.yaml || true
npx --yes prettier --check services/operations/homepage-admin/manifests/templates/configmap.yaml
```

`yamllint` reports Helm template syntax as errors on this file and is expected to complain; the CI workflow excludes it. Prettier must pass — if it does not, run `npx --yes prettier --write` on the file.

- [ ] **Step 6: Commit**

```bash
git add services/operations/homepage-admin/manifests/templates/configmap.yaml
git commit -m "$(cat <<'MSG'
feat(homepage-admin): restructure settings into five intent tabs

Replaces the Home/Media/Operations/Infrastructure tabs with
Pulse/Play/Make/Run/Iron, surfaces widget errors, and adds the stocks
header widget backed by Finnhub.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
Copilot-Session: 14065d41-0039-4ae2-a1f0-d2e6eedddd0b
MSG
)"
```

---

### Task 4: Admin services — Pulse and Play tabs

This task **replaces** the whole `services.yaml` key with just the Pulse and Play groups. Tasks 5 and 6 append to it. The dashboard is intentionally incomplete between tasks; the coverage script's failure list is the progress bar.

**Files:**
- Modify: `services/operations/homepage-admin/manifests/templates/configmap.yaml`

**Interfaces:**
- Consumes: layout section names from Task 3; `HOMEPAGE_VAR_NTFY_TOKEN` and `HOMEPAGE_VAR_DISPATCHARR_USER`/`_PASS` from Task 2.
- Produces: the `services.yaml` key, opened with the Pulse and Play groups. Task 5 appends `Create` onwards to the same key; Task 6 appends `Compute` onwards and rewrites `bookmarks.yaml`.

- [ ] **Step 1: Replace the `services.yaml` key**

Replace everything from `  services.yaml: |` up to (but not including) `  bookmarks.yaml: |` with the following. PromQL queries are single-quoted so the double quotes inside label matchers need no escaping.

```yaml
  services.yaml: |
    # ==================== PULSE ====================
    - At a Glance:
        - Cluster Health:
            icon: kubernetes.png
            href: https://grafana.internal.starktastic.net
            description: Nodes, pods, alerts, volumes
            widget:
              type: prometheusmetric
              url: http://kube-prometheus-stack-prometheus.monitoring.svc.cluster.local:9090
              refreshInterval: 30000
              metrics:
                - label: Nodes Ready
                  query: 'sum(kube_node_status_condition{condition="Ready",status="true"})'
                - label: Unhealthy Pods
                  query: 'sum(kube_pod_status_phase{phase=~"Pending|Failed|Unknown"}) or vector(0)'
                - label: Firing Alerts
                  query: 'sum(ALERTS{alertstate="firing"}) or vector(0)'
                - label: Fullest Volume
                  query: 'max(kubelet_volume_stats_used_bytes / kubelet_volume_stats_capacity_bytes)'
                  format:
                    type: percent
        - Edge & Certs:
            icon: traefik.png
            href: https://traefik.internal.starktastic.net
            description: Probes, certificates, traffic
            widget:
              type: prometheusmetric
              url: http://kube-prometheus-stack-prometheus.monitoring.svc.cluster.local:9090
              refreshInterval: 30000
              metrics:
                - label: Failed Probes
                  query: 'count(probe_success == 0) or vector(0)'
                - label: Cert Expiry
                  query: 'min(probe_ssl_earliest_cert_expiry) - time()'
                  format:
                    type: number
                    scale: "1/86400"
                    suffix: " days"
                    options:
                      maximumFractionDigits: 0
                - label: Requests
                  query: 'sum(rate(traefik_entrypoint_requests_total[5m]))'
                  format:
                    type: number
                    suffix: " req/s"
                    options:
                      maximumFractionDigits: 1
                - label: p95 Latency
                  query: 'histogram_quantile(0.95, sum by (le) (rate(traefik_entrypoint_request_duration_seconds_bucket[5m])))'
                  format:
                    type: number
                    scale: 1000
                    suffix: " ms"
                    options:
                      maximumFractionDigits: 0
        - Security:
            icon: crowdsec.png
            href: https://grafana.internal.starktastic.net
            description: Bans, detections, bad requests
            widget:
              type: prometheusmetric
              url: http://kube-prometheus-stack-prometheus.monitoring.svc.cluster.local:9090
              refreshInterval: 60000
              metrics:
                - label: Active Bans
                  query: 'sum(cs_active_decisions) or vector(0)'
                  format:
                    type: number
                    options:
                      maximumFractionDigits: 0
                - label: Falco 24h
                  query: 'sum(increase(falcosecurity_falcosidekick_falco_events_total[24h])) or vector(0)'
                  format:
                    type: number
                    options:
                      maximumFractionDigits: 0
                - label: 4xx/5xx 1h
                  query: 'sum(increase(traefik_entrypoint_requests_total{code=~"4..|5.."}[1h])) or vector(0)'
                  format:
                    type: number
                    options:
                      maximumFractionDigits: 0
    - In Flight:
        - Jellyfin:
            icon: jellyfin.png
            href: https://benplus.app
            description: Who is watching what
            siteMonitor: http://jellyfin-main.media.svc.cluster.local:8096
            widget:
              type: jellyfin
              url: http://jellyfin-main.media.svc.cluster.local:8096
              key: {{ "{{" }}HOMEPAGE_VAR_JELLYFIN_KEY{{ "}}" }}
              enableBlocks: false
              enableNowPlaying: true
              enableUser: true
              showEpisodeNumber: true
        - qBittorrent:
            icon: qbittorrent.png
            href: https://qbittorrent.internal.starktastic.net
            description: Active transfers
            siteMonitor: http://qbittorrent-main.media.svc.cluster.local:8080
            widget:
              type: qbittorrent
              url: http://qbittorrent-main.media.svc.cluster.local:8080
        - qBittorrent RU:
            icon: qbittorrent.png
            href: https://qbittorrent-ru.internal.starktastic.net
            description: Active transfers (RU)
            siteMonitor: http://qbittorrent-ru-main.media.svc.cluster.local:8080
            widget:
              type: qbittorrent
              url: http://qbittorrent-ru-main.media.svc.cluster.local:8080
        - Argo CD:
            icon: argo-cd.png
            href: https://argocd.internal.starktastic.net
            description: Sync and health of every app
            siteMonitor: https://argocd-server.argocd.svc.cluster.local:443
            widget:
              type: argocd
              url: https://argocd-server.argocd.svc.cluster.local:443
              key: {{ "{{" }}HOMEPAGE_VAR_ARGOCD_KEY{{ "}}" }}
        - ntfy:
            icon: ntfy.png
            href: https://ntfy.starktastic.net
            description: Latest alert
            siteMonitor: http://ntfy.operations.svc.cluster.local:80
            widget:
              type: ntfy
              url: http://ntfy.operations.svc.cluster.local:80
              topic: alerts
              key: {{ "{{" }}HOMEPAGE_VAR_NTFY_TOKEN{{ "}}" }}
    - Coming Up:
        - Calendar:
            widget:
              type: calendar
              view: monthly
              maxEvents: 15
              showTime: true
              integrations:
                - type: ical
                  url: http://sonarr.media.svc.cluster.local:8989/feed/v3/calendar/Sonarr.ics?apikey={{ "{{" }}HOMEPAGE_VAR_SONARR_KEY{{ "}}" }}
                  name: Sonarr
                  color: blue
                - type: ical
                  url: http://sonarr-ru.media.svc.cluster.local:8989/feed/v3/calendar/Sonarr.ics?apikey={{ "{{" }}HOMEPAGE_VAR_SONARR_RU_KEY{{ "}}" }}
                  name: Sonarr RU
                  color: sky
                - type: ical
                  url: http://radarr.media.svc.cluster.local:7878/feed/v3/calendar/Radarr.ics?apikey={{ "{{" }}HOMEPAGE_VAR_RADARR_KEY{{ "}}" }}
                  name: Radarr
                  color: red
                - type: ical
                  url: http://radarr-ru.media.svc.cluster.local:7878/feed/v3/calendar/Radarr.ics?apikey={{ "{{" }}HOMEPAGE_VAR_RADARR_RU_KEY{{ "}}" }}
                  name: Radarr RU
                  color: rose
                - type: ical
                  url: http://lidarr.media.svc.cluster.local:8686/feed/v1/calendar/Lidarr.ics?apikey={{ "{{" }}HOMEPAGE_VAR_LIDARR_KEY{{ "}}" }}
                  name: Lidarr
                  color: green
        - Vikunja:
            icon: vikunja.png
            href: https://vikunja.starktastic.net
            description: What is due
            siteMonitor: http://vikunja.operations.svc.cluster.local:3456
            widget:
              type: vikunja
              url: http://vikunja.operations.svc.cluster.local:3456
              key: {{ "{{" }}HOMEPAGE_VAR_VIKUNJA_KEY{{ "}}" }}
              enableTaskList: true
              version: 2
        - Mealie:
            icon: mealie.png
            href: https://mealie.starktastic.net
            description: Tonight's meal plan
            siteMonitor: http://mealie.operations.svc.cluster.local:9000
            widget:
              type: mealie
              url: http://mealie.operations.svc.cluster.local:9000
              key: {{ "{{" }}HOMEPAGE_VAR_MEALIE_KEY{{ "}}" }}
              version: 2
    - Out There:
        - News:
            icon: mdi-newspaper-variant
            href: https://news.ycombinator.com
            description: Hacker News front page
            widget:
              type: customapi
              url: https://hn.algolia.com/api/v1/search?tags=front_page
              refreshInterval: 600000
              display: dynamic-list
              mappings:
                items: hits
                name: title
                label: points
                limit: 6
                format: number
                target: https://news.ycombinator.com/item?id={objectID}
    # ==================== PLAY ====================
    - Watch:
        - Jellyfin:
            icon: jellyfin.png
            href: https://benplus.app
            description: Movies, TV & anime
            siteMonitor: http://jellyfin-main.media.svc.cluster.local:8096
        - Dispatcharr:
            icon: dispatcharr.png
            href: https://dispatcharr.internal.starktastic.net
            description: Live TV & IPTV proxy
            siteMonitor: http://dispatcharr.media.svc.cluster.local:9191
            widget:
              type: dispatcharr
              url: http://dispatcharr.media.svc.cluster.local:9191
              username: {{ "{{" }}HOMEPAGE_VAR_DISPATCHARR_USER{{ "}}" }}
              password: {{ "{{" }}HOMEPAGE_VAR_DISPATCHARR_PASS{{ "}}" }}
              enableActiveStreams: true
        - Cineplete:
            icon: mdi-movie-open-check
            href: https://cineplete.internal.starktastic.net
            description: What is left to watch
            siteMonitor: http://cineplete.media.svc.cluster.local:8787
        - Samsung TV+:
            icon: samsung-tv-plus.png
            description: Free channel playlists
            namespace: media
            app: samsung-tvplus
    - Listen:
        - Navidrome:
            icon: navidrome.png
            href: https://music.benplus.app
            description: Music streaming
            siteMonitor: http://navidrome.media.svc.cluster.local:4533
            widget:
              type: navidrome
              url: http://navidrome.media.svc.cluster.local:4533
              user: {{ "{{" }}HOMEPAGE_VAR_NAVIDROME_USER{{ "}}" }}
              token: {{ "{{" }}HOMEPAGE_VAR_NAVIDROME_TOKEN{{ "}}" }}
              salt: {{ "{{" }}HOMEPAGE_VAR_NAVIDROME_SALT{{ "}}" }}
        - Audiobookshelf:
            icon: audiobookshelf.png
            href: https://audiobooks.benplus.app
            description: Audiobooks & podcasts
            siteMonitor: http://audiobookshelf.media.svc.cluster.local:80
            widget:
              type: audiobookshelf
              url: http://audiobookshelf.media.svc.cluster.local:80
              key: {{ "{{" }}HOMEPAGE_VAR_AUDIOBOOKSHELF_KEY{{ "}}" }}
    - Read:
        - Calibre-Web:
            icon: calibre-web.png
            href: https://books.benplus.app
            description: E-book library
            siteMonitor: http://calibre-web.media.svc.cluster.local:8083/opds
            widget:
              type: calibreweb
              url: http://calibre-web.media.svc.cluster.local:8083
              username: {{ "{{" }}HOMEPAGE_VAR_CALIBRE_USER{{ "}}" }}
              password: {{ "{{" }}HOMEPAGE_VAR_CALIBRE_PASS{{ "}}" }}
    - Look Back:
        - Immich:
            icon: immich.png
            href: https://photos.benplus.app
            description: Photos & videos
            siteMonitor: http://immich-main.media.svc.cluster.local:2283
            widget:
              type: immich
              url: http://immich-main.media.svc.cluster.local:2283
              key: {{ "{{" }}HOMEPAGE_VAR_IMMICH_KEY{{ "}}" }}
              version: 2
    - Ask For It:
        - Seerr:
            icon: overseerr.png
            href: https://request.benplus.app
            description: Request movies & TV
            siteMonitor: http://seerr.media.svc.cluster.local:5055
            widget:
              type: seerr
              url: http://seerr.media.svc.cluster.local:5055
              key: {{ "{{" }}HOMEPAGE_VAR_SEERR_KEY{{ "}}" }}
        - Seerr RU:
            icon: overseerr.png
            href: https://request-ru.benplus.app
            description: Request movies & TV (RU)
            siteMonitor: http://seerr-ru.media.svc.cluster.local:5055
            widget:
              type: seerr
              url: http://seerr-ru.media.svc.cluster.local:5055
              key: {{ "{{" }}HOMEPAGE_VAR_SEERR_RU_KEY{{ "}}" }}
        - Shelfmark:
            icon: mdi-bookshelf
            href: https://request-books.benplus.app
            description: Request books
            siteMonitor: http://shelfmark.media.svc.cluster.local:8084
```

- [ ] **Step 2: Verify the chart renders and every embedded file parses**

```bash
helm template hp services/operations/homepage-admin/manifests | python3 -c "
import re, sys, yaml
for d in yaml.safe_load_all(sys.stdin):
    if d and d.get('kind') == 'ConfigMap':
        for name, body in (d.get('data') or {}).items():
            if name.endswith('.yaml') and body.strip():
                yaml.safe_load(re.sub(r'\{\{HOMEPAGE_VAR_[A-Z0-9_]+\}\}', 'x', body))
                print('ok', name)
"
```

Expected: `ok` for all six `.yaml` keys, no traceback.

- [ ] **Step 3: Verify group names match the layout**

```bash
helm template hp services/operations/homepage-admin/manifests | python3 -c "
import re, sys, yaml
for d in yaml.safe_load_all(sys.stdin):
    if d and d.get('kind') == 'ConfigMap':
        sub = lambda b: re.sub(r'\{\{HOMEPAGE_VAR_[A-Z0-9_]+\}\}', 'x', b)
        layout = set(yaml.safe_load(sub(d['data']['settings.yaml']))['layout'])
        groups = {list(g)[0] for g in yaml.safe_load(sub(d['data']['services.yaml']))}
        print('orphan groups:', sorted(groups - layout))
        print('empty sections:', sorted(layout - groups))
"
```

Expected:

```
orphan groups: []
empty sections: ['Acquire', 'Compute', 'Convert', 'Create', 'Data', 'Find', 'Guard', 'Home', 'Network', 'Observe', 'Organise', 'Refine', 'Send', 'Ship', 'Storage']
```

`orphan groups` must be empty. The `empty sections` list shrinks to `[]` by the end of Task 6.

- [ ] **Step 4: Run the coverage check**

```bash
python3 scripts/check-homepage-coverage.py; echo "exit=$?"
```

Expected: `exit=1` with exactly 29 `missing from admin dashboard` lines and **no** `missing from user dashboard` or `leaked` lines. This task placed 18 of the 47 hosts.

Assert it precisely:

```bash
python3 scripts/check-homepage-coverage.py | awk '/missing from admin/ {print $5}' | sort > /tmp/still-missing.txt
cat /tmp/still-missing.txt | wc -l
python3 scripts/check-homepage-coverage.py | grep -E 'missing from user|leaked' || echo "no user-side failures"
```

Expected: `29`, then `no user-side failures`. `/tmp/still-missing.txt` must contain exactly:

```
auth.starktastic.net
autobrr.internal.starktastic.net
bazarr.internal.starktastic.net
bytestash.internal.starktastic.net
changedetection.internal.starktastic.net
convertx.starktastic.net
cyberchef.starktastic.net
excalidash.starktastic.net
falco.internal.starktastic.net
files.internal.starktastic.net
ha.internal.starktastic.net
karakeep.starktastic.net
lidarr.internal.starktastic.net
lingarr.internal.starktastic.net
listmonk.starktastic.net
metube.benplus.app
microbin.starktastic.net
pairdrop.starktastic.net
paperless.internal.starktastic.net
pdf.starktastic.net
pgadmin.internal.starktastic.net
prowlarr.internal.starktastic.net
radarr-ru.internal.starktastic.net
radarr.internal.starktastic.net
search.starktastic.net
sonarr-ru.internal.starktastic.net
sonarr.internal.starktastic.net
vaultwarden.internal.starktastic.net
zigbee2mqtt.internal.starktastic.net
```

If a host you expected to have placed still appears, that group was mistyped or nested at the wrong indentation.

- [ ] **Step 5: Format**

```bash
npx --yes prettier --check services/operations/homepage-admin/manifests/templates/configmap.yaml
```

Expected: no output beyond the "All matched files use Prettier code style!" line.

- [ ] **Step 6: Commit**

```bash
git add services/operations/homepage-admin/manifests/templates/configmap.yaml
git commit -m "$(cat <<'MSG'
feat(homepage-admin): add Pulse and Play tab services

Pulse leads with three PromQL health cards, live transfers, the release
calendar and a news feed. Play groups everything you consume by verb.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
Copilot-Session: 14065d41-0039-4ae2-a1f0-d2e6eedddd0b
MSG
)"
```

---

### Task 5: Admin services — Make and Run tabs

Appends the ten remaining non-infrastructure groups to `services.yaml`.

**Files:**
- Modify: `services/operations/homepage-admin/manifests/templates/configmap.yaml`

**Interfaces:**
- Consumes: the `services.yaml` key created in Task 4; `HOMEPAGE_VAR_FILEBROWSER_USER`/`_PASS` from Task 2.
- Produces: the `Create`…`Ship` groups. Task 6 appends `Compute` onwards after them.

Headless entries use `namespace` plus `app`, which Homepage resolves through the label selector `app.kubernetes.io/name=<app>`. These labels cannot be verified from a workstation without cluster access; Task 8 verifies and corrects them against the live cluster.

- [ ] **Step 1: Append the Make and Run groups**

Insert the following immediately after the `Shelfmark` entry added in Task 4, still inside the `services.yaml` block and at the same indentation as the other `- GroupName:` lines:

```yaml
    # ==================== MAKE ====================
    - Create:
        - Excalidash:
            icon: excalidraw.png
            href: https://excalidash.starktastic.net
            description: Whiteboard & diagrams
            siteMonitor: http://excalidash.operations.svc.cluster.local:80
        - ByteStash:
            icon: bytestash.png
            href: https://bytestash.internal.starktastic.net
            description: Code snippets
            siteMonitor: http://bytestash.operations.svc.cluster.local:5000
        - MicroBin:
            icon: microbin.png
            href: https://microbin.starktastic.net
            description: Paste & share
            siteMonitor: http://microbin.operations.svc.cluster.local:8080
    - Convert:
        - ConvertX:
            icon: convertx.png
            href: https://convertx.starktastic.net
            description: File format converter
            siteMonitor: http://convertx.operations.svc.cluster.local:3000
        - Stirling PDF:
            icon: stirling-pdf.png
            href: https://pdf.starktastic.net
            description: PDF toolbox
            siteMonitor: http://stirling-pdf.operations.svc.cluster.local:8080
        - CyberChef:
            icon: cyberchef.png
            href: https://cyberchef.starktastic.net
            description: Encode, decode, analyse
            siteMonitor: http://cyberchef.operations.svc.cluster.local:8000
        - MeTube:
            icon: metube.png
            href: https://metube.benplus.app
            description: Download video & audio
            siteMonitor: http://metube.media.svc.cluster.local:8081
        - LibreTranslate:
            icon: libretranslate.png
            description: Translation API
            namespace: media
            app: libretranslate
    - Find:
        - SearXNG:
            icon: searxng.png
            href: https://search.starktastic.net
            description: Private metasearch
            siteMonitor: http://searxng.operations.svc.cluster.local:8080
        - Karakeep:
            icon: karakeep.png
            href: https://karakeep.starktastic.net
            description: Bookmarks & read-later
            siteMonitor: http://karakeep.operations.svc.cluster.local:3000
            widget:
              type: karakeep
              url: http://karakeep.operations.svc.cluster.local:3000
              key: {{ "{{" }}HOMEPAGE_VAR_KARAKEEP_KEY{{ "}}" }}
        - Changedetection:
            icon: changedetection.png
            href: https://changedetection.internal.starktastic.net
            description: Watch pages for changes
            siteMonitor: http://changedetection.operations.svc.cluster.local:5000
            widget:
              type: changedetectionio
              url: http://changedetection.operations.svc.cluster.local:5000
              key: {{ "{{" }}HOMEPAGE_VAR_CHANGEDETECTION_KEY{{ "}}" }}
    - Organise:
        - Vikunja:
            icon: vikunja.png
            href: https://vikunja.starktastic.net
            description: Tasks & projects
            siteMonitor: http://vikunja.operations.svc.cluster.local:3456
        - Paperless-ngx:
            icon: paperless-ngx.png
            href: https://paperless.internal.starktastic.net
            description: Scanned documents
            siteMonitor: http://paperless-ngx.operations.svc.cluster.local:8000
            widget:
              type: paperlessngx
              url: http://paperless-ngx.operations.svc.cluster.local:8000
              key: {{ "{{" }}HOMEPAGE_VAR_PAPERLESS_KEY{{ "}}" }}
        - Filebrowser:
            icon: filebrowser.png
            href: https://files.internal.starktastic.net
            description: Web file manager
            siteMonitor: http://filebrowser.operations.svc.cluster.local:80
            widget:
              type: filebrowser
              url: http://filebrowser.operations.svc.cluster.local:80
              username: {{ "{{" }}HOMEPAGE_VAR_FILEBROWSER_USER{{ "}}" }}
              password: {{ "{{" }}HOMEPAGE_VAR_FILEBROWSER_PASS{{ "}}" }}
        - Mealie:
            icon: mealie.png
            href: https://mealie.starktastic.net
            description: Recipes & shopping lists
            siteMonitor: http://mealie.operations.svc.cluster.local:9000
    - Send:
        - PairDrop:
            icon: pairdrop.png
            href: https://pairdrop.starktastic.net
            description: Device-to-device transfer
            siteMonitor: http://pairdrop.operations.svc.cluster.local:3000
        - ntfy:
            icon: ntfy.png
            href: https://ntfy.starktastic.net
            description: Push notifications
            siteMonitor: http://ntfy.operations.svc.cluster.local:80
        - Listmonk:
            icon: listmonk.png
            href: https://listmonk.starktastic.net
            description: Newsletters & mailing lists
            siteMonitor: http://listmonk.operations.svc.cluster.local:9000
    # ==================== RUN ====================
    - Acquire:
        - Radarr:
            icon: radarr.png
            href: https://radarr.internal.starktastic.net
            description: Movies
            siteMonitor: http://radarr.media.svc.cluster.local:7878
            widget:
              type: radarr
              url: http://radarr.media.svc.cluster.local:7878
              key: {{ "{{" }}HOMEPAGE_VAR_RADARR_KEY{{ "}}" }}
              enableQueue: true
              highlight: &queue_depth
                queued:
                  numeric:
                    - level: danger
                      when: gte
                      value: 50
                    - level: warn
                      when: gte
                      value: 20
                    - level: good
                      when: eq
                      value: 0
        - Radarr RU:
            icon: radarr.png
            href: https://radarr-ru.internal.starktastic.net
            description: Movies (RU)
            siteMonitor: http://radarr-ru.media.svc.cluster.local:7878
            widget:
              type: radarr
              url: http://radarr-ru.media.svc.cluster.local:7878
              key: {{ "{{" }}HOMEPAGE_VAR_RADARR_RU_KEY{{ "}}" }}
              enableQueue: true
              highlight: *queue_depth
        - Sonarr:
            icon: sonarr.png
            href: https://sonarr.internal.starktastic.net
            description: TV series
            siteMonitor: http://sonarr.media.svc.cluster.local:8989
            widget:
              type: sonarr
              url: http://sonarr.media.svc.cluster.local:8989
              key: {{ "{{" }}HOMEPAGE_VAR_SONARR_KEY{{ "}}" }}
              enableQueue: true
              highlight: *queue_depth
        - Sonarr RU:
            icon: sonarr.png
            href: https://sonarr-ru.internal.starktastic.net
            description: TV series (RU)
            siteMonitor: http://sonarr-ru.media.svc.cluster.local:8989
            widget:
              type: sonarr
              url: http://sonarr-ru.media.svc.cluster.local:8989
              key: {{ "{{" }}HOMEPAGE_VAR_SONARR_RU_KEY{{ "}}" }}
              enableQueue: true
              highlight: *queue_depth
        - Lidarr:
            icon: lidarr.png
            href: https://lidarr.internal.starktastic.net
            description: Music
            siteMonitor: http://lidarr.media.svc.cluster.local:8686
            widget:
              type: lidarr
              url: http://lidarr.media.svc.cluster.local:8686
              key: {{ "{{" }}HOMEPAGE_VAR_LIDARR_KEY{{ "}}" }}
        - Prowlarr:
            icon: prowlarr.png
            href: https://prowlarr.internal.starktastic.net
            description: Indexer manager
            siteMonitor: http://prowlarr.media.svc.cluster.local:9696
            widget:
              type: prowlarr
              url: http://prowlarr.media.svc.cluster.local:9696
              key: {{ "{{" }}HOMEPAGE_VAR_PROWLARR_KEY{{ "}}" }}
        - Autobrr:
            icon: autobrr.png
            href: https://autobrr.internal.starktastic.net
            description: Release automation
            siteMonitor: http://autobrr.media.svc.cluster.local:7474
            widget:
              type: autobrr
              url: http://autobrr.media.svc.cluster.local:7474
              key: {{ "{{" }}HOMEPAGE_VAR_AUTOBRR_KEY{{ "}}" }}
        - qBittorrent:
            icon: qbittorrent.png
            href: https://qbittorrent.internal.starktastic.net
            description: Torrent client
            siteMonitor: http://qbittorrent-main.media.svc.cluster.local:8080
        - qBittorrent RU:
            icon: qbittorrent.png
            href: https://qbittorrent-ru.internal.starktastic.net
            description: Torrent client (RU)
            siteMonitor: http://qbittorrent-ru-main.media.svc.cluster.local:8080
    - Refine:
        - Bazarr:
            icon: bazarr.png
            href: https://bazarr.internal.starktastic.net
            description: Subtitle fetching
            siteMonitor: http://bazarr.media.svc.cluster.local:6767
            widget:
              type: bazarr
              url: http://bazarr.media.svc.cluster.local:6767
              key: {{ "{{" }}HOMEPAGE_VAR_BAZARR_KEY{{ "}}" }}
        - Lingarr:
            icon: mdi-translate
            href: https://lingarr.internal.starktastic.net
            description: Subtitle translation
            siteMonitor: http://lingarr.media.svc.cluster.local:8080
        - Subgen:
            icon: mdi-subtitles
            description: Whisper subtitle generation
            namespace: media
            app: subgen
        - Recyclarr:
            icon: recyclarr.png
            description: TRaSH guide sync
            namespace: media
            app: recyclarr
        - Unpackerr:
            icon: unpackerr.png
            description: Archive extraction
            namespace: media
            app: unpackerr
        - Cross-seed:
            icon: cross-seed.png
            description: Cross-seeding automation
            namespace: media
            app: cross-seed
        - qbit-manage:
            icon: qbitmanage.png
            description: Torrent housekeeping
            namespace: media
            app: qbit-manage
        - qbit-manage RU:
            icon: qbitmanage.png
            description: Torrent housekeeping (RU)
            namespace: media
            app: qbit-manage-ru
        - FlareSolverr:
            icon: flaresolverr.png
            description: Cloudflare challenge solver
            namespace: media
            app: flaresolverr
    - Home:
        - Home Assistant:
            icon: home-assistant.png
            href: https://ha.internal.starktastic.net
            description: Smart home control
            siteMonitor: http://home-assistant-main.home-automation.svc.cluster.local:8123
            widget:
              type: homeassistant
              url: http://home-assistant-main.home-automation.svc.cluster.local:8123
              key: {{ "{{" }}HOMEPAGE_VAR_HASS_KEY{{ "}}" }}
        - Zigbee2MQTT:
            icon: zigbee2mqtt.png
            href: https://zigbee2mqtt.internal.starktastic.net
            description: Zigbee device bridge
            siteMonitor: http://zigbee2mqtt.home-automation.svc.cluster.local:8080
        - Mosquitto:
            icon: mosquitto.png
            description: MQTT broker
            namespace: home-automation
            app: mosquitto
    - Observe:
        - Grafana:
            icon: grafana.png
            href: https://grafana.internal.starktastic.net
            description: Dashboards & alerting
            siteMonitor: http://kube-prometheus-stack-grafana.monitoring.svc.cluster.local:80/api/health
            widget:
              type: grafana
              alerts: alertmanager
              url: http://kube-prometheus-stack-grafana.monitoring.svc.cluster.local:80
              username: {{ "{{" }}HOMEPAGE_VAR_GRAFANA_USER{{ "}}" }}
              password: {{ "{{" }}HOMEPAGE_VAR_GRAFANA_PASS{{ "}}" }}
              version: 2
        - Prometheus:
            icon: prometheus.png
            href: https://grafana.internal.starktastic.net/explore
            description: Metrics store
            siteMonitor: http://kube-prometheus-stack-prometheus.monitoring.svc.cluster.local:9090/-/healthy
            widget:
              type: prometheus
              url: http://kube-prometheus-stack-prometheus.monitoring.svc.cluster.local:9090
        - Loki:
            icon: loki.png
            description: Log aggregation
            namespace: monitoring
            app: loki
        - Tempo:
            icon: tempo.png
            description: Distributed tracing
            namespace: monitoring
            app: tempo
        - Alloy:
            icon: alloy.png
            description: Telemetry collector
            namespace: monitoring
            app: alloy
        - Blackbox Exporter:
            icon: prometheus.png
            description: Endpoint probing
            namespace: monitoring
            app: prometheus-blackbox-exporter
        - Alertmanager ntfy:
            icon: ntfy.png
            description: Alert-to-push bridge
            namespace: monitoring
            app: alertmanager-ntfy
    - Guard:
        - Authentik:
            icon: authentik.png
            href: https://auth.starktastic.net
            description: Identity provider & SSO
            siteMonitor: http://authentik-server.authentik.svc.cluster.local:80
            widget:
              type: authentik
              url: http://authentik-server.authentik.svc.cluster.local:80
              key: {{ "{{" }}HOMEPAGE_VAR_AUTHENTIK_KEY{{ "}}" }}
              version: 2
        - Vaultwarden:
            icon: vaultwarden.png
            href: https://vaultwarden.internal.starktastic.net
            description: Password manager
            siteMonitor: http://vaultwarden.operations.svc.cluster.local:8080
        - Falco:
            icon: mdi-shield-search
            href: https://falco.internal.starktastic.net
            description: Runtime threat detection
            siteMonitor: http://falco-falcosidekick-ui.falco.svc.cluster.local:2802
        - CrowdSec:
            icon: crowdsec.png
            description: Intrusion detection & bans
            namespace: crowdsec
            app: crowdsec
        - cert-manager:
            icon: cert-manager.png
            description: TLS certificate lifecycle
            namespace: cert-manager
            app: cert-manager
        - Sealed Secrets:
            icon: mdi-lock-check
            description: Encrypted secrets controller
            namespace: kube-system
            app: sealed-secrets
    - Ship:
        - Argo CD:
            icon: argo-cd.png
            href: https://argocd.internal.starktastic.net
            description: GitOps controller
            siteMonitor: https://argocd-server.argocd.svc.cluster.local:443
        - apps:
            icon: github.png
            href: https://github.com/Starktastic-Homelab/apps/pulls
            description: Open pull requests
            widget: &github_prs
              type: customapi
              url: https://api.github.com/repos/Starktastic-Homelab/apps/pulls?state=open&per_page=10
              refreshInterval: 600000
              display: dynamic-list
              headers:
                Authorization: Bearer {{ "{{" }}HOMEPAGE_VAR_GITHUB_TOKEN{{ "}}" }}
                X-GitHub-Api-Version: "2022-11-28"
                User-Agent: Homepage-Dashboard
              mappings:
                name: title
                label: user.login
                limit: 5
                target: https://github.com/Starktastic-Homelab/apps/pull/{number}
        - ansible:
            icon: github.png
            href: https://github.com/Starktastic-Homelab/ansible/pulls
            description: Open pull requests
            widget:
              <<: *github_prs
              url: https://api.github.com/repos/Starktastic-Homelab/ansible/pulls?state=open&per_page=10
              mappings:
                name: title
                label: user.login
                limit: 5
                target: https://github.com/Starktastic-Homelab/ansible/pull/{number}
        - packer:
            icon: github.png
            href: https://github.com/Starktastic-Homelab/packer/pulls
            description: Open pull requests
            widget:
              <<: *github_prs
              url: https://api.github.com/repos/Starktastic-Homelab/packer/pulls?state=open&per_page=10
              mappings:
                name: title
                label: user.login
                limit: 5
                target: https://github.com/Starktastic-Homelab/packer/pull/{number}
        - terraform:
            icon: github.png
            href: https://github.com/Starktastic-Homelab/terraform/pulls
            description: Open pull requests
            widget:
              <<: *github_prs
              url: https://api.github.com/repos/Starktastic-Homelab/terraform/pulls?state=open&per_page=10
              mappings:
                name: title
                label: user.login
                limit: 5
                target: https://github.com/Starktastic-Homelab/terraform/pull/{number}
```

Note the `target:` templates use single braces (`{number}`), which Helm passes through untouched. Only `{{` needs escaping.

- [ ] **Step 2: Verify the chart renders and every embedded file parses**

```bash
helm template hp services/operations/homepage-admin/manifests | python3 -c "
import re, sys, yaml
for d in yaml.safe_load_all(sys.stdin):
    if d and d.get('kind') == 'ConfigMap':
        for name, body in (d.get('data') or {}).items():
            if name.endswith('.yaml') and body.strip():
                yaml.safe_load(re.sub(r'\{\{HOMEPAGE_VAR_[A-Z0-9_]+\}\}', 'x', body))
                print('ok', name)
"
```

Expected: `ok` for all six `.yaml` keys.

- [ ] **Step 3: Verify only the Iron sections remain empty**

```bash
helm template hp services/operations/homepage-admin/manifests | python3 -c "
import re, sys, yaml
for d in yaml.safe_load_all(sys.stdin):
    if d and d.get('kind') == 'ConfigMap':
        sub = lambda b: re.sub(r'\{\{HOMEPAGE_VAR_[A-Z0-9_]+\}\}', 'x', b)
        layout = set(yaml.safe_load(sub(d['data']['settings.yaml']))['layout'])
        groups = {list(g)[0] for g in yaml.safe_load(sub(d['data']['services.yaml']))}
        print('orphan groups:', sorted(groups - layout))
        print('empty sections:', sorted(layout - groups))
"
```

Expected:

```
orphan groups: []
empty sections: ['Compute', 'Data', 'Network', 'Storage']
```

- [ ] **Step 4: Run the coverage check**

```bash
python3 scripts/check-homepage-coverage.py | awk '/missing from admin/ {print $5}' | sort
```

Expected exactly one line remaining:

```
pgadmin.internal.starktastic.net
```

Tasks 4 and 5 between them place 46 of the 47 hosts. `pgadmin.internal.starktastic.net` is placed by Task 6. If `traefik.internal.starktastic.net` also appears, the `href` on Task 4's *Edge & Certs* card was lost.

- [ ] **Step 5: Format**

```bash
npx --yes prettier --check services/operations/homepage-admin/manifests/templates/configmap.yaml
```

- [ ] **Step 6: Commit**

```bash
git add services/operations/homepage-admin/manifests/templates/configmap.yaml
git commit -m "$(cat <<'MSG'
feat(homepage-admin): add Make and Run tab services

Make covers everything that produces output; Run covers the automation
that keeps the library fed, observed and guarded. Headless workloads are
surfaced through the Kubernetes integration, and Falco is on a dashboard
for the first time.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
Copilot-Session: 14065d41-0039-4ae2-a1f0-d2e6eedddd0b
MSG
)"
```

---

### Task 6: Admin services — Iron tab and bookmarks

The final admin task. After it the coverage check's admin half is green.

**Files:**
- Modify: `services/operations/homepage-admin/manifests/templates/configmap.yaml`

**Interfaces:**
- Consumes: the `services.yaml` key from Tasks 4 and 5.
- Produces: a complete admin dashboard. Task 8 validates the whole thing.

- [ ] **Step 1: Append the Iron groups**

Insert immediately after the `terraform` entry added in Task 5, still inside the `services.yaml` block:

```yaml
    # ==================== IRON ====================
    - Compute:
        - Proxmox VE:
            icon: proxmox.png
            href: https://10.9.9.20:8006
            description: Hypervisor
            widget:
              type: proxmox
              url: https://10.9.9.20:8006
              username: {{ "{{" }}HOMEPAGE_VAR_PROXMOX_USER{{ "}}" }}
              password: {{ "{{" }}HOMEPAGE_VAR_PROXMOX_PASS{{ "}}" }}
              node: pve
        - kube-master-01:
            icon: proxmox.png
            description: Control plane (4c / 16GB)
            proxmoxNode: pve
            proxmoxVMID: 200
        - kube-worker-01:
            icon: proxmox.png
            description: Worker (6c / 28GB / GPU)
            proxmoxNode: pve
            proxmoxVMID: 201
        - kube-worker-02:
            icon: proxmox.png
            description: Worker (6c / 28GB / GPU)
            proxmoxNode: pve
            proxmoxVMID: 202
        - Intel Device Operator:
            icon: mdi-chip
            description: GPU device plugin
            namespace: kube-system
            app: intel-device-operator
    - Network:
        - OPNsense:
            icon: opnsense.png
            href: https://10.9.9.1
            description: Firewall & router
            widget:
              type: opnsense
              url: https://10.9.9.1
              username: {{ "{{" }}HOMEPAGE_VAR_OPNSENSE_USER{{ "}}" }}
              password: {{ "{{" }}HOMEPAGE_VAR_OPNSENSE_PASS{{ "}}" }}
        - AdGuard Home:
            icon: adguard-home.png
            href: http://10.9.9.1:3000
            description: DNS filtering
            widget:
              type: adguard
              url: http://10.9.9.1:3000
              username: {{ "{{" }}HOMEPAGE_VAR_ADGUARD_USER{{ "}}" }}
              password: {{ "{{" }}HOMEPAGE_VAR_ADGUARD_PASS{{ "}}" }}
        - Traefik:
            icon: traefik.png
            href: https://traefik.internal.starktastic.net
            description: Ingress & reverse proxy
            siteMonitor: http://traefik-api.traefik-system.svc.cluster.local:8080/ping
            widget:
              type: traefik
              url: http://traefik-api.traefik-system.svc.cluster.local:8080
        - MetalLB:
            icon: metallb.png
            description: "Load balancer (ext 10.9.8.90 / int 10.9.9.90)"
            namespace: metallb-system
            app: metallb
    - Storage:
        - TrueNAS:
            icon: truenas.png
            href: https://10.9.9.30
            description: NAS & shared storage
            widget:
              type: truenas
              url: https://10.9.9.30
              version: 2
              key: {{ "{{" }}HOMEPAGE_VAR_TRUENAS_KEY{{ "}}" }}
              enablePools: true
        - NFS Provisioner:
            icon: mdi-nas
            description: Dynamic PV provisioning
            namespace: kube-system
            app: nfs-provisioner
    - Data:
        - PostgreSQL:
            icon: postgres.png
            description: Primary database
            namespace: databases
            app: postgres
        - Redis:
            icon: redis.png
            description: Cache & session store
            namespace: databases
            app: redis
        - pgAdmin:
            icon: pgadmin.png
            href: https://pgadmin.internal.starktastic.net
            description: Database administration
            siteMonitor: http://pgadmin-pgadmin4.databases.svc.cluster.local:80
```

- [ ] **Step 2: Replace the `bookmarks.yaml` key**

Replace everything from `  bookmarks.yaml: |` to the end of the file with:

```yaml
  bookmarks.yaml: |
    - Code:
        - apps:
            - abbr: AP
              href: https://github.com/Starktastic-Homelab/apps
        - ansible:
            - abbr: AN
              href: https://github.com/Starktastic-Homelab/ansible
        - packer:
            - abbr: PK
              href: https://github.com/Starktastic-Homelab/packer
        - terraform:
            - abbr: TF
              href: https://github.com/Starktastic-Homelab/terraform
    - Reference:
        - Homepage:
            - abbr: HP
              href: https://gethomepage.dev/configs/services/
        - Kubernetes:
            - abbr: K8
              href: https://kubernetes.io/docs/home/
        - TRaSH Guides:
            - abbr: TR
              href: https://trash-guides.info
        - Dashboard Icons:
            - abbr: IC
              href: https://github.com/homarr-labs/dashboard-icons/tree/main/png
    - Accounts:
        - CrowdSec Console:
            - abbr: CS
              href: https://app.crowdsec.net
        - Finnhub:
            - abbr: FH
              href: https://finnhub.io/dashboard
```

- [ ] **Step 3: Verify every layout section now has services**

```bash
helm template hp services/operations/homepage-admin/manifests | python3 -c "
import re, sys, yaml
for d in yaml.safe_load_all(sys.stdin):
    if d and d.get('kind') == 'ConfigMap':
        sub = lambda b: re.sub(r'\{\{HOMEPAGE_VAR_[A-Z0-9_]+\}\}', 'x', b)
        layout = set(yaml.safe_load(sub(d['data']['settings.yaml']))['layout'])
        groups = {list(g)[0] for g in yaml.safe_load(sub(d['data']['services.yaml']))}
        print('orphan groups:', sorted(groups - layout))
        print('empty sections:', sorted(layout - groups))
        yaml.safe_load(sub(d['data']['bookmarks.yaml']))
        print('bookmarks ok')
"
```

Expected:

```
orphan groups: []
empty sections: []
bookmarks ok
```

- [ ] **Step 4: Verify every icon reference is a real icon**

```bash
helm template hp services/operations/homepage-admin/manifests \
  | grep -oE 'icon: [a-z0-9.-]+' | sort -u | sed 's/icon: //' \
  | while read -r i; do
      case "$i" in
        mdi-*) u="https://cdn.jsdelivr.net/npm/@mdi/svg@latest/svg/${i#mdi-}.svg" ;;
        *.png) u="https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/png/$i" ;;
        *) continue ;;
      esac
      printf '%-28s %s\n' "$i" "$(curl -s -o /dev/null -w '%{http_code}' "$u")"
    done
```

Expected: every line ends in `200`. Any `404` is a typo — fix it before committing. `/icons/favicon.svg` is skipped by the `case` because it is a local file.

- [ ] **Step 5: Confirm the admin half of the coverage check is green**

```bash
python3 scripts/check-homepage-coverage.py; echo "exit=$?"
```

Expected: `Homepage coverage OK: 47 hosts, both dashboards consistent` and `exit=0`.

The check passes here because the user dashboard was already complete before the redesign. Task 7 rewrites it and must keep it that way.

- [ ] **Step 6: Format and commit**

```bash
npx --yes prettier --check services/operations/homepage-admin/manifests/templates/configmap.yaml
git add services/operations/homepage-admin/manifests/templates/configmap.yaml
git commit -m "$(cat <<'MSG'
feat(homepage-admin): add Iron tab services and rewrite bookmarks

Completes the admin dashboard: hypervisor, nodes, network, storage and
databases, plus bookmarks grouped by code, reference and accounts. All 47
ingress hosts are now covered.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
Copilot-Session: 14065d41-0039-4ae2-a1f0-d2e6eedddd0b
MSG
)"
```

---

### Task 7: User dashboard

A complete rewrite of the smaller ConfigMap: three tabs, public hosts only, status dots on everything, and errors hidden.

**Files:**
- Modify: `services/operations/homepage/manifests/templates/configmap.yaml`

**Interfaces:**
- Consumes: `HOMEPAGE_VAR_HASS_KEY` from Task 2 and the existing `HOMEPAGE_VAR_*` keys already in `services/operations/homepage/manifests/templates/secrets.yaml`.
- Produces: a complete user dashboard. Task 8 validates it.

The instance's `kubernetes.yaml` stays `mode: disabled`, so this dashboard cannot use `namespace`/`app` entries — every service here has an `href` and a `siteMonitor`.

- [ ] **Step 1: Replace the `settings.yaml` key**

Replace everything from `  settings.yaml: |` up to (but not including) `  widgets.yaml: |` with:

```yaml
  settings.yaml: |
    title: Starktastic
    headerStyle: boxedWidgets
    statusStyle: dot
    useEqualHeights: true
    hideVersion: true
    hideErrors: true
    disableCollapse: false
    disableIndexing: true
    iconStyle: theme
    favicon: /icons/favicon.svg
    quicklaunch:
      searchDescriptions: true
      hideInternetSearch: false
      showSearchSuggestions: false
      provider: custom
      url: https://search.starktastic.net/search?q=
    pwa:
      shortcuts:
        - name: Pulse
          url: "/#pulse"
        - name: Play
          url: "/#play"
        - name: Make
          url: "/#make"
    layout:
      # -- Pulse --
      At Home:
        tab: Pulse
        style: row
        columns: 2
        icon: home-assistant.png
      Now Playing:
        tab: Pulse
        style: row
        columns: 2
        icon: mdi-heart-pulse
      Coming Up:
        tab: Pulse
        style: row
        columns: 3
        icon: mdi-calendar-month
      Out There:
        tab: Pulse
        style: row
        columns: 2
        icon: mdi-newspaper-variant
      # -- Play --
      Watch:
        tab: Play
        style: row
        columns: 2
        icon: jellyfin.png
      Listen:
        tab: Play
        style: row
        columns: 2
        icon: navidrome.png
      Read:
        tab: Play
        style: row
        columns: 2
        icon: calibre-web.png
      Look Back:
        tab: Play
        style: row
        columns: 2
        icon: immich.png
      Ask For It:
        tab: Play
        style: row
        columns: 3
        icon: overseerr.png
      # -- Make --
      Create:
        tab: Make
        style: row
        columns: 2
        icon: excalidraw.png
      Convert:
        tab: Make
        style: row
        columns: 3
        icon: convertx.png
      Find:
        tab: Make
        style: row
        columns: 2
        icon: searxng.png
      Organise:
        tab: Make
        style: row
        columns: 2
        icon: vikunja.png
      Send:
        tab: Make
        style: row
        columns: 3
        icon: ntfy.png
```

- [ ] **Step 2: Replace the `widgets.yaml` key**

Replace everything from `  widgets.yaml: |` up to (but not including) `  services.yaml: |` with:

```yaml
  widgets.yaml: |
    - logo:
        icon: /icons/favicon.svg
    - greeting:
        text_size: xl
        text: Welcome home
    - search:
        provider: custom
        url: https://search.starktastic.net/search?q=
        target: _blank
    - openmeteo:
        label: Weather
        latitude: 32.08
        longitude: 34.78
        timezone: Asia/Jerusalem
        units: metric
    - datetime:
        text_size: xl
        format:
          dateStyle: long
          timeStyle: short
          hourCycle: h23
```

No `kubernetes` and no `stocks` widget here — household members get no cluster statistics and no Finnhub key on this instance.

- [ ] **Step 3: Replace the `services.yaml` key**

Replace everything from `  services.yaml: |` up to (but not including) `  bookmarks.yaml: |` with:

```yaml
  services.yaml: |
    # ==================== PULSE ====================
    - At Home:
        - Home:
            icon: home-assistant.png
            description: Temperature, doors, lights
            widget:
              type: homeassistant
              url: http://home-assistant-main.home-automation.svc.cluster.local:8123
              key: {{ "{{" }}HOMEPAGE_VAR_HASS_KEY{{ "}}" }}
              custom:
                - state: sensor.living_room_temperature
                  label: Living room
                - state: sensor.outdoor_temperature
                  label: Outside
                - template: >-
                    {{ "{{" }} states.light|selectattr('state','equalto','on')|list|length {{ "}}" }}
                  label: Lights on
                - template: >-
                    {{ "{{" }} states.binary_sensor|selectattr('attributes.device_class','equalto','door')|selectattr('state','equalto','on')|list|length {{ "}}" }}
                  label: Doors open
    - Now Playing:
        - Jellyfin:
            icon: jellyfin.png
            href: https://benplus.app
            description: Movies, TV & anime
            siteMonitor: http://jellyfin-main.media.svc.cluster.local:8096
            widget:
              type: jellyfin
              url: http://jellyfin-main.media.svc.cluster.local:8096
              key: {{ "{{" }}HOMEPAGE_VAR_JELLYFIN_KEY{{ "}}" }}
              enableBlocks: false
              enableNowPlaying: true
              enableUser: false
              showEpisodeNumber: true
        - Navidrome:
            icon: navidrome.png
            href: https://music.benplus.app
            description: Music streaming
            siteMonitor: http://navidrome.media.svc.cluster.local:4533
            widget:
              type: navidrome
              url: http://navidrome.media.svc.cluster.local:4533
              user: {{ "{{" }}HOMEPAGE_VAR_NAVIDROME_USER{{ "}}" }}
              token: {{ "{{" }}HOMEPAGE_VAR_NAVIDROME_TOKEN{{ "}}" }}
              salt: {{ "{{" }}HOMEPAGE_VAR_NAVIDROME_SALT{{ "}}" }}
    - Coming Up:
        - Calendar:
            widget:
              type: calendar
              view: monthly
              maxEvents: 10
              showTime: true
              integrations:
                - type: ical
                  url: http://sonarr.media.svc.cluster.local:8989/feed/v3/calendar/Sonarr.ics?apikey={{ "{{" }}HOMEPAGE_VAR_SONARR_KEY{{ "}}" }}
                  name: TV
                  color: blue
                - type: ical
                  url: http://radarr.media.svc.cluster.local:7878/feed/v3/calendar/Radarr.ics?apikey={{ "{{" }}HOMEPAGE_VAR_RADARR_KEY{{ "}}" }}
                  name: Movies
                  color: red
                - type: ical
                  url: http://lidarr.media.svc.cluster.local:8686/feed/v1/calendar/Lidarr.ics?apikey={{ "{{" }}HOMEPAGE_VAR_LIDARR_KEY{{ "}}" }}
                  name: Music
                  color: green
        - Vikunja:
            icon: vikunja.png
            href: https://vikunja.starktastic.net
            description: What is due
            siteMonitor: http://vikunja.operations.svc.cluster.local:3456
            widget:
              type: vikunja
              url: http://vikunja.operations.svc.cluster.local:3456
              key: {{ "{{" }}HOMEPAGE_VAR_VIKUNJA_KEY{{ "}}" }}
              enableTaskList: true
              version: 2
        - Mealie:
            icon: mealie.png
            href: https://mealie.starktastic.net
            description: Tonight's meal plan
            siteMonitor: http://mealie.operations.svc.cluster.local:9000
            widget:
              type: mealie
              url: http://mealie.operations.svc.cluster.local:9000
              key: {{ "{{" }}HOMEPAGE_VAR_MEALIE_KEY{{ "}}" }}
              version: 2
    - Out There:
        - News:
            icon: mdi-newspaper-variant
            href: https://news.ycombinator.com
            description: Hacker News front page
            widget:
              type: customapi
              url: https://hn.algolia.com/api/v1/search?tags=front_page
              refreshInterval: 600000
              display: dynamic-list
              mappings:
                items: hits
                name: title
                label: points
                limit: 5
                format: number
                target: https://news.ycombinator.com/item?id={objectID}
    # ==================== PLAY ====================
    - Watch:
        - Jellyfin:
            icon: jellyfin.png
            href: https://benplus.app
            description: Movies, TV & anime
            siteMonitor: http://jellyfin-main.media.svc.cluster.local:8096
    - Listen:
        - Navidrome:
            icon: navidrome.png
            href: https://music.benplus.app
            description: Music streaming
            siteMonitor: http://navidrome.media.svc.cluster.local:4533
        - Audiobookshelf:
            icon: audiobookshelf.png
            href: https://audiobooks.benplus.app
            description: Audiobooks & podcasts
            siteMonitor: http://audiobookshelf.media.svc.cluster.local:80
            widget:
              type: audiobookshelf
              url: http://audiobookshelf.media.svc.cluster.local:80
              key: {{ "{{" }}HOMEPAGE_VAR_AUDIOBOOKSHELF_KEY{{ "}}" }}
    - Read:
        - Calibre-Web:
            icon: calibre-web.png
            href: https://books.benplus.app
            description: E-book library
            siteMonitor: http://calibre-web.media.svc.cluster.local:8083/opds
            widget:
              type: calibreweb
              url: http://calibre-web.media.svc.cluster.local:8083
              username: {{ "{{" }}HOMEPAGE_VAR_CALIBRE_USER{{ "}}" }}
              password: {{ "{{" }}HOMEPAGE_VAR_CALIBRE_PASS{{ "}}" }}
    - Look Back:
        - Immich:
            icon: immich.png
            href: https://photos.benplus.app
            description: Photos & videos
            siteMonitor: http://immich-main.media.svc.cluster.local:2283
            widget:
              type: immich
              url: http://immich-main.media.svc.cluster.local:2283
              key: {{ "{{" }}HOMEPAGE_VAR_IMMICH_KEY{{ "}}" }}
              version: 2
    - Ask For It:
        - Seerr:
            icon: overseerr.png
            href: https://request.benplus.app
            description: Request movies & TV
            siteMonitor: http://seerr.media.svc.cluster.local:5055
            widget:
              type: seerr
              url: http://seerr.media.svc.cluster.local:5055
              key: {{ "{{" }}HOMEPAGE_VAR_SEERR_KEY{{ "}}" }}
        - Seerr RU:
            icon: overseerr.png
            href: https://request-ru.benplus.app
            description: Request movies & TV (RU)
            siteMonitor: http://seerr-ru.media.svc.cluster.local:5055
            widget:
              type: seerr
              url: http://seerr-ru.media.svc.cluster.local:5055
              key: {{ "{{" }}HOMEPAGE_VAR_SEERR_RU_KEY{{ "}}" }}
        - Shelfmark:
            icon: mdi-bookshelf
            href: https://request-books.benplus.app
            description: Request books
            siteMonitor: http://shelfmark.media.svc.cluster.local:8084
    # ==================== MAKE ====================
    - Create:
        - Excalidash:
            icon: excalidraw.png
            href: https://excalidash.starktastic.net
            description: Whiteboard & diagrams
            siteMonitor: http://excalidash.operations.svc.cluster.local:80
        - MicroBin:
            icon: microbin.png
            href: https://microbin.starktastic.net
            description: Paste & share
            siteMonitor: http://microbin.operations.svc.cluster.local:8080
    - Convert:
        - ConvertX:
            icon: convertx.png
            href: https://convertx.starktastic.net
            description: File format converter
            siteMonitor: http://convertx.operations.svc.cluster.local:3000
        - Stirling PDF:
            icon: stirling-pdf.png
            href: https://pdf.starktastic.net
            description: PDF toolbox
            siteMonitor: http://stirling-pdf.operations.svc.cluster.local:8080
        - CyberChef:
            icon: cyberchef.png
            href: https://cyberchef.starktastic.net
            description: Encode, decode, analyse
            siteMonitor: http://cyberchef.operations.svc.cluster.local:8000
        - MeTube:
            icon: metube.png
            href: https://metube.benplus.app
            description: Download video & audio
            siteMonitor: http://metube.media.svc.cluster.local:8081
    - Find:
        - SearXNG:
            icon: searxng.png
            href: https://search.starktastic.net
            description: Private metasearch
            siteMonitor: http://searxng.operations.svc.cluster.local:8080
        - Karakeep:
            icon: karakeep.png
            href: https://karakeep.starktastic.net
            description: Bookmarks & read-later
            siteMonitor: http://karakeep.operations.svc.cluster.local:3000
            widget:
              type: karakeep
              url: http://karakeep.operations.svc.cluster.local:3000
              key: {{ "{{" }}HOMEPAGE_VAR_KARAKEEP_KEY{{ "}}" }}
    - Organise:
        - Vikunja:
            icon: vikunja.png
            href: https://vikunja.starktastic.net
            description: Tasks & projects
            siteMonitor: http://vikunja.operations.svc.cluster.local:3456
        - Mealie:
            icon: mealie.png
            href: https://mealie.starktastic.net
            description: Recipes & shopping lists
            siteMonitor: http://mealie.operations.svc.cluster.local:9000
    - Send:
        - PairDrop:
            icon: pairdrop.png
            href: https://pairdrop.starktastic.net
            description: Device-to-device transfer
            siteMonitor: http://pairdrop.operations.svc.cluster.local:3000
        - ntfy:
            icon: ntfy.png
            href: https://ntfy.starktastic.net
            description: Push notifications
            siteMonitor: http://ntfy.operations.svc.cluster.local:80
        - Listmonk:
            icon: listmonk.png
            href: https://listmonk.starktastic.net
            description: Newsletters & mailing lists
            siteMonitor: http://listmonk.operations.svc.cluster.local:9000
```

The *At Home* card has no `href` and no `siteMonitor` because Home Assistant is only reachable at `ha.internal.starktastic.net`, which must not appear on this instance. The `custom` entity IDs and templates are best guesses against a Home Assistant this repository cannot query; Task 8 verifies them and replaces any that render blank.

- [ ] **Step 4: Replace the `bookmarks.yaml` key**

Replace everything from `  bookmarks.yaml: |` to the end of the file with:

```yaml
  bookmarks.yaml: |
    - Account:
        - My Account:
            - abbr: AC
              href: https://auth.starktastic.net
    - Elsewhere:
        - GitHub:
            - abbr: GH
              href: https://github.com/Starktastic-Homelab
```

- [ ] **Step 5: Verify the chart renders, parses, and every section is filled**

```bash
helm template hp services/operations/homepage/manifests | python3 -c "
import re, sys, yaml
for d in yaml.safe_load_all(sys.stdin):
    if d and d.get('kind') == 'ConfigMap':
        sub = lambda b: re.sub(r'\{\{[^}]*\}\}', 'x', b)
        for name, body in (d.get('data') or {}).items():
            if name.endswith('.yaml') and body.strip():
                yaml.safe_load(sub(body))
        layout = set(yaml.safe_load(sub(d['data']['settings.yaml']))['layout'])
        groups = {list(g)[0] for g in yaml.safe_load(sub(d['data']['services.yaml']))}
        print('orphan groups:', sorted(groups - layout))
        print('empty sections:', sorted(layout - groups))
        print('tabs:', sorted({v['tab'] for v in yaml.safe_load(sub(d['data']['settings.yaml']))['layout'].values()}))
"
```

The substitution here is `\{\{[^}]*\}\}` rather than the `HOMEPAGE_VAR_` pattern used on the admin instance, because this file also contains Home Assistant Jinja templates in `{{ ... }}` form.

Expected:

```
orphan groups: []
empty sections: []
tabs: ['Make', 'Play', 'Pulse']
```

- [ ] **Step 6: Verify no internal host and no cluster access leaked in**

```bash
helm template hp services/operations/homepage/manifests | grep -n 'internal.starktastic.net' || echo "no internal hosts"
helm template hp services/operations/homepage/manifests | grep -n 'mode: disabled'
```

Expected: `no internal hosts`, then a line showing `mode: disabled` inside `kubernetes.yaml`.

- [ ] **Step 7: Verify every service with an href also has a siteMonitor**

```bash
helm template hp services/operations/homepage/manifests | python3 -c "
import re, sys, yaml
for d in yaml.safe_load_all(sys.stdin):
    if d and d.get('kind') == 'ConfigMap':
        svcs = yaml.safe_load(re.sub(r'\{\{[^}]*\}\}', 'x', d['data']['services.yaml']))
        bad = [n for g in svcs for entries in g.values() for e in entries
               for n, v in e.items() if v.get('href') and not v.get('siteMonitor')]
        print('href without siteMonitor:', bad)
"
```

Expected: `href without siteMonitor: ['News']`. The news card links to an external site, which has no in-cluster monitor. Any other name in that list is a bug.

- [ ] **Step 8: Run the coverage check and format**

```bash
python3 scripts/check-homepage-coverage.py; echo "exit=$?"
npx --yes prettier --check services/operations/homepage/manifests/templates/configmap.yaml
```

Expected: `Homepage coverage OK: 47 hosts, both dashboards consistent`, `exit=0`, and a clean Prettier run.

- [ ] **Step 9: Commit**

```bash
git add services/operations/homepage/manifests/templates/configmap.yaml
git commit -m "$(cat <<'MSG'
feat(homepage): rewrite the household dashboard around intent tabs

Three mobile-friendly tabs mirroring the admin scheme with every internal
service removed. Adds status dots via siteMonitor on every entry, a Home
Assistant summary card, a news feed and a greeting header.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
Copilot-Session: 14065d41-0039-4ae2-a1f0-d2e6eedddd0b
MSG
)"
```

---

### Task 8: Wire the check into CI, validate everything, and write the rollout runbook

**Files:**
- Modify: `.github/workflows/validate-and-diff.yml`
- Modify: `docs/superpowers/plans/2026-08-06-homepage-dashboard-redesign.md` (tick the boxes as you go — no code change)

**Interfaces:**
- Consumes: `scripts/check-homepage-coverage.py` from Task 1 and both rewritten ConfigMaps.
- Produces: nothing further depends on this task.

The check is wired in last so that every commit on the branch that CI actually evaluates ends green. Wiring it in Task 1 would leave the branch red for six commits.

- [ ] **Step 1: Add Helm to the validate job**

The coverage script shells out to `helm template`. The `validate` job does not currently install Helm. Insert this step immediately after the `Install yamllint` step in `.github/workflows/validate-and-diff.yml`:

```yaml
      - name: Setup Helm
        uses: azure/setup-helm@v4
        with:
          version: v3.16.2
```

- [ ] **Step 2: Add the coverage check step**

Insert immediately after the `Validate static manifests` step (the one with `id: kubeconform`):

```yaml
      - name: Check Homepage dashboard coverage
        id: homepage
        run: |
          pip install pyyaml
          set +e
          python3 scripts/check-homepage-coverage.py > homepage.txt 2>&1
          EXIT_CODE=$?
          echo "exit_code=$EXIT_CODE" >> $GITHUB_OUTPUT
          cat homepage.txt
          if [ $EXIT_CODE -ne 0 ]; then echo "❌ Homepage Coverage Failed"; else echo "✅ Homepage Coverage Passed"; fi
```

- [ ] **Step 3: Add it to the validation report**

Insert immediately before the line `          echo "" >> validation-report.md` that closes the report body (the last one, after the kubeconform `fi`):

```yaml
          if [ "${{ steps.homepage.outputs.exit_code }}" -eq 0 ]; then
            echo "✅ **Homepage Coverage:** Passed" >> validation-report.md
          else
            echo "❌ **Homepage Coverage:** FAILED" >> validation-report.md
            echo "" >> validation-report.md
            echo "<details>" >> validation-report.md
            echo "<summary>Log</summary>" >> validation-report.md
            echo "" >> validation-report.md
            echo '```' >> validation-report.md
            cat homepage.txt >> validation-report.md
            echo '```' >> validation-report.md
            echo "" >> validation-report.md
            echo "</details>" >> validation-report.md
          fi
```

- [ ] **Step 4: Make the job fail on a coverage failure**

Replace the `Check status` step's condition:

```yaml
      - name: Check status
        if: steps.yamllint.outputs.exit_code != 0 || steps.kubeconform.outputs.exit_code != 0
        run: exit 1
```

with:

```yaml
      - name: Check status
        if: steps.yamllint.outputs.exit_code != 0 || steps.kubeconform.outputs.exit_code != 0 || steps.homepage.outputs.exit_code != 0
        run: exit 1
```

- [ ] **Step 5: Verify the workflow file parses**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/validate-and-diff.yml')); print('workflow ok')"
```

Expected: `workflow ok`.

- [ ] **Step 6: Run the whole local validation suite**

```bash
python3 scripts/check-homepage-coverage.py; echo "coverage exit=$?"
helm template hp services/operations/homepage-admin/manifests > /dev/null && echo "admin renders"
helm template hp services/operations/homepage/manifests > /dev/null && echo "user renders"
npx --yes prettier --check 'services/operations/homepage*/manifests/templates/*.yaml' '.github/workflows/validate-and-diff.yml'
```

Expected: `Homepage coverage OK: 47 hosts, both dashboards consistent`, `coverage exit=0`, `admin renders`, `user renders`, and a clean Prettier run.

- [ ] **Step 7: Commit**

```bash
git add .github/workflows/validate-and-diff.yml
git commit -m "$(cat <<'MSG'
ci: fail the build when a service is missing from a dashboard

Runs scripts/check-homepage-coverage.py alongside yamllint and
kubeconform so a new ingress cannot ship without a dashboard entry.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
Copilot-Session: 14065d41-0039-4ae2-a1f0-d2e6eedddd0b
MSG
)"
```

- [ ] **Step 8: Open the pull request**

```bash
git push -u origin feat/homepage-dashboard-redesign
gh pr create --fill --base main
```

Wait for the `Validate` job to pass and read the ArgoCD diff preview comment. The diff should touch only the two `homepage*` ConfigMaps, the two SealedSecrets, and nothing else. If it shows changes to unrelated Applications, stop and investigate before merging.

- [ ] **Step 9: Post-merge — force both pods to pick up the new config**

`settings.yaml` does not hot-reload in Homepage, and Stakater Reloader is **not** deployed in this cluster (the `reloader.stakater.com/auto` annotation elsewhere in the repo is a no-op). Both Deployments must be restarted by hand after Argo CD syncs:

```bash
kubectl -n operations rollout restart deployment/homepage-admin deployment/homepage
kubectl -n operations rollout status deployment/homepage-admin --timeout=120s
kubectl -n operations rollout status deployment/homepage --timeout=120s
```

- [ ] **Step 10: Post-merge — verify the headless entries resolve**

Task 5 and Task 6 guessed `app.kubernetes.io/name` label values. Check them against the cluster:

```bash
for e in \
  "media samsung-tvplus" "media libretranslate" "media subgen" "media recyclarr" \
  "media unpackerr" "media cross-seed" "media qbit-manage" "media qbit-manage-ru" \
  "media flaresolverr" "home-automation mosquitto" "monitoring loki" "monitoring tempo" \
  "monitoring alloy" "monitoring prometheus-blackbox-exporter" "monitoring alertmanager-ntfy" \
  "crowdsec crowdsec" "cert-manager cert-manager" "kube-system sealed-secrets" \
  "kube-system intel-device-operator" "kube-system nfs-provisioner" \
  "metallb-system metallb" "databases postgres" "databases redis"; do
  set -- $e
  n=$(kubectl -n "$1" get pods -l "app.kubernetes.io/name=$2" --no-headers 2>/dev/null | wc -l)
  printf '%-24s %-32s %s pods\n' "$1" "$2" "$n"
done
```

Every line must show at least `1 pods`. For any that show `0`, find the real label and correct the `app:` value in the admin ConfigMap:

```bash
kubectl -n <namespace> get pods --show-labels | head
```

If a workload has no `app.kubernetes.io/name` label at all, swap `app: <name>` for an explicit selector on that entry, for example:

```yaml
        - Loki:
            icon: loki.png
            description: Log aggregation
            namespace: monitoring
            podSelector: app.kubernetes.io/instance=loki
```

- [ ] **Step 11: Post-merge — verify the PromQL cards**

The three `prometheusmetric` cards on *Pulse* could not be tested without cluster access. `hideErrors: false` on the admin instance means a bad query shows as an error on the card rather than an empty space. Open `https://admin.starktastic.net` and confirm all eleven metrics render a number. For any that do not, paste the query into Grafana Explore at `https://grafana.internal.starktastic.net/explore` and adjust.

Most likely corrections:
- `cs_active_decisions` — if CrowdSec's metrics are not scraped, delete the *Active Bans* metric.
- `falcosecurity_falcosidekick_falco_events_total` — Falcosidekick's metric name varies by chart version; check with `{__name__=~"falco.*"}` in Explore.
- `kubelet_volume_stats_*` — requires kubelet metrics scraping, which kube-prometheus-stack enables by default.

- [ ] **Step 12: Post-merge — verify the Home Assistant card on the user page**

Open `https://starktastic.net` and check the *At Home* card. The four entries use guessed entity IDs. Find the real ones in Home Assistant under Developer Tools → States, and correct `sensor.living_room_temperature` and `sensor.outdoor_temperature` in the user ConfigMap. `hideErrors: true` on this instance means a wrong entity ID renders blank rather than erroring — an empty value is the signal.

- [ ] **Step 13: Post-merge — verify the new widgets authenticate**

On `https://admin.starktastic.net`, confirm each of these renders data rather than an error:

| Widget | Section | If it fails |
| --- | --- | --- |
| ntfy | Pulse → In Flight | Token lacks read access to the `alerts` topic; reissue with topic scope. |
| Dispatcharr | Play → Watch | Wrong credentials, or the API requires a token rather than basic auth. |
| Filebrowser | Make → Organise | Wrong credentials, or the instance uses proxy-header auth — add `authHeader`. |
| stocks | header | Finnhub key invalid or rate-limited; raise `cache`. |

- [ ] **Step 14: Delete the branch**

```bash
git checkout main && git pull && git branch -d feat/homepage-dashboard-redesign
```

---

## Deferred

- **CrowdSec widget.** The `crowdsec` service widget needs username/password against the LAPI, which this cluster runs in TLS-only mode with password auth disabled. It is not attempted; the *Security* PromQL card covers bans instead. Revisit if the LAPI is ever reconfigured to accept machine credentials.
- **`resources` and `glances` info widgets.** `resources` reports the Homepage container's own limits, not the host's, which is meaningless in this cluster; Glances is not deployed. The `kubernetes` header widget and the *Cluster Health* card cover the same ground.
- **`.gitignore`.** This repository has none, and `.superpowers/` from the brainstorming session is untracked. Out of scope for this plan.
- **Radarr RU / Sonarr RU calendar feeds on the user page.** `HOMEPAGE_VAR_RADARR_RU_KEY` and `HOMEPAGE_VAR_SONARR_RU_KEY` stay sealed but unused on that instance: five overlapping iCal sources make the monthly calendar unreadable on a phone, and the RU libraries land in the same Jellyfin. Add them if the household asks.
