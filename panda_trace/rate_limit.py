from __future__ import annotations

import time
from dataclasses import dataclass

from panda_trace.config import Settings


@dataclass
class _Bucket:
    window_started_at: float
    count: int


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._buckets: dict[tuple[str, str], _Bucket] = {}

    def check(self, key_id: str, action: str, *, limit: int, window_seconds: int = 60) -> bool:
        now = time.time()
        bucket_key = (key_id, action)
        bucket = self._buckets.get(bucket_key)
        if bucket is None or now - bucket.window_started_at >= window_seconds:
            self._buckets[bucket_key] = _Bucket(window_started_at=now, count=1)
            return True
        if bucket.count >= limit:
            return False
        bucket.count += 1
        return True


class RedisRateLimiter:
    def __init__(self, redis_url: str) -> None:
        try:
            import redis
        except ImportError as exc:  # pragma: no cover - dependency is installed in prod image
            raise RuntimeError("Redis rate limiter requires the redis package.") from exc

        self.client = redis.Redis.from_url(redis_url, decode_responses=True)

    def check(self, key_id: str, action: str, *, limit: int, window_seconds: int = 60) -> bool:
        bucket = int(time.time() // window_seconds)
        redis_key = f"rate:{key_id}:{action}:{bucket}"
        count = self.client.incr(redis_key)
        if count == 1:
            self.client.expire(redis_key, window_seconds + 5)
        return int(count) <= limit


def create_rate_limiter(settings: Settings) -> InMemoryRateLimiter | RedisRateLimiter:
    if settings.rate_limit_backend == "memory":
        return InMemoryRateLimiter()
    if settings.rate_limit_backend == "redis":
        return RedisRateLimiter(settings.redis_url)
    raise RuntimeError(f"Unknown RATE_LIMIT_BACKEND: {settings.rate_limit_backend}")
