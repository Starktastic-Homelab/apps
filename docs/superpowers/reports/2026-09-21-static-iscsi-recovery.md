# TrueNAS 25.10.7 retained static iSCSI rehearsal

The isolated rehearsal supports a **stock node-manual CSI plugin with externally managed NAS lifecycle** as the next pilot candidate. Two complete K3s VM/disk replacements recovered the same storage through actual Argo and Sealed Secrets. This is lab qualification, not production migration approval or a production-ready recovery operator.

## Results

| Check | Observed result |
| --- | --- |
| Production after NAS upgrade | 3 Ready nodes without pressure, 125/125 ready pods, 77/77 Synced/Healthy applications, 68/68 original bindings, 38/38 SealedSecrets, 7/7 certificates |
| Blank actual NodeStage | Stock `mkfs.ext4 -m 0 -n` followed by failed `blkid`; mount failed and the entire 128 MiB LUN hash stayed unchanged |
| Existing storage | Explicitly initialized unpartitioned ext4 mounted normally; normal SQLite startup refused missing databases |
| Damaged media | External verification rejected a wrong valid filesystem UUID, corrupted superblock and partition table before writable mounting; each refusal preserved the full-device hash |
| Access controls | Actual wrong CHAP and foreign initiator logins rejected; admission rejected 11 dynamic, alias, identity and writer-hold bypass cases |
| Sealing-key loss | Secret decryption failed, CHAP stayed absent and a writer was denied; restoring the external key recovered the secret |
| Clean movement and contention | Drain preserved all acknowledgements; a second RWOP pod remained Pending |
| Partition and fencing | Both old writers committed while only their control NIC was disconnected; stale UUID and HTTP401 fencing failures left replacement held; exact VM power-off preceded stale-pod deletion and replacement |
| Fresh-cluster recovery 1 | New CA/node/PV/PVC UIDs; same 3 ZVOL GUIDs and filesystem UUIDs; 16/16 prior acknowledgements per service recovered |
| Fresh-cluster recovery 2 | Again new CA/node/PV/PVC UIDs; same storage; 21/21 prior acknowledgements per service recovered |
| Snapshot and lost reply | Discarded the snapshot reply before success recording, reconnected and found exactly one snapshot; distinct clone target retained CHAP/ACL and all 26 source transactions |
| Interrupted expansion | Separate NAS/device/filesystem/record stages grew service-a from 2 to 3 GiB; ordinary recovery rejected unreconciled capacity; actual Argo rebound the retained data at 3 GiB |
| Prune, application and direct deletion | Argo reported PruneSkipped for both PV/PVC; cascading Application deletion retained both identities; direct deletion of the quiesced pair retained native data, which new Git-managed objects rebound |
| Independent restore | With the exact lab NAS VM stopped throughout, backups restored on hypervisor storage with integrity `ok` and all 21 backup-time acknowledgements per service |
| Final data | 31 acknowledged transactions per service, exact values and integrity verified; service-a 3 GiB, service-b 2 GiB |

Evidence: [blank stage](evidence/2026-09-21-static-blank-nodestage.json), [admission](evidence/2026-09-21-static-admission.json), [fence](evidence/2026-09-21-static-fencing.json), [timeout](evidence/2026-09-21-static-fence-timeout.json), [rebuilds](evidence/2026-09-21-static-rebuilds.json), [lifecycle](evidence/2026-09-21-static-lifecycle.json), [independent backup](evidence/2026-09-21-static-independent-backup.json), [final identities and acknowledgements](evidence/2026-09-21-static-final-state.json).

## Operational implications

NFS remains appropriate for the existing shared media and backup paths. This candidate puts each SQLite application database on its own ext4 iSCSI volume. The durable record is the NAS identity plus filesystem/service identity and explicit binding; Kubernetes object UIDs are deliberately disposable. No NAS API credential, dynamic provisioner, snapshot controller or expansion controller is installed in Kubernetes.

A cluster rebuild restores the external sealing key, Argo source and retained bindings, then verifies native identity, filesystem and copied SQLite marker/WAL before releasing writers. The writer authorization is external to Git and tied to the newly created namespace UID. A stale authorization cannot release a fresh cluster. Fixed initiator identities are restored by role only after the old VM disks are destroyed or their exact VM identities fenced.

Maintenance is explicit. Expansion needs a writer hold, verified unmount, NAS growth, device capacity discovery, offline ext4 growth and a reconciled record. This test recreated the retained PV/PVC to establish the new capacity; it did not use Kubernetes CSI expansion. Snapshot clones get distinct native identities and authenticated targets. The clone's copied filesystem UUID and service marker remain source identities for restore verification; it was not onboarded as a new production service and was deliberately damaged only after its restore passed.

The actual NAS calls use the documented [snapshot](https://api.truenas.com/v25.10/api_methods_pool.snapshot.create.html), [clone](https://api.truenas.com/v25.10/api_methods_pool.snapshot.clone.html) and [dataset update](https://api.truenas.com/v25.10/api_methods_pool.dataset.update.html) APIs, exercised against the 25.10.7 lab.

## Limits and unresolved production work

- `-n` is mke2fs no-write mode, not a native CSI never-format guarantee. Blank actual NodeStage was exercised; damaged/partitioned/wrong-valid media was rejected by the external gate, not sent through NodeStage. Do not permit writer admission to bypass that gate.
- Fencing is an external operator workflow in this fixture. Stale UUID, denied API authorization and an artificially short client timeout were tested live; the timeout left the VM running and replacement admission held. Production-scoped fencing credentials and automation remain unqualified.
- Lost-reply reconciliation was demonstrated for snapshot creation. General onboarding interruption recovery is not an automated allocator: the one-shot fixture stops and requires inspection. The first transport-close injection produced no snapshot; the harness confirmed absence before a separately recorded post-commit fault test.
- A copied SQLite WAL is recovered outside a read-only, `noload` source mount. A filesystem that requires journal repair may remain held; no automatic repair or blank replacement is allowed.
- This is a small, single-host synthetic correctness test, not a Jellyfin workload benchmark, NAS/host HA test or full production backup/restore rehearsal. A backup on the same Proxmox host does not protect against losing that host.
- Lab Git delivery exposed two readiness races; the publisher now verifies the served revision from Argo's repository pod, and bootstrap waits for Argo readiness. An external recovery ConfigMap update also exposed an SSA ownership conflict; the external verifier now updates its own existing ConfigMap with a scoped patch.

## Decisions made during the rehearsal

- Keep the accepted isolated scope and inline execution. A wrong choice costs another lab iteration; it authorizes no production migration.
- Select the NAS data disk by pinned serial, with boot/in-use checks, after Linux device names reordered. A mismatch stops pool creation.
- Remove only checksum-matched redundant guest image archives while retaining seed media. A missing image would need reimport; the 50 GiB disk envelope was preserved.
- Serve the isolated Git source using the pinned Argo image's Git daemon and immutable commit-addressed ConfigMaps. A delivery failure holds reconciliation rather than changing production.
- Stamp the externally read namespace UID into an annotation for admission, and select only writer pods for parameter lookup; a separate policy forbids removing the writer label. These are safeguards under trusted cluster administration, not protection against a cluster administrator changing policy.
- Verify SQLite identity on a private DB/WAL copy from a read-only mount. A failed check leaves recovery held rather than repairing or initializing source storage.

## Cleanup and next step

Cleanup verified: VM IDs 910–913 and their disks, private bridges/firewall, ISO images, transient services, tunnel, host staging, local private runtime and 111 local temporary paths were removed. Runner 300 is running with its service active and listener present. Production remains 125/125 ready pods, 77/77 healthy/synced applications and 68/68 unchanged bindings; all certificates and SealedSecrets are healthy. The host reported approximately 31.9 GiB available memory and 136.1 GiB free in vm-pool. User-supplied credential files were preserved. See [cleanup evidence](evidence/2026-09-21-static-cleanup.json).

The isolated lab no longer needs the temporary worker RAM reduction. Terraform #223 can proceed through the user’s normal review/merge workflow. No production RAM change or PR merge was performed here.

After the lab review, prepare one Jellyfin pilot with a complete cold backup, a dedicated retained target, exact ownership/CHAP records and a rollback procedure. Keep media on NFS and use Jellyfin's supported SQLite backend for that pilot. Applications with supported PostgreSQL backends can be evaluated separately; this rehearsal does not require an unofficial Jellyfin PostgreSQL provider.

## Validation and review

Static identity/capacity/disk/session-ownership tests: 14 passed. Existing isolation/guard/lifecycle tests: 17 passed. Repository pre-commit formatting, YAML, JSON, shell checks and diff checks passed after formatting. The archived Kubernetes manifests were exercised by the real lab API and compared semantically with the live-tested Git source; a separate kubeconform binary was not available. One fresh independent review found one Important issue and no Critical or Minor findings: verification could log out an existing CSI session after refusing a mounted device. The fix rejects existing sessions before changing node records, accepts only a newly created probe session, and requires quiescence before releasing writers. Three regression methods (both guest scripts) reproduced the bug and passed after the fix; all 14 static and 17 prior tests pass. This final safety fix was tested with command-mocked regressions after lab cleanup; the live cluster was not recreated again.

### Review scope decisions

- Production fencing authorization and replacement coordination remain unqualified external-operator work. The cost of an incorrect assumption is unsafe replacement, so a production pilot must qualify this first.
- General onboarding interruption recovery remains inspection-required. The cost is manual recovery time; the fixture must not allocate again after an unknown outcome.
- Damaged-media NodeStage behavior remains unqualified beyond the tested blank case. The external gate must remain mandatory; bypassing it could permit unsafe device mutation.
- Workload performance, host/NAS HA and host-loss backup recovery were outside the synthetic rehearsal. The cost is additional qualification and an independent failure-domain backup before production reliance.
- The reviewer made no live calls against infrastructure already destroyed. Regression coverage verifies the final session-ownership fix; it does not constitute another live rollout.
- Previously reviewed REST and driver internals remain historical evidence. The fresh review checked narrative coherence and concentrated code review on this static continuation; the prior controller is not the selected production candidate.

No minor findings were deferred.
