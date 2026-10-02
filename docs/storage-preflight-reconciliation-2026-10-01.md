# Read-only retained-storage reconciliation — 2026-10-01

The existing pinned VM300 runtime queried TrueNAS using its existing CA trust,
leaf-certificate pin and private credentials. No private credential or TLS file
was exported to the workstation. A checksum-verified websocket-client 1.9.2 wheel
was used from a temporary directory and removed after the query; no package was
installed. The RPC wrapper allowed only the query/config methods listed below.

Onboarding reconciliation passed the existing native identity validator, including
NAS version, pool/ZVOL identity, extent/LUN/target mapping, CHAP identity,
initiator restrictions and durability policy. Every field reconstructed from the
original onboarding intent matches the saved record. The saved record additionally
contains `filesystem_uuid`, which is not derived or checked by NAS reconciliation.
No filesystem mount, probe, writer handoff, or playback test was performed here.

Snapshot policy reconciliation found exactly one matching native task, ID 2,
matching the original intent. No create/update/delete or service action ran.

SHA-256 identities of the unchanged input evidence:

| File under `operations/jellyfin` | SHA-256 |
| --- | --- |
| `record.json` | `d6d51cc3b2c0dafdacd47c5522b11e61472ca5f666d34ad2d27ebfe4103ed51b` |
| `onboarding.jsonl` | `0655440d559f41ece3ed3279133c20fe1800ae221fe12bab05777d55cba80294` |
| `snapshot-intent.jsonl` | `e5a80be0415869597e8a69c34858e96b8bac6acbe3750ac4b252b923ec1fa5c7` |

Read-only RPCs: `system.version`, `pool.query`, `pool.dataset.query`,
`pool.snapshottask.query`, `iscsi.global.config`, `iscsi.extent.query`,
`iscsi.target.query`, `iscsi.targetextent.query`, `iscsi.portal.query`,
`iscsi.initiator.query`, and `iscsi.auth.query` (tag/user projection only).

The original journals were neither edited nor removed. This report is a dated
operator observation, not a machine-consumed authorization receipt. The local
status/preflight inspector intentionally continues to report both journals as
`unknown`; it does not infer current completion from a historical journal or this
report. Migration readiness, live filesystem identity and the outstanding SQLite
contention finding are not closed by these checks.
