# Phase 1: Problem Brief

**Project:** systems-monitoring, the monitoring for Arthur's live apps:
- **Juku**, the JLPT study assistant (Project 7), once it has real users;
- the **Pitstop** read-only demo (Project 3);
- **MCP-backbone**, the database MCP server (Project 1).

It is the eighth portfolio piece. Project 6
([agent-observability](https://github.com/NabilRobert/agent-observability))
answers "what happened in this request". This project answers "is it
working right now, and who gets told when it isn't".

## Problem

**For the portfolio:**
- Every earlier project measures something once: an eval run, a replay, an
  overhead benchmark. None says how a live service is doing *today*, or
  what promise it makes to its users.
- A reviewer from a reliability-minded team asks three questions an
  agent demo can't answer: what is your target, how do you know you're
  meeting it, and who gets woken when you aren't?

**For the apps:**
- **Nobody is told when something breaks.** Today an outage is found when
  Arthur happens to open the page.
- **One small shared server runs everything.** A container that leaks
  memory, a full disk or an expiring certificate takes down all three apps
  at once.
- **The server is reachable from the internet.** A login nobody expected,
  a `sudo` nobody ran, or a new port listening should reach Arthur within
  a minute, not at the next manual check.
- **Agent apps fail quietly.** A chat that answers wrongly, a spend that
  runs ahead of its cap, or a tool that starts refusing still returns
  HTTP 200.

## Users

| Party | Wants |
|---|---|
| **Arthur (operator, the only one paged)** | A message on his phone only for things a user would notice or a security event, each with a runbook. Nothing else |
| **Juku's learners** | Chat that answers, and reports that arrive on Sunday. They never see the monitoring; they feel its absence |
| **Reviewer / hiring team** | SLOs with error budgets, alerts on budget burn, a runbook for every alert, and a postmortem: proof of operating discipline, from records |

## How it's handled today, and where it breaks

- **Juku plans its own app monitoring** (its ADR-009): Grafana over its
  Postgres records, with alerts to a Telegram bot. That covers tool calls,
  pipeline runs and spend inside Juku. It doesn't cover the server, the
  other two apps, uptime seen from outside, or security events.
- **Project 6** keeps the last 5,000 traces in memory. It is for debugging
  one request, not for counting: it restarts empty, and it has no alerts.
- **The server has no host monitoring.** Memory, disk and certificate
  expiry are checked by hand.
- **Security events are in the logs only.** `auth.log` records every login
  and every `sudo`, but nobody reads it until something has gone wrong.

## Success metrics (verifiable)

1. **Every alert is tested on purpose and received.** Each alert rule has
   a test that fires it from synthetic input and checks the message
   arrives at the notification channel (locally: a stand-in for the
   channel's API). On the server, each is fired once by hand and the
   received message is recorded.
2. **Every alert has a runbook** in `docs/runbooks/`, linked from the alert
   itself: what it means, how to check, what to do, when to escalate.
3. **Security alerts reach the channel within 60 s** of the log line, for
   SSH logins, `sudo` use, failed-login bursts and new listening ports.
   Measured locally on synthetic lines, then once on the server.
4. **The whole monitoring stack fits its memory budget** (Phase 2, NF1).
   Each container has a hard cap, and its idle and busy memory are
   measured and published.
5. **Juku has SLOs with error budgets** (drafted in [ADR-008](../adr/0008-juku-slos-and-error-budgets.md)):
   computed from Juku's own records by committed SQL, with burn-rate
   alerts, and a monthly budget report. The targets are drafts until
   Juku has two weeks of real traffic.
6. **One real postmortem** is written up publicly within the first two
   months of Juku being live: blameless, from records, with the fix and
   its measured effect. If nothing breaks, a planned game-day (a
   deliberate failure) is written up instead, and labelled as such.
7. **Alert noise stays low:** at most 2 non-security alerts a week on
   average, and every alert in a month is either acted on or followed by a
   rule change. Counted from Alertmanager's records.
8. **$0.** No paid tools, no paid model calls. The canary uses a scripted
   model; quality grading uses deterministic checks first.

## Non-goals (current pass)

- **No new tracing.** Project 6 owns traces. This project links to them
  (by trace ID) and never re-implements them.
- **No duplicate of Juku's dashboards.** Juku's per-tool, per-agent and
  pipeline panels stay in Juku's Grafana. This project adds what Juku's
  records can't see, and the SLO layer on top.
- **No blocking, only detecting.** Security monitoring never changes
  firewall rules, SSH settings or accounts. Responding is Arthur's job,
  with a runbook.
- **No log archive.** Logs are read for detection and not stored again.
  No Loki, no Elasticsearch.
- **No public status page,** for now. Uptime numbers go in the write-up.
- **No server details in public.** Addresses, hostnames and usernames
  stay out of every committed file.

## Decisions (settled 2026-10-28)

1. **Repo name:** `systems-monitoring` (Arthur).
2. **Order:** planning and the security-alerts slice now, locally; the
   SLOs, AI-quality monitoring and canary wait for Juku to be live.
3. **Budget:** $0.
4. **Deployment** is Arthur's, from a runbook. This project deploys
   nothing.

## Cost of doing nothing

The portfolio shows agents that are measured, traced and guarded, but not
*operated*: no targets, no alerts, no runbooks. And the first sign of a
problem on the shared server, including an unexpected login, stays a
user's complaint or a lucky look at a log.
