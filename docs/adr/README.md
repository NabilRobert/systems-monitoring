# Architecture decisions (Phase 5)

Short ADRs, 2026-10-28. Each one is a recommendation until Arthur agrees
(see the end). The theme throughout: **one small shared server with hard
memory caps**, so every choice is judged first on memory, then on moving
parts.

```
 auth log, /proc/net/tcp ──► Vector (security rules) ───────┐   (slice 1)
                                                            │
 blackbox_exporter ─┐                                       │
 Vector host_metrics┼─► VictoriaMetrics ─► vmalert ─────────┤   (probes, host, containers: slice 3)
                    │                                       ├─► Alertmanager ─► Telegram bot ─► Arthur
                                                            │
 Juku's Postgres records ─► slo-check (committed SQL) ──────┤   (SLOs, AI signals: slice 5)
 Juku's Grafana (its own ADR-009), if kept ─────────────────┘

 Traces stay in Project 6's viewer: alerts link to them; nothing copies them.
```

One file per decision. Each lists the options considered and why the
others were rejected.

| ADR | Decision |
|---|---|
| [ADR-001](0001-alertmanager-only-delivery-path.md) | Alertmanager is the only delivery path |
| [ADR-002](0002-telegram-not-whatsapp.md) | Telegram, not WhatsApp |
| [ADR-003](0003-blackbox-probes-not-gatus.md) | blackbox_exporter for probes, not Gatus |
| [ADR-004](0004-glitchtip-behind-memory-gate.md) | GlitchTip, behind a memory gate |
| [ADR-005](0005-victoriametrics-host-metrics-from-vector.md) | VictoriaMetrics, with host metrics from Vector |
| [ADR-006](0006-security-detection-with-vector.md) | Security detection with Vector, not custom code (settled) |
| [ADR-007](0007-listening-ports-from-socket-snapshot.md) | New listening ports come from a socket snapshot, not logs |
| [ADR-008](0008-juku-slos-and-error-budgets.md) | Juku's SLOs and error budgets (DRAFT until Juku is live) |
| [ADR-009](0009-slis-from-juku-records.md) | SLIs come from Juku's records, checked by `slo-check` |
| [ADR-010](0010-reuse-project-6-traces.md) | Reuse Project 6's traces by linking, never copying |
| [ADR-011](0011-memory-budget.md) | Memory budget |
| [ADR-012](0012-frameworks-and-plain-code.md) | Frameworks and plain code |

## Open, for Arthur

| # | Decision | Recommendation |
|---|---|---|
| 1 | Delivery path ([ADR-001](0001-alertmanager-only-delivery-path.md)) | Alertmanager for everything; Juku's Grafana points at it instead of at Telegram |
| 2 | Channel ([ADR-002](0002-telegram-not-whatsapp.md)) | Telegram, the same bot as Juku |
| 3 | Probes ([ADR-003](0003-blackbox-probes-not-gatus.md)) | blackbox_exporter; Gatus only as the fallback |
| 4 | Errors ([ADR-004](0004-glitchtip-behind-memory-gate.md)) | GlitchTip, only if it passes the 256 MB gate |
| 5 | Metrics ([ADR-005](0005-victoriametrics-host-metrics-from-vector.md)) | VictoriaMetrics, with the cgroup script instead of cAdvisor |
| 6 | Security detection ([ADR-006](0006-security-detection-with-vector.md), 007) | **Settled:** Vector; detect only; failed logins as silent messages |
| 7 | Juku's SLOs ([ADR-008](0008-juku-slos-and-error-budgets.md)) | The drafts above, confirmed after two weeks live |
| 8 | An external uptime check (needs an account) | Later, once Juku is live: the only way to hear that the whole server is down |
