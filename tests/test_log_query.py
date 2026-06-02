from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from panda_trace.config import Settings
from panda_trace.errors import APIError
from panda_trace.log_query import (
    clickhouse_like_pattern,
    decode_cursor,
    encode_cursor,
    normalize_requested_severities,
    normalize_severity,
    record_matches_search,
    record_matches_tail,
    validate_search_time_range,
)
from panda_trace.schemas import SearchLogsRequest, TailFilter


def test_query_module_normalizes_severity_and_cursor() -> None:
    assert normalize_severity("WARN") == "warning"
    assert normalize_requested_severities(_search(severity=["ERR", "fatal"])) == {"error", "critical"}
    assert decode_cursor(encode_cursor(42)) == 42

    with pytest.raises(APIError) as exc:
        normalize_severity("loud")
    assert exc.value.code == "invalid_severity"

    with pytest.raises(APIError) as exc:
        decode_cursor("nope")
    assert exc.value.code == "invalid_cursor"


def test_query_module_validates_time_range() -> None:
    settings = Settings(max_search_range_days=1)
    validate_search_time_range(_search(), settings)

    with pytest.raises(APIError) as exc:
        validate_search_time_range(
            _search(from_=datetime(2026, 6, 2, tzinfo=timezone.utc)),
            settings,
        )
    assert exc.value.code == "invalid_time_range"

    with pytest.raises(APIError) as exc:
        validate_search_time_range(
            _search(to=datetime(2026, 6, 3, tzinfo=timezone.utc)),
            settings,
        )
    assert exc.value.code == "time_range_too_large"


def test_query_module_matches_search_and_tail_filters() -> None:
    record = SimpleNamespace(
        project_id="proj_1",
        source_id="src_1",
        timestamp=datetime(2026, 6, 1, 12, 30, tzinfo=timezone.utc),
        severity="error",
        trace_id="trace_1",
        span_id=None,
        request_id="req_1",
        logger="billing",
        message="Payment timeout",
        exception={"message": "gateway timeout", "stacktrace": "Traceback..."},
        attributes={"customer_id": "cus_1"},
    )
    key = SimpleNamespace(project_ids=[], source_ids=[])
    request = _search(
        query="gateway",
        severity=["error"],
        trace_id="trace_1",
        request_id="req_1",
        logger="billing",
        attributes={"customer_id": "cus_1"},
        sources=["src_1"],
    )

    assert record_matches_search(
        key=key,
        record=record,
        request=request,
        severities=normalize_requested_severities(request),
        requested_sources=set(request.sources),
        project_allowed=lambda _key, _project_id: True,
        source_allowed=lambda _key, _source_id: True,
    )
    assert not record_matches_search(
        key=key,
        record=record,
        request=_search(query="missing"),
        severities=set(),
        requested_sources=set(),
        project_allowed=lambda _key, _project_id: True,
        source_allowed=lambda _key, _source_id: True,
    )
    assert record_matches_tail(record, TailFilter(project_id="proj_1", severity=["ERR"], query="payment"))
    assert not record_matches_tail(record, TailFilter(project_id="proj_1", source_id="src_2"))


def test_clickhouse_like_pattern_escapes_wildcards() -> None:
    assert clickhouse_like_pattern(r"Gateway_100%\\") == r"%gateway\_100\%\\\\%"


def _search(**overrides: object) -> SearchLogsRequest:
    start = datetime(2026, 6, 1, tzinfo=timezone.utc)
    if "from_" in overrides:
        overrides["from"] = overrides.pop("from_")
    data = {
        "project_id": "proj_1",
        "from": start,
        "to": start + timedelta(days=1),
    } | overrides
    return SearchLogsRequest.model_validate(data)
