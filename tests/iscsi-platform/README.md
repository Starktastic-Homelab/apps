# Retained iSCSI rehearsal

This directory contains an isolated, destructive **lab** fixture and captured
synthetic evidence. It is not production deployment configuration. Read the
[design](../../docs/superpowers/specs/2026-09-20-retained-iscsi-rehearsal-design.md)
and [execution ledger](../../docs/superpowers/plans/2026-09-20-isolated-iscsi-fixture.md).

The current run uses only Proxmox VM IDs910–913, with exact names, SMBIOS UUIDs
and a unique tag in a private manifest. Never reuse a manifest for another run.
The host guard stops only matching identities. Separate control/storage bridges
have no uplinks; nftables denies host ingress and forwarding from lab guests.
Management uses loopback-only SSH forwarding. Production NAS data is never
mounted by the fixture.

Secrets, kubeconfig, operation receipts and acknowledged-write ledger live in
`.runtime/` (ignored, mode0700). No command may use the default kubeconfig for
lab work. `lab.py` always supplies the private kubeconfig explicitly.

Pinned inputs: TrueNAS25.10.6; K3s1.37.0+k3s1; democratic-csi chart0.15.1 and
image1.9.5; app-template5.2.1; snapshot-controller8.2.1. Image references in the
rendered fixture and CSI values include immutable amd64 digests. Seed media
is SHA256-verified inside each guest before installation.

## Lifecycle checks

- `python3 -m unittest discover -s tests/iscsi-platform -p 'test_*.py'`
- `export.py` captures actual PV/CSI and native NAS identities once, before data
  initialization. `records.json` is the canonical synthetic recovery record.
- `admission.py` renders native Deny policies from those records; onboarding is
  closed by default. `check_admission.py` exercises rejection paths.
- `deploy_fixture.py initialize` is a one-shot authorized lab operation. Its
  external receipt is consumed before any write. Never rerun it after an
  ambiguous result; reconcile the existing database instead.
- `deploy_fixture.py serve` renders the pinned app-template as one-replica
  StatefulSets with explicit existing claims, without volumeClaimTemplates.
- `check_writes.py write <unique-phase>` commits deterministic values and fsyncs
  returned acknowledgements outside the lab. `check_writes.py verify` checks
  every acknowledged value and SQLite integrity, not merely row counts.
- `backup.py` uses SQLite's online backup API and copies the result outside NAS.

Normal fixture startup opens only an existing database and verifies its service
marker. Missing data must never trigger initialization. RWOP is a Kubernetes
constraint, not physical fencing: a partitioned VM must be verified off before
its stale pod objects are removed and another writer mounts the volume.

## Findings during this run

TrueNAS25.10.6 grants REST access only to FULL_ADMIN. Granular dataset/iSCSI roles
successfully authenticated over WSS but returned403 on REST. The stock driver
therefore uses a dedicated **lab-only** full-admin API account; this is an
unresolved production permission limitation. No dashboard or production key is
used. REST is deprecated and removed in TrueNAS26, so this pinned result cannot
be generalized to a NAS upgrade.

The driver's optional `zvolDedup: off` sends an obsolete `dedup` API field.
Omitting it allowed the same claims to provision; parent and volume properties
were verified OFF. NAS HTTPS uses a dedicated CA with hostname verification.
The chart emits invalid `parameters: null` for an empty snapshot class;
a separate standard VolumeSnapshotClass with `parameters: {}` avoids that.

## Cleanup contract

Before deletion, stop writers and verify each VM's ID/name/UUID/tag and every
disk's ownership. Delete only the run's VMs, disks, ISO/staging files, transient
services, private bridges and nft table. Stop its local tunnels, remove private
keys/tokens/kubeconfigs and downloaded artifacts, then reconcile production
node identities/health and host storage/memory. Preserve sanitized source,
checksums, mappings and evidence. A failed rehearsal still requires cleanup.
