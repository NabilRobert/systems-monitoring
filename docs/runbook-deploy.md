# Deploy runbook: security alerts (slice 1)

For Arthur, on the shared server. About an hour, most of it step 7.
Nothing in this repo deploys itself; every step is run by hand.

**What gets installed:** two containers, both capped at 48 MB, both
read-only, with no capabilities and nothing reachable from outside:
- `alertmanager`, on `127.0.0.1:9093` only;
- `authwatch`, which reads `/var/log` read-only and the host's
  `/proc/net/tcp`, and listens on nothing.

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
  tell the session. authwatch can read `journalctl -f -o short-iso` from
  standard input (`AUTHWATCH_LOG_FILE=-`), but that needs a small systemd
  unit instead of this compose service, which isn't written yet.

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
- `AUTHWATCH_HOST_LABEL`: a name for the server in messages, not its real
  hostname.
- `AUTH_LOG_GID`: the number from step 3.
- `TZ`: the server's timezone (`timedatectl | grep 'Time zone'`).
- `AUTHWATCH_KNOWN_NETWORKS`: leave empty at first, so every login buzzes.
  Fill it in later if your own logins get tiresome; they then arrive
  silently.

Now see what's listening, to set the allow-list:

```bash
docker compose build authwatch
docker compose run --rm --no-deps authwatch list-ports
```

Every line marked `NOT ALLOWED` would alert. For each one, either add it
to `AUTHWATCH_ALLOWED_PORTS` (only if it's meant to be public: usually
`22,80,443`), or note it as something to bind to `127.0.0.1` later. Run
`list-ports` again until it shows only what you expect.

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

Both should be `Up`, and `authwatch` `(healthy)` within a minute.
`docker compose logs authwatch` should show `watching /host/log/auth.log`.

## 7. Fire each alert once, and record that it arrived

Note the time you do each, and the time the message arrives.

| # | Do | Expect on the phone |
|---|---|---|
| 1 | `docker compose exec authwatch python -m authwatch test-alert` | 🔴 AuthwatchTest |
| 2 | Open a second SSH session from your laptop | 🔴 SSHLogin with your user, `publickey`, your address |
| 3 | In it: `sudo true` | 🔴 SudoCommand `sudo: <you> ran as root: /usr/bin/true` |
| 4 | `sudo -k` then `sudo true`, and type a wrong password three times | 🔴 SudoAuthFailure `3 incorrect password attempts` |
| 5 | `python3 -m http.server 18999 --bind 0.0.0.0`, wait a minute, then Ctrl-C | 🔴 NewListeningPort `0.0.0.0:18999`, then ✅ Resolved about two minutes after stopping |
| 6 | From your laptop (see step 0 about bans): `for i in $(seq 25); do ssh -o BatchMode=yes -o PreferredAuthentications=none -o ConnectTimeout=5 nosuchuser@<server> true; done` | 🟡 SSHFailedLoginBurst, silently |

If one doesn't arrive, follow
[runbooks/authwatch-test.md](runbooks/authwatch-test.md).

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
`AUTHWATCH_FLOOD_TOTAL` above the busiest normal 10 minutes, then
`docker compose up -d authwatch`. The aim: a flood message means
something unusual.

## Day to day

- **Maintenance with lots of sudo:** silence it for the duration instead
  of stopping authwatch:

  ```bash
  docker compose exec alertmanager amtool silence add alertname=SudoCommand --duration=1h --comment=maintenance --alertmanager.url=http://127.0.0.1:9093
  ```

- **Monthly drill**, on the 1st: step 7 row 1 (test-alert).
- **Updating:** `git pull`, then `docker compose up -d --build`.
- **Images** are pinned by digest in `compose.yaml` and the Dockerfile;
  update them by changing the digest in a branch, not on the server.

## Rolling back

```bash
docker compose down
```

This stops and removes both containers; the server is as it was, apart
from the `deploy/.env` and `deploy/secrets/` files you created (delete
them if you're removing it for good). To revoke the bot, send `/revoke`
to @BotFather.
