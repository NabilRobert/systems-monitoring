# ProbesNotRunning

**Means:** VictoriaMetrics hasn't been able to reach blackbox_exporter for
5 minutes. With no probes, `AppDown` can't fire, so app outages would go
unnoticed.

## Check

1. `docker compose ps blackbox`: running?
2. `docker compose logs --tail 50 blackbox`: a config error after an edit
   of `deploy/blackbox/blackbox.yml`?
3. `docker compose logs --tail 50 victoriametrics | grep -i scrape`.

## What to do

`docker compose up -d blackbox`. If the config is broken, fix it (or
revert the last change) first.

## Over when

The ✅ Resolved message arrives.
