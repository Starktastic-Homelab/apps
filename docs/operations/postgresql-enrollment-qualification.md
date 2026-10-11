# PostgreSQL enrollment and retained startup qualification

The disposable native PostgreSQL qualification passed on 11 October 2026.
At qualification completion, production enrollment and the retained startup
overlay remained inactive. This record does not authorize production database
changes or an NFS-to-CSI migration; subsequent activation is documented in the
[operations guide](postgresql-enrollment.md).

The tested sources are [PR1324](https://github.com/Starktastic-Homelab/apps/pull/1324)
(enrollment), [PR1326](https://github.com/Starktastic-Homelab/apps/pull/1326)
(consumer completion gate), and
[PR1327](https://github.com/Starktastic-Homelab/apps/pull/1327)
(retained startup guard, merge `3ffde755742e4230b01305269e8f3da3722e6c38`).
The [qualification plan](../superpowers/plans/2026-10-10-postgresql-enrollment-native-lab.md)
defines the matrix and production boundary.

## What passed

| Check | Observed result |
| --- | --- |
| Native first installation | Explicit one-time registry bootstrap; sealed canonical credentials; successful native Argo full-sync enrollment hook and database authentication. |
| Idempotency and hook lifecycle | Same-generation retries preserved database identity, ledger, catalog and password verifiers. Failed hooks retained evidence; successful hooks were cleaned up. |
| Existing database adoption | A synthetic legacy database retained its data, credential verifier, owner, memberships, extension, schema/table grants and default privileges. Wrong owner, attributes and password failed without takeover. Removing the declaration retained SQL objects and data. |
| Consumer acceptance | Fresh consumers in both controllers and services phases waited for current successful enrollment, including when login was already possible after a deliberately failed authentication child. Selective/apply-only sync, stale acceptance, denied API reads and unavailable API connections did not release fresh writers. |
| Read-only startup guard | The actual pinned Bitnami Pod started with the sole identity guard preceding its stock entrypoint. A wrong expected identity on the retained lab disk blocked the entrypoint; restoring the exact expectation recovered the same database. |
| Startup negatives | Nine isolated Kubernetes fixtures rejected empty data, wrong identity, wrong major, control CRC damage, truncated control, standby/recovery signals, and unreadable base/WAL directories before the main container started. Valid fixture identities were independently bound before each guard execution. All fixture Pods and ConfigMaps were removed. |
| Missing image | Stock Proxmox CSI returned `NotFound`; neither init nor main containers started. Independent Proxmox content checks confirmed no replacement image was created. |
| Complete compute replacement | Explicitly replacing the control plane automatically planned replacement of both workers through the native Terraform incarnation trigger. All three old generations were stopped before replacement and all three replacements had fresh roots and VM UUIDs. Native Ansible installed the new cluster with retirement checks present; fresh metadata contained no stale Nodes to retire. Writer exclusion in this test came from the verified old-VM stops and cohort replacement. |
| Fresh Kubernetes metadata | Namespace, Node, PV, PVC and Pod generations changed. The unchanged static Git binding reattached the retained image without manual PV/PVC repair. Normal ApplicationSet reconciliation completed the native hook and released both fresh consumers unattended. |
| Data and credentials after rebuild | The physical system identifier, complete enrollment ledger, role verifiers, catalog, memberships, legacy grants/extensions/default privileges and legacy data were unchanged. All twelve previously acknowledged rows survived abrupt old-compute loss; both fresh consumers added new acknowledgments. |
| Cleanup | Independent readback confirmed all operation-owned VMs, roots, synthetic image, dataset/export, storage, pool, users, tokens, roles, ACLs and containers absent. Private credential/key/kubeconfig/verifier copies were removed and the original maintenance owner was released. Production VM configurations, the recorded ACL baseline and original NAS exports matched. |

The rebuild reused the existing synthetic sealing key and encrypted Git inputs.
It did not repeat SQL registry bootstrap, regenerate passwords, reseal credentials,
restore Kubernetes metadata, request a backup checkpoint, or repair PV bindings.
The test used synthetic databases and a dedicated NAS dataset; production database
contents, passwords and the production sealing private key were not copied.

## Tested environment

| Component | Frozen version |
| --- | --- |
| PostgreSQL server | Bitnami PostgreSQL 18.6, chart 18.12.4, image digest `b74b23f091dcc87041bcae557d840c36458af46b955279cb13aedec4c32d7f71` |
| Enrollment client | PostgreSQL 18.6 Alpine, digest `6c538e7206ea40ff740ef27883529390a690b6ead6ba96b44c67a9f7c638e8fd` |
| k3s | `v1.37.0+k3s1` |
| ArgoCD / chart | `v3.5.3` / `10.9.2` |
| Sealed Secrets / chart | `v0.40.0` / `2.20.0` |
| Stock Proxmox CSI / chart | `v0.20.0` / `0.5.10` |
| Terraform source | `3331a4f058ae7ae7a4e8f70a060d60f9ecf39a4b` |
| Ansible source | `6d520867695f8d9b3071dec2ef53938abf808e04` |

The disclosed lab overrides used 2 GiB per VM, staged stopped clones for watchdog
binding before serial starts, used lab addresses and selectors, and excluded
kube-vip. They preserved the native module's disk ownership and control-plane
incarnation behavior, native k3s/retirement roles, original ApplicationSet phases
and values cascade, and unmodified upstream CSI filesystem handling. Native Helm
charts installed the lab controllers; this was not a production CI workflow run.
Synthetic acknowledgment writers were made idempotent for restart of the same Pod
UID; their exact acknowledged payloads were verified before the rebuild.

## Limits and recovery contract

Normal compute/metadata replacement needed no manual recovery checkpoint. The
already-accepted storage-fault trade-off remains: the deliberately missing image
left external-attacher finalizers on its never-attached test metadata. Cleanup
required independently confirming image absence and `attached=false`, then
removing only the exact test attachment/PV finalizers. This was fault recovery,
not a step in the successful cluster rebuild.

The guard checks retained PG18 data identity, expected structure/access and native
control-file validity. It is not a full data/WAL integrity check or a writer fence.
RWOP attachment and verified old-VM retirement/cohort replacement supply the
fencing contract. Under that contract, the selected policy accepts stock Bitnami
PID cleanup after the guard passes; abrupt lab compute loss recovered successfully.

This qualification does not establish a production rollout, cold-copy migration,
off-NAS restore, future image/chart compatibility, or all application-specific
PostgreSQL converters. Those retain their separate inventory and approval gates.

## Evidence and next boundary

Sanitized immutable receipts remain on VM300 under
`/var/lib/homelab-maintenance/operations/pg-enrollment-native-qualification/receipts/`.
Key records are `retained-startup-integration-complete`,
`retained-startup-identity-negative-complete`,
`retained-startup-fixtures-retry-complete`, `startup-missing-image-cleanup-complete`,
`rebuild-terraform-plan-complete`, `rebuild-terraform-apply-complete`,
`rebuild-cluster-ready`, `retained-startup-rebuild-restore-complete`,
`cleanup-access-final-complete`, `cleanup-owner-release-complete`, and
`independent-final-verification`. Historical failed probe/cleanup attempts remain
recorded separately; their completed deletions were reconciled rather than replayed.

The next production proposal must bind the current server's physical identity,
storage and credential layout before one-time registry bootstrap and an inactive
to active manifest PR. Use a synthetic production pilot before individually
inventoried legacy adoption and application conversion. PostgreSQL NFS-to-CSI cold
copy, startup fencing, capacity and independent restore remain separate scope.
