from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from panda_trace.access import (
    assert_log_read_allowed,
    assert_log_write_allowed,
    project_allowed,
    require_auth_org,
    source_allowed,
)
from panda_trace.config import Settings
from panda_trace.errors import bad_request, not_found, permission_denied, rate_limited
from panda_trace.log_query import (
    decode_cursor,
    encode_cursor,
    normalize_requested_severities,
    normalize_severity,
    record_matches_search,
    validate_search_time_range,
)
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
from panda_trace.payloads import log_payload_size
from panda_trace.schemas import LogCreate, SearchLogsRequest, TailFilter, utc_now
from panda_trace.security import (
    ALL_SCOPES,
    extract_key_id,
    hash_secret,
    make_api_key_secret,
    verify_secret,
)
from panda_trace.tail import TailHub


def _id(prefix: str, counter: int) -> str:
    return f"{prefix}_{counter:08d}"


class InMemoryStore:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._counters: dict[str, int] = {}
        self.orgs: dict[str, Org] = {}
        self.projects: dict[str, Project] = {}
        self.sources: dict[str, Source] = {}
        self.agents: dict[str, Agent] = {}
        self.api_keys: dict[str, ApiKeyRecord] = {}
        self.logs: dict[str, LogRecord] = {}
        self.attachments: dict[str, list[AttachmentRecord]] = {}
        self.attachment_bytes: dict[str, bytes] = {}
        self.audit_events: list[AuditEvent] = []
        self.idempotency: dict[tuple[str, str], str] = {}
        self.quota_counters: dict[str, int] = {}
        self.tail_hub = TailHub()

    async def ready(self) -> dict[str, Any]:
        return {"store": "memory", "status": "ready"}

    def _next_id(self, prefix: str) -> str:
        self._counters[prefix] = self._counters.get(prefix, 0) + 1
        return _id(prefix, self._counters[prefix])

    async def create_org_bootstrap(self, name: str, owner_agent_name: str) -> tuple[Org, Agent, ApiKeyRecord, str]:
        async with self._lock:
            now = utc_now()
            org = Org(id=self._next_id("org"), name=name, created_at=now)
            agent = Agent(id=self._next_id("agent"), org_id=org.id, name=owner_agent_name, created_at=now)
            key_id = self._next_id("key")
            secret = make_api_key_secret(key_id)
            key = ApiKeyRecord(
                id=key_id,
                agent_id=agent.id,
                org_id=org.id,
                secret_hash=hash_secret(secret),
                scopes=sorted(ALL_SCOPES),
                project_ids=[],
                source_ids=[],
                ip_allowlist=[],
                created_at=now,
                expires_at=None,
            )
            self.orgs[org.id] = org
            self.agents[agent.id] = agent
            self.api_keys[key.id] = key
            self._audit_unlocked(
                "orgs.create",
                org_id=org.id,
                agent_id=agent.id,
                api_key_id=key.id,
                project_id=None,
                source_id=None,
                ip=None,
                metadata={"bootstrap": True},
            )
            return org, agent, key, secret

    async def authenticate(self, secret: str) -> ApiKeyRecord | None:
        key_id = extract_key_id(secret)
        if not key_id:
            return None
        key = self.api_keys.get(key_id)
        if key is None:
            return None
        if not verify_secret(secret, key.secret_hash):
            return None
        return key

    async def get_agent(self, agent_id: str) -> Agent:
        agent = self.agents.get(agent_id)
        if not agent:
            raise not_found("Agent")
        return agent

    async def create_project(self, auth: AuthContext, org_id: str, name: str) -> Project:
        self._require_org(auth, org_id)
        async with self._lock:
            project = Project(id=self._next_id("proj"), org_id=org_id, name=name, created_at=utc_now())
            self.projects[project.id] = project
            self._audit_unlocked(
                "projects.create",
                org_id=org_id,
                agent_id=auth.agent.id,
                api_key_id=auth.key.id,
                project_id=project.id,
                source_id=None,
                ip=auth.client_ip,
                metadata={"name": name},
            )
            return project

    async def create_source(self, auth: AuthContext, project_id: str, name: str, slug: str | None) -> Source:
        project = self._get_project_for_key(auth.key, project_id)
        async with self._lock:
            source = Source(
                id=self._next_id("src"),
                org_id=project.org_id,
                project_id=project.id,
                name=name,
                slug=slug or name.lower().replace(" ", "-"),
                created_at=utc_now(),
            )
            self.sources[source.id] = source
            self._audit_unlocked(
                "sources.create",
                org_id=project.org_id,
                agent_id=auth.agent.id,
                api_key_id=auth.key.id,
                project_id=project.id,
                source_id=source.id,
                ip=auth.client_ip,
                metadata={"name": name, "slug": source.slug},
            )
            return source

    async def list_sources(self, auth: AuthContext, project_id: str | None) -> list[Source]:
        sources = list(self.sources.values())
        if project_id:
            self._get_project_for_key(auth.key, project_id)
            sources = [source for source in sources if source.project_id == project_id]
        else:
            sources = [source for source in sources if source.org_id == auth.key.org_id]
        return [source for source in sources if self._source_allowed(auth.key, source.id)]

    async def create_agent(self, auth: AuthContext, org_id: str, name: str) -> Agent:
        self._require_org(auth, org_id)
        async with self._lock:
            agent = Agent(id=self._next_id("agent"), org_id=org_id, name=name, created_at=utc_now())
            self.agents[agent.id] = agent
            self._audit_unlocked(
                "agents.create",
                org_id=org_id,
                agent_id=auth.agent.id,
                api_key_id=auth.key.id,
                project_id=None,
                source_id=None,
                ip=auth.client_ip,
                metadata={"created_agent_id": agent.id, "name": name},
            )
            return agent

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
        expires_at: datetime | None,
    ) -> tuple[ApiKeyRecord, str]:
        self._require_org(auth, org_id)
        target_agent = await self.get_agent(agent_id)
        if target_agent.org_id != org_id:
            raise permission_denied("Cannot create a key for an agent in another org.")
        for project_id in project_ids:
            self._get_project_for_key(auth.key, project_id)
        for source_id in source_ids:
            self._get_source_for_key(auth.key, source_id)
        async with self._lock:
            key_id = self._next_id("key")
            secret = make_api_key_secret(key_id)
            key = ApiKeyRecord(
                id=key_id,
                agent_id=agent_id,
                org_id=org_id,
                secret_hash=hash_secret(secret),
                scopes=sorted(set(scopes)),
                project_ids=sorted(set(project_ids)),
                source_ids=sorted(set(source_ids)),
                ip_allowlist=ip_allowlist,
                created_at=utc_now(),
                expires_at=expires_at,
            )
            self.api_keys[key.id] = key
            self._audit_unlocked(
                "api_keys.create",
                org_id=org_id,
                agent_id=auth.agent.id,
                api_key_id=auth.key.id,
                project_id=None,
                source_id=None,
                ip=auth.client_ip,
                metadata={"created_key_id": key.id, "target_agent_id": agent_id, "scopes": key.scopes},
            )
            return key, secret

    async def revoke_api_key(self, auth: AuthContext, key_id: str) -> ApiKeyRecord:
        async with self._lock:
            key = self.api_keys.get(key_id)
            if not key or key.org_id != auth.key.org_id:
                raise not_found("API key")
            key.revoked_at = utc_now()
            self._audit_unlocked(
                "api_keys.revoke",
                org_id=auth.key.org_id,
                agent_id=auth.agent.id,
                api_key_id=auth.key.id,
                project_id=None,
                source_id=None,
                ip=auth.client_ip,
                metadata={"revoked_key_id": key_id},
            )
            return key

    async def ingest_log(
        self,
        auth: AuthContext,
        log: LogCreate,
        *,
        settings: Settings,
        idempotency_key: str | None = None,
    ) -> LogRecord:
        idem = idempotency_key or log.idempotency_key
        if idem:
            existing_id = self.idempotency.get((auth.key.id, idem))
            if existing_id and existing_id in self.logs:
                return self.logs[existing_id]
        project, source = self._resolve_project_source(auth.key, log.project_id, log.source_id)
        severity = normalize_severity(log.severity)
        payload_size = log_payload_size(log)
        self._reserve_key_ingest_quota(
            auth.key.id,
            payload_size,
            limit=settings.max_key_daily_ingest_bytes,
        )
        self._reserve_project_ingest_quota(
            project.id,
            payload_size,
            limit=settings.max_project_daily_ingest_bytes,
        )
        received_at = utc_now()
        record = LogRecord(
            id=self._next_id("log"),
            org_id=auth.key.org_id,
            project_id=project.id,
            source_id=source.id,
            timestamp=log.timestamp or received_at,
            received_at=received_at,
            severity=severity,
            message=log.message,
            service=log.service,
            environment=log.environment,
            trace_id=log.trace_id,
            span_id=log.span_id,
            request_id=log.request_id,
            logger=log.logger,
            event=log.event,
            attributes=log.attributes,
            exception=log.exception.model_dump(exclude_none=True) if log.exception else None,
            schema_version=log.schema_version,
        )
        async with self._lock:
            self.logs[record.id] = record
            if idem:
                self.idempotency[(auth.key.id, idem)] = record.id
            self._audit_unlocked(
                "logs.write",
                org_id=auth.key.org_id,
                agent_id=auth.agent.id,
                api_key_id=auth.key.id,
                project_id=record.project_id,
                source_id=record.source_id,
                ip=auth.client_ip,
                metadata={"log_id": record.id, "severity": severity},
            )
        await self._publish(record)
        return record

    async def get_log(self, auth: AuthContext, log_id: str) -> LogRecord:
        record = self.logs.get(log_id)
        if not record:
            raise not_found("Log")
        self._assert_log_read_allowed(auth.key, record)
        await self.record_audit(
            auth,
            "logs.read",
            project_id=record.project_id,
            source_id=record.source_id,
            metadata={"log_id": log_id},
        )
        return record

    async def add_attachment(
        self,
        auth: AuthContext,
        log_id: str,
        *,
        filename: str,
        content_type: str,
        content: bytes,
    ) -> AttachmentRecord:
        record = self.logs.get(log_id)
        if not record:
            raise not_found("Log")
        self._assert_log_write_allowed(auth.key, record)
        attachment = AttachmentRecord(
            id=self._next_id("att"),
            org_id=record.org_id,
            project_id=record.project_id,
            source_id=record.source_id,
            log_id=record.id,
            filename=filename,
            content_type=content_type,
            size_bytes=len(content),
            storage_backend="memory",
            object_key=f"memory://{record.id}/{filename}",
            created_at=utc_now(),
        )
        async with self._lock:
            self.attachments.setdefault(log_id, []).append(attachment)
            self.attachment_bytes[attachment.id] = content
            self._audit_unlocked(
                "log_attachments.create",
                org_id=auth.key.org_id,
                agent_id=auth.agent.id,
                api_key_id=auth.key.id,
                project_id=record.project_id,
                source_id=record.source_id,
                ip=auth.client_ip,
                metadata={
                    "log_id": log_id,
                    "attachment_id": attachment.id,
                    "filename": filename,
                    "size_bytes": len(content),
                },
            )
        return attachment

    async def list_attachments(self, auth: AuthContext, log_id: str) -> list[AttachmentRecord]:
        record = self.logs.get(log_id)
        if not record:
            raise not_found("Log")
        self._assert_log_read_allowed(auth.key, record)
        await self.record_audit(
            auth,
            "log_attachments.list",
            project_id=record.project_id,
            source_id=record.source_id,
            metadata={"log_id": log_id},
        )
        return list(self.attachments.get(log_id, []))

    async def get_attachment(
        self, auth: AuthContext, log_id: str, attachment_id: str
    ) -> tuple[AttachmentRecord, bytes]:
        record = self.logs.get(log_id)
        if not record:
            raise not_found("Log")
        self._assert_log_read_allowed(auth.key, record)
        attachment = next(
            (item for item in self.attachments.get(log_id, []) if item.id == attachment_id),
            None,
        )
        if attachment is None:
            raise not_found("Attachment")
        content = self.attachment_bytes.get(attachment.id)
        if content is None:
            raise not_found("Attachment content")
        await self.record_audit(
            auth,
            "log_attachments.read",
            project_id=record.project_id,
            source_id=record.source_id,
            metadata={
                "log_id": log_id,
                "attachment_id": attachment.id,
                "filename": attachment.filename,
                "size_bytes": attachment.size_bytes,
            },
        )
        return attachment, content

    async def search_logs(
        self,
        auth: AuthContext,
        request: SearchLogsRequest,
        *,
        settings: Settings,
        audit_action: str = "logs.search",
        audit: bool = True,
        limit_override: int | None = None,
    ) -> tuple[list[LogRecord], str | None, int]:
        validate_search_time_range(request, settings)
        project = self._get_project_for_key(auth.key, request.project_id)
        self._reserve_agent_read_quota(
            auth.agent.id,
            limit=settings.max_agent_daily_read_queries,
        )
        if limit_override is None:
            limit = min(request.limit, settings.max_page_size)
        else:
            limit = min(limit_override, settings.max_export_rows)
        offset = decode_cursor(request.cursor)

        severities = normalize_requested_severities(request)
        requested_sources = set(request.sources)
        for source_id in requested_sources:
            source = self._get_source_for_key(auth.key, source_id)
            if source.project_id != project.id:
                raise permission_denied("Source does not belong to the requested project.")

        records = [
            record
            for record in self.logs.values()
            if self._matches_search(auth.key, record, request, severities, requested_sources)
        ]
        reverse = request.sort in {"timestamp_desc", "received_at_desc"}
        key_name = "received_at" if request.sort == "received_at_desc" else "timestamp"
        records.sort(key=lambda record: getattr(record, key_name), reverse=reverse)
        total = len(records)
        page = records[offset : offset + limit]
        next_cursor = encode_cursor(offset + limit) if offset + limit < total else None
        if audit:
            await self.record_audit(
                auth,
                audit_action,
                project_id=project.id,
                source_id=None,
                metadata={
                    "result_count": len(page),
                    "total_matches": total,
                    "query": request.query,
                    "from": request.from_.isoformat(),
                    "to": request.to.isoformat(),
                },
            )
        return page, next_cursor, total

    async def list_audit_logs(self, auth: AuthContext, org_id: str | None = None) -> list[AuditEvent]:
        target_org = org_id or auth.key.org_id
        self._require_org(auth, target_org)
        return [event for event in self.audit_events if event.org_id == target_org]

    async def record_audit(
        self,
        auth: AuthContext,
        action: str,
        *,
        project_id: str | None,
        source_id: str | None,
        metadata: dict[str, Any],
    ) -> None:
        async with self._lock:
            self._audit_unlocked(
                action,
                org_id=auth.key.org_id,
                agent_id=auth.agent.id,
                api_key_id=auth.key.id,
                project_id=project_id,
                source_id=source_id,
                ip=auth.client_ip,
                metadata=metadata,
            )

    async def ensure_tail_allowed(
        self, auth: AuthContext, project_id: str, source_id: str | None
    ) -> None:
        if source_id:
            source = self._get_source_for_key(auth.key, source_id)
            if source.project_id != project_id:
                raise permission_denied("Source does not belong to the requested project.")
            return
        self._get_project_for_key(auth.key, project_id)

    async def tail(self, filter_: TailFilter) -> AsyncIterator[LogRecord]:
        async for record in self.tail_hub.tail(filter_):
            yield record

    async def acquire_tail_stream(self, auth: AuthContext, settings: Settings) -> None:
        async with self._lock:
            await self.tail_hub.acquire_stream(auth, settings)

    async def release_tail_stream(self, auth: AuthContext) -> None:
        async with self._lock:
            await self.tail_hub.release_stream(auth)

    async def _publish(self, record: LogRecord) -> None:
        await self.tail_hub.publish(record)

    def _audit_unlocked(
        self,
        action: str,
        *,
        org_id: str,
        agent_id: str | None,
        api_key_id: str | None,
        project_id: str | None,
        source_id: str | None,
        ip: str | None,
        metadata: dict[str, Any],
    ) -> None:
        event = AuditEvent(
            id=self._next_id("audit"),
            org_id=org_id,
            action=action,
            agent_id=agent_id,
            api_key_id=api_key_id,
            project_id=project_id,
            source_id=source_id,
            ip=ip,
            metadata=metadata,
            created_at=utc_now(),
        )
        self.audit_events.append(event)

    def _require_org(self, auth: AuthContext, org_id: str) -> None:
        require_auth_org(auth, org_id, org_id in self.orgs)

    def _get_project_for_key(self, key: ApiKeyRecord, project_id: str) -> Project:
        project = self.projects.get(project_id)
        if not project or project.org_id != key.org_id:
            raise not_found("Project")
        if key.project_ids and project_id not in key.project_ids:
            raise permission_denied("API key cannot access this project.")
        return project

    def _get_source_for_key(self, key: ApiKeyRecord, source_id: str) -> Source:
        source = self.sources.get(source_id)
        if not source or source.org_id != key.org_id:
            raise not_found("Source")
        if not self._project_allowed(key, source.project_id):
            raise permission_denied("API key cannot access this source's project.")
        if not self._source_allowed(key, source_id):
            raise permission_denied("API key cannot access this source.")
        return source

    def _project_allowed(self, key: ApiKeyRecord, project_id: str) -> bool:
        return project_allowed(key, project_id)

    def _source_allowed(self, key: ApiKeyRecord, source_id: str) -> bool:
        return source_allowed(key, source_id)

    def _resolve_project_source(
        self, key: ApiKeyRecord, project_id: str | None, source_id: str | None
    ) -> tuple[Project, Source]:
        if source_id:
            source = self._get_source_for_key(key, source_id)
            project = self._get_project_for_key(key, source.project_id)
            if project_id and project_id != project.id:
                raise bad_request("source_project_mismatch", "source_id does not belong to project_id.")
            return project, source

        candidate_sources = [
            source
            for source in self.sources.values()
            if source.org_id == key.org_id
            and (not project_id or source.project_id == project_id)
            and self._project_allowed(key, source.project_id)
            and self._source_allowed(key, source.id)
        ]
        if len(candidate_sources) != 1:
            raise bad_request(
                "source_required",
                "source_id is required unless the API key resolves to exactly one source.",
            )
        source = candidate_sources[0]
        project = self._get_project_for_key(key, source.project_id)
        return project, source

    def _assert_log_read_allowed(self, key: ApiKeyRecord, record: LogRecord) -> None:
        assert_log_read_allowed(key, record)

    def _assert_log_write_allowed(self, key: ApiKeyRecord, record: LogRecord) -> None:
        assert_log_write_allowed(key, record)

    def _matches_search(
        self,
        key: ApiKeyRecord,
        record: LogRecord,
        request: SearchLogsRequest,
        severities: set[str],
        requested_sources: set[str],
    ) -> bool:
        return record_matches_search(
            key=key,
            record=record,
            request=request,
            severities=severities,
            requested_sources=requested_sources,
            project_allowed=self._project_allowed,
            source_allowed=self._source_allowed,
        )

    def _reserve_project_ingest_quota(self, project_id: str, size_bytes: int, *, limit: int) -> None:
        if limit <= 0:
            return
        key = f"quota:project_ingest:{project_id}:{utc_now().date().isoformat()}"
        current = self.quota_counters.get(key, 0)
        if current + size_bytes > limit:
            raise rate_limited("Project daily ingest quota exceeded.")
        self.quota_counters[key] = current + size_bytes

    def _reserve_key_ingest_quota(self, key_id: str, size_bytes: int, *, limit: int) -> None:
        if limit <= 0:
            return
        key = f"quota:key_ingest:{key_id}:{utc_now().date().isoformat()}"
        current = self.quota_counters.get(key, 0)
        if current + size_bytes > limit:
            raise rate_limited("API key daily ingest byte quota exceeded.")
        self.quota_counters[key] = current + size_bytes

    def _reserve_agent_read_quota(self, agent_id: str, *, limit: int) -> None:
        if limit <= 0:
            return
        key = f"quota:agent_reads:{agent_id}:{utc_now().date().isoformat()}"
        current = self.quota_counters.get(key, 0)
        if current + 1 > limit:
            raise rate_limited("Agent daily read query quota exceeded.")
        self.quota_counters[key] = current + 1

