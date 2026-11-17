# Operator notes

> Moved from the README on 2026-11-16. The text is unchanged.

## Retained storage and cluster rebuilds

The shared [Proxmox CSI driver](../../infrastructure/system/proxmox-csi/README.md) manages
retained NAS-backed block images. Jellyfin uses a static Git binding; normal cluster
rebuilds do not require a Velero checkpoint. The retired iSCSI stack is removed
through the [cleanup plan](../superpowers/plans/2026-10-06-retire-jellyfin-iscsi.md).

## Bazarr storage

Bazarr keeps its database in shared PostgreSQL and private configuration on retained
Proxmox CSI; media and subtitles remain on NFS. See the [storage and recovery
runbook](../runbooks/bazarr-storage.md).

## ntfy storage

ntfy stores users, tokens, ACLs, messages and webpush state in shared PostgreSQL;
attachments use retained Proxmox CSI. See its [storage and recovery runbook](../runbooks/ntfy-storage.md).

## Grafana storage

Grafana stores its database in shared PostgreSQL and private files on retained
Proxmox CSI. See its [storage and recovery runbook](../runbooks/grafana-storage.md).

## pgAdmin storage

pgAdmin stores its configuration database in shared PostgreSQL and private files on
retained Proxmox CSI. See its [storage and recovery runbook](../runbooks/pgadmin-storage.md).

## MetalLB and Job alerts

The `homelab` MetalLB pool contains fixed `/32` reservations, so it is excluded from
capacity alerts. A LoadBalancer without an ingress address for 10 minutes still
alerts; capacity alerts for other pools and MetalLB configuration alerts remain
enabled. Jellyfin LDAP sync Jobs expire after 24 hours, bounding historical failure
alerts without suppressing new failures. Watchdog remains the intentional heartbeat.

## Probe paths

Calibre-Web probes use `/login`; Excalidash backend probes send
`X-Forwarded-Proto: https` to its existing trusted-proxy middleware. Both receive
direct HTTP 200 responses instead of cross-host redirects. Probe timing and normal
application redirects remain unchanged.

## FlareSolverr and the Falco exception

Falco exempts only the pinned FlareSolverr image's expected ChromeDriver execution
in `media`, with its executable path, process ancestry, and UID constrained. Update
the exception in `infrastructure/system/falco/values.yaml` alongside every FlareSolverr
image pin update, including Renovate PRs. Use the Linux/amd64 image config digest
without `sha256:`, not the manifest digest; unrelated executions remain subject to
the original rule.

## Checking the alert policy

Run `python3 scripts/check-alert-policy.py` with Helm, Docker, PyYAML, and `promtool`
installed. It resolves the pinned image's config ID without pulling the FlareSolverr
image. The check also accepts a command prefix, for example
`python3 scripts/check-alert-policy.py docker run --rm -i --network none --entrypoint promtool prom/prometheus:v3.14.0`.
