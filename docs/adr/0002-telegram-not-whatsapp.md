# ADR-002: Telegram, not WhatsApp

Part of the [architecture decisions](README.md).

**Decision:** Alertmanager's built-in Telegram receiver, to a bot that
messages only Arthur. The token is read from a file (`bot_token_file`);
the chat ID is filled in when the config is rendered on the server. Both
stay out of git. `page` alerts buzz; `ticket` alerts arrive silently
(`disable_notifications`).

**Why:**
- It's built in: no bridge service, nothing extra to run.
- It's free, needs no business verification, and the bot can be revoked
  in a minute.
- Juku already settled on the same bot (Juku's Phase 5, decision 2).

**Rejected:**
- *WhatsApp Cloud API:* Meta business verification, a dedicated number,
  pre-approved templates for every message the business starts, and
  per-message pricing beyond the free tier. It also needs a bridge
  service, because Alertmanager has no WhatsApp receiver.
- *Unofficial WhatsApp libraries:* against WhatsApp's terms; the number
  can be banned, and the bridge holds a logged-in session on the server.
- *Email:* fine as a backup, but slow to notice on a phone. Could be added
  as a second receiver later.
