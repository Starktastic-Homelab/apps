# Native PostgreSQL enrollment: local engine qualification

Scope: inactive source and isolated synthetic Docker tests. No production database,
password, application, disk or manifest was changed. This report is not an Argo,
Sealed Secrets decryption, k3s rebuild or production activation qualification.

## Results

The local enrollment suite passed 13 tests: 8 native SQL engine cases, 4 controlled
sealing-preparation cases and 1 inactive Job/projection contract case. PostgreSQL
backup regression passed 4 tests and NAS transport regression passed 7 tests.
Relevant pre-commit hooks, repository YAML lint,
Homepage coverage, Jellyfin compatibility and README image checks passed.

| Gate | Result and evidence |
|---|---|
| First creation/canonical login/app-owned sentinel | Passed; ready/LOGIN after setup, exact UTF-8/quote/space/special-character password |
| Repeated enrollment | Passed; database/role OIDs, password verifier, physical system ID and sentinel unchanged |
| Adoption/removal | Passed; synthetic legacy grants/membership/default ACLs/extension/owner/data/verifier preserved |
| Complete-set preflight | Passed; duplicate/reserved/malformed bindings, unsupported password bytes, tombstone conflicts and later bad adopted credential cause no preceding new-role write |
| Missing/corrupt registry and wrong server | Passed; no inferred bootstrap or replacement objects; owner/shape/ACL changes rejected |
| Child SQL failure | Passed; nonzero parent outcome and provisioning NOLOGIN retained; retry completes |
| Interruption | Passed at before-role, after-role, after-password, after-database, after-schema and after-ready; exact existing objects resumed, latest ready sentinel retained |
| Pending/ready corruption | Passed; unexpected pending LOGIN, missing recorded role, wrong pending DB owner, missing ready role/DB/registry and changed binding rejected |
| Concurrency | Passed; maintenance session keeps its lock through schema child work, competitor fails at bounded 30-second acquisition, two healthy competitors succeed |
| New service isolation | Passed; application cannot read registry, connect to another new DB or read its object after explicit test-only CONNECT grant |
| Post-commit authentication-child failure | Passed; Job returns nonzero, completed ready/LOGIN/data/credential survive acceptance retry; writer gating remains an external lab requirement |
| Reserved Secret identity collision | Passed; app inputs targeting enrollment/admin Secret rejected before sealing |
| Canonical sealed preparation | Passed with controlled sealing fixtures; same value twice, unrelated ciphertext/metadata retained, duplicate output refused, partial sealing publishes nothing |
| Native sealing input format | Local kubectl 1.36.3 client dry-run preserves exact synthetic password bytes; no live API call or cryptographic decryption tested |
| Job source | Passed; native pinned client, Sync wave 1, bounded nonroot execution/read-only projections, failed-hook retention, no API token/CSI/bootstrap SQL |

See [machine-readable sanitized receipts](evidence/2026-10-10-postgresql-enrollment-engine.json)
for exact runtime hashes, client/server image pins, nonce resource identities,
observed data sizes and verified cleanup. Passwords and verifiers are compared
privately; neither appears in receipts or test failure diffs.

## Harness and defects found

Each test uses its own internal Docker network with no published ports, one owned
server volume and exact nonce container identities. Server cap 1GiB/1CPU; at most
two native clients 128Mi/0.5CPU per fixture; logs two5Mi files. Owned usage is checked
below 1GiB; this is an observational cap, not a filesystem quota. Cleanup checks
removal results for recorded resources, never performs daemon-wide pruning and
emits sanitized receipts only when explicitly requested with `--evidence PATH`.
The runtime cannot accept a test fault flag or use this harness's external DSN.

Interruption fixtures add only `SELECT pg_sleep(50)` at documented native SQL
boundary comments, or append it to the native schema child. Tests assert that
removing exactly that pause restores the source byte-for-byte; receipts record the
canonical source hash. Exact synthetic client/backend termination releases the
lock, then the unchanged runtime resumes. This is native SQL, not mocked enrollment.

Qualification and fresh review exposed and fixed three defects through failing tests:

- psql `\quit 1` ignores the argument and returned success after child failure.
  An explicit SQL exception under ON_ERROR_STOP now returns failure before ready/LOGIN.
- Catalog preflight alone allowed an earlier new entry before a later adopted
  credential failed. Established/adopted authentication now preflights before writes.

- Fresh review reproduced an application/aggregate Secret identity collision.
  Preparation now rejects both reserved database-namespace Secret identities before sealing.

Final review also found the plan's broad child-failure requirement conflicted with
native login ordering in the binding design. Ruling: schema/setup failure stays
NOLOGIN, but post-commit authentication failure leaves completed ready/LOGIN and
fails the Job; rollback/reset could change established data or credentials and a
NOLOGIN role cannot authenticate earlier. A native failure characterization and
retry preserves identity/data/verifier. Cost if wrong: premature writers; activation
remains blocked until native consumer gating is proved in the external lab. No
production state was changed by this ruling.

Fixture adaptations: wait for the final network listener rather than Bitnami's
initialization server; use only its synthetic password for private admin queries;
account for PG18 native NOT NULL catalog constraints. Cached Helm and explicit
local loopback permission resolved initial prerequisites for existing checks.

Preparation adds optional existing aggregate/app SealedSecret input paths, omitted
from the plan's CLI but required to preserve ciphertext. Plaintext streams through
private sealing stdin instead of plaintext temporary files. No local helper run
applies manifests or changes SQL. The helper's refusal on duplicate preparation
is distinct from the runtime's successful idempotent repeat.

## Remaining gates

Untested: real synthetic seal/decrypt/readback, installed Argo hook/failed-sync/
selective-sync behavior, same-group controller consumer gating, full native
Terraform/Ansible compute+metadata replacement with retained PostgreSQL disk,
missing/wrong disk startup guard and actual production legacy adoption.

The [remaining native lab plan](../plans/2026-10-10-postgresql-enrollment-native-lab.md)
requires a fresh allocation/identity/version/capacity/credential preflight and exact
approval; removed CNPG scopes are not reusable. Production one-time bootstrap,
activation/pilot, per-app adoption/Autobrr conversion and PostgreSQL CSI migration
remain separately scoped. Current Bitnami empty-PGDATA initialization and
postmaster.pid handling must be guarded/qualified before claiming retained-disk
rebuild safety. Off-NAS restore remains a separate PostgreSQL storage gate.
