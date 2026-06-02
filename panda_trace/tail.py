from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator

from panda_trace.config import Settings
from panda_trace.errors import rate_limited
from panda_trace.log_query import record_matches_tail
from panda_trace.log_codecs import log_from_tail_payload
from panda_trace.models import AuthContext, LogRecord
from panda_trace.representations import record_to_dict
from panda_trace.schemas import TailFilter


class TailHub:
    def __init__(self) -> None:
        self._subscribers: list[tuple[TailFilter, asyncio.Queue[LogRecord]]] = []
        self._stream_counts: dict[str, int] = {}

    async def tail(self, filter_: TailFilter) -> AsyncIterator[LogRecord]:
        queue = self._subscribe(filter_)
        try:
            while True:
                yield await queue.get()
        finally:
            self._unsubscribe(queue)

    async def acquire_stream(self, auth: AuthContext, settings: Settings) -> None:
        if settings.max_concurrent_tail_streams <= 0:
            return
        current = self._stream_counts.get(auth.key.id, 0)
        if current >= settings.max_concurrent_tail_streams:
            raise rate_limited("Concurrent tail stream limit exceeded.")
        self._stream_counts[auth.key.id] = current + 1

    async def release_stream(self, auth: AuthContext) -> None:
        current = self._stream_counts.get(auth.key.id, 0)
        if current <= 1:
            self._stream_counts.pop(auth.key.id, None)
        else:
            self._stream_counts[auth.key.id] = current - 1

    async def publish(self, record: LogRecord) -> None:
        stale: list[asyncio.Queue[LogRecord]] = []
        for filter_, queue in self._subscribers:
            if not record_matches_tail(record, filter_):
                continue
            try:
                queue.put_nowait(record)
            except asyncio.QueueFull:
                stale.append(queue)
        for queue in stale:
            self._unsubscribe(queue)

    def _subscribe(self, filter_: TailFilter) -> asyncio.Queue[LogRecord]:
        queue: asyncio.Queue[LogRecord] = asyncio.Queue(maxsize=100)
        self._subscribers.append((filter_, queue))
        return queue

    def _unsubscribe(self, queue: asyncio.Queue[LogRecord]) -> None:
        self._subscribers = [(filter_, q) for filter_, q in self._subscribers if q is not queue]


class RedisTailAdapter:
    def __init__(self, redis_client: Any) -> None:
        self.redis = redis_client

    async def tail(self, filter_: TailFilter) -> AsyncIterator[LogRecord]:
        pubsub = self.redis.pubsub()
        channel = tail_channel(filter_.project_id)
        await asyncio.to_thread(pubsub.subscribe, channel)
        try:
            while True:
                message = await asyncio.to_thread(
                    pubsub.get_message,
                    ignore_subscribe_messages=True,
                    timeout=15,
                )
                if not message:
                    continue
                record = log_from_tail_payload(json.loads(message["data"]))
                if record_matches_tail(record, filter_):
                    yield record
        finally:
            await asyncio.to_thread(pubsub.unsubscribe, channel)
            await asyncio.to_thread(pubsub.close)

    async def acquire_stream(self, auth: AuthContext, settings: Settings) -> None:
        if settings.max_concurrent_tail_streams <= 0:
            return
        key = f"tail_streams:{auth.key.id}"

        def op() -> int:
            count = int(self.redis.incr(key))
            self.redis.expire(key, max(settings.tail_idle_timeout_seconds * 2, 60))
            return count

        count = await asyncio.to_thread(op)
        if count > settings.max_concurrent_tail_streams:
            await asyncio.to_thread(self.redis.decr, key)
            raise rate_limited("Concurrent tail stream limit exceeded.")

    async def release_stream(self, auth: AuthContext) -> None:
        key = f"tail_streams:{auth.key.id}"

        def op() -> None:
            value = int(self.redis.decr(key))
            if value <= 0:
                self.redis.delete(key)

        await asyncio.to_thread(op)

    async def publish(self, record: LogRecord) -> None:
        payload = json.dumps(record_to_dict(record), separators=(",", ":"))
        await asyncio.to_thread(self.redis.publish, tail_channel(record.project_id), payload)


def tail_channel(project_id: str) -> str:
    return f"tail:project:{project_id}"
