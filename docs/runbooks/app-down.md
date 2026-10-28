# AppDown

**Means:** every probe of one app's page or health endpoint failed for 3
minutes (no answer, or not 200 within 5 s). Users can't reach it. It
resolves on its own once a probe succeeds again.

While it fires, the same app's SLO burn alerts are held back
(Alertmanager's inhibit rule): the outage is the news.

## Check, in this order

1. **From outside** (your laptop or phone): does the page load? If it
   does, the problem may be the probe's path from the server (DNS, the
   reverse proxy), not the app.
2. **The container:** `docker ps --format '{{.Names}} {{.Status}}'`. Is
   the app's container running, restarting, or `(unhealthy)`?
3. **Its logs:** `docker logs --tail 100 <container>`.
4. **Memory:** an `OutOfMemoryKill` alert just before this one means the
   app hit its memory cap ([memory.md](memory.md)).
5. **The reverse proxy:** if every app is down at once, it's the proxy or
   the server, not one app.
6. **One request:** a recent trace of the app in the trace viewer
   (Project 6) shows where requests stop.

## What to do

- Container stopped or crash-looping: read the last log lines, fix the
  cause, `docker compose up -d` in that app's folder.
- Out of memory: see [memory.md](memory.md) before simply raising the cap.
- A bad deploy: roll back to the previous image or commit.

## Afterwards

If the outage spent more than 20% of the month's availability budget
([ADR-008](../adr/0008-juku-slos-and-error-budgets.md)), write a postmortem: what users saw, how it was found, the
cause, the fix, and what changes so it doesn't recur.

## Over when

The ✅ Resolved message arrives.
