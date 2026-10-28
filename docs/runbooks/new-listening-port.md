# NewListeningPort

**Means:** a TCP port is listening on a non-loopback address and isn't in
`AUTHWATCH_ALLOWED_PORTS`. It stays firing while the port listens, and a
"Resolved" message follows when it closes.

## Is it expected?

Expected if you just started or changed a service, or published a
container port. Then the fix is the allow-list (below), or binding the
service to `127.0.0.1` behind the reverse proxy, which is usually better.

**Not expected:** a port nobody opened. A listener you can't explain is a
classic sign of a backdoor.

## Check

1. Which process owns it: `sudo ss -ltnp 'sport = :<port>'`.
2. If it's `docker-proxy`, which container: `docker ps --format
   '{{.Names}} {{.Ports}}' | grep <port>`.
3. When that process started and from where: `ps -o pid,lstart,user,cmd -p
   <pid>` and `sudo ls -l /proc/<pid>/exe`.
4. Whether it's reachable from outside (from your laptop, not the
   server): `nc -vz <server> <port>`.

## What to do

- **Expected, and it should be public:** add it to
  `AUTHWATCH_ALLOWED_PORTS` in `deploy/.env` and run `docker compose up -d
  authwatch`. The alert resolves within about two minutes.
- **Expected, but it shouldn't be public:** bind it to `127.0.0.1`
  (compose: `"127.0.0.1:<port>:<port>"`) and restart that service.
- **Not expected** *(changes the server)*: stop the process, keep a copy
  of its binary and command line for later, and follow
  [ssh-login.md](ssh-login.md), "What to do": someone ran it.

## Known gap

A container port published by Docker with the userland proxy turned off
has no listening socket on the host, so it isn't seen. Check weekly:
`docker ps --format '{{.Names}} {{.Ports}}'`.

## Over when

The port is closed or added to the allow-list, and the "Resolved"
message has arrived.
