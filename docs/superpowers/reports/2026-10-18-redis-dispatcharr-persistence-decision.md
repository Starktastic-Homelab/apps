# Redis durability: Dispatcharr access decision

Status: the user approved the native ACL amendment on18October2026. It extends
Task4 of the approved Redis/Immich preparation. Tasks1–3 remain locally qualified. No production
configuration, credentials, data, workloads or maintenance ownership changed.

## Verified disabling path

The exact deployed Dispatcharr0.31.0 image calls `CONFIG SET save` and
`CONFIG SET appendonly` from its Redis client initialization. It disables RDB
saves and AOF for the entire Redis server, including other logical databases.
The same function changes the global idle timeout to300 seconds. No opt-out
condition surrounds those persistence calls in this deployed function.

Read-only hashes of `/app/core/utils.py` in both running web and Celery Pods
match the exact-image fixture. Fresh production values are `appendonly=no`,
`save=""`, `timeout=300`. An individual historical request was not traced, but
the deployed disabling path is reproduced independently: ordinary Dispatcharr
client initialization changes synthetic Redis from AOF enabled to disabled.
A CSI storage move alone would leave that path intact.

The [upstream function](https://github.com/Dispatcharr/Dispatcharr/blob/v0.31.0/core/utils.py)
shows the same persistence behavior. The pinned deployed image, rather than the
movable tag or source lines, is the qualification authority.

## Approved bounded amendment

Use native [Redis ACLs](https://redis.io/docs/latest/operate/oss_and_stack/management/security/acl/)
to protect the shared server configuration:

1. Keep the current default application account and every existing application
   password, endpoint, key/channel permission and database assignment.
2. Deny `CONFIG SET` and `ACL` commands to that application account. Configuration
   reads, queue operations and normal data access remain available. Denying ACL
   changes prevents this account from simply undoing its restriction.
3. Add a distinct `homelab-maintenance` Redis account for reviewed administration.
   Give it a new random credential, protected through the existing SealedSecret
   and sealing-key recovery workflow. Proposed Secrets are
   `databases/redis-maintenance-auth` and `databases/redis-server-acl`. The latter
   holds native ACL declarations with password hashes; both are sealed in Git.
4. Make the native ACL file part of Redis startup, so a rebuild enforces the same
   policy. Preserve the freshly verified idle timeout explicitly in the final
   configuration; retain the approved empty scheduled-RDB policy and everysec AOF.
5. Extend the finite packet to use maintenance authentication for configuration
   changes and to prove application restrictions, exporter compatibility and
   persistence after restart. Keep the current-memory recovery gate before source
   shutdown or AOF transition. Include credential creation/handling in the later
   concrete production proposal.

This adds one permanent maintenance credential and changes application command
permissions. Dispatcharr will log a rejected configuration attempt while its
client continues normally. It needs no application patch or new Redis instance.
The unmodified CSI driver, source preservation and unattended rebuild design
remain the same. No ACL or credential has been installed in production.

An alternative is a separate Redis for Dispatcharr, with a separate retained
queue transfer, claim, lifecycle and monitoring contract. That adds another
stateful service and a larger migration scope. The native ACL amendment is the
recommended smaller change.

## Synthetic evidence

[Sanitized evidence](evidence/2026-10-18-dispatcharr-redis-persistence.json)
records the exact images/module hash and the following native results:

- Unrestricted stock Dispatcharr decoded and binary clients connect and perform
  queue-like reads/writes, then the AOF-enabled assertion fails because AOF is off.
- With the candidate ACL, both exact-image clients still connect/read/write and
  AOF stays enabled. Unauthorized configuration changes and ACL self-escalation
  refuse; separate maintenance configuration access works.
- Actual pinned Celery/Kombu and Immich BullMQ pending/in-flight synthetic job
  recovery still passes using the unchanged application password.
- The exact Redis exporter reports Redis up1, AOF enabled1, write status1 and
  scrape error0 under the restriction.
- Native configuration-file ACLs remain effective after Redis recreation and
  another stock Dispatcharr initialization.
- All operation-labeled containers/volumes are removed on success and failure.
  No application entrypoint or production data/credentials entered the fixtures.

The fixture extracts the real RedisClient class without editing it, initializes
only synthetic Django settings and TRACE logging, and invokes its real methods.
This is client/native-engine evidence, not a complete Dispatcharr service-start
or production-task acceptance claim. Full chart/Secret rendering, the finite
packet, whole-package review and hosted CI remain pending.

## Continuation gate

The user approved this expanded access/credential design. The amendment
authorizes preparation and qualification only. Production
outages, real-data/key or credential handling, allocation, activation and merge
authority still need the finished reviewed execution proposal. Redis cannot be
accepted while a permitted client can keep disabling AOF.
