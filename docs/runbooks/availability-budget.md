# AvailabilityFastBurn, AvailabilitySlowBurn, AvailabilityBudgetTrend

**Means:** an app is failing probes fast enough to use up its monthly
availability budget early. The SLO is 99.5% of probes succeeding over 28
days (Phase 5, ADR-008), so the budget is 0.5%: about 3.4 hours a month.

| Alert | Spending | Severity |
|---|---|---|
| Fast burn | 2% of the budget in an hour | page |
| Slow burn | 5% in 6 hours | page |
| Trend | 10% in 3 days | silent ticket |

Each needs enough probes in its window first, so a fresh deploy with a
few minutes of history can't page on one failed probe.

Unlike `AppDown`, these catch an app that is *partly* failing: slow
answers, or failing one probe in ten.

## Check

1. The error ratio over time: in VictoriaMetrics' UI
   (`http://127.0.0.1:8428/vmui` through an SSH tunnel), plot
   `app:probe_error:ratio_5m{app="<app>"}` for the last day.
2. Slow or failing: `probe_duration_seconds{app="<app>"}` near 5 s means
   timeouts; `probe_http_status_code` shows what it answered.
3. Then as for [app-down.md](app-down.md): container, logs, memory.

## What to do

Fix the cause. If the budget for the month is spent, the error-budget
policy applies (ADR-008): no feature changes to that app until it
recovers, reliability work only, and a postmortem if one incident spent
more than 20%.

## Over when

The ✅ Resolved message arrives (the trend alert can take hours to clear).
