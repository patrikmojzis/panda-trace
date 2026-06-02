from __future__ import annotations

from typing import Annotated, Callable

from fastapi import Depends, Header, Request

from panda_trace.auth import authenticate_request, require_auth_scope
from panda_trace.config import Settings
from panda_trace.errors import rate_limited
from panda_trace.models import AuthContext
from panda_trace.rate_limit import InMemoryRateLimiter
from panda_trace.store_interface import LogStore


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_store(request: Request) -> LogStore:
    return request.app.state.store


async def get_auth(
    request: Request,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    store: LogStore = Depends(get_store),
) -> AuthContext:
    client_ip = request.client.host if request.client else None
    return await authenticate_request(store=store, authorization=authorization, client_ip=client_ip)


def require_scope(scope: str) -> Callable:
    async def dependency(auth: AuthContext = Depends(get_auth)) -> AuthContext:
        return require_auth_scope(auth, scope)

    return dependency


def check_rate(auth: AuthContext, request: Request, action: str) -> None:
    limiter: InMemoryRateLimiter = request.app.state.rate_limiter
    if not limiter.check(
        auth.key.id,
        action,
        limit=request.app.state.settings.rate_limit_per_minute,
        window_seconds=60,
    ):
        raise rate_limited(f"Rate limit exceeded for {action}.")
