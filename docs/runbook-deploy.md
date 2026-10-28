# Deploy runbook: security alerts (slice 1), metrics and probes (slice 3)

For Arthur, on the shared server. About an hour, most of it step 7.
Nothing in this repo deploys itself; every step is run by hand.

**What gets installed:** two containers, both read-only, with no
capabilities and nothing reachable from outside:
- `alertmanager` (capped at 48 MB), on `127.0.0.1:9093` only;
- `vector` (capped at 128 MB), which reads `/var/log` read-only and the host's
  `/proc/net/tcp`, and listens only on loopback (its health check).

**What it never does:** change the firewall, SSH, accounts or any other
security setting. It only reads and reports.

`<server>` below is the server's address; it never goes in a file in
this repo.

## 0. Before you start

- [ ] Docker and the compose plugin are installed (`docker compose version`).
- [ ] You know which log the server writes (step 3).
- [ ] If fail2ban or CrowdSec runs on the server, step 7's failed-login
      test could ban your own address. Run that part from another
      network, or skip it.

## 1. Get the code

```bash
git clone https://github.com/NabilRobert/systems-monitoring.git ~/systems-monitoring
cd ~/systems-monitoring/deploy
```

## 2. Make the Telegram bot

On your phone, in Telegram:
1. Message **@BotFather**, send `/newbot`, and pick a name. It answers
   with a token. Don't paste it anywhere else.
2. Open the new bot and send it any message (a bot can't start a chat).

On the server, store the token without it entering your shell history:

```bash
mkdir -p secrets
read -rs TOKEN && printf '%s\n' "$TOKEN" > secrets/telegram_bot_token
```

Find your chat ID (the number at `"chat":{"id":…}` in the reply):

```bash
curl -s "https://api.telegram.org/bot$(cat secrets/telegram_bot_token)/getUpdates" | grep -o '"chat":{"id":[0-9-]*'
```

```bash
printf '%s\n' '<your chat ID>' > secrets/telegram_chat_id
unset TOKEN
```

Alertmanager runs as `nobody` (65534), so it must be able to read these
files, and nobody else should:

```bash
sudo chown -R 65534:65534 secrets
sudo chmod 500 secrets
sudo chmod 400 secrets/*
```

## 3. Which log does the server write?

```bash
ls -l /var/log/auth.log
```

- **It exists** (Ubuntu and most Debian with rsyslog): note its group ID
  for step 4, `stat -c '%g' /var/log/auth.log` (usually `4`, `adm`).
- **It doesn't** (journald only, as on a minimal Debian): stop here and
  tell the session. Vector can read the journal (its `journald` source),
  but that configuration isn't written yet.

Check the SSH program name the log uses (OpenSSH 9.8 and later write
`sshd-session`); both are understood:

```bash
sudo grep -m3 -E 'sshd(-session)?\[' /var/log/auth.log
```

## 4. Settings

```bash
cp .env.example .env
chmod 600 .env
```

Edit `.env`:
- `HOST_LABEL`: a name for the server in messages, not its real
  hostname.
- `AUTH_LOG_GID`: the number from step 3.
- `SECURITY_KNOWN_NETWORKS`: leave empty at first, so every login buzzes.
  Fill it in later if your own logins get tiresome; they then arrive
  silently.

Now see what's listening, to set the allow-list:

```bash
sudo ss -ltnH | awk '{print $4}' | sort -u
```

Every address here that isn't `127.0.0.1:…` or `[::1]:…` would alert.
For each one, either add its port to `SECURITY_ALLOWED_PORTS` (only if
it's meant to be public: usually `22,80,443`), or note it as something
to bind to `127.0.0.1` later. Then check the rules with your settings:

```bash
docker compose run --rm --no-deps vector validate --skip-healthchecks /etc/vector/vector.yaml
```

Expect `Validated`.

## 5. Check the Alertmanager config

```bash
docker compose run --rm --entrypoint amtool alertmanager check-config /etc/alertmanager/alertmanager.yml
```

Expect `SUCCESS`.

## 6. Start

```bash
docker compose up -d
docker compose ps
```

Both should be `Up`, and `vector` `(healthy)` within a minute.
`docker compose logs vector` should show `Found new file to watch`
with `file=/host/log/auth.log`.

## 7. Fire each alert once, and record that it arrived

Note the time you do each, and the time the message arrives.

| # | Do | Expect on the phone |
|---|---|---|
| 1 | The `amtool alert add` command in [runbooks/test-alert.md](runbooks/test-alert.md) | 🔴 DeliveryTest |
| 2 | Open a second SSH session from your laptop | 🔴 SSHLogin with your user, `publickey`, your address |
| 3 | In it: `sudo true` | 🔴 SudoCommand `sudo: <you> ran as root: /usr/bin/true` |
| 4 | `sudo -k` then `sudo true`, and type a wrong password three times | 🔴 SudoAuthFailure `3 incorrect password attempts` |
| 5 | `python3 -m http.server 18999 --bind 0.0.0.0`, wait a minute, then Ctrl-C | 🔴 NewListeningPort `0.0.0.0:18999`, then ✅ Resolved about two minutes after stopping |
| 6 | From your laptop (see step 0 about bans): `for i in $(seq 25); do ssh -o BatchMode=yes -o PreferredAuthentications=none -o ConnectTimeout=5 nosuchuser@<server> true; done` | 🟡 SSHFailedLoginBurst, silently |

If one doesn't arrive, follow
[runbooks/test-alert.md](runbooks/test-alert.md).

Then record the memory:

```bash
docker stats --no-stream --format '{{.Name}} {{.MemUsage}}'
```

Send the session the six arrival delays and the two memory numbers (no
addresses or user names), for the README.

## 8. First week: calibrate

Each evening, count the day's failed logins:

```bash
sudo grep -cE 'Invalid user|Failed|preauth' /var/log/auth.log
```

If `SSHFailedLoginFlood` fired on an ordinary day, raise
the flood threshold above the busiest normal 10 minutes: in
`vector/vector.yaml`, both `max_events: 200` (`flood_groups`) and
`threshold = 200` (`flood_alerts`), then `docker compose up -d vector`. The aim: a flood message means
something unusual.

## 9. Slice 3: metrics, uptime probes and their alerts

Adds three containers (VictoriaMetrics 128 MB, vmalert 32 MB, blackbox
32 MB; all read-only, no capabilities, only VictoriaMetrics published, on
`127.0.0.1:8428`) and host metrics from the existing Vector. The
always-on total becomes 368 MB of caps.

1. **Update:** `git pull` in `~/systems-monitoring`.
2. **Probe targets:** the domains stay on the server, never in git.

   ```bash
   cp targets/apps.yml.example targets/apps.yml
   ```

   Fill in the two domains. Each entry's `app` label is what the alerts
   and SLOs use. Add Juku here once it's live.
3. **Check the rules file** loads (this checks the rules only; step 4's
   `docker compose ps` shows whether vmalert itself started):

   ```bash
   docker compose run --rm --no-deps --entrypoint /vmalert-prod vmalert -rule=/etc/vmalert/rules.yml -dryRun
   ```

4. **Start:** `docker compose up -d`. `vector` is recreated (it now also
   reads the host's `/proc` and `/sys`, read-only). Then
   `docker compose ps`: all five `Up`.
5. **Look:** through an SSH tunnel from your laptop,
   `ssh -L 8428:127.0.0.1:8428 <server>`, open
   `http://127.0.0.1:8428/vmui` and query:
   - `probe_success`: one series per app, value `1`;
   - `host_filesystem_used_ratio{mountpoint="/"}`: the disk's fill level;
   - `host_cgroup_memory_current_bytes`: one series per container.
6. **Fire AppDown once** without touching a real app: add a target that
   can't succeed to `targets/apps.yml`,

   ```yaml
   - targets: ["https://<pitstop-demo-domain>/no-such-page"]
     labels:
       app: drill
   ```

   wait (VictoriaMetrics reloads targets within a minute; the alert needs
   3 minutes of failures), and expect 🔴 **AppDown** about 4–5 minutes
   later. Remove the entry, and ✅ Resolved follows within a few minutes.
7. **Record** `docker stats --no-stream --format '{{.Name}} {{.MemUsage}}'`
   and send the session the five memory numbers and the AppDown delay
   (no domains or addresses).

**Known limits** (in the runbooks too):
- Everything runs on the server it watches: if the whole server goes
  down, nothing here can say so. An outside check needs an account
  (slice plan, later).
- The disk alert watches the filesystem holding `/`.

## Day to day

- **Maintenance with lots of sudo:** silence it for the duration instead
  of stopping Vector:

  ```bash
  docker compose exec alertmanager amtool silence add alertname=SudoCommand --duration=1h --comment=maintenance --alertmanager.url=http://127.0.0.1:9093
  ```

- **Monthly drill**, on the 1st: step 7 row 1 (test-alert).
- **Silences cover vmalert's alerts too**, for example during a planned
  restart: `amtool silence add app=pitstop-demo --duration=30m …`.
- **Updating:** `git pull`, then `docker compose up -d --build`.
- **Images** are pinned by digest in `compose.yaml` and the Dockerfile;
  update them by changing the digest in a branch, not on the server.

## Rolling back

```bash
docker compose down
```

This stops and removes every container. What stays: the files you
created (`deploy/.env`, `deploy/targets/apps.yml`, `deploy/secrets/`;
delete them if you're removing it for good) and the stored metrics and
Alertmanager state (`docker compose down -v` removes those too). To revoke the bot, send `/revoke`
to @BotFather.
