# Retire Jellyfin iSCSI plumbing

Approved scope: remove the unused legacy driver, bindings, CHAP credentials,
writer authorization/guards/scripts and NAS export; retain the original ZVOL,
all snapshots, independent backup and historical evidence. Proxmox CSI/Jellyfin
remains running. Migration merge authority ended; deliver reviewable PRs for user
merge in the ordered retirement sequence below.

1. Trace dependencies and prepare Apps/Ansible source removal in isolated branches.
   Preserve native maintenance locking, worker retirement, CSI topology/bootstrap,
   current CSI qualification and generic NAS transport. Remove the iSCSI-only
   enrollment/fencing tooling and optional historical status/preflight executor.
   Preserve installed immutable runtime/manifest as historical evidence; retire
   its old service entry point rather than rewriting that runtime in place.
2. Remove obsolete Apps mutation/admission CI and keep current Proxmox CSI and NAS
   transport validation. Replace the active storage runbook with current-state
   guidance; historical reports remain dated evidence in Git.
3. Validate remaining checks and obtain one final scoped review. Create and attach
   Ansible cleanup PR and a draft Apps cleanup PR. Stop for the Ansible merge.
   Apps must remain draft until NAS export retirement: its automatic pruning
   removes the old alias/PV/IQN guards.
4. Under fresh owned maintenance, recheck accepted Jellyfin target, exact legacy
   inventory, no old consumers/attachments/sessions and full recovery preservation.
   Archive sanitized object identities. Stop/disable NAS iSCSI only if the sole
   target/extent/mapping/auth/initiator set is still exactly Jellyfin's. Delete only
   export metadata with the native disk-removal option explicitly false.
5. After verifying NAS export retirement, mark the Apps PR ready and stop for
   its user merge. Reconcile the merged Apps cleanup. Explicitly delete the retired prune-protected
   source PV/PVC with Retain; remove orphan CHAP/authorization resources and old
   dynamic authorization guards after export removal, then the idle driver namespace.
   Keep the short archived-claim deny policy throughout both merges and retirement;
   keep the original NFS claim prune/delete-protected. Retire the old
   runner unit/request entry point and only its exact credential copies/owned
   fencing identity after verifying exclusive ownership. Preserve permanent NAS,
   CSI, kubeconfig, sealing-key and generic runner credentials and all evidence.
   No package/kernel change or reboot. Verify Jellyfin/LDAP/one CSI attachment,
   source GUID/snapshots/backup and no active old iSCSI resources; release ownership.

Expected: no Jellyfin outage, no source-data deletion, no new controller or custom
runtime replacement, normal Terraform-to-Ansible lifecycle preserved. Failure
keeps the owned operation/evidence; do not clear a lock or remove finalizers to
conceal an uncertain writer. Partial metadata retirement is journaled and resumed
against exact identities, never repeated blindly.
