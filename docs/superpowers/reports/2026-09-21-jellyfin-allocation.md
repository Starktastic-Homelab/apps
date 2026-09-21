# Jellyfin allocation and next-stage readiness

## Verified live prerequisites

Apps #1236 deployed revision `543e58116ff9a1c84d60dcaead599f387938e093`.
The retained CSI driver registered on both workers; both four-container node
pods were healthy with zero restarts. All 97 existing Deployments/StatefulSets
were ready. Jellyfin's running pod was unchanged with zero restarts.

The separately approved allocation completed on 2026-09-21. Independent readback
verified the following native identities; names alone never authorize recreation:

| Field | Verified value |
| --- | --- |
| Dataset | `apps/iscsi/jellyfin-config` |
| Pool GUID | `9917900421692286909` |
| ZVOL GUID | `14950202402923644020` |
| Capacity | 64 GiB, non-sparse reservation |
| Durability / block size | Local STANDARD / 16 KiB |
| Target / extent / LUN | 97 / 97 / 0 |
| Serial | `8eb9e631136f4471` |
| NAA | `0x6589cfc000000b92325e983b56b8502a` |
| Target IQN | `iqn.2005-10.org.freenas.ctl:jellyfin` |
| Portal | `10.9.8.30:3260`, portal ID 1 |
| Service marker | `19b50cf8-a026-408e-83df-521d13bec20b` |
| Initiator group / CHAP tag | 6 / 19701 |
| Snapshot policy | ID 2, recursive `apps/iscsi`, one-week retention |

The export has 512-byte sectors, third-party copy disabled, CHAP authentication,
the exact two enrolled worker IQNs and the storage-subnet restriction. iSCSI is
enabled and running. The snapshot schedule matches the existing `apps/pv`
schedule; actual scheduled execution and restore are not yet qualified.

Native records and mutation journals are retained on VM300 under
`/var/lib/homelab-maintenance/operations/jellyfin`. The completed operation is
`jellyfin-allocation-20260921T203910Z`. Recovery records and the private CHAP
credential were independently copied to the approved encrypted laptop backup.
No secret is included in this report. Temporary NAS password material was removed
from the operation, and maintenance ownership was released and checked absent.

The volume is unformatted and has no filesystem UUID. No worker session, stored
target, retained PV, copy or writer authorization was created. These identities
are evidence, not a deployable filesystem record.

## Next merge and outage boundary

Merge #1237 only after its checks pass against main. It adds backup, restore and
transition tooling; it changes no running application definition.

Keep #1238 draft until a separate Jellyfin outage window is approved. Before
requesting that window, retarget and validate #1238 after #1237 merges, inspect
its exact deployment diff, record current source identities and application
baseline privately, and verify worker and laptop capacity again. The exact
production image is already present locally; the encrypted laptop filesystem
had approximately 762 GiB available during this preparation.

During the approved window:

1. Acquire fresh shared maintenance ownership. Merge the reviewed source hold,
   wait for writers/jobs to exit, and verify the actual reconciled revision.
2. Snapshot the source and capture the complete held configuration to the
   encrypted laptop. Independently verify file metadata, SQLite and a restored
   application using the exact production image.
3. Only after that restore passes, finalize and review the one-time initialization
   command sheet against the native identities above and actual device readback.
   Require a blank, unmounted 64 GiB device with matching serial/NAA, no competing
   sessions, and a durable exclusive format intent. No forced format or retry
   after an uncertain outcome is allowed.
4. Format and copy only within that approved scope. Record the actual filesystem
   UUID, verify every persistent file and metadata entry, flush and unmount,
   then complete the normal read-only native/filesystem checks.
5. Seal actual CHAP, generate and review target-held and target-released Git
   revisions, and externally authorize exactly one verified worker generation.
   Keep public ingress and LDAP writes closed until operator acceptance.
6. Verify playback, hardware transcode, seek/progress writes, a clean worker
   handoff, target backup/restore and the required 24-hour observation.

Until the target first opens writable, the untouched NFS source remains the
rollback source after proving target quiescence. After the conservative first-write
boundary, rollback requires a fresh cold target copy to a new NFS directory and
claim. Preserve both source and target; no cleanup is authorized by this stage.

The exact initialization command sheet and target Git revisions remain gated on
the fresh cold restore and returned filesystem identity. This preparation does
not claim that formatting, migration, playback or target restore has occurred.
