# ADR 0011: Restrict Loki ingress with one NetworkPolicy

- **Status:** Accepted
- **Date:** 2026-11-06

## Context

Loki runs with `auth_enabled: false`, and Alloy ships every pod's logs to it. Any pod in the cluster could query
`loki-gateway.monitoring` or `loki.monitoring:3100` and read every app's logs. Some apps log tokens or one-time secrets:
unpackerr v1 logs a generated admin password at startup (apps#1459, fixed for that app in apps#1463). ADR 0008 declined
a cluster-wide NetworkPolicy set because there was no security driver. This exposure is one.

## Decision

Add one ingress-only NetworkPolicy, `loki-ingress` in `services/operations/loki/manifests/`. It selects the Loki pods
(`loki-0` and `loki-gateway`) and admits only Alloy, Grafana, Prometheus (the Loki ServiceMonitor) and Loki itself, all in
`monitoring`. ADR 0008 still holds for everything else.

## Rationale

- kube-router (ADR 0007) already enforces NetworkPolicy. kube-prometheus-stack ships one of the same shape for the
  Grafana image renderer.
- Gateway basic auth alone would not help: the `loki` Service on port 3100 bypasses the gateway, so a policy would be
  needed anyway. It would also add a sealed credential to two clients.
- The Loki chart's `networkPolicy.enabled` renders `loki-namespace-only` with `podSelector: {}` and Ingress plus Egress.
  That would restrict every pod in `monitoring`, including Grafana's and Alertmanager's egress.
- Ingress-only and without port lists, so Loki's egress and its own gRPC and memberlist traffic don't change.

## Consequences

- A new Loki client (another Grafana, a log-based alert in another namespace) must be added to the policy.
- A chart upgrade that renames `app.kubernetes.io/name` or `app.kubernetes.io/instance` on Alloy, Grafana or Prometheus
  pods cuts that client off. Alloy then drops logs after its retries, so check log ingestion after such upgrades.
- Pods in `monitoring` that are not listed (Alertmanager, kube-state-metrics, Tempo) can no longer reach Loki either.
