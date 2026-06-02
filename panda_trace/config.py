from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import quote


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return int(raw)


def _postgres_dsn_from_env() -> str:
    raw = os.getenv("POSTGRES_DSN")
    if raw:
        return raw
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = _int_env("POSTGRES_PORT", 5432)
    database = os.getenv("POSTGRES_DB", "panda_trace")
    user = quote(os.getenv("POSTGRES_USER", "panda"), safe="")
    password = quote(os.getenv("POSTGRES_PASSWORD", "panda"), safe="")
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"


@dataclass(frozen=True)
class Settings:
    env: str = "dev"
    store_backend: str = "memory"
    rate_limit_backend: str = "memory"
    tail_backend: str = "memory"
    redaction_mode: str = "disabled"
    require_https: bool = False
    bootstrap_token: str | None = None
    public_base_url: str = "http://localhost:8000"
    log_retention_days: int = 730
    max_log_bytes: int = 262_144
    max_batch_bytes: int = 10_485_760
    max_batch_items: int = 1000
    max_attachment_bytes: int = 52_428_800
    max_request_bytes: int = 73_400_320
    max_search_range_days: int = 31
    max_page_size: int = 500
    max_export_rows: int = 10_000
    rate_limit_per_minute: int = 600
    max_key_daily_ingest_bytes: int = 268_435_456
    max_project_daily_ingest_bytes: int = 1_073_741_824
    max_agent_daily_read_queries: int = 10_000
    max_concurrent_tail_streams: int = 25
    tail_idle_timeout_seconds: int = 300
    allow_docs_without_auth: bool = True

    postgres_dsn: str = "postgresql://panda:panda@localhost:5432/panda_trace"
    clickhouse_host: str = "localhost"
    clickhouse_port: int = 8123
    clickhouse_database: str = "panda_trace"
    clickhouse_user: str = "default"
    clickhouse_password: str = ""
    redis_url: str = "redis://localhost:6379/0"
    minio_endpoint: str = "http://localhost:9000"
    minio_access_key: str = "panda"
    minio_secret_key: str = "panda-secret"
    minio_bucket: str = "panda-trace"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            env=os.getenv("PANDA_TRACE_ENV", "dev"),
            store_backend=os.getenv("PANDA_TRACE_STORE", "memory"),
            rate_limit_backend=os.getenv("RATE_LIMIT_BACKEND", "memory"),
            tail_backend=os.getenv("TAIL_BACKEND", "memory"),
            redaction_mode=os.getenv("REDACTION_MODE", "disabled"),
            require_https=os.getenv("REQUIRE_HTTPS", "false").lower() in {"1", "true", "yes"},
            bootstrap_token=os.getenv("BOOTSTRAP_TOKEN") or None,
            public_base_url=os.getenv("PUBLIC_BASE_URL", "http://localhost:8000"),
            log_retention_days=_int_env("LOG_RETENTION_DAYS", 730),
            max_log_bytes=_int_env("MAX_LOG_BYTES", 262_144),
            max_batch_bytes=_int_env("MAX_BATCH_BYTES", 10_485_760),
            max_batch_items=_int_env("MAX_BATCH_ITEMS", 1000),
            max_attachment_bytes=_int_env("MAX_ATTACHMENT_BYTES", 52_428_800),
            max_request_bytes=_int_env("MAX_REQUEST_BYTES", 73_400_320),
            max_search_range_days=_int_env("MAX_SEARCH_RANGE_DAYS", 31),
            max_page_size=_int_env("MAX_PAGE_SIZE", 500),
            max_export_rows=_int_env("MAX_EXPORT_ROWS", 10_000),
            rate_limit_per_minute=_int_env("RATE_LIMIT_PER_MINUTE", 600),
            max_key_daily_ingest_bytes=_int_env("MAX_KEY_DAILY_INGEST_BYTES", 268_435_456),
            max_project_daily_ingest_bytes=_int_env("MAX_PROJECT_DAILY_INGEST_BYTES", 1_073_741_824),
            max_agent_daily_read_queries=_int_env("MAX_AGENT_DAILY_READ_QUERIES", 10_000),
            max_concurrent_tail_streams=_int_env("MAX_CONCURRENT_TAIL_STREAMS", 25),
            tail_idle_timeout_seconds=_int_env("TAIL_IDLE_TIMEOUT_SECONDS", 300),
            allow_docs_without_auth=os.getenv("ALLOW_DOCS_WITHOUT_AUTH", "true").lower()
            in {"1", "true", "yes"},
            postgres_dsn=_postgres_dsn_from_env(),
            clickhouse_host=os.getenv("CLICKHOUSE_HOST", "localhost"),
            clickhouse_port=_int_env("CLICKHOUSE_PORT", 8123),
            clickhouse_database=os.getenv("CLICKHOUSE_DATABASE", "panda_trace"),
            clickhouse_user=os.getenv("CLICKHOUSE_USER", "default"),
            clickhouse_password=os.getenv("CLICKHOUSE_PASSWORD", ""),
            redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
            minio_endpoint=os.getenv("MINIO_ENDPOINT", "http://localhost:9000"),
            minio_access_key=os.getenv("MINIO_ACCESS_KEY", "panda"),
            minio_secret_key=os.getenv("MINIO_SECRET_KEY", "panda-secret"),
            minio_bucket=os.getenv("MINIO_BUCKET", "panda-trace"),
        )
