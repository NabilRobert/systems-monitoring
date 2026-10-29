# ADR-001: Alertmanager is the only delivery path

Part of the [architecture decisions](README.md).

**Decision:** every source sends alerts to one Alertmanager:
- the security detector ([ADR-006](0006-security-detection-with-vector.md)) and `slo-check` post to its HTTP API;
- `vmalert` evaluates metric rules and posts to it;
- Juku's Grafana, if Juku keeps it, uses Alertmanager as its contact
  point instead of talking to Telegram itself.

Alertmanager groups, deduplicates, silences and routes. Its routing tree is
committed and tested (`amtool config routes test`).

**Why:** one place to silence everything during maintenance, one message
format, one set of routing tests, and about 20 MB of memory.

**Rejected:**
- *Each tool's own alerting* (Gatus, Grafana, GlitchTip, a script each):
  four configs, four message formats, and no single silence.
- *Grafana alerting as the hub:* it ties every alert to Juku's Grafana,
  which Juku may replace with cron alerts if Grafana's memory doesn't fit
  (Juku's spike 3).
