# DeliveryTest

**Means:** someone sent a test alert by hand, to check that alerts reach
the phone. It's sent as a page, so it proves the loudest path works.

Send it from `deploy/` on the server:

```bash
docker compose exec alertmanager amtool alert add DeliveryTest severity=page host=test event_id="$(date +%s)" --annotation=summary="Test alert: delivery works" --annotation=runbook_url=https://github.com/NabilRobert/systems-monitoring/blob/main/docs/runbooks/test-alert.md --alertmanager.url=http://127.0.0.1:9093
```

The `event_id` label makes it a one-shot event, so it never sends a
"resolved" message.

## Is it expected?

Only if you just sent it: after deploying, after changing the
Alertmanager config or the bot, and on the first of each month as a
drill.

## If it didn't arrive within a minute

1. `docker compose logs --tail 50 alertmanager`: a `Notify attempt
   failed` line shows Telegram's answer (a wrong token or chat ID, most
   often).
2. `docker compose exec alertmanager amtool alert query
   --alertmanager.url=http://127.0.0.1:9093`: is the alert there at all?
3. Check that the bot token and chat ID files in `deploy/secrets/` have
   the right values and are readable (`ls -l`), without printing them.
4. Check that you have sent the bot a message at least once: a bot can't
   start a chat.

## If the test arrives but real alerts don't

Vector isn't sending. `docker compose logs --tail 50 vector`: look for
`Found new file to watch` (it is reading the log) and for `ERROR` lines
from `to_alertmanager`.

## Over when

The message has arrived.
