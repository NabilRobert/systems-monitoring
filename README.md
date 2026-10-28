# systems-monitoring

Monitoring for small live apps on one shared server: security alerts,
uptime, host health and availability SLOs with error budgets now;
Juku's own SLOs and AI-specific signals once it is live. It watches three apps:
[MCP-backbone](https://github.com/NabilRobert/MCP-backbone), the
[Pitstop](https://github.com/NabilRobert/pitstop-crew-public) demo, and
Juku (a JLPT study assistant, not yet live).

[agent-observability](https://github.com/NabilRobert/agent-observability)
answers "what happened in this request". This answers "is it working
right now, and who gets told when it isn't". Everything runs within hard
memory caps, on $0 of tooling.

**Status:** slices 1 (security alerts) and 3 (metrics, uptime probes,
host health, availability SLOs) are built and tested locally in Docker.
Nothing is deployed yet; the [deploy runbook](docs/runbook-deploy.md) is
ready. The rest is planned in the [slice plan](docs/planning/slice-plan.md).

## Slice 1: security alerts

```
 auth log ─┐
           ├─► Vector ────► Alertmanager ─► Telegram bot ─► one person's phone
 /proc/net ┘   (detects)    (groups, routes,
                             silences)
```

| Alert | When | Message |
|---|---|---|
| `SSHLogin` | Any successful SSH login | 🔴 buzzes; silent from a known network |
| `SudoCommand` | Any `sudo` command | 🔴 buzzes |
| `SudoAuthFailure` | `sudo` refused (wrong password, not in sudoers) | 🔴 buzzes |
| `NewListeningPort` | A non-loopback TCP listener outside the allow-list | 🔴 buzzes, then ✅ when it closes |
| `SSHFailedLoginBurst` | ≥ 20 failed logins from one address in 60 s | 🟡 silent |
| `SSHFailedLoginFlood` | ≥ 200 failed logins from all addresses in 10 min | 🟡 silent |

Failed logins are silent on purpose: with key-only SSH they can't
succeed, and every public server is scanned all day. A *successful*
login always buzzes. Each alert links its [runbook](docs/runbooks/).

**It only detects.** Nothing here changes a firewall, SSH setting or
account ([ADR-006](docs/adr/0006-security-detection-with-vector.md)).

**Nothing is hand-written that a tool already does.** The detection is
[Vector](https://vector.dev) configuration
([`deploy/vector/vector.yaml`](deploy/vector/vector.yaml)): it follows
the auth log through rotation, starts at the end so old lines never
alert, reads both syslog timestamp formats and OpenSSH 9.8's
`sshd-session`, counts each failed *connection* once, reads listening
sockets from `/proc/net/tcp{,6}`, and buffers alerts while Alertmanager
is down. A custom Python watcher was built first; it was replaced after
Vector passed the same end-to-end tests ([ADR-006](docs/adr/0006-security-detection-with-vector.md) has the comparison).

## Slice 3: uptime, host health and availability SLOs

```
 blackbox (probes each app) ─┐
                             ├─► VictoriaMetrics ─► vmalert ─► Alertmanager ─► Telegram
 Vector (host and containers)┘    (30 days)        (rules)
```

| Alert | When | Message |
|---|---|---|
| `AppDown` | Every probe of an app failed for 3 minutes | 🔴, then ✅ |
| `ProbesNotRunning` | The prober itself is down for 5 minutes | 🔴 |
| `CertificateExpiresSoon`, `…VerySoon` | Under 14 days (renewal failing), under 3 days | 🟡, 🔴 |
| `DiskAlmostFull`, `DiskFull` | Root disk over 85% for 15 min, over 95% for 5 min | 🟡, 🔴 |
| `HostMemoryLow` | Under 10% of memory available for 5 minutes | 🔴 |
| `OutOfMemoryKill` | The kernel killed a process (a container hit its cap) | 🔴 |
| `MonitoringPipelineSilent` | Vector sent no host metrics for 5 minutes: security alerts may be down too | 🔴 |
| `AvailabilityFastBurn`, `…SlowBurn`, `…BudgetTrend` | An app spending its 99.5% availability budget too fast: 2% in an hour, 5% in 6 hours, 10% in 3 days | 🔴, 🔴, 🟡 |

The SLO alerts follow the multi-window burn-rate method of Google's SRE
workbook, scaled to 28 days, with two additions found while testing:
each needs most of its window's probes first (or one failed probe right
after a deploy would page), and they stay quiet while `AppDown` already
covers the outage.

**Reuse:** host and container metrics come from Vector, which already
runs for slice 1, instead of node_exporter plus a hand-written script;
that kept the whole always-on stack at **368 MB** of memory caps.

## Tested

| Check | What it proves |
|---|---|
| 28 rule tests (`vector test`) | Each security rule on real sshd, sudo and `/proc/net/tcp` line shapes: what alerts, at what severity, with what text, and what stays quiet |
| 19 rule tests (`vmalert-tool unittest`) | Each uptime, host and SLO rule on made-up series over time (up to 3 days): when it fires, and when it must not, including right after a deploy |
| 36 mutations of the rules | 15 of the security rules and 19 of the metric rules (an off-by-one threshold, a missed log format, a dropped "enough probes" floor, `increase` instead of `increase_prometheus`…) and 2 of the runbook links: each makes a test fail |
| 7 routing tests | `amtool` from the pinned image: the config is valid, and each kind of alert reaches the right receiver |
| 13 end-to-end tests, in Docker | The **production** compose file (images, hardening, caps, routing, health checks) with stand-ins for Telegram's API and for an app: each security alert from a synthetic log line or socket table to a delivered message, within 60 s; host metrics and probe results reaching VictoriaMetrics; the app stopped → AppDown → restarted → Resolved; no alert that no test caused |
| 4 runbook tests | Every alert in both rule sets links a runbook that exists and is indexed |

Measured locally (Docker Desktop, arm64), peaks during the end-to-end run:

| Container | Peak memory | Cap |
|---|---|---|
| `vector` | 95.5 MiB (74–79 steady) | 128 MB |
| `victoriametrics` | 106 MiB (fills its cache on purpose) | 128 MB |
| `alertmanager` | 19.8 MiB | 48 MB |
| `blackbox` | 16.5 MiB | 32 MB |
| `vmalert` | 14.9 MiB | 32 MB |

Security alerts arrived 15–23 s after their log line (Alertmanager's 15 s
grouping wait plus batching). AppDown arrived 3 min 56 s after the app
stopped: 3 minutes is the rule's own wait, so one failed probe isn't an
outage. On the server these get measured again
([runbook](docs/runbook-deploy.md), steps 7 and 9).

VictoriaMetrics' memory gate, separately: with 30 days of data stored,
15.9 MiB idle and 61.6 MiB peak on 30-day queries.

## Docs

| Start here | What |
|---|---|
| [docs/guide.md](docs/guide.md) | How it works, step by step, with diagrams, a glossary and where to change things |
| [docs/adr/](docs/adr/README.md) | The decisions, one per file, each with the options considered |
| [docs/planning/](docs/planning/README.md) | The specs and plans: problem, requirements, slice plan, spike results |
| [docs/runbooks/](docs/runbooks/README.md) | One runbook per alert |
| [docs/runbook-deploy.md](docs/runbook-deploy.md) | Deploying it on the server, step by step |

## Run it

```bash
uv sync
uv run ruff check . && uv run pyright && uv run pytest   # quick checks
uv run pytest -m e2e e2e/                                # Docker, about 12 minutes
```

## Layout

| Path | What |
|---|---|
| `deploy/vector/` | The six security rules and the host metrics, with unit tests |
| `deploy/vmalert/` | Uptime, host and SLO alert rules, with unit tests |
| `deploy/victoriametrics/`, `deploy/blackbox/`, `deploy/targets/` | What is scraped and probed (the real targets stay on the server) |
| `deploy/alertmanager/` | Routing, receivers, the inhibit rule and the Telegram message template |
| `deploy/compose.yaml`, `deploy/.env.example` | The stack and its settings |
| `e2e/` | The Docker tests and the Telegram stand-in |
| `tests/` | Quick checks that need no Docker (runbook coverage) |
| `docs/guide.md` | How it works, step by step, with a glossary: start here |
| `docs/adr/` | The decisions, one per file, with the options considered; Juku's draft SLOs (ADR-008) |
| `docs/planning/` | Problem, requirements, slice plan, spike results |
| `docs/runbooks/` | One runbook per alert |
| `docs/runbook-deploy.md` | Deploying slice 1, step by step |

## Licence

MIT.
