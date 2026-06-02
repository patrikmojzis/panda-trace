from __future__ import annotations

from pathlib import Path

from panda_trace.errors import APIError


ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT / "docs"
LLMS_FULL_DOCS = [
    "quickstart.md",
    "api-reference.md",
    "authentication.md",
    "log-ingestion.md",
    "search.md",
    "tailing.md",
    "export.md",
    "attachments.md",
    "errors.md",
    "limits.md",
    "tenancy.md",
]


def read_doc(name: str) -> str:
    path = (DOCS_DIR / name).resolve()
    if DOCS_DIR.resolve() not in path.parents and path != DOCS_DIR.resolve():
        raise APIError(404, "not_found", "Doc not found.")
    if not path.exists() or not path.is_file():
        raise APIError(404, "not_found", "Doc not found.")
    return path.read_text(encoding="utf-8")


def render_llms_txt(public_base_url: str) -> str:
    return read_doc("llms.txt").replace("{{PUBLIC_BASE_URL}}", public_base_url)


def render_llms_full_txt(public_base_url: str) -> str:
    parts = [render_llms_txt(public_base_url)]
    parts.extend(read_doc(name) for name in LLMS_FULL_DOCS)
    return "\n\n---\n\n".join(parts)
