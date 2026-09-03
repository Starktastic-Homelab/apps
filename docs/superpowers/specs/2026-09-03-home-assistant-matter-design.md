# Home Assistant Matter Integration Design

**Date:** 2026-09-03  
**Status:** Approved

## Goal

Add usable Matter support to the existing Home Assistant deployment without
prematurely migrating platforms. Compare the Roborock S8 MaxV Ultra through
both Home Assistant's native Roborock integration and Matter, then keep each
path only for what it does better.

The first rollout prioritizes Matter over Wi-Fi/Ethernet. Thread remains a
future option, but the design does not depend on the Apple border routers
currently present on the network.

## Current State

- Home Assistant runs from
  `services/home-automation/home-assistant/values.yaml` as a container on k3s.
- Its pod already uses `hostNetwork: true` and
  `dnsPolicy: ClusterFirstWithHostNet`.
- The pod currently runs on `kube-master-01`, where `eth1` is attached to MAIN
  (`10.9.8.0/24`) and has working IPv6 addresses and a default IPv6 route.
- Nothing listens on `127.0.0.1:5580`, so Home Assistant correctly rejects the
  default `ws://localhost:5580/ws` Matter Server URL.
- OPNsense routes between MAIN and IOT (`10.9.50.0/24`). Both networks have
  static ULA IPv6 prefixes.
- OPNsense's mDNS repeater currently joins MAIN and IOT, which explains why
  Home Assistant can discover Matter advertisements across the VLAN boundary.
- OPNsense has an `Allow Matter` rule from IOT to MAIN limited to port 5540.
  Matter does not guarantee port 5540: devices advertise ports and controllers
  use ephemeral UDP ports, so this rule is not treated as proof of a correct
  Matter path.
- Two Apple Thread border routers, `Bedroom` and `Office`, advertise the
  `MyHome99` Thread network on MAIN. They may be tested later but are not a
  dependency.
- The S8 MaxV Ultra is already connected to IOT Wi-Fi. Home Assistant's native
  Roborock integration supports the S series and provides substantially more
  vacuum-specific functionality than Matter.

## Constraints

- Keep the Roborock on the IOT VLAN.
- Keep all deployable infrastructure changes in Git. Do not mutate k3s hosts or
  OPNsense ad hoc.
- Do not expose the Matter Server's unauthenticated WebSocket or dashboard.
- Persist Matter fabric keys and pairings across pod replacement.
- Do not weaken device attestation or add broad firewall access to force
  commissioning.
- Do not make Thread or a Home Assistant OS migration part of the first
  rollout.
- Do not build automations against either Roborock entry until the comparison
  is complete.

Home Assistant integration setup remains application state stored in the
existing Home Assistant configuration volume; it is not host infrastructure.

## Approaches Considered

| Approach | Advantages | Costs |
| --- | --- | --- |
| Matter Server sidecar in the existing Home Assistant pod | Smallest change; exact `127.0.0.1` WebSocket URL; no exposed WebSocket; reuses host networking | Self-managed deployment is unsupported upstream; cross-VLAN Matter remains experimental; sidecar health is coupled to the Home Assistant pod |
| Dedicated dual-homed Matter Server VM | Direct IOT attachment; stable address and firewall target; Home Assistant remains on k3s | Adds a VM, Terraform and Ansible work, and an exposed inter-host WebSocket; still a self-managed unsupported server |
| Full Home Assistant OS migration | Official Matter app and the best-tested Matter/Thread host behavior | Full Home Assistant migration and larger network/storage blast radius; direct VLAN placement still needs design |

## Decision

Use the sidecar first and define evidence-based promotion gates.

This is a reversible experiment, not a claim that relayed mDNS across VLANs is
an upstream-supported production topology. A dedicated VM or Home Assistant OS
migration gets its own design only if the trial proves the smaller deployment
insufficient.

Phase one modifies only:

- `renovate.json` to require manual review for every Docker image declared in
  the Home Assistant pod because Home Assistant and Matter Server are a
  compatibility pair even when Renovate proposes the update. This file-scoped
  guard covers routine Docker version/digest updates; the repository-wide
  `vulnerabilityAlerts.automerge: true` security-remediation policy stays
  unchanged.
- `services/home-automation/home-assistant/values.yaml` for the sidecar,
  loopback probes, and volume mount.
- `services/home-automation/home-assistant/manifests/pvc.yaml` for a named
  Matter data claim.

The native Roborock and Matter integrations are configured after deployment
through Home Assistant's normal UI. No Ansible, Terraform, OPNsense, or k3s
host file changes are part of phase one.

## Architecture

The existing Home Assistant Deployment remains the only Kubernetes workload
changed in phase one. Its pod gains a second container:

```text
Home Assistant container
        |
        | ws://127.0.0.1:5580/ws
        v
Matter Server sidecar -- eth1 / IPv6 --> OPNsense --> IOT --> Roborock
        |
        v
separate persistent /data volume
```

The sidecar uses the official
`ghcr.io/matter-js/matterjs-server` image at release `1.4.0`, pinned to an
immutable digest following repository convention. Matter Server 1.4.0 retains
backward-compatible WebSocket schemas for older clients; Home Assistant's
config flow remains the final compatibility check before any device is paired.

The container inherits the pod's existing host network and uses:

- `PRIMARY_INTERFACE=eth1` for Matter discovery and device traffic.
- `LISTEN_ADDRESS=127.0.0.1` so the unauthenticated WebSocket and dashboard
  bind to the k3s node's loopback namespace shared by this `hostNetwork` pod.
- `STORAGE_PATH=/data` for persistent fabric state.
- No Bluetooth adapter, D-Bus socket, privileged mode, Service, LoadBalancer,
  or ingress.

The existing app-template chart already supports multiple containers and
container-specific `advancedMounts`. The existing PVC manifest gains a named
1 GiB `nfs-pv` claim; `values.yaml` references that claim and mounts it at
`/data` only in the Matter Server container. Keeping the claim as a separate
manifest lets rollback remove the sidecar without pruning its fabric state.
The Home Assistant configuration volume is not exposed to the sidecar.

## Components and Data Flow

### Matter Server

Matter Server owns the Matter fabric, device credentials, subscriptions, and
local device communication. Home Assistant is its sole configured WebSocket
client.

The Home Assistant Companion app handles commissioning. For the already
networked Roborock, the Roborock app opens a Matter commissioning window and
provides the pairing code; no Bluetooth hardware is required on a k3s node.

### Home Assistant Matter Integration

The Matter integration connects to `ws://127.0.0.1:5580/ws`. Its config flow
must establish a real WebSocket connection and validate the server version
before creating the config entry.

Matter exposes the standard vacuum capabilities the device advertises, such as
start, stop, pause, return home, locate, state, and optional cleanable areas.
The trial records what the S8 MaxV Ultra actually implements rather than
assuming feature parity from the specification.

### Native Roborock Integration

The built-in Roborock integration performs account discovery through
Roborock's service, then prefers local polling to the vacuum on TCP 58867 with
cloud fallback. It provides the richer device path: maps, rooms, cleaning
modes, dock controls, maintenance data, and Roborock-specific actions.

The native and Matter device entries remain separate during the trial. No
template entities, wrappers, or synchronization automations hide their
differences.

### Network

Phase one reuses the current MAIN-to-IOT IPv6 routing and mDNS repeater without
changing OPNsense. The relayed cross-VLAN mDNS path remains an explicitly
unsupported, likely-failure boundary; the seven-day trial keeps it unchanged so
promotion decisions rely on packet evidence instead of assumptions.

The existing port-5540 rule is not expanded, replaced, or cited as a
requirement in this phase. If packet evidence later proves a PF rule or state
timeout is the failure, that change must be address-scoped, managed as code,
and designed separately. It must not assume a fixed Matter UDP port.

## Security and Failure Handling

- With `hostNetwork: true`, Matter Server binds its unauthenticated dashboard
  and WebSocket to the k3s node's loopback namespace. Home Assistant is the
  sole configured client, but other host processes or host-network pods on the
  same node could also reach it. MAIN and IOT still cannot reach it through a
  network interface, Service, or ingress.
- Device attestation remains enabled. Certificate or firmware failures are
  surfaced rather than bypassed.
- The image is version- and digest-pinned. Renovate can still propose later
  Home Assistant pod image updates, but the file-scoped rule requires manual
  review because Home Assistant and Matter Server are a compatibility pair.
- Fabric state is isolated on persistent storage and survives pod replacement.
- A startup probe prevents premature liveness failures while Matter Server
  initializes.
- A liveness probe restarts only a wedged Matter Server container.
- The sidecar has no readiness probe, so a temporary Matter failure does not
  deliberately remove Home Assistant's service endpoint.

A crash-looping sidecar can still make the shared pod unready. This is the
accepted ceiling of the minimal design. The immediate rollback is to remove
the sidecar while retaining its PVC; the native Roborock integration continues
to provide vacuum control.

Failures are classified in this order:

1. Matter Server process and loopback WebSocket health.
2. Commissionable mDNS data arrives intact at the host: complete, internally
   consistent PTR/SRV/TXT/AAAA records, and the advertised endpoint reaches
   the host.
3. IPv6 address and route reachability.
4. Stateful-firewall evidence on the filtering kernel: inspect conntrack on
   the k3s node, or Proxmox only if its firewall is enabled, then inspect
   OPNsense PF state, advertised UDP port, and timeout behavior.
5. Roborock device attestation or firmware behavior.

A receiving-side packet capture showing missing, malformed, or inconsistent
records is sufficient evidence against the relayed cross-VLAN path. A same-L2
control experiment requires a separately approved dedicated-VM or Home
Assistant OS design; do not move the device, the current Home Assistant
workload, or network configuration ad hoc in phase one.

Do not respond to a failure by exposing port 5580, disabling attestation,
mounting host Bluetooth, opening all IOT-to-MAIN traffic, or stacking another
discovery proxy.

## Validation and Comparison

### Repository Checks

Render the existing app-template values and verify:

- One pod contains the Home Assistant and Matter Server containers.
- Only Matter Server receives the `/data` mount.
- Matter Server listens on loopback port 5580.
- No Service or ingress exposes port 5580.

Run the apps repository's existing formatting and schema validation. Do not
add a test framework.

### Runtime Acceptance

1. Confirm Home Assistant reaches `ws://127.0.0.1:5580/ws` and creates the
   Matter integration.
2. Configure the native Roborock integration and verify local status, map,
   start, pause, dock, and one room-clean action.
3. Open the Roborock Matter commissioning window, pair the same vacuum, and
   exercise every Matter control it exposes.
4. Complete one normal cleaning cycle.
5. Leave the vacuum idle for at least 30 minutes, then verify that state
   changes and commands still work after ordinary stateful-firewall UDP state
   expiry windows.
6. Restart or reschedule the Home Assistant pod once. Verify that Matter
   pairings, the native entry, and both control paths recover without
   re-pairing.
7. Observe seven days of normal use through existing Home Assistant history
   and logs. Add no comparison dashboard or metrics pipeline.

Compare:

- available entities and actions;
- command success and latency;
- state correctness and update delay;
- room, map, dock, and maintenance coverage;
- recovery after idle time and pod replacement;
- practical cloud dependence.

## Promotion Gates

### Keep the Sidecar

Keep phase one when pairing, commands, state subscriptions, idle recovery, and
pod replacement remain reliable throughout the trial. Continue using native
Roborock for rich controls and Matter for interoperability.

### Promote to a Dedicated Matter VM

Create a separate design for a dual-homed MAIN/IOT VM only when:

- Matter Server and Home Assistant remain healthy; and
- packet, conntrack, or PF-state evidence repeatedly identifies the VLAN
  boundary, relayed mDNS, IPv6 route handling, or state timeout as the
  failure.

The VM would place Matter traffic directly on IOT while binding its WebSocket
only to a MAIN address allowed from Home Assistant. A future owned Thread
border router would also live on IOT. The existing Apple border routers remain
optional.

### Promote to Home Assistant OS

Create a migration design only when the operational cost of maintaining an
unsupported standalone Matter Server, or the need for a supported owned Thread
stack, outweighs the cost of moving Home Assistant. One vacuum or one
unexplained commissioning failure is not sufficient evidence.

## Rollback

1. Remove the Matter integration entry from Home Assistant.
2. Remove the file-scoped Home Assistant Docker automerge guard from
   `renovate.json`.
3. Remove the Matter Server container configuration from the Home Assistant
   values.
4. Leave the Matter data claim in the PVC manifest until the trial decision is
   final.
5. Keep the native Roborock integration.

No OPNsense, Terraform, Ansible, or k3s host rollback is needed because phase
one changes none of them.

## References

- [Home Assistant Matter integration](https://www.home-assistant.io/integrations/matter/)
- [Home Assistant Roborock integration](https://www.home-assistant.io/integrations/roborock/)
- [Matter.js Server Docker guidance](https://github.com/matter-js/matterjs-server/blob/main/docs/docker.md)
- [Matter.js Server OS and network requirements](https://github.com/matter-js/matterjs-server/blob/main/docs/os_requirements.md)
- [Matter.js WebSocket schema changelog](https://github.com/matter-js/matterjs-server/blob/main/docs/websocket-api-schema-changelog.md)
