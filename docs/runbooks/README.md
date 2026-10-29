# Runbooks

One per alert. Each alert's message links its runbook. A test
(`tests/test_config.py`) fails if an alert has none.

| Alert | Severity | Runbook |
|---|---|---|
| `SSHLogin` | page (ticket from a known network) | [ssh-login.md](ssh-login.md) |
| `SudoCommand` | page | [sudo-command.md](sudo-command.md) |
| `SudoAuthFailure` | page | [sudo-auth-failure.md](sudo-auth-failure.md) |
| `SSHFailedLoginBurst`, `SSHFailedLoginFlood` | ticket | [ssh-failed-logins.md](ssh-failed-logins.md) |
| `NewListeningPort` | page | [new-listening-port.md](new-listening-port.md) |
| `DeliveryTest` (sent by hand) | page | [test-alert.md](test-alert.md) |
| `AppDown` | page | [app-down.md](app-down.md) |
| `ProbesNotRunning` | page | [probes-not-running.md](probes-not-running.md) |
| `CertificateExpiresSoon`, `CertificateExpiresVerySoon` | ticket, page | [certificate-expires.md](certificate-expires.md) |
| `DiskAlmostFull`, `DiskFull` | ticket, page | [disk-full.md](disk-full.md) |
| `HostMemoryLow`, `OutOfMemoryKill` | page | [memory.md](memory.md) |
| `MonitoringPipelineSilent` | page | [monitoring-pipeline-silent.md](monitoring-pipeline-silent.md) |
| `AvailabilityFastBurn`, `AvailabilitySlowBurn`, `AvailabilityBudgetTrend` | page, page, ticket | [availability-budget.md](availability-budget.md) |

**Page** buzzes the phone; **ticket** arrives silently. Every runbook
follows the same order: what it means, is it expected, what to check,
what to do, when it's over.

**Commands below are read-only** unless marked *(changes the server)*.
Those are Arthur's to run; nothing in this repo runs them.
