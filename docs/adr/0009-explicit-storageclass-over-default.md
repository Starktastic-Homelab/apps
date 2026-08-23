# ADR 0009: Pin `storageClassName` explicitly instead of relying on a default class

- **Status:** Accepted
- **Date:** 2026-08-23

## Context

k3s ships a packaged `local-storage` AddOn that declares the `local-path` StorageClass with
`storageclass.kubernetes.io/is-default-class: "true"`. We want `nfs-pv` (RWX, NFS-backed, survives node loss) to be the
class our workloads land on.

To get there we used to ship `infrastructure/system/nfs-provisioner/manifests/local-path-default-off.yaml`, which
re-declared `local-path` with the annotation flipped to `"false"`. Its comment claimed this gave us "exactly one default
class".

It never did. k3s re-writes its packaged manifests to disk and re-applies them **on every k3s start**, so the annotation
flipped back on every restart — and k3s restarts often here (29 times in the 14 days before this ADR). The observable
result was:

- Two StorageClasses marked default simultaneously (`local-path` _and_ `nfs-pv`).
- The `nfs-provisioner` Argo Application permanently `OutOfSync` on `StorageClass/local-path`, which masked any _real_
  drift in that Application.
- Workload storage silently depending on the DefaultStorageClass admission plugin's multiple-default tiebreak: newest
  `creationTimestamp` wins. `nfs-pv` only won because it was created 100 seconds after `local-path` on 2026-08-12.

## Decision

Stop fighting k3s over the default-class annotation.

1. Delete `local-path-default-off.yaml`. Let k3s own `local-path` entirely.
2. Set `storageClassName: nfs-pv` explicitly on every PVC that previously rode the default — raw manifests _and_
   Helm-rendered ones (see the 2026-08-23 update below).
3. Keep `nfs-pv`'s own `defaultClass: true` (in `values.yaml`) as a safety net for anything new that forgets — but
   nothing in the repo depends on it any more.

## Rationale

The deleted file could not work by construction: any Argo-managed declaration of that annotation loses to k3s's AddOn
controller on the next restart. Enabling `selfHeal` on the Application would only have shortened the window, not closed
it, and would have contradicted the repo-wide choice to keep Argo auto-sync off.

Making the 21 PVCs explicit was verified to be a **no-op against the live cluster**: the DefaultStorageClass admission
plugin had already mutated each of those PVCs to `storageClassName: nfs-pv` at creation time, so Git now simply states
what the cluster already holds. (`spec.storageClassName` is immutable post-bind, so this was the only safe direction.)

Alternatives considered and rejected:

- **`--disable local-storage`** — would remove the SC entirely and give us a single default. Rejected:
  `media/jellyfin-cache` is a 50Gi RWO transcode cache that genuinely wants node-local disk, and disabling the AddOn
  deletes the SC its PVC binds through.
- **A `.skip` file for `local-storage.yaml`** — stops k3s managing the AddOn, so an Argo-owned SC would stick. Rejected:
  we would inherit the whole local-path-provisioner Deployment, RBAC and image version, on every server node, for one
  annotation.
- **Leaving the default ambiguous** (delete the file and nothing else) — works today, but a future k3s upgrade that
  recreates the `local-path` SC would make it the newest default and silently send new PVCs to node-local disk.

## Consequences

- `nfs-provisioner` can reach `Synced` and stay there, so drift in it is meaningful again.
- Storage choice is self-documenting at each PVC instead of resolved implicitly at admission time.
- Two classes remain annotated as default, but nothing in the repo relies on which one wins.
- **New PVCs must set `storageClassName` explicitly.** Omitting it is no longer a supported pattern here, even though it
  would still happen to work.

## Update (2026-08-23): the tiebreak flipped, and the first pass was incomplete

The last rejected alternative above guessed that "a future k3s upgrade that recreates the `local-path` SC would make it
the newest default". That was too optimistic — it takes no upgrade. k3s re-applies the AddOn on **every start**, so
`local-path` is recreated with a fresh `creationTimestamp` each time. Measured immediately after the next k3s restart:

```
local-path   2026-08-23T00:44:12Z   is-default=true    # minutes old
nfs-pv       2026-08-12T20:59:52Z   is-default=true    # 10 days old
```

`local-path` is therefore **permanently** the newest default and permanently wins the tiebreak. Confirmed with a
server-side dry-run (persists nothing):

```
$ kubectl create --dry-run=server -f - <<< '<PVC with no storageClassName>'
ponytail-tiebreak-probe -> storageClass=local-path
```

The first pass only pinned PVCs declared as **raw manifests**. Every Helm-rendered PVC was still riding the default.
`global.storageClass` in `templates/globals.yaml` does not help: `app-template` ignores it (verified by rendering the
chart with and without it). Rendering all `app-template` services showed **24 of 24 PVCs with no `storageClassName` at
all**, plus three unpinned volume claims in `kube-prometheus-stack`.

Had any of those PVCs been recreated, a volume declaring `ReadWriteMany` would have been satisfied by node-local RWO
`local-path`, and its data would have disappeared on the next reschedule — silently, because both ApplicationSets
carried an `ignoreDifferences` entry hiding `/spec/storageClassName`.

So, additionally:

4. Pin `storageClass: nfs-pv` in `templates/common.yaml`, which is applied as `commonValues` to every service and so
   covers the shared `config` volume in one place.
5. Pin the five service-local volumes that are not named `config`, and the three `kube-prometheus-stack` claims
   (grafana, prometheus, alertmanager).
6. Drop the `/spec/storageClassName` `ignoreDifferences` from both ApplicationSets. It was added on the premise that the
   field had been "dropped from desired manifests now that nfs-pv is the sole cluster default" — both halves of which
   are now false. With every PVC pinned, Git and the cluster agree, so the field can be diffed honestly again.

Verified the same way as the first pass: rendering every `app-template` service goes from 24 `<UNSET>` to 24 `nfs-pv`,
and all 24 match the live cluster exactly — a provable no-op that only closes the future-recreation hole.

### Note on the immutable StatefulSets

`prometheus` and `alertmanager` store through `volumeClaimTemplates`, which are immutable. Setting `storageClassName` on
a live StatefulSet is a 422 `Invalid` update, which prometheus-operator handles by **deleting and recreating the
StatefulSet** (`ForceUpdateStatefulSet` in `pkg/k8s/statefulset.go`, `DeletePropagationForeground`).

This is safe _here_, and was checked before making the change: both StatefulSets have
`persistentVolumeClaimRetentionPolicy: {whenDeleted: Retain, whenScaled: Retain}` and their PVCs carry **no
`ownerReferences`**, so the volumes survive and are re-adopted by name. The cost is a pod restart on the next sync.

The same is _not_ true of `loki`, whose STS is `whenDeleted: Delete` and whose PVC **is** owner-referenced — deleting
that StatefulSet would delete its volume. Loki and tempo were already pinned, so no change was needed there; the check
is recorded here because the next person to touch a `volumeClaimTemplate` needs to run it first.

## Update (2026-08-24): the second pass was incomplete too — `commonValues` does not reach `infrastructure/**`

The pass above pinned every service by adding `storageClass: nfs-pv` to `templates/common.yaml`. That file reaches an
app only if the ApplicationSet generator passes it as `commonValues`, and in `bootstrap/appsets/cluster-apps.yaml` only
the `services/**` generator does — `infrastructure/**` is generated with `commonValues: ""`.

So `crowdsec` and `pgadmin` kept rendering `storageClassName: null` against live PVCs bound to `nfs-pv`. With the
`ignoreDifferences` entry now gone, Argo tried to null an immutable field and the API server refused:

```text
PersistentVolumeClaim "crowdsec-db-pvc" is invalid: spec: Forbidden:
spec is immutable after creation except resources.requests and
volumeAttributesClassName for bound claims
```

A bound PVC's spec is immutable, so this never converges — it just retries. crowdsec reached retry #7 and pgadmin #10
before it was noticed. Fixed by pinning in each app's own `values.yaml`.

**The generalisable part:** `templates/common.yaml` is a `services/**` mechanism, not a repo-wide one. Anything under
`infrastructure/**` must set storage explicitly in its own values file, using **that chart's** key — they are not
interchangeable, and none of these three are:

| Chart                  | Key                                           |
| ---------------------- | --------------------------------------------- |
| `app-template` (5.1.0) | `persistence.<name>.storageClass`             |
| `pgadmin4` (1.66.0)    | `persistentVolume.storageClass`               |
| `crowdsec` (0.24.0)    | `lapi.persistentVolume.data.storageClassName` |

`app-template` additionally **ignores** `global.storageClass`, so there is no repo-wide shortcut available even for the
services. Read the key out of `helm show values` rather than assuming it.
