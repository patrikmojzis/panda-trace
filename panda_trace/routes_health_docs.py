from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse

from panda_trace.config import Settings
from panda_trace.dependencies import get_settings, get_store
from panda_trace.docs_content import read_doc, render_llms_full_txt, render_llms_txt
from panda_trace.responses import envelope
from panda_trace.store_interface import LogStore


router = APIRouter()


@router.get("/healthz", tags=["health"])
async def healthz() -> dict[str, Any]:
    return envelope({"status": "ok"})


@router.get("/readyz", tags=["health"])
async def readyz(store: LogStore = Depends(get_store)) -> dict[str, Any]:
    return envelope(await store.ready())


@router.get("/llms.txt", response_class=PlainTextResponse, tags=["docs"])
async def llms_txt(settings: Settings = Depends(get_settings)) -> str:
    return render_llms_txt(settings.public_base_url)


@router.get("/llms-full.txt", response_class=PlainTextResponse, tags=["docs"])
async def llms_full_txt(settings: Settings = Depends(get_settings)) -> str:
    return render_llms_full_txt(settings.public_base_url)


@router.get("/docs/{doc_name:path}", response_class=PlainTextResponse, tags=["docs"])
async def markdown_doc(doc_name: str) -> str:
    return read_doc(doc_name)
