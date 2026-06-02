from __future__ import annotations

from datetime import datetime, timezone

from panda_trace.log_codecs import LOG_COLUMNS, log_from_row, log_from_tail_payload, log_insert_row
from panda_trace.models import LogRecord
from panda_trace.representations import record_to_dict


def test_log_codecs_round_trip_clickhouse_row_and_tail_payload() -> None:
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    record = LogRecord(
        id="log_1",
        org_id="org_1",
        project_id="proj_1",
        source_id="src_1",
        timestamp=now,
        received_at=now,
        severity="error",
        message="timeout",
        service="api",
        trace_id="trace_1",
        attributes={"customer_id": "cus_1"},
        exception={"type": "TimeoutError", "message": "gateway", "stacktrace": "Traceback"},
    )

    row_record = log_from_row(dict(zip(LOG_COLUMNS, log_insert_row(record), strict=True)))
    assert row_record == record

    tail_record = log_from_tail_payload(record_to_dict(record))
    assert tail_record == record
