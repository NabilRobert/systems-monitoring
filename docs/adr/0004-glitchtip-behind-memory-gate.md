# ADR-004: GlitchTip, behind a memory gate

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
