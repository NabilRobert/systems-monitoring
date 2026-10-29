# ADR-012: Frameworks and plain code

Part of the [architecture decisions](README.md).

**Decision:** the stack Arthur already uses, so this looks like the other
projects:
- **Python tooling:** uv, ruff, pyright (strict), pytest.
- **`slo-check` (slice 5):** Typer for its command line, pydantic-settings
  for its settings, SQLAlchemy 2 for the read-only queries, httpx and
  tenacity to post to Alertmanager with retries.
- **Everything else is configuration** of existing tools (Alertmanager,
  Vector, later VictoriaMetrics and the exporters), tested by running
  them.

**Plain code, on purpose:** the Telegram stand-in in `e2e/` is a 50-line
standard-library HTTP server used only by tests; a web framework would be
heavier than the problem.
