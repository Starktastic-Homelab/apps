# Backlog & Known Gaps

An informal, single place for intentional gaps and not-yet-implemented ideas, so they don't
live as scattered TODOs. Significant *decisions* are recorded as ADRs under `docs/adr/`.

## Known gaps

- **Runtime threat detection:** No host/container runtime security agent (e.g. Falco) is
  deployed. Edge/web traffic is filtered by CrowdSec.
- **Alerting depth:** Only a few component-specific custom alerts exist (e.g. kube-vip,
  CrowdSec); there is no broad custom Prometheus alert coverage and no blackbox / synthetic
  (uptime) monitoring yet.
- **Diagrams:** Architecture is documented in prose only; no diagrams-as-code.
- **Contributor docs:** No CONTRIBUTING guide, issue/PR templates, or CODEOWNERS.
- **Network policies:** No cluster-authored default-deny NetworkPolicies; only chart-shipped
  policies are in effect (see `docs/adr/0008-networkpolicies-declined.md`).
- **CNI:** A Cilium migration is deferred (see `docs/adr/0007-cni-flannel-kube-router.md`).
