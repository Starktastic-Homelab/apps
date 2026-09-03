# Home Assistant Matter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Add a loopback-only Matter.js Server sidecar to the existing Home
Assistant pod, preserve its fabric state, and compare a Roborock S8 MaxV Ultra
through native Roborock and Matter integrations.

**Architecture:** Home Assistant and Matter Server share the existing
host-network pod. Home Assistant connects to `ws://127.0.0.1:5580/ws`; Matter
Server uses `eth1` for Matter traffic and a dedicated NFS-backed `/data` claim.
Port 5580 binds only to the node-local loopback shared by the host-network pod;
no LAN or IOT interface, Service, or ingress exposes it.

**Tech Stack:** Kubernetes, Argo CD, bjw-s app-template 5.1.0, Matter.js Server
1.4.0, Home Assistant 2026.6.4, Helm, yq, kubeconform, pre-commit

---

## Scope and Constraints

Run repository commands from the isolated `apps` worktree on branch
`MrStarktastic/matter-integration-design`.

Change only:

- `renovate.json`
- `services/home-automation/home-assistant/values.yaml`
- `services/home-automation/home-assistant/manifests/pvc.yaml`

Keep these constraints throughout:

- Deploy only through Git and Argo CD. Do not use `kubectl apply`, patch a k3s
  host, or mutate OPNsense.
- Keep the Roborock on IOT. Do not expand the current firewall policy during
  this trial.
- Pin `ghcr.io/matter-js/matterjs-server` to release `1.4.0` and digest
  `sha256:54232d0d3e7dff5a54759469d2753399270412b4c30c55b31750a4595e4cb236`.
- Keep Renovate proposing routine Home Assistant pod Docker version/digest
  updates, but require manual review through the file-scoped guard because
  Home Assistant and Matter Server are a compatibility pair. Keep the
  repository-wide `vulnerabilityAlerts.automerge: true` policy unchanged for
  security remediations.
- Treat the relayed cross-VLAN mDNS path as an explicitly unsupported,
  likely-failure boundary; this trial gathers evidence for keep-or-promote
  decisions without changing that network design.
- Bind the Matter WebSocket to `127.0.0.1`, use `eth1` as the primary
  interface, and persist state under `/data`.
- Add no Service, ingress, Bluetooth device, D-Bus mount, privilege,
  attestation bypass, memory limit, automation, wrapper entity, or Home
  Assistant upgrade.
- Keep native Roborock and Matter entries separate for the entire comparison.
- If the sidecar is rolled back, retain the `matter-server-data` claim.

## File Responsibilities

- `renovate.json` keeps routine Docker version/digest updates for the Home
  Assistant values file in the normal Renovate queue while disabling
  automerge for that one chart. It does not change the repository-wide
  `vulnerabilityAlerts.automerge: true` security-remediation policy.
- `values.yaml` declares the Matter Server container, its probes and resource
  request, and container-specific volume mounts. It continues to expose only
  Home Assistant on port 8123.
- `manifests/pvc.yaml` declares the retained `matter-server-data` claim beside
  the existing Home Assistant claim.
- `app.yaml` and the shared templates are read-only inputs to rendering. They
  must not change in this phase.

## Failure Stop Rule

If commissioning or control fails, stop changing configuration and classify
the failure in this order:

1. Matter Server process and loopback WebSocket health.
2. Commissionable mDNS data arrives intact at the host: complete, internally
   consistent PTR/SRV/TXT/AAAA records, and the advertised endpoint reaches
   the host.
3. Device IPv6 address and route reachability.
4. Stateful-firewall evidence on the filtering kernel: inspect conntrack on
   the k3s node, or Proxmox only if its firewall is enabled, then inspect
   OPNsense PF state, advertised UDP port, and state-timeout behavior.
5. Roborock firmware or device-attestation behavior.

A receiving-side packet capture showing missing, malformed, or inconsistent
records is sufficient evidence against the relayed cross-VLAN path. A same-L2
control experiment requires a separately approved dedicated-VM or Home
Assistant OS design; do not move the device, the current Home Assistant
workload, or network configuration ad hoc in phase one.

Capture evidence at the first failing layer and end this phase as blocked.
Do not expose port 5580, disable attestation, add host Bluetooth, broaden
IOT-to-MAIN access, or stack another discovery proxy as a diagnostic shortcut.

### Task 1: Add the persistent Matter Server sidecar and guard its image updates

**Files:**

- Modify: `renovate.json`
- Modify: `services/home-automation/home-assistant/values.yaml:1-106`
- Modify: `services/home-automation/home-assistant/manifests/pvc.yaml:1-10`
- Test inputs: `templates/globals.yaml`, `templates/common.yaml`,
  `templates/ingress-chart/`, and
  `services/home-automation/home-assistant/app.yaml`

**Interface contract:**

- Input: Renovate package rules plus app-template 5.1.0 and the repository's
  global, common, and Home Assistant values.
- Output: a file-scoped Docker Renovate rule disables automerge for image
  updates declared in `services/home-automation/home-assistant/values.yaml`;
  one Deployment has `main` and `matter-server` containers; only
  `matter-server` mounts `/data`; only `main` mounts `/config`; all exposed
  Services and ingress routes still target port 8123.

**Step 1: RED — prove no Home Assistant image guard exists yet**

```bash
if yq -e '
  .packageRules[]
  | select(
      .matchDatasources == ["docker"]
      and .matchFileNames == ["services/home-automation/home-assistant/values.yaml"]
      and .automerge == false
    )
' renovate.json >/dev/null; then
  status=0
else
  status=$?
fi

test "$status" -eq 4
```

Expected: the query exits `4` because no matching file-scoped rule exists yet.

**Step 2: Prove the current render has no Matter Server**

```bash
helm template home-assistant \
  oci://ghcr.io/bjw-s-labs/helm/app-template \
  --version 5.1.0 \
  -f templates/globals.yaml \
  -f templates/common.yaml \
  -f services/home-automation/home-assistant/values.yaml \
  > /tmp/home-assistant-prechange.yaml

if yq -e '
  select(.kind == "Deployment")
  | .spec.template.spec.containers[]
  | select(.name == "matter-server")
' /tmp/home-assistant-prechange.yaml >/dev/null; then
  status=0
else
  status=$?
fi

rm -f /tmp/home-assistant-prechange.yaml
test "$status" -eq 4
```

Expected: Helm renders successfully, the Matter container assertion returns
`4` because no matching container exists, and the final `test` succeeds.

**Step 3: Add the Matter data claim**

Replace
`services/home-automation/home-assistant/manifests/pvc.yaml` with:

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: home-assistant-config
  namespace: home-automation
spec:
  accessModes: ["ReadWriteMany"]
  storageClassName: nfs-pv
  resources:
    requests:
      storage: 5Gi
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: matter-server-data
  namespace: home-automation
spec:
  accessModes: ["ReadWriteMany"]
  storageClassName: nfs-pv
  resources:
    requests:
      storage: 1Gi
```

The `nfs-pv` StorageClass has a `Retain` reclaim policy. Keeping this manifest
through rollback preserves the fabric data without a chart-owned claim.

**Step 4: Add the sidecar and isolate both data mounts**

Replace `services/home-automation/home-assistant/values.yaml` with:

```yaml
controllers:
  main:
    containers:
      main:
        image:
          repository: ghcr.io/home-assistant/home-assistant
          tag: 2026.6.4@sha256:adb3341e31e03e0048e60d8c1cf952e118a381ae258bb921d3da12a3b27bf0c2
        resources:
          requests:
            memory: 512Mi
        env:
          PUID: null
          PGID: null
        probes:
          liveness:
            enabled: true
            type: TCP
            port: 8123
          readiness:
            enabled: true
            type: TCP
            port: 8123
          startup:
            enabled: true
            type: TCP
            port: 8123
            spec:
              initialDelaySeconds: 10
              failureThreshold: 60
              periodSeconds: 10
      matter-server:
        image:
          repository: ghcr.io/matter-js/matterjs-server
          tag: 1.4.0@sha256:54232d0d3e7dff5a54759469d2753399270412b4c30c55b31750a4595e4cb236
        env:
          PRIMARY_INTERFACE: eth1
          LISTEN_ADDRESS: "127.0.0.1"
          STORAGE_PATH: /data
        resources:
          requests:
            cpu: 10m
            memory: 128Mi
        probes:
          liveness:
            enabled: true
            custom: true
            spec:
              tcpSocket:
                host: 127.0.0.1
                port: 5580
              failureThreshold: 3
              periodSeconds: 10
              timeoutSeconds: 2
          startup:
            enabled: true
            custom: true
            spec:
              tcpSocket:
                host: 127.0.0.1
                port: 5580
              failureThreshold: 30
              periodSeconds: 2
              timeoutSeconds: 2

defaultPodOptions:
  hostNetwork: true
  dnsPolicy: ClusterFirstWithHostNet
  securityContext:
    fsGroup: 0

service:
  main:
    controller: main
    ports:
      http:
        port: 8123
  lan:
    controller: main
    type: LoadBalancer
    externalTrafficPolicy: Local
    annotations:
      metallb.universe.tf/loadBalancerIPs: "{{ .Values.global.network.loadBalancers.homeAssistant }}"
    ports:
      http:
        port: 8123
      mdns:
        port: 5353
        protocol: UDP

persistence:
  config:
    enabled: false
  home-assistant-config:
    existingClaim: home-assistant-config
    advancedMounts:
      main:
        main:
          - path: /config
  matter-server-data:
    existingClaim: matter-server-data
    advancedMounts:
      main:
        matter-server:
          - path: /data
  media:
    enabled: false
```

The 128 MiB value is a scheduling request, not a limit. Measure real use during
the trial before changing it or constraining the Node.js heap.

**Step 5: Add the Home Assistant Renovate guard**

Add this file-scoped rule to `renovate.json`, changing no other Renovate
behavior:

```json
{
  "description": "Require manual review for Home Assistant pod image updates because Home Assistant and Matter Server are a compatibility pair",
  "matchDatasources": ["docker"],
  "matchFileNames": ["services/home-automation/home-assistant/values.yaml"],
  "automerge": false
}
```

This file-scoped guard controls routine Docker version/digest updates declared
in `services/home-automation/home-assistant/values.yaml`. It does not change
the repository-wide `vulnerabilityAlerts.automerge: true`
security-remediation policy, and it does not add a `major-update` label to
non-major Home Assistant updates.

**Step 6: Run the repository formatter and YAML/JSON linter**

```bash
pre-commit run --files \
  renovate.json \
  services/home-automation/home-assistant/values.yaml \
  services/home-automation/home-assistant/manifests/pvc.yaml
```

Expected: every applicable hook passes. If Prettier reformats any file,
inspect the result and run the same command again until it exits zero without
changes.

**Step 7: GREEN — verify the new Renovate guard**

```bash
yq -e '
  .packageRules[]
  | select(
      .matchDatasources == ["docker"]
      and .matchFileNames == ["services/home-automation/home-assistant/values.yaml"]
      and .automerge == false
    )
' renovate.json
```

Expected: the query prints the new rule and exits zero.

**Step 8: Render the application and ingress**

```bash
helm template home-assistant \
  oci://ghcr.io/bjw-s-labs/helm/app-template \
  --version 5.1.0 \
  -f templates/globals.yaml \
  -f templates/common.yaml \
  -f services/home-automation/home-assistant/values.yaml \
  > /tmp/home-assistant-rendered.yaml

helm template home-assistant-ingress \
  templates/ingress-chart \
  -f templates/globals.yaml \
  -f services/home-automation/home-assistant/app.yaml \
  > /tmp/home-assistant-ingress-rendered.yaml
```

Expected: both commands exit zero. Helm reports app-template digest
`sha256:0d039f7760db66790168e9de13780327ad1adecca0a3b31621e32146d8be503c`.

**Step 9: Assert the rendered security and mount contract**

```bash
set -euo pipefail

test "$(yq -r '
  select(.kind == "Deployment")
  | [.spec.template.spec.containers[].name]
  | length
' /tmp/home-assistant-rendered.yaml)" = "2"

yq -e '
  select(.kind == "Deployment")
  | .spec.template.spec.containers[]
  | select(.name == "matter-server")
  | select(
      .image
      == "ghcr.io/matter-js/matterjs-server:1.4.0@sha256:54232d0d3e7dff5a54759469d2753399270412b4c30c55b31750a4595e4cb236"
    )
  | select(any(.env[];
      .name == "PRIMARY_INTERFACE" and .value == "eth1"))
  | select(any(.env[];
      .name == "LISTEN_ADDRESS" and .value == "127.0.0.1"))
  | select(any(.env[];
      .name == "STORAGE_PATH" and .value == "/data"))
  | select(all(.env[];
      .name != "BLUETOOTH_ADAPTER" and .name != "BLE_PROXY"))
  | select(.resources.requests.cpu == "10m")
  | select(.resources.requests.memory == "128Mi")
  | select(((.resources.limits // {}) | length) == 0)
  | select(
      .startupProbe.tcpSocket.host == "127.0.0.1"
      and .startupProbe.tcpSocket.port == 5580
    )
  | select(
      .livenessProbe.tcpSocket.host == "127.0.0.1"
      and .livenessProbe.tcpSocket.port == 5580
    )
  | select(.readinessProbe == null)
  | select(.securityContext.privileged != true)
  | select(any(.volumeMounts[];
      .name == "matter-server-data" and .mountPath == "/data"))
  | select(all(.volumeMounts[];
      .name == "matter-server-data" and .mountPath == "/data"))
' /tmp/home-assistant-rendered.yaml >/dev/null

yq -e '
  select(.kind == "Deployment")
  | .spec.template.spec.containers[]
  | select(.name == "main")
  | select(any(.volumeMounts[];
      .name == "home-assistant-config" and .mountPath == "/config"))
  | select(all(.volumeMounts[];
      .name != "matter-server-data"))
' /tmp/home-assistant-rendered.yaml >/dev/null

! yq -e '
  select(.kind == "Service")
  | .spec.ports[]
  | select(.port == 5580 or .targetPort == 5580)
' /tmp/home-assistant-rendered.yaml >/dev/null

yq -e '
  select(.kind == "IngressRoute")
  | .spec.routes[].services[]
  | select(.name == "home-assistant-main" and .port == 8123)
' /tmp/home-assistant-ingress-rendered.yaml >/dev/null

! yq -e '
  select(.kind == "IngressRoute")
  | .spec.routes[].services[]
  | select(.port == 5580)
' /tmp/home-assistant-ingress-rendered.yaml >/dev/null

echo "Rendered Matter contract passed"
```

Expected: `Rendered Matter contract passed`. A missing sidecar, wrong digest,
non-loopback probe, leaked mount, readiness probe, resource limit, Bluetooth
configuration, or port-5580 exposure makes this step fail.

**Step 10: Validate every changed and rendered Kubernetes object**

```bash
kubeconform \
  -verbose \
  -summary \
  -ignore-missing-schemas \
  -schema-location default \
  -schema-location \
  'https://raw.githubusercontent.com/datreeio/CRDs-catalog/main/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json' \
  services/home-automation/home-assistant/manifests/pvc.yaml \
  /tmp/home-assistant-rendered.yaml \
  /tmp/home-assistant-ingress-rendered.yaml
```

Expected summary: `8 resources found in 3 files - Valid: 8, Invalid: 0,
Errors: 0, Skipped: 0`.

**Step 11: Inspect the focused change and clean generated files**

```bash
git diff --check
git diff -- \
  renovate.json \
  services/home-automation/home-assistant/values.yaml \
  services/home-automation/home-assistant/manifests/pvc.yaml
rm -f \
  /tmp/home-assistant-rendered.yaml \
  /tmp/home-assistant-ingress-rendered.yaml
git status --short
```

Expected: only the three intended files are modified; the diff contains one
file-scoped Renovate rule, one new PVC, one sidecar, and two
container-scoped mounts.

**Step 12: Commit the phase-one change**

```bash
git add \
  renovate.json \
  services/home-automation/home-assistant/values.yaml \
  services/home-automation/home-assistant/manifests/pvc.yaml
git commit \
  -m "feat: add Home Assistant Matter server sidecar" \
  -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

Expected: one focused phase-one commit. Do not push, open or merge a pull
request, or resolve review threads on the user's behalf.

**Verification:** Task 1 Steps 6-11 prove formatting, the Renovate guard,
schema validity, the two-container render, loopback-only port 5580, and mount
isolation.

**Commit:** Task 1 Step 12 creates the single focused phase-one commit.

### Task 2: Verify the GitOps deployment

**Files:** None

**Dependency:** Task 1's commit must be merged to `main` by the user and
reconciled by Argo CD. Stop at this gate; do not bypass it with an imperative
cluster change.

**Step 1: Confirm Argo CD reconciliation and rollout health**

```bash
kubectl -n argocd get application home-assistant \
  -o jsonpath='{.status.sync.status}{"\t"}{.status.health.status}{"\n"}'
kubectl -n home-automation rollout status \
  deployment/home-assistant \
  --timeout=5m
```

Expected: `Synced Healthy` and a successful Deployment rollout.

**Step 2: Confirm both containers and the bound claim**

```bash
kubectl -n home-automation get deployment home-assistant \
  -o jsonpath='{range .spec.template.spec.containers[*]}{.name}{"\t"}{.image}{"\n"}{end}'
kubectl -n home-automation get pvc matter-server-data
kubectl -n home-automation get pods \
  -l app.kubernetes.io/instance=home-assistant \
  -o jsonpath='{range .items[0].status.containerStatuses[*]}{.name}{"\tready="}{.ready}{"\trestarts="}{.restartCount}{"\n"}{end}'
```

Expected:

- `main` retains the pinned Home Assistant image.
- `matter-server` uses the exact 1.4.0 digest from Task 1.
- `matter-server-data` is `Bound`, `RWX`, and 1 GiB.
- Both containers are ready without an ongoing restart loop.

**Step 3: Prove a real WebSocket handshake from Home Assistant**

```bash
kubectl -n home-automation exec -i \
  deployment/home-assistant \
  -c main \
  -- python - <<'PY'
import asyncio

from aiohttp import ClientSession, ClientTimeout


async def main() -> None:
    timeout = ClientTimeout(total=5)
    async with ClientSession(timeout=timeout) as session:
        async with session.ws_connect("ws://127.0.0.1:5580/ws"):
            print("Matter WebSocket handshake succeeded")


asyncio.run(main())
PY
```

Expected: `Matter WebSocket handshake succeeded`.

**Step 4: Prove that the unprivileged sidecar can write its PVC**

```bash
kubectl -n home-automation exec \
  deployment/home-assistant \
  -c matter-server \
  -- sh -ceu '
    test -w /data
    printf "%s\n" ok > /data/.matter-server-write-check
    test "$(cat /data/.matter-server-write-check)" = ok
    rm /data/.matter-server-write-check
  '
```

Expected: exit zero with no retained test file. `nfs-subdir-external-provisioner`
should create the claim directory with mode `0777`, which already permits the
image's built-in `1000:1000` user. If this fails, inspect the Matter Server
logs for a permission error, classify it as a storage-provisioning defect, and
fix NFS/provisioner ownership or permissions through separate
infrastructure-as-code. Do not run an ad-hoc `chown` on the NFS host, run the
container as root, or add a privileged init container.

**Step 5: Capture the kernel UDP assured-timeout value without changing it**

```bash
kubectl -n home-automation exec \
  deployment/home-assistant \
  -c main \
  -- cat /proc/sys/net/netfilter/nf_conntrack_udp_timeout_stream
```

Expected: one integer value from the host-network pod's kernel namespace. A
value below `1800` is not itself a failure when no stateful firewall on that
kernel filters the Matter flow. Inspect this on the k3s node kernel, or on
Proxmox only when its firewall is enabled, before blaming that timeout. Do
not change a sysctl in this phase.

**Step 6: Check startup state and resource use**

```bash
kubectl -n home-automation logs \
  deployment/home-assistant \
  -c matter-server \
  --since=10m
kubectl -n home-automation top pod \
  -l app.kubernetes.io/instance=home-assistant \
  --containers
```

Expected: Matter Server reports `/data` as its storage location, listens on
loopback port 5580, and has no crash, bind, or permission error. Record the
sidecar's initial memory use; do not add a limit based on a single sample.

**Verification:** Tasks 2 Steps 1-6 are the deployment acceptance check.

**Commit:** None; this task must not mutate repository or cluster
configuration.

### Task 3: Configure native Roborock and Matter side by side

**Files:** None. These are owner-operated Home Assistant and mobile-app
actions stored in the existing Home Assistant configuration volume.

**Step 1: Connect Home Assistant to the custom Matter Server**

In Home Assistant:

1. Open **Settings > Devices & services > Add integration > Matter**.
2. On **Select the connection method**, deselect the option to use the
   official Matter Server app, then submit.
3. Enter `ws://127.0.0.1:5580/ws`.
4. Finish the config flow before opening a pairing window on the vacuum.

Expected: the Matter integration loads without a repair or compatibility
error. It has no device until commissioning in Step 4.

If version negotiation fails, stop. Capture the config-flow error and both
container logs; do not pair the vacuum, upgrade Home Assistant opportunistically,
or replace the pinned server without a separate compatibility decision.

**Step 2: Configure the native Roborock integration**

In Home Assistant:

1. Open **Settings > Devices & services > Add integration > Roborock**.
2. Enter the email used by the Roborock app, leave region on **Auto**, and
   submit the emailed verification code.
3. Open the discovered S8 MaxV Ultra device.

Expected: Home Assistant creates the native device and exposes its supported
vacuum, map, room, cleaning-mode, dock, and maintenance entities. Account
credentials and the verification code stay in the Home Assistant UI; do not
write them to Git or terminal history.

**Step 3: Establish the native baseline**

From the native Roborock device entry, verify:

- live status and map load;
- start, pause, and return-to-dock;
- one room-clean action;
- at least one supported dock action;
- maintenance values and state updates.

Record available entities/actions, command success, approximate command
latency, and state-update delay. Do not create an automation, template entity,
or comparison dashboard.

**Step 4: Commission the vacuum onto Home Assistant's Matter fabric**

1. Confirm the Roborock firmware is current and the vacuum remains connected
   to IOT Wi-Fi.
2. In the Roborock app, open the S8 MaxV Ultra's Matter setup and start its
   commissioning window.
3. In the Home Assistant Companion app, open
   **Settings > Connectivity > Matter > Add device** and scan or enter the
   code supplied by Roborock.
4. Treat it as a new Matter device unless the Roborock flow explicitly says
   it is already commissioned to another Matter fabric.

Expected: the same physical vacuum appears as a separate Matter device without
removing the native Roborock device.

If Roborock reports a certificate, firmware, or attestation failure, stop and
record it. Do not bypass attestation or choose an uncertified-device override.

**Step 5: Exercise the Matter surface**

Inventory every entity and action that the Matter entry actually exposes,
then test start, pause, stop, return home, locate, state updates, and
cleanable-area control when present.

Record the same success, latency, and update-delay observations used for the
native baseline. Missing optional Matter capabilities are comparison results,
not deployment failures.

**Verification:** Both entries control the same vacuum independently and
remain visibly separate. Native Roborock completes its richer baseline;
Matter completes every advertised basic control without exposing port 5580.

**Commit:** None; Home Assistant integration state is intentionally managed
through the application UI.

### Task 4: Validate idle recovery, pod replacement, and seven-day use

**Files:** None

**Step 1: Run one normal cleaning cycle**

Use the vacuum normally from start through docking. Confirm both entries
report the resulting cleaning and dock states correctly.

**Step 2: Test ordinary idle recovery**

Leave the vacuum idle for at least 30 minutes. Then issue one command through
Matter and one through native Roborock, and verify both state paths update.

Expected: neither path needs a reload or re-pair after ordinary
stateful-firewall UDP state expiry windows.

**Step 3: Replace the Home Assistant pod without changing Git state**

```bash
set -euo pipefail

namespace=home-automation
selector='app.kubernetes.io/instance=home-assistant'

pvc_uid_before="$(
  kubectl -n "$namespace" get pvc matter-server-data \
    -o jsonpath='{.metadata.uid}'
)"
pod_before="$(
  kubectl -n "$namespace" get pod -l "$selector" \
    -o jsonpath='{.items[0].metadata.name}'
)"
node_before="$(
  kubectl -n "$namespace" get pod "$pod_before" \
    -o jsonpath='{.spec.nodeName}'
)"

kubectl -n "$namespace" delete pod "$pod_before" --wait=true
kubectl -n "$namespace" wait \
  --for=condition=Ready \
  pod \
  -l "$selector" \
  --timeout=5m

pod_after="$(
  kubectl -n "$namespace" get pod -l "$selector" \
    -o jsonpath='{.items[0].metadata.name}'
)"
node_after="$(
  kubectl -n "$namespace" get pod "$pod_after" \
    -o jsonpath='{.spec.nodeName}'
)"
pvc_uid_after="$(
  kubectl -n "$namespace" get pvc matter-server-data \
    -o jsonpath='{.metadata.uid}'
)"

test "$pod_before" != "$pod_after"
test "$pvc_uid_before" = "$pvc_uid_after"
printf 'pod: %s@%s -> %s@%s\n' \
  "$pod_before" "$node_before" "$pod_after" "$node_after"
printf 'persistent claim UID: %s\n' "$pvc_uid_after"
```

Expected: Kubernetes creates a differently named pod, the claim UID is
unchanged, and both containers become ready. The new pod may run on the same
or a different node; either outcome exercises pod replacement.

**Step 4: Recheck WebSocket and application recovery**

```bash
kubectl -n home-automation exec -i \
  deployment/home-assistant \
  -c main \
  -- python - <<'PY'
import asyncio

from aiohttp import ClientSession, ClientTimeout


async def main() -> None:
    timeout = ClientTimeout(total=5)
    async with ClientSession(timeout=timeout) as session:
        async with session.ws_connect("ws://127.0.0.1:5580/ws"):
            print("Matter WebSocket recovered after pod replacement")


asyncio.run(main())
PY
```

In Home Assistant, verify that the native entry, Matter integration, and
commissioned vacuum recover without reauthentication or re-pairing. Exercise
one command through each path.

**Step 5: Observe seven days without adding telemetry**

Use existing Home Assistant history and logs during normal use. At the end of
the period, run:

```bash
kubectl -n home-automation get pods \
  -l app.kubernetes.io/instance=home-assistant \
  -o jsonpath='{range .items[0].status.containerStatuses[*]}{.name}{"\tready="}{.ready}{"\trestarts="}{.restartCount}{"\n"}{end}'
kubectl -n home-automation top pod \
  -l app.kubernetes.io/instance=home-assistant \
  --containers
kubectl -n home-automation logs \
  deployment/home-assistant \
  -c matter-server \
  --since=168h
```

Review:

- available entities and actions;
- command success and practical latency;
- state correctness and update delay;
- room, map, dock, and maintenance coverage;
- recovery after idle time and pod replacement;
- observed cloud dependence;
- sidecar restart count and memory trend.

**Step 6: Apply the approved promotion gate**

- Keep the sidecar if pairing, subscriptions, commands, idle recovery, and pod
  replacement stayed reliable.
- Start a separate dedicated-VM design only if Matter Server and Home
  Assistant stayed healthy while packet, conntrack, or PF-state evidence
  repeatedly identified the VLAN boundary, relayed mDNS, IPv6 routing, or
  state timeout as the failure.
- Start a separate Home Assistant OS migration design only if unsupported
  server maintenance or an owned, supported Thread stack justifies the larger
  migration.

One commissioning failure without network evidence is not a promotion
decision. Do not change OPNsense, add another discovery proxy, or start either
promotion from this plan.

**Verification:** Seven days of normal use produce a clear keep/promote
decision based on the approved criteria.

**Commit:** None; this task records operational evidence only.

## Conditional Rollback

Use this only if the Matter sidecar blocks Home Assistant recovery or the
Matter integration cannot pass version negotiation.

1. If Home Assistant is reachable, remove its Matter integration entry first.
   If it is not reachable, perform the Git rollback first and remove the stale
   entry after Home Assistant returns.
2. In `renovate.json`, delete only the file-scoped Docker package rule for
   `services/home-automation/home-assistant/values.yaml`. In `values.yaml`,
   delete only
   `controllers.main.containers.matter-server` and
   `persistence.matter-server-data`.
3. Keep the Home Assistant `/config` `advancedMounts` conversion and keep the
   entire `matter-server-data` PVC document in `manifests/pvc.yaml`.
4. Verify the rollback without changing the cluster:

```bash
set -euo pipefail

pre-commit run --files \
  renovate.json \
  services/home-automation/home-assistant/values.yaml \
  services/home-automation/home-assistant/manifests/pvc.yaml

helm template home-assistant \
  oci://ghcr.io/bjw-s-labs/helm/app-template \
  --version 5.1.0 \
  -f templates/globals.yaml \
  -f templates/common.yaml \
  -f services/home-automation/home-assistant/values.yaml \
  > /tmp/home-assistant-rollback.yaml

helm template home-assistant-ingress \
  templates/ingress-chart \
  -f templates/globals.yaml \
  -f services/home-automation/home-assistant/app.yaml \
  > /tmp/home-assistant-ingress-rollback.yaml

! yq -e '
  .packageRules[]
  | select(
      .matchDatasources == ["docker"]
      and .matchFileNames == ["services/home-automation/home-assistant/values.yaml"]
      and .automerge == false
    )
' renovate.json >/dev/null

test "$(yq -r '
  select(.kind == "Deployment")
  | [.spec.template.spec.containers[].name]
  | length
' /tmp/home-assistant-rollback.yaml)" = "1"

! yq -e '
  select(.kind == "Deployment")
  | .spec.template.spec.containers[]
  | select(.name == "matter-server")
' /tmp/home-assistant-rollback.yaml >/dev/null

yq -e '
  select(.kind == "Deployment")
  | .spec.template.spec.containers[]
  | select(.name == "main")
  | select(any(.volumeMounts[];
      .name == "home-assistant-config" and .mountPath == "/config"))
' /tmp/home-assistant-rollback.yaml >/dev/null

! yq -e '
  select(.kind == "Service")
  | .spec.ports[]
  | select(.port == 5580 or .targetPort == 5580)
' /tmp/home-assistant-rollback.yaml >/dev/null

! yq -e '
  select(.kind == "IngressRoute")
  | .spec.routes[].services[]
  | select(.port == 5580)
' /tmp/home-assistant-ingress-rollback.yaml >/dev/null

kubeconform \
  -verbose \
  -summary \
  -ignore-missing-schemas \
  -schema-location default \
  -schema-location \
  'https://raw.githubusercontent.com/datreeio/CRDs-catalog/main/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json' \
  services/home-automation/home-assistant/manifests/pvc.yaml \
  /tmp/home-assistant-rollback.yaml \
  /tmp/home-assistant-ingress-rollback.yaml

git diff --check
rm -f \
  /tmp/home-assistant-rollback.yaml \
  /tmp/home-assistant-ingress-rollback.yaml
```

Expected: applicable hooks pass; the render has one `main` container, no
Matter container or port-5580 exposure, and still mounts `/config`; kubeconform
reports all eight objects valid.

5. Commit the rollback:

```bash
git add \
  renovate.json \
  services/home-automation/home-assistant/values.yaml
git commit \
  -m "revert: disable Home Assistant Matter server sidecar" \
  -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

The user still owns push and merge. The native Roborock integration remains
available, the claim remains declared, and no OPNsense, Terraform, Ansible, or
k3s host rollback is required.
