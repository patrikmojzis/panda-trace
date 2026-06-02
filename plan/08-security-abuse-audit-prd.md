# PRD: Security, Abuse Controls, Audit

## Goal

Expose Panda Trace publicly without letting bad clients drain data, scan forever, or melt the host.

## Security Baseline

- Require HTTPS in production.
- Authenticate every non-health/docs endpoint.
- Hash API keys at rest.
- Enforce key expiration and revocation.
- Enforce scoped access on every read and write.
- Never trust client-provided tenant identity without checking the key.
- Disable browser CORS by default unless explicitly configured.

## Abuse Controls

Use Redis-backed controls:

- Per-key request rate limits.
- Per-key ingest byte limits.
- Per-project daily ingest quota.
- Per-agent read query quota.
- Max query time range.
- Max page size.
- Max export size.
- Max concurrent tail streams.
- Optional IP allowlists.

## Audit Events

Audit at least:

```text
logs.search
logs.read
logs.tail.start
logs.export
api_keys.create
api_keys.revoke
sources.create
agents.create
permission.change
quota.change
```

Audit event shape:

```json
{
  "kind": "audit",
  "action": "logs.search",
  "agent_id": "agent_123",
  "project_id": "proj_123",
  "ip": "1.2.3.4",
  "query_summary": {},
  "result_count": 42
}
```

Store audit logs in Panda Trace too, with a separate kind/table so product logs and audit logs do not get confused.

## Secret Redaction

No automatic redaction in v1, but create a clean hook in the ingestion pipeline:

```text
raw request -> validation -> optional redaction -> normalize -> store
```

Default redaction mode can be disabled.

## Acceptance Checks

- Read actions generate audit events.
- Rate limits return clear errors.
- IP allowlist failures are denied before expensive work.
- Oversized searches/exports cannot bypass caps.

## Think While Implementing

- Rate limit library:
- Audit write failure behavior:
- Redaction hook interface:
- Production TLS assumptions:

