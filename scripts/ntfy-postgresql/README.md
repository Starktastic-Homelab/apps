# ntfy PostgreSQL preparation

`prepare.py sources` generates inactive retained runtime fragments. It does not
apply them. `prepare.py enrollment --output <new-private-directory>` appends the
ntfy enrollment once and seals its application password/URL. Preserve that output
on any uncertain result; do not generate another password on retry.

The guard checks the retained marker, attachments directory, canonical secret URL,
and absence of SQLite fallback. `main.sql` checks the existing physical server,
role/database, all stock table columns/owners, versions and essential identities.
The shared completion gate accepts only the current successful enrollment inputs.

`initial.sql` is the pinned upstream initial schema, with empty-target validation
and removal of only its verified blank anonymous seed. Run it once before the
unchanged upstream importer, then let stock ntfy upgrade schemas. `data.py` compares
all typed application fields independently. It rejects omitted populated stores,
invalid text, duplicated external message IDs and any changed field.

This directory is preparation only. Refer to the [design](../../docs/superpowers/specs/2026-10-15-ntfy-postgresql-csi-design.md)
and [qualification](../../docs/superpowers/reports/2026-10-15-ntfy-assessment.md).
