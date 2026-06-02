# Tenancy

Panda Trace uses this hierarchy:

```text
org
  project
    source
      logs

agent
  api keys
```

Rules:

- API keys belong to agents.
- API keys are scoped to one org.
- Project and source scopes narrow what a key can access.
- Server-side auth decides tenancy. Client-provided IDs never override key permissions.
- Read, search, tail, and export actions are audited.

