# ADR-006: Security detection with Vector, not custom code (settled)

Part of the [architecture decisions](README.md).

**The rules** (the same whichever tool runs them):

| Alert | From | Severity |
|---|---|---|
| `SSHLogin` | `Accepted <method> for <user> from <addr>` | `page`; `ticket` from a configured known network |
| `SudoCommand` | `sudo: <user> : … COMMAND=…` | `page` |
| `SudoAuthFailure` | `sudo: <user> : … incorrect password attempt(s)` | `page` |
| `SSHFailedLoginBurst` | ≥ 20 failed logins from one address in 60 s | `ticket` |
| `SSHFailedLoginFlood` | ≥ 200 failed logins from all addresses in 10 min | `ticket` |
| `NewListeningPort` | [ADR-007](0007-listening-ports-from-socket-snapshot.md) | `page` |

Each event is its own Alertmanager alert (a unique `event_id`), ending
five minutes after Alertmanager receives it, so one event is one message and never "resolves".
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

**Break-it pass (2026-10-29), found and fixed, each now a test:**
- *Events buffered through a long Alertmanager outage were lost.* Vector
  stamped each event's end time when it created it, so after an outage
  of more than 5 minutes they arrived already over and were never sent.
  Events now carry no end time; Alertmanager ends them `resolve_timeout`
  (5 min) after it receives them. (The custom watcher had handled this;
  the Vector port had lost it.)
- *Failed logins with a space in the user name weren't counted,* so a
  scanner could stay under the burst threshold. sshd logs the name as
  given. The name is now matched greedily, and the address and port are
  taken from the end of the line, where sshd writes them; a name that
  contains "from <address> port <n>" or "[preauth]" can't plant a false
  address.
- Checked and already fine: a login written straight into a freshly
  rotated log, a 10 KB line with non-Latin text, and an Alertmanager
  restart with an alert waiting.

