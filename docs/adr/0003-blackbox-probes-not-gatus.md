# ADR-003: blackbox_exporter for probes, not Gatus

Part of the [architecture decisions](README.md).

**Decision:** Prometheus's `blackbox_exporter` probes each app's public
page and health endpoint every minute (Juku, the Pitstop demo's
`/api/health`, MCP-backbone's `/healthz`) and reads each certificate's
expiry. VictoriaMetrics scrapes it; `vmalert` alerts.

**Why:**
- About 15 MB, and no state of its own.
- Its `probe_success` series is exactly the availability SLI, so the
  burn-rate rules are standard PromQL and sit with the other metric
  rules.
- One alerting path ([ADR-001](0001-alertmanager-only-delivery-path.md)).

**Rejected:**
- *Gatus:* a pleasant YAML config and a status page, but it brings its own
  storage, UI and alerting. Its alerting would be a second path, and its
  "custom" provider can't set `endsAt`, so resolved alerts would linger.
  Used only as a prober, it's about twice the memory of blackbox for a UI
  the metrics store already has. **It is the fallback** if VictoriaMetrics
  fails its memory gate ([ADR-005](0005-victoriametrics-host-metrics-from-vector.md)): Gatus alone still gives uptime,
  certificates and alerts.
- *An external uptime service:* it would catch the server itself being
  down, which nothing on the server can. But it's an account, so it needs
  Arthur's OK (Phase 2, Won't for now; listed in the slice plan).
