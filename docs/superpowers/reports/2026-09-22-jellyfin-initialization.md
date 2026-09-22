# Jellyfin retained target initialized

The approved format-and-copy operation completed on 2026-09-22 under the original
shared maintenance lock. Jellyfin remains held: zero replicas, closed ingress,
suspended LDAP sync, and no production target-write authorization.

## Verified identity

- Dataset: `apps/iscsi/jellyfin-config`, ZVOL GUID `14950202402923644020`.
- Capacity: 64 GiB; target/extent/mapping 97, LUN 0.
- Serial: `8eb9e631136f4471`; NAA: `0x6589cfc000000b92325e983b56b8502a`.
- Filesystem UUID: `d3cc0be9-ad2f-4c67-a6fc-abc6104b7712`.
- Marker: `19b50cf8-a026-408e-83df-521d13bec20b`.
- Worker: kube-worker-02, VM202, SMBIOS `d6c40da9-aaa5-4b5c-a9ce-70d3cfdcc4b4`,
  Kubernetes UID `63d963c8-0c04-4be8-81a3-07e8aa1cc240`.

## Evidence

Before formatting, native identity, reservation, quiescence, worker generation,
absence of sessions, device identity and blank signatures were checked. Exclusive,
fsynced intent receipts preceded the single non-forced ext4 format.

The independently restored cold archive was streamed to the target:

- SHA256: `f80e2c10b6a33e74f82c10913a5e76978ef5978ea64c3c5835b3c1cd19466724`.
- Archive bytes: 28,696,647,680; verified inventory entries: 118,792.
- All hashes, ownership, modes, links, nanosecond timestamps and portable xattrs
  matched the captured source inventory. Only the exact NFS mode ACL projections
  accepted by Apps #1239 were omitted; the raw archive and manifest are retained.
- Five SQLite databases passed integrity checks on private copies with sidecars.
- Filesystem use after copy: approximately 43%, below the 70% gate.
- The marker was written only after copy verification.
- A clean disconnect/reconnect and `ro,noload` mount passed inventory, marker,
  filesystem identity and private-copy SQLite checks again.
- Final unmount/logout/node-record cleanup passed; both workers and the NAS
  independently confirmed no remaining target session.

The operational probe used stdin/private-file CHAP configuration; the current
`initiator_probe.py` command-argument credential path was not used. Its credential
handling must be corrected before using that helper for release verification.
No third-party code was patched. The native record now includes the observed
filesystem UUID, and the original maintenance lock remains held.

Private receipts, execution scripts and the accepted record are retained beside
the independent backup under the `20260922T055644Z-preflight/initialization-evidence`
directory and on the runner's original migration operation. The source snapshot
is `apps/pv@jellyfin-cold-20260922T060429Z`, GUID `8882008524600065698`.

## Target-held change and remaining gates

The target-held manifests bind the exact retained PV/PVC and sealed CHAP, pin the
future writer to the verified worker generation, and configure disposable cache
and transcodes. They keep replicas zero, ingress closed and LDAP suspended.
The original NFS claims remain retained. The sealed credentials were validated
against the current controller without creating them.

After the user merges target-held, verify binding, reconcile the exact held
revision, and complete external release checks before a separate target-released
change. Starting Jellyfin, reopening ingress, playback/transcode acceptance,
clean worker handoff, target backup/restore and 24-hour observation remain pending.
This initialization result does not qualify the entire pilot.

Reassess the supervised outage at 07:34:28 UTC (90 minutes from observed hold),
including remaining Git review and application acceptance work. Before target
application-write authorization, rollback uses the retained original NFS source
only after proving target quiescence. After that boundary, use a fresh target copy
and new NFS claim; never restart stale state.
