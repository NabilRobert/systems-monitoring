# systems-monitoring

Monitoring for small live apps on one shared server: security alerts now;
uptime, host health, SLOs with error budgets, and AI-specific signals
next. It watches three apps:
[MCP-backbone](https://github.com/NabilRobert/MCP-backbone), the
[Pitstop](https://github.com/NabilRobert/pitstop-crew-public) demo, and
Juku (a JLPT study assistant, not yet live).

[agent-observability](https://github.com/NabilRobert/agent-observability)
answers "what happened in this request". This answers "is it working
right now, and who gets told when it isn't". Everything runs within hard
memory caps, on $0 of tooling.

**Status:** slice 1, security alerts, is built and tested locally in
Docker. Nothing is deployed yet; the [deploy runbook](docs/runbook-deploy.md)
is ready. The rest is planned in the [slice plan](docs/planning/slice-plan.md).

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
account (Phase 5, ADR-006).

**Nothing is hand-written that a tool already does.** The detection is
[Vector](https://vector.dev) configuration
([`deploy/vector/vector.yaml`](deploy/vector/vector.yaml)): it follows
the auth log through rotation, starts at the end so old lines never
alert, reads both syslog timestamp formats and OpenSSH 9.8's
`sshd-session`, counts each failed *connection* once, reads listening
sockets from `/proc/net/tcp{,6}`, and buffers alerts while Alertmanager
is down. A custom Python watcher was built first; it was replaced after
Vector passed the same end-to-end tests (ADR-006 has the comparison).

## Tested

| Check | What it proves |
|---|---|
| 28 rule tests (`vector test`) | Each rule on real sshd, sudo and `/proc/net/tcp` line shapes: what alerts, at what severity, with what text, and what stays quiet |
| 15 mutations of the rules | Each one (an off-by-one threshold, a missed log format, a wrong byte order, an ignored allow-list…) makes a rule test fail |
| 7 routing tests | `amtool` from the pinned image: the config is valid, and each kind of alert reaches the right receiver |
| 9 end-to-end tests, in Docker | The **production** compose file (images, hardening, caps, routing) with a stand-in for Telegram's API: each alert from a synthetic log line or socket table to a delivered message, silent or not as designed, HTML-escaped, within 60 s; the hand-sent delivery drill; old lines and allowed ports never alert |
| 3 runbook tests | Every alert in the rules has a runbook that exists and is indexed |

Measured locally (Docker Desktop, arm64), during the end-to-end run:

| Container | Peak memory | Cap |
|---|---|---|
| `vector` | 73.1 MiB | 96 MB |
| `alertmanager` | 19.8 MiB | 48 MB |

Every alert arrived 15–23 s after its log line: Alertmanager's 15 s
grouping wait plus Vector's batching. On the server these get measured
again ([runbook](docs/runbook-deploy.md), step 7).

## Run it

```bash
uv sync
uv run ruff check . && uv run pyright && uv run pytest   # quick checks
uv run pytest -m e2e e2e/                                # Docker, about 5 minutes
```

## Layout

| Path | What |
|---|---|
| `deploy/vector/` | The six detection rules, and their unit tests |
| `deploy/alertmanager/` | Routing, receivers and the Telegram message template |
| `deploy/compose.yaml`, `deploy/.env.example` | The stack and its settings |
| `e2e/` | The Docker tests and the Telegram stand-in |
| `tests/` | Quick checks that need no Docker (runbook coverage) |
| `docs/guide.md` | How it works, step by step, with a glossary: start here |
| `docs/planning/` | Problem, requirements, decisions (with the options considered), Juku's draft SLOs, slice plan |
| `docs/runbooks/` | One runbook per alert |
| `docs/runbook-deploy.md` | Deploying slice 1, step by step |

## Licence

MIT.
