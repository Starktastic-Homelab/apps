// Mock upstream for the Homepage render check (ADR 0020). It serves canned data from /mock/data; nothing real.
// render_check.py points every URL the pod would fetch at http://mock:8080/<slug>/<path>, where <slug> is the
// real upstream's host and port with dots and colons as dashes (sonarr.media:8989 -> sonarr-media-8989).
//
// Lookup for <slug>/<path> (the query string is ignored unless a rule matches on it):
//   1. data/<slug>/_rules.json: [{path, method?, query?, status?, headers?, file?|json?|text?}]
//      path is exact, or a regex when it starts with "^". file is relative to data/.
//   2. <path>.<METHOD>.json, <path>.json, <path>, <path>/index.json under data/<slug>/
//   Hosts Homepage hard-codes (weather, stocks) are aliased to this container and read data/_hosts/<host>/.
//   Built in: /up/* -> 200, /down/* -> 503; <slug>/api/v1/query -> a vector from data/<slug>/values.json, which
//   maps a PromQL string, or a substring of it (the longest key wins), to a number or [{metric, value}].
// Text bodies get {{iso[:+2d]}}, {{date}}, {{epoch}}, {{epochms}}, {{ics}}, {{icsdate}}, {{rfc}} filled with
// times relative to now, so calendars and "ago" fields always look current.
//
// MOCK_SCENARIO=<name>: look in /mock/<name>/ before /mock/data/; values.json files merge, the scenario wins.
// MOCK_STRICT=1: a PromQL query needs its own exact key; without one it answers 500, so a missing value
//   shows as a widget error instead of "-" or a neighbour's number.
// MOCK_PORTS=8080,9090: plain-HTTP ports to listen on (default 80 and 8080).
// Every request is logged to /mock/requests.log as one JSON line.
const http = require("http");
const https = require("https");
const fs = require("fs");
const path = require("path");

const ROOT = process.env.MOCK_ROOT || "/mock";
const SCENARIO = process.env.MOCK_SCENARIO || "calm";
const STRICT = process.env.MOCK_STRICT === "1";
const DATA = path.join(ROOT, "data");
const OVER = path.join(ROOT, SCENARIO);
const ROOTS = SCENARIO !== "data" && fs.existsSync(OVER) ? [OVER, DATA] : [DATA];
const LOG = path.join(ROOT, "requests.log");
const LOCAL_HOSTS = new Set(["mock", "localhost", "127.0.0.1", ""]);
const TYPES = {
  ".json": "application/json", ".ics": "text/calendar", ".xml": "application/xml", ".rss": "application/rss+xml",
  ".txt": "text/plain", ".html": "text/html", ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg",
};
const TEXTUAL = new Set([".json", ".ics", ".xml", ".rss", ".txt", ".html", ".svg", ""]);

function shift(spec) {
  const m = /^([+-])(\d+(?:\.\d+)?)([smhdw])$/.exec(spec || "");
  if (!m) return 0;
  const ms = parseFloat(m[2]) * { s: 1, m: 60, h: 3600, d: 86400, w: 604800 }[m[3]] * 1000;
  return m[1] === "-" ? -ms : ms;
}

function fill(text) {
  const now = Date.now();
  return text.replace(/\{\{(iso|date|epochms|epoch|icsdate|ics|rfc)(?::([+-][\d.]+[smhdw]))?\}\}/g, (_, kind, spec) => {
    const d = new Date(now + shift(spec));
    const iso = d.toISOString();
    switch (kind) {
      case "iso": return iso;
      case "date": return iso.slice(0, 10);
      case "epoch": return String(Math.floor(d.getTime() / 1000));
      case "epochms": return String(d.getTime());
      case "ics": return iso.replace(/[-:]/g, "").replace(/\.\d{3}/, "");
      case "icsdate": return iso.slice(0, 10).replace(/-/g, "");
      case "rfc": return d.toUTCString();
      default: return "";
    }
  });
}

// The first root that holds rel as a regular file, never outside that root.
function find(rel) {
  for (const root of ROOTS) {
    const full = path.normalize(path.join(root, rel));
    if (full !== root && !full.startsWith(root + path.sep)) continue;
    try {
      if (fs.statSync(full).isFile()) return { file: full, buf: fs.readFileSync(full) };
    } catch {}
  }
  return null;
}

function body(buf, ext) {
  return TEXTUAL.has(ext) ? Buffer.from(fill(buf.toString("utf8"))) : buf;
}

// values.json of a Prometheus slug, data first and the scenario's entries over it; null when it has none.
function promTable(slug) {
  let table = null;
  for (const root of [...ROOTS].reverse()) {
    try { table = { ...(table || {}), ...JSON.parse(fs.readFileSync(path.join(root, slug, "values.json"), "utf8")) }; } catch {}
  }
  return table;
}

function promVector(table, query) {
  let hit, matched = null;
  if (Object.prototype.hasOwnProperty.call(table, query)) { hit = table[query]; matched = "prom:exact"; }
  else if (!STRICT) {
    // Longest matching substring key wins, so specific keys beat generic ones.
    const keys = Object.keys(table).filter((k) => k && query.includes(k)).sort((a, b) => b.length - a.length);
    if (keys.length) { hit = table[keys[0]]; matched = "prom:substring:" + keys[0]; }
  }
  if (hit === undefined && STRICT) {
    return { status: 500, matched: "prom:unmatched", json: { status: "error", errorType: "mock", error: "mock: no value for " + query } };
  }
  const t = Date.now() / 1000;
  let result;
  if (hit === undefined) result = [];
  else if (Array.isArray(hit)) result = hit.map((r) => ({ metric: r.metric || {}, value: [t, String(r.value)] }));
  else result = [{ metric: {}, value: [t, String(hit)] }];
  return { status: 200, matched: matched || "prom:unmatched", json: { status: "success", data: { resultType: "vector", result } } };
}

function matchRule(rules, p, method, query) {
  for (const r of rules) {
    if (r.method && r.method.toUpperCase() !== method) continue;
    const ok = r.path.startsWith("^") ? new RegExp(r.path).test(p) : r.path === p;
    if (!ok) continue;
    if (r.query && !query.includes(r.query)) continue;
    return r;
  }
  return null;
}

function respond(req, res, proto) {
  const u = new URL(req.url, `${proto}://mock`);
  const host = (req.headers.host || "").split(":")[0].toLowerCase();
  const local = LOCAL_HOSTS.has(host);
  const base = local ? "" : path.join("_hosts", host);
  const p = decodeURIComponent(u.pathname);
  const method = req.method.toUpperCase();
  const query = u.search.slice(1);
  const slug = local ? (p.split("/")[1] || "") : "";
  let status = 404, headers = { "content-type": "application/json" }, out = null, matched = null;

  if (local && p.startsWith("/up/")) {
    status = 200; out = Buffer.from("ok"); headers["content-type"] = "text/plain"; matched = "builtin:up";
  } else if (local && p.startsWith("/down/")) {
    status = 503; out = Buffer.from("down"); headers["content-type"] = "text/plain"; matched = "builtin:down";
  } else if (local && p === `/${slug}/api/v1/query`) {
    const table = promTable(slug);
    if (table) {
      const v = promVector(table, u.searchParams.get("query") || "");
      status = v.status; out = Buffer.from(JSON.stringify(v.json)); matched = v.matched;
    }
  }

  if (matched === null) {
    let rules = [];
    const rf = find(path.join(base, slug, "_rules.json"));
    if (rf) { try { rules = JSON.parse(rf.buf.toString("utf8")); } catch { rules = []; } }
    const rule = matchRule(rules, p, method, query);
    if (rule) {
      status = rule.status || 200;
      Object.assign(headers, rule.headers || {});
      if (rule.file) {
        const hit = find(rule.file);
        const ext = path.extname(rule.file);
        if (hit) { out = body(hit.buf, ext); if (!rule.headers || !rule.headers["content-type"]) headers["content-type"] = TYPES[ext] || "application/octet-stream"; }
        else { status = 500; out = Buffer.from(JSON.stringify({ error: "mock: rule file missing", file: rule.file })); }
      } else if (rule.json !== undefined) out = Buffer.from(fill(JSON.stringify(rule.json)));
      else if (rule.text !== undefined) { out = Buffer.from(fill(rule.text)); if (!rule.headers || !rule.headers["content-type"]) headers["content-type"] = "text/plain"; }
      else out = Buffer.from("");
      matched = "rule:" + rule.path;
    } else {
      for (const c of [`${p}.${method}.json`, `${p}.json`, p, `${p}/index.json`]) {
        const hit = find(path.join(base, c));
        if (!hit) continue;
        const ext = path.extname(hit.file);
        status = 200; out = body(hit.buf, ext); headers["content-type"] = TYPES[ext] || "application/json";
        matched = c;
        break;
      }
    }
  }
  if (out === null) out = Buffer.from(JSON.stringify({ error: "mock: no data", host, path: p, method }));
  try {
    fs.appendFileSync(LOG, JSON.stringify({ t: new Date().toISOString(), proto, host, method, path: p, query, status, matched }) + "\n");
  } catch {}
  res.writeHead(status, headers);
  res.end(method === "HEAD" ? undefined : out);
}

function handler(proto) {
  return (req, res) => {
    req.on("data", () => {});
    req.on("end", () => {
      try { respond(req, res, proto); } catch (e) { res.writeHead(500, { "content-type": "application/json" }); res.end(JSON.stringify({ error: String(e) })); }
    });
  };
}

const PORTS = (process.env.MOCK_PORTS || "80,8080").split(",").map(Number);
for (const port of PORTS) http.createServer(handler("http")).listen(port, () => console.log("mock http", port));
let key, cert;
try { key = fs.readFileSync(path.join(ROOT, "certs", "key.pem")); cert = fs.readFileSync(path.join(ROOT, "certs", "cert.pem")); } catch {}
if (key && cert) https.createServer({ key, cert }, handler("https")).listen(443, () => console.log("mock https 443"));
