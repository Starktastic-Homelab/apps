# F18 fix: count NotReady only while the fencer watches (approved by Ben, 2026-11-18)

**Why.** After a host cold boot the API returns each worker's NotReady condition from before the shutdown, already
older than `not_ready_seconds`. Fence rule 2 passes on the first read, so a worker that is booting normally is
fenced, and the settle rule (correct by design) then latches the fence on its new boot (lab B10 Step 3 and leg a).

**Goal.** A stale NotReady never starts a fence. **Non-goals.** No change to settle, unfence, holds, manual fences or
the clock source. **Anti-goal.** Never fence sooner than today.

**Approaches.**
- Chosen: a watch start. The fencer records the API server time (Date header) of its first successful read after
  it starts, and again after any loop whose API read failed or after more than 3 loops without a successful read
  (review finding, 2026-11-18). Rule 2 measures NotReady from
  `max(lastTransitionTime, watch start)`.
- Rejected: settle on the deciding read's bootID (the ADR settles after the cut on purpose).
- Rejected: Lease renewals as the heartbeat (equally stale after a cold boot).

**Cost.** After a storage VM reboot, a fencer restart or an API outage, a truly hung worker is fenced up to
`not_ready_seconds` later.

**Tests.** A stale NotReady on the first read is not fenced; a worker is fenced `not_ready_seconds` after the watch
start; a blind loop resets the watch start. Lab re-test (Ben OKs it then): restart 972 and 973 with 971 up and no
hold; expect no fence.
