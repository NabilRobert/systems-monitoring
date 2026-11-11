# CertificateExpiresSoon, CertificateExpiresVerySoon

**Means:** an app's TLS certificate expires in under 14 days (silent
ticket) or under 3 days (page). Certificates normally renew automatically
30 days before expiry, so 14 days means renewal has been failing for two
weeks.

## Check

1. Which domain: the alert names the probed URL.
2. The reverse proxy's log, for the renewal error:
   `sudo journalctl -u caddy --since "-2d" | grep -i -E "renew|acme|certificate"`
   (or the proxy you run).
3. Common causes: DNS no longer points at the server, port 80 or 443
   closed by a firewall change, the certificate authority's rate limit.

**Behind Cloudflare (Framed):** the probe sees Cloudflare's certificate,
not Caddy's, and Cloudflare renews its own. An alert here means
Cloudflare's renewal failed: check the site's edge certificates in the
Cloudflare dashboard. Caddy's certificate for Framed isn't probed. If it
expires and Cloudflare checks it (SSL mode "Full (strict)"), Cloudflare
answers 526 and `AppDown` fires instead ([app-down.md](app-down.md)).

## What to do

Fix the cause, then reload the proxy so it retries *(changes the server;
Arthur only)*. The alert clears after the next probe sees the new
certificate.

## Over when

The ✅ Resolved message arrives.
