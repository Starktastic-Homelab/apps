# Media retained-state preparation

These manifests are inactive until copied into the owning application/base-configs
paths during the reviewed native cutover. They preserve existing image pins,
services/probes, credentials and shared media/ingest interfaces. Cleanuparr additionally requires separately qualified native PostgreSQL conversion
and the existing enrollment/completion gate before its CSI activation.

Each private image is4GiB, ext4, RWOP/Retain, cache none, owned independently of
workers under VMID9999. The read-only Python init checks the exact app marker and
required native paths/SQLite headers without opening SQLite, changing journals or
repairing files. Full cold file/POSIX/native recovery is an execution gate.

Cineplete uses config/ and data/ subpaths. Audiobookshelf uses config/ and metadata/
subpaths, preserving its formerly container-only metadata. RU overrides contain
only instance identity/claim changes; activation must add valuesOverride:true to
the variant app.yaml. Init guards receive neither shared media nor book ingest.

With Helm, kubeconform and PyYAML available:

```sh
MEDIA_RETAINED_RENDERS=/tmp/media-retained bash scripts/media-retained/check.sh
```

See the [design](../../docs/superpowers/specs/2026-10-17-media-retained-csi-design.md)
and [plan](../../docs/superpowers/plans/2026-10-17-media-retained-csi.md). Never start
an empty source/target or resume a preserved NFS writer after target authority.
