# Production Proxmox CSI shared setup results

Completed **2026-10-05, 00:47 Asia/Jerusalem**, within the user's approved
[shared-setup scope](../plans/2026-10-04-proxmox-csi-production-setup.md).
Persistent storage and scoped access are ready. CSI remains disabled; no worker
replacement, service image allocation or application migration ran.

## Persistent resources

| Resource | Verified result |
| --- | --- |
| TrueNAS dataset | `apps/k3s-block`, GUID `13918781591004512447` |
| Capacity | 128GiB aggregate quota, zero reservation/refreservation |
| Dataset settings | Inherited encryption/LZ4, unlocked, sync STANDARD, POSIX; root:root, mode0755 |
| NFS export | Share10, `/mnt/apps/k3s-block`, read/write, only `10.9.9.20/32`, maproot root:root |
| Proxmox storage | `k3s-block`, NFS4.2 from `10.9.9.30`, images only, node `pve`; active and empty |
| Pool | `k3s-csi`, empty |
| Image owner | 9999 reserved in the pool comment; no VM/container9999 exists |
| API identity | Separated `kubernetes-csi@pve!retained`, role `HomelabCSI` |
| Credential | VM300 `/var/lib/homelab-maintenance/private/proxmox-csi.json`, mode0600 |

The [shared-storage settings](../../../infrastructure/system/proxmox-csi/shared-storage-settings.json)
record the exact non-secret inputs for Ansible's existing manual playbook. They
are not automatically consumed by Apps or a deployment workflow. These resources
stay outside disposable cluster Terraform state and are intended to survive
cluster destroy/apply. The owner reservation remains an operator convention,
not a Proxmox allocation lock.

## Verification

- Ran the exact merged Ansible role at
  `913941f2610681d048587f30b0984453c7b768af` in the approved pinned container on
  VM300. The first run completed with 22 successful tasks and 7 changes; the second
  completed with 25 successful tasks and **zero changes**, with the credential
  byte-for-byte unchanged. Both had zero failures/unreachable hosts.
- Confirmed exactly the five approved privileges and six user/token ACL entries:
  inherited on `/pool/k3s-csi`, non-inherited on `/storage/k3s-block` and
  `/vms/9999`. User and separated-token effective grants match. The token has no
  power-management or VM-allocation privileges.
- Authenticated the token to the API and read the empty storage inventory.
  VM configurations 100,200,201,202,300,900 each returned **HTTP403** with that
  token; its visible VM inventory was empty, as expected before pool enrollment.
- Matched full configuration hashes for those six VMs before/after setup.
  Existing NAS exports and global NFS configuration are unchanged; NFS remains
  running. No cluster playbook or deployment workflow was dispatched.
- Removed the temporary administrator inventory, setup container and staged
  setup source. The generated scoped credential remains protected on VM300.
  The original user-supplied administrator file was preserved. Maintenance
  ownership was released after verification and evidence archival.

This verifies shared configuration and scoped read access. It does not claim
that production CSI attachment, VM pool enrollment or application storage has
been activated; those remain part of the coordinated rollout.

## Verification-tool corrections

The first NAS assertion expected parsed reservation values to equal numeric zero.
TrueNAS returned `parsed: null` with `rawvalue: "0"`. Readback confirmed the quota
and both zero reservations; the verifier was corrected to check that raw value.
No NAS property was changed to satisfy the assertion.

Python3.13's initial strict TLS check rejected the existing PVE CA because it
lacks a key-usage extension. The completed probe disabled only
`VERIFY_X509_STRICT`, retaining `CERT_REQUIRED`, trusted-CA signature/expiry
validation and IP/hostname checking. Before sending the token, it additionally
matched the served leaf's SHA256 to the certificate independently read over
authenticated SSH:
`991939462464635f91d2a089924eab1055637e8bd48d7771a26cb2b378b41a1c`.
No certificate was replaced and no insecure/no-verification API request was
used for token validation. Production driver and retirement-client CA handling
still need their own verification before activation.

## Evidence and next gate

The [sanitized receipt](evidence/2026-10-05-proxmox-csi-production-setup.json)
contains dataset identity, setup recaps, exact grants, permission denials,
configuration hashes, verification corrections and completion receipt.

The fuller public-script/log archive remains mode0600 on VM300 at
`/var/lib/homelab-maintenance/operations/csi-production-setup-20261004/setup-evidence.json`.
Its SHA256 is
`c6744c52f6d4761ed033517a13c0e22d896e244d3ab78eab2623826ebaf41b37`.
The operation-path date is retained from the approved proposal; execution was
on October 5 local time. No token or administrator secret is in Git or this archive.

Before controller activation, prepare the combined worker-replacement/Jellyfin
migration scope: enable and verify retirement visibility and topology, publish
recoverable sealed CSI configuration, inspect the first cohort/pool Terraform
plan, and stage the data transfer and writer release. Current Jellyfin iSCSI
generation safeguards remain intact. Ordinary rebuilds retain the accepted
merge flow with no Velero checkpoint.
