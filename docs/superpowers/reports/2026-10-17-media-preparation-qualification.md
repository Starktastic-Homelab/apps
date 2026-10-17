# Media migration preparation qualification

Scope: Sonarr/RU, Radarr/RU, Lidarr, Cleanuparr, Navidrome, Audiobookshelf,
Shelfmark and Cineplete. The user authorizes autonomous implementation, ordinary
scoped outages and PR merges, and specifically selected Cleanuparr PostgreSQL.
The nine other engines, all application images and shared media interfaces stay
unchanged. Inactive preparation is PR1379; production acceptance is separate.

The actual common/base/RU layers rendered119 valid resources with zero invalid
resources/errors and two SealedSecret schema skips. Twelve permanent guard/render
tests passed, including refusal of empty/wrong/linked native state and distinct
RU identities. Forty-one native package tests passed. All ten read-only startup
guards ran as their actual consumer UIDs without extra groups/capabilities.
All ten exact read-only-cold archive population entrypoints verified complete
file/POSIX state before markers, including both Cineplete roots and ABS metadata.
The exact encrypted cold restore entrypoint independently decrypted/restored a
synthetic SQLite dataset and examined its complete copied native rows.

Cleanuparr2.10.6's stock converter and exact production import adapters passed a
synthetic43-table/454-column comparison. The source application rows remained
unchanged; PostgreSQL target-empty checks rejected populated schemas. This is
mechanics evidence, not acceptance of real users/settings/events. The converter
upgrades its SQLite input in place, so only writable disposable copies enter it.
Preserved NFS sources, cold archives and CSI population never use that input.

One fresh independent whole-package review used gpt-6-astra. It identified two
Important issues, both fixed with failing-then-passing regression tests before
freeze: explicitly create/verify Cleanuparr's permanent application prerequisites
and controller-owned Secret before conversion, and protect audit/remove accepted
local plaintext fixtures before cleanup acceptance/owner release. Actual leaf-only
Docker cleanup passed with synthetic UID1001-owned private database trees while
preserving recovery media and separate keys. No Critical or Minor findings remain.

The95-file frozen native packet is
`312dfb7cc1e7301d9b4d3135540932c50762fc0cc5558e4430e30e8e9ece7bd2`.
It reuses qualified native ownership, known-terminal/no-replay and original-clock
primitives. An independent Tempo merge during preparation was preserved by a
rebase; it did not change this packet. Current-data cold restores, real-data
conversion, native snapshots/backups/fencing, exact-head activation checks/diff,
live lifecycle/reconciliation and cleanup remain mandatory execution gates.
The review did not assert human OIDC sign-ins, production scans/downloads or
notification delivery, and did not re-audit upstream CSI/runtime internals.
Protected native source/evidence is retained in encrypted audits outside Git.

The final pre-execution pass also pins each complete candidate Deployment spec:
any concurrent Git change to image, replicas, privileges or other workload fields
is rejected before the target-authority record. All ten reviewed candidates pass;
changed image/replicas/token settings fail. No production phase used the earlier
93-file pre-authority freeze.

Active-state validation also passes. The Cleanuparr comparison accepts both the
pre-conversion and already-active baseline while strictly asserting all six
selected PostgreSQL environment inputs; the reproduced activation-only test
assumption was corrected before production. Final native suite41/41, permanent
guard/render suite12/12, scoped pre-commit all green.
