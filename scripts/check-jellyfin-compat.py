#!/usr/bin/env python3
"""Check Jellyfin integration and readiness compatibility; run from the repo root."""

import ast
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import re
import subprocess
from threading import Thread
import urllib.error
import urllib.request

import yaml


class ResponseHandler(BaseHTTPRequestHandler):
    status = 200
    body = b"[]"
    received_headers = None

    def do_GET(self):
        type(self).received_headers = self.headers
        self.rfile.read(int(self.headers.get("Content-Length", "0")))
        self.send_response(self.status)
        self.end_headers()
        self.wfile.write(self.body)

    do_POST = do_GET

    def log_message(self, *_args):
        pass


def mappings(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from mappings(value)
    elif isinstance(node, list):
        for value in node:
            yield from mappings(value)


failures = []
with HTTPServer(("127.0.0.1", 0), ResponseHandler) as server:
    thread = Thread(target=server.serve_forever)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}"
    try:
        sync_path = Path("services/media/jellyfin/manifests/sync.py")
        bazarr_path = Path("services/media/bazarr/manifests/bazarr-scripts.yaml")
        bazarr_source = yaml.safe_load(bazarr_path.read_text())["data"]["postprocess.py"]
        for path, source, function, arguments in (
            (sync_path, sync_path.read_text(), "jellyfin_api", (url, "test-key", "/Users")),
            (bazarr_path, bazarr_source, "jellyfin_refresh", ("/data/library/example",)),
        ):
            # ponytail: exercise the real HTTP helpers without unrelated LDAP/translation setup.
            definition = next(
                node for node in ast.parse(source).body
                if isinstance(node, ast.FunctionDef) and node.name == function
            )
            scope = {
                "json": json, "urllib": urllib,
                "JELLYFIN_URL": url, "JELLYFIN_TOKEN": "test-key",
            }
            exec(compile(ast.Module(body=[definition], type_ignores=[]), str(path), "exec"), scope)
            ResponseHandler.received_headers = None
            scope[function](*arguments)
            headers = ResponseHandler.received_headers
            if (
                headers is None
                or headers.get("Authorization") != 'MediaBrowser Token="test-key"'
                or "X-Emby-Token" in headers
            ):
                failures.append(f"{path}: use canonical MediaBrowser authorization")

        values = yaml.safe_load(Path("services/media/jellyfin/values.yaml").read_text())
        probes = values["controllers"]["main"]["containers"]["main"]["probes"]
        command = probes["readiness"].get("spec", {}).get("exec", {}).get("command")
        if not probes["readiness"].get("custom") or not command:
            failures.append("Jellyfin readiness must require the Healthy response body")
        else:
            command = [part.replace("http://127.0.0.1:8096", url) for part in command]
            for status, body, ready in (
                (200, b"Healthy", True),
                (200, b"Degraded", False),
                (503, b"Healthy", False),
            ):
                ResponseHandler.status, ResponseHandler.body = status, body
                result = subprocess.run(command, capture_output=True, text=True, timeout=10)
                if (result.returncode == 0) != ready:
                    failures.append(f"Readiness incorrectly handles HTTP {status} {body!r}")
    finally:
        server.shutdown()
        thread.join()

for dashboard in ("homepage", "homepage-admin"):
    chart = f"services/operations/{dashboard}/manifests"
    rendered = subprocess.run(
        ["helm", "template", dashboard, chart], capture_output=True, text=True, check=True,
    ).stdout
    configmap = next(doc for doc in yaml.safe_load_all(rendered) if doc and doc.get("kind") == "ConfigMap")
    services = yaml.safe_load(re.sub(
        r"\{\{HOMEPAGE_VAR_[A-Z0-9_]+\}\}", "test-value", configmap["data"]["services.yaml"],
    ))
    widgets = [node for node in mappings(services) if node.get("type") == "jellyfin"]
    if not widgets or any(widget.get("version") != 2 for widget in widgets):
        failures.append(f"{dashboard}: all Jellyfin widgets must use numeric version: 2")

if failures:
    raise SystemExit("\n".join(failures))
print("Jellyfin compatibility OK: authorization, readiness, and both dashboard widgets")
