# LiveVersionBehind, LiveVersionUnknown, VersionCheckNotRunning

All three are silent tickets: nothing is broken right now. See
[ADR-013](../adr/0013-version-drift-check.md).

- **`LiveVersionBehind`:** the app has been behind GitHub `main` at every
  check for a day. The fix or feature merged there isn't live yet.
- **`LiveVersionUnknown`:** for 6 hours, no check could tell which version
  is running. This isn't "in date": drift could be going unseen.
- **`VersionCheckNotRunning`:** no check has reported anything for an hour.

The reason in a `LiveVersionUnknown` message:

| Reason | Means |
|---|---|
| `app_unreachable` | The app's health URL didn't answer (`AppDown` covers the outage) |
| `version_missing` | It answered, but with no commit hash in `version`, for example `unknown` |
| `unknown_commit` | GitHub doesn't know that commit in that repository: a local commit never pushed, or a wrong `repo` in `versions.yml` |
| `github_error` | GitHub answered with something else, usually the rate limit (60 calls an hour per address) |
| `github_unreachable` | GitHub didn't answer at all |

## Is it expected?

`LiveVersionBehind` after a merge that doesn't need deploying (docs, tests,
CI): the check counts every commit on `main`. Deploy anyway to clear it, or
silence it (below).

## Check

What's running, and how far behind (use the domain from `versions.yml`):

```bash
curl -s https://<domain>/healthz
```

```bash
curl -s https://api.github.com/repos/<owner>/<repo>/compare/<version>...main | grep -m1 ahead_by
```

What the check last saw, through the SSH tunnel to `127.0.0.1:8428/vmui`
(the deploy runbook, step 9):

```
last_over_time(app_version_commits_behind[1h])
last_over_time(app_version_check_unknown[1h])
```

For `VersionCheckNotRunning`:

```bash
cat targets/versions.yml
```

```bash
docker compose logs --tail 50 vector | grep -iE 'versions.yml|version_'
```

The file must exist on the server and be a YAML list, with `app`,
`version_url` and `repo` in each entry.

## What to do

- **Behind:** deploy the app *(changes the server)*, using that app's own
  runbook. The ✅ Resolved follows at the next check.
- **Not worth deploying:** silence it for a while:

  ```bash
  docker compose exec alertmanager amtool silence add alertname=LiveVersionBehind app=<app> --duration=72h --comment="docs only" --alertmanager.url=http://127.0.0.1:9093
  ```

- **`github_error` that won't clear:** something else on this address may be
  using up the rate limit. `curl -s https://api.github.com/rate_limit` shows
  what's left.
- **`unknown_commit`:** push the commit, or fix `repo` in `versions.yml`.
- **`version_missing`:** that's the app's to fix, in its own repo. Until
  then, take its entry out of `versions.yml`.

## Over when

The ✅ Resolved message arrives. A `LiveVersionBehind` that resolves while
`LiveVersionUnknown` fires isn't a deploy: the day-long window has simply run
out of good checks.
