from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from panda_trace.dependencies import get_store, require_scope
from panda_trace.models import AuthContext
from panda_trace.representations import audit_to_dict
from panda_trace.responses import envelope
from panda_trace.store_interface import LogStore


router = APIRouter()


@router.get("/v1/audit-logs", tags=["audit"])
async def audit_logs(
    org_id: str | None = None,
    auth: AuthContext = Depends(require_scope("audit:read")),
    store: LogStore = Depends(get_store),
) -> dict[str, Any]:
    events = await store.list_audit_logs(auth, org_id)
    return envelope([audit_to_dict(event) for event in events])
