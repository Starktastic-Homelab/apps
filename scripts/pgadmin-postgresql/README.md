# pgAdmin PostgreSQL and retained CSI

`prepare.py sources` renders inactive chart adapters and manifests; it never applies.
The overlay pins the existing pgAdmin9.18 image and preserves administrator Secret,
authentication and saved-server discovery. Its dedicated completion service account
has read access only to the two existing enrollment acceptance objects. The default
service account remains unprivileged; its token is not mounted in pgAdmin.

The retained file guard requires the identity marker and the three private-file
directories, rejects legacy SQLite engine/backup files and competing database
configuration, and validates the canonical Secret-mounted URI against its password.
Projected Secret links must resolve inside their own volume. The URI file contains
a quoted Python string because the stock entrypoint writes a Python configuration
assignment. A native stock-image rehearsal verifies this convention and the pool
limit of two connections plus one overflow connection.

The read-only SQL guard checks the physical PostgreSQL server, restricted role,
complete stock schema52 catalog (columns, defaults, nullability, constraints and
indexes), original schema markers and application-key fingerprints, and an active
internal administrator. Empty or wrong retained data cannot reach stock setup.
Keep image/schema signatures and guard qualification together when upgrading.

`data.py` copies all22tables into a schema initialized by the exact stock image,
leaving backend schema markers unchanged. It compares every field and duplicate,
preserves JSON/SQL NULL distinctions and allocator floors, and refuses replay into
a changed bootstrap generation. Rows are transactional; PostgreSQL sequence updates
are not transactional, so exclusive operation receipts and no-replay fencing remain
required. No pgloader, application patch or additional controller is introduced.

`prepare.py enrollment --output <new-private-directory>` generates one append-only
strictly sealed credential set. Existing aggregate ciphertext is retained byte for
byte. It never applies and refuses an existing output. Keep partial ciphertext on
uncertain failure; inspect it rather than regenerating a credential generation.

Run `python3 scripts/test-pgadmin-data.py` and
`python3 scripts/test-pgadmin-retained-startup.py`. CI supplies an actual layered
chart render through `PGADMIN_RETAINED_RENDER`. Local native SQL negative checks
require an explicitly labelled port-free `PGADMIN_SQL_CONTAINER`; never select a
production container. Real-data qualification and production acceptance are separate
in the [assessment](../../docs/superpowers/reports/2026-10-16-pgadmin-assessment.md)
and [plan](../../docs/superpowers/plans/2026-10-16-pgadmin-postgresql-csi.md).
