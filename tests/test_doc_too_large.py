"""Preflight and API mapping for documents that exceed LLM context."""

import pytest

from llm.openai_compat import (
    DocTooLargeError,
    _doc_too_large_from_api_error,
    raise_if_prompt_too_large,
)


def test_raise_if_prompt_too_large(monkeypatch):
    monkeypatch.setenv("LLM_MAX_CONTEXT_TOKENS", "1000")
    monkeypatch.setenv("LLM_COMPLETION_RESERVE_TOKENS", "100")
    with pytest.raises(DocTooLargeError) as exc:
        raise_if_prompt_too_large("system", "x" * 5000)
    assert exc.value.code == "doc_too_large"
    assert exc.value.n_ctx == 1000


def test_map_llama_server_exceed_context_error():
    err = Exception(
        "Error code: 400 - {'error': {'code': 400, 'message': "
        "'request (77777 tokens) exceeds the available context size (32768 tokens), "
        "try increasing it', 'type': 'exceed_context_size_error', "
        "'n_prompt_tokens': 77777, 'n_ctx': 32768}}"
    )
    mapped = _doc_too_large_from_api_error(err)
    assert mapped is not None
    assert mapped.code == "doc_too_large"
    assert mapped.n_prompt_tokens == 77777
    assert mapped.n_ctx == 32768
