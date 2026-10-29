# Planning

The specs and plans, in the order they were written. The decisions they
led to are in [../adr/](../adr/README.md), one file per decision.

| Doc | What it settles |
|---|---|
| [Phase 1: problem brief](phase-1-problem-brief.md) | The problem, the users, the success metrics, the non-goals |
| [Phase 2: requirements and constraints](phase-2-requirements-constraints.md) | What the monitoring must do, the memory budget, what waits for Juku |
| [Phase 5: architecture decisions](../adr/README.md) | Each component chosen, with the options considered; Juku's draft SLOs and error budgets (moved to `docs/adr/`, one file per decision) |
| [Slice plan](slice-plan.md) | The order of work, what each slice proves, what is cut first, and progress |

Phases 3, 4 and 6 (domain model, flows and failures, risks and spikes)
are folded into the decisions and the slice plan: the domain is small,
and the risks are the memory gates.

## Spikes and gates

Each spike's write-up lives in the decision it settled:

| Spike | Result | Write-up |
|---|---|---|
| Existing detectors vs. custom code (Vector, run against the same end-to-end tests) | Vector adopted; the custom watcher removed | [ADR-006](../adr/0006-security-detection-with-vector.md); code on branch `spike/vector-detectors` |
| VictoriaMetrics memory gate (30 days of data under a 128 MB cap) | Passed: 15.9 MiB idle, 61.6 MiB peak | [ADR-005](../adr/0005-victoriametrics-host-metrics-from-vector.md) |
| Vector's host metrics instead of node_exporter | Adopted | [ADR-005](../adr/0005-victoriametrics-host-metrics-from-vector.md) |
| GlitchTip memory gate (256 MB, 1,000 events) | Failed: an out-of-memory kill with defaults, nothing ingested when tuned to fit; fallback in use | [ADR-004](../adr/0004-glitchtip-behind-memory-gate.md) |
