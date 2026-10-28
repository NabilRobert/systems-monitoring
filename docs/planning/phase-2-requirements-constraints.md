# Phase 2: Requirements & Constraints

**Time budget:** short, in parallel with Juku's preparation. Planning and
the first slice (security alerts) now; the rest in slices (see
[slice-plan.md](slice-plan.md)), most of them gated on Juku being live.

## Core scenario

1. Someone logs in to the server over SSH. Within a minute Arthur's phone
   shows: "SSH login: user `deploy`, key, from 203.0.113.7". It was him;
   he ignores it. If it wasn't, the message links the runbook.
2. Juku's chat starts timing out at 9 pm, when the study group is online.
   The fast-burn alert fires: "Juku chat latency SLO: 2% of the monthly
   budget spent in the last hour". The runbook says where to look: the
   host memory panel, then the slow traces in Project 6's viewer.
3. The certificate for the Pitstop demo will expire in 10 days and
   renewal has failed. A silent message arrives; the phone doesn't buzz
   at 3 am for something that can wait ten days.
4. On the first of the month, a budget report shows each SLO's target,
   what was achieved, and how much budget is left. It goes into the
   write-up as it is, including the misses.

## Requirements

**Alert delivery**
- **A1.** One delivery path for every alert: Alertmanager. It groups,
  deduplicates, silences and routes. Every source (the security watcher,
  the probes, the metric rules, and Juku's Grafana) sends to it.
- **A2.** One channel to Arthur: a Telegram bot that messages only him
  (the same bot Juku settled on). The bot token is read from a file,
  never from a committed config.
- **A3.** Two severities, both delivered at once. `page`: a normal
  message that makes the phone buzz (security events, fast SLO burn, an
  app down). `ticket`: a silent message, read when Arthur next looks
  (slow burn, certificate expiry, disk trend, failed-login bursts).
  *Not* "daytime only": Alertmanager drops a muted alert that resolves
  before the mute ends, so a one-shot event would never arrive.
- **A4.** Every alert carries a `runbook_url` annotation pointing at its
  runbook in this repo.
- **A5.** Every alert rule has an automated test that fires it from
  synthetic input and asserts it reaches the channel.
- **A6.** No alert message contains a learner's nickname, question text
  or other content. Security alerts carry the user name and source
  address, because they go only to Arthur.

**Security (slice 1)**
- **S1.** Detect from the system's auth log:
  - every successful SSH login (user, method, source address);
  - every `sudo` command, and every failed `sudo` authentication;
  - a burst of failed SSH logins: at least N from one source address in
    W seconds, and at least M from all sources in W seconds (defaults
    in Phase 5, ADR-006).
- **S2.** Detect a new listening TCP port, compared with an allow-list of
  expected ports, from a periodic snapshot of the host's sockets.
- **S3.** Detection only. Nothing in this project changes the firewall,
  SSH configuration, accounts or any other security setting.
- **S4.** Survive log rotation, and never alert on old lines at startup.
- **S5.** One alert per event, not per retry: Alertmanager's grouping and
  a stable fingerprint per event prevent repeats.

**Uptime and health (later slices)**
- **U1.** Probe each app's public page and health endpoint every minute,
  and each certificate's expiry daily.
- **U2.** Host memory, disk and load; per-container memory against its
  cap; container restarts and out-of-memory kills.
- **U3.** Exceptions with stack traces, grouped (GlitchTip, behind a
  memory gate; Phase 5, ADR-004).

**SLOs and AI-specific (after Juku is live)**
- **L1.** SLOs for Juku from its own records (draft targets in Phase 5,
  ADR-008), with multi-window burn-rate alerts and a monthly report.
- **L2.** Spend per day against Juku's caps, chat refusal and failure
  rates, gateway blocks, and the facts-only fallback rate, from Juku's
  and the gateway's records.
- **L3.** Answer quality over time: a small weekly sample checked by the
  harness's deterministic graders, at $0.
- **L4.** A canary: a scripted agent runs one real task end to end through
  the gateway every hour, with a scripted model ($0).

**Reuse**
- **R1.** Traces stay in Project 6. Alerts and runbooks link to a trace
  search by service and time, or by trace ID where a record has one.
- **R2.** SLIs come from the same Postgres records Juku's evidence SQL
  uses, not from the trace viewer (which keeps only 5,000 traces in
  memory and restarts empty).

## Non-functional requirements

- **NF1. Memory:** every container has a hard cap. The always-on stack
  (Alertmanager, the security detector, probes, metrics) stays within
  **384 MB of caps** in total; GlitchTip, if it passes its gate, gets at
  most 256 MB more. Idle and busy memory are measured and published.
- **NF2. Loopback only:** no monitoring UI or API is published on a
  public interface. Arthur reaches them through an SSH tunnel.
- **NF3. Least privilege:** containers run non-root where the image
  allows, with a read-only filesystem and `cap_drop: ALL`. The security
  watcher mounts the auth log read-only and needs no capabilities.
- **NF4. Pinned images:** every image is pinned by digest.
- **NF5. Latency of alerts:** under 60 s from a security log line to the
  channel; under 3 minutes for an app going down.
- **NF6. Retention:** metrics kept 30 days; nothing else stored beyond
  Alertmanager's own state.

## Constraints

- **Budget:** $0. No paid tools, services or model calls. Anything that
  needs an account (an external uptime check, for example) needs
  Arthur's OK first.
- **One small shared server** for everything: the three apps, Project 6's
  viewer, the gateway and this stack. Memory is the scarce resource.
- **All server work is Arthur's.** This repo ships configs, tests and a
  runbook; it deploys nothing.
- **Juku isn't live yet.** Its SLOs are drafts; its quality and canary
  slices wait for launch.
- **Juku owns its app metrics** (its ADR-009: Grafana over Postgres, no
  Prometheus in the app). This project respects that and adds no metrics
  endpoint to Juku.
- **No server details in public writing.**

## Priorities

| Priority | Requirement |
|---|---|
| **Must** | A1–A6, S1–S5, NF1–NF5: alert delivery and security alerts, tested |
| **Must** | U1, U2: uptime and host health, before Juku launches |
| **Must** | L1: Juku's SLOs, confirmed after two weeks of traffic |
| **Should** | L2, L4: AI-specific signals and the canary |
| **Should** | One real postmortem (or a labelled game-day) |
| **Could** | U3 GlitchTip, if it passes the memory gate |
| **Could** | L3 sampled quality grading |
| **Won't (now)** | A public status page; a log archive; an external uptime check (needs an account) |
