# Phase 5: Architecture Decisions

Short ADRs, 2026-10-28. Each one is a recommendation until Arthur agrees
(see the end). The theme throughout: **one small shared server with hard
memory caps**, so every choice is judged first on memory, then on moving
parts.

```
 auth log, /proc/net/tcp ──► Vector (detector) ─────────────┐   (security, slice 1)
                                                            │
 blackbox_exporter ─┐                                       │
 node_exporter ─────┼─► VictoriaMetrics ─► vmalert ─────────┤   (probes, host, containers)
 (+ cgroup script) ─┘                                       ├─► Alertmanager ─► Telegram bot ─► Arthur
                                                            │
 Juku's Postgres records ─► slo-check (committed SQL) ──────┤   (SLOs, AI signals)
 Juku's Grafana (its own ADR-009), if kept ─────────────────┘

 Traces stay in Project 6's viewer: alerts link to them; nothing copies them.
```

### ADR-001: Alertmanager is the only delivery path

**Decision:** every source sends alerts to one Alertmanager:
- the security detector (ADR-006) and `slo-check` post to its HTTP API;
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

### ADR-002: Telegram, not WhatsApp

**Decision:** Alertmanager's built-in Telegram receiver, to a bot that
messages only Arthur. The token is read from a file (`bot_token_file`);
the chat ID is filled in when the config is rendered on the server. Both
stay out of git. `page` alerts buzz; `ticket` alerts arrive silently
(`disable_notifications`).

**Why:**
- It's built in: no bridge service, nothing extra to run.
- It's free, needs no business verification, and the bot can be revoked
  in a minute.
- Juku already settled on the same bot (Juku's Phase 5, decision 2).

**Rejected:**
- *WhatsApp Cloud API:* Meta business verification, a dedicated number,
  pre-approved templates for every message the business starts, and
  per-message pricing beyond the free tier. It also needs a bridge
  service, because Alertmanager has no WhatsApp receiver.
- *Unofficial WhatsApp libraries:* against WhatsApp's terms; the number
  can be banned, and the bridge holds a logged-in session on the server.
- *Email:* fine as a backup, but slow to notice on a phone. Could be added
  as a second receiver later.

### ADR-003: blackbox_exporter for probes, not Gatus

**Decision:** Prometheus's `blackbox_exporter` probes each app's public
page and health endpoint every minute (Juku, the Pitstop demo's
`/api/health`, MCP-backbone's `/healthz`) and reads each certificate's
expiry. VictoriaMetrics scrapes it; `vmalert` alerts.

**Why:**
- About 15 MB, and no state of its own.
- Its `probe_success` series is exactly the availability SLI, so the
  burn-rate rules are standard PromQL and sit with the other metric
  rules.
- One alerting path (ADR-001).

**Rejected:**
- *Gatus:* a pleasant YAML config and a status page, but it brings its own
  storage, UI and alerting. Its alerting would be a second path, and its
  "custom" provider can't set `endsAt`, so resolved alerts would linger.
  Used only as a prober, it's about twice the memory of blackbox for a UI
  the metrics store already has. **It is the fallback** if VictoriaMetrics
  fails its memory gate (ADR-005): Gatus alone still gives uptime,
  certificates and alerts.
- *An external uptime service:* it would catch the server itself being
  down, which nothing on the server can. But it's an account, so it needs
  Arthur's OK (Phase 2, Won't for now; listed in the slice plan).

### ADR-004: GlitchTip, behind a memory gate

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

### ADR-005: VictoriaMetrics, not Prometheus

**Decision:** VictoriaMetrics single-node stores metrics (30 days,
`-retentionPeriod=30d`) and scrapes the exporters itself. `vmalert`
evaluates the rules. Caps: 128 MB and 32 MB. **Gate:** under its cap at
idle and while answering a 30-day range query, measured in slice 3.

Container memory comes from a short script that reads each container's
cgroup files (`memory.current`, `memory.max`, the `oom_kill` count in
`memory.events`) every 30 s and writes them for node_exporter's textfile
collector.

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
- *No metrics store (Juku's Postgres only):* Postgres records can't see
  host memory, disk, other apps or probes.
- *A hosted metrics service:* an account, and data leaving the server.

### ADR-006: Security detection with Vector, not custom code (settled)

**The rules** (the same whichever tool runs them):

| Alert | From | Severity |
|---|---|---|
| `SSHLogin` | `Accepted <method> for <user> from <addr>` | `page`; `ticket` from a configured known network |
| `SudoCommand` | `sudo: <user> : … COMMAND=…` | `page` |
| `SudoAuthFailure` | `sudo: <user> : … incorrect password attempt(s)` | `page` |
| `SSHFailedLoginBurst` | ≥ 20 failed logins from one address in 60 s | `ticket` |
| `SSHFailedLoginFlood` | ≥ 200 failed logins from all addresses in 10 min | `ticket` |
| `NewListeningPort` | ADR-007 | `page` |

Each event is its own Alertmanager alert (a unique `event_id`), ending
five minutes later, so one event is one message and never "resolves".
Labels carry a configured host name, never the real hostname. Failed
logins are `ticket` because with key-only SSH they can't succeed and
every public server is scanned all day; a *successful* login and every
`sudo` page.

**Options considered** (reuse before building; checked 2026-10-28):

| Option | Licence, upkeep | Covers | Memory | Verdict |
|---|---|---|---|---|
| Arthur's own repos | — | Nothing: no log detection or alert delivery anywhere (grep across the folder) | — | Nothing to reuse |
| **Vector** 0.59 (log pipeline) | MPL-2.0; Datadog, monthly releases | **All six rules:** file tailing with rotation, regex parsing, per-connection dedupe, windows (`reduce` + `throttle`), an `exec` source for the socket table, an HTTP sink with a bounded retry buffer | **66 MiB idle**, measured | **Chosen** |
| Fluent Bit | Apache-2.0, CNCF | Tailing, parsing, HTTP out; but counting in a window needs a Lua script, which is custom code again | ~10 MiB (commonly reported) | Close second |
| fail2ban, notify-only | GPL-2.0, active | Failed-login bursts only (a true sliding window). Logins and `sudo` would mean abusing a ban engine with `maxretry=1`; actions are shell commands | ~40–60 MiB | Partial; and it is built to block |
| CrowdSec engine, no bouncer | MIT, active | Community brute-force scenarios and an HTTP notifier; no scenarios for successful logins or `sudo`. Shares signals with its central API unless turned off | ~60–120 MiB | Partial; privacy setting to manage |
| mtail | Apache-2.0, Google | Logs to metrics; needs the metrics store (slice 3), and one series per scanning address | small | Later at best |
| Promtail + Loki ruler | Promtail is end-of-life (replaced by Alloy) | Would store the logs again (a non-goal) | 100s of MiB | No |
| grok_exporter | Unmaintained since 2021 | — | — | No |
| Wazuh, OSSEC | GPL | A full SIEM | Wazuh well over 1 GB | No |
| A PAM or `sshrc` hook | — | Logins only | — | Changes the server's authentication settings: no |
| Custom (`authwatch`, built first) | Ours | All six, exact sliding windows | **19 MiB** peak, measured | Replaced by Vector |

**The spike** (branch `spike/vector-detectors`): the same six rules as
Vector configuration, run against **the same 8 end-to-end tests** as the
custom version, in the same Docker harness. All 8 pass; every message
arrived in 16–27 s.

| | Vector | authwatch |
|---|---|---|
| Code to maintain | ~290 lines of YAML and VRL | ~750 lines of Python, 65 unit tests |
| Memory (measured) | 66 MiB idle, cap 96 MB | 19 MiB peak, cap 48 MB |
| Burst and flood windows | Close to a sliding window (a group that starts slowly is dropped and the count restarts) | Exact sliding window |
| Settings | Names and lists from the environment; thresholds are numbers in the config file (Vector no longer expands `${…}` in its config unless a flag named `--dangerously-allow-env-var-interpolation` is set) | All from the environment |
| Unit tests | 28 `vector test` cases | 65 pytest tests |

**Decision: Vector** (settled with Arthur, 2026-10-28). It does the whole job, it is a standard tool
an operations team will recognise, and it removes a hand-written parser,
follower, queue and retry loop. The costs are 47 MB more memory (the
always-on total becomes 384 MB, exactly the Phase 2 budget) and
approximate windows on two `ticket` alerts that are calibrated by hand
anyway. authwatch was removed; it remains in the history of the
`feat/security-alerts` branch. The rules have their own unit tests
(`deploy/vector/tests/rules.yaml`, run with `vector test`), each
mutation-checked.

**Traps found in the spike, for the record:** VRL scopes variables to
their block; it evaluates `a || b && c` left to right; the HTTP sink's
`json` codec already sends a batch as a JSON array (adding `[`…`]` made
Alertmanager answer 400 and drop the batch); and Vector's data directory
must be writable by its user.

### ADR-007: New listening ports come from a socket snapshot, not logs

**Decision:** every 30 s, the detector (ADR-006) reads the host's `/proc/net/tcp` and
`/proc/net/tcp6` (the container uses the host's network namespace,
read-only, no capabilities) and alerts on any listening socket not in an
allow-list (`22`, `80`, `443`, and so on, set on the server). The alert
stays firing while the port listens and resolves when it closes.
Loopback-only listeners are ignored by default: they aren't reachable
from outside, and Docker creates them constantly.

**Why:** nothing logs "a port started listening". Reading `/proc` needs
no tools in the image and no privileges.

**Known gap, in the runbook:** a container port published through
Docker's iptables rules with the userland proxy turned off has no
listening socket on the host. The runbook adds a weekly
`docker ps --format '{{.Ports}}'` check.

**Rejected:**
- *Running `ss -ltn`:* needs `iproute2` in the image for the same data.
- *osquery's `listening_ports` table:* the same data, with a daemon of
  its own and access to the host's processes.
- *Falco:* needs a privileged container or eBPF access.
- *auditd rules on `bind()`:* changes the kernel's audit configuration (a
  security setting) and is very noisy.
- *An outside port scan:* sees only what's open past the firewall, needs
  a second machine, and scanning from a cloud host can breach its terms.

### ADR-008: Juku's SLOs and error budgets (DRAFT until Juku is live)

**Status: draft.** The targets come from Juku's own plan (its Phase 2,
non-functional requirements) and are confirmed or changed after **two
weeks of real traffic**. Every change is recorded with its reason. A
target missed in the first window is published, not quietly lowered.

**Window:** rolling 28 days (four whole weeks, so each weekday counts the
same).

| SLO | SLI (good / valid events) | Target | Budget per 28 days |
|---|---|---|---|
| **Availability** | 1-minute probes of Juku's page and health endpoint that return 200 within 5 s / all probes | 99.5% | 201 bad minutes (about 3.4 h) |
| **Chat latency** | chat answers completed within 40 s / chat answers started | 95% | 5% of answers |
| | … within 15 s | 50% | (the median target) |
| **Chat success** | chat turns ending in an answer / chat turns, **excluding** turns stopped by the budget guard by design (counted and reported separately) | 99% | 1% of turns |
| **Weekly reports on time** | due reports ready within 1 h of their scheduled time; the facts-only fallback counts as delivered | at most **2 late or missing** per 28 days, and never the same learner two weeks running | 2 reports |
| **Answer quality** | sampled chat answers passing the deterministic checks (every cited entry exists; each stated reading, meaning and JLPT level matches the cited entry) / sampled answers. All answers if under 200 a week, else a random 200 | 95% | 5% of the sample |

**Notes on the targets:**
- **Chat latency follows Juku's plan** (p50 ≤ 15 s, p95 ≤ 40 s) rather than
  the earlier example of "99% under 5 s". A tool-using agent turn on
  gpt-5-mini takes several model calls; 5 s isn't honest for it.
- **Reports use a count, not a percentage.** With 10–30 learners there are
  only 40–120 reports in a window; "99%" would mean "zero misses" with
  extra steps.
- **Quality is checked by code at $0.** A model-graded sample is added only
  if Arthur funds it.
- **MCP-backbone and the Pitstop demo** get one availability SLO each
  (99.5%, from probes), proposed now and confirmed after two weeks of
  probe data.

**Burn-rate alerts** (multi-window, as in Google's SRE workbook, scaled to
28 days):

| Alert | Budget spent | Long / short window | Burn rate | Severity |
|---|---|---|---|---|
| Fast burn | 2% | 1 h / 5 min | 13.4 | `page` |
| Slow burn | 5% | 6 h / 30 min | 5.6 | `page` |
| Trend | 10% | 3 days / 6 h | 0.93 | `ticket` |

Juku has little traffic, so a 1-hour window may hold five chat turns, and
one slow answer would look like a fire. **The fast and slow rules need at
least 10 valid events in the long window**; below that, only the 3-day
rule judges. Probe-based SLOs have 60 events an hour and need no floor.

**Error-budget policy** (Arthur's commitment, as the only engineer):
- Budget left: ship normally.
- Budget spent in the window: no feature changes on that path until it
  recovers; only reliability fixes. Noted in JOURNEY.
- One incident spends more than 20% of a budget: a postmortem.
- A monthly report (committed SQL, output committed) shows each SLO's
  target, result and budget left, misses included.

### ADR-009: SLIs come from Juku's records, checked by `slo-check`

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

### ADR-010: Reuse Project 6's traces by linking, never copying

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

### ADR-011: Memory budget

| Container | Cap | Slice |
|---|---|---|
| `alertmanager` | 48 MB | 1 |
| `vector` (security detection) | 96 MB | 1 |
| `blackbox` | 32 MB | 3 |
| `victoriametrics` | 128 MB | 4 |
| `vmalert` | 32 MB | 4 |
| `node-exporter` (with the cgroup textfile script) | 48 MB | 4 |
| `slo-check` (runs every 5 min, exits) | 48 MB | 6 |
| **Always-on total** | **384 MB** (Phase 2, NF1: at most 384) | |
| `glitchtip` and its database, if it passes ADR-004's gate | 256 MB | 5 |

Every cap is a hard `mem_limit`. Idle and busy memory are measured on the
server once deployed and published next to these numbers.

**Cut order if the server is short of memory** (decided now, not under
pressure): GlitchTip first; then VictoriaMetrics, `vmalert` and
node_exporter, replaced by Gatus alone (uptime and certificates only).
**Never cut** the security detector or Alertmanager.

### ADR-012: Frameworks and plain code

**Decision:** the stack Arthur already uses, so this looks like the other
projects:
- **Python tooling:** uv, ruff, pyright (strict), pytest.
- **`slo-check` (slice 5):** Typer for its command line, pydantic-settings
  for its settings, SQLAlchemy 2 for the read-only queries, httpx and
  tenacity to post to Alertmanager with retries.
- **Everything else is configuration** of existing tools (Alertmanager,
  Vector, later VictoriaMetrics and the exporters), tested by running
  them.

**Plain code, on purpose:** the Telegram stand-in in `e2e/` is a 50-line
standard-library HTTP server used only by tests; a web framework would be
heavier than the problem.

## Open, for Arthur

| # | Decision | Recommendation |
|---|---|---|
| 1 | Delivery path (ADR-001) | Alertmanager for everything; Juku's Grafana points at it instead of at Telegram |
| 2 | Channel (ADR-002) | Telegram, the same bot as Juku |
| 3 | Probes (ADR-003) | blackbox_exporter; Gatus only as the fallback |
| 4 | Errors (ADR-004) | GlitchTip, only if it passes the 256 MB gate |
| 5 | Metrics (ADR-005) | VictoriaMetrics, with the cgroup script instead of cAdvisor |
| 6 | Security detection (ADR-006, 007) | **Settled:** Vector; detect only; failed logins as silent messages |
| 7 | Juku's SLOs (ADR-008) | The drafts above, confirmed after two weeks live |
| 8 | An external uptime check (needs an account) | Later, once Juku is live: the only way to hear that the whole server is down |
