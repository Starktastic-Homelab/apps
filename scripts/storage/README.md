# NAS transport

`nas_rpc.py` is the shared credential-private TrueNAS transport. It verifies the
CA and independent leaf fingerprint, bounds RPC calls and suppresses secrets from
errors. `requirements.txt` pins its existing websocket dependency.

The retired service-specific iSCSI allocator, writer release, enrollment, NFS
migration, historical status/preflight adapter and their workflows are removed.
Previous source and dated qualification reports remain in Git history. Current
Jellyfin storage guidance is in [the runbook](../../docs/runbooks/jellyfin-storage.md).

Run `python3 -m unittest discover -s scripts/storage/tests -v` after installing
the requirements. Stock CSI rendering is checked by
`scripts/check-proxmox-csi-render.py` with the actual chart/value layers.
