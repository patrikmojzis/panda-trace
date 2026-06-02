from __future__ import annotations

import pytest

from panda_trace.docs_content import read_doc, render_llms_full_txt, render_llms_txt
from panda_trace.errors import APIError


def test_docs_content_renders_llms_documents() -> None:
    llms = render_llms_txt("https://trace.example.test")
    assert "Panda Trace" in llms
    assert "https://trace.example.test/openapi.json" in llms

    full = render_llms_full_txt("https://trace.example.test")
    assert "Quickstart" in full
    assert "Authentication" in full


def test_docs_content_blocks_path_traversal() -> None:
    assert "Search" in read_doc("search.md")

    with pytest.raises(APIError) as exc:
        read_doc("../README.md")
    assert exc.value.code == "not_found"
