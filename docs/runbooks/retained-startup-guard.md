# Retained-volume startup guard

Every retained volume's workload runs one generic marker guard before its app starts:
[`guard.py`](../../infrastructure/base-configs/files/retained-startup/guard.py), served as ConfigMap
`retained-startup-guard` in each namespace that needs it by
[`retained-startup-guard.yaml`](../../infrastructure/base-configs/templates/retained-startup-guard.yaml).

The init container runs `python3 -I -B /retained-startup/guard.py <app> <root> [<kind> [<marker-file>]]` in the
pinned python image, as the app's own user, with the claim mounted read-only at `<root>`. It accepts only when
`<root>/<marker-file>` (default `.homelab-<app>-<kind>`, kind `data` by default) is a regular file of 1 to 128 bytes
holding exactly `homelab/<app>/<kind>/v1` and a newline. Otherwise it prints one refusal line and exits 1, and the
app does not start.

The guard checks no native files, formats, versions, PostgreSQL system identifiers or database contents, and it never
creates, repairs or rewrites data. A refusal is a stop: investigate the retained image and filesystem identity. Never
create, rename or rewrite a marker to get past it. The only explicit marker file is seerr-ru's, which carries its base
app's name.

The marker rule is the same for every volume: the marker is `<root>/.homelab-<app>-<kind>` and holds
`homelab/<app>/<kind>/v1` and a newline. `<app>` and `<kind>` are lowercase names (letters, digits and inner
hyphens, at most 63 characters, and the whole marker must fit in 128 bytes); `<kind>` defaults to `data`. Each guarded workload's arguments (`<app>`, `<root>`,
and any `<kind>` or marker file) are in its app's `values.yaml`, on the init container whose command runs
`/retained-startup/guard.py`; the uid is that container's `runAsUser`. A new app needs only that init container and
its marker, never a change to the guard or its tests; an app in a new namespace also adds that namespace to the
template's list.

Jellyfin (`/config/.homelab-jellyfin-data`) and filebrowser (`/home/filebrowser/data/.homelab-filebrowser-data`) carry
markers but are not wired to the guard yet.
