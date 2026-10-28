# AuthwatchTest

**Means:** someone ran `docker compose exec authwatch python -m authwatch
test-alert` to check delivery. It's sent as a page, so it proves the
loudest path works.

## Is it expected?

Only if you just ran it: after deploying, after changing the Alertmanager
config or the bot, and on the first of each month as a drill.

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

## Over when

The message has arrived.
