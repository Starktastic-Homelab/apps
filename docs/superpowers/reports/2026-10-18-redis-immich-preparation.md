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
