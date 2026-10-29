"""End to end: probes and host metrics → VictoriaMetrics → vmalert →
Alertmanager → the Telegram stand-in. Needs Docker."""

import time
from pathlib import Path

import pytest

from e2e.stack import compose, query_metrics, record_latency, text_of, wait_for, wait_for_metric

pytestmark = pytest.mark.e2e


def test_host_metrics_from_vector_reach_victoriametrics(stack: Path):
    assert wait_for_metric("host_load1")
    assert wait_for_metric('host_filesystem_used_ratio{mountpoint="/"}')
    assert wait_for_metric("host_memory_oom_kill_events_total")
    # The real hostname is dropped; alerts carry HOST_LABEL instead.
    assert query_metrics('count({__name__=~"host_.+", host!=""})') == []


def test_probes_of_a_healthy_app_succeed(stack: Path):
    [result] = wait_for_metric('probe_success{app="demo-app"}')
    value = result["value"]
    assert isinstance(value, list)
    assert value[1] == "1"  # pyright: ignore[reportUnknownMemberType]


def test_vmalert_records_the_slo_error_ratios(stack: Path):
    # Proves vmalert is running and writing its recording rules back.
    assert wait_for_metric('app:probe_error:ratio_5m{app="demo-app"}', timeout=120)


def test_app_down_pages_then_resolves(stack: Path):
    compose("stop", "demo-app")
    stopped_at = time.time()
    # 3 minutes of failed probes, plus scrape, evaluation and grouping.
    message = wait_for("<b>AppDown</b> on e2e-host", timeout=360)
    assert "demo-app is down: every probe of http://demo-app:8080/health failed" in text_of(message)
    record_latency("AppDown after stopping the app", float(message["received_at"]) - stopped_at)  # pyright: ignore[reportArgumentType]
    compose("start", "demo-app")
    wait_for("✅ Resolved: <b>AppDown</b>", timeout=240)
