# NAS transport

`nas_rpc.py` is the shared credential-private TrueNAS transport. It verifies the
CA and independent leaf fingerprint, bounds RPC calls and suppresses secrets from
errors. `requirements.txt` pins its existing websocket dependency.

The retired service-specific iSCSI allocator, writer release, enrollment, NFS
migration, historical status/preflight adapter and their workflows are removed.
Previous source and dated qualification reports remain in Git history. Current
Jellyfin storage guidance is in [the runbook](../../docs/runbooks/jellyfin-storage.md).

Run `python3 -m unittest discover -s scripts/storage/tests -v` after installing
the requirements.

`migrate_volume.py` (with `copy_volume.sh`) is the migration-only copy tool for retained-volume cutovers
(ADR 0017): `precheck` refuses a copy while anything can write the source, `render` writes the temporary PV/PVC
pairs and the copy Job (plus, for a reverse copy, the read-only source gate) to a directory outside the repo, and
`verify-teardown` confirms nothing labelled for the migration is left. It runs only on the tool host that Task 4.0
Step 7 settles (D23), because it needs `kubectl`, `gh` and the maintenance lock root together. Nothing else imports,
renders or runs it, and Task 5.9 deletes it with its tests and this paragraph.
