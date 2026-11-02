# ADR-013: Version drift check, in Vector

Part of the [architecture decisions](README.md).

**Decision:** Vector checks each live app against GitHub `main` every 15
minutes (`deploy/vector/version-drift.yaml`) and vmalert decides when that's
worth a message. No new container, no script, and no change to the memory
budget ([ADR-011](0011-memory-budget.md)).

**The check:** read `version` from the app's health answer, then ask GitHub's
compare endpoint (`/repos/<repo>/compare/<version>...main`) how many commits
`main` has that the live build lacks.

**Options considered:**

| Option | Verdict |
|---|---|
| **Vector's VRL `http_request`, one `exec` source reading the target list** | **Chosen.** It runs in a container we already have. The second call depends on the first answer, which `http_client` sources can't do |
| Two `http_client` sources (the app, then GitHub's `commits/main`), joined by a rule | Can only compare strings: it would call an unknown commit "behind", and it can't count commits |
| blackbox probes | They check a response; they can't carry a value into a second request |
| A small Python service (httpx, a loop) | Clearest code, but a new image and about 32 MB of cap against the 16 MB left in the budget |
| A shell script under Vector's `exec` | The image has `wget` and `awk` but no `jq`: JSON parsing by hand |
| diun, Watchtower, Renovate | They compare image tags or dependency versions. These apps deploy from a git checkout |

Writing this ourselves is justified only because no tool compares a running
app's reported commit with a branch. It's about 150 lines of configuration.

**Which apps:** only apps that report their commit. MCP-backbone does
(`/healthz`, `version`). The Pitstop demo's `/api/health` doesn't, so it isn't
listed; Juku isn't live. Adding one is one entry in `targets/versions.yml`.

**Choices:**

- **Grace period: 24 hours.** Arthur deploys by hand, not on merge, so a merge
  one evening and a deploy the next day is routine. A shorter wait would
  message about normal work, and a longer one lets a merged fix sit for days
  unseen. It's a ticket either way.
- **`min_over_time` over a day, not `for: 24h`.** `for` restarts when the
  series has a gap, so any GitHub outage or vmalert restart would restart the
  wait. Commit dates don't work either: a branch's commits predate its merge,
  so an old branch would look overdue the moment it merged.
- **Every 15 minutes.** One call per app per check. Against GitHub's 60
  unauthenticated calls an hour per address, that's room for about 15 apps
  even with nothing else on the address using the limit.
- **Unknown is its own result.** No failure path produces a commit count,
  so "unknown" can't read as "in date". It's a ticket after 6 hours, never a
  page, and `VersionCheckNotRunning` covers the check itself stopping.
- **All tickets.** A live app behind `main` is work to do, not an incident.

**Measured:**
- A hung endpoint fails after 44 s (10 s and 3 retries), and `http_request`
  has no setting for this. With `VECTOR_THREADS=1` and two hung targets,
  another source in the same Vector ran on with no gap over 1 s, so a hung
  check doesn't stall the rest of Vector.
- Against the real API: 15 commits behind for the example old build, 0 for
  `main`'s head, `unknown_commit` for a made-up commit and for a repository
  that doesn't exist. A Vector running only this pipeline sat at 34 MiB after
  six such checks, with answers of about 150 KB.

**Known limits:**
- Every commit counts, so a docs-only merge still reads as behind.
- A tagged checkout would report `v1.0-3-gabc…`, which reads as
  `version_missing`. No app has tags yet.
- `http_request` shows neither status code nor headers, so a rate limit is
  recognised only as "not an answer" (`github_error`).
