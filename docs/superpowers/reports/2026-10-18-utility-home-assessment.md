# Utility, download and MQTT storage assessment

Read-only production inspection on18October2026 found all eight named Apps ready and Synced. No production data, credentials, ownership or workload was changed during assessment.

| App | Current private state | Candidate retained disk |
| --- | --- | --- |
| qBittorrent | About484MiB;4055 torrent/fastresume pairs, settings, categories, tags and VueTorrent module cache |2GiB |
| qBittorrent RU | About15MiB;5 torrent/fastresume pairs and the same native layout |1GiB |
| Changedetection | Native JSON/settings, two watch directories and application secret |1GiB |
| Stirling-PDF | Settings, H2 MVStore2.3.232, native database backups/cache |1GiB |
| Microbin | SQLite database and complete attachment tree |1GiB |
| Lingarr | Existing PostgreSQL integration plus local.db, Hangfire.db and data-protection keys |1GiB |
| Mosquitto | Persistent MQTT broker state currently lacks a working disk path |1GiB |
| Zigbee2MQTT | Coordinator/network backup, device database, configuration and runtime state; two native identities |1GiB |

Shared media and incomplete-download payloads remain on their existing NFS claims, preserving paths/hardlinks and torrent behavior. The current file modes/owners are preserved; the startup guard runs as the native file owner with capabilities dropped.

## Native findings

Mosquitto2.0.22 enables persistence but points at`/config/data/`; its PVC is mounted at`/mosquitto/data/`, and the configured path does not exist. The migration protects current in-memory state through a temporary in-container path alias and native SIGUSR1 flush, followed by graceful shutdown. The final ConfigMap uses`/mosquitto/data/`. An isolated exact-image fixture proved that retained MQTT messages survive this repair and recreation. No device commands are published in production.

qBittorrent5.2.3 uses native fastresume files. An isolated exact-image fixture proved that s6 can stop its service gracefully while retaining the container, write resume state and reload the exact synthetic torrent identity. This avoids relying on the source Pod's30-second deletion grace for4055 records. The target has600seconds of termination grace. Main and RU are populated/qualified before one paired activation PR because RU inherits main values.

All read-only native production checks passed: both torrent inventories, both Changedetection watch identities, existing HTTP/auth behavior, Mosquitto version, and coordinator/network/device identity parsing. Tests refuse absent/wrong/linked identities, invalid native formats, an empty Zigbee database and truncated MQTT persistence. The MQTT guard checks native version6 chunk bounds/configuration without modifying the file.

Lingarr and Zigbee2MQTT offline fixtures validate recovered files with their pinned stock images and active SQLite integrity where applicable. They do not contact the shared PostgreSQL backend or radio. Their real backend/device acceptance is a separate production gate after complete cold recovery has passed. All other apps additionally start their exact stock images on recovered copies without external networking. qBittorrent's external module fetching is excluded from isolated fixtures; all existing module-cache bytes remain in the complete recovery/population proof.

Stirling's external database support requires a paid plan; this scope preserves the installed H2 backend and login settings. Image updates require review of the retained H2 filename/engine. [Official database configuration](https://docs.stirlingpdf.com/Configuration/Storage/External%20Database/), [plan capabilities](https://docs.stirlingpdf.com/Server/Licensing/Plans-and-Licences/).

## Capacity and rebuild contract

Dataset`apps/k3s-block`, GUID13918781591004512447, currently has a256GiB quota,205GiB of active logical raw images and about164.78GiB of remaining committed growth. Snapshot/historical allocation means eight new images do not fit alongside staging and8GiB spare under that ceiling. The user approved raising only this quota to288GiB; execution remains pending. The pool is healthy with about259GiB physical free at assessment.

The fixed cohort maximum is9GiB. Before every allocation, check full remaining growth of existing images, unallocated cohort images,512MiB staging and8GiB spare against both fresh dataset availability and physical pool free. Preserve the historical Jellyfin partial and all unrelated images. Static upstream CSI disks remain outside worker ownership, with Retain/RWOP bindings and native read-only startup guards; Kubernetes metadata is reconstructible from Git without a Velero checkpoint.

## Vikunja retirement

The user requested complete removal. Its PostgreSQL database/role are dedicated, with no role memberships or ownership outside that database. Its Authentik application/provider are dedicated; the group binding refers to shared identity infrastructure and that group must remain. Remove active GitOps/workloads/ingress, dedicated Secret/PVC/PV/files/database/role/OIDC app/provider and dashboard entries/keys only after independent recovery is protected and verified. Historical cutover evidence and encrypted recoveries are archives, not active deployment declarations. Retirement uses its own serial maintenance owner so intentional deletion cannot weaken the eight-app continuous presence/readiness watch.

## Preparation validation

-90 rendered resources validated, zero schema errors or missing schemas.
-10 retained-state/manifest checks passed, including complete app container and Service comparison against actual inherited source layers.
-27 native safety checks passed, including full shutdown/cold program assembly, exclusive intents/known terminals, clocks, exact placement restoration, watcher scope and transport encoding.
-Exact-image isolated qBittorrent shutdown/reload and MQTT persistence repair/recreation passed. Fresh native preflight confirmed all11 scoped Argo owners idle/Healthy/Synced, original source generations, healthy nodes, verified runner runtime, no maintenance owner and no target collisions.

These are preparation results. They do not claim production migration or Vikunja removal is complete.
