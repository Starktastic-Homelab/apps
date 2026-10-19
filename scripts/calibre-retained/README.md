# Calibre-Web Automated retained SQLite

Prepare one static 1GiB Retain/RWOP volume for `/config` and
`/calibre-library`, mounted as whole directories from `config` and `library`.
The stock split-library settings point book files to `/calibre-books`, backed
by the unchanged NFS `library/books` directory. Ingest remains on NFS.

The current five databases are `app.db`, `gdrive.db`, `cwa.db`, `metadata.db`
and `.calnotes/notes.db`. Keep the complete notes directory, including resources,
and the original encryption key. The read-only startup guard rejects wrong
identity, missing/redirected files, malformed SQLite headers and invalid native
key shape. Native SQLite recovery stays with the stock image.

`test_native.py` runs the exact configured image without networking or production
data. It exercises stock web login/edit/download, covers, notes, AZW3 conversion
and ingestion, closes the app, compares every byte/POSIX attribute and all five
native SQLite integrity/row proofs, then boots and checks the recovered app.
Calibre's bundled APSW extension supplies its custom notes tokenizer. Qualification
code is explicitly compiled with assertions enabled because `calibre-debug`
uses optimized Python. Cleanup checks exact container IDs and fixture ownership.

The active preparation adds only an unused guard, static target bindings and
retention protection on the existing NFS claim. Prepared production values,
source PVC and source hold stay inactive until separately reviewed cold-copy
execution and green activation CI. No app image, account, key, integration,
endpoint, book or pending ingest item is replaced.

Before activation, use fresh native maintenance ownership and verify the exact
writer scope. Stop CWA and hold generic writers during its checkpoint. Package
cold config and the complete metadata/notes trees inside the homelab; real
credentials must never enter workstation/CI fixtures. Verify native state before
startup. Preserve retired metadata outside the active book directory and keep
the old config claim. Restore normal services only after native, restart and
both-worker checks and exact Git/live reconciliation. Never automatically fall
back to old NFS databases after new writes.

The [stock split fields](https://github.com/crocodilestick/Calibre-Web-Automated/blob/v4.0.6/cps/config_sql.py)
and [stock ingest path handling](https://github.com/crocodilestick/Calibre-Web-Automated/blob/v4.0.6/scripts/ingest_processor.py)
are qualified by the pinned-image test. No upstream app or CSI driver patch is used.
