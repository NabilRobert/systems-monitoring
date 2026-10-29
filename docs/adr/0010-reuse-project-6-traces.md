# ADR-010: Reuse Project 6's traces by linking, never copying

Part of the [architecture decisions](README.md).

**Decision:**
- Alerts carry a link to Project 6's trace search for the service and the
  alert's time range; record-based alerts include example trace IDs
  (Juku's per-call records store them).
- Runbooks start at the alert, go to the metric or record, then to one
  trace. Nothing here stores or re-derives spans.
- The canary (slice 8) is a scripted agent run through the gateway, so
  its trace in Project 6's viewer shows the whole request across three
  services. That reuses Project 6's own end-to-end check rather than
  writing a new one.

**Why:** Project 6 deliberately stops at traces; this project starts
where it stops.
