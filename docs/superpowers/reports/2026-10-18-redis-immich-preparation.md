# Redis and Immich retained CSI preparation

Status: Tasks1–3 locally qualified on18October2026. The finite private command
packet, independent final review, hosted CI and concrete execution proposal are
still pending. No production setting, workload, data, allocation, owner or backup
key has changed. No real records or credentials entered a fixture or Git.

Task4 found a repeatable AOF-disabling path in the exact deployed Dispatcharr
client. The [access-design decision](2026-10-18-redis-dispatcharr-persistence-decision.md)
contains native reproduction and a qualified ACL candidate. The user approved that amendment. All seven Redis native tests now pass under
the restricted startup configuration, and seven render checks validate the
server-only ACL Secret mount. The finite command packet remains in preparation;
current inactive candidates are not yet a complete production solution.

## Qualified components

- Ten state tests, seven native Redis/exporter/ACL tests and two native PG17 tests pass.
- Seven actual-render contract tests pass. Kubeconform validates all47 candidate and
  baseline resources with no invalid/error/skipped resources. Real promtool
  tests pass for two-minute AOF-disable/write-failure alerts and recovery.
- The native Redis fixture matches the actual chart’s configuration and live
  UID/GID1001:1001/module set. Current-memory RDB recovery precedes live AOF
  enabling in the fixture; historical AOF fails the full current-state proof.
  Native Celery/Kombu and BullMQ recover pending/in-flight synthetic jobs.
- PG17 physical and independent logical recovery preserve all native proof fields,
  including records, duplicates, binary/vector values, roles/verifiers, schema,
  extensions and sequence floors. Cold bytes/POSIX metadata match. Wrong,
  corrupt, missing, linked, unreadable or recovery media refuse startup. Stock
  stale-PID and WAL recovery are qualified under the fencing contract.
- The exact exporter reports enabled1, disabled0, write-status0 under an actual
  private2MiB ENOSPC fault, then healthy1 after space returns. No notification
  is sent. Live read-only queries confirm the metric names and
  `namespace="databases",service="redis-metrics"` selectors. Prometheus in the
  `monitoring` namespace selects these rules across namespaces; the inactive
  rule also retains `release: kube-prometheus-stack`.

The detailed engine reports are [Redis](2026-10-18-redis-native-qualification.md)
and [Immich](2026-10-18-immich-native-qualification.md). Sanitized source/access
and monitoring evidence is under `evidence/2026-10-18-redis-*.json`.

## Inactive desired state

Static2GiB Redis and10GiB Immich PG claims prebind their exact external-owner9999
images, ext4/cache-none, RWOP/Retain, topology and prune/delete protection. Both
use the existing Linux workers and indefinite not-ready/unreachable holds.
No application definition has been activated.

Redis keeps its chart command/config/module/auth/service/probe behavior and pins
the exact running Redis/exporter digests. It adds the read-only retained guard,
explicit everysec fsync, named existing claim and durability rules. Approved native ACLs add a server-only
`redis-server-acl` Secret mount, restrict application CONFIG SET/ACL commands and
use a distinct maintenance credential. Timeout300 preserves the verified live
idle policy. No real credential or SealedSecret has been generated. Full rendered
StatefulSet/container/config/service comparisons permit only these scoped changes.

Immich changes only its PG storage, guard, process permissions and placement.
Server/ML deployments, endpoints, credentials, photo/video and model-cache mounts
match their actual baseline exactly. Upstream schema validation remains enabled:
a temporary values materialization removes only the old fsGroup, PID-deletion
init and its mount before applying the normal overlay. Production activation
must apply those reviewed deletions to the real service values.

The independent native CI job feeds an explicit success gate in the existing
required Validate job. This keeps its existing15-minute timeout and requires no
branch-protection edit. CI publication is still pending; local tests do not prove
hosted checks or a live rollout.

## Recovery limits and remaining gates

The qualified stock Redis loader may discard an incomplete final AOF command
after a crash under the accepted everysec policy. It rejects other invalid AOF
formats; the guard never repairs retained data. The ordinary fsync policy has its
normal disaster-loss window, commonly about a second, rather than a zero-loss
guarantee. Full source-to-target migration state remains mandatory. Native AOF
checks need private scratch copies because the checker opens files writable.

A fresh production check still must account for every configured/idle consumer,
prove clocks and quiescence, protect current Redis memory before restarting,
identify any recurring AOF disable, validate complete PG/asset roots and writers,
and recheck NAS/pool capacity with full future growth,512MiB staging and8GiB spare.
The288GiB quota and historical Jellyfin partial stay unchanged.

Real-data/key transfers, outages, allocation and activation/merge authority remain
separately gated. Final acceptance still needs real queue processing, native PG
and existing-asset/API checks, Pod recreation, healthy-worker movement, restored
placement, exact merged-main Healthy/Synced state and a six-minute release watch.
No full-cluster Terraform destroy/apply rehearsal has been performed here.


## Command-packet progress and accepted decisions

Nineteen local process/ownership/recovery tests pass, including native maintenance
exclusion, lost-reply refusal, original deadlines, metadata-preserving native tar,
encryption/decryption and bounded transfers that refuse overwrite. Read-only
SSH/QGA probes accepted a112293-byte program and verified the native integer
terminal form. All eight proposed bindings/source-guard objects passed actual
Kubernetes server dry-run; no objects were persisted.

The signed-in browser opened an existing Immich photo and its metadata. The
user-provided temporary read-only API key then verified an existing4112724-byte
original against its API checksum over HTTPS. The key remained on this computer,
outside Git; image bytes were streamed and not saved. This is a baseline check,
not post-migration acceptance.

Packet assembly recorded a [Dispatcharr DVR preservation decision](2026-10-18-dispatcharr-dvr-queue-decision.md):
its native web startup cleanup deletes pending DVR queue messages. Exact-image
synthetic RED and minimal-change candidate GREEN are recorded separately from the
passing protocol suite. The user accepted stock DVR resets; no startup override is selected. Full phase
assembly, final review and hosted CI remain pending; no complete executable packet
or rollout is claimed. The user selected the [checkpoint-only pause](2026-10-18-immich-checkpoint-writer-scope.md)
for all21 overlapping media workloads. Unrelated media apps resume after the
immutable database/photo checkpoint barrier; Filebrowser and the NFS provisioner
remain paused until database retirement permits their release. Actual downtime
remains subject to the finished execution proposal.

## Further packet qualification

The private package now has independent commands for current-memory Redis and
cold AOF restoration, PG17 physical and independent logical restoration, and
complete metadata-preserving population of a fresh mounted target. The population
command writes its retained marker after equality, syncs the filesystem and
refuses a second population attempt. Damaged/changed input tests refuse recovery.
These component checks do not yet establish the complete production sequence.

Local native supervision tests cover original owner/clock identity, lost replies,
nested child exclusion, failed-outcome inspection, private binary stdin and the
actual maintenance lock. The real SSH/QGA adapter is prepared behind an explicit
execution-approval check; its mutation methods have not run against homelab hosts.
No homelab maintenance owner has been acquired.

The pinned Immich image uses the `immich_bull` queue prefix. Its native BullMQ
pause/drain/resume test preserves pending payloads and original pause flags while
active work finishes. Preparation keeps web health checks available while holding
external producers, then requires complete source shutdown and writer retirement.
The full source-stop, snapshot, transfer, activation and recovery sequence remains
in qualification; independent final review, hosted CI and the finished execution
proposal are still required.

The assembled read-only queue-plan command also passed against the existing Pods:
19 Immich queues, one Paperless worker, and both Dispatcharr workers. Disposable
queue tests include active, pending and scheduled ETA tasks; shutdown waits for
all three states to drain. Exact native beat process generations are checked
before signaling, and the generated commands fit the qualified guest argument
bound. No live producer was stopped or queue paused during these checks.

Original phase budgets now reach native child commands. A real local late-write
regression is refused after its deadline; changing a command outcome or phase
predecessor also blocks continuation. The cutover-specific PostgreSQL cold
restore additionally requires a clean native shutdown. This does not alter the
retained startup guard's accepted stock recovery behavior under fencing.

A separate exact-image source-client fixture verifies the source run ID, full
16-database checkpoint, connected-client census and selected native ACL/AOF
transition. Wrong source generations and unaccounted clients fail closed;
application credentials remain usable while their persistence-disable command
is denied. These are synthetic records, not copies of production data.

Read-only database directory sizing found about 49MiB of historical Redis files
and 349MiB of Immich PostgreSQL files. Historical Redis files remain insufficient
to recover its current memory. VM300 has about 7.1GiB free and the required native
recovery tools; this supports the proposed bounded database staging. Fresh checks
remain mandatory during execution. Original photos use the coordinated ZFS
snapshot strategy, with no full-library copy.
