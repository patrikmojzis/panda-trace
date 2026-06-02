from __future__ import annotations

from datetime import datetime, timezone

import pytest

from panda_trace.access import (
    assert_log_read_allowed,
    assert_log_write_allowed,
    project_allowed,
    require_key_org,
    source_allowed,
)
from panda_trace.errors import APIError
from panda_trace.models import ApiKeyRecord, LogRecord
from panda_trace.security import SecretHash


def test_access_rules_for_org_project_source_and_log_records() -> None:
    key = _key(project_ids=["proj_1"], source_ids=["src_1"])
    allowed = _record(project_id="proj_1", source_id="src_1")

    require_key_org(key, "org_1")
    assert project_allowed(key, "proj_1")
    assert source_allowed(key, "src_1")
    assert_log_read_allowed(key, allowed)
    assert_log_write_allowed(key, allowed)

    with pytest.raises(APIError) as exc:
        require_key_org(key, "org_2")
    assert exc.value.code == "permission_denied"

    with pytest.raises(APIError) as exc:
        assert_log_read_allowed(key, _record(project_id="proj_2", source_id="src_1"))
    assert exc.value.message == "API key cannot read logs for this project."

    with pytest.raises(APIError) as exc:
        assert_log_write_allowed(key, _record(project_id="proj_1", source_id="src_2"))
    assert exc.value.message == "API key cannot write logs for this source."


def _key(project_ids: list[str], source_ids: list[str]) -> ApiKeyRecord:
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    return ApiKeyRecord(
        id="key_1",
        agent_id="agent_1",
        org_id="org_1",
        secret_hash=SecretHash(salt="salt", digest="digest"),
        scopes=[],
        project_ids=project_ids,
        source_ids=source_ids,
        ip_allowlist=[],
        created_at=now,
        expires_at=None,
    )


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
