# F24: stock LVM off the storage VM's data disks (short design)

Date: 2026-11-19. Status: approved by Ben 2026-11-19. Lab finding F24 (spec item 9 of
`2026-11-18-storage-vm-lvm-isolation-design.md`). Notes and research: `storage-lab/b8/f24-notes.md`, workflow
`wf_22948b8d-b5b` (Linux v6.12, systemd 257, initramfs-tools, lvm2 2.03.31 sources).

## Intent

F24 was "the storage VM waits ~180 s in the initramfs when a data disk is stalled". Recon found a larger fault: Debian's
stock LVM activates both VGs at every boot, unscoped and with no time limit, in the initramfs (the lvm2 hook always
installs `69-lvm.rules`, whose no-systemd path runs `vgchange -aay`), before the role's scoped activation runs. Proven on
971: `/run/lvm/vgs_online/{retained,regen}` predate `/run/systemd/system`. So no boot result so far tested the role's
own activation. Ben, 2026-11-19: **only the role's own commands may ever activate retained and regen.** Ben picked
approach 1 plus one diagnostic boot for the hold.

## Goals

- No stock LVM path activates, monitors or deactivates retained or regen: not the initramfs, not `lvm-activate-*`, not
  `lvm2-monitor`, not `blk-availability`.
- Retained activates only through the role drop-in's scoped `vgchange --devices <retained PV> -ay retained`; regen only
  through `storage-reconcile activate --vg regen`. No unscoped fallback.
- A storage VM booted from an image without these settings is refused by the role, not silently accepted.
- The boot hold's mechanism is confirmed or refuted by one diagnostic lab boot before any fix for it is chosen.

## Non-goals and anti-goals

- No fix for the boot hold itself here. The diagnostic boot (below) showed the hold lasts as long as the stall (no bound
  seen up to ~290 s) and has two releases: udev moved on at ~191 s with the stall still on, but the root mount waited
  until ~2 s after the stall ended. LVM settings cannot reach either wait. Whether to accept and document it, or test a
  kernel option first, is a separate decision for Ben; `module.async_probe=1` is untested and this boot suggests it
  would not be enough alone. **Outcome 2026-11-19:** one `module.async_probe=1` stalled boot was worse (no recovery after the stall, reset needed); Ben accepted the hold and ADR
  0017 documents it.
- No per-VG `--setautoactivation n` (a metadata write on retained, and LVM would still read the disks; Ben picked the
  image setting).
- Anti-goal: anything that leaves retained activatable by an unscoped command, or that lets a wrong PV path end in an
  active retained VG.

## Approaches

1. **Image setting (Ben's pick).** Packer sets `global/event_activation = 0` in the storage image's `lvm.conf`, masks
   `lvm2-monitor.service` and `blk-availability.service`, and rebuilds the initramfs (the lvm2 hook copies `lvm.conf`).
   `pvscan --cache` then returns before reading a PV, so LVM no longer reads the data disks during udev. Explicit
   `vgchange -ay` is unaffected. The role drops its unscoped fallback.
2. Per-VG `--setautoactivation n`: travels with the disk, but writes retained metadata, still reads the disks at every
   boot, and a restored or new disk without the flag activates again. Not taken.

## Design

1. **Packer, `scripts/storage.sh`**, after `apt install ... lvm2`:
   - set `event_activation = 0` in the `global` section of `/etc/lvm/lvm.conf`, and fail the build unless
     `lvmconfig global/event_activation` prints `event_activation=0`;
   - `systemctl mask lvm2-monitor.service blk-availability.service` (every LV is linear: nothing needs monitoring, and
     systemd-shutdown detaches dm devices at the end of shutdown);
   - `update-initramfs -u -k all`, and fail the build unless every `/boot/initrd.img-*` carries `event_activation = 0`
     in its `etc/lvm/lvm.conf` (read with `unmkinitramfs`; the lvm2 hook copies `/etc/lvm` whole; `base.sh` rebuilt the
     initramfs before lvm2 was installed, and without `-k all` only the newest kernel's is rebuilt);
   - `apt-mark hold lvm2` next to the rtslib holds: its postinst runs an unscoped `vgcfgbackup`, and a conffile
     replacement would turn event activation back on, so an lvm2 upgrade is a deliberate, drained operation;
   - the image's `10-lvm.conf` drop-in loses both `ExecStartPre=` lines (unscoped `vgchange -ay`, untimed) and keeps
     only `Wants=`/`After=network-online.target`. Before the first deploy the root disk's saved LIO config is empty, so
     nothing needs active VGs; the reconcile activates scoped on demand (`lvm.activate`, `--devices <pv>`). Design
     check finding: keeping the lines would break the role-only rule on every not-yet-deployed boot.
2. **Ansible role.**
   - `rtslib-fb-targetctl` drop-in: `ExecStartPre=/sbin/vgchange --devices {{ storage_vm_pv_devices.retained }} -ay
     retained` (no `/bin/sh -c`, no `||` fallback). A wrong path leaves retained inactive and the unit fails at that
     line, so **no target is restored, regen included** (fail closed, my call: retained first keeps today's order; a
     regen-first order would cost up to 30 s per stalled boot). The fence set is still restored by `nftables.service`'s
     own `restore-set` (verified). The reconcile alerts show the missing targets.
   - `assert.yml` (`check_mode: false`, `changed_when: false`; `dry-run.yml` imports it): refuse to run unless
     `lvmconfig global/event_activation` is 0, `lvm2-monitor` and `blk-availability` are masked, lvm2 is held, and
     `/run/lvm/vgs_online` and `/run/lvm/pvs_online` are empty or absent. Only `pvscan`'s event path writes those files
     (lvm2 2.03.31 `tools/pvscan.c`), so a file there proves stock activation ran on this boot, for example from an
     initramfs that was not rebuilt. An old image is refused with a message naming the packer change.
   - the role's package-hold loop adds lvm2.
3. **Docs.** ADR 0017 "Restoring the configuration at boot" (the "Debian 13 activates VGs through transient udev units"
   paragraph and the fallback sentence) restated: stock activation is off in the image, the role is the only activator,
   no fallback. Lab report: correct F24 (the line "udev settle on vdc; no LVM in the initramfs" is wrong on both counts),
   record that F11 Steps 3-4 and the B10 boot rows tested stock activation and must be re-run, and mark Step 4's
   fallback result void. The 2026-11-18 isolation spec's fallback line gets a pointer to this design.

## Tests (RED first)

- packer `scripts/tests/test_image_layout.py`: `storage.sh` sets `event_activation = 0`, checks it with `lvmconfig`,
  masks both units, holds lvm2, runs `update-initramfs -u -k all` after the lvm2 install and the setting, and checks
  every initrd; `10-lvm.conf` has no `ExecStartPre`.
- ansible `scripts/tests/test_storage_vm_role.py`: the rendered drop-in has exactly the scoped `vgchange` line and no
  `||`; `assert.yml` holds the four checks, not in check mode; the hold loop names lvm2.

## Lab check (each step with Ben's OK; not before 06:05)

1. **Diagnostic boot: done 2026-11-19 06:05** (stall 300 s, reset 971, dmesg of the new boot). dm loaded at 191.7 s,
   `vdc: unable to read partition table` (RDB block 8) at 288.2 s, vda1 mounted 288.4 s; the stall ended at ~286 s.
   Prediction "partition-read failure near 190 s" was wrong; "root mount ~3 s after the stall ends" was right. Both VGs'
   `vgs_online` files again predate `/run/systemd/system` (retained ~192 s, regen ~289 s). The initramfs has no lvm2 boot
   scripts (only `56-lvm.rules`, `69-lvm.rules`, `lvm`, `/etc/lvm`), so `event_activation = 0` covers every initramfs
   path. Writers contiguous after.
2. Apply the image change on 971 by hand (the same `storage.sh` lines; the template rebuild is proven by the packer
   build), deploy the role, reboot clean: no `vgs_online` files before userspace, VGs activated by the drop-in's scoped
   line only (journal), `lvm2-monitor`/`blk-availability` masked.
3. Re-run the boot rows that tested stock activation: F11 Step 3 (regen stalled at boot), Step 4 (wrong retained path:
   now expected to fail closed, retained inactive, no targets), B10 boot rows. Also a first boot with no role deploy
   (VGs stay inactive) and a role deploy onto it (reconcile activates scoped).

## Design check (2026-11-19, workflow wf_fb92914e-f1b, lvm2 v2_03_31 / Debian 2.03.31-2 / systemd v257 sources)

Verified: with `event_activation=0`, `pvscan --cache --checkcomplete` returns before opening any device, so neither
69-lvm path fires; the hook copies `/etc/lvm` whole into the initramfs; lvm2 2.03.31 has no activation generator or
`lvm2-pvscan@`; `blk-availability` does nothing at start and its stop is an unscoped `blkdeactivate`, while
systemd-shutdown's final dm detach removes the LVs anyway; explicit `vgchange -ay` ignores the setting. Folded in: the
image drop-in's unscoped lines, the runtime `/run/lvm` check, `-k all`, the lvm2 hold, and the fail-closed scope.

## Left to the builder

How the `lvm.conf` edit is done (it must survive the stock file's layout), the assert wording, and test names.
