from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from panda_trace.auth import authenticate_request, require_auth_scope
from panda_trace.errors import APIError
from panda_trace.store import InMemoryStore


def test_authenticate_request_builds_context_and_enforces_scope() -> None:
    async def check() -> None:
        store = InMemoryStore()
        org, agent, key, secret = await store.create_org_bootstrap("Acme", "owner")

        auth = await authenticate_request(
            store=store,
            authorization=f"Bearer {secret}",
            client_ip="127.0.0.1",
        )

        assert auth.key.id == key.id
        assert auth.agent.id == agent.id
        assert auth.key.org_id == org.id
        assert require_auth_scope(auth, "logs:write") is auth

        with pytest.raises(APIError) as exc:
            require_auth_scope(auth, "nope")
        assert exc.value.code == "permission_denied"

    asyncio.run(check())


def test_authenticate_request_rejects_bad_expired_and_ip_blocked_keys() -> None:
    async def check() -> None:
        store = InMemoryStore()
        _, _, key, secret = await store.create_org_bootstrap("Acme", "owner")

        with pytest.raises(APIError) as exc:
            await authenticate_request(store=store, authorization=None, client_ip="127.0.0.1")
        assert exc.value.code == "unauthorized"

        key.expires_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        with pytest.raises(APIError) as exc:
            await authenticate_request(store=store, authorization=f"Bearer {secret}", client_ip="127.0.0.1")
        assert exc.value.message == "API key has expired."

        key.expires_at = None
        key.ip_allowlist = ["203.0.113.0/24"]
        with pytest.raises(APIError) as exc:
            await authenticate_request(store=store, authorization=f"Bearer {secret}", client_ip="127.0.0.1")
        assert exc.value.code == "permission_denied"

    asyncio.run(check())
