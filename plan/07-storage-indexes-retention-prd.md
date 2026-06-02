# PRD: Storage, Indexes, Retention

## Goal

Store control-plane data transactionally and store logs in a time-series/analytical layout that can survive serious volume.

## Postgres Tables

Minimum control-plane tables:

```text
orgs
projects
sources
agents
agent_project_memberships
api_keys
quotas
ip_allowlists
audit_events
```

## ClickHouse Tables

Minimum log-plane tables:

```text
logs
audit_logs
```

Optional materialized views:

```text
log_facets_by_hour
log_counts_by_severity
log_counts_by_source
```

## Logs Columns

Store these as first-class columns:

```text
id
org_id
project_id
source_id
timestamp
received_at
severity
service
environment
trace_id
span_id
request_id
logger
message
exception_type
exception_message
exception_stacktrace
attributes
schema_version
```

## Index Direction

Primary access pattern:

```text
tenant/project/source + time range + severity/text/trace filters
```

ClickHouse ordering should favor tenant isolation and time-bound scans. Full-text indexes should start on `message`; add exception text indexes when the cost is acceptable.

## Retention

Default retention:

```env
LOG_RETENTION_DAYS=730
```

Retention must be configurable. Prefer ClickHouse TTL for logs. Keep audit retention configurable separately if needed later.

## Acceptance Checks

- Logs can be queried efficiently by project/source/time.
- Full-text search works on `message`.
- Retention is controlled by environment config.
- Control-plane writes stay in Postgres, not ClickHouse.

## Think While Implementing

- ClickHouse `ORDER BY` shape:
- Partition granularity:
- JSON/Map attributes representation:
- Facet materialized view value:

