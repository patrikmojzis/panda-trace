from __future__ import annotations

import asyncio
import json
import uuid
from io import BytesIO
from urllib.parse import urlparse
from typing import Any, AsyncIterator

from panda_trace.access import (
    assert_log_read_allowed,
    assert_log_write_allowed,
    project_allowed,
    require_key_org,
    source_allowed,
)
from panda_trace.config import Settings
from panda_trace.errors import bad_request, not_found, permission_denied, rate_limited
from panda_trace.log_query import (
    clickhouse_like_pattern,
    decode_cursor,
    encode_cursor,
    normalize_severity,
    validate_search_time_range,
)
from panda_trace.log_codecs import LOG_COLUMNS, log_from_row, log_insert_row
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
from panda_trace.row_codecs import (
    agent_from_row,
    attachment_from_row,
    audit_from_row,
    key_from_row,
    project_from_row,
    source_from_row,
)
from panda_trace.schemas import LogCreate, SearchLogsRequest, TailFilter, utc_now
from panda_trace.security import (
    ALL_SCOPES,
    extract_key_id,
    hash_secret,
    make_api_key_secret,
    verify_secret,
)
from panda_trace.tail import RedisTailAdapter, TailHub


class PostgresClickHouseStore:
    """Production store backed by Postgres control-plane tables and ClickHouse logs.

    The class satisfies the `LogStore` interface so route logic can swap storage
    adapters without learning Postgres, ClickHouse, Redis, or MinIO details.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.tail_hub = TailHub()
        try:
            from clickhouse_connect import get_client
            from minio import Minio
            from psycopg.rows import dict_row
            from psycopg.types.json import Jsonb
            from psycopg_pool import ConnectionPool
            import redis
        except ImportError as exc:  # pragma: no cover - exercised only without prod deps
            raise RuntimeError(
                "Persistent store requires psycopg[binary,pool], clickhouse-connect, redis, and minio."
            ) from exc

        self._jsonb = Jsonb
        self.pg = ConnectionPool(
            conninfo=settings.postgres_dsn,
            kwargs={"row_factory": dict_row},
            min_size=1,
            max_size=10,
            open=True,
        )
        self.ch = get_client(
            host=settings.clickhouse_host,
            port=settings.clickhouse_port,
            username=settings.clickhouse_user,
            password=settings.clickhouse_password,
            database=settings.clickhouse_database,
        )
        minio_endpoint = urlparse(settings.minio_endpoint)
        if minio_endpoint.scheme:
            endpoint = minio_endpoint.netloc
            secure = minio_endpoint.scheme == "https"
        else:
            endpoint = settings.minio_endpoint
            secure = False
        self.minio = Minio(
            endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=secure,
        )
        self.redis = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        self.redis_tail = RedisTailAdapter(self.redis)
        self._configure_retention()

    async def close(self) -> None:
        await asyncio.to_thread(self.pg.close)
        await asyncio.to_thread(self.redis.close)

    async def ready(self) -> dict[str, Any]:
        def check() -> dict[str, Any]:
            with self.pg.connection() as conn:
                conn.execute("SELECT 1").fetchone()
            clickhouse_ok = self.ch.command("SELECT 1")
            return {
                "store": "postgres_clickhouse",
                "postgres": "ready",
                "clickhouse": "ready" if clickhouse_ok == 1 else clickhouse_ok,
            }

        return await asyncio.to_thread(check)

    def _configure_retention(self) -> None:
        days = int(self.settings.log_retention_days)
        if days <= 0:
            return
        self.ch.command(
            f"ALTER TABLE logs MODIFY TTL timestamp + INTERVAL {days} DAY"
        )
        self.ch.command(
            f"ALTER TABLE audit_logs MODIFY TTL created_at + INTERVAL {days} DAY"
        )

    async def create_org_bootstrap(
        self, name: str, owner_agent_name: str
    ) -> tuple[Org, Agent, ApiKeyRecord, str]:
        now = utc_now()
        org = Org(id=_new_id("org"), name=name, created_at=now)
        agent = Agent(id=_new_id("agent"), org_id=org.id, name=owner_agent_name, created_at=now)
        key_id = _new_id("key")
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
        event = AuditEvent(
            id=_new_id("audit"),
            org_id=org.id,
            action="orgs.create",
            agent_id=agent.id,
            api_key_id=key.id,
            project_id=None,
            source_id=None,
            ip=None,
            metadata={"bootstrap": True},
            created_at=now,
        )

        def op() -> None:
            with self.pg.connection() as conn, conn.transaction():
                conn.execute(
                    "INSERT INTO orgs (id, name, created_at) VALUES (%s, %s, %s)",
                    (org.id, org.name, org.created_at),
                )
                conn.execute(
                    "INSERT INTO agents (id, org_id, name, created_at) VALUES (%s, %s, %s, %s)",
                    (agent.id, agent.org_id, agent.name, agent.created_at),
                )
                self._insert_key(conn, key)
                self._insert_audit_pg(conn, event)

        await asyncio.to_thread(op)
        await self._insert_audit_ch(event)
        return org, agent, key, secret

    async def authenticate(self, secret: str) -> ApiKeyRecord | None:
        key_id = extract_key_id(secret)
        if not key_id:
            return None

        def op() -> ApiKeyRecord | None:
            row = self._fetch_one_pg("SELECT * FROM api_keys WHERE id = %s", (key_id,))
            if not row:
                return None
            key = key_from_row(row)
            if not verify_secret(secret, key.secret_hash):
                return None
            return key

        return await asyncio.to_thread(op)

    async def get_agent(self, agent_id: str) -> Agent:
        def op() -> Agent:
            row = self._fetch_one_pg("SELECT * FROM agents WHERE id = %s", (agent_id,))
            if not row:
                raise not_found("Agent")
            return agent_from_row(row)

        return await asyncio.to_thread(op)

    async def create_project(self, auth: AuthContext, org_id: str, name: str) -> Project:
        require_key_org(auth.key, org_id)
        project = Project(id=_new_id("proj"), org_id=org_id, name=name, created_at=utc_now())
        event = _audit_from_auth(auth, "projects.create", project.id, None, {"name": name})

        def op() -> None:
            self._ensure_org_exists(org_id)
            with self.pg.connection() as conn, conn.transaction():
                conn.execute(
                    "INSERT INTO projects (id, org_id, name, created_at) VALUES (%s, %s, %s, %s)",
                    (project.id, project.org_id, project.name, project.created_at),
                )
                self._insert_audit_pg(conn, event)

        await asyncio.to_thread(op)
        await self._insert_audit_ch(event)
        return project

    async def create_source(self, auth: AuthContext, project_id: str, name: str, slug: str | None) -> Source:
        project = await self._project_for_key(auth.key, project_id)
        source = Source(
            id=_new_id("src"),
            org_id=project.org_id,
            project_id=project.id,
            name=name,
            slug=slug or name.lower().replace(" ", "-"),
            created_at=utc_now(),
        )
        event = _audit_from_auth(auth, "sources.create", project.id, source.id, {"name": name, "slug": source.slug})

        def op() -> None:
            with self.pg.connection() as conn, conn.transaction():
                conn.execute(
                    """
                    INSERT INTO sources (id, org_id, project_id, name, slug, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (source.id, source.org_id, source.project_id, source.name, source.slug, source.created_at),
                )
                self._insert_audit_pg(conn, event)

        await asyncio.to_thread(op)
        await self._insert_audit_ch(event)
        return source

    async def list_sources(self, auth: AuthContext, project_id: str | None) -> list[Source]:
        if project_id:
            await self._project_for_key(auth.key, project_id)
            sql = "SELECT * FROM sources WHERE org_id = %s AND project_id = %s ORDER BY created_at DESC"
            params = (auth.key.org_id, project_id)
        else:
            sql = "SELECT * FROM sources WHERE org_id = %s ORDER BY created_at DESC"
            params = (auth.key.org_id,)

        def op() -> list[Source]:
            rows = self._fetch_all_pg(sql, params)
            return [
                source_from_row(row)
                for row in rows
                if project_allowed(auth.key, row["project_id"])
                and source_allowed(auth.key, row["id"])
            ]

        return await asyncio.to_thread(op)

    async def create_agent(self, auth: AuthContext, org_id: str, name: str) -> Agent:
        require_key_org(auth.key, org_id)
        agent = Agent(id=_new_id("agent"), org_id=org_id, name=name, created_at=utc_now())
        event = _audit_from_auth(auth, "agents.create", None, None, {"created_agent_id": agent.id, "name": name})

        def op() -> None:
            self._ensure_org_exists(org_id)
            with self.pg.connection() as conn, conn.transaction():
                conn.execute(
                    "INSERT INTO agents (id, org_id, name, created_at) VALUES (%s, %s, %s, %s)",
                    (agent.id, agent.org_id, agent.name, agent.created_at),
                )
                self._insert_audit_pg(conn, event)

        await asyncio.to_thread(op)
        await self._insert_audit_ch(event)
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
        require_key_org(auth.key, org_id)
        target_agent = await self.get_agent(agent_id)
        if target_agent.org_id != org_id:
            raise permission_denied("Cannot create a key for an agent in another org.")
        for project_id in project_ids:
            await self._project_for_key(auth.key, project_id)
        for source_id in source_ids:
            await self._source_for_key(auth.key, source_id)

        key_id = _new_id("key")
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
        event = _audit_from_auth(
            auth,
            "api_keys.create",
            None,
            None,
            {"created_key_id": key.id, "target_agent_id": agent_id, "scopes": key.scopes},
        )

        def op() -> None:
            with self.pg.connection() as conn, conn.transaction():
                self._insert_key(conn, key)
                self._insert_audit_pg(conn, event)

        await asyncio.to_thread(op)
        await self._insert_audit_ch(event)
        return key, secret

    async def revoke_api_key(self, auth: AuthContext, key_id: str) -> ApiKeyRecord:
        def op() -> tuple[ApiKeyRecord, AuditEvent]:
            row = self._fetch_one_pg("SELECT * FROM api_keys WHERE id = %s", (key_id,))
            if not row or row["org_id"] != auth.key.org_id:
                raise not_found("API key")
            revoked_at = utc_now()
            event = _audit_from_auth(auth, "api_keys.revoke", None, None, {"revoked_key_id": key_id})
            with self.pg.connection() as conn, conn.transaction():
                conn.execute("UPDATE api_keys SET revoked_at = %s WHERE id = %s", (revoked_at, key_id))
                self._insert_audit_pg(conn, event)
            row["revoked_at"] = revoked_at
            return key_from_row(row), event

        key, event = await asyncio.to_thread(op)
        await self._insert_audit_ch(event)
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
            existing = await self._idempotency_lookup(auth.key.id, idem)
            if existing:
                return await self._get_log_by_id(existing)
        project, source = await self._resolve_project_source(auth.key, log.project_id, log.source_id)
        severity = normalize_severity(log.severity)
        payload_size = log_payload_size(log)
        await self._reserve_key_ingest_quota(
            auth.key.id,
            payload_size,
            limit=settings.max_key_daily_ingest_bytes,
        )
        await self._reserve_project_ingest_quota(
            project.id,
            payload_size,
            limit=settings.max_project_daily_ingest_bytes,
        )
        received_at = utc_now()
        record = LogRecord(
            id=_new_id("log"),
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
        event = _audit_from_auth(
            auth,
            "logs.write",
            record.project_id,
            record.source_id,
            {"log_id": record.id, "severity": severity},
        )

        def op() -> None:
            self.ch.insert("logs", [log_insert_row(record)], column_names=LOG_COLUMNS)
            if idem:
                with self.pg.connection() as conn, conn.transaction():
                    conn.execute(
                        """
                        INSERT INTO idempotency_keys (api_key_id, idempotency_key, log_id)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (api_key_id, idempotency_key) DO NOTHING
                        """,
                        (auth.key.id, idem, record.id),
                    )
                    self._insert_audit_pg(conn, event)
            else:
                with self.pg.connection() as conn, conn.transaction():
                    self._insert_audit_pg(conn, event)

        await asyncio.to_thread(op)
        await self._insert_audit_ch(event)
        await self._publish(record)
        return record

    async def get_log(self, auth: AuthContext, log_id: str) -> LogRecord:
        record = await self._get_log_by_id(log_id)
        assert_log_read_allowed(auth.key, record)
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
        record = await self._get_log_by_id(log_id)
        assert_log_write_allowed(auth.key, record)
        attachment = AttachmentRecord(
            id=_new_id("att"),
            org_id=record.org_id,
            project_id=record.project_id,
            source_id=record.source_id,
            log_id=record.id,
            filename=filename,
            content_type=content_type,
            size_bytes=len(content),
            storage_backend="minio",
            object_key=f"{record.org_id}/{record.project_id}/{record.source_id}/{record.id}/{_new_id('blob')}",
            created_at=utc_now(),
        )
        event = _audit_from_auth(
            auth,
            "log_attachments.create",
            record.project_id,
            record.source_id,
            {
                "log_id": log_id,
                "attachment_id": attachment.id,
                "filename": filename,
                "size_bytes": len(content),
            },
        )

        def op() -> None:
            if not self.minio.bucket_exists(self.settings.minio_bucket):
                self.minio.make_bucket(self.settings.minio_bucket)
            self.minio.put_object(
                self.settings.minio_bucket,
                attachment.object_key,
                BytesIO(content),
                length=len(content),
                content_type=content_type,
            )
            with self.pg.connection() as conn, conn.transaction():
                self._insert_attachment_pg(conn, attachment)
                self._insert_audit_pg(conn, event)

        await asyncio.to_thread(op)
        await self._insert_audit_ch(event)
        return attachment

    async def list_attachments(self, auth: AuthContext, log_id: str) -> list[AttachmentRecord]:
        record = await self._get_log_by_id(log_id)
        assert_log_read_allowed(auth.key, record)
        await self.record_audit(
            auth,
            "log_attachments.list",
            project_id=record.project_id,
            source_id=record.source_id,
            metadata={"log_id": log_id},
        )

        def op() -> list[AttachmentRecord]:
            rows = self._fetch_all_pg(
                "SELECT * FROM log_attachments WHERE log_id = %s ORDER BY created_at DESC",
                (log_id,),
            )
            return [attachment_from_row(row) for row in rows]

        return await asyncio.to_thread(op)

    async def get_attachment(
        self, auth: AuthContext, log_id: str, attachment_id: str
    ) -> tuple[AttachmentRecord, bytes]:
        record = await self._get_log_by_id(log_id)
        assert_log_read_allowed(auth.key, record)

        def op() -> tuple[AttachmentRecord, bytes]:
            row = self._fetch_one_pg(
                "SELECT * FROM log_attachments WHERE log_id = %s AND id = %s",
                (log_id, attachment_id),
            )
            if row is None:
                raise not_found("Attachment")
            attachment = attachment_from_row(row)
            response = self.minio.get_object(self.settings.minio_bucket, attachment.object_key)
            try:
                content = response.read()
            finally:
                response.close()
                response.release_conn()
            return attachment, content

        attachment, content = await asyncio.to_thread(op)
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
        await self._validate_search_request(auth.key, request, settings)
        await self._reserve_agent_read_quota(
            auth.agent.id,
            limit=settings.max_agent_daily_read_queries,
        )
        offset = decode_cursor(request.cursor)
        if limit_override is None:
            limit = min(request.limit, settings.max_page_size)
        else:
            limit = min(limit_override, settings.max_export_rows)

        def op() -> tuple[list[LogRecord], int]:
            where, params = self._search_where(auth.key, request)
            count_rows = list(self.ch.query(
                f"SELECT count() AS count FROM logs WHERE {' AND '.join(where)}",
                parameters=params,
            ).named_results())
            total = count_rows[0]["count"] if count_rows else 0
            order_by = {
                "timestamp_desc": "timestamp DESC, received_at DESC",
                "timestamp_asc": "timestamp ASC, received_at ASC",
                "received_at_desc": "received_at DESC",
            }[request.sort]
            rows = list(self.ch.query(
                f"""
                SELECT {', '.join(LOG_COLUMNS)}
                FROM logs
                WHERE {' AND '.join(where)}
                ORDER BY {order_by}
                LIMIT %(limit)s OFFSET %(offset)s
                """,
                parameters=params | {"limit": limit, "offset": offset},
            ).named_results())
            return [log_from_row(row) for row in rows], int(total)

        records, total = await asyncio.to_thread(op)
        next_cursor = encode_cursor(offset + limit) if offset + limit < total else None
        if audit:
            await self.record_audit(
                auth,
                audit_action,
                project_id=request.project_id,
                source_id=None,
                metadata={
                    "result_count": len(records),
                    "total_matches": total,
                    "query": request.query,
                    "from": request.from_.isoformat(),
                    "to": request.to.isoformat(),
                },
            )
        return records, next_cursor, total

    async def list_audit_logs(self, auth: AuthContext, org_id: str | None = None) -> list[AuditEvent]:
        target_org = org_id or auth.key.org_id
        require_key_org(auth.key, target_org)

        def op() -> list[AuditEvent]:
            rows = self._fetch_all_pg(
                "SELECT * FROM audit_events WHERE org_id = %s ORDER BY created_at DESC LIMIT 1000",
                (target_org,),
            )
            return [audit_from_row(row) for row in rows]

        return await asyncio.to_thread(op)

    async def record_audit(
        self,
        auth: AuthContext,
        action: str,
        *,
        project_id: str | None,
        source_id: str | None,
        metadata: dict[str, Any],
    ) -> None:
        event = _audit_from_auth(auth, action, project_id, source_id, metadata)

        def pg_op() -> None:
            with self.pg.connection() as conn, conn.transaction():
                self._insert_audit_pg(conn, event)

        await asyncio.to_thread(pg_op)
        await self._insert_audit_ch(event)

    async def ensure_tail_allowed(
        self, auth: AuthContext, project_id: str, source_id: str | None
    ) -> None:
        if source_id:
            source = await self._source_for_key(auth.key, source_id)
            if source.project_id != project_id:
                raise permission_denied("Source does not belong to the requested project.")
            return
        await self._project_for_key(auth.key, project_id)

    async def tail(self, filter_: TailFilter) -> AsyncIterator[LogRecord]:
        if self.settings.tail_backend == "memory":
            async for record in self.tail_hub.tail(filter_):
                yield record
            return

        if self.settings.tail_backend != "redis":
            raise RuntimeError(f"Unknown TAIL_BACKEND: {self.settings.tail_backend}")
        async for record in self.redis_tail.tail(filter_):
            yield record

    async def acquire_tail_stream(self, auth: AuthContext, settings: Settings) -> None:
        if settings.max_concurrent_tail_streams <= 0:
            return
        if settings.tail_backend == "memory":
            await self.tail_hub.acquire_stream(auth, settings)
            return
        await self.redis_tail.acquire_stream(auth, settings)

    async def release_tail_stream(self, auth: AuthContext) -> None:
        if self.settings.tail_backend == "memory":
            await self.tail_hub.release_stream(auth)
            return
        await self.redis_tail.release_stream(auth)

    async def _publish(self, record: LogRecord) -> None:
        if self.settings.tail_backend == "memory":
            await self.tail_hub.publish(record)
            return
        if self.settings.tail_backend != "redis":
            raise RuntimeError(f"Unknown TAIL_BACKEND: {self.settings.tail_backend}")
        await self.redis_tail.publish(record)

    def _fetch_one_pg(self, sql: str, params: tuple[Any, ...]) -> dict[str, Any] | None:
        with self.pg.connection() as conn:
            return conn.execute(sql, params).fetchone()

    def _fetch_all_pg(self, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        with self.pg.connection() as conn:
            return list(conn.execute(sql, params).fetchall())

    def _insert_key(self, conn: Any, key: ApiKeyRecord) -> None:
        conn.execute(
            """
            INSERT INTO api_keys (
              id, agent_id, org_id, secret_salt, secret_digest, secret_iterations,
              scopes, project_ids, source_ids, ip_allowlist, created_at, expires_at, revoked_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                key.id,
                key.agent_id,
                key.org_id,
                key.secret_hash.salt,
                key.secret_hash.digest,
                key.secret_hash.iterations,
                self._jsonb(key.scopes),
                self._jsonb(key.project_ids),
                self._jsonb(key.source_ids),
                self._jsonb(key.ip_allowlist),
                key.created_at,
                key.expires_at,
                key.revoked_at,
            ),
        )

    def _insert_audit_pg(self, conn: Any, event: AuditEvent) -> None:
        conn.execute(
            """
            INSERT INTO audit_events (
              id, org_id, action, agent_id, api_key_id, project_id, source_id, ip, metadata, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                event.id,
                event.org_id,
                event.action,
                event.agent_id,
                event.api_key_id,
                event.project_id,
                event.source_id,
                event.ip,
                self._jsonb(event.metadata),
                event.created_at,
            ),
        )

    def _insert_attachment_pg(self, conn: Any, attachment: AttachmentRecord) -> None:
        conn.execute(
            """
            INSERT INTO log_attachments (
              id, org_id, project_id, source_id, log_id, filename, content_type,
              size_bytes, storage_backend, object_key, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                attachment.id,
                attachment.org_id,
                attachment.project_id,
                attachment.source_id,
                attachment.log_id,
                attachment.filename,
                attachment.content_type,
                attachment.size_bytes,
                attachment.storage_backend,
                attachment.object_key,
                attachment.created_at,
            ),
        )

    async def _insert_audit_ch(self, event: AuditEvent) -> None:
        def op() -> None:
            self.ch.insert(
                "audit_logs",
                [
                    [
                        event.id,
                        event.org_id,
                        event.action,
                        event.agent_id,
                        event.api_key_id,
                        event.project_id,
                        event.source_id,
                        event.ip,
                        json.dumps(event.metadata, separators=(",", ":")),
                        event.created_at,
                    ]
                ],
                column_names=[
                    "id",
                    "org_id",
                    "action",
                    "agent_id",
                    "api_key_id",
                    "project_id",
                    "source_id",
                    "ip",
                    "metadata",
                    "created_at",
                ],
            )

        await asyncio.to_thread(op)

    def _ensure_org_exists(self, org_id: str) -> None:
        if not self._fetch_one_pg("SELECT id FROM orgs WHERE id = %s", (org_id,)):
            raise not_found("Org")

    async def _project_for_key(self, key: ApiKeyRecord, project_id: str) -> Project:
        def op() -> Project:
            row = self._fetch_one_pg("SELECT * FROM projects WHERE id = %s", (project_id,))
            if not row or row["org_id"] != key.org_id:
                raise not_found("Project")
            if not project_allowed(key, project_id):
                raise permission_denied("API key cannot access this project.")
            return project_from_row(row)

        return await asyncio.to_thread(op)

    async def _source_for_key(self, key: ApiKeyRecord, source_id: str) -> Source:
        def op() -> Source:
            row = self._fetch_one_pg("SELECT * FROM sources WHERE id = %s", (source_id,))
            if not row or row["org_id"] != key.org_id:
                raise not_found("Source")
            if not project_allowed(key, row["project_id"]):
                raise permission_denied("API key cannot access this source's project.")
            if not source_allowed(key, source_id):
                raise permission_denied("API key cannot access this source.")
            return source_from_row(row)

        return await asyncio.to_thread(op)

    async def _resolve_project_source(
        self, key: ApiKeyRecord, project_id: str | None, source_id: str | None
    ) -> tuple[Project, Source]:
        if source_id:
            source = await self._source_for_key(key, source_id)
            project = await self._project_for_key(key, source.project_id)
            if project_id and project_id != project.id:
                raise bad_request("source_project_mismatch", "source_id does not belong to project_id.")
            return project, source
        return await self._single_source_for_key(key, project_id)

    async def _single_source_for_key(
        self, key: ApiKeyRecord, project_id: str | None
    ) -> tuple[Project, Source]:
        def op() -> list[Source]:
            if project_id:
                sql = "SELECT * FROM sources WHERE org_id = %s AND project_id = %s"
                params = (key.org_id, project_id)
            else:
                sql = "SELECT * FROM sources WHERE org_id = %s"
                params = (key.org_id,)
            rows = self._fetch_all_pg(sql, params)
            return [
                source_from_row(row)
                for row in rows
                if project_allowed(key, row["project_id"]) and source_allowed(key, row["id"])
            ]

        candidates = await asyncio.to_thread(op)
        if len(candidates) != 1:
            raise bad_request(
                "source_required",
                "source_id is required unless the API key resolves to exactly one source.",
            )
        source = candidates[0]
        project = await self._project_for_key(key, source.project_id)
        return project, source

    async def _validate_search_request(
        self, key: ApiKeyRecord, request: SearchLogsRequest, settings: Settings
    ) -> None:
        validate_search_time_range(request, settings)
        await self._project_for_key(key, request.project_id)
        for source_id in request.sources:
            source = await self._source_for_key(key, source_id)
            if source.project_id != request.project_id:
                raise permission_denied("Source does not belong to the requested project.")

    def _search_where(
        self, key: ApiKeyRecord, request: SearchLogsRequest
    ) -> tuple[list[str], dict[str, Any]]:
        where = [
            "org_id = %(org_id)s",
            "project_id = %(project_id)s",
            "timestamp >= %(from)s",
            "timestamp <= %(to)s",
        ]
        params: dict[str, Any] = {
            "org_id": key.org_id,
            "project_id": request.project_id,
            "from": request.from_,
            "to": request.to,
        }
        source_filter = request.sources or key.source_ids
        if source_filter:
            where.append("source_id IN %(source_ids)s")
            params["source_ids"] = tuple(source_filter)
        if request.severity:
            where.append("severity IN %(severity)s")
            params["severity"] = tuple(normalize_severity(item) for item in request.severity)
        for field in ["trace_id", "span_id", "request_id", "logger"]:
            value = getattr(request, field)
            if value:
                where.append(f"{field} = %({field})s")
                params[field] = value
        if request.query:
            where.append(
                """
                (
                  lowerUTF8(message) LIKE %(query_like)s OR
                  lowerUTF8(ifNull(exception_message, '')) LIKE %(query_like)s OR
                  lowerUTF8(ifNull(exception_stacktrace, '')) LIKE %(query_like)s
                )
                """
            )
            params["query_like"] = clickhouse_like_pattern(request.query)
        for index, (key_name, value) in enumerate(request.attributes.items()):
            param_key = f"attr_{index}"
            path_key = f"attr_path_{index}"
            where.append(f"JSON_VALUE(attributes, %({path_key})s) = %({param_key})s")
            params[path_key] = f"$.{key_name}"
            params[param_key] = str(value)
        return where, params

    async def _get_log_by_id(self, log_id: str) -> LogRecord:
        def op() -> LogRecord:
            result = list(self.ch.query(
                f"SELECT {', '.join(LOG_COLUMNS)} FROM logs WHERE id = %(id)s LIMIT 1",
                parameters={"id": log_id},
            ).named_results())
            if not result:
                raise not_found("Log")
            return log_from_row(result[0])

        return await asyncio.to_thread(op)

    async def _idempotency_lookup(self, api_key_id: str, key: str) -> str | None:
        def op() -> str | None:
            row = self._fetch_one_pg(
                "SELECT log_id FROM idempotency_keys WHERE api_key_id = %s AND idempotency_key = %s",
                (api_key_id, key),
            )
            return row["log_id"] if row else None

        return await asyncio.to_thread(op)

    async def _reserve_project_ingest_quota(
        self, project_id: str, size_bytes: int, *, limit: int
    ) -> None:
        if limit <= 0:
            return
        await self._reserve_daily_redis_counter(
            f"quota:project_ingest:{project_id}",
            size_bytes,
            limit,
            "Project daily ingest quota exceeded.",
        )

    async def _reserve_key_ingest_quota(self, key_id: str, size_bytes: int, *, limit: int) -> None:
        if limit <= 0:
            return
        await self._reserve_daily_redis_counter(
            f"quota:key_ingest:{key_id}",
            size_bytes,
            limit,
            "API key daily ingest byte quota exceeded.",
        )

    async def _reserve_agent_read_quota(self, agent_id: str, *, limit: int) -> None:
        if limit <= 0:
            return
        await self._reserve_daily_redis_counter(
            f"quota:agent_reads:{agent_id}",
            1,
            limit,
            "Agent daily read query quota exceeded.",
        )

    async def _reserve_daily_redis_counter(
        self, prefix: str, amount: int, limit: int, message: str
    ) -> None:
        key = f"{prefix}:{utc_now().date().isoformat()}"

        def op() -> int:
            value = int(self.redis.incrby(key, amount))
            if value == amount:
                self.redis.expire(key, 48 * 60 * 60)
            return value

        value = await asyncio.to_thread(op)
        if value > limit:
            await asyncio.to_thread(self.redis.decrby, key, amount)
            raise rate_limited(message)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _audit_from_auth(
    auth: AuthContext,
    action: str,
    project_id: str | None,
    source_id: str | None,
    metadata: dict[str, Any],
) -> AuditEvent:
    return AuditEvent(
        id=_new_id("audit"),
        org_id=auth.key.org_id,
        action=action,
        agent_id=auth.agent.id,
        api_key_id=auth.key.id,
        project_id=project_id,
        source_id=source_id,
        ip=auth.client_ip,
        metadata=metadata,
        created_at=utc_now(),
    )
