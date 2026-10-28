# ADR-007: New listening ports come from a socket snapshot, not logs

Part of the [architecture decisions](README.md).

**Decision:** every 30 s, the detector ([ADR-006](0006-security-detection-with-vector.md)) reads the host's
socket tables and alerts on any listening socket not in an allow-list (`22`, `80`, `443`, and so on, set on the server). The alert
stays firing while the port listens and resolves when it closes.
Loopback-only listeners are ignored by default: they aren't reachable
from outside, and Docker creates them constantly.

**How it sees the host's sockets:** the host's `/proc` is mounted
read-only, and `/host/proc/1/net/tcp` (and `tcp6`) are the tables of the
network namespace of the host's first process: the host's own. So the
container needs neither the host's network nor any capability. (The first
version used the host's network; slice 3 moved Vector onto the compose
network so it can reach Alertmanager and VictoriaMetrics by name.
Checked: as `nobody` with no capabilities, it sees the same listeners as
a host-network container.)

**Why:** nothing logs "a port started listening". Reading `/proc` needs
no tools in the image and no privileges.

**Known gap, in the runbook:** a container port published through
Docker's iptables rules with the userland proxy turned off has no
listening socket on the host. The runbook adds a weekly
`docker ps --format '{{.Ports}}'` check.

**Rejected:**
- *Running `ss -ltn`:* needs `iproute2` in the image for the same data.
- *osquery's `listening_ports` table:* the same data, with a daemon of
  its own and access to the host's processes.
- *Falco:* needs a privileged container or eBPF access.
- *auditd rules on `bind()`:* changes the kernel's audit configuration (a
  security setting) and is very noisy.
- *An outside port scan:* sees only what's open past the firewall, needs
  a second machine, and scanning from a cloud host can breach its terms.
