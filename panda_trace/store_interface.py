from __future__ import annotations

from typing import Any, AsyncIterator, Protocol

from panda_trace.config import Settings
from panda_trace.schemas import LogCreate, SearchLogsRequest, TailFilter
from panda_trace.models import (
    Agent,
    ApiKeyRecord,
    AttachmentRecord,
    AuditEvent,
    AuthContext,
    LogRecord,
    Org,
    Project,
    Source,
)


class LogStore(Protocol):
    async def ready(self) -> dict[str, Any]: ...

    async def create_org_bootstrap(
        self, name: str, owner_agent_name: str
    ) -> tuple[Org, Agent, ApiKeyRecord, str]: ...

    async def authenticate(self, secret: str) -> ApiKeyRecord | None: ...

    async def get_agent(self, agent_id: str) -> Agent: ...

    async def create_project(self, auth: AuthContext, org_id: str, name: str) -> Project: ...

    async def create_source(
        self, auth: AuthContext, project_id: str, name: str, slug: str | None
    ) -> Source: ...

    async def list_sources(self, auth: AuthContext, project_id: str | None) -> list[Source]: ...

    async def create_agent(self, auth: AuthContext, org_id: str, name: str) -> Agent: ...

    async def create_api_key(
        self,
        auth: AuthContext,
        *,
        agent_id: str,
        org_id: str,
        project_ids: list[str],
        source_ids: list[str],
        scopes: list[str],
        ip_allowlist: list[str],
        expires_at: Any,
    ) -> tuple[ApiKeyRecord, str]: ...

    async def revoke_api_key(self, auth: AuthContext, key_id: str) -> ApiKeyRecord: ...

    async def ingest_log(
        self,
        auth: AuthContext,
        log: LogCreate,
        *,
        settings: Settings,
        idempotency_key: str | None = None,
    ) -> LogRecord: ...

    async def get_log(self, auth: AuthContext, log_id: str) -> LogRecord: ...

    async def add_attachment(
        self,
        auth: AuthContext,
        log_id: str,
        *,
        filename: str,
        content_type: str,
        content: bytes,
    ) -> AttachmentRecord: ...

    async def list_attachments(self, auth: AuthContext, log_id: str) -> list[AttachmentRecord]: ...

    async def get_attachment(
        self, auth: AuthContext, log_id: str, attachment_id: str
    ) -> tuple[AttachmentRecord, bytes]: ...

    async def search_logs(
        self,
        auth: AuthContext,
        request: SearchLogsRequest,
        *,
        settings: Settings,
        audit_action: str = "logs.search",
        audit: bool = True,
        limit_override: int | None = None,
    ) -> tuple[list[LogRecord], str | None, int]: ...

    async def list_audit_logs(self, auth: AuthContext, org_id: str | None = None) -> list[AuditEvent]: ...

    async def record_audit(
        self,
        auth: AuthContext,
        action: str,
        *,
        project_id: str | None,
        source_id: str | None,
        metadata: dict[str, Any],
    ) -> None: ...

    async def ensure_tail_allowed(
        self, auth: AuthContext, project_id: str, source_id: str | None
    ) -> None: ...

    async def acquire_tail_stream(self, auth: AuthContext, settings: Settings) -> None: ...

    async def release_tail_stream(self, auth: AuthContext) -> None: ...

    async def tail(self, filter_: TailFilter) -> AsyncIterator[LogRecord]: ...
