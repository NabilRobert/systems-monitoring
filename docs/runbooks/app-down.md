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

## Apps behind Cloudflare (Framed)

The probe of Framed goes out to Cloudflare and back to the server, like a
visitor's request. The status code it got tells you which hop failed:
query `probe_http_status_code{app="framed"}` in vmui (0 means no answer
within 5 s).

| Code | Means | Look at |
|---|---|---|
| 502 | Caddy is up; the Framed container isn't answering | `docker compose -p framed ps`, then `docker compose -p framed logs --tail 100` |
| 521, 522 | Cloudflare can't reach the server at all | Caddy (`systemctl status caddy`), the server itself; other apps will be down too |
| 526 | Cloudflare rejects Caddy's certificate for Framed | `sudo journalctl -u caddy --since "-2d" \| grep -i framed` for a failed renewal |
| 403 | Cloudflare challenged the prober as a bot; people are fine | Cloudflare's security events for the site |

The page probe (`/`) proves the Node server answers. It doesn't touch
Framed's database, so a broken database with a working server shows up as
errors in the app, not here.

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
