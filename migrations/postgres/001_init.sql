CREATE TABLE IF NOT EXISTS orgs (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS projects (
  id TEXT PRIMARY KEY,
  org_id TEXT NOT NULL REFERENCES orgs(id),
  name TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sources (
  id TEXT PRIMARY KEY,
  org_id TEXT NOT NULL REFERENCES orgs(id),
  project_id TEXT NOT NULL REFERENCES projects(id),
  name TEXT NOT NULL,
  slug TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agents (
  id TEXT PRIMARY KEY,
  org_id TEXT NOT NULL REFERENCES orgs(id),
  name TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS api_keys (
  id TEXT PRIMARY KEY,
  agent_id TEXT NOT NULL REFERENCES agents(id),
  org_id TEXT NOT NULL REFERENCES orgs(id),
  secret_salt TEXT NOT NULL,
  secret_digest TEXT NOT NULL,
  secret_iterations INTEGER NOT NULL,
  scopes JSONB NOT NULL,
  project_ids JSONB NOT NULL,
  source_ids JSONB NOT NULL,
  ip_allowlist JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ,
  revoked_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS audit_events (
  id TEXT PRIMARY KEY,
  org_id TEXT NOT NULL REFERENCES orgs(id),
  action TEXT NOT NULL,
  agent_id TEXT,
  api_key_id TEXT,
  project_id TEXT,
  source_id TEXT,
  ip TEXT,
  metadata JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS idempotency_keys (
  api_key_id TEXT NOT NULL REFERENCES api_keys(id),
  idempotency_key TEXT NOT NULL,
  log_id TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (api_key_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS log_attachments (
  id TEXT PRIMARY KEY,
  org_id TEXT NOT NULL REFERENCES orgs(id),
  project_id TEXT NOT NULL REFERENCES projects(id),
  source_id TEXT NOT NULL REFERENCES sources(id),
  log_id TEXT NOT NULL,
  filename TEXT NOT NULL,
  content_type TEXT NOT NULL,
  size_bytes BIGINT NOT NULL,
  storage_backend TEXT NOT NULL,
  object_key TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_projects_org ON projects(org_id);
CREATE INDEX IF NOT EXISTS idx_sources_project ON sources(project_id);
CREATE INDEX IF NOT EXISTS idx_api_keys_agent ON api_keys(agent_id);
CREATE INDEX IF NOT EXISTS idx_audit_events_org_created ON audit_events(org_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_log_attachments_log_id ON log_attachments(log_id);
