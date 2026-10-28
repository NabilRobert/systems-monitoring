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
           ├─► authwatch ─► Alertmanager ─► Telegram bot ─► one person's phone
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

`authwatch` is about 750 lines of standard-library Python, comments included:
- follows the auth log through rotation and truncation, starting at the
  end so old lines never alert; reads both syslog timestamp formats, and
  both `sshd` and OpenSSH 9.8's `sshd-session`;
- counts each failed *connection* once, however many lines it logs;
- reads listening sockets from `/proc/net/tcp{,6}` (no tools, no
  privileges);
- queues alerts if Alertmanager is down (bounded, with backoff).

## Tested

| Check | What it proves |
|---|---|
| 65 unit tests | Parsing real sshd and sudo line shapes, every rule and threshold, socket-table decoding, rotation, the queue and retries |
| 22 mutations of the code | Each one (an off-by-one threshold, a missed log format, a dropped dedup, a lost rotation…) makes a test fail |
| 7 routing tests | `amtool` from the pinned image: the config is valid, and each kind of alert reaches the right receiver |
| 8 end-to-end tests, in Docker | The **production** compose file (images, hardening, caps, routing) with a stand-in for Telegram's API: each alert from a synthetic log line or socket table to a delivered message, silent or not as designed, HTML-escaped, within 60 s; old lines and allowed ports never alert |

Measured locally (Docker Desktop, arm64), during the end-to-end run:

| Container | Peak memory | Cap |
|---|---|---|
| `authwatch` | 18.6 MiB | 48 MB |
| `alertmanager` | 13.9 MiB | 48 MB |

Every alert arrived 15–20 s after its log line: Alertmanager's 15 s
grouping wait plus polling. On the server these get measured again
([runbook](docs/runbook-deploy.md), step 7).

## Run it

```bash
uv sync
uv run ruff check . && uv run pyright && uv run pytest   # unit tests
uv run pytest -m e2e e2e/                                # Docker, about 4 minutes
```

## Layout

| Path | What |
|---|---|
| `authwatch/` | The log and socket watcher |
| `deploy/` | Compose file, Alertmanager config and message template, `.env.example` |
| `e2e/` | The Docker tests and the Telegram stand-in |
| `docs/planning/` | Problem, requirements, decisions (with rejected alternatives), Juku's draft SLOs, slice plan |
| `docs/runbooks/` | One runbook per alert |
| `docs/runbook-deploy.md` | Deploying slice 1, step by step |

## Licence

MIT.
