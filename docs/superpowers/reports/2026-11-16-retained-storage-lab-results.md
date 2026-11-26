# Retained storage lab results (ADR 0017)

## B1 Step 1: read-only preflight, 2026-11-16 ~13:35 IST: PASS (DHCP pools not read)

Run with `~/.cache/claude-homelab-live/memsize/b1pre.py` and `b1bk.py`, read-only, Ben's per-session OK.

| Check | Expected | Read | Result |
|---|---|---|---|
| MemAvailable, VM300 at full 4096 MiB | >= 8.5 GiB | 20.6 GiB; VM300 balloon = maxmem = 4 GiB | pass |
| ARC | capped | size 7.98 GiB, c_max 8.00 GiB (ansible#340) | pass |
| `crashkernel=` | gone | absent from /proc/cmdline (kernel 7.0.14-29-pve) | pass |
| pstore | empty | /var/lib/systemd/pstore and /sys/fs/pstore empty | pass |
| Last backup | green | `homelab-backup@backup` 11-16 04:30 success; health 13:00 success | pass |
| usbbk free | >= 50 GiB | 527 GiB | pass |
| vzdump job | 100 and 300 only | `vmid 100,300` | pass |
| IDs 970-979, 9970, 9979 | unused | none in /cluster/resources; no k3s-block volumes for 9970/9979 | pass |
| vmbr9, `lab-nfs` | absent | `Device "vmbr9" does not exist`; no `nfs: lab-nfs` in storage.cfg | pass |
| Tag audit | no k3s/master/worker/storage tags outside 100, 200-202, 300 | none (VM 900 untagged) | pass |
| k3s-block | baseline | TrueNAS `apps/k3s-block` 110.5 GB available of a 309 GB quota; pvesm 43% used; mount vers=4.2,hard,timeo=600 | recorded |
| vm-pool | baseline | 136 GiB available (70% used) | recorded |
| vmbr0 / vmbr1 | baseline | pve 10.9.9.20/24 (vmbr0), 10.9.8.20/24 (vmbr1) | recorded |
| vmbr0 / vmbr1 DHCP pools | read | not read: they are on OPNsense, which pve cannot see | open (Ben) |

CPU (30-day RRD): host 20 threads, average 11%, max 81%. The lab's 7 vCPUs at `cpuunits 50` fit.

**DHCP pools (Ben, 2026-11-16):** .100-.254 on both vmbr0 (10.9.9.0/24) and vmbr1 (10.9.8.0/24).

## B1 Step 2: allocation (recorded 2026-11-16)

Static addresses sit outside the DHCP pools and outside the addresses already in use. Those are: .1 gateways; .20 pve;
.30 TrueNAS; k3s from offset 50 (.50-.52); VIP 10.9.9.99; LoadBalancers 10.9.9.90, 10.9.8.80, .90, .91 and .92. An ARP
and ping probe from pve found 10.9.9.60-69 and 10.9.8.60-69 silent (all INCOMPLETE), and nothing in
`/etc/pve/qemu-server` uses them.

| VM | Name | RAM, vCPU | vmbr0 (10.9.9.0/24) | vmbr1 (10.9.8.0/24) | vmbr9 | Tag |
|---|---|---|---|---|---|---|
| 970 | `lab-nfs` | 512 MiB, 1 | 10.9.9.60 | - | - | `lab-nfs` |
| 971 | `lab-storage` | 1.5 GiB, 2 | 10.9.9.61 | - | 10.99.9.10 | `lab-storage` |
| 972 | `lab-server` | 2 GiB, 2 | 10.9.9.62 (k3s VIP) | 10.9.8.62 | 10.99.9.11 | `lab-k3s` |
| 973 | `lab-agent` | 1.5 GiB, 2 | 10.9.9.63 | 10.9.8.63 | 10.99.9.12 | `lab-k3s` |
| 974-976 | lab templates | - | - | - | - | `lab` |

- Gateway 10.9.8.1 on vmbr1 (matches terraform); nameserver 10.9.9.1.
- Every lab VM has `--cpuunits 50` and no ballooning.
- Data disks: `retained` = `k3s-block:9970/vm-9970-disk-0.raw` (8 GiB); `regen` = `lab-nfs:9970/vm-9970-disk-1.raw` (4 GiB); variant N `/srv/labn/regen-n.raw` (2 GiB).
- Ceiling 5.5 GiB: stop any start that leaves MemAvailable under 3 GiB, or VM300 under 4096 MiB.

## B1 Step 3: credentials (2026-11-16): PASS

- Ben created `lab-storage@pve`, token `lab` (privsep 0), and the `LabISO` role, with the ACLs in the plan's layout
  note. Ben's `/version` call with the token returned JSON.
- `pveum user token permissions lab-storage@pve lab`: PVEVMAdmin privileges on `/vms/970`-`976` and `/vms/9970`
  only; AllocateSpace and Audit on `k3s-block`, `local-zfs` and `vm-pool`; AllocateTemplate and Audit on `local`;
  SDN.Use on `/sdn/zones/localnetwork`; audit only on `/nodes/pve`. Nothing else.
- VM300: `<lab>/creds` and `<lab>/ssh` are tmpfs (16 MiB, mode 700). `pve.env` is mode 600, root, 9 keys; its values
  were not read.
- `<lab>/ssh/id_lab` was generated (ed25519, 600), comment `lab-storage-adr0017`.
- VM300 MemAvailable 3.2 GiB (idle).
- `lab-nfs` ACL still to add after B2 Step 3.

## B1 Step 4: maintenance locks (PASS, 2026-11-16 18:19Z)

- Ben approved the window in session. ansible#342 (lab backup exclude) merged and deployed first (run 43876886087, 13:33Z).
- Precheck on VM300: no `operation.json`, no `Runner.Worker`, only `garage-server` running; MemAvailable 3.22 GiB.
- Production lock: root `/var/lib/homelab-maintenance`, owner `lab/storage-2026-11-16`, operation `lab-storage`,
  stage `acquired`, taken with the helper CI pins (ansible 8872697). `verify` OK.
- Lab lock: root `<lab>` with its own `runner-instance` (new UUID, mode 600), owner `lab/storage-2026-11-16`,
  operation `lab-playbooks`, helper from ansible `main`. `verify` OK.
- Nonces and helper copies: `<lab>/locks/` (disk, root, mode 600; values not printed). Release at B11 with the same
  owner and `MAINTENANCE_NONCE` from those files.
- Held from now to B10: no ansible, terraform or packer merge (their deploys would fail at acquire).

## B2 Step 1: lab bridge vmbr9 (PASS, 2026-11-16, Ben approved)

- Deviation: `proxmox-storage-bridge.yml` needs the CI deploy key to reach pve, which the lab must not use. The role's
  present-path steps were run verbatim through the pve helper instead (`memsize/b2bridge.py`): assert the
  `source /etc/network/interfaces.d/*` line, write `/etc/network/interfaces.d/vmbr9` (0644 root, `bridge-ports none`,
  `bridge-stp off`, `bridge-fd 0`, no address), `ifup vmbr9` only if the link is absent. No `ifreload`;
  `/etc/network/interfaces` untouched.
- Precheck: `interfaces.d` empty, no `interfaces.new`, no `vmbr9`, no guest config references it, ifupdown2 3.3.0.
- Run 1: file CHANGED, ifup CHANGED. Run 2: file unchanged, ifup skipped (idempotent).
- `ip link show vmbr9`: UP admin flag, no ports, no address (state UNKNOWN/LOWER_UP for an empty bridge, not
  NO-CARRIER). `ifquery --check vmbr0 vmbr1 vmbr9` OK. Every NIC, tap and fw port still on its old bridge; host keeps
  only 10.9.9.20 and 10.9.8.20.
- Production after: pve answers on both bridges; auth/admin 302, photos.benplus.app 200.
- Removal at B11: the role's absent path (refuses while any guest config references vmbr9).

## B2 Step 2: lab images 974-976 (PASS, 2026-11-16, Ben approved)

- Setup on VM300: packer branch `feat/retained-storage-vm` d3f390f copied to `<lab>/src/packer` (git archive);
  `<lab>/lab.pkrvars.hcl` = `base_vm_id=974`, `k3s_vm_id=975`, `storage_vm_id=976`, `vm_name_prefix="lab"`.
  Container `hashicorp/packer@sha256:5aa2160b623fad0b99f8ae8d9cc162ba9775ae428367edca88addc01bb86dd52` (Packer
  1.16.2, the `light` tag CI uses), mounting only `<lab>`, `HOME=<lab>`, credentials from `creds/pve.env` (lab token).
  No `-force`, no manifest push, no release. Launcher `memsize/b2build.py`, one build per call.
- Per-build guards: `qm status <id>` fails on pve; no `Runner.Worker`; production lock `verify` OK; var-file IDs.
- **Base 974: guard 2 (var-file IDs) did not gate it.** It false-failed on the file's own `Never 900-902` comment, and
  as an `&&` list under `set -e` it did not stop the script, so the build started without "var-file IDs OK". Guard 1
  (`qm status 974` fails) passed and the artifact is 974. Guard 2 was fixed (comments skipped, failure exits 8) before
  k3s and printed OK for k3s and storage.
- Base result: `lab-base-debian-13.7.0-20261116182528`, template 974, 5 m 49 s, kernel 6.12.117. seal.sh printed
  `userdel: user packer is currently used by process 720`; `userdel -f` removed it anyway and seal's `getent` check
  passed. VM300 MemAvailable 3.17 GiB after.
- ISO: the build re-uploaded the existing **production** ISO `local:iso/4d4333d834fd2e83e52358a5f52ab8f3049efa07.iso`
  (same name and size 792723456, checksum-verified; only mtime changed to 2026-11-16 20:26 +02). No new ISO file.
  B11 must NOT delete it.
- k3s 975: `lab-k3s-debian-13.7.0-20261116183139`, 7 m 57 s; i915-sriov-dkms 2025.12.10.2 built and signed for
  6.12.117. Storage 976: `lab-storage-debian-13.7.0-20261116184000`, 1 m 35 s; `python3-rtslib-fb` and
  `targetcli-fb` held. Guards 1-2 printed OK for both. VM300 MemAvailable stayed ~3.2 GiB.
- Template configs via the lab token (pve root CA pinned at `<lab>/pve-root-ca.pem`, TLS verification on): 974, 975
  and 976 are templates with no `ciuser`, `sshkeys` or `cipassword`.
- Clone check of 974 (no ciuser, slots 973 then 972, destroyed after each, no zvols left): machine-id 32-hex,
  different per clone (`4f31df71...`, `1ef8bf53...`), journal "Initializing machine ID from SMBIOS/DMI UUID", dbus
  link to `/etc/machine-id`, no `packer` user, no `/etc/sudoers.d/packer` or `90-cloud-init-users`, one cloud-init
  instance record, no gcc, kernel 6.12.117. cloud-init `status: error`, `users-groups`/`ssh-authkey-fingerprints`
  `KeyError('name')`: expected without `ciuser`, because the image's `default_user` has no name (same cloud.cfg as
  `main`) and both terraform roots set one. Rerun with `ciuser` pending.
- **Finding: destroying a VM drops its `/vms/<id>` ACLs (PVE 9.2.28), with or without `purge`.** The checker's two
  destroys removed `/vms/973` and `/vms/972` from `lab-storage@pve`. Per-VMID grants therefore cannot survive any lab
  destroy-and-recreate (B7 rebuilds, a terraform replace). 975 and 976 clone checks blocked (HTTP 403) until fixed.
- Fix (Ben, 2026-11-16): pool `lab-storage` with members 974-976 and `PVEVMAdmin` on `/pool/lab-storage`. `/vms/972`
  and `/vms/973` not restored. The checker clones with `pool=lab-storage` and, before every clone and destroy,
  asserts that every VM the token can see is in 970-976 (it saw exactly 974, 975, 976 each time).
- Clone checks with `ciuser=labcheck` + the lab key, all in slot 973, destroyed after each (no `973.conf`, no
  `vm-973-*` zvols left). Raw output: `~/.cache/claude-homelab-live/storage-lab/b2-clone-checks.txt`.

  | Check | 974 base | 975 k3s | 976 storage |
  |---|---|---|---|
  | machine-id (32-hex, distinct) | `8d98cb4f...` | `06081e23...` | `5688099c...` |
  | journal | Initializing machine ID from SMBIOS/DMI UUID | same | same |
  | dbus link | `/etc/machine-id` | same | same |
  | `packer` user / `sudoers.d/packer` | absent / absent | absent / absent | absent / absent |
  | ciuser created, 1 key, NOPASSWD sudo, 3 host keys, sshd active | yes | yes | yes |
  | cloud-init | done, `errors: []`, 1 instance | same | same |
  | gcc | not installed | installed (DKMS needs it) | **not installed** |
  | packages | qemu-guest-agent | + nfs-common, i915-sriov-dkms 2025.12.10.2 installed for 6.12.117 | + nfs-common, lvm2, targetcli-fb (hold), python3-rtslib-fb (hold) |
  | open-iscsi | absent | absent (by design: k3s role installs it after writing the IQN) | absent |

  cloud-init's `extended_status` is `degraded done` only for the `user` string deprecation and the "Not unlocking
  password" warning (no password is set, by design).
- terraform `storage/` (branch, now in `edb2dbf`): `variable "pool_id"` (default null) wired to `pool_id`; new
  `test_pool_is_lab_only`; `test-storage-root.py` 9/9 OK, `fmt -check` clean (terraform 1.17.2, CI's pin).
- For B11: delete templates 974-976, the pool and its ACL; keep the production ISO.

## B2 Step 3: lab NFS VM 970 and `lab-nfs` (PASS, 2026-11-16, Ben approved)

- VM 970 `lab-nfs` (`memsize/lab970.py`, lab token, lab-only guard: token saw 974-976 before, 970 + 974-976 after):
  full clone of 974 into pool `lab-storage` on `local-zfs`, 512 MiB, balloon 0, 1 core, cpuunits 50, onboot 0, tag
  `lab-nfs`, ciuser `debian` + lab key, `10.9.9.60/24` gw `10.9.9.1`, nameserver `10.9.9.1`, disk resized to 16 GiB
  (`local-zfs:vm-970-disk-0`; local-zfs is not in restic or vzdump). cloud-init done, eth0 10.9.9.60, 14 GiB free.
- NFS on 970 (`memsize/b2nfs.py`, SSH from VM300 with `id_lab`, host key in `<lab>/ssh/known_hosts`):
  nfs-kernel-server 1:2.8.3-1, versions +3 +4 +4.1 +4.2, `/etc/exports.d/lab.exports`:
  `/srv/lab 10.9.9.20(rw,no_root_squash,sync,no_subtree_check)` and (D1 variant N)
  `/srv/labn 10.9.9.61(rw,no_root_squash,sync,no_subtree_check)`. `exportfs -v` matches.
- pve (pve helper, root): `pvesm add nfs lab-nfs --server 10.9.9.60 --export /srv/lab --content images
  --options vers=4.2`. `findmnt /mnt/pve/lab-nfs`: `nfs4 ... vers=4.2 ... hard ... proto=tcp,timeo=600`. `pvesm
  status`: lab-nfs active (15.7 GiB); every other storage still active. Production probes: auth 302, admin 302,
  photos 200.
- Hard mount: before stopping 970, disable and unmount `lab-nfs` on pve (added to the plan's B1 Step 4 note).
- Ben added `PVEDatastoreUser` on `/storage/lab-nfs` (2026-11-16). Lab token check: `lab-nfs` nfs, active, enabled,
  `images`, 14.7 GB free, empty; token sees VMs 970, 974-976 only.
  Variant N's 971-side mount and loop units are Task A16 / B3.
- B11: remove `lab-nfs` (disable, umount, `pvesm remove`) before destroying 970.

## B3: lab storage VM 971 (Steps 1-4 PASS, 2026-11-16, Ben approved)

- Step 1 (lab token, `memsize/b3disks.py`): `k3s-block:9970/vm-9970-disk-0.raw` (raw, 8 GiB, sparse; under
  `images/9970`, excluded from restic by ansible#342) and `lab-nfs:9970/vm-9970-disk-1.raw` (raw, 4 GiB, sparse).
- Step 2 (`memsize/b3tf.py`): branch `storage/` root (with the `pool_id` change, now in `edb2dbf`) copied to `<lab>/tf/storage`,
  `backend_override.tf` = local state `<lab>/tf/state/storage.tfstate`, `lab.auto.tfvars.json` (mode 600): VM 971
  `lab-storage`, template 976, 2 cores, 1536 MiB, `10.9.9.61/24` gw `10.9.9.1`, vmbr9 `10.99.9.10/24`, nameserver
  `10.9.9.1`, user `debian` + lab key, tags `["lab-storage"]`, `pool_id = "lab-storage"`, generation `1`, data disks
  virtio1/virtio2 as above. Container `hashicorp/terraform@sha256:6e9c1e647c31a960dc9b59e13272f9111d90010c10b717f77ffb324767660475`
  (1.17.2), bpg 0.118.0. Prechecks: no `Runner.Worker`, prod lock `verify` OK, VM300 MemAvailable 3.2 GiB,
  `check_clone_source.py 976` OK (TLS verified with the pinned CA). Saved plan: create VM + generation only; VM 971 in
  pool, full clone of 976, cpu host, balloon 0 (`floating = 0`), NICs vmbr0/vmbr9, disks attached by path with
  `discard=on`, `cache=none`, iothread; `purge_on_destroy=false`, `delete_unreferenced_disks_on_destroy=false`,
  `prevent_destroy`. Applied the saved plan: 2 added in 43 s.
- After apply (lab token): `onboot=0` and `cpuunits=50` set by API. bpg defaults `on_boot=true` and leaves cpuunits;
  in the lab 971 must not autostart before 970. This is lab drift a later plan will show; production keeps
  `on_boot=true`.
- Step 2 checks: `qm config 971` has `virtio1 k3s-block:9970/vm-9970-disk-0.raw` and
  `virtio2 lab-nfs:9970/vm-9970-disk-1.raw`, both `discard=on`; `vmbr9` UP and `bridge link show master vmbr9` lists
  `tap971i1` (forwarding); guest eth0 10.9.9.61, eth1 10.99.9.10, vdb 8G, vdc 4G, reaches 970;
  `rtslib-fb-targetctl` failed (expected, no VGs). pve storages all active, MemAvailable 18.6 GiB.
- Step 3 (SSH, lab key): after asserting vdb = 8 GiB, vdc = 4 GiB and both blank: `pvcreate`, `vgcreate retained
  /dev/vdb`, `vgcreate regen /dev/vdc`, `vgchange --addtag hold_fence retained`. `vgs`: retained <8 GiB tag
  `hold_fence`; regen <4 GiB, no tags. Ordering ruling: `regen` stays on vdc now; it moves to the variant N loop
  device only for the B8 legs, then back (D1 text).
- Step 4: `<lab>/inventory.yml` (storage `lab-storage` 10.9.9.61; masters `lab-server` 10.9.9.62; workers
  `lab-server`, `lab-agent` 10.9.9.63) and `<lab>/vars.yml` (VIP 10.9.9.62, eth0/eth1, CSI and retirement off,
  `ansible_ssh_private_key_file` = lab key, API URL, workers' vmbr9 .11/.12, bridge .10, ssh sources
  `10.9.9.10/32` + `10.9.8.0/24`, bare repo `<lab>/apps-inventory.git` on `feat/retained-storage-vm` 785cd5bf with
  `retained-volumes.json` = `[]`, maintenance root `/maintenance/lab-storage`, lab timings with quarantine 900 s;
  variant N lines commented). Both root, mode 600.
- Housekeeping: removed packer's 757 MiB ISO download copy from `<lab>/src/packer` (VM300's disk is in the Sunday
  vzdump); `<lab>` is 89 MiB.

## B4: lab k3s and democratic-csi (2026-11-16, Ben approved)

- Step 1 (lab token, `memsize/lab972.py`): full clones of 975 into pool `lab-storage`: 972 `lab-server` (2048 MiB)
  and 973 `lab-agent` (1536 MiB), 2 cores, cpu host, cpuunits 50, balloon 0, onboot 0, tag `lab-k3s`, ciuser
  `debian` + lab key, nameserver 10.9.9.1, net0 vmbr0 / net1 vmbr1 / net2 vmbr9, ipconfig0 `10.9.9.6x/24`,
  ipconfig1 `10.9.8.6x/24` gw 10.9.8.1, ipconfig2 `10.99.9.1{1,2}/24`. Root disk grown 4 -> 16 GiB (deviation: 4 GiB
  cannot hold k3s and its images). Tag audit after start: lab VMs carry only `lab-*` tags, and production's
  `all_k3s`/`masters`/`workers` need the exact tag `k3s`, so no lab VM can join a production run.
- Lab shell: image `lab-shell:adr0017` built on VM300 from `python:3.14-trixie@sha256:1cef1664561971647b94fedf437145415991d4feeda09c81df12acfad8829cde`
  (deploy.yml's base), the branch's `requirements.txt`/`requirements.yml` (ansible-core 2.21.6, kubernetes.core 6.6.0,
  ansible.posix 2.2.2), kubectl v1.37.2 and helm v4.3.2 (checksums verified). Runs with only `<lab>` mounted,
  `HOME=<lab>`, `KUBECONFIG=<lab>/.kube/config`. `<lab>/labkube.sh` refuses unless the server is
  `https://10.9.9.62:6443` and the nodes are exactly `node/lab-agent node/lab-server`.
- Lab ansible copy `<lab>/ansible` = branch bdfbea3 (git archive). `group_vars/all/secrets.yml` replaced by an
  unencrypted file with the five keys the code reads (`docker_hub_username`, `docker_hub_token`,
  `argocd_admin_password_hash`, `argocd_oidc_client_secret`, `vault_proxmox_root_password`), all empty; no vaulted
  file left; `vault_password_file` removed from the copy's `ansible.cfg` (it would abort startup with no `.vault_pass`).
- Step 2: `--list-tasks` lists the lab guard (play 1), no `kube-vip` and no `bootstrap_cluster` task (play 9 empty).
  Real run (no `-v`): lab-server ok=53 changed=16, lab-agent ok=24 changed=13, failed=0. Checks:
  - `labkube.sh get nodes -o name` = `node/lab-agent`, `node/lab-server`, both Ready, v1.37.2+k3s1, both `worker`;
  - IQNs `iqn.2026-11.net.starktastic:lab-server` / `:lab-agent`; open-iscsi 2.1.11-1+deb13u2, `iscsid.socket` enabled;
  - `/configz` `shutdownGracePeriod: 1m0s` (critical pods 10s);
  - k3s journal: kube-controller-manager runs with `--disable-force-detach-on-timeout=true`;
  - `config.yaml` has no `max-volume-attachments` label;
  - `flannel.1`: `vxlan id 1 local 10.9.8.6x dev eth1`; eth2 saw only ~40 packets (ARP/ND), no 8472 traffic;
  - system pods pulled anonymously with the empty Docker Hub auth.
- Step 3: democratic-csi from the apps branch with lab values. CSIDriver `org.democratic-csi.node-manual`; node
  DaemonSet 2/2; controller on `lab-server`; images match the pinned digests; Secret `storage-fencer-token` exists.
- Step 4 (`storage.yml`): runs 1 and 2 failed on the k3s hosts with `'storage_vm_attached_pvs' is undefined`
  (the storage host itself was ok, failed=0). **Branch bug found**: one `set_fact` set `storage_vm_attached_pvs`
  and `storage_vm_attached_ids`, the second reading the first. Ansible templates every argument of a `set_fact`
  before setting any of them, so a sibling key is never visible. The same pattern in `expire-volume.yml` was
  worse: the claims would read the previous candidate's PVs (stale facts) instead of failing. Fix on the ansible
  branch (now in `ce72f98`): each pair is split into two tasks (`grow.yml`, `expire-volume.yml`); a new test,
  `test_set_fact_never_reads_a_sibling_key`, scans every `set_fact` in the role (both list and one-line forms);
  47 role tests pass, all `test_storage_*.py` pass, ansible-lint (production) passes, review clean. The fixed
  files were copied into `<lab>/ansible`.
  Run 3: failed=0. Run 4 is the idempotence run: failed=0, and the only changes are the always-changed scratch tasks
  (inventory checkout, temp kubeconfig, dry-run copy, cleanup).
  Checks on 971: `rtslib-fb-targetctl`, `nftables` and `storage-fencer` are active; `/etc/storage-fencer/token` and
  `ca.crt` are root, mode 600. `targetcli` has no targets and both VGs have 0 LVs, as expected with an empty
  inventory. The fencer logged `error: API: token unreadable` twice at 21:14:02-03, before the role wrote the token
  at 21:14:04. The role then restarted it at 21:14:07 (NRestarts=0), with no error since.
  `storage-fencer.prom`: `storage_fencer_last_api_success_timestamp_seconds` is current;
  `api_errors_total{auth,unreachable}` = 0; `storage_fence_failures_total` = 0.
  Reconcile success timestamp is current. **PASS.**
- Step 5: the lab inventory commit `8f5ff30f` (on top of 785cd5bf in `<lab>/apps-inventory.git`) adds `lab-sqlite`
  (new, retained), `lab-raw` (migrated, retained) and `lab-regen` (new, regenerable), each 1Gi, in namespace
  `lab-storage-test`. The same JSON is copied to `<lab>/apps-src`. `storage.yml` run 5: failed=0 (lab-storage
  changed=8).
  On 971:
  - LVs `retained/lab-sqlite`, `retained/lab-raw` and `regen/lab-regen`, each 1.00g;
  - ledger tags `ledger:<id>:created`, with `hold_fence` kept on `retained`;
  - ext4 on the two `new` LVs only (`lab-raw` is raw, `blkid -p` rc 2);
  - 3 targets, portal 10.99.9.10:3260, ACLs for both node IQNs, no-auth;
  - `storage_target_missing` = 0 for all three.
  
  Rendered PVs, PVCs and the two marker guards (Step 5 command plus `--show-only templates/retained-volumes-guard.yaml`)
  and applied them; all three PVs are Bound RWOP Retain. The writer (`<lab>/b4/writer.yaml`) is a one-replica Recreate
  Deployment with a preferred affinity for `lab-agent`, not a hard selector, because later steps move it with cordon.
  Its initContainer runs `lab-sqlite-retained-guard` read-only. The writer uses WAL and `synchronous=FULL`, and writes
  numbered rows 1..n. It logs `ack <n>` after each COMMIT, and at start it checks `integrity_check` and that the rows
  are contiguous (exits 3 otherwise).
  Result:
  - guard `Retained volume identity accepted.`;
  - `start host=lab-agent integrity=ok count=0 max=0 contiguous=True`, then `ack 1..`;
  - pod Running on `lab-agent`;
  - VolumeAttachment `lab-sqlite` -> `lab-agent` attached;
  - iSCSI session from 10.99.9.12 (eth2) to 10.99.9.10:3260, LOGGED_IN.
  
  **PASS. B4 PASS.**

## B5: Checks 4, 5, 7 and 12 (2026-11-16 21:29-22:16, Ben approved)

Every case below ran on the lab only (970-976, `lab-storage-test`), under the production lock and the lab lock.
Evidence: run logs in `<lab>/logs/b5-*.log`, notes in `~/.cache/claude-homelab-live/storage-lab/b5/notes.md`.

### Check 4: missing and blank devices: PASS (two findings)

- **Missing LV:** PV/PVC/pod `lab-missing` with no target. Result:
  - the pod stays ContainerCreating;
  - 971 logs "Unable to locate Target IQN";
  - the agent's session is FAILED (TRANSPORT WAIT) and no block device appears;
  - no mkfs in the driver log or the agent journal.

  **F1:** the NodeStage login retry is bounded but long. democratic-csi wraps `iscsiadm -l` in `retry(15, 2000)`, and each login lasts about 2 min (8 tries × 15 s). The stage ran 19:29:24Z-19:59:58Z (30.5 min) holding the volume's operation lock. Meanwhile:
  - the deleted pod's NodeUnstage was Aborted ("operation locked");
  - the VolumeAttachment outlived its PV;
  - the agent kept a FAILED session.

  The stage returned at 19:59:58Z; at the next look (20:02Z) the VolumeAttachment and the session were gone. Risk: a target with that IQN created inside the window would be logged into with no pod.
- **Blank migrated LV:** `lab-raw` (raw) with a migrated-style guard (marker plus a native file). The driver ran `mkfs.ext4 -m 0 -O mmp -e remount-ro`. The guard listed only `lost+found`, refused, and the pod went to Init:Error. `dumpe2fs -h` shows:
  - `mmp`, interval 5;
  - errors remount read-only;
  - node `lab-agent`, clean sequence.

  971 showed the LV as blank until `blockdev --flushbufs`, because of its page cache. **Residual risk confirmed:** the driver formats a blank migrated LV; only the guard stops the app.
- **Ledgered LV missing at boot:** `lvrename regen lab-regen lab-regen-hidden`, then a reboot of 971 only. Result:
  - targetctl skipped the storage object;
  - boot-check logged `error: lab-regen: LUN 0 is not bound to /dev/regen/lab-regen` and the unit failed;
  - the `retained` targets served;
  - the writer reconnected after one connection error, with no restart and acks 1..3872 contiguous.

  After undoing the rename, `storage.yml` passed and rebuilt the LUN.

  **F2:** nothing alerts on this. `storage_target_missing` is written only by reconcile, which only runs from `storage.yml` (971 has no timer), so it keeps its pre-boot 0. node-exporter on 971 has no systemd collector.

  **N1:** after recovery `rtslib-fb-targetctl` stays `failed`. That is by design: `_start_targetctl` will not start it while sessions exist and logs a warning. The next boot starts it normally.
- **VG missing:** steps:
  1. confirmed no session on the regen IQN (configfs ACL `info`, the code's own method);
  2. deleted the target and backstore under `flock /run/lock/storage-lio` and saved;
  3. the LV was not open;
  4. `vgchange -an regen`, then removed `virtio2` with the lab token.

  Results:
  - `storage.yml` failed at the dry-run gate, refusing **every** entry (all three, not only `regen`) with `vg-missing`, with no actions;
  - a reboot with the disk detached gave `error: VG regen is missing` and a failed unit, while the `retained` targets served and the writer kept running;
  - re-attaching the same volid let udev reactivate `regen` with its ledger, and `storage.yml` passed.
- **Populated LV with no udev fs data:**
  - **Deviation:** a literal `59-` rule matching `ID_PATH` never fires, because `60-persistent-storage.rules` sets `ID_PATH` (line 110) before its blkid gate (line 123). The lab rule imports `path_id` itself first.
  - **Precondition:** after a manual login, the by-path link exists, udev has no `ID_FS_*` and no by-uuid link, while `blkid -p` sees ext4.
  - **Result:** writer scaled 0→1. The driver ran `blkid -p -o export` and no mkfs. The guard accepted; the writer reported `integrity=ok count=5645 contiguous=True`.
  - The rule was removed, and a change event restored `ID_FS_TYPE`.

### Check 5: ledger and deletion: PASS after one fix (with one ruling and one hand-made VA)

- **New:** commit A `5263fbc2` created `lab-later` (regen) and `lab-exp` (retained), each tagged `ledger:<id>:created`.
- **Lost and orphan:**
  - with `lab-raw` renamed away and an `lvcreate regen/lab-orphan`, the dry-run refused `lab-raw` `lv-missing` (blocking), `lab-raw-away` `orphan` and `lab-orphan` `orphan`;
  - with the name restored, the real apply ran and failed on `refused: lab-orphan: orphan`;
  - only `vg-missing`, `removal-brake` and `lv-missing` block the dry-run (the `BLOCKING` set in `reconcile.py`, read from the code).
- **Crash mid-create:** `-e @pause-create.json` (the whole timings map with `pause_after: ["create:lvcreate"]`).
  - The process stopped (state T) with `ledger:lab-crash:creating`; SIGKILL made the run fail with `exited -9`; the LIO flock was free.
  - The retry refused `lab-crash: crashed-create`, and the installed config went back to `pause_after: []`.
  - Cleanup was by hand (`lvremove`, targeted `--deltag`). **F3:** no runbook covers recovering from `crashed-create` or `orphan`.
- **Old SHA:** commit B `b9b3a71e` removed both. A stale clone with the branch at A was left on VM300. The run logged `… feat/retained-storage-vm at b9b3a71e…` and marked both `pending-delete`. A 40-hex `storage_vm_inventory_branch` failed at the first task after the lab guard, before any lock task.
- **Removal while running:** commit C `7652062c` removed `lab-regen` and `lab-sqlite`. The `lab-sqlite` target and LUN stayed, the tag was set, and the writer kept writing. Re-adding it 37 s later (commit D) cleared the tag.

  **Ruling:** "expiry refuses" and "re-add within 15 min" cannot both hold for one volume, because candidates exist only past quarantine. `lab-regen` carried the past-quarantine refusal.
- **Copy pair and VA isolation:** Block PV/PVC `lab-copy-src` with `volumeHandle: lab-regen` plus a pod. With the pod running, the refusal fired on the session clause first. With the pod deleted and a hand-made VolumeAttachment for `lab-copy-src` (attached, no session), expiry refused `lab-regen` on the **VolumeAttachment clause**. That proves the lookup by handle.
- **Login without a pod:** a hand `iscsiadm -l` to `lab-exp` (no pod, no VA) was refused on `not storage_vm_candidate.sessions`, in two runs; it was then logged out.
- **CI class change:** a fixture moving `lab-sqlite` from retained to regenerable gives `ERROR: lab-sqlite: class changed retained -> regenerable` and rc 1, even with `PR_LABELS=storage-removals-approved`.
- **Expiry deletes:**
  - The first real run deleted `lab-later`'s PVC and PV, but `storage-reconcile expire` exited 1.
  - **F4 (bug, fixed):** `blkdiscard` refused the LV because it carries a filesystem signature, which every `new` volume does. The volume was left half-expired: PVC, PV and target gone; LV, ledger and pending tag kept; no tombstone; no data lost. A retry is refused (sessions are unreadable for a deleted target) until `storage.yml` re-exports the target.
  - **Root cause:** util-linux `blkdiscard` refuses a signed device only when `isatty(0)`. Under Ansible (become, no pipelining) the reconcile's stdin is a pty, and `host.run` passed it through. Proven on 971: with a pty, rc 1 and the refusal; with stdin `/dev/null`, rc 0 and the signature gone. The unit tests mock `host.run`, so they could not see it.
  - **Fix** on the ansible branch (now in `ce72f98`): `host.run` now runs every command with `stdin=subprocess.DEVNULL` (this also stops an LVM prompt from hanging). `blkdiscard` stays without `-f`, because `-f` also drops the `O_EXCL` open that refuses a still-mounted or held LV. `test_run_stdin_is_devnull` puts a pipe on fd 0 and checks the child sees `/dev/null` (red before the fix); `test_expire_order` pins the argv without `-f`.
  - The lab runs below used a first fix (`blkdiscard -f`); the final fix was installed afterwards (`storage.yml` failed=0) and its mechanism proven directly on 971, not by a second expiry.
  - With the first fix installed, `lab-later` expired (LV and target gone, `tombstone:lab-later`). After logout, `lab-exp` lost its PVC, PV, target and LV, gained `tombstone:lab-exp`, and the run exited rc 0.
- **Tombstone:** re-adding `lab-exp` gives `refused: lab-exp: tombstoned`, with no LV and no target.
- **Hold:** with `hold_create` on `retained`, `lab-held` was refused `hold-create`, `storage_hold_create` = 1, and the run failed. Only `hold_create` was removed afterwards (`hold_fence` kept).
- **Lock:** with only the lab lock released, `storage-expiry.yml` failed at "Verify maintenance ownership" while `lab-later` was deletable, and nothing was deleted. The lock was then re-taken with a new nonce.

### Check 7: online growth: PASS

- 1→2Gi: LV 2.00g; the pod's `df` shows 2,077,073,408 B with no restart.
- 2→3Gi with `pause_after: ["grow:lvextend"]`:
  - paused with the LV at 3.00g and the backstore at 3.0 GiB, the filesystem still 2 GiB;
  - SIGKILL, then a retry;
  - the filesystem reached 3,133,972,480 B with no restart.
- Later inventory commits carry `lab-sqlite` at 3Gi.

### Check 12: network, metrics and reclaim: PASS

- **Unlisted bridge source:** `nc -s 10.99.9.50` → 10.99.9.10:3260 times out; `-s 10.99.9.12` succeeds.
- **LAN sources:** from 973's 10.9.9.63 and 10.9.8.63, and from pve, 10.9.9.61:3260 and :9100 all fail. The nft input policy is drop:
  - tcp/22 only from 10.9.8.0/24 and 10.9.9.10;
  - 3260/9100 only on eth1, to 10.99.9.10, from .11/.12;
  - `@fenced` is dropped first.
- **SSH:** after `systemctl reload nftables` (the fenced set survives), SSH from the lab-shell container works.
- **Metrics:** from 973 (source .12), `storage_pending_delete` shows all four removed ids with their `since`.
- **Unstage isolation:** a second volume (`lab-raw`) on 973 next to the writer was unstaged. Its session and mount are gone; the writer showed no restart and no I/O errors, with acks contiguous.
- **Reclaim:** `du` of `k3s-block:9970/vm-9970-disk-0.raw` was 411,409 KiB with the 400 MiB fill, and 1,545 KiB after the expiry (apparent size 8 GiB in both).

### Review of the B5 fixes

A review workflow read the B5 changes. Confirmed findings:

- **F5 (medium, fixed):** `grow-volume.yml` ran `resize2fs` whenever a VolumeAttachment existed, but a VA outlives the login and the mount (before NodeStage, after NodeUnstage, a failed mount). On an unmounted filesystem `resize2fs` takes the offline path: it demands `e2fsck` and fails, or races kubelet's mount. The play now:
  - lists sessions (`iscsiadm` rc 21, "No active sessions", is not an error; checked live on lab-server);
  - refuses more than one session of the target;
  - only when logged in: rescans, checks the size, and runs `resize2fs` only if `findmnt --source <device>` reports `ext4` (rc 0 mounted, rc 1 not; checked live on lab-agent).

  Skipping is safe because the play is level-triggered. `test_growth_play_is_level_triggered` pins the gate, the `findmnt` argv and the rc handling.
- **F4's root cause** (above): stdin pty, not the signature; fixed in `host.run`.
- Minor, open for the migration plan:
  - `mkfs` and discards run with no timeout while `LIO_LOCK` is held, so a hung device blocks the fencer and boot check;
  - the fake `sessions()` returns `[]` for a deleted target, so the tests cannot see the real retry refusal after a half-expiry;
  - recovery from a half-expired volume works only through `storage.yml` re-exporting the target, and no runbook says so (joins F3);
  - `lvremove` and the tombstone `vgchange` are separate commands, so a failure between them leaves `lv-missing`, which blocks every reconcile until fixed by hand;
  - `test_failure_exits_1_and_keeps_ledger` checks only the ledger tag, not that no target or LV was touched.

After the fixes: all 8 `test_storage_*` modules pass, `ansible-lint --profile production` passes, and the lab `storage.yml` run passed (failed=0) with the writer Running.

**State after B5:**
- inventory `lab-sqlite` 3Gi, `lab-raw` 1Gi, `lab-regen` 1Gi (lab repo `4265cdbe`);
- tombstones `lab-later` and `lab-exp`;
- the writer Running on `lab-agent`;
- `rtslib-fb-targetctl` failed (N1);
- `<lab>/b5/stale-clone` left for B11.

## B6: Check 6, hangs and fencing (2026-11-16 20:37Z to 2026-11-17 00:25Z, Ben approved)

Every case ran on the lab only, under both locks. The writer was put on 973 (`lab-agent`) before each case, with its VolumeAttachment there and its rows contiguous, except Step 6 `fence:3` (kill), where F6 had left the writer stuck in MountDevice on 973. Evidence: `~/.cache/claude-homelab-live/storage-lab/b6/notes.md` (every timestamp below), writer log streams in `<lab>/b6/*.log`, metrics captures and promtool tests in `~/.cache/claude-homelab-live/storage-lab/b6/cap/`. Lab fencer settings: `not_ready_seconds` 60, loop 5 s, `proof_timeout` 30 s.

"Every acknowledged row is present" was checked against the live DB, not the log stream: the per-host `max(n)` after a move equals the old pod's last ack, and the new pod's start line says `contiguous=True` with that count. A hung node's log stream goes stale, so stream acks alone would undercount.

### Steps 1-2: baseline and fencer stopped: PASS

- **Step 1:** `hold_fence` removed. Loops clean, `fence_active` 0, failures 0, API errors 0.
- **Step 2:** fencer stopped, 973 suspended for 10 min. At the 300 s eviction the ReplicaSet made a replacement pod, which stayed Pending on the RWOP claim ("already in-use by another pod"). The VA stayed on 973 and nothing ran on 972. After the resume the same VA served a new pod on 973 with count 21259 (= the last ack). **Ruling:** the plan's "the writer is not recreated" is read as "no replacement runs and the VA does not move". The Pod object is created; only `ReadWriteOncePod` keeps it Pending, so this result depends on RWOP (an RWO claim would not hold it back). Plan wording to fix.

### Step 3: four hang cases with the fencer running: PASS

| Case | Fence after the hang | Writer Running on 972 | Count at start = last ack |
|---|---|---|---|
| `qm suspend` | 106 s | 2 min 58 s | 22272 |
| `kill -STOP` of the QEMU pid | 112 s | 2 min 56 s | 25005 |
| `freeze` inside 973 | 111 s | 2 min 48 s | 26750 |
| `net0 link_down=1` | 109 s | 3 min 5 s | 30904 |

- Each fence logged, in this order: tag `unknown`, `nft add`, ACL deletes, `nft list` + `ss` (no socket), `proven`, then `tainted`. The tag settled on the hung boot's bootID on the next loop.
- In cases 2-4 a DB read after the fence showed no `lab-agent` row past the last ack. In case 1 the replacement started at max = last ack (22272, contiguous); no later per-host read was taken.
- **link_down** is the case where 973 kept writing over its untouched storage NIC while NotReady. The ACL delete found a live session (`TARG_SESS_STATE_LOGGED_IN`); 22 ms passed from `nft add` to a passing proof. Every row 973 committed before the cut is present and none after it.
- **Ruling (freeze):** `echo freeze` has no wake path in this guest. Neither the RTC alarm nor an API resume woke the s2idle guest; a QMP `sendkey shift` did.

### Step 4: after resume: PASS

- 973 logged I/O errors and `Remounting filesystem read-only` in every case. Cases 2-4 also logged `Aborting journal`; case 1 logged a JBD2 I/O error updating the journal superblock instead.
- `dumpe2fs -h` on 972: `mmp_node_name lab-server`, sequence moving (0x3a → 0x3c in 10 s).
- `e2fsck -fn` on an `lvcreate -s` snapshot taken on 971 under the LIO lock, after a journal-only replay on the snapshot (`e2fsck -E journal_only -y`, expected for a crash-consistent copy of a mounted fs): clean except the lazy free-blocks counter of a live fs. Snapshot removed.

### Step 5: in-flight ACL removal: PASS

- With `fio` (randwrite 4k, direct, iodepth 4) on 973: `prove lab-agent` rc 1, all three ACLs present, address not in the set, one established socket listed.
- `fence lab-agent` under that load: the ACL delete with a live session took about 28 ms; proof passed; rc 0; the CLI did not taint.
- The loop then settled the tag on the current boot (the node was still Ready), tainted it, and the writer moved with count 32472 (= its last ack). `fio` died with EIO after the 120 s session recovery timeout.

### Step 6: crash convergence: PASS (one finding, one ruling)

- `pause_after` was set by hand in `config.json`, restored from a clean copy and `cmp`-checked after each case. Covered `fence:1`-`fence:6` and `unfence:1`-`unfence:5`, beyond the plan's `fence:1-5` and `unfence:1-4`. A further `fence:3` run used a hard reset of 971 instead of a kill.
- Each converged to a finished operation with at most one taint PATCH, never two out-of-service taints.
- Writer moves (start count = last ack, from the stream logs `s6f1`/`s6f3r`): `fence:1` 33102, `fence:3` with the 971 reset 36007, `fence:4` 36306, `fence:5` 36534, `fence:6` 36762. Not checked: `fence:2` (the replacement failed NodeStage, F6, and the put-back deleted it before the retry; no start line), `fence:3` (kill) (void: no writer on 973), and the chained `unfence:1-4` re-fences (convergence only).
- **Ruling:** a crash during an unfence (`unfence:1-4`) restarts the fencer with the tag `unknown`, which re-fences and settles on the new boot. The result is a finished fence plus one more reboot, which unfences. That matches `test_unfence_crash_after_reopen_refences`. `unfence:5` (tag already deleted) is a finished unfence.
- 971 hard reset at `fence:3`: `nftables` `ExecStartPost` restore-set ran before `targetctl`, and `boot-check` stripped the stale saved ACL. The cut held across the reboot, and the window S7-B predicted did not occur.
- **N3 (lab only):** the first try lost the cleared `pause_after` in the hard reset because it was not synced. Fixed with `sync` before the kill. Ansible sets `pause_after` only in the lab.
- **F6 (medium, fixed 2026-11-19, lab PASS): the first NodeStage after every fencing failover times out.** After an unclean stop, ext4 MMP makes the new mount wait ("MMP interval 42 higher than expected, please wait"; the 42 is the wait the kernel computes from the on-disk MMP check interval, which was not recorded). Observed: NodeStage started 21:58:10Z, the kernel mount completed 21:58:54Z, and NodeStage failed at 21:58:55Z with `"timeout":true` (45 s). The 30 s attribution is inferred from democratic-csi's mount exec timeout (`MOUNT_DEFAULT_TIMEOUT`, 30 s default, `mount.js:13/431`); open whether it expired at ~21:58:40 and surfaced only when the mount call returned, or the exec started later than the stage. The kernel mount stays, and kubelet's retry finds it and succeeds. The first-stage timeout is recorded for `fence:2` and the `fence:3` reset run; for the other moves it is inferred from the same MMP wait after an unclean stop (moves took ~3 min).
  - The failure seen: a put-back deleted the pod before the retry, so nothing unstaged. 972 kept the session and the mount, the VA moved to 973, and MMP refused the second mount for 10 min ("already mounted or mount point busy").
  - No data harm, because MMP blocked the double mount. A block-mode or non-MMP volume would have had no such guard.
  - **Status 2026-11-19:** cause traced in source (spec `superpowers/specs/2026-11-19-f6-mount-timeout-design.md`): the
    timeout kills only democratic-csi's bash `mount` wrapper, the mount finishes anyway, and the error is reported as
    `INTERNAL`, which kubelet treats as final, so a pod deleted before the retry never gets NodeUnstage. The 42 s is
    ext4's MMP wait for check interval 10 (worst case ~720 s). Fix (Ben): `MOUNT_DEFAULT_TIMEOUT=900000` on the node
    driver, so kubelet's non-final 2 min deadline comes first.
  - **Lab check 2026-11-19, PASS** (`~/.cache/claude-homelab-live/storage-lab/f6/notes.md`, driver lines in `f6/*-drv.txt`):
    the env was JSON-patched onto the lab node DaemonSet (writers drained) and read back as 900000 in both `csi-driver`
    containers. `/usr/local/bin/mount` is the bash wrapper, and the imageID is the pinned digest. Failover (hard stop
    973): lab-sqlite's NodeStage on lab-server took 48.1 s and succeeded on the first call (1 request, 1 response, no
    handler error, no FailedMount), and the rows stayed contiguous. Leak case: a second failover, with lab-sqlite scaled
    to 0 15 s into the 49.2 s stage. The stage returned, kubelet sent NodeUnstage 0.2 s later, and lab-server kept no
    lab-sqlite mount or session (lab-regen untouched). The next start on lab-agent staged in 4.2 s (clean unmount, no MMP
    wait), with the rows contiguous. Not covered: a wait over 120 s (the Uncertain path), which rests on the source
    reading.
  - Fix candidates: set `MOUNT_DEFAULT_TIMEOUT` above the MMP wait (for example 120 s) in the democratic-csi node env (holds either way; check it against kubelet's own NodeStage deadline). A shorter MMP interval gains little: `mmp_update_interval` is already 5 s (B5 `dumpe2fs`), the kernel minimum. A clean unmount followed by a mount elsewhere took 23 s (no MMP wait).

### Step 7: persistence during a fence: PASS (one finding, two routes)

A sampler on 971 checked set membership, the `lab-agent` ACLs and the drop rule every ~0.1 s.

- `systemctl reload nftables`: the set was seen empty from .326 to restore-set at .452 (~0.13 s); the reload started at .26, so the gap was at most ~0.19 s (the sampler runs every ~0.1 s). The rest of the ruleset stayed loaded. ACLs absent in every sample.
- `systemctl restart nftables`: one sample (.881) with no ruleset at all, then an empty set (.989), then restore-set (29.012); all between the restart at 28.83 and 29.012 (at most ~0.18 s), the no-ruleset part at most ~0.16 s. ACLs absent throughout.
- **Ruling:** the sub-second set gaps are acceptable. `generate_node_acls=0` keeps the ACL leg closed, and the proof needs both legs. During a restart's no-ruleset window (at most ~0.16 s) 971 has no filter at all, so all its ports are open; noted.
- A `storage.yml` reconcile during the fence rendered `elements = { 10.99.9.12 }` from the tag and reloaded: 866 samples, 0 bad, fencer not restarted.
- 971 soft reboot: the cut held, the fencer un-settled and re-settled on the same boot, and the writer on 972 rode through with one connection error and 0 restarts.
- **F7 (medium, open; S7-A confirmed): a stale rendered element re-cuts a worker after its unfence.** The reconcile during the fence left `elements = { 10.99.9.12 }` in `/etc/nftables.conf`. After the automatic unfence, one `systemctl reload nftables` put 10.99.9.12 back in the drop set with no tag.
  - Effect: 973 was silently cut from storage. The fencer proves only tagged workers, `storage_fence_active` stays 0, and the next reconcile does not object. It fails closed (availability only, no data risk). Any 971 reboot or nftables reload after an unfence would do it.
  - Undone with `storage.yml`, which re-rendered an empty set.
  - **Second route (from the review, by code reading, not run):** `storage.yml` reads the tags under the LIO lock (`tasks/main.yml:139-143`), but the `set_fact`, the template write and the end-of-play `Reload nftables` run outside it. An automatic unfence between the read and the handler is re-cut at once by that same play, with no later reload needed. ADR 0017's "rendered from the tags, read under the LIO lock" covers the read only.
  - Why it stays: `restore_set` (`reconcile.py:229-242`) only adds tagged addresses and never removes one; the reconcile's set check looks only for missing tagged addresses.
  - **Preferred fix (closes both routes):** make `restore-set` sync the set to the tags under `LIO_LOCK`: add the tagged addresses, then delete every element that is not a tagged worker's bridge address, skipping the delete if the tag read had errors (fail closed; `_fenced_tags` already returns an error, not an empty map, when VG `retained` is not visible, `reconcile.py:222-224`, so an early-boot run cannot strip a rendered element). Add the reverse check (an untagged element) to the reconcile's set check. One unit test each.
  - Other candidates: rendering no elements loses the atomic coverage rendered elements give on a reload, and at boot the set can be empty until the `rtslib-fb-targetctl` `ExecStartPost` restore-set (ADR: nftables starts before the VG tags are readable). Re-rendering on unfence cannot stop a reconcile already in flight, so it is dropped.

### Step 8: bootID rules: PASS (one wording ruling)

- **Reboot after the settle unfences with no manual step:** every put-back above.
- **Same-bootID resume stays fenced** (`seen-bootid`): cases 1, 2 and 4 and Step 5.
- **vmstate snapshot rolled back after the fence stays fenced:** 28 `seen-bootid` loops, 0 unfences. The restored guest's writes hit I/O errors, and no row from the rolled-back RAM reached the DB. Snapshot deleted.
- **Slow reboot** (oneshot sleep 360 before `k3s-agent`): fenced, then the tag settled on the old bootID because nothing on the new boot had posted yet. The new boot unfenced on its own when Ready, about 8 min after the reboot. **Ruling:** the plan expected a settle on the new bootID and one more reboot. The code does what the ADR argues: a boot that has not posted cannot have mounted (`node.startup=manual`), and `test_reboot_after_fence_unfences` pins it. The plan and ADR wording needs fixing; the settle on the new boot is covered by the next case. Unit removed.
- **Fencer stopped across a reboot and mount, then NotReady** (fencer stopped 2 min 48 s, under the 10 min blind limit; `k3s-agent` stopped): the fence cut a live session and settled on the new boot. An orphaned writer process (KillMode=process) committed up to 42926; the replacement started at 42926, contiguous. Once Ready again on that boot it stayed fenced (23 `seen-bootid`, 0 unfences).
- **Fencer restart while fenced:** the tag went `unknown` and settled again on the next loop. Seen at every Step 6 restart and both 971 reboots.

### Step 9: refusals and blindness: PASS (two notes)

Each case paused 973 for 180 s (well past `not_ready_seconds`) with the fencer running. Nothing was fenced in any case: 0 fence lines, tags unchanged, set empty, no taint.

| Case | Fencer evidence |
|---|---|
| `hold_fence` tag | 15 `hold` reason lines |
| dummy VA on 973, attacher `csi.proxmox.sinextra.dev` | 15 `foreign-va` lines |
| no peer (out-of-service NoSchedule taint on 972) | 15 `no-peer` lines |
| API unreachable (6443 dropped on 972) | 18 timeouts; `api_errors{code="unreachable"}` up; `last_api_success` frozen; recovered on its own |
| k3s server stopped on 972 + 973 paused | 36 `Connection refused`. **Ruling:** a server outage is blind, never a fence |
| token Secret deleted | HTTP 401 within 8 s; 37 × 401 in the pause, `api_errors{code="auth"}` 11 → 48. Re-created with the same token hash; recovered with no restart |
| token rotated (SA deleted and re-applied) | 401s continue (38 in the pause, auth 146 → 182). A `storage.yml` run copied the new token (Secret and file sha256 prefixes match) and restarted the fencer |

`StorageFencerBlind` (A15 expression) was tested with promtool against per-minute captures turned into `input_series`:

| Case | Result at minute 12 |
|---|---|
| token deleted | fires, API leg, age 648 s |
| token rotated | fires, API leg, age 656 s |
| stale textfile (fencer stopped 12 min 19 s, 973 Ready) | fires on both legs: API age 660 s, `storage-fencer.prom` mtime age 654 s; other textfiles not selected |

Each test also expects nothing at minute 0 and at minute 11, the last minute with every selected age at or under 600 s (588 s, 596 s, and 600/594 s for stale). That pins the threshold between 600 s and 648 s: a mutated `> 300` rule fails the minute-11 check. (The first version had only minute 0 and 12, which any threshold from ~5 s to ~647 s would pass.) The `absent()` legs were not exercised here. Open for the migration plan: the CI cases in apps `scripts/check-alert-policy.py` have no just-under-600 s negative case either.

- **Note (spec gap):** the plan says "the expected metrics appear" in every case. No metric exists for `hold`, `foreign-va` or `no-peer`; their only evidence is the reason lines and flat counters. A long-standing hold is invisible to Prometheus. Decide in the migration plan whether a `storage_fencer_refusing{node,reason}` gauge is wanted.
- **Note:** a rotated token stays blind until a `storage.yml` run copies it. The alert covers that window.

### Step 10: manual fence with the fencer stopped: PASS (one finding)

- **10a:** fencer stopped, 973 suspended.
  - `fence lab-agent`: rc 0, proof passed, tag `unknown`, no taint.
  - Bare `unfence lab-agent`: rc 1 with the "`qm status` … `--confirm-stopped`" message.
  - Resumed 973: still cut (prove rc 0).
  - Fencer started: loop 1 proven, tainted (once), un-settled; loop 2 settled on 973's live bootID and held it with `seen-bootid`.
  - Writer moved with count 55551 (= last ack). Reset 973: automatic unfence, writer back with count 59021.
- **10b:** fencer stopped, suspend, manual fence, then `vm stop` until the API showed `status: stopped`, `qmpstatus: stopped`, pid null.
  - `unfence lab-agent --confirm-stopped`: rc 0, tag gone, set empty, ACLs back, no taint at any point.
  - 973 started on a new boot; the writer container restarted there with count 59244 (= last ack).
- **Negative:** `fence lab-nosuch`: "is not a configured worker", rc 1.
- **F8 (medium, open; from the review, by code reading): a manual unfence of a settled tag has no guard.** `manual_unfence` (`fencer.py:266-282`) refuses only a bootID-`unknown` tag. On a settled tag a bare `storage-fencer unfence <node>` reopens storage with no bootID, Ready or history check, bypassing the loop's `seen-bootid` rule. B6 produced exactly that state several times: Step 5, 10a and the vmstate rollback each left a Ready worker on its fenced boot while 972 had the volume mounted. Within the 120 s iSCSI replacement timeout that initiator could recover its session against the mounted disk, with MMP the only guard. Step 10 tested the guard on an `unknown` tag only; no test covers a settled one.
  - Fix: require `--confirm-stopped` for every manual unfence (drop the `== UNKNOWN` condition, reword the message and the usage line), plus a test: settled tag, worker Ready on that boot, bare unfence rc 1 with no writes; `--confirm-stopped` unfences.
  - Docs: the ADR manual fallback says every manual unfence needs `qm status` stopped. The `StorageWorkerFenced` text ("If it is already Ready, it booted before the fence was settled") misreads same-boot Ready cases; reword to "a Ready worker on its fenced or a seen bootID may be a resumed or rolled-back hung boot: reboot it, never unfence it by hand".

### Lab notes from B6 (not product defects)

- **N2:** after a long suspend 973's clock lagged by the suspend time while timesyncd still said synchronized. Restarting `systemd-timesyncd` stepped it. Pod log timestamps are guest time.
- `kubectl wait --for=condition=Ready` right after a short stop returns at once on the stale Ready status; read the bootID instead.
- My first stale-textfile promtool run failed on my own expectation, which ignored the rule's `file=` filter. After the fix all three tests pass.
- ssh to 973 over eth1 (10.9.8.63) timed out from VM300; not investigated (not on the storage path).

**State after B6:**
- writer `72jz5` Running on `lab-agent`, rows contiguous (`lab-agent` max 59261 at 00:25Z);
- read-only sweep: no rendered elements in 971's `/etc/nftables.conf`, live set empty, `config.json` = clean copy, no `inet b6` table on 972, neither node cordoned or tainted;
- nothing fenced, no holds;
- VG tags `ledger:lab-raw:created`, `ledger:lab-sqlite:created`, `tombstone:lab-exp`;
- `config.json` clean, fencer active;
- `fio` on 973 and `/root/b6*` helpers on 971 left for B11.

### Fixes for F7 and F8 (2026-11-17, ansible `ce72f98`, lab re-run PASS)

- **F8:** `storage-fencer unfence` now refuses every fence tag without `--confirm-stopped`, settled or not. A worker that rebooted and is Ready needs no manual unfence: the loop does it.
- **F7:** `restore-set` now makes the live set match the fence tags.
  - It adds the tagged addresses first. Then, only when every tag was read, it removes untagged elements.
  - Any malformed, conflicting or unknown-node tag, or a missing VG, keeps every element (fail closed).
  - No crash point needs an untagged element: a fence tags before it adds the address, and an unfence removes the address before the tag.
  - Both routes converge, because the reload that brings a stale element back runs `restore-set` as its ExecReload.
  - `storage-reconcile apply` also fails on an untagged element whenever the tags parse, so the state is no longer silent.
- **Tests:** four new unit tests; four mutants killed; 196 storage tests pass. An independent review found nothing blocking.
- **Accepted edge:** changing a fenced worker's `bridge_address` makes `restore-set` drop the old address. Established flows could then pass the nft rule again; the deleted LIO ACLs still block them. Migration plan: unfence before renumbering.
- **Still to run in the lab:**
  - Step 7 route 1: render during a fence, unfence, reload. Expect: set empty, apply green.
  - Step 10: bare unfence of a settled tag. Expect: rc 1, no writes.

**Lab re-run of the fixes (2026-11-17 03:16Z to 03:24Z, Ben approved): PASS.** The three changed files went on through `storage.yml` (`failed=0`). One fence cycle on 973 followed: suspend, settled after ~112 s, writer on lab-server after 2 min 47 s with no acknowledged row lost.

| Check | Result |
|---|---|
| F8: bare `unfence` of the settled tag | rc 1 with the new message; tag kept, still cut |
| F7 route 1: `storage.yml` during the fence, auto-unfence after a reset, then `systemctl reload nftables` | The reload brought 10.99.9.12 back; its `restore-set` removed it at once ("has no fence tag"). Set empty, ACLs back. Step 7 left 973 cut here |
| Untagged element added by hand | `apply` rc 1 with the new error, set untouched; a reload removed it; `apply` rc 0 |
| Clean-up | writer back on `lab-agent`, rows contiguous; `storage.yml` re-rendered an empty set; nothing fenced or tainted |

F7 route 2 (`storage.yml` overlapping an auto-unfence) was not run: it ends in the same reload and `restore-set` path shown above.

## B7: Checks 2 and 3, rebuilds (2026-11-17 03:26Z to 07:55Z, Ben approved)

**Check 2, full k3s rebuild: PASS.**
- **Rebuild:** writer scaled to 0 first (a planned rebuild drains). 972 and 973 were destroyed, re-cloned and rebuilt with `k3s.yml`, democratic-csi and `storage.yml`; nothing failed.
- **Fencer:** while the cluster was gone it only logged API errors (refused, timeout, then the new CA's certificate errors) and fenced nothing. `storage.yml` copied the new token and CA; both checksums changed (compared, never printed). The fencer restarted and its API-success metric is current.
- **Volumes:** re-rendered from the current inventory; all three PVs Bound RWOP Retain. The writer started with `count=111424 contiguous=True`, at or past the last acknowledged row (111369).
- **Identity:** LV and VG UUIDs, VG tags, IQNs and filesystem UUIDs match the baseline, so no `mkfs` ran.

**Check 3, storage VM rebuild: steps 1, 3 and 4 PASS with F9; step 2 not proven, blocked by F10.**

| Step | Result |
|---|---|
| 1. `prevent_destroy = false`, generation 2, saved plan, apply, `storage.yml` | 971 destroyed and recreated in 55 s; the data disks kept the same `9970` volids and sizes. Fresh `storage.yml` `failed=0`: LV/VG UUIDs, tags (ledgers, tombstones), target and ACL IQNs and filesystem UUIDs identical; every target re-exported; the fencer started clean with an empty fence set |
| 1. writer | **Did not reconnect (F9).** It lost the connection 10 s after the destroy; iSCSI session recovery timed out at 120 s, ext4 went read-only, and the pod crash-looped. The target came back about 23 s later. After a pod restart: MMP wait 44 s, mounted "with errors", `count=182981 contiguous=True`, equal to the last acknowledged row. No acknowledged row lost |
| 2. `qm resize 971 virtio1 +1G`, `pvresize` | Disk 9G with the same volid; VG grew to 9 GiB |
| 2. plan with the old 8G | Shows `size = 9 -> 8` in place |
| 2. apply | **Failed with `cannot delete boot disk "virtio0"` (F10).** Nothing changed; the shrink path was never reached. A first try failed earlier on the lab token's missing `Pool.Allocate` |
| 2. plan with tfvars 9G (the runbook's follow-up PR) | No disk diff |
| 3. generation 3, template 9979 | `check_clone_source.py` exits 1, no plan file, 971 running |
| 4. restore | `prevent_destroy = true` blocks the generation-3 replace ("Instance cannot be destroyed"); with generation back at 2 the plan shows only the known lab drift (`on_boot`, `pool_id`) |

### F9: a storage VM rebuild outlasts iSCSI recovery

The rebuild cut the writer off for about 2 min 23 s, more than `replacement_timeout` (120 s). Every worker holding a volume then gets I/O errors and a read-only ext4, and each workload needs a pod restart. The restart remounts with an MMP wait of about 45 s and leaves the filesystem error flag set.

For the migration plan:
- The rebuild runbook drains first: scale writers to 0, as Check 2 did.
- Decide when a flagged filesystem gets an offline `e2fsck`. Not run here, because it writes to retained data.
- Raising `replacement_timeout` would not cover a full rebuild.

### F10: bpg disk updates delete undeclared drives

`storage/main.tf` declares only the data disks; virtio0 comes from the clone. The saved plan's disk lists held only virtio1 and virtio2, yet the apply tried to remove virtio0. Only Proxmox's boot-order check stopped it.

So "an apply neither resizes nor moves the disk" is untested. Any disk-touching update to the storage VM is unsafe until this is fixed.

Fix candidate: declare the cloned root disk (virtio0) in `storage/main.tf`, then re-run step 2's stale-size apply in the lab.

### Fix for F10 (2026-11-17, terraform `edb2dbf`, lab re-test PASS)

**Cause (bpg v0.118.0, read from source):**
- On any change to the disk list, `vmUpdate` deletes every live ide/sata/scsi/virtio drive that the config does not declare. Only cdrom and `vm-<id>-cloudinit` are exempt.
- The read side keeps only interfaces already in state, so the cloned virtio0 never shows in a plan.
- The error B7 hit is bpg's own boot-order guard. It runs before any write, so nothing was sent.

**Fix:**
- `storage/main.tf` declares virtio0 with the template's values (local-zfs, 4 GiB, discard on). The block sits after the data disks: computed `path_in_datastore` carries over by list index, and with virtio0 first the plan gave it virtio1's path.
- `data_disks` now requires a path and refuses `virtio0`.
- Three new plan tests; 11 pass.
- An independent review found nothing blocking.

**Lab re-test on 971 (writer running, rows contiguous throughout):**

| Apply | Result |
|---|---|
| Add virtio0 to the existing state | Success, with a "reboot required" warning only. Volids and sizes unchanged, nothing deleted. virtio0 has a pending option change (aio, backup, iothread at PVE defaults) until the next power cycle |
| Stale 8G against the 9G disk | `Cannot shrink k3s-block:9970/vm-9970-disk-0.raw in VM 971`; config byte-identical |
| 10G | `Cannot resize ... not owned by this VM`; config unchanged |
| Restore 9G | Plan shows only the usual lab drift |

Check 3 step 2 now passes: an apply neither resizes nor moves the disk.

**Not covered in the lab:** a fresh clone with virtio0 declared. It is traced in source only: the cloned volume is kept, with no move or resize at 4 = 4.

**For the migration plan:**
- Add a contract-index entry for packer `source-base.pkr.hcl` `disks` and terraform `storage/main.tf` virtio0. If the root grows past 4 GiB, the create fails part-way.
- Any `data_disks` change re-sends every disk's options first.

## B8 Check 8: NFS stall and export withdrawal (2026-11-17 08:30Z to 10:20Z, Ben approved; host legs approved separately)

**PASS, with findings F11, F12 and F13.** Variant N ran first: 971 mounted `/srv/labn` itself and VG `regen` sat on a loop file. Then `regen` went back to the host-attached disk, with its original identity, for the two pve-client legs.

| Leg | Retained (`lab-sqlite`) | Regen (`lab-regen`) |
|---|---|---|
| N stall: drop 971 → 970:2049, 3 min | max ack gap 0.3 s | blocked 182 s, no errors, session reset and recovered |
| N withdrawal: `exportfs -u` 971, 3 min | unaffected | I/O errors at once, ext4 read-only, recovered at the last ack (2454) |
| Host stall: `systemctl stop nfs-kernel-server`, 3 min | max gap 0.4 s | blocked 184 s, no errors |
| Host withdrawal: `exportfs -u` pve, 3 min | max gap 0.4 s | I/O errors at once, read-only, recovered at the last ack (3828) |

**Every leg:**
- No acknowledged row was lost.
- `vgs retained` and `storage-fencer prove lab-server` stayed under 100 ms.
- Snapshot `e2fsck -fn` was clean.
- pve's kernel showed only the expected NFS client lines, and pstore stayed empty.
- 971 was never paused.

**Rulings:**
- **N stall method:** a drop rule on 971 (970 has no nft). Stopping `nfs-kernel-server` would also have stalled pve's client.
- **Snapshot fsck:** replay the journal on the throwaway snapshot first. A plain `-fn` on a live filesystem's snapshot only reports unreplayed-journal noise.
- **Host `regen`:** renamed for variant N, not wiped.

**F11, the reconcile hangs during a stall (both paths).** `storage-reconcile apply --dry-run` passed its 60 s cap while the regen device was stalled. That is a Hang-policy design finding: `storage.yml` and `boot-check` would block on one dead VG. The fix is a per-VG timeout, or skipping a VG whose device does not answer. **Status 2026-11-18:** fixed in code; **lab re-test 2026-11-18 PASS with two new findings (F23, F24)**. During a 180 s regen stall every dry run returned rc 1 (`vg-missing`) in about 30 s, `storage-fencer status` took 0.12 s, a real apply refused everything in 30 s, and the fencer kept looping (31 s gap while the apply held the lock). Ben picked approach A ("fail closed"): every LVM command is scoped to one VG's PV with a 30 s give-up-not-kill limit, and the fencer reads retained only (spec `superpowers/specs/2026-11-18-storage-vm-lvm-isolation-design.md`). Steps 3–4 ran with stock activation on (F24) and are re-run under F24; Step 4's fallback result is void.

**F12, stale LVM hints (both paths).**
- During the withdrawal an `lvs` rewrote `/run/lvm/hints` without the failing PV.
- The device set did not change, so LVM never refreshed the hints. After the export came back, VG `regen` was still "missing", and the reconcile refused all three volumes, retained included, until `pvscan --cache`.
- Fix: set `devices { hints = "none" }` in the storage VM's lvm.conf.
- **Status 2026-11-18:** fixed differently; **lab re-test 2026-11-18 PASS**: after a 180 s withdrawal and restore the first apply was clean (rc 0, 0.6 s) with no `pvscan`, and `/run/lvm/hints` was never rewritten. Every command our code runs passes `--devices <pv>`, which turns hints off for that command. `hints = "none"` was not adopted, because it would make hand-typed commands scan a stalled disk (same spec).

**F23, a fence blocks on the regen ACL during a regen stall (spec item 8, lab 2026-11-18).** A hard-stopped worker with regen I/O in flight was fenced mid-stall: the tag, the nft cut and the retained ACL deletes returned at once, but the regen ACL delete (configfs rmdir with commands outstanding) blocked until the stall ended, so `LIO_LOCK` was held about 125 s and the fencer loop counted a lock failure. Cause (research, Linux v6.12 LIO and configfs source): the ACL rmdir is LIO's drain, returning only after the dead worker's queued commands finish, which the stalled disk holds; the nft cut stops new packets only. That wait is the safety barrier: nothing is tainted until it ends, so no new writer mounts while old writes can still land. What waits behind it: `restore-set`, the reconcile, manual LIO commands, and the same worker's settle and taint; `one-at-a-time` already forbids a second fence. **Status 2026-11-18:** kept by design (Ben, approach A): retained ACLs are deleted first and, for the loop's fences, `StorageFenceDraining` fires after 2 minutes; the lab case was a manual fence, which shows only as the loop's lock failures, (spec `superpowers/specs/2026-11-18-fence-drain-wait-design.md`); **lab re-check 2026-11-19 PASS** (loop fence, regen stall 360 s): the gauge was set 16 s and 143 s into the drain with `storage_fence_active` 1, retained `acls/` had already dropped the worker, the fencer sat in D state in `configfs_rmdir` -> `core_tpg_del_initiator_node_acl`, the worker's regen socket stayed ESTABLISHED, and after the uncut the ACL lines (regen last), the taint and a gauge of 0 followed; writers contiguous. A listing of the stalled target's `acls/` hangs uninterruptibly in `configfs_dir_open`.

**F24, the storage VM cannot boot while a data disk is stalled, and stock LVM activates both VGs (lab 2026-11-18/19).** With regen stalled, a reset 971 sat in the initramfs from 1.3 s to 183 s, so retained targets also waited. Recon found a larger fault: the initramfs ran Debian's stock `vgchange -aay` on both VGs at every boot, unscoped (proof, twice: `/run/lvm/vgs_online/{retained,regen}` older than `/run/systemd/system`), so no boot row so far tested the role's own activation. Diagnostic boot 2026-11-19 (regen stalled 300 s, reset 971): device-mapper loaded at 191.7 s with the stall still on, `vdc: unable to read partition table` at 288.2 s, root mounted at 288.4 s, about 2 s after the stall ended. So the hold lasts the whole stall (no bound seen up to ~290 s), and it sits in the kernel and udev, not LVM. **Status 2026-11-19:** activation fixed in code by spec `superpowers/specs/2026-11-19-storage-vm-boot-lvm-design.md` (Ben): stock activation off in the image, the role the only activator, no fallback (a wrong retained path now fails closed: no targets). Lab proof 2026-11-19 (plan Task 4, all PASS): hand-applied image change, clean boots, a no-role boot (VGs stay inactive, the redeploy activates scoped) and the F11 re-runs. Regen stalled 180 s: root mounted 1.3 s after the stall ended, no `/run/lvm/*_online` files, dm nodes born at targetctl start, 3 targets LUN 0 + 2 ACLs, writers contiguous. Wrong retained path: the deploy is refused and changes nothing; the reboot times out on the device after 90 s, targetctl fails, no dm devices, no targets, the fence set still loads; the deploy restores all, writers contiguous. The B10 boot rows hold on these boots. Hold test 2026-11-19 (Ben): one stalled boot with `module.async_probe=1` was worse than stock: 971 answered neither during the 180 s stall nor in the 200 s after it (stock: ~1.3 s after), left no journal, and needed a reset; the cause is unproven (no console capture), likely the initramfs giving up on the root device. Reverted to stock (grub.cfg identical), writers contiguous. Ben accepted the hold (2026-11-19); ADR 0017 documents it under Restoring the configuration at boot and Consequences. F24 is closed. F11 Steps 3–4 and the B10 boot rows ran with stock activation on; they are re-run under F24, and Step 4's fallback result is void.

**F13, a same-node pod delete does not restage.** kubelet reuses the existing global mount, so a read-only filesystem stays read-only. Recovery is to scale to 0, confirm the unstage, then scale back up. That remount waited about 44 s for MMP and mounted "with errors".

**Variant N notes:**
- The loop unit adopts a manual attach.
- `rtslib-fb-targetctl` `Requires=` the loop unit, and its ExecStop is `targetctl clear`. So removing variant N must re-render the drop-in before stopping the loop unit, or every target is cleared.
- The role does not remove the units; that was done by hand.
- `/srv/labn/regen-n.raw` is left on 970 for B11.

## B8 Check 9: crash, hard stops and latency (2026-11-17 10:20Z to 10:50Z, Ben approved)

**Crash: PASS.** A harness pod ran the writer with no sleep between commits and was SIGKILLed 20 times at random points (0.5 to 3 s). All 20 runs were OK:
- integrity_check was ok every time;
- row count equalled max;
- every printed ack was present.

In 19 runs, max was last ack + 1, so the kill landed between COMMIT and the ack print.

**Storage VM (971) hard stop: PASS.**
- Stopped and started straight away; LIO and the fencer were back 18 s after the stop.
- Both writers stalled 15.3 s with no I/O errors and no restarts.
- Rows were contiguous on both volumes, LV UUIDs equalled the baseline, and snapshot fsck returned 0 on both.

**Worker (973) hard stop: PASS.**
- Stopped and started straight away. The retained writer restarted in place, after ext4 journal recovery and the MMP wait, with a 117.3 s gap. The writer on the other worker saw 0.3 s.
- No acknowledged row was lost, integrity was ok, and snapshot fsck returned 0.
- The node reboot cleared the old stage, so F13 did not apply.

**Latency.** Same script on lab-agent for both paths: fio 4k randwrite with fsync=1 for 60 s, then SQLite synchronous=FULL single-row commits for 60 s.

| Path | fio IOPS | fsync p50 / p99 | SQLite commits/s | commit p50 / p99 |
|---|---|---|---|---|
| Retained (iSCSI → storage VM → k3s-block) | 158 | 6.0 / 12.0 ms | 83 | 10.2 / 24.0 ms |
| Proxmox CSI (k3s-block hot-plugged) | 158 | 6.0 / 12.0 ms | 78 | 12.0 / 20.0 ms |

The NFS backend's fsync sets the floor, and the extra storage-VM hop adds nothing measurable. No gate was set.

**Cleanup gap:** the lab token can allocate on `k3s-block` but not free (`Datastore.Allocate`). The 1 GiB comparison volume `vm-9970-disk-2.raw` is detached and left for B11.

## B8 Check 11: graceful worker shutdown (2026-11-17 10:53Z to 11:00Z, Ben approved)

**Result: FAIL on "no fence"; safety PASS.**
- The writer moved to the other worker 162 s after `systemctl poweroff`, with every acknowledged row present.
- 973 came back, and the fencer removed its fence and taint on its own when it saw the new boot ID.
- But lab-agent was fenced, because the graceful path never released the attachment.

**F14, graceful shutdown cuts NodeUnstage short.**
- kubelet's shutdown manager killed the democratic-csi node pod (`system-node-critical`) in the same second it started `UnmountDevice` for the retained volume.
- The plugin had already unmounted ext4 and logged out of iSCSI, but the RPC failed with EOF, and the retries found no registered driver.
- kubelet never recorded the unstage, so the VolumeAttachment stayed until the fencer tainted the node after 60 s NotReady.
- Without the fencer, an undrained poweroff would hold the volume until kubelet comes back: `disable-force-detach-on-timeout=true` means there is no 6-minute force-detach (corrected 2026-11-18). A drain first avoids this, because DaemonSets survive a drain.

**F15, worker poweroff takes about 2 minutes.**
- k3s-agent leaves containerd-shim processes behind, and systemd waits 90 s before killing them (corrected in the re-test below: the `cleanup` container's scope and its `DefaultTimeoutStopSec`, not systemd-shutdown).
- That kept the VM up past the fence threshold. The fence landed 14 s after the VM stopped.
- Fix candidate: `k3s-killall.sh` at shutdown. Superseded: the serial console named the cause (re-test below).

## Check 11 re-test: F14, F15, F21, F22 (2026-11-18, Ben approved each step)

Fix design: `docs/superpowers/specs/2026-11-18-csi-node-shutdown-design.md` (with its amendments); plan
`docs/superpowers/plans/2026-11-18-csi-node-shutdown.md`. The lab got the change by hand: the kubelet drop-in on both
workers and a JSON patch of the live (helm-installed) node DaemonSet; the kustomize render is covered by the unit tests;
the apps PR's diff preview and the first production sync will prove the Argo wiring (unproven in the lab). Lab timings: fencer not-ready 60 s, node status 10 s.

**F15 cause (serial console and persistent journal on 973):** the chart's `cleanup` container runs `sh` as PID 1 in a
`while true; do sleep 2; done` loop, which ignores SIGTERM. kubelet's critical tier ran out, k3s-agent stopped and left
the shim (`KillMode=process`), and its systemd scope waited `DefaultTimeoutStopSec` 90 s. Baseline drained shutdown on
the old code: 102 s. Removing `cleanup` fixed it; no k3s change was needed (the plan's F15 task was dropped).

**F21 (data integrity), found in the first Leg A.** On an undrained shutdown, kernel I/O errors and a journal abort hit
both volumes during the unstage: `umount` returned, node-manual logged out of iSCSI, the disk removal ran
`fs_bdev_mark_dead` (failing sync, `shut down requested (2)`), and the final `ext4_put_super` ran later, in the
driver's `rmdir`. Cause: `driver-registrar` mounts all of `/var/lib/kubelet` with no propagation (rprivate). A
registrar started while volumes were staged (here by the Leg C rollout) holds private copies of every globalmount, so
the host umount drops only one reference and unflushed writes are lost at the logout. Proven by a mountinfo sweep: after
a node-DS restart while staged, private copies existed only in `driver-registrar`; `csi-driver` stayed in the host's
peer group. Same report upstream: democratic-csi/charts#76 and #79 (unmerged PR #77). Fsync'd rows survived. Any
node-DS rollout (a Renovate bump) would have armed it in production.

**F22: the preStop hold did not hold.** It waited while `/proc/mounts` listed a globalmount, but the unstage's first step
(umount) removes that entry; the logout, node-record delete and `rmdir` follow. kubelet starts the critical group after
the pod unmounts, so the hook ran after both umounts and returned at once; SIGTERM reached `csi-driver` mid-unstage. The
VA was still released, by timing luck. Now the hook holds while a node-manual `globalmount` directory (removed by the
driver's last step) or an iSCSI session to `iqn.2026-11.net.starktastic.storage:*` exists.

**Lab volumes:** the ext4 error flag on lab-sqlite and lab-regen dated from 2026-11-17 (kmmpd and EIO events), not
Leg A, whose superblock write failed. `e2fsck -fnF` on 971 after `blockdev --flushbufs`: structure clean. Repaired with
`e2fsck -fy` over a manual iSCSI login on lab-agent; state clean on both, re-checked clean on 971.

| Leg | Setup | Result |
|---|---|---|
| Baseline | old code, drained `qm shutdown 973` | 102 s stop (F15) |
| Step 4 deploy | kubelet 90s/40s on both nodes, logind InhibitDelayMaxUSec 90 s, patched DS (1 container + 2 sidecar init containers) | PASS, rollout 136 s, rows PASS |
| Leg C | rollout restart with both writers on lab-agent | PASS: old staged pod held 34 s, writers, VAs, mounts and sessions unchanged, 0 unstages |
| Leg A 1 | undrained `qm shutdown 973`, F14 patch only | stop 15 s, VAs gone +32 s, no fence, rows PASS, but F21 and F22 |
| F21 control | lab-server unstage, node pod started before staging | PASS: unmount before disk removal, 0 error lines |
| F21 proof | old spec, DS restarted while staged, mountinfo sweep | private copies only in `driver-registrar` |
| F21 fix | fixed spec rolled out while staged, sweep | no private copies |
| F21 unstage | scale to 0 on lab-agent after that | PASS: unmount before disk removal, 0 error lines, rows PASS |
| Leg A 2 | fixed spec, DS restarted while staged, undrained `qm shutdown 973` | **PASS**: stop 28 s (12 s hold), both VAs gone +16 s, writers Running on lab-server +19 s, no fence (only `not-ready-too-short`), ext4 unmount before each disk removal, 0 error lines, driver server shutdown 12.9 s after the last NodeUnstage response, exit order `csi-driver`, `driver-registrar`, `csi-proxy`, rows contiguous |
| Leg B | fixed spec, nothing staged on 973 | **PASS**: stop 4 s, node plugin exits in order within 0.14 s |
| Step 7 | Proxmox host guest shutdown (read-only, pve-manager 9.2.28) | **PASS**: the k3s VMs have no `startup=`, so `stopall` allows `down // 180` s then force-stops; 180 s covers 90 s kubelet plus poweroff. Unordered VMs stop first, so workers stop before TrueNAS (order 1) and a storage VM with order 2. The master stops in the same parallel group as the workers |

**Check 11 result: PASS** on every expectation, including "no fence". Not re-run at production's 300 s fence window
(the 60 s lab window is the stricter test). Leg A 1 evidence: `storage-lab/b10/f14/lega1/`.

## B9 Step 1: single-app restore (2026-11-17 11:08Z to 11:12Z, Ben approved): PASS

- **Drain and copy:** both writers were scaled to 0 and 971 was shut down gracefully, so the outage stayed under the 120 s limit from F9. On pve, holding the backup lock, `cp --sparse=always` copied disk-0 into `/usbbk/restore/lab-20261117/` in 1 s.
- **Restore read:** the copy was attached on a loop device with `vgimportclone -n restore_20261117`, and `lab-sqlite` was mounted `ro`.
- **Result:** the copied database passed `integrity_check` with count = max = 253696, which equals the source at copy time (the writer's start-up guard read the same count).
- **Unwind:** nothing was left on pve: no loop devices, no device-mapper entries, no copy. The kernel log was clean.
- **Notes:**
  - pve's LVM saw the copy's `retained` VG but did not auto-activate it.
  - The WAL held committed rows, so a restore must copy `rows.db-wal` along with `rows.db`.
- **Not run:** the optional `zfs clone` leg needs Ben's go-ahead. Step 3 is not run (lab image excluded from restic).

## B9 Step 2: whole-disk restore while fenced (2026-11-17 11:15Z to 11:31Z, Ben approved, restore OK'd separately): PASS

**Setup:**
- With the writers drained and 971 stopped, a copy of disk-0 was taken as `T0.raw`, and a dummy `fenced:lab-server:stale` tag was added to it offline.
- After T0, `lab-later2` was added, a fresh id because `lab-later` is tombstoned in `regen`.
- 973 was then fenced by suspending it.

**Runbook steps 1–6, as written in ADR 0017:**
1. The live fence tags (only lab-agent's) and out-of-service taints (only lab-agent) were recorded, and `hold_fence` was set.
2. A rollback copy was taken, whose sha256 matched the live disk. `T0.raw` was copied over disk-0, and its sha256 matched T0.
3. Offline on pve: holds added, the live fence tag added and the stale tag deleted, with nothing left mapped.

**Results:**
- After boot, 973 was still fenced: the nft set was restored from the tag and the taint was kept.
- `storage.yml` refused `lab-later2` and created nothing. The reason was `hold-create`, not the plan's `lv-missing`, because the restored ledger never knew `lab-later2`.
- After resolving it (removed from the inventory, since it held no data) and clearing the holds, `storage.yml` passed.
- `lab-sqlite` came back at exactly the T0 row count, 255137.
- 973 was unfenced on its new boot ID, and the copies were deleted.

**F16:** while `hold_create` is set, `storage-reconcile apply` exits 1 without logging a reason, and `--dry-run` exits 0. It should log that the hold is blocking, and the dry-run should agree.

**F17:** the storage VM's LIO config is on its root disk, which a data-disk restore doesn't roll back. So targets for volumes created after the snapshot come back empty: targetctl skips the missing backstore. The reconcile neither flags nor removes them. They were removed by hand in the lab.

## B10: boot order, host reboot and late NFS (2026-11-17, Ben approved each step)

**Step 1 (Check 1 reading, Ben):** production order with a slow NFS: TrueNAS is ordered first, and its NFS is the last thing to come up. Check 1 passes on Step 3; Step 4 is a design input.

**Step 2, lab startup: PASS.**
- From `qm start 971`, `rtslib-fb-targetctl` was active and discovery from 973 listed all 3 targets within 11.4 s (two runs).
- Ruling: `up=30`. 970 was moved to `order=1,up=60`, since it serves 971's regen disk; at `order=3` a cold boot would have refused 971.

**Step 3, host reboot in production order (19:03 IST): PASS, with findings F18 and F19.**
- Stop and start order matched the slots, with no "not online" lines. pve was reachable 7 min after the reboot, and every guest was up by 19:14:31. The k3s VMs were off for about 10 min.
- pve's `pvestatd`/`pveproxy` stop jobs hung about 1.5 min on the dead NFS storages. This happens on either D1 path, since pve keeps mounting `k3s-block`.
- Lab: `rtslib-fb-targetctl` and the fencer were active 5 s after 971 booted. Writer rows were contiguous across the reboot (sqlite 348711 to 351014, regen 114940 to 117248).
- Production: healthy, apart from 3 known GPU admission-race pods, which were deleted.

**F18 (serious):** a cold boot latches a fence on the node's new bootID. The API came back still showing lab-agent's stale NotReady from before the shutdown. The fencer fenced it, then settled the fence on the bootID the kubelet re-registered with, which was its current boot. lab-agent stayed fenced while Ready, until one more `qm reboot 973`, which unfenced it in 16 s. In production, every host cold boot would leave a worker fenced and evicted. It recurred at the leg (a) restart below, where `hold_fence` blocked it. **Fix (Ben approved 2026-11-18, ansible `ce72f98`):** NotReady counts only from the fencer's watch start (its first successful API read after it starts, after a failed read, or after a gap of more than 3 loops); fence rule 2 in ADR 0017 says so. Unit tests pass. **Lab re-test PASS (2026-11-18):** with 971 up and no hold, 973 and 972 were shut down and started again (12:08-12:12Z; the API was down from 12:10:39Z to 12:12:31Z). When the API came back, lab-agent's NotReady was more than 60 s old, the shape that fenced it before; the fencer logged `lab-agent: watch-too-short` and fenced nothing. Both nodes went Ready, taints cleared, no `fenced:` tags, the nft set stayed empty, 3 targets with 2 ACLs each, and both writers' rows grew (sqlite 645633 to 647337, regen 407181 to 408876).

**F19:** the runner's lab `ssh` and `creds` directories are tmpfs, so the host reboot wiped the lab key and token. Both were restored on 2026-11-17.

**Step 4, late NFS at boot: both legs done.**
- **Leg (b), variant N:** 971 booted with its in-guest NFS blocked.
  - `srv-labn.mount` timed out after 91 s (systemd's 90 s default). The loop unit and `rtslib-fb-targetctl` then failed with "Dependency failed", leaving 0 targets, retained included, because the role's drop-in `Requires=` the loop unit.
  - Nothing retried within 60 s of the NFS coming back. One `systemctl start rtslib-fb-targetctl` restored everything in 2 s.
  - With the NFS reachable, targets were up 6 s after boot and VG `regen` activated (one sample, no udev race).
  - **F20:** SSH logins to 971 were refused for the whole mount wait (systemd-user-sessions waits for `remote-fs.target`); the console and guest agent still worked.
- **Leg (a), host path:** 970 shut down, so pve's `lab-nfs` storage was offline.
  - `qm start 971` was refused in 10 s ("storage 'lab-nfs' is not online") and 971 stayed stopped. pve logged only "not online" lines, with no hang.
  - Starting 970 and then 971 brought all 3 targets back in 45 s.
- **Final:** `hold_fence` was cleared after the node taints were gone. Writer rows were contiguous (sqlite 369372 to 370999, regen 135339 to 136937), and no fence or hold tags were left.

**Step 5 (Ben, 2026-11-19): Check 1 closed as PASS on the Step 3 reboot, with no re-run.** That reboot ran code from before
the F18, F11/F12, F14 and F24 fixes, each of which passed in the lab only through guest cycles (F18: workers cycled with the API
down about 2 min, 2026-11-18; F24: 971 reset with its NFS stalled, 2026-11-19). The whole boot sequence on the final code is
first exercised at the production cutover's host reboot.

## Decision D1: host path (Ben, 2026-11-18)

The data disks stay host-attached on `k3s-block`; variant N is rejected (ADR 0017, disk location).
- **Same on both paths:** NFS stall, export withdrawal (B8) and the host-reboot stall. F11, F12, F13 and F18 apply to both.
- **Host path better:** a late NFS fails closed and is visible. Variant N ran with 0 targets until a manual start, and blocked SSH (F20).
- **Variant N better, untested:** an oops in its NFS client would reboot only the storage VM, not the host. That gain lasts only from Retirement until the storage VM replaces TrueNAS (Ben's plan), when no NFS is left under the block data.
- **Not measured:** performance. In theory it's equal for small sync writes, and the host path does better under load, since 971 has 2 vCPUs.
- **Code:** the variant N code was removed from the ansible and packer branches on 2026-11-18. Only the oops-reboot sysctl stays.

## B11 summary (2026-11-19)

This part closes the lab (plan Task B11 Step 1). Line references (`l.`, `R L`) point to this report as of commit `19b36835` (856 lines, before this summary was added), and `ADR L` to ADR 0017 at the same commit. Every ADR change marked **edit** below goes back to Ben before production.

### Summary: checks

This summary covers plan Checks 1-12, which are ADR 0017's qualification list (ADR "Qualification in a disposable lab", l.756-830). The "Where" column gives this report's section headings, with line numbers from the 856-line version of the report.

| # | Check | Result | Where | Findings raised |
|---|---|---|---|---|
| 1 | Cold boot | **PASS** (Ben closed it on the Step 3 reboot, with no re-run on the final code, l.844-847) | B10, Steps 1-5 (l.815-847) | F18 (serious), F19; F20 came from the Step 4 variant N leg, which is a design input, not part of the check (l.817, 838) |
| 2 | Full k3s rebuild | **PASS** | B7 (l.575-579) | none |
| 3 | Storage VM rebuild | **PASS** after F10. On the first run, steps 1, 3 and 4 passed and step 2 was blocked by F10 (l.581). The step 2 re-test passed (l.633). A fresh clone with virtio0 declared is traced in source only (l.635). | B7 table (l.581-592); Fix for F10 (l.611-635) | F9, F10 |
| 4 | Missing and blank devices | **PASS** (two findings) | B5 Check 4 (l.275-320) | F1, F2, N1; the blank-LV format is a confirmed residual risk (l.294) |
| 5 | Ledger and deletion | **PASS** after one fix (F4) | B5 Check 5 (l.322-349) | F3 (open), F4 (fixed); one ruling on the quarantine wording (l.336); one hand-made VA (l.337); half-expiry follow-ups from the review (l.385-388) |
| 6 | Hangs and fencing | **PASS**, Steps 1-10 | B6 (l.399-571); F7/F8 lab re-run PASS (l.562-571); F6 lab PASS (l.452-460) | F6, F7, F8; N2, N3; rulings at l.408, 422, 441, 469, 485, 499; spec-gap note on refusal metrics (l.513) |
| 7 | Online growth | **PASS** | B5 Check 7 (l.351-358); Review of the B5 fixes (l.376-381) | F5 (from the B5 review, fixed) |
| 8 | NFS stall and export withdrawal | **PASS**, on both the host path and variant N (l.643) | B8 Check 8 (l.641-682) | F11, F12, F13; the F11 re-test found F23 and F24 (l.664, 672, 674) |
| 9 | Crash and latency | **PASS** (crash and both hard stops); latency measured, no gate set (l.710) | B8 Check 9 (l.684-712) | none. The 1 GiB comparison volume is left for B11 (l.712) |
| 10 | Restore drills | **Partial** (this summary's reading; the report gives no overall Check 10 result). B9 Steps 1 and 2 PASS. The single-app leg used a `cp` copy, not the ADR's ZFS clone; the ZFS clone leg and the off-site restic leg were not run (l.790). | B9 Step 1 (l.781-790); B9 Step 2 (l.792-813) | F16, F17 |
| 11 | Graceful shutdown | **PASS** on the re-test (l.778). The first run was a FAIL on "no fence" (l.716). Argo wiring is unproven in the lab (l.736-737), and the re-test ran at the 60 s lab fence window, not production's 300 s (l.778). | B8 Check 11 (l.714-730); Check 11 re-test (l.732-779) | F14, F15, F21 (data integrity), F22 |
| 12 | Network, metrics and reclaim | **PASS** | B5 Check 12 (l.360-370) | none |

**Measured `up=`:** after `qm start 971`, `rtslib-fb-targetctl` was active and discovery from 973 listed all 3 targets within 11.4 s (two runs). The value is set to `up=30` (B10 Step 2, l.819-821).

**Boot order:**
- **Lab:** 970 (standing in for TrueNAS) was moved to `order=1,up=60`, and 971 uses `up=30` (l.821). 971's `order=2` and the workers' `onboot` with no `startup` come from the plan's B10 Step 2 command (plan l.1386-1388); the report confirms the k3s VMs have no `startup=` (l.776).
- **Production reboot:** stop and start order matched the slots, with no "not online" lines (l.824). The plan's expectation was "VM 100 starts first, 971 next" (plan l.1399); the report does not restate the order.
- **Shutdown:** unordered VMs stop first, so the workers stop before TrueNAS (order 1) and before a storage VM with order 2 (l.776).
- **Late NFS:** this is a design input, not a check (l.817). On the host path, `qm start 971` is refused in 10 s while `lab-nfs` is offline, with no hang (Step 4 leg (a), l.839-841).

### Summary: findings

The table below lists all 24 findings. The report gives a severity for six of them: F5, F6, F7 and F8 are medium, F18 is serious and F21 is data integrity. F4 is only labelled "bug, fixed" (l.342). The other rows say "not given". Commits are from git on the `feat/retained-storage-vm` branches (2026-11-19, none pushed). Every ansible lab fix is in `ce72f98`, including F4, F5, F7, F8 and the `set_fact` fix, which its message does not name. Line numbers point to the report, `docs/superpowers/reports/2026-11-16-retained-storage-lab-results.md`, unless they say ADR.

| ID | Severity (report) | Finding | Status | Report section |
|---|---|---|---|---|
| F1 | not given | NodeStage login retry is bounded but long: about 30 min holding the volume's operation lock, and the VolumeAttachment outlives its PV | **Open.** The report names no fix. The risk is a login with no pod if a matching target appears in that window | B5 Check 4, l.283-288 |
| F2 | not given | A ledgered LV missing at boot raises no alert. `storage_target_missing` is written only by reconcile, and 971 has no timer | **Open.** No fix in the report | B5 Check 4, l.303 |
| F3 | not given | No runbook for recovering from `crashed-create` or `orphan`, or from a half-expired volume | **Open** (runbook). The half-expiry case was folded into F3 at l.386 | B5 Check 5, l.332; Review of the B5 fixes, l.386 |
| F4 | "bug, fixed" | `blkdiscard` refused signed LVs because reconcile's stdin was a pty, which left a volume half-expired | **Fixed in code** on the ansible branch: `host.run` uses `stdin=DEVNULL`; `test_run_stdin_is_devnull` is red before the fix, and `test_expire_order` pins the argv without `-f`. Ansible `ce72f98`. **Lab:** the expiries ran under a first fix (`blkdiscard -f`). The final fix was installed (`storage.yml` failed=0) and its mechanism proven on 971. A second expiry was not run | B5 Check 5, l.341-346; l.382 |
| F5 | medium | `grow-volume.yml` ran `resize2fs` whenever a VolumeAttachment existed, even when nothing was mounted | **Fixed in code**, gated on session and `findmnt`, with a pinning test. Ansible `ce72f98`. **Lab:** the `iscsiadm` and `findmnt` rc handling was checked live, and `storage.yml` passed afterwards. The report records no grow re-run under the fix | Review of the B5 fixes, l.376-381, l.390 |
| F6 | medium | The first NodeStage after a fencing failover times out on the ext4 MMP wait. A pod deleted before kubelet's retry leaks its mount and session | **Fixed 11-19** (`MOUNT_DEFAULT_TIMEOUT=900000`), apps `b2c3d350`. **Lab PASS** on failover and the leak case. Not covered: an MMP wait over 120 s, which rests on reading the source | B6 Step 6, l.444-461 |
| F7 | medium | A stale rendered nft element re-cuts a worker after its unfence. Route 2 is a reconcile overlapping an unfence | **Fixed in code** (`restore-set` syncs the set to the tags; apply fails on an untagged element). Ansible `ce72f98`. **Lab re-run PASS** for route 1. Route 2 was not run, because it ends in the same path | B6 Step 7, l.472-478; Fixes for F7 and F8, l.547-571 |
| F8 | medium | A manual unfence of a settled tag had no guard | **Fixed in code** (every unfence needs `--confirm-stopped`). Ansible `ce72f98`. **Lab re-run PASS**: rc 1, tag kept | B6 Step 10, l.528-530; l.549, l.566 |
| F9 | not given | A storage VM rebuild outlasts the 120 s iSCSI recovery, so writers go read-only and need a pod restart | **Open, for the migration plan.** No code fix: the rebuild runbook must drain first, and when to run an offline `e2fsck` is still to decide | B7 Check 3, l.586; F9, l.594-601 |
| F10 | not given | bpg disk updates delete undeclared drives; the apply tried to remove virtio0 | **Fixed**, terraform `edb2dbf` (virtio0 declared, `data_disks` validated, 3 new plan tests). **Lab re-test PASS**: Check 3 step 2 now passes. Not covered: a fresh clone with virtio0 declared, which was traced in source only | B7 F10, l.603-609; Fix for F10, l.611-639 |
| F11 | not given | The reconcile hangs past its 60 s cap while the regen device is stalled | **Fixed**, ansible `ce72f98` (every LVM command scoped to one VG's PV with a 30 s give-up-not-kill limit; the fencer reads retained only; fail closed). **Lab re-test PASS** on 11-18, and the re-runs under F24 also passed (l.674). Step 4's fallback result is void | B8 Check 8, l.664; F24, l.674 |
| F12 | not given | Stale `/run/lvm/hints` left VG `regen` "missing" after the export returned, until `pvscan --cache` | **Fixed differently** (`--devices <pv>` on every command; `hints = "none"` not adopted), ansible `ce72f98`. **Lab re-test PASS** on 11-18 | B8 Check 8, l.666-670 |
| F13 | not given | Deleting a pod on the same node does not restage, so a read-only fs stays read-only | **Open / no fix.** The report gives only the recovery: scale to 0, confirm the unstage, scale up. It did not apply to the worker hard stop, because the reboot cleared the stage (l.701) | B8 Check 8, l.676; B8 Check 9, l.701 |
| F14 | not given | Graceful shutdown cuts NodeUnstage short, so the VolumeAttachment stays and the node gets fenced | **Fixed**, apps `299490dc` and ansible `ce72f98` (kubelet drop-in). **Lab re-test PASS** (Check 11 PASS incl. "no fence"). The Argo wiring is unproven in the lab, and the 300 s production window was not re-run | B8 Check 11, l.716-725; Check 11 re-test, l.732-779 |
| F15 | not given | A worker poweroff takes about 2 min. The cause is the chart's `cleanup` container ignoring SIGTERM | **Fixed** by removing `cleanup` (no k3s change), apps `299490dc`. **Lab PASS** (baseline 102 s; Leg A 2 stop 28 s, Leg B 4 s) | B8 Check 11, l.727-730; Check 11 re-test, l.739-742, l.766-775 |
| F16 | not given | Under `hold_create`, apply exits 1 with no reason logged, while `--dry-run` exits 0 | **Open.** No fix in the report | B9 Step 2, l.811 |
| F17 | not given | A data-disk restore leaves empty LIO targets for volumes created after the snapshot. Reconcile neither flags nor removes them | **Open.** Removed by hand in the lab; no fix in the report | B9 Step 2, l.813 |
| F18 | **serious** | A cold boot latches a fence on the node's new bootID, which would leave a worker fenced in production | **Fixed**, ansible `ce72f98` (NotReady counts from watch start; ADR fence rule 2, ADR l.402-405). **Lab re-test PASS** on 11-18. Not yet run on a real host reboot (l.844-847) | B10 Step 3, l.829; Step 5, l.844-847 |
| F19 | not given | The runner's lab `ssh`/`creds` are tmpfs, so the host reboot wiped the lab key and token | **Lab environment issue** (the report gives no class; inferred). Restored 11-17 | B10 Step 3, l.831 |
| F20 | not given | Variant N: SSH to 971 is refused for the whole NFS mount wait | **Moot** (inferred; the report gives no status). Variant N was rejected (D1) and its code removed from the ansible and packer branches (packer `091f578`, ansible `ce72f98`) | B10 Step 4, l.838; Decision D1, l.851-856 |
| F21 | **data integrity** | `driver-registrar` mounts `/var/lib/kubelet` rprivate. A node-DS rollout while volumes are staged then loses unflushed writes at the next unstage | **Fixed spec proven in the lab** (no private copies; unstage PASS; Leg A 2 PASS). Apps `299490dc` (node DaemonSet patch) | Check 11 re-test, l.744-752, l.772-774 |
| F22 | not given | The preStop hold did not hold, because it watched `/proc/mounts`, which the unstage clears first | **Fixed**, apps `299490dc` (hold on the globalmount dir or an iSCSI session). **Lab PASS** (Leg A 2, 12 s hold) | Check 11 re-test, l.754-758, l.774 |
| F23 | not given | A fence blocks on the regen ACL rmdir during a regen stall, holding `LIO_LOCK` about 125 s | **Accepted by design** (Ben, approach A). Retained ACLs are deleted first, and `StorageFenceDraining` fires after 2 min for the loop's fences (a manual fence shows only as lock failures); ansible `ce72f98`, apps `299490dc`. **Lab re-check PASS** on 11-19 (loop fence, 360 s stall) | B8 Check 8, l.672 |
| F24 | not given | Stock LVM activated both VGs unscoped at boot, and 971 cannot boot while a data disk is stalled | **Fixed** for activation, packer `e43d185` and ansible `a036b47`. **Lab PASS**. The boot hold for the whole stall was **accepted** by Ben and is documented in ADR 0017 (Restoring the configuration at boot, ADR l.144-149; Consequences, ADR l.739-740). Closed | B8 Check 8, l.674 |

**Not findings:** N1 (`rtslib-fb-targetctl` stays failed by design, l.305), N2 (guest clock lag after suspend, l.534) and N3 (lab `pause_after` sync, l.443) are lab notes, not product defects.

**Unnumbered findings** (the report does not give them an F number):
- Destroying a VM drops its `/vms/<id>` ACLs. Fixed with the `lab-storage` pool ACL (B2 Step 2, l.117-122).
- A `set_fact` read a sibling key, so `storage.yml` failed and `expire-volume.yml` read stale facts. Fixed with a new test, ansible `ce72f98` (B4 Step 4, l.226-234).
- Residual risk confirmed: the driver formats a blank migrated LV; only the guard stops the app (B5 Check 4, l.294).

**Other open items:**
- The B5 review left five minor items for the migration plan (l.383-388). For example, `mkfs` and discards run with no timeout while holding `LIO_LOCK`, and there is a gap between `lvremove` and the tombstone.
- Step 9 asks whether a `storage_fencer_refusing` gauge is wanted (l.513), and a just-under-600 s CI case is missing (l.511).
- F7's accepted edge: unfence before renumbering a worker's `bridge_address` (l.557).
- F10's migration items: a contract-index entry for the packer root disk and terraform virtio0, and `data_disks` changes re-send every disk's options (l.637-639).
- Wording to fix: the plan's Step 2 "not recreated" (l.408), the Step 8 slow-reboot expectation in the plan and ADR (l.485), and the `StorageWorkerFenced` alert text (l.530).
- F6 note: a block-mode or non-MMP volume would have had no MMP guard against the double mount (l.446).
- Check 1 closed on a reboot that ran the pre-fix code (l.844-847).
### ADR changes the lab forces

Line numbers: "R" is the results report and "ADR" is ADR 0017, both as read on 2026-11-19. In the "ADR state" column, **done** means the ADR already says it. **edit** means the ADR still needs a change.

#### Already in the ADR

| Lab source | Change | ADR state |
|---|---|---|
| D1 (R L849-856) | Data disks stay host-attached. Variant N is rejected. | **done**, ADR L87-94 |
| F24 (R L674) | Stock LVM activation is off. The role is the only activator, with no fallback. A stalled disk holds the whole boot (accepted). The image holds lvm2. | **done**, ADR L117-137, L144-151, L167, L739-740 |
| F6 (R L444-460) | `MOUNT_DEFAULT_TIMEOUT=900000` on the node driver. | **done**, ADR L241-247 |
| F18 (R L829) | NotReady counts only from the fencer's watch start. A cold boot fences nothing. | **done**, ADR L401-406, L522-524 |
| F11 (R L664) | VG reads give up after 30 s. A VG that does not answer reads as missing. The fencer reads `retained` only. | **done**, ADR L335, L574-598 |
| F12 (R L666-670) | Our code passes `--devices <pv>`, which turns hints off. `hints = "none"` was not adopted. | **done**, ADR L576-578, L586 |
| F23 (R L672) | A fence waits for the LIO drain (kept by design). Retained ACLs are deleted first. `StorageFenceDraining` fires after 2 min. | **done**, ADR L501-504, L555-557, L599-609 |
| F14, F15, F21, F22 (R L721-778) | kubelet drop-in 90s/40s. Node DaemonSet patch: no `cleanup`, native sidecars, no registrar `kubelet-dir`. A preStop hold on `globalmount` or a session. | **done**, ADR L253-256, L530-540, L821-824 |
| Check 1 reading (R L817) | TrueNAS is ordered first, but its NFS comes up last. | **done**, ADR L762-763 |
| B5 minor: no timeout on `mkfs` and discards under `LIO_LOCK` (R L384) | A hung device can block the fencer and boot check. | **done** as named residuals, ADR L588-598 |

#### Still to edit

**Status 2026-11-19 (Ben: "Make the edits"):** every **edit** row below is now in ADR 0017; the ADR line numbers in
this table are from before those edits. F16 still needs its code fix. The F1 bound, the F2 alert, F9's `e2fsck`
timing, the `lvremove` gap, the refusing gauge and Check 10's unrun legs are listed under the ADR's Open questions.
The review of the edits also added a writer drain to the whole-disk restore runbook (the B9 drill drained first) and a
Partial status on Check 10. A second round (2026-11-21, Ben: "Add the gaps to the ADR") added the pre-production gaps
from a downsides review: the lab gate's real status, a "Not proven there" list, capacity and overcommit notes, the
manual-fence Proxmox CSI warning (proposed), and new Open questions.

| Lab source | Change | ADR state |
|---|---|---|
| F8 (R L528-530, L549, L566) | Every manual unfence needs `--confirm-stopped`, settled tag or not. | **edit**. ADR L550-552 asks for it only on an `unknown` tag while the fencer is down. |
| F8 docs (R L530) | Reword `StorageWorkerFenced`. A Ready worker on its fenced boot, or on a bootID already seen, may be a resumed hung boot. Reboot it and never unfence it by hand. | **edit**. ADR L498-499 still says "it booted before the fence was settled". |
| F7 (R L472-477, L550-556) | `restore-set` makes the live set match the tags: it adds tagged addresses and removes untagged ones, and fails closed on any tag error. `apply` fails on an untagged element. "Rendered from the tags, read under the LIO lock" covers the read only (R L475). | **edit**. ADR L479-482 says it only re-adds. ADR L489-490 checks only for missing tagged addresses. |
| Slow-reboot ruling (R L485) | A boot that has not posted its bootID settles the tag on the old bootID. The new boot then unfences itself when Ready, with no extra reboot. The report says "the plan and ADR wording needs fixing". | **edit**. Check 6 at ADR L805-806 still expects a settle on the new bootID plus one more reboot. ADR L525-527 ("a boot still NotReady 5 minutes on ... needs one more reboot") may need the same fix. |
| F5 (R L376-381) | The grow step runs `resize2fs` only where a session is logged in and `findmnt` shows ext4 mounted. A VolumeAttachment alone is not enough. | **edit**. ADR L327 says "on the worker holding the VolumeAttachment". |
| F9 (R L594-601) | A storage-VM rebuild cuts I/O for about 2 min 23 s, which is more than `replacement_timeout` (120 s). The rebuild must drain writers first. When a flagged fs gets an offline `e2fsck` is still to be decided. | **edit**. ADR L157 says only that a rebuild "pauses I/O". It says nothing about read-only filesystems or a drain. |
| F10 (R L611-639) | `storage/main.tf` declares virtio0, placed after the data disks. `data_disks` refuses `virtio0`. A contract row is needed for packer `disks` against terraform virtio0 (R L638). Any `data_disks` change re-sends every disk's options (R L639). | **edit**. ADR L82-83 and L893 do not mention virtio0. No such contract row in the `.github` row at ADR L896. Open question ADR L753 ("bpg `path_in_datastore` attach holds up") is answered by Check 3 (R L585, L619, L633). |
| `up=` (R L820-821) | Measured: all 3 targets listed within 11.4 s (two runs). The ruling is `up=30`. | **edit**. ADR L263-264 says "measured", with no value. Open question ADR L754 is still listed. |
| Latency (R L703-710) | fsync and SQLite latency is about equal to Proxmox CSI. | **edit**. ADR L728-729 still says "must be measured". |
| Quota (R L19) | Lab read: `apps/k3s-block` 309 GB quota, 110.5 GB available. 309 GB is about 288 GiB, so the read matches the documented quota. | **edit**. ADR L663 calls the 288 GiB quota a mismatch, and open question ADR L751 is still listed. The report does not re-read the mount's 219 GiB total (ADR L662), so the mismatch with the mount is not resolved. |
| B9 Step 1 (R L789) | A single-app restore must copy `rows.db-wal` along with `rows.db`. | **edit**. ADR L652 says only "Copy the files". |
| F17 (R L813) | A data-disk restore leaves LIO targets (on the root disk) for volumes created after the snapshot. They come back empty, and the reconcile neither flags nor removes them. | **edit**. The restore runbook (ADR L619-643) has no step for this. |
| F16 (R L811) | Under `hold_create`, `apply` exits 1 with no reason logged, and `--dry-run` exits 0. | ADR L336 already states the intended behaviour. **Code fix needed.** The report gives no fix. |
| F2 (R L303) | Nothing alerts on a failed boot check. `target_missing` is written only by reconcile, 971 has no timer, and node-exporter has no systemd collector. | **edit**. ADR L108-111 and L142-143 assume a failed unit is visible. |
| F1 (R L283-288) | NodeStage login retries for about 30.5 min while holding the volume lock. A target created inside that window would be logged in with no pod (R L288). | **edit**. ADR silent. |
| F3, F13 (R L332, L386, L676) | Runbooks are needed for `crashed-create` and orphan recovery, and for half-expiry recovery through `storage.yml`. A read-only fs recovers by scaling to 0, confirming the unstage, then scaling up. A same-node pod delete does not restage. | **edit**. The runbook list at ADR L895 has only restore, hang fencing and growth. Check 8 at ADR L816 says only "manual restage". |
| B5 minor: `lvremove` and tombstone (R L387) | They are separate commands. A failure between them leaves `lv-missing`, which blocks every reconcile until fixed by hand. | **open decision** (migration plan). ADR silent. |
| Step 9 note (R L513) | There is no metric for `hold`, `foreign-va` or `no-peer` refusals. A `storage_fencer_refusing` gauge is still to be decided. | **open decision**. ADR L493-496 lists no such metric. |
| Accepted edge (R L557) | Changing a fenced worker's `bridge_address` drops the old address. Unfence before renumbering. | **edit** (or migration plan). ADR silent. |
| nftables restart (R L469) | A restart leaves at most about 0.16 s with no ruleset, so every port is open. | Mostly **done**: ADR L140-141 says handlers only reload. An optional note could say this. |
| RWOP ruling (R L408) | "Volumes never move" with the fencer stopped holds only because of RWOP. | Plan wording only. ADR L787 and L248 already match. |

### Limits

- **No server fence.** Only the agent was ever fenced. The server also ran workloads. Fencing a server is outside the lab (ADR L758-760).
- **Simulated hangs.** The four hang methods were `qm suspend`, `kill -STOP` of QEMU, an in-guest `freeze`, and `net0 link_down=1` (R L412-417). `freeze` had no wake path and needed a QMP `sendkey` (R L422). No real kernel hang or hardware fault was tested.
- **"Both workers NotReady" was simulated.** The `no-peer` case was an out-of-service taint on 972, not two dead workers (R L497).
- **Oops rate.** The lab cannot measure how often pve's NFS client oopses (plan B11 Step 1). Variant N's gain against an oops was never tested (R L854).
- **ZFS-clone leg not run.** It needs Ben's go-ahead (R L790). The B9 copy used `cp --sparse=always` (R L783).
- **Off-site restore not run.** B9 Step 3 did not run, because the lab image is excluded from restic (R L790). Check 10's off-site half (ADR L819-820) is therefore unproven.
- **Lab timings, not production ones.**
  - The fencer used `not_ready_seconds` 60 (R L401), and quarantine was 900 s instead of 3 days (R L193).
  - Check 11 was not re-run at production's 300 s fence window (R L778).
  - ADR's "volumes move within about 6 minutes" (ADR L791-792) was measured only at 60 s. There, fences landed 106-112 s after the hang, and writers ran 2 min 48 s to 3 min 5 s after it (R L414-417).
- **Final-code boot not run.** The B10 Step 3 host reboot ran code from before the F18, F11/F12, F14 and F24 fixes. Each of those passed through guest cycles only. The whole boot sequence on the final code first runs at the production cutover (R L844-847).
- **F6:** a mount wait over 120 s (kubelet's Uncertain path) was not covered. It rests on reading the source (R L459-460). The MMP check interval was not recorded in the lab (R L444); the fix spec infers interval 10 (R L450).
- **F7 route 2** (`storage.yml` overlapping an auto-unfence) was not run (R L571).
- **F10:** a fresh clone with virtio0 declared was traced in source only (R L635).
- **F4:** the final `host.run` fix was proven by its mechanism, not by a second expiry (R L345).
- **F24:** the `module.async_probe=1` failure has no proven cause. No console capture was taken (R L674).
- **StorageFencerBlind:** the `absent()` legs were not exercised (R L511).
- **Node DaemonSet patch:** applied by hand in the lab. The Argo and kustomize wiring is unproven until the first production sync (R L735-737).
- **970 `up=60`:** a ruling, not a measurement (R L821; b10/notes.md L12).
- **F9:** offline `e2fsck` of a flagged fs was not rehearsed. It would write to retained data (R L600).
- **Performance:** variant N's performance was not measured (R L855). The lab had 3 inventory volumes (R L244-249) against 33 live attachments in production (ADR L26), so scale was not tested.
- **Worker journals** were not kept: they were volatile, current boot only (b10/notes.md L93).

### Numbers

#### Boot and `up=`

| What | Value | Source |
|---|---|---|
| 971 start until all 3 targets are listed from 973 | ≤ 11.1 s and ≤ 11.4 s (two runs, polled every 2-3 s) | R L820; b10/notes.md L3 |
| Ruling | `up=30`, about 2.5x the measurement | R L821; b10/notes.md L4 |
| 970 slot | `order=1,up=60`, not measured | R L821; b10/notes.md L12 |
| Host reboot | pve reachable after 7 min. Every guest up by 19:14:31. k3s VMs off about 10 min. Targets and fencer active 5 s after 971 booted. | R L824-826 |
| pve stop jobs on the dead NFS | hung about 1.5 min | R L825 |
| Late NFS, host path | `qm start` refused in 10 s. 3 targets back 45 s after starting 970 and then 971. | R L840-841 |
| Late NFS, variant N | mount timed out at 91 s. One manual start restored everything in 2 s. Targets up 6 s after boot when the NFS was reachable. | R L835-837 |

#### B8 Check 9: crash and latency

60 s runs on lab-agent (R L703-710):

| Path | fio IOPS | fsync p50 / p99 | SQLite commits/s | commit p50 / p99 |
|---|---|---|---|---|
| Retained (iSCSI) | 158 | 6.0 / 12.0 ms | 83 | 10.2 / 24.0 ms |
| Proxmox CSI | 158 | 6.0 / 12.0 ms | 78 | 12.0 / 20.0 ms |

- **Crash:** 20 of 20 SIGKILLs were OK. In 19 of them, max was the last ack + 1 (R L686-691).
- **971 hard stop:** LIO and the fencer were back 18 s after the stop. Writers stalled 15.3 s (R L694-695).
- **973 hard stop:** the retained writer had a 117.3 s gap. The writer on the other worker saw 0.3 s (R L699).

#### Lab-storage (971) resources

These are not in the report. They come from b10/notes.md L94-95 (pve RRD weekly max since 11-16 19:30Z, hourly buckets, plus a live read at 12:31Z).

| What | Value |
|---|---|
| CPU, peak | 27.8 % of 2 vCPU (11-16 20:30Z) |
| Guest memory, peak | 703 MiB of 1536 MiB (11-16 23:00Z) |
| Memory in use at 12:31Z (16 h uptime) | 305 MiB |
| `storage-fencer` | cgroup `memory.peak` 24 MiB, RSS 30 MiB |
| Pressure (PSI) | cpu and mem 0, io some 0.36 |

#### NFS stall and export withdrawal (B8 Check 8)

| Leg | Retained | Regen |
|---|---|---|
| Variant N stall, 3 min | max ack gap 0.3 s | blocked 182 s (182.3 s), no errors. Session reset at +76 s and recovered. |
| Variant N withdrawal | unaffected | I/O errors at once, then ext4 read-only; recovered at the last ack (2454) |
| Host stall, 3 min | max gap 0.4 s | blocked 184 s (183.8 s), no errors. Connection error at +77 s, session recovered. |
| Host withdrawal | max gap 0.4 s | I/O errors at once, then read-only; recovered at the last ack (3828) |

Sources: R L645-650; b8/notes.md L11, L15, L28.

- **Probes:** `vgs retained` and `prove` stayed under 100 ms (R L654), measured at 30-79 ms (b8/notes.md L10, L34).
- **Before F11:** the reconcile dry run passed its 60 s cap (R L664); it hit the cap twice, rc 124 (b8/notes.md L10).
- **F11 re-test:** dry runs gave rc 1 in about 30 s. `status` took 0.12 s. The fencer had a 31 s gap while an apply held the lock (R L664).
- **F12 re-test:** the first apply after restore was clean in 0.6 s (R L670).
- **F23:** `LIO_LOCK` was held about 125 s (R L672).
- **F24, stock boot:** in a 300 s regen stall, root mounted at 288.4 s, about 2 s after the stall ended. Under the fix, with a 180 s stall, root mounted 1.3 s after the stall ended (R L674).

#### Other timings

- **Fences (60 s lab window):**
  - fences landed 106-112 s after the hang. Writers ran on 972 after 2 min 48 s to 3 min 5 s (R L414-417);
  - with a live session, `nft add` to a passing proof took 22 ms (R L421), and the ACL delete took about 28 ms (R L433);
  - nftables set gaps were at most about 0.13-0.19 s (R L467-468).
- **MMP and NodeStage (F6):**
  - MMP waited 42 s (R L444), and 44-45 s in other moves (R L586, L596, L676);
  - with the fix, NodeStage took 48.1 s and 49.2 s, and 4.2 s after a clean unmount (R L455-458);
  - a clean unmount followed by a mount elsewhere took 23 s (R L461).
- **Storage-VM rebuild (F9):** the cut lasted about 2 min 23 s against 120 s recovery (R L596). The recreate took 55 s (R L585).
- **Shutdown (Check 11):**
  - baseline drained stop on the old code: 102 s (R L741, L766);
  - after the fix: undrained stop 28 s; nothing staged, 4 s (R L774-775);
  - first-run failure: the writer moved after 162 s (R L717).
- **Reclaim:** 411,409 KiB down to 1,545 KiB (R L370).
- **F1:** NodeStage held the volume lock for 30.5 min (R L283).

## B11 Step 2: cleanup (2026-11-19 14:05Z to 14:06Z, Ben approved)

Ran `b11clean.sh pve`, then `b11clean.sh runner` (lab scripts, kept off-repo with the evidence). Each step checked its
target first and stopped at the first surprise; nothing stopped.

- **VMs:** 973, 972, 971 destroyed, then 970, 974, 975, 976. Each was checked first: ID 970-976, `lab-` name, and only
  its own `local-zfs` disks or 9970 volumes. `qm list` after: 100, 200-202, 300 running, 900 stopped; no 970-979.
  Destroying 970 also removed variant N's `/srv/labn` export and `regen-n.raw`.
- **9970 volumes:** `qm destroy --purge` does not free volumes owned by VMID 9970, so they were freed by name, each
  only after a grep showed no guest config referenced it: `k3s-block:9970/vm-9970-disk-0.raw` (9 GiB),
  `k3s-block:9970/vm-9970-disk-2.raw` (1 GiB), `lab-nfs:9970/vm-9970-disk-1.raw` (4 GiB). k3s-block holds no 9970
  volume and `images/9970` is gone.
- **lab-nfs:** removed and unmounted while 970 still served it (a dead NFS mount hung pve stop jobs in B10).
- **vmbr9:** no guest used it and it had no ports; `ifdown`, then the `interfaces.d` file was removed. This does what
  the bridge playbook's `absent` path does, without an ansible run while the lab held the lock.
- **Proxmox access:** user `lab-storage@pve` (and its token), pool `lab-storage` and role `LabISO` deleted; no ACL
  names them.
- **Runner:** the lab lock, then the production lock (`lab/storage-2026-11-16`) released, each checked by the absence
  of `operation.json`; lab containers and the `lab-shell:adr0017` image removed; the ssh and creds tmpfs unmounted;
  `<lab>` removed after a check that nothing was mounted under it. The evidence was copied out first
  (`lab-evidence.tgz`, 5330 files, without creds, keys, locks or state).
- **Restic (item 2), 2026-11-19 16:40Z:** with the backup lock held, `restic find` for `images/9970` and everything
  under it, across all 27 snapshots (11 `daily`, 2026-11-09 to 11-19), found nothing. The control, the same search for
  `images/9999` in the latest `daily`, listed its images, so the pattern form works. The B1 exclude kept the lab out.
- **Exclude revert (item 6):** ansible PR 350 (`chore/remove-lab-backup-exclude`), open. Six hash-named
  ISOs on `local` were left, since lab and production ISOs cannot be told apart by name.
