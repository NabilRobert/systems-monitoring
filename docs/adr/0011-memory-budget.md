# ADR-011: Memory budget

Part of the [architecture decisions](README.md).

| Container | Cap | Slice |
|---|---|---|
| `alertmanager` | 48 MB | 1 |
| `vector` (security detection; host metrics from slice 3) | 128 MB | 1 |
| `victoriametrics` | 128 MB | 3 |
| `vmalert` | 32 MB | 3 |
| `blackbox` | 32 MB | 3 |
| **Always-on total** | **368 MB** (Phase 2, NF1: at most 384) | |
| `slo-check` (runs every 5 min for seconds, then exits) | 48 MB | 5 |
| **Peak, while `slo-check` runs** | **416 MB: over budget (open, below)** | |

*Measured in slice 3's end-to-end run (Docker Desktop, arm64), peak:*
Vector 95.5 MiB (74–79 steady; it was capped at 96 MB, too tight, so
raised to 128), VictoriaMetrics 106 MiB (it fills its cache allowance on
purpose), Alertmanager 19.8, blackbox 16.5, vmalert 14.9.

**Open for slice 5:** with `slo-check` the peak is 416 MB. Either the
budget rises to about 420 MB, or `slo-check` is measured and fits in
what's left (16 MB, unlikely for Python), or blackbox and vmalert drop
to 24 MB each (both peaked under 17 MiB). To decide with `slo-check`'s
measured memory.

*Correction, 2026-10-28:* the first version of this table said 336 MB
with node_exporter and the custom watcher; its rows added up to 384, and
with Vector's larger cap they would have come to 432, over budget.
Dropping node_exporter ([ADR-005](0005-victoriametrics-host-metrics-from-vector.md)) brings it back.
| `glitchtip` and its database, if it passes [ADR-004](0004-glitchtip-behind-memory-gate.md)'s gate | 256 MB | 5 |

Every cap is a hard `mem_limit`. Idle and busy memory are measured on the
server once deployed and published next to these numbers.

**Cut order if the server is short of memory** (decided now, not under
pressure): GlitchTip first; then VictoriaMetrics and `vmalert`, replaced
by Gatus alone (uptime and certificates only), with Vector's host metrics
turned off.
**Never cut** the security detector or Alertmanager.
