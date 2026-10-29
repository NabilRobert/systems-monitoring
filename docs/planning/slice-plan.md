# Slice Plan

Vertical slices: each one runs end to end, from a signal to a message on
Arthur's phone (locally: to a stand-in for Telegram's API), and each is
tested. Every slice costs $0.

## Slices

| Slice | What it proves, end to end | Needs Juku live? | Est. |
|---|---|---|---|
| **0. Planning** | Phases 1, 2 and 5 and this plan | No | 0.5 day |
| **1. Security alerts** | Vector ([ADR-006](../adr/0006-security-detection-with-vector.md)) reads synthetic auth-log lines and a fake socket table in Docker; Alertmanager routes them; the Telegram receiver delivers them to a local stand-in. Every rule has a unit test and an end-to-end test, each mutation-checked. A runbook per alert, and a deploy runbook for Arthur | No | 1 day |
| **2. Deploy slice 1** (Arthur) | On the server, from `docs/runbook-deploy.md`: each alert fired once by hand and received; the failed-login thresholds calibrated on a week of real traffic; idle memory recorded | No | Arthur, 1 h |
| **3. Metrics and probes** | VictoriaMetrics, `vmalert`, `blackbox_exporter`, and host and container metrics from Vector ([ADR-005](../adr/0005-victoriametrics-host-metrics-from-vector.md): this replaced node_exporter and a cgroup script). Alerts: an app down, the prober down, a certificate under 14 and 3 days, disk over 85% and 95%, host memory low, an out-of-memory kill, Vector silent. Availability SLOs with burn-rate alerts for MCP-backbone and the Pitstop demo. The memory gate ([ADR-005](../adr/0005-victoriametrics-host-metrics-from-vector.md)) measured before anything else | No | 1 day |
| **4. Errors** | The GlitchTip spike against its gate ([ADR-004](../adr/0004-glitchtip-behind-memory-gate.md)). If it passes: its compose file and a test event from a sample app. If it fails: the result is published and the fallback recorded | No | 0.5 day |
| **— Checkpoint —** | The server is watched before Juku's first user: security, uptime, host health. Report to Arthur | | |
| **5. Juku's SLOs** | `slo-check` with the committed SLI SQL; burn-rate tests on fixture rows (each window, the 10-event floor); Juku's Grafana pointed at Alertmanager. After two weeks: the drafts confirmed or changed, with reasons | **Yes** | 1 day |
| **6. AI-specific signals** | Spend *rate* against the cap (will the pool run out before the window ends?), chat refusal and failure rates, gateway blocks, the facts-only fallback rate; the weekly quality sample through the harness's deterministic checks. Juku's own alerts (budget thresholds, heartbeat, audit chain) stay Juku's and are not duplicated | **Yes** | 1 day |
| **7. Canary** | Every hour, a scripted agent (scripted model, $0) runs one real task through the gateway to MCP-backbone and checks the answer. A failure pages; its trace is linked from Project 6's viewer | **Yes** (gateway in front of MCP-backbone) | 0.5 day |
| **8. Write-up** | A runbook for every alert (checked by a test that every rule's `runbook_url` exists); the first monthly SLO report; one real postmortem, or a labelled game-day; the README with measured memory; a portfolio entry for the site session | **Yes** | 1 day |

**Order:** 0 → 1 → (2, Arthur) → 3 → 4 → checkpoint → Juku launches →
5 → 6 → 7 → 8. Slices 3 and 4 don't depend on each other.

**Progress (2026-10-29):** slices 0, 1, 3 and 4 done, locally; the
deploy runbook covers slices 2 and 3. Slice 4's GlitchTip failed its
memory gate, so its fallback is in use ([ADR-004](../adr/0004-glitchtip-behind-memory-gate.md)). Nothing is deployed.

## Fixed before building (so no choice is made after seeing results)

- **Every alert is tested twice:** a unit test on the rule, and an
  end-to-end test that the message reaches the channel stand-in. A rule
  without both doesn't merge.
- **Every alert has a runbook,** linked from the alert.
- **Memory gates** ([ADR-004](../adr/0004-glitchtip-behind-memory-gate.md), [ADR-005](../adr/0005-victoriametrics-host-metrics-from-vector.md)) are measured before the component is
  adopted, and the numbers are published either way.
- **SLO targets are drafts until two weeks of traffic;** after that, a
  change needs a written reason, and the first window's result is
  published even if missed.
- **Detection only:** no slice changes a firewall, SSH, account or other
  security setting.

## Spend plan

**Everything costs $0.** The images are open source (Alertmanager, Python,
VictoriaMetrics, the exporters, GlitchTip). The canary's model is
scripted. Quality checks are deterministic. Telegram's bot API is free.

## Fallback decision (made in advance)

If time or memory runs short, cut in this order:
1. Slice 4, GlitchTip (fallback: error counts and traces, [ADR-004](../adr/0004-glitchtip-behind-memory-gate.md)).
2. Slice 6's quality sample (keep the rate signals).
3. Slice 3's metrics store, replaced by Gatus alone (uptime and
   certificates only; [ADR-011](../adr/0011-memory-budget.md)).

**Never cut:**
- security alerts (slice 1);
- a runbook for every alert;
- the published SLO results, misses included;
- detection only, never blocking;
- no server details in any committed file.
