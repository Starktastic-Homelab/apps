# Utility, download and MQTT retained storage

This is the activation contract for the eight-app cohort; activation is still pending until its reviewed execution receipts and final completion report exist.

Private state moves to static ext4 images under Proxmox owner9999 on`k3s-block`, using the unmodified upstream driver, Retain and ReadWriteOncePod. Sizes are2GiB for qBittorrent and1GiB each for qBittorrent RU, Changedetection, Stirling-PDF, Microbin, Lingarr, Mosquitto and Zigbee2MQTT. PVC names and handles are explicit in`scripts/utility-home-retained/production/*-bindings.yaml`.

Ordinary Terraform destroy/apply and worker replacement retain the existing workflow: disk identities/bindings/guard bytes come from Git, physical worker retirement supplies fencing, and the native guard refuses missing/wrong data before the app starts. No Kubernetes-metadata backup acceptance is added to Terraform. Shared media/download paths and Lingarr's existing PostgreSQL enrollment remain unchanged.

Do not start a retired NFS source after a target writer has been requested. Source admission holds prevent the known old PVC/direct-NFS mounts. Before authority, source rollback requires exact complete cold file/POSIX equality and fully retired target helpers/attachments. After authority, recover the current target or a separately accepted recovery; never replay stale source state.

Every allocation/growth reserves all active future raw-image growth, remaining cohort images,512MiB staging and8GiB spare against fresh dataset and pool availability. The approved quota ceiling is288GiB for dataset GUID13918781591004512447. The quota change must have its own accepted native receipt; approval alone is not evidence that it was applied. Do not remove the historical Jellyfin partial or another image to manufacture capacity.

qBittorrent main/RU share an inherited values base, so both must be stopped, backed up, independently restored/qualified and populated before their paired activation PR. Keep every torrent/resume ID, category/tag, counters, settings and VueTorrent cache. Gracefully stop the native s6 service and prove no restart occurred before scaling away the source. Payload performance troubleshooting remains a separate task; this migration does not tune it.

Mosquitto's permanent persistence path is`/mosquitto/data/`. The one-time repair must first flush original in-memory state through the source PVC, then shut down gracefully and qualify its native persistence independently. Preserve retained messages and durable sessions; do not publish production device commands. Zigbee2MQTT retains its coordinator, network keys, device IDs and serial/MQTT endpoints; never re-pair or generate a new network to pass acceptance.

Recovery is complete native cold files with POSIX and active SQLite proofs, encrypted on VM300 and this computer with keys kept separately outside Git. Preserve original sources/snapshots for the eight migrations, current targets and encrypted audit/recovery copies. Finish only after native acceptance, recreation, healthy-worker movement, exact default placement, current-main equality, six clean minutes of normal automation, exact transient cleanup and owner release.

Vikunja is a separate authorized full retirement, not a ninth CSI target. Its dedicated database/role/files/OIDC resources and dashboard references are removed after verified encrypted recovery. Shared PostgreSQL, Authentik users/groups/policies and historical recoveries remain.
