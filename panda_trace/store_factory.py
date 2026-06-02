from __future__ import annotations

from panda_trace.config import Settings
from panda_trace.persistent_store import PostgresClickHouseStore
from panda_trace.store import InMemoryStore
from panda_trace.store_interface import LogStore


def create_store_from_settings(settings: Settings) -> LogStore:
    if settings.store_backend == "memory":
        return InMemoryStore()
    if settings.store_backend == "persistent":
        return PostgresClickHouseStore(settings)
    raise RuntimeError(f"Unknown PANDA_TRACE_STORE: {settings.store_backend}")
