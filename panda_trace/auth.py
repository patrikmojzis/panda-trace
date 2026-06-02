from __future__ import annotations

from datetime import datetime, timezone

from panda_trace.errors import permission_denied, unauthorized
from panda_trace.models import AuthContext
from panda_trace.security import ip_allowed
from panda_trace.store_interface import LogStore


async def authenticate_request(
    *,
    store: LogStore,
    authorization: str | None,
    client_ip: str | None,
) -> AuthContext:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise unauthorized("Authorization header must be `Bearer <api_key>`.")
    secret = authorization.split(" ", 1)[1].strip()
    key = await store.authenticate(secret)
    if key is None:
        raise unauthorized()
    now = datetime.now(timezone.utc)
    if key.revoked_at is not None:
        raise unauthorized("API key has been revoked.")
    if key.expires_at is not None and key.expires_at <= now:
        raise unauthorized("API key has expired.")
    if not ip_allowed(client_ip, key.ip_allowlist):
        raise permission_denied("Client IP is not allowed for this API key.")
    agent = await store.get_agent(key.agent_id)
    return AuthContext(key=key, agent=agent, client_ip=client_ip)


def require_auth_scope(auth: AuthContext, scope: str) -> AuthContext:
    if scope not in auth.key.scopes:
        raise permission_denied(f"Missing required scope: {scope}")
    return auth
