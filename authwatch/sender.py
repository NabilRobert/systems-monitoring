"""Deliver alerts to Alertmanager, keeping them while it is unreachable."""

import json
import logging
import urllib.error
import urllib.request
from collections import deque
from collections.abc import Callable
from datetime import datetime, timedelta

from authwatch.alerts import Alert

log = logging.getLogger(__name__)

# (url, JSON body) -> raises on failure
Post = Callable[[str, bytes], None]


def http_post(url: str, body: bytes) -> None:
    request = urllib.request.Request(
        url, data=body, method="POST", headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        if response.status >= 300:
            raise OSError(f"Alertmanager answered {response.status}")


class Sender:
    """A bounded queue in front of Alertmanager's API.

    If Alertmanager is down, alerts wait and are retried with exponential
    backoff (up to `max_backoff`). A full queue drops the oldest alert and
    counts it in `dropped`, so a long outage can't exhaust memory.
    """

    def __init__(
        self,
        alertmanager_url: str,
        host: str,
        runbook_base: str,
        post: Post = http_post,
        max_queue: int = 1000,
        max_backoff: timedelta = timedelta(minutes=2),
    ) -> None:
        self._url = alertmanager_url.rstrip("/") + "/api/v2/alerts"
        self._host = host
        self._runbook_base = runbook_base
        self._post = post
        self._queue: deque[Alert] = deque()
        self._max_queue = max_queue
        self._max_backoff = max_backoff
        self._backoff = timedelta(0)
        self._next_try: datetime | None = None
        self.dropped = 0
        self.rejected = 0
        self.sent = 0

    @property
    def pending(self) -> int:
        return len(self._queue)

    def enqueue(self, alerts: list[Alert]) -> None:
        for alert in alerts:
            if len(self._queue) >= self._max_queue:
                self._queue.popleft()
                self.dropped += 1
                log.error("alert queue full: dropped the oldest alert (%d so far)", self.dropped)
            self._queue.append(alert)

    def flush(self, now: datetime) -> bool:
        """Send everything queued. Returns False if Alertmanager was unreachable."""
        if not self._queue or (self._next_try is not None and now < self._next_try):
            return not self._queue
        batch = list(self._queue)
        body = json.dumps([a.payload(self._host, self._runbook_base, now) for a in batch]).encode()
        try:
            self._post(self._url, body)
        except urllib.error.HTTPError as exc:
            if 400 <= exc.code < 500:
                # Alertmanager rejected the alerts themselves: retrying the
                # same body would block the queue for ever.
                for _ in batch:
                    self._queue.popleft()
                self.rejected += len(batch)
                log.error("Alertmanager rejected %d alerts: %s", len(batch), exc)
                return True
            return self._failed(exc, len(batch), now)
        except OSError as exc:
            return self._failed(exc, len(batch), now)
        for _ in batch:
            self._queue.popleft()
        self.sent += len(batch)
        self._backoff = timedelta(0)
        self._next_try = None
        return True

    def _failed(self, exc: OSError, count: int, now: datetime) -> bool:
        self._backoff = min(max(self._backoff * 2, timedelta(seconds=1)), self._max_backoff)
        self._next_try = now + self._backoff
        log.warning(
            "Alertmanager unreachable (%s); %d alerts queued, retry in %s",
            exc,
            count,
            self._backoff,
        )
        return False
