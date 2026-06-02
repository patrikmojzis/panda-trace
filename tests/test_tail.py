from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from panda_trace.config import Settings
from panda_trace.errors import APIError
from panda_trace.models import ApiKeyRecord, AuthContext, LogRecord, Agent
from panda_trace.security import SecretHash
from panda_trace.schemas import TailFilter
from panda_trace.tail import TailHub, tail_channel


def test_tail_channel_is_project_scoped() -> None:
    assert tail_channel("proj_1") == "tail:project:proj_1"


def test_tail_hub_filters_records_and_enforces_stream_limit() -> None:
    async def check() -> None:
        hub = TailHub()
        auth = _auth()
        settings = Settings(max_concurrent_tail_streams=1)

        await hub.acquire_stream(auth, settings)
        with pytest.raises(APIError) as exc:
            await hub.acquire_stream(auth, settings)
        assert exc.value.code == "rate_limited"
        await hub.release_stream(auth)
        await hub.acquire_stream(auth, settings)
        await hub.release_stream(auth)

        iterator = hub.tail(TailFilter(project_id="proj_1", source_id="src_1"))
        task = asyncio.create_task(iterator.__anext__())
        await asyncio.sleep(0)
        await hub.publish(_record(project_id="proj_1", source_id="src_2"))
        assert not task.done()
        await hub.publish(_record(project_id="proj_1", source_id="src_1"))
        assert (await asyncio.wait_for(task, timeout=1)).source_id == "src_1"
        await iterator.aclose()

    asyncio.run(check())


def _auth() -> AuthContext:
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    key = ApiKeyRecord(
        id="key_1",
        agent_id="agent_1",
        org_id="org_1",
        secret_hash=SecretHash(salt="salt", digest="digest"),
        scopes=[],
        project_ids=[],
        source_ids=[],
        ip_allowlist=[],
        created_at=now,
        expires_at=None,
    )
    return AuthContext(key=key, agent=Agent(id="agent_1", org_id="org_1", name="agent", created_at=now), client_ip=None)


def _record(project_id: str, source_id: str) -> LogRecord:
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    return LogRecord(
        id="log_1",
        org_id="org_1",
        project_id=project_id,
        source_id=source_id,
        timestamp=now,
        received_at=now,
        severity="info",
        message="hello",
    )
