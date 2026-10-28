# SSHFailedLoginBurst, SSHFailedLoginFlood

**Means:**
- **Burst:** at least 20 failed SSH logins from **one** address within
  60 s.
- **Flood:** at least 200 from **all** addresses within 10 minutes.

The numbers are in `deploy/vector/vector.yaml` (`burst_groups`,
`burst_alerts`, `flood_groups`, `flood_alerts`). The windows are close
to, not exactly, sliding windows: a group that starts slowly is dropped
and the count starts again.

Each connection counts once, however many lines it logs. Both arrive
silently (ticket), because with key-only SSH a failed attempt can't
succeed. What matters is a *successful* login, which always alerts on its
own (`SSHLogin`).

## Is it expected?

Background scanning hits every public server all day. Occasional bursts
are normal. Look closer if:
- the attempts use **your real user names**, not `root`, `admin`,
  `oracle` and the like (someone knows something about this server);
- an `SSHLogin` from an unknown address follows a burst;
- bursts become constant, or the flood alert fires daily (the
  thresholds may be too low, or the server is being targeted).

## Check

1. Which users were tried: `sudo grep -E 'Invalid user|Failed|preauth'
   /var/log/auth.log | tail -50`.
2. That password login is really off (read-only):
   `sudo sshd -T | grep -E '^(passwordauthentication|kbdinteractiveauthentication|permitrootlogin)'`.
   Expected: `no`, `no`, and `no` or `prohibit-password`.
3. Whether any login succeeded from the same address: `sudo grep
   'Accepted' /var/log/auth.log | grep <address>`.

## What to do

Usually nothing: the message is for the record. If step 2 shows password
login is on, or a real user name is being tried, that's a setting for
Arthur to change *(changes the server)*. This project never blocks
addresses itself (detect only; Phase 2, S3).

## Calibrating the thresholds

In the first week, count a normal day:
`sudo grep -cE 'Invalid user|Failed|preauth' /var/log/auth.log`.
Set the flood threshold well above the busiest normal 10 minutes, so it
fires on something unusual, not on every scan.

## Over when

Nothing to close: each alert ends by itself after 5 minutes.
