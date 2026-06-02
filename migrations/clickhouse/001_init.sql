CREATE DATABASE IF NOT EXISTS panda_trace;

CREATE TABLE IF NOT EXISTS panda_trace.logs
(
  id String,
  org_id String,
  project_id String,
  source_id String,
  timestamp DateTime('UTC'),
  received_at DateTime('UTC'),
  severity LowCardinality(String),
  service Nullable(String),
  environment Nullable(String),
  trace_id Nullable(String),
  span_id Nullable(String),
  request_id Nullable(String),
  logger Nullable(String),
  event Nullable(String),
  message String,
  exception_type Nullable(String),
  exception_message Nullable(String),
  exception_stacktrace Nullable(String),
  attributes String,
  schema_version UInt16,
  INDEX idx_logs_message_ngram lowerUTF8(message) TYPE ngrambf_v1(4, 8192, 3, 0) GRANULARITY 4,
  INDEX idx_logs_exception_message_ngram lowerUTF8(ifNull(exception_message, '')) TYPE ngrambf_v1(4, 8192, 3, 1) GRANULARITY 4,
  INDEX idx_logs_exception_stacktrace_ngram lowerUTF8(ifNull(exception_stacktrace, '')) TYPE ngrambf_v1(4, 8192, 3, 2) GRANULARITY 4
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(timestamp)
ORDER BY (org_id, project_id, source_id, timestamp, severity)
TTL timestamp + INTERVAL 730 DAY;

ALTER TABLE panda_trace.logs
  ADD INDEX IF NOT EXISTS idx_logs_message_ngram lowerUTF8(message) TYPE ngrambf_v1(4, 8192, 3, 0) GRANULARITY 4;

ALTER TABLE panda_trace.logs
  ADD INDEX IF NOT EXISTS idx_logs_exception_message_ngram lowerUTF8(ifNull(exception_message, '')) TYPE ngrambf_v1(4, 8192, 3, 1) GRANULARITY 4;

ALTER TABLE panda_trace.logs
  ADD INDEX IF NOT EXISTS idx_logs_exception_stacktrace_ngram lowerUTF8(ifNull(exception_stacktrace, '')) TYPE ngrambf_v1(4, 8192, 3, 2) GRANULARITY 4;

CREATE TABLE IF NOT EXISTS panda_trace.audit_logs
(
  id String,
  org_id String,
  action LowCardinality(String),
  agent_id Nullable(String),
  api_key_id Nullable(String),
  project_id Nullable(String),
  source_id Nullable(String),
  ip Nullable(String),
  metadata String,
  created_at DateTime('UTC')
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(created_at)
ORDER BY (org_id, created_at, action)
TTL created_at + INTERVAL 730 DAY;
