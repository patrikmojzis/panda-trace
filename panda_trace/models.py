from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from panda_trace.security import SecretHash


@dataclass
class Org:
    id: str
    name: str
    created_at: datetime


@dataclass
class Project:
    id: str
    org_id: str
    name: str
    created_at: datetime


@dataclass
class Source:
    id: str
    org_id: str
    project_id: str
    name: str
    slug: str
    created_at: datetime


@dataclass
class Agent:
    id: str
    org_id: str
    name: str
    created_at: datetime


@dataclass
class ApiKeyRecord:
    id: str
    agent_id: str
    org_id: str
    secret_hash: SecretHash
    scopes: list[str]
    project_ids: list[str]
    source_ids: list[str]
    ip_allowlist: list[str]
    created_at: datetime
    expires_at: datetime | None
    revoked_at: datetime | None = None


@dataclass
class LogRecord:
    id: str
    org_id: str
    project_id: str
    source_id: str
    timestamp: datetime
    received_at: datetime
    severity: str
    message: str
    service: str | None = None
    environment: str | None = None
    trace_id: str | None = None
    span_id: str | None = None
    request_id: str | None = None
    logger: str | None = None
    event: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    exception: dict[str, Any] | None = None
    schema_version: int = 1


@dataclass
class AuditEvent:
    id: str
    org_id: str
    action: str
    agent_id: str | None
    api_key_id: str | None
    project_id: str | None
    source_id: str | None
    ip: str | None
    metadata: dict[str, Any]
    created_at: datetime


@dataclass
class AttachmentRecord:
    id: str
    org_id: str
    project_id: str
    source_id: str
    log_id: str
    filename: str
    content_type: str
    size_bytes: int
    storage_backend: str
    object_key: str
    created_at: datetime


@dataclass
class AuthContext:
    key: ApiKeyRecord
    agent: Agent
    client_ip: str | None
