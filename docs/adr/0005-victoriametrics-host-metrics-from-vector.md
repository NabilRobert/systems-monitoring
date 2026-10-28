# ADR-005: VictoriaMetrics, with host metrics from Vector

Part of the [architecture decisions](README.md).

**Decision:** VictoriaMetrics single-node stores metrics (30 days,
`-retentionPeriod=30d`) and scrapes the prober itself. `vmalert`
evaluates the rules. Caps: 128 MB and 32 MB.

**Gate (passed, slice 3, 2026-10-28):** 30 days of data shaped like
ours (2,500 series, one point a minute) stored, then the container
restarted under its 128 MB cap: **15.9 MiB idle**, and **61.6 MiB peak**
while answering three 30-day range queries (each under 0.13 s). No
out-of-memory kill. Loading those 30 days in bulk did *not* fit under the
cap (killed twice, even one series per request): any backfill runs
uncapped, offline.

**Host and container metrics come from Vector's `host_metrics` source**
(memory, the root filesystem, load, each Docker container's memory and
CPU, and the kernel's out-of-memory kill count), pushed to
VictoriaMetrics by remote write. Vector already runs for [ADR-006](0006-security-detection-with-vector.md), so this
replaces both node_exporter and the hand-written cgroup script planned
here, and saves a container (reuse before building).

What it can't give: a container's memory *cap*, and container names (it
reports cgroup IDs). So the planned "container over 90% of its cap" alert
became **"the kernel killed a process for lack of memory"**, which is what
a container reaching its cap actually causes, and what a user would
notice. Per-container memory stays in VictoriaMetrics for diagnosis.

**Traps found, both fixed and tested:**
- MetricsQL's `increase()` counts a series' *first* value as an increase.
  The out-of-memory counter is cumulative since boot, so every Vector
  restart would have paged. The rule uses `increase_prometheus()`.
- "No host metrics for 5 minutes" would fire for the half-minute before
  Vector's first push on every deploy. It waits one minute first.

**Why:**
- At this scale (a few thousand series), VictoriaMetrics commonly runs in
  tens of megabytes, below Prometheus with the same data. The gate
  measures it rather than trusting that.
- MetricsQL accepts PromQL, so the rules and skills are the standard
  ones, and a later move to Prometheus is a config change.
- No second Grafana: Juku's Grafana, if kept, adds VictoriaMetrics as a
  Prometheus data source; otherwise `vmui` (built in) is enough for
  Arthur alone.

**Rejected:**
- *Prometheus:* standard and well known, but more memory for the same
  series. It is the fallback if VictoriaMetrics misbehaves.
- *cAdvisor for container metrics:* commonly 50–150 MB to report a few
  numbers per container that the cgroup files already hold.
- *node_exporter plus a cgroup script (the first plan):* a container and
  a hand-written script for what Vector, already running, reports.
- *No metrics store (Juku's Postgres only):* Postgres records can't see
  host memory, disk, other apps or probes.
- *A hosted metrics service:* an account, and data leaving the server.
