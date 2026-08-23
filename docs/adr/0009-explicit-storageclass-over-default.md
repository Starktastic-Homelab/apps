# ADR 0009: Pin `storageClassName` explicitly instead of relying on a default class

- **Status:** Accepted
- **Date:** 2026-08-23

## Context

k3s ships a packaged `local-storage` AddOn that declares the `local-path` StorageClass with
`storageclass.kubernetes.io/is-default-class: "true"`. We want `nfs-pv` (RWX, NFS-backed,
survives node loss) to be the class our workloads land on.

To get there we used to ship `infrastructure/system/nfs-provisioner/manifests/local-path-default-off.yaml`,
which re-declared `local-path` with the annotation flipped to `"false"`. Its comment claimed this
gave us "exactly one default class".

It never did. k3s re-writes its packaged manifests to disk and re-applies them **on every k3s
start**, so the annotation flipped back on every restart — and k3s restarts often here (29 times
in the 14 days before this ADR). The observable result was:

- Two StorageClasses marked default simultaneously (`local-path` *and* `nfs-pv`).
- The `nfs-provisioner` Argo Application permanently `OutOfSync` on `StorageClass/local-path`,
  which masked any *real* drift in that Application.
- Workload storage silently depending on the DefaultStorageClass admission plugin's
  multiple-default tiebreak: newest `creationTimestamp` wins. `nfs-pv` only won because it was
  created 100 seconds after `local-path` on 2026-08-12.

## Decision

Stop fighting k3s over the default-class annotation.

1. Delete `local-path-default-off.yaml`. Let k3s own `local-path` entirely.
2. Set `storageClassName: nfs-pv` explicitly on the 21 PVCs that previously rode the default.
3. Keep `nfs-pv`'s own `defaultClass: true` (in `values.yaml`) as a safety net for anything new
   that forgets — but nothing in the repo depends on it any more.

## Rationale

The deleted file could not work by construction: any Argo-managed declaration of that annotation
loses to k3s's AddOn controller on the next restart. Enabling `selfHeal` on the Application would
only have shortened the window, not closed it, and would have contradicted the repo-wide choice to
keep Argo auto-sync off.

Making the 21 PVCs explicit was verified to be a **no-op against the live cluster**: the
DefaultStorageClass admission plugin had already mutated each of those PVCs to
`storageClassName: nfs-pv` at creation time, so Git now simply states what the cluster already
holds. (`spec.storageClassName` is immutable post-bind, so this was the only safe direction.)

Alternatives considered and rejected:

- **`--disable local-storage`** — would remove the SC entirely and give us a single default.
  Rejected: `media/jellyfin-cache` is a 50Gi RWO transcode cache that genuinely wants node-local
  disk, and disabling the AddOn deletes the SC its PVC binds through.
- **A `.skip` file for `local-storage.yaml`** — stops k3s managing the AddOn, so an Argo-owned SC
  would stick. Rejected: we would inherit the whole local-path-provisioner Deployment, RBAC and
  image version, on every server node, for one annotation.
- **Leaving the default ambiguous** (delete the file and nothing else) — works today, but a future
  k3s upgrade that recreates the `local-path` SC would make it the newest default and silently
  send new PVCs to node-local disk.

## Consequences

- `nfs-provisioner` can reach `Synced` and stay there, so drift in it is meaningful again.
- Storage choice is self-documenting at each PVC instead of resolved implicitly at admission time.
- Two classes remain annotated as default, but nothing in the repo relies on which one wins.
- **New PVCs must set `storageClassName` explicitly.** Omitting it is no longer a supported
  pattern here, even though it would still happen to work.
