# ADR-004: GlitchTip, behind a memory gate (gate failed: fallback in use)

Part of the [architecture decisions](README.md).

**Decision:** GlitchTip (open-source, Sentry-compatible) for exceptions
with stack traces, grouped, **only if** a spike shows it fits:
- in its minimal mode as documented (Postgres only, web and worker in one
  process; verified in the spike, not assumed);
- with its database, under a 256 MB total cap;
- through a burst of 1,000 synthetic events, with no out-of-memory kill.

Juku and the Pitstop demo would send to it with the standard Sentry SDKs,
with personal data off (`send_default_pii=False`) and request bodies
dropped.

**Fallback if the gate fails:** no exception store. Error *counts* come
from Juku's records (each per-call record has an error category) and
alert through `slo-check`; the stack trace for one request is found in
its trace in Project 6's viewer.

## The gate, run 2026-10-29 (slice 4): failed

GlitchTip 6.2.6 (image from 2026-08-08) in the minimal mode the decision
asked for, which it does support: web and worker in one process
(`run-all-in-one.sh`) and no Valkey (Postgres as cache and task queue).
Postgres 18. A throwaway org and project, then 1,000 Sentry-protocol
error events (5 KB each: a 15-frame stack trace, five error types) sent
20 at a time. Memory sampled every 2 s.

| Configuration | Idle | Peak | Out-of-memory kill | Accepted | Stored |
|---|---|---|---|---|---|
| Defaults; GlitchTip 192 MB + Postgres 64 MB | 118 + 43 MiB | 192 (at its cap) + 62 MiB | **Yes, in Postgres** | 740 of 1,000 (260 timed out) | **440** |
| Tuned as its changelog suggests (ingest batches of 10, 2 task lanes, a 6-connection pool); 160 MB + 96 MB | 87 + 50 MiB | 107 + 58 MiB | No | **0** (every request timed out) | **0** |

- **Defaults:** GlitchTip sat at its cap the whole burst, Postgres had a
  process killed, and more than half the events were lost.
- **Tuned:** memory stayed low, but the web side waited for database
  connections the background tasks were holding ("pool error: Timeout
  occurred while waiting for a slot"), so nothing was ingested. A bigger
  pool needs more Postgres connections, and so more Postgres memory: a
  working configuration exists somewhere above this gate, not inside it.

Not tried: a middle configuration with a larger budget (roughly 384 MB or
more for the pair). That's a budget decision, not a tuning one, and it
would push the always-on total far past the server's limit (ADR-011).

**So the fallback applies** (decided before the run, above): no exception
store. Error counts come from the apps' records and alert through
`slo-check` (slice 5); the stack trace for one failing request is in its
trace in Project 6's viewer. Revisit if the server gains memory, or if
errors become frequent enough that grouping them pays for ~400 MB.

**Why:** grouped stack traces with first-seen and frequency are the
fastest way from "error rate up" to the line of code, and GlitchTip is
the only Sentry-compatible option light enough to try.

**Rejected:**
- *Self-hosted Sentry:* well over a gigabyte (Kafka, ClickHouse, Redis).
- *Sentry's hosted free tier:* an account, and exception data (which can
  hold content) leaving the server.
- *Copying exceptions into Project 6's traces as the store:* traces live
  in memory and roll over at 5,000; they're for one request, not for
  counting.
