"""Alerts → Alertmanager's API: the payload, the queue and the retries."""

import io
import json
import urllib.error
from datetime import UTC, datetime, timedelta

from authwatch.alerts import EVENT_TTL, PAGE, Alert
from authwatch.sender import Sender

T0 = datetime(2026, 10, 28, 3, 0, tzinfo=UTC)
AM = "http://alertmanager:9093"
RUNBOOKS = "https://example.org/runbooks"


def alert(n: int = 0, ends_at: datetime | None = None) -> Alert:
    return Alert(
        "SSHLogin",
        PAGE,
        f"login {n}",
        T0,
        ends_at or T0 + EVENT_TTL,
        {"user": "deploy", "event_id": str(n)},
    )


class FakeAlertmanager:
    def __init__(self) -> None:
        self.bodies: list[list[dict[str, object]]] = []
        self.urls: list[str] = []
        self.fail_with: OSError | None = None

    def __call__(self, url: str, body: bytes) -> None:
        if self.fail_with is not None:
            raise self.fail_with
        self.urls.append(url)
        self.bodies.append(json.loads(body))


def test_payload_shape():
    am = FakeAlertmanager()
    sender = Sender(AM + "/", "web-1", RUNBOOKS, post=am)
    sender.enqueue([alert()])
    assert sender.flush(T0)
    assert am.urls == ["http://alertmanager:9093/api/v2/alerts"]
    assert am.bodies == [
        [
            {
                "labels": {
                    "alertname": "SSHLogin",
                    "severity": "page",
                    "host": "web-1",
                    "user": "deploy",
                    "event_id": "0",
                },
                "annotations": {
                    "summary": "login 0",
                    "runbook_url": "https://example.org/runbooks/ssh-login.md",
                },
                "startsAt": "2026-10-28T03:00:00+00:00",
                "endsAt": "2026-10-28T03:05:00+00:00",
            }
        ]
    ]
    assert sender.pending == 0


def test_unreachable_keeps_alerts_and_backs_off():
    am = FakeAlertmanager()
    am.fail_with = urllib.error.URLError("connection refused")
    sender = Sender(AM, "h", RUNBOOKS, post=am)
    sender.enqueue([alert(1), alert(2)])
    assert not sender.flush(T0)
    assert sender.pending == 2
    am.fail_with = None
    # Within the 1 s backoff: not retried yet.
    assert not sender.flush(T0 + timedelta(milliseconds=500))
    assert am.bodies == []
    assert sender.flush(T0 + timedelta(seconds=1))
    assert [a["annotations"] for a in am.bodies[0]] == [  # type: ignore[index]
        {"summary": "login 1", "runbook_url": f"{RUNBOOKS}/ssh-login.md"},
        {"summary": "login 2", "runbook_url": f"{RUNBOOKS}/ssh-login.md"},
    ]


def test_backoff_doubles_up_to_the_limit():
    am = FakeAlertmanager()
    am.fail_with = ConnectionRefusedError()
    sender = Sender(AM, "h", RUNBOOKS, post=am, max_backoff=timedelta(seconds=4))
    sender.enqueue([alert()])
    now = T0
    waits: list[timedelta] = []
    for _ in range(5):
        sender.flush(now)
        assert sender._next_try is not None  # pyright: ignore[reportPrivateUsage]
        waits.append(sender._next_try - now)  # pyright: ignore[reportPrivateUsage]
        now = sender._next_try  # pyright: ignore[reportPrivateUsage]
    assert waits == [timedelta(seconds=s) for s in (1, 2, 4, 4, 4)]


def test_alert_that_waited_past_its_end_is_moved_forward():
    am = FakeAlertmanager()
    sender = Sender(AM, "h", RUNBOOKS, post=am)
    sender.enqueue([alert()])
    later = T0 + timedelta(hours=1)
    sender.flush(later)
    assert am.bodies[0][0]["endsAt"] == (later + EVENT_TTL).isoformat()


def test_state_alert_keeps_its_short_end():
    am = FakeAlertmanager()
    sender = Sender(AM, "h", RUNBOOKS, post=am)
    state = Alert("NewListeningPort", PAGE, "port", T0, T0 + timedelta(seconds=15), {"port": "1"})
    sender.enqueue([state])
    sender.flush(T0)
    assert am.bodies[0][0]["endsAt"] == (T0 + timedelta(seconds=15)).isoformat()


def test_full_queue_drops_the_oldest():
    sender = Sender(AM, "h", RUNBOOKS, post=FakeAlertmanager(), max_queue=3)
    sender.enqueue([alert(n) for n in range(5)])
    assert (sender.pending, sender.dropped) == (3, 2)


def test_rejected_payload_is_dropped_not_retried_forever():
    am = FakeAlertmanager()
    am.fail_with = urllib.error.HTTPError(AM, 400, "bad request", {}, io.BytesIO())  # type: ignore[arg-type]
    sender = Sender(AM, "h", RUNBOOKS, post=am)
    sender.enqueue([alert()])
    assert sender.flush(T0)
    assert (sender.pending, sender.rejected) == (0, 1)


def test_server_error_is_retried():
    am = FakeAlertmanager()
    am.fail_with = urllib.error.HTTPError(AM, 503, "unavailable", {}, io.BytesIO())  # type: ignore[arg-type]
    sender = Sender(AM, "h", RUNBOOKS, post=am)
    sender.enqueue([alert()])
    assert not sender.flush(T0)
    assert sender.pending == 1
