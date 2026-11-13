#!/usr/bin/env python3
"""Render both Homepage pages in the deployed image against a mock upstream and check the DOM (ADR 0020).

    render_check.py [--pages household,admin] [--out DIR]   run the check; exit 1 on any failure
    render_check.py --serve [--scenario calm|alarm]         leave the pages up for a browser test
    render_check.py --down                                  remove what --serve left running

Needs Docker and Playwright for Python (requirements.txt). The browser is the machine's Chrome, or the
executable named by HP_CHROME. Nothing here reaches the cluster: every URL the pod would fetch is pointed at
the mock, and every credential is the word "mock".
"""
import argparse
import copy
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from catalog import load_catalog, slug  # noqa: E402
from generate import ROOT, inventory  # noqa: E402
from render import ADMIN_ONLY, PAGES, PLACEHOLDER, build_page, mount_path  # noqa: E402

MOCK = "http://mock:8080"
PORTS = {"household": 3401, "admin": 3402}
VIEWPORTS = {"390x844": (390, 844), "1440x900": (1440, 900)}
SCENARIOS = ("calm", "alarm")
DOWN = {"calm": set(), "alarm": {"seerr-ru"}}  # tiles whose status dot is down in that scenario
NETWORK, MOCK_NAME = "hpcheck", "hpcheck-mock"
# custom.css selectors the mock cannot make match, and small tap targets that are Homepage's own. One reason each.
SELECTOR_ALLOW: dict[str, str] = {}
SMALL_ALLOW: dict[str, str] = {}


def mock_slug(url: str) -> str:
    """The mock data directory for an upstream: its host and port, dots and colons as dashes."""
    return re.sub(r"[.:]", "-", urllib.parse.urlsplit(url).netloc)


def mock_url(url: str) -> str:
    u = urllib.parse.urlsplit(url)
    return f"{MOCK}/{mock_slug(url)}{u.path}" + (f"?{u.query}" if u.query else "")


def _rewrite(node) -> None:
    """Point every `url` below a widget at the mock, in place."""
    if isinstance(node, dict):
        if node.get("type") == "truenas":
            node.pop("version", None)  # version 2 is JSON-RPC over a websocket; the mock answers the REST API
        for key, val in node.items():
            if key == "url" and isinstance(val, str) and val.startswith(("http://", "https://")):
                node[key] = mock_url(val)
            else:
                _rewrite(val)
    elif isinstance(node, list):
        for item in node:
            _rewrite(item)


def _tiles(entries):
    for entry in entries:
        (_name, val), = entry.items()
        if isinstance(val, dict):
            yield val
        else:
            yield from _tiles(val)


def build_config(data: dict, down: set) -> dict:
    """One page's files for the check, from render.build_page()'s data: no cluster, no secrets, no real host."""
    data = copy.deepcopy(data)
    for tile in _tiles(data["services.yaml"]):
        if "siteMonitor" in tile:
            tile["siteMonitor"] = f"{MOCK}/{'down' if tile['id'] in down else 'up'}/{tile['id']}"
        for key in ADMIN_ONLY:
            tile.pop(key, None)  # no cluster and no Proxmox behind the status dots here
        _rewrite(tile.get("widget"))
        _rewrite(tile.get("widgets"))
    for entry in data["widgets.yaml"]:
        (kind, opts), = entry.items()
        if kind != "search":  # the search URL is opened by the browser, never fetched by the pod
            _rewrite(opts)
    _rewrite(data.get("proxmox.yaml"))
    data["settings.yaml"] = {**data["settings.yaml"], "hideErrors": False, "disableUpdateCheck": True}
    data["kubernetes.yaml"] = {"mode": "disabled"}
    out = {}
    for key, val in data.items():
        text = val if isinstance(val, str) else yaml.safe_dump(val, sort_keys=False, allow_unicode=True,
                                                               width=float("inf"))
        out[key] = PLACEHOLDER.sub("mock", text)
    return out


def failures(inv: dict, runs: list, page: str) -> list:
    """One line per failed expectation. `inv` is generate.inventory()[page]; a run is one tab in one viewport."""
    out = []
    tab_of_group = {g["name"]: g["tab"] for g in inv["groups"]}
    home = {e["id"]: tab_of_group[e["group"]] for e in inv["tiles"] + inv["bookmarks"]}
    matched, seen = {}, set()
    for r in runs:
        where = f"{page} {r['tab']} {r['viewport']} {r['scenario']}"
        seen.add(r["tab"])
        if not r["ok"]:
            out.append(f"{where}: the dashboard did not render (config error panel, or no tabs)")
            continue
        ids = set(r["ids"])
        for eid, tab in home.items():
            if tab == r["tab"] and eid not in ids:
                out.append(f"{where}: {eid} is missing")
            elif tab != r["tab"] and eid in ids:
                out.append(f"{where}: {eid} belongs to tab {tab}")
        for group, tab in tab_of_group.items():
            if tab == r["tab"] and group not in r["groups"]:
                out.append(f"{where}: group {group} is missing")
        if r["errors"]:
            out.append(f"{where}: {r['errors']} widget error box(es)")
        out += [f"{where}: {url} failed to load" for url in r["missing"]]
        if page == "household" and r["viewport"].startswith("390x"):
            out += [f"{where}: under 44x44 px: {s}" for s in r["small"] if not any(k in s for k in SMALL_ALLOW)]
        for sel, hit in r["selectors"].items():
            matched[sel] = matched.get(sel, False) or hit
    out += [f"{page}: tab {t['name']} was never rendered" for t in inv["tabs"] if t["name"] not in seen]
    out += [f"{page}: custom.css selector matches nothing: {sel}"
            for sel, hit in matched.items() if not hit and sel not in SELECTOR_ALLOW]
    return out


SETTLED_JS = "() => !!document.querySelector('#layout-groups') && !document.querySelector('.animate-pulse')"
SNAPSHOT_JS = r"""
() => {
  const q = (sel) => [...document.querySelectorAll(sel)];
  // Complex selectors of one rule, split at top-level commas.
  const parts = (text) => {
    const out = []; let depth = 0, cur = "";
    for (const ch of text) {
      if ("([".includes(ch)) depth++;
      if (")]".includes(ch)) depth--;
      if (ch === "," && depth === 0) { out.push(cur.trim()); cur = ""; } else cur += ch;
    }
    return out.concat(cur.trim()).filter(Boolean);
  };
  // State and pseudo-elements say nothing about whether the hook still exists.
  const bare = (sel) => sel.replace(/::?(before|after|placeholder|marker|selection|backdrop)\b/g, "")
    .replace(/:(hover|active|focus-visible|focus-within|focus|visited|checked|disabled)\b/g, "");
  const selectors = {};
  const walk = (rules) => {
    for (const rule of rules) {
      if (rule instanceof CSSKeyframesRule) continue;
      if (rule.selectorText) {
        for (const sel of parts(rule.selectorText)) {
          let hit = false;
          try { const b = bare(sel).trim(); hit = b === "" || !!document.querySelector(b); } catch (e) { hit = false; }
          selectors[sel] = selectors[sel] || hit;
        }
      } else if (rule.cssRules) walk(rule.cssRules);
    }
  };
  const sheet = [...document.styleSheets].find((s) => (s.href || "").endsWith("/api/config/custom.css"));
  if (sheet) walk(sheet.cssRules);
  const small = [];
  for (const el of q('a[href], button, input, select, [role="tab"], [tabindex]:not([tabindex="-1"])')) {
    const r = el.getBoundingClientRect(), cs = getComputedStyle(el);
    if (!r.width || !r.height || cs.visibility === "hidden" || cs.display === "none" || cs.opacity === "0") continue;
    if (el.closest("dialog:not([open])") || el.disabled) continue;
    if (r.width < 44 || r.height < 44) {
      const text = (el.textContent || el.getAttribute("aria-label") || el.title || "").trim().slice(0, 28);
      const home = el.closest(".service, .bookmark")?.id || el.closest("[id]")?.id || "?";
      small.push(`${el.tagName.toLowerCase()}${el.id ? "#" + el.id : ""} ${Math.round(r.width)}x${Math.round(r.height)} "${text}" in ${home}`);
    }
  }
  return {
    ok: !!document.querySelector("#information-widgets") && !!document.querySelector("#myTab"),
    ids: q(".service[id], .bookmark[id]").map((e) => e.id),
    groups: q(".service-group-name, .bookmark-group-name").map((e) => e.textContent.trim()),
    errors: q(".service details, .information-widget-error").length,
    small, selectors,
  };
}
"""


def sh(*args, check=True, quiet=True):
    return subprocess.run([str(a) for a in args], check=check, text=True,
                          stdout=subprocess.PIPE if quiet else None, stderr=subprocess.STDOUT if quiet else None)


def image(repo: Path) -> str:
    """The deployed Homepage image, by digest."""
    path = Path(repo) / PAGES["admin"]["dir"] / "values.yaml"
    im = yaml.safe_load(path.read_text(encoding="utf-8"))["controllers"]["main"]["containers"]["main"]["image"]
    tag = str(im["tag"])
    return f"{im['repository']}@{tag.split('@', 1)[1]}" if "@" in tag else f"{im['repository']}:{tag}"


def down() -> None:
    sh("docker", "rm", "-f", MOCK_NAME, *[f"hpcheck-{p}" for p in PAGES], check=False)
    sh("docker", "network", "rm", NETWORK, check=False)


def up(repo: Path, work: Path, scenario: str, pages: list) -> None:
    """Start the mock and one Homepage container per page. Everything is copied under `work` first."""
    down()
    img = image(repo)
    sh("docker", "network", "create", NETWORK)
    shutil.copytree(HERE / "mock", work / "mock")
    certs = work / "mock/certs"
    certs.mkdir()
    # Throwaway self-signed pair, so the mock can answer as the weather and stock hosts Homepage hard-codes.
    sh("openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2", "-subj", "/CN=mock",
       "-keyout", certs / "key.pem", "-out", certs / "cert.pem")
    (certs / "key.pem").chmod(0o644)
    sh("docker", "run", "-d", "--no-healthcheck", "--name", MOCK_NAME, "--network", NETWORK,
       "--network-alias", "mock", "--network-alias", "api.open-meteo.com", "--network-alias", "finnhub.io",
       "-e", f"MOCK_SCENARIO={scenario}", "-e", "MOCK_STRICT=1", "-v", f"{work / 'mock'}:/mock",
       "--entrypoint", "node", img, "/mock/server.js")
    cat = load_catalog(repo)
    for page in pages:
        cfg, pub = work / page / "config", work / page / "public"
        cfg.mkdir(parents=True)
        pub.mkdir()
        mounts = ["-v", f"{cfg}:/app/config"]
        for key, text in build_config(build_page(repo, cat, page), DOWN[scenario]).items():
            target = mount_path(key)
            if target.startswith("/app/config/"):
                (cfg / key).write_text(text, encoding="utf-8")
            else:
                (pub / key).write_text(text, encoding="utf-8")
                mounts += ["-v", f"{pub / key}:{target}:ro"]
        port = PORTS[page]
        sh("docker", "run", "-d", "--name", f"hpcheck-{page}", "--network", NETWORK, "-p", f"127.0.0.1:{port}:3000",
           "-e", f"HOMEPAGE_ALLOWED_HOSTS=localhost:{port},127.0.0.1:{port}",
           "-e", "NODE_TLS_REJECT_UNAUTHORIZED=0",  # only so the mock's self-signed pair is accepted
           "-e", f"PUID={os.getuid()}", "-e", f"PGID={os.getgid()}", *mounts, img)
    for page in pages:
        url, deadline = f"http://127.0.0.1:{PORTS[page]}/", time.time() + 120
        while True:
            try:
                urllib.request.urlopen(url, timeout=5).read()
                break
            except (urllib.error.URLError, OSError) as err:
                if time.time() > deadline:
                    raise SystemExit(f"{page}: Homepage did not answer on {url}: {err}\n"
                                     + sh("docker", "logs", "--tail", "30", f"hpcheck-{page}", check=False).stdout)
                time.sleep(1)


def mock_misses(work: Path) -> list:
    """Requests the mock had no data for: the first thing to read when a widget shows an error."""
    out = set()
    log = work / "mock/requests.log"
    for line in log.read_text(encoding="utf-8").splitlines() if log.is_file() else []:
        r = json.loads(line)
        if r["status"] >= 400 and not r["path"].startswith("/down/"):
            out.add(f"mock answered {r['status']}: {r['method']} {r['host']}{r['path']}"
                    + (f"?{r['query']}" if r["query"] else ""))
    return sorted(out)


def snapshot(browser, page: str, inv: dict, scenario: str, out: Path | None) -> list:
    from playwright.sync_api import TimeoutError as PlaywrightTimeout

    runs, origin = [], f"http://127.0.0.1:{PORTS[page]}"
    for vp, (width, height) in VIEWPORTS.items():
        ctx = browser.new_context(viewport={"width": width, "height": height})
        tab_page = ctx.new_page()
        missing = []

        def on_response(resp):
            path = urllib.parse.urlsplit(resp.url).path
            if resp.url.startswith(origin) and path.startswith(("/images/", "/icons/")) and resp.status >= 400:
                missing.append(path)

        tab_page.on("response", on_response)
        tab_page.goto(origin + "/", wait_until="domcontentloaded")
        for i, tab in enumerate(inv["tabs"]):
            if i:
                missing.clear()  # the first tab also owns what the page load fetched
            try:
                tab_page.wait_for_selector("#layout-groups", timeout=30000)
                if i:
                    tab_page.click(f'[id="{tab["name"]}-tab"]', timeout=10000)
                # Never wait for the network to go idle: icons come from a CDN the check must not depend on.
                tab_page.wait_for_function(SETTLED_JS, timeout=20000)
            except PlaywrightTimeout:
                pass  # the snapshot below reports what is missing
            try:  # icons come from a CDN: give them a moment for the screenshots, but never fail on them
                tab_page.wait_for_function("() => [...document.images].every((i) => i.complete)", timeout=6000)
            except PlaywrightTimeout:
                pass
            tab_page.wait_for_timeout(1500)
            snap = tab_page.evaluate(SNAPSHOT_JS)
            runs.append({"tab": tab["name"], "viewport": vp, "scenario": scenario, "missing": sorted(set(missing)),
                         **snap})
            if out:
                name = f"{page}-{scenario}-{vp}-{slug(tab['name'])}"
                tab_page.screenshot(path=str(out / f"{name}.png"))
                tab_page.set_viewport_size({"width": width, "height": 2600})  # the page scrolls inside a wrapper
                tab_page.wait_for_timeout(300)
                tab_page.screenshot(path=str(out / f"{name}-full.png"))
                tab_page.set_viewport_size({"width": width, "height": height})
        ctx.close()
    return runs


def main(argv=None, repo: Path = ROOT) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pages", default="household,admin")
    parser.add_argument("--out", type=Path, help="directory for screenshots")
    parser.add_argument("--serve", action="store_true", help="leave the pages running and exit")
    parser.add_argument("--scenario", choices=SCENARIOS, default="calm", help="with --serve")
    parser.add_argument("--down", action="store_true", help="remove the containers and exit")
    args = parser.parse_args(argv)
    pages = [p for p in args.pages.split(",") if p]
    if set(pages) - set(PAGES):
        parser.error(f"--pages takes {', '.join(PAGES)}")
    if args.down:
        down()
        return 0
    if args.serve:
        up(repo, Path(tempfile.mkdtemp(prefix="hpcheck-")), args.scenario, pages)
        print(*[f"{p}: http://127.0.0.1:{PORTS[p]}/  ({args.scenario})" for p in pages], sep="\n")
        print("stop with: render_check.py --down")
        return 0

    from playwright.sync_api import sync_playwright

    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
    inv = inventory(repo)
    runs, misses = {p: [] for p in pages}, []
    with sync_playwright() as pw:
        chrome = os.environ.get("HP_CHROME")
        browser = pw.chromium.launch(**({"executable_path": chrome} if chrome else {"channel": "chrome"}))
        for scenario in SCENARIOS:
            work = Path(tempfile.mkdtemp(prefix="hpcheck-"))
            try:
                up(repo, work, scenario, pages)
                for page in pages:
                    runs[page] += snapshot(browser, page, inv[page], scenario, args.out)
                misses += [f"{scenario}: {m}" for m in mock_misses(work)]
            finally:
                down()
                if os.environ.get("HP_KEEP_WORK"):  # for debugging mock data: config dirs and the request log
                    print(f"kept {work}")
                else:
                    shutil.rmtree(work, ignore_errors=True)
        browser.close()
    problems = [line for page in pages for line in failures(inv[page], runs[page], page)]
    if problems:
        print(*problems, *misses, sep="\n")
        print(f"\nHomepage render check FAILED ({len(problems)} problems)")
        return 1
    tabs = sum(len(inv[p]["tabs"]) for p in pages)
    print(f"Homepage render check OK: {', '.join(pages)}; {tabs} tabs, {len(VIEWPORTS)} viewports, "
          f"{len(SCENARIOS)} scenarios")
    return 0


if __name__ == "__main__":
    sys.exit(main())
