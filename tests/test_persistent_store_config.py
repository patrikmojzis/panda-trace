from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree

from panda_trace.config import Settings
from panda_trace.persistent_store import _create_clickhouse_client


def test_shared_clickhouse_client_does_not_create_a_session() -> None:
    captured: dict[str, object] = {}
    client = object()

    def fake_get_client(**kwargs: object) -> object:
        captured.update(kwargs)
        return client

    assert _create_clickhouse_client(Settings(), fake_get_client) is client
    assert captured["autogenerate_session_id"] is False


def test_clickhouse_diagnostic_logs_have_bounded_retention() -> None:
    config_path = Path(__file__).parents[1] / "deploy" / "clickhouse" / "panda-trace.xml"
    config = ElementTree.parse(config_path).getroot()

    for table in ("query_log", "trace_log", "text_log", "metric_log"):
        assert config.findtext(f"{table}/ttl") == "event_date + INTERVAL 7 DAY DELETE"
