# Handoff: officially supported PostgreSQL adoption

Continue the homelab application-state reliability work as a separate PostgreSQL task. Start with discovery and a concrete migration proposal. Do not execute production cutovers merely because earlier work had maintenance approval.

## User intent and division of work

The user wants the three-node k3s cluster to be replaceable through Packer/Terraform without losing application state. SQLite databases on NFS have been a concern across multiple services. Investigate moving applications to the existing shared PostgreSQL instance where their deployed versions officially support it.

The original task retains ownership of iSCSI generalization, recovery robustness, script cleanup and Jellyfin's unresolved application contention. Coordinate changes that affect shared infrastructure. Do not independently alter the retained-storage platform, its lock, admission gates, or Jellyfin configuration.

## Workspace and authoritative sources

Repositories: `/home/benf/Projects/homelab/{apps,ansible,terraform,packer}` and `/home/benf/Projects/homelab/.github`.

Read repository AGENTS.md instructions, README and validation workflows. Fetch current main before reasoning from files: the user's apps checkout is an unrelated older feature branch, contains untracked prior audit documents, and lacks some already-merged storage tools. Preserve that checkout and all existing changes; use an isolated worktree for implementation.

Current known apps main at this handoff: `5de6a10c1e84f1f6b8dc71e8eb2f1d5598441c69`; verify freshness. This SHA is context, not permission to deploy an old revision.

Starting evidence (historical, refresh before use):
- Original-checkout `docs/superpowers/reports/2026-09-20-application-state-audit.md` and its `evidence/2026-09-20-storage-bindings.json`.
- `docs/superpowers/specs/2026-09-20-retained-iscsi-rehearsal-design.md` in that checkout: prior official-support research, some conclusions may now be stale.
- Current-main `docs/superpowers/reports/2026-09-21-postgres-backup-reliability.md` and `evidence/2026-09-21-postgres-backup-restore.json`.
- Current-main `docs/superpowers/reports/evidence/2026-09-21-application-backup-coverage.json` and NFS durability execution report.

## Work to do

1. Refresh application/image/engine/volume/consumer inventory. Confirm effective runtime configuration safely, not just chart defaults or an old database file's existence. Never print Secret values, passwords, tokens, connection strings or full environments.
2. For each candidate, verify primary upstream documentation/source for the exact deployed version. Record separately:
   - Official PostgreSQL backend support and recommended production use.
   - Official migration tooling/path from the existing SQLite installation.
   - Data the migration preserves or loses: accounts, permissions, history, metadata, plugin state, queues, saved progress and ancillary databases/files.
   - PostgreSQL version/extension requirements, connection budget and operational dependencies.
3. Classify: already PostgreSQL; supported candidate with supported migration; backend supported but conversion unsupported/uncertain; unsupported; unknown. Do not equate backend support with supported conversion, or silently accept lost history. Explicitly flag any third-party converter or manual SQL conversion for a separate decision.
4. Review shared PostgreSQL capacity and failure domain, per-app roles/databases, least privilege, sealed credentials, restore tooling and cluster-rebuild recovery. PostgreSQL adoption does not remove non-database state or automatically qualify its own NFS durability; inspect current effective mounts and server settings before making such claims. Do not move PostgreSQL storage in this task without coordination.
5. Produce a ranked app matrix, a small first candidate, and a per-app migration/rehearsal plan. Include fresh source backup, isolated restore/conversion, semantic checks, application acceptance, cutover/downtime estimate and rollback boundaries after destination writes.
6. Implement reviewed preparation through small PRs. Rehearse on isolated copies before proposing a production window. User merges PRs. Never call an unperformed migration or restore successful.

## Inventory leads, not approved migrations

The September 20 audit observed SQLite on NFS for Sonarr/Radarr and their RU variants, Lidarr, Prowlarr, Bazarr, Autobrr, Navidrome, Audiobookshelf, Cleanuparr, Seerr and Seerr RU, Calibre-Web Automated, Home Assistant, ntfy, Excalidash, Karakeep, Bytestash, ConvertX, CrowdSec and pgAdmin. Grafana's engine was inferred rather than fully verified. Refresh all of these; they are not all PostgreSQL candidates.

Prior sources warned that some Servarr products support PostgreSQL but not conversion of an existing SQLite installation, and that some other applications cannot preserve history. Reverify exact current support rather than carrying those statements forward as facts.

Historical PostgreSQL-configured consumers: Authentik, Vikunja, Paperless, Lingarr, Dispatcharr and Mealie. Immich uses a separate PostgreSQL instance. Vaultwarden/Listmonk require runtime confirmation because their configuration is Secret-injected. Avoid unnecessary remigrations.

The user previously deprioritized Filebrowser's local DB and Audiobookshelf. Do not silently expand their priority or discard their data.

## Existing backup work

The shared PostgreSQL backup pipeline had incorrectly accepted failed pg_dumpall producers. A merged fix was prepared with producer validation, private staging, atomic publication and retention only after success. A September 21 isolated restore of PostgreSQL 18.6 passed for nine databases and 542 user tables. That is historical evidence, not a fresh backup or proof every subsequent scheduled run succeeded. Check actual rollout/scheduled-job results and obtain fresh migration-specific backups.

The same-NAS backup destination does not protect against NAS loss. Independent backup/restore remains a separate requirement.

## Shared operational constraints

- TrueNAS was upgraded to 25.10.7; verify current version. Proxmox is 10.9.9.20:8006, VM100 is NAS, VM200–202 are k3s, VM300 is the runner. No spare physical lab host; do not overcommit resources or stop VMs without a fresh justified plan.
- Management access uses the user's WireGuard connection; kubeconfig is `~/.kube/config`. The existing fetch script is `ansible/scripts/get-kubeconfig.sh`.
- Credential references may exist at `/tmp/runner-ssh.sh`, `/tmp/proxmox_pass.txt`, `/tmp/truenas_creds.txt`. They are ephemeral; do not print contents, assume availability, or ask for secret values in chat. Ask for restoration of a path only if truly required.
- Original external maintenance ownership is still retained. Runner operation: `/var/lib/homelab-maintenance/operations/jellyfin-migration-20260922T055644Z`. Do not acquire replacement ownership, clear receipts, take over the lock, or reuse stale release authorization. Coordinate with the original task before any shared maintenance operation.
- Read-only inventory/research and isolated preparation are in scope. New downtime, live data conversion, VM changes, deletion, fencing and shared-storage mutation are not authorized by this handoff.

## Jellyfin status, to avoid duplicated work

Jellyfin already runs on retained ext4/iSCSI on worker01. Cold target backup, two independent restores, clean worker handoff, playback, GPU transcoding, and public reopening passed. Apps #1248 started it; #1249 reopened it. The old NFS data is stale and must never be restarted as rollback after target writes.

The same pod remained healthy with zero restarts for over 24 hours. There was one SQLite lock burst during two Seerr scans plus a later Android TV progress request with a disposed connection. Storage health and snapshots passed; root cause is unproven. Isolated read tests and a mixed read/write test did not reproduce it. No PostgreSQL migration or third-party Jellyfin provider is requested here.

Private evidence is under `/home/benf/Backups/homelab/jellyfin/`; retain it. Do not copy database dumps or private operational credentials into Git or PRs.

## First deliverable

Return a cited support/migration matrix, current shared-PostgreSQL readiness findings, and a recommended first rehearsal with explicit data-preservation/rollback criteria. List unresolved support questions instead of guessing. Do not begin a production migration.
