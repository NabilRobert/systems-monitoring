# HostMemoryLow, OutOfMemoryKill

**Means:**
- **HostMemoryLow:** under 10% of the server's memory has been available
  for 5 minutes. The next container to grow may be killed.
- **OutOfMemoryKill:** the kernel killed a process for lack of memory in
  the last 10 minutes. Usually a container reached its `mem_limit`.

## Check

1. Which container: `docker ps --format '{{.Names}} {{.Status}}'` (look for
   a recent restart) and
   `docker inspect --format '{{.Name}} {{.State.OOMKilled}}' $(docker ps -aq)`.
2. The kernel's record: `sudo journalctl -k --since "-30min" | grep -i -E "oom|killed process"`.
3. Who is using memory now: `docker stats --no-stream`.
4. Per-container history: the `host_cgroup_memory_current_bytes` series in
   VictoriaMetrics (`http://127.0.0.1:8428/vmui` through an SSH tunnel).

## What to do

- A container at its cap after a change: the change is the suspect.
  Roll back, or raise the cap *only* if the new size is measured and
  still fits the server (the caps add up; [ADR-011](../adr/0011-memory-budget.md)).
- The whole server short: stop what isn't needed, and look at what grew.

## Over when

The ✅ Resolved message arrives (OutOfMemoryKill clears 10 minutes after
the last kill).
