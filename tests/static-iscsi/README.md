# Static iSCSI recovery rehearsal

This is an isolated lab continuation, not production deployment configuration.
Read the [design](../../docs/superpowers/specs/2026-09-21-static-iscsi-recovery-design.md)
and [plan](../../docs/superpowers/plans/2026-09-21-static-iscsi-recovery.md).
Run-specific secrets, keys, ownership and acknowledgements live in `.runtime/`
(mode0700, ignored). No lab command may use the default kubeconfig.

The stock-image formatting probe operates only on disposable16MiB regular files.
Run it in a fresh temporary directory using the exact Docker command in the plan;
copy `format-probe.js` to that directory as `probe.js` first. The positive control
must change bytes/create ext4; the `-n` cases must preserve the whole-file hash and
leave no filesystem signature. This helper test does not establish NodeStage
safety; actual block-device mounting remains a required lab acceptance test.

Fixture scripts adapted from the prior rehearsal pin TrueNAS25.10.7. Reuse the
corrected `../iscsi-platform/guard.py` and its tests. Never reuse historical private
manifests or temporary scripts containing embedded copies of older guard code.
The lab is incomplete until the execution ledger records every acceptance result.

The [completed-run report](../../docs/superpowers/reports/2026-09-21-static-iscsi-recovery.md)
distinguishes live CSI tests from external verification and production gaps.
`gitops/` archives the nonsecret manifests exercised by actual Argo. These are
run-specific fixtures and evidence, not a reusable production bootstrap: native
identities and VM ownership refer to this disposable run, whose private inputs
are removed at cleanup. Never run these host scripts against another VM generation
without independently establishing its ownership.
