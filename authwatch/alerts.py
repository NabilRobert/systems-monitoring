"""The alert shape sent to Alertmanager, and the alert names."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta

PAGE = "page"
TICKET = "ticket"

# How long a one-shot event stays "firing" in Alertmanager. Long enough to
# be grouped and sent; short enough that it is gone by the next morning.
EVENT_TTL = timedelta(minutes=5)
_MIN_LEFT = timedelta(minutes=1)

# Each alert name has a runbook at docs/runbooks/<slug>.md.
RUNBOOKS = {
    "SSHLogin": "ssh-login",
    "SudoCommand": "sudo-command",
    "SudoAuthFailure": "sudo-auth-failure",
    "SSHFailedLoginBurst": "ssh-failed-logins",
    "SSHFailedLoginFlood": "ssh-failed-logins",
    "NewListeningPort": "new-listening-port",
    "AuthwatchTest": "authwatch-test",
}


@dataclass(frozen=True, slots=True)
class Alert:
    name: str
    severity: str
    summary: str
    starts_at: datetime
    ends_at: datetime
    labels: dict[str, str] = field(default_factory=dict[str, str])

    def payload(self, host: str, runbook_base: str, now: datetime) -> dict[str, object]:
        """One element of the list Alertmanager's POST /api/v2/alerts takes.

        A one-shot event that waited in the queue until its end time was
        close would reach Alertmanager already resolved and never be sent,
        so its end time is moved forward. A state (no `event_id`) is re-sent
        on every check, so its short end time is kept: that is what lets it
        resolve soon after it stops being true.
        """
        ends_at = self.ends_at
        if "event_id" in self.labels and ends_at < now + _MIN_LEFT:
            ends_at = now + EVENT_TTL
        return {
            "labels": {
                "alertname": self.name,
                "severity": self.severity,
                "host": host,
                **self.labels,
            },
            "annotations": {
                "summary": self.summary,
                "runbook_url": f"{runbook_base.rstrip('/')}/{RUNBOOKS[self.name]}.md",
            },
            "startsAt": _rfc3339(self.starts_at),
            "endsAt": _rfc3339(ends_at),
        }


def _rfc3339(ts: datetime) -> str:
    return ts.isoformat(timespec="seconds")
