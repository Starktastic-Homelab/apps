# Proposed PostgreSQL consumer startup gate

Approved by the user on 2026-10-11. This authorizes inactive source implementation and review, not production activation.

The native lab has proved that selective sync and apply strategy can report
Succeeded without enrollment, and that Healthy/Synced can coexist with a failed
enrollment hook. SQL ready/LOGIN is committed before the authentication child
returns; successful login alone cannot prove the whole enrollment Job succeeded.
A new consumer must verify current acceptance before its writer starts.

Recommended approach: use native Argo Application status as the completion
receipt. Give the enrollment hook a deterministic name derived from its declared
configuration, frozen runtime/job semantics and encrypted canonical inputs. Put
the same nonsecret generation in the enrollment ConfigMap. An init container
checks a successful full sync containing that exact successful hook and matching
current generation; it rejects selective/apply-only sync, failed/running/stale
operations, missing metadata and unavailable API access. Check the ConfigMap
generation before and after reading the Application to reject a concurrent update.
A following native PostgreSQL client check verifies the consumer's actual
canonical login before starting the writer.

Access is limited to GET of the named postgres Argo Application in argocd and
named enrollment ConfigMap in databases. The init container receives a projected
service-account token; the application container does not receive that token
through this feature. No API Secret access, list/watch, write permission,
administrator password or new controller is needed. Existing SQL ledger and its
privileges stay unchanged. Generic inactive source and synthetic consumers get
separate review and merge before native lab use; existing production consumers
remain untouched pending their own adoption.

Trade-off: fresh Pods remain blocked whenever the current enrollment acceptance
cannot be verified, including incomplete or hook-skipping syncs. Existing running
Pods continue. Native Argo objects are regenerated and requalified automatically
on a fresh cluster; they are not backed up as durable state.

Alternative: add a generation-aware final acceptance record and a restricted
read API in SQL. That avoids the Argo-object read dependency but changes the
approved ledger/interface/privilege model and requires SQL versioning and more
custom logic. A retained Job receipt would instead change successful-hook cleanup
and introduce another Kubernetes receipt lifecycle.

Required qualification: controller- and service-phase consumers; blocked/failed
hook; authentication child forced to fail after ready/LOGIN; selective/apply-only
and stale-generation rejection; full retry; no early writer; fresh-metadata
retained-disk rebuild. The independent startup guard remains required before the
full rebuild test.
