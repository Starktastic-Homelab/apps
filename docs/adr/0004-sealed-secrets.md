# ADR 0004: Use sealed-secrets for secret management

- **Status:** Accepted
- **Date:** 2026-06-22

## Context

Secrets must be stored in Git (GitOps) without exposing plaintext, and managed by a single
maintainer without standing external infrastructure.

## Decision

Use Bitnami **sealed-secrets** (chart version `2.19.0`, deploy phase `foundation`). Secrets are
encrypted to `SealedSecret` resources committed to Git; the in-cluster controller decrypts
them into native `Secret`s.

## Rationale

- **No external dependency:** Unlike an external-secrets operator backed by a cloud/Vault
  secret store, sealed-secrets needs no external service to operate — simpler and cheaper for
  a homelab.
- **Encrypted at rest in Git:** Ciphertext is safe to commit; only the cluster's controller
  key can decrypt.
- **Fits the bootstrap order:** Runs in the `foundation` phase so secrets exist before
  dependent controllers/services.

## Consequences

- The controller's private key is the root of trust — its backup/DR is critical (handled by
  the separate secrets-backup tooling and `cert-backup`).
- No native secret rotation from an upstream store; rotation is manual/redeploy.
