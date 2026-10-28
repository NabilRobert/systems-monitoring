# SudoAuthFailure

**Means:** `sudo` refused someone: a wrong password, a user not in
`sudoers`, or a command not allowed. The message gives the user, the
reason and the command they tried.

## Is it expected?

A mistyped password of your own, just now, is expected. Anything else is
not. **"user NOT in sudoers"** is never expected: an account that
shouldn't have root tried to get it.

## Check

1. Who the user is and how they're logged in: `who -a`, `last -a`, and
   the `SSHLogin` alert for that session.
2. What else that session did: `sudo grep <user> /var/log/auth.log |
   tail -50`.
3. For a service account (no login shell expected): which process ran
   `sudo`, from the PID in the log line: `ps -o pid,ppid,user,cmd -p <pid>`
   if it is still running.

## What to do (if not expected)

Treat it as an intruder with a foothold who is trying to get root: follow
[ssh-login.md](ssh-login.md), "What to do", for that user's sessions.

## Over when

Explained (your own typo), or the session is ended and the account's
access is reviewed.
