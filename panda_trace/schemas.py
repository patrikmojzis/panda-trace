from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from panda_trace.security import ALL_SCOPES


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class Envelope(BaseModel):
    data: Any
    meta: dict[str, Any] = Field(default_factory=dict)


class CreateOrgRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    owner_agent_name: str = Field(default="owner-agent", min_length=1, max_length=120)


class CreateProjectRequest(BaseModel):
    org_id: str
    name: str = Field(min_length=1, max_length=120)


class CreateSourceRequest(BaseModel):
    project_id: str
    name: str = Field(min_length=1, max_length=120)
    slug: str | None = Field(default=None, min_length=1, max_length=120)


class CreateAgentRequest(BaseModel):
    org_id: str
    name: str = Field(min_length=1, max_length=120)


class CreateApiKeyRequest(BaseModel):
    agent_id: str
    org_id: str
    project_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    scopes: list[str] = Field(min_length=1)
    ip_allowlist: list[str] = Field(default_factory=list)
    expires_at: datetime | None = None

    @field_validator("scopes")
    @classmethod
    def validate_scopes(cls, scopes: list[str]) -> list[str]:
        unknown = sorted(set(scopes) - ALL_SCOPES)
        if unknown:
            raise ValueError(f"Unknown scopes: {', '.join(unknown)}")
        return sorted(set(scopes))

    @field_validator("expires_at")
    @classmethod
    def normalize_expires_at(cls, value: datetime | None) -> datetime | None:
        return ensure_utc(value)


class LogException(BaseModel):
    type: str | None = None
    message: str | None = None
    stacktrace: str | None = None


class CreateAttachmentRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(default="application/octet-stream", min_length=1, max_length=120)
    content_base64: str = Field(min_length=1)


class LogCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp: datetime | None = None
    severity: str
    message: str = Field(min_length=1)
    service: str | None = None
    environment: str | None = None
    trace_id: str | None = None
    span_id: str | None = None
    request_id: str | None = None
    logger: str | None = None
    event: str | None = None
    project_id: str | None = None
    source_id: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    exception: LogException | None = None
    schema_version: int = 1
    idempotency_key: str | None = None

    @field_validator("timestamp")
    @classmethod
    def normalize_timestamp(cls, value: datetime | None) -> datetime | None:
        return ensure_utc(value)


class BatchLogRequest(BaseModel):
    logs: list[LogCreate] = Field(min_length=1)
    idempotency_key: str | None = None


class SearchLogsRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    project_id: str
    from_: datetime = Field(alias="from")
    to: datetime
    query: str | None = None
    severity: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    trace_id: str | None = None
    span_id: str | None = None
    request_id: str | None = None
    logger: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    limit: int = Field(default=100, ge=1)
    cursor: str | None = None
    sort: Literal["timestamp_desc", "timestamp_asc", "received_at_desc"] = "timestamp_desc"

    @field_validator("from_", "to")
    @classmethod
    def normalize_range_datetime(cls, value: datetime) -> datetime:
        normalized = ensure_utc(value)
        assert normalized is not None
        return normalized


class ExportLogsRequest(SearchLogsRequest):
    format: Literal["json", "jsonl"] = "jsonl"


class TailFilter(BaseModel):
    project_id: str
    source_id: str | None = None
    severity: list[str] = Field(default_factory=list)
    query: str | None = None
