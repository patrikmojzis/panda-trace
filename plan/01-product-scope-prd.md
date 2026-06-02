# PRD: Product Scope

## Goal

Build Panda Trace as a high-quality logs API for AI agents. Agents should be able to ingest logs, search logs, tail live logs, export logs, and inspect audit trails through a secure public API.

## Primary Users

- AI agents that write logs.
- AI agents that read logs for debugging and analysis.
- Project/admin agents that manage sources, keys, and access.
- Human maintainers who operate the service through scripts or API clients.

## Core Jobs

- Store structured logs from multiple projects.
- Search logs by time, severity, source, trace, request, text, and attributes.
- Tail live logs with server-sent events.
- Export logs as JSON/JSONL.
- Enforce tenant boundaries between orgs, projects, sources, and agents.
- Audit all sensitive actions, especially reads and key management.

## Non-Goals For V1

- No human dashboard.
- No billing system.
- No alerting workflow beyond searchable logs and audit logs.
- No raw SQL, Mongo, or ClickHouse query passthrough.
- No mandatory secret redaction yet, but leave a redaction hook.

## Success Criteria

- A new agent can read `/llms.txt`, inspect OpenAPI, create a valid request, and ingest/search logs without human handholding.
- A compromised write-only key cannot read logs.
- A reader for one project cannot search another project.
- Searches require bounded time ranges and cannot accidentally scan everything forever.
- Logs can be retained for two years by default, configurable by environment.

## Think While Implementing

Use this space for notes while building:

- Unexpected user/agent behavior:
- Painful API shape:
- Ambiguous naming:
- Operational risk:

