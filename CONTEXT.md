# Context

## Terms

### Agent

An agent is a user principal. API keys belong to agents, and permissions are evaluated as agent access to orgs, projects, sources, and actions.

- Use when: naming auth, key, quota, audit, or permission behaviour.
- Avoid when: referring to a log producer; that is a Source.
- Code: `panda_trace/models.py`, `panda_trace/auth.py`, `panda_trace/access.py`

### Org

An org is the top-level tenant container for projects, sources, agents, keys, logs, attachments, and audit events.

- Use when: naming tenant-wide access and bootstrap behaviour.
- Avoid when: referring to an individual application or workspace; that is a Project.
- Code: `panda_trace/models.py`, `panda_trace/store_interface.py`

### Project

A project is a product, app, or workspace under an org. Logs are searched and exported within a project.

- Use when: naming search scope, quotas, and project-level permissions.
- Avoid when: referring to the concrete log producer; that is a Source.
- Code: `panda_trace/models.py`, `panda_trace/log_query.py`, `panda_trace/access.py`

### Source

A source is a log producer inside a project, such as an API, worker, or deployment environment.

- Use when: naming write scoping, source spoofing checks, and tail filters.
- Avoid when: referring to the agent that reads or writes through an API key.
- Code: `panda_trace/models.py`, `panda_trace/access.py`, `panda_trace/log_query.py`

### Log

A log is a structured event stored for a source, with severity, message, timestamps, trace fields, attributes, and optional exception data.

- Use when: naming ingestion, search, read, export, tail, and storage row behaviour.
- Avoid when: referring to audit records about API activity; those are Audit Events.
- Code: `panda_trace/models.py`, `panda_trace/log_codecs.py`, `panda_trace/log_query.py`

### Audit Event

An audit event records API activity by an agent and key, optionally tied to a project or source.

- Use when: naming audit log persistence, mirroring, and read behaviour.
- Avoid when: referring to product logs ingested by agents.
- Code: `panda_trace/models.py`, `panda_trace/persistent_store.py`, `panda_trace/row_codecs.py`

### Attachment

An attachment is a blob stored beside a log. Attachments are not indexed as log text.

- Use when: naming blob upload, metadata listing, and download behaviour.
- Avoid when: referring to log attributes or exception fields.
- Code: `panda_trace/models.py`, `panda_trace/payloads.py`, `panda_trace/representations.py`

### Log Query

A log query is the bounded, structured retrieval request used by search, export, and tail matching rules.

- Use when: naming severity normalization, cursor handling, time-range validation, and filter matching.
- Avoid when: referring to raw SQL or database-native query syntax; Panda Trace does not expose those.
- Code: `panda_trace/log_query.py`

### Tail

Tail is the server-sent event flow for streaming matching logs as they arrive.

- Use when: naming subscriber management, Redis pubsub, stream limits, and SSE behaviour.
- Avoid when: referring to paginated search or export.
- Code: `panda_trace/tail.py`, `panda_trace/main.py`

### Store Adapter

A store adapter satisfies the `LogStore` interface using a concrete backend, currently memory or Postgres plus ClickHouse plus Redis plus MinIO.

- Use when: naming backend selection, persistence seams, and tests that swap storage.
- Avoid when: naming product concepts like Org, Project, Source, or Log.
- Code: `panda_trace/store_interface.py`, `panda_trace/store.py`, `panda_trace/persistent_store.py`, `panda_trace/store_factory.py`
