# ADR-009: SLIs come from Juku's records, checked by `slo-check`

Part of the [architecture decisions](README.md).

**Decision:** the record-based SLOs (chat, reports, quality, spend) are
computed by committed SQL over Juku's Postgres records, through a
read-only role. A small job, `slo-check`, runs every 5 minutes, computes
the burn rates for each window, and posts to Alertmanager. The monthly
report runs the same SQL. The availability SLOs stay in `vmalert`, on
the probe metrics.

**Why:**
- **Same numbers everywhere:** the alert, the monthly report and the
  published evidence come from one SQL file, so they can't drift.
- **Respects Juku's ADR-009:** no metrics endpoint inside Juku.
- **Testable:** fixture rows in, expected burn rate out, in an ordinary
  test. It doesn't depend on whether Juku keeps Grafana.

**Rejected:**
- *Grafana alert rules over Postgres:* tied to Juku's Grafana decision, and
  hard to unit-test.
- *A SQL exporter → VictoriaMetrics → vmalert (Sloth-style rules):* a second
  copy of the numbers that can drift from the evidence SQL, plus a
  high-churn exporter.
- *Spans from Project 6:* in memory, 5,000 at most, empty after a restart.
