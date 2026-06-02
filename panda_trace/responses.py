from __future__ import annotations

from typing import Any


def envelope(data: Any, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"data": data, "meta": meta or {}}
