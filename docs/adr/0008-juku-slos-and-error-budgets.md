# ADR-008: Juku's SLOs and error budgets (DRAFT until Juku is live)

Part of the [architecture decisions](README.md).

**Status: draft.** The targets come from Juku's own plan (its Phase 2,
non-functional requirements) and are confirmed or changed after **two
weeks of real traffic**. Every change is recorded with its reason. A
target missed in the first window is published, not quietly lowered.

**Window:** rolling 28 days (four whole weeks, so each weekday counts the
same).

| SLO | SLI (good / valid events) | Target | Budget per 28 days |
|---|---|---|---|
| **Availability** | 1-minute probes of Juku's page and health endpoint that return 200 within 5 s / all probes | 99.5% | 201 bad minutes (about 3.4 h) |
| **Chat latency** | chat answers completed within 40 s / chat answers started | 95% | 5% of answers |
| | … within 15 s | 50% | (the median target) |
| **Chat success** | chat turns ending in an answer / chat turns, **excluding** turns stopped by the budget guard by design (counted and reported separately) | 99% | 1% of turns |
| **Weekly reports on time** | due reports ready within 1 h of their scheduled time; the facts-only fallback counts as delivered | at most **2 late or missing** per 28 days, and never the same learner two weeks running | 2 reports |
| **Answer quality** | sampled chat answers passing the deterministic checks (every cited entry exists; each stated reading, meaning and JLPT level matches the cited entry) / sampled answers. All answers if under 200 a week, else a random 200 | 95% | 5% of the sample |

**Notes on the targets:**
- **Chat latency follows Juku's plan** (p50 ≤ 15 s, p95 ≤ 40 s) rather than
  the earlier example of "99% under 5 s". A tool-using agent turn on
  gpt-5-mini takes several model calls; 5 s isn't honest for it.
- **Reports use a count, not a percentage.** With 10–30 learners there are
  only 40–120 reports in a window; "99%" would mean "zero misses" with
  extra steps.
- **Quality is checked by code at $0.** A model-graded sample is added only
  if Arthur funds it.
- **MCP-backbone and the Pitstop demo** get one availability SLO each
  (99.5%, from probes), proposed now and confirmed after two weeks of
  probe data.

**Burn-rate alerts** (multi-window, as in Google's SRE workbook, scaled to
28 days):

| Alert | Budget spent | Long / short window | Burn rate | Severity |
|---|---|---|---|---|
| Fast burn | 2% | 1 h / 5 min | 13.4 | `page` |
| Slow burn | 5% | 6 h / 30 min | 5.6 | `page` |
| Trend | 10% | 3 days / 6 h | 0.93 | `ticket` |

Juku has little traffic, so a 1-hour window may hold five chat turns, and
one slow answer would look like a fire. **The fast and slow rules need at
least 10 valid events in the long window**; below that, only the 3-day
rule judges. Probe-based SLOs have 120 probes an hour, but right after a
deploy a window may hold only a few, so their burn alerts also need most
of the window's probes first (100 of 120 in an hour; 600 of 720 in 6
hours; 6,000 of 8,640 in 3 days). Found in slice 3: without it, one
failed probe in the first minutes after a deploy paged.

**Error-budget policy** (Arthur's commitment, as the only engineer):
- Budget left: ship normally.
- Budget spent in the window: no feature changes on that path until it
  recovers; only reliability fixes. Noted in JOURNEY.
- One incident spends more than 20% of a budget: a postmortem.
- A monthly report (committed SQL, output committed) shows each SLO's
  target, result and budget left, misses included.
