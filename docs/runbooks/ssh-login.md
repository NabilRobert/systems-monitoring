# SSHLogin

**Means:** someone logged in to the server over SSH. The message gives the
user, the method (`publickey`, `password`) and the source address.
Silent (ticket) if the address is in `SECURITY_KNOWN_NETWORKS`; otherwise
it buzzes (page).

## Is it expected?

It is expected if **you** (or a deploy you started) logged in just now,
as that user, from that address. Anything else is not, including:
- a login you didn't make, even from a known network;
- `password` as the method, if password login is meant to be off;
- a user you don't recognise.

## If not expected: check, in this order

1. Who is on now: `who -a` and `last -n 20 -a`.
2. What the session did: the lines after the login in the auth log
   (`sudo` use will also have alerted), and `sudo journalctl _UID=<uid>
   --since "-1h"`.
3. Whether keys changed: `ls -la ~<user>/.ssh/` and the mtime of
   `authorized_keys`.
4. Whether anything new is running or listening: `ps -ef --sort=start_time
   | tail -20`; a `NewListeningPort` alert would also have fired.

## What to do (if not expected)

*(Changes the server; Arthur only.)*
1. End the session: `sudo pkill -KILL -u <user>` (or the PID from `who`).
2. Remove any key you don't recognise from `authorized_keys`, and rotate
   your own keys if one may have leaked.
3. Write down the times and what you saw, then decide whether the server
   needs rebuilding from a clean image. Treat secrets on it as exposed.

## Over when

The login is explained, or the session is ended and the access path is
closed. A login that was you needs nothing.
