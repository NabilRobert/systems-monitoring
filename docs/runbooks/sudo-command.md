# SudoCommand

**Means:** a user ran a command with `sudo`. The message gives the user,
who it ran as, and the command (cut at 200 characters).

## Is it expected?

Yes if you ran it (or a deploy script you started did). A burst of `sudo`
messages during your own maintenance is normal; they are grouped per user
into one message every 5 minutes.

**Not expected:** a command you didn't run, a user who shouldn't have
`sudo`, or a command that edits users, keys, `sudoers`, SSH settings,
cron or the firewall.

## If not expected: check

1. Whether the user is logged in now: `who -a`; how they got in: the
   `SSHLogin` alert before this one, or `last -a`.
2. Everything they ran recently: `sudo grep 'COMMAND=' /var/log/auth.log
   | tail -50` (or `journalctl _COMM=sudo --since "-1h"`).
3. If the command changed something, look at that thing directly (for
   example `getent passwd`, `/etc/sudoers.d/`, `crontab -l -u root`).

## What to do (if not expected)

Follow [ssh-login.md](ssh-login.md), "What to do": end the session, close
the access path, and treat the server as exposed. Root access means
anything on the server may have been changed.

## If a script runs sudo on a schedule

Don't silence `SudoCommand` as a whole. Change the script so it doesn't
need `sudo` (a dedicated user, file permissions, a systemd unit), or
silence that one user's alerts for a fixed time with `amtool silence add
alertname=SudoCommand user=<user> --duration=...` while it's fixed.

## Over when

The command is explained or its effects are undone.
