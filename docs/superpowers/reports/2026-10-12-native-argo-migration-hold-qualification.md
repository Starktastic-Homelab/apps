# Native Argo storage-maintenance hold qualification

The disposable, isolated lab used stock ArgoCD3.5.3 and k3s1.37.0, matching the
installed releases, with native Application and RollingSync ApplicationSet
controllers and a synthetic local Git repository. No physical network NIC,
production Kubernetes credentials or Proxmox administrator credential was present.

The exact-app recurring deny window (`* * * * *`,24h,UTC, manualSync=false,
syncOverrun=false) passed these cases:

- Manual sync rejected through the native API.
- RollingSync updated desired revision while the held resource stayed unchanged.
- An unrelated automated application continued updating.
- A minute recurrence boundary and controller/ApplicationSet restart retained the hold.
- A genuine admission-quota failure produced a scheduled70s retry. After activating
  the hold and removing the fault, the timer passed without creating its resource.
- Automated revision changes and deliberate self-heal drift stayed blocked,
  including across an application-controller restart.
- Removing only the owned window preserved another window and allowed the final
  revision to reconcile automatically or through a fresh native sync.

## Queued operation retirement

The native terminate-operation API can leave an operation Terminating under an
active window. The qualified finite maintenance procedure uses one Kubernetes
JSON patch testing the exact Application UID, resourceVersion, operation and
operationState, removing the operation and marking that exact state Failed with
finishedAt. This is an imperative recovery step, not a driver fork or controller.

RollingSync can immediately enqueue a new operation. Require the final accepted
source/revision and a new operation identity; an absolute idle-state assertion is
not valid in this case. Refresh the Application and verify its comparedTo source.
A subsequent controller restart must not resurrect the discarded old operation.
A watch started before window removal observed only the final resource payload,
with no transient return to the stale revision.

An imperatively created resource without Argo tracking metadata can remain
OutOfSync until native sync adopts it. Before release, verify the actual payload,
final desired source and retired stale operation independently. Do not supply
tracking metadata by force or mistake this status for permission to replay an
old sync. After release, require final native Succeeded/Synced acceptance.

These results qualify the mechanism used by the live-storage design. Each
production operation still needs fresh project ownership, idle acquisition,
writer inventory, source protection, backup, exact target and release evidence.

## October13 production findings

The completed [Prowlarr cutover](2026-10-13-prowlarr-production-cutover.md)
encountered two revisionless held RollingSync operations. A known old Git SHA
could not classify them. The separately approved amendment captured exact
Application UIDs, operation bodies, controller, start time and unresolved source
snapshots, and proved no resolved revision or resource result existed.

One native termination request per captured generation was followed by an atomic
UID/resourceVersion/full-operation/full-state tested replacement, marking the
old state terminal and queuing the complete current sources with resolved final
revision arrays and prune disabled. The hold stayed unchanged through this step.
Current-main desired/live equality passed on both sides of replacement; all four
owners then reconciled to the merged SHA and a full six-minute native Deployment
watch passed before cleanup.

Carry these checks into the next application-specific procedure. A missing Git
revision alone, a sync-window message alone or an operation belonging to a
different generation does not authorize retirement. Unknown API outcomes retain
maintenance ownership and require reconciliation rather than a second request.
