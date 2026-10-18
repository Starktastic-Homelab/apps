# Dispatcharr DVR queue preservation decision

Status: decision needed during Redis/Immich preparation. Production is unchanged.
The native Redis ACL amendment is approved; the additional application change
below is proposed, not approved or deployed.

## Finding and effect

The exact deployed Dispatcharr image starts a separate Celery worker for the
`dvr` queue. Its web entrypoint runs `scripts/wait_for_redis.py` on every modular
startup. That script preserves keys beginning with `celery`, `_kombu` or
`unacked`, then deletes other keys in its selected Redis database. This includes
pending `dvr` messages and their priority queues.

The deployed script's SHA256 matches [v0.31.0](https://github.com/Dispatcharr/Dispatcharr/blob/v0.31.0/scripts/wait_for_redis.py):
`76553144e5c2f1b47ccfc97ffd0e850ce3761c63d00e0d4995e3446b0f6e384c`.
The checked [v0.32.0 script](https://github.com/Dispatcharr/Dispatcharr/blob/v0.32.0/scripts/wait_for_redis.py)
and current main retain the same incomplete preservation list. An image upgrade
alone to that checked release does not fix it.

In an isolated exact-image fixture, native Kombu published one ordinary Celery
message and two DVR messages at priorities 0 and 3. The unchanged startup cleanup
preserved the ordinary message and deleted both DVR messages. Adding `dvr` to its
preserved prefixes retained all three. The native DVR consumer then read and
acknowledged both messages; unrelated synthetic transient state was still cleared.
Only the actual cleanup function ran, not the full Dispatcharr entrypoint. No
production data, credentials, service connection or path entered the fixture.
All owned containers and volumes were removed. [Sanitized evidence](evidence/2026-10-18-dispatcharr-dvr-queue.json).

A read-only production snapshot found zero pending list entries in both `celery`
and `dvr`. This does not establish that there are no active/reserved jobs, and
neither the snapshot nor the fixture establishes historical production loss.

The approved ACLs block CONFIG SET and ACL changes while retaining normal data
access. They therefore do not prevent this startup deletion. Accepting a complete
storage checkpoint cannot establish durable DVR queue recovery if normal client
startup subsequently removes those messages.

## Recommended preparation amendment

Qualify a minimal startup-script override for the web container, retaining the
pinned image and all other script behavior. Its only functional source change is:

```diff
-_CELERY_KEY_PREFIXES = ('celery', '_kombu', 'unacked')
+_CELERY_KEY_PREFIXES = ('celery', '_kombu', 'unacked', 'dvr')
```

Preparation would add the exact script mount and a compatibility check tied to
its original source hash, test the actual rendered container and both native
priority queues, and include the resulting change in the final whole-package
review and execution proposal. No fork of Redis or CSI is needed. Dispatcharr
would have a local startup-script override, so future image upgrades must check
that override against their upstream source; this is the maintenance trade-off.

This decision authorizes preparation only. Credential generation, production
permissions, restarts, data transfers, storage allocation, activation and merges
still require the finished execution proposal.

The alternatives are to accept Dispatcharr's existing DVR queue reset behavior
explicitly, weakening the selected queue-preservation contract, or defer the Redis
operation until a stock fix is available. Redis/Immich Task 4 remains incomplete
pending this decision; the approved Redis ACL work remains intact.
