from __future__ import annotations

from dataclasses import asdict
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header

from panda_trace.config import Settings
from panda_trace.dependencies import get_settings, get_store, require_scope
from panda_trace.errors import permission_denied
from panda_trace.models import AuthContext
from panda_trace.representations import api_key_public_dict
from panda_trace.responses import envelope
from panda_trace.schemas import (
    CreateAgentRequest,
    CreateApiKeyRequest,
    CreateOrgRequest,
    CreateProjectRequest,
    CreateSourceRequest,
)
from panda_trace.store_interface import LogStore


router = APIRouter()


@router.post("/v1/orgs", tags=["control-plane"])
async def create_org(
    payload: CreateOrgRequest,
    x_bootstrap_token: Annotated[str | None, Header(alias="X-Bootstrap-Token")] = None,
    store: LogStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    if settings.env == "prod" or settings.bootstrap_token:
        if not settings.bootstrap_token:
            raise permission_denied("Org bootstrap is disabled until BOOTSTRAP_TOKEN is configured.")
        if x_bootstrap_token != settings.bootstrap_token:
            raise permission_denied("Invalid bootstrap token.")
    org, agent, key, secret = await store.create_org_bootstrap(payload.name, payload.owner_agent_name)
    return envelope(
        {
            "org": asdict(org),
            "owner_agent": asdict(agent),
            "api_key": api_key_public_dict(key) | {"secret": secret},
        },
        {"secret_returned_once": True},
    )


@router.post("/v1/projects", tags=["control-plane"])
async def create_project(
    payload: CreateProjectRequest,
    auth: AuthContext = Depends(require_scope("projects:write")),
    store: LogStore = Depends(get_store),
) -> dict[str, Any]:
    project = await store.create_project(auth, payload.org_id, payload.name)
    return envelope(asdict(project))


@router.post("/v1/sources", tags=["control-plane"])
async def create_source(
    payload: CreateSourceRequest,
    auth: AuthContext = Depends(require_scope("sources:write")),
    store: LogStore = Depends(get_store),
) -> dict[str, Any]:
    source = await store.create_source(auth, payload.project_id, payload.name, payload.slug)
    return envelope(asdict(source))


@router.get("/v1/sources", tags=["control-plane"])
async def list_sources(
    project_id: str | None = None,
    auth: AuthContext = Depends(require_scope("sources:read")),
    store: LogStore = Depends(get_store),
) -> dict[str, Any]:
    sources = await store.list_sources(auth, project_id)
    return envelope([asdict(source) for source in sources])


@router.post("/v1/agents", tags=["control-plane"])
async def create_agent(
    payload: CreateAgentRequest,
    auth: AuthContext = Depends(require_scope("agents:write")),
    store: LogStore = Depends(get_store),
) -> dict[str, Any]:
    agent = await store.create_agent(auth, payload.org_id, payload.name)
    return envelope(asdict(agent))


@router.post("/v1/api-keys", tags=["control-plane"])
async def create_api_key(
    payload: CreateApiKeyRequest,
    auth: AuthContext = Depends(require_scope("keys:write")),
    store: LogStore = Depends(get_store),
) -> dict[str, Any]:
    key, secret = await store.create_api_key(
        auth,
        agent_id=payload.agent_id,
        org_id=payload.org_id,
        project_ids=payload.project_ids,
        source_ids=payload.source_ids,
        scopes=payload.scopes,
        ip_allowlist=payload.ip_allowlist,
        expires_at=payload.expires_at,
    )
    return envelope(api_key_public_dict(key) | {"secret": secret}, {"secret_returned_once": True})


@router.delete("/v1/api-keys/{key_id}", tags=["control-plane"])
async def revoke_api_key(
    key_id: str,
    auth: AuthContext = Depends(require_scope("keys:write")),
    store: LogStore = Depends(get_store),
) -> dict[str, Any]:
    key = await store.revoke_api_key(auth, key_id)
    return envelope(api_key_public_dict(key))
