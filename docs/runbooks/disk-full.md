# DiskAlmostFull, DiskFull

**Means:** the server's root disk has been over 85% full for 15 minutes
(silent ticket), or over 95% for 5 minutes (page). At 100%, databases stop
writing and containers fail to start.

## Check

1. What's big: `sudo du -xh --max-depth=1 / 2>/dev/null | sort -h | tail -15`.
2. Docker, usually the cause: `docker system df`.
3. Logs: `sudo journalctl --disk-usage` and `sudo du -sh /var/log`.

## What to do

*(Changes the server; Arthur only.)*
- Unused images and build cache: `docker image prune -a` and
  `docker builder prune` (check `docker system df` first; running
  containers' images are kept).
- The journal: `sudo journalctl --vacuum-size=200M`.
- Never delete a database's files by hand.

## Note

The disk measured is the one holding `/`. If Docker's data is on a
separate disk, this alert doesn't watch it; ask the session to add it.

## Over when

The ✅ Resolved message arrives.
