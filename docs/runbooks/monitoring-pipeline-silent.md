# MonitoringPipelineSilent

**Means:** Vector has sent no host metrics for 5 minutes. Vector also runs
the security detection, so **security alerts may not be working** either.

## Check

1. `docker compose ps vector`: running and `(healthy)`?
2. `docker compose logs --tail 50 vector`: look for `ERROR`, especially
   from `to_victoriametrics` or a config error after an edit.
3. If Vector is running but VictoriaMetrics isn't receiving:
   `docker compose ps victoriametrics`.

## What to do

`docker compose up -d vector`. Then send the drill in
[test-alert.md](test-alert.md), and open an SSH session to check that a
login alert arrives.

## Over when

The ✅ Resolved message arrives and a test login alerts.
