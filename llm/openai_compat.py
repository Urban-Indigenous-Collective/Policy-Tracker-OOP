import json
import os
import re

from openai import OpenAI


class DocTooLargeError(ValueError):
    """Raised when prompt tokens exceed the configured LLM context window."""

    def __init__(
        self,
        message: str,
        *,
        estimated_tokens: int | None = None,
        n_prompt_tokens: int | None = None,
        n_ctx: int | None = None,
        char_len: int | None = None,
    ):
        super().__init__(message)
        self.code = "doc_too_large"
        self.estimated_tokens = estimated_tokens
        self.n_prompt_tokens = n_prompt_tokens
        self.n_ctx = n_ctx
        self.char_len = char_len


def estimate_prompt_tokens(system: str, user: str) -> int:
    """Rough token estimate (chars/4) for preflight context checks."""
    return max(1, (len(system or "") + len(user or "") + 32) // 4)


def llm_max_context_tokens() -> int:
    try:
        # Default matches deploy/qwen36-llama-server.service (-c 131072 -np 1).
        return int(os.getenv("LLM_MAX_CONTEXT_TOKENS", "131072"))
    except ValueError:
        return 131072


def raise_if_prompt_too_large(system: str, user: str) -> None:
    """Fail closed before calling the model when the prompt cannot fit in ctx."""
    estimated = estimate_prompt_tokens(system, user)
    n_ctx = llm_max_context_tokens()
    # Reserve headroom for the completion JSON.
    usable = max(1024, n_ctx - int(os.getenv("LLM_COMPLETION_RESERVE_TOKENS", "2048")))
    if estimated > usable:
        raise DocTooLargeError(
            f"doc_too_large: estimated prompt {estimated} tokens exceeds usable "
            f"context {usable} (n_ctx={n_ctx})",
            estimated_tokens=estimated,
            n_ctx=n_ctx,
            char_len=len(system or "") + len(user or ""),
        )


def _doc_too_large_from_api_error(exc: BaseException) -> DocTooLargeError | None:
    text = f"{type(exc).__name__} {exc}"
    lowered = text.lower()
    if "exceed_context_size_error" not in lowered and "exceeds the available context" not in lowered:
        return None
    n_prompt = None
    n_ctx = None
    match_prompt = re.search(r"n_prompt_tokens['\":\s]+(\d+)", text)
    match_ctx = re.search(r"n_ctx['\":\s]+(\d+)", text)
    if match_prompt:
        n_prompt = int(match_prompt.group(1))
    if match_ctx:
        n_ctx = int(match_ctx.group(1))
    request_match = re.search(r"request \((\d+) tokens\)", text)
    if n_prompt is None and request_match:
        n_prompt = int(request_match.group(1))
    return DocTooLargeError(
        f"doc_too_large: request ({n_prompt or '?'} tokens) exceeds context "
        f"({n_ctx or llm_max_context_tokens()} tokens)",
        n_prompt_tokens=n_prompt,
        n_ctx=n_ctx or llm_max_context_tokens(),
    )


class OpenAICompatProvider:
    """OpenAI-compatible backend (Ollama, vLLM, OpenAI, etc.)."""

    def __init__(self, base_url=None, model=None, api_key=None):
        self.base_url = (
            base_url
            or os.getenv("LLM_BASE_URL")
            or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        )
        self._model = (
            model
            or os.getenv("LLM_MODEL")
            or os.getenv("OLLAMA_MODEL", "qwen2.5vl:32b")
        )
        self.api_key = (
            api_key
            or os.getenv("LLM_API_KEY")
            or os.getenv("OLLAMA_API_KEY", "ollama")
        )
        self.temperature = float(os.getenv("LLM_TEMPERATURE", "0"))
        self.seed = int(os.getenv("LLM_SEED", "42"))
        self.client = OpenAI(base_url=self.base_url, api_key=self.api_key)

    @property
    def model(self) -> str:
        return self._model

    def _chat_kwargs(self, messages, json_mode=False):
        kwargs = {
            "model": self._model,
            "messages": messages,
            "temperature": self.temperature,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        extra_body = {"options": {"temperature": self.temperature, "seed": self.seed}}
        kwargs["extra_body"] = extra_body
        return kwargs

    @staticmethod
    def _parse_json_content(content: str) -> dict:
        content = content.strip()
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if match:
                return json.loads(match.group())
            raise ValueError(f"Model did not return valid JSON: {content[:200]}")

    def complete_json(self, system: str, user: str, schema: dict | None = None) -> dict:
        schema_hint = ""
        if schema:
            schema_hint = f"\n\nRespond with JSON matching this schema:\n{json.dumps(schema, indent=2)}"
        full_system = system + schema_hint
        raise_if_prompt_too_large(full_system, user)
        messages = [
            {"role": "system", "content": full_system},
            {"role": "user", "content": user},
        ]
        try:
            try:
                response = self.client.chat.completions.create(
                    **self._chat_kwargs(messages, json_mode=True)
                )
            except Exception as first:
                mapped = _doc_too_large_from_api_error(first)
                if mapped:
                    raise mapped from first
                response = self.client.chat.completions.create(
                    **self._chat_kwargs(messages, json_mode=False)
                )
        except Exception as exc:
            mapped = _doc_too_large_from_api_error(exc)
            if mapped:
                raise mapped from exc
            raise
        content = response.choices[0].message.content or "{}"
        return self._parse_json_content(content)

    def complete_text(self, system: str, user: str) -> str:
        raise_if_prompt_too_large(system, user)
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        try:
            response = self.client.chat.completions.create(**self._chat_kwargs(messages, json_mode=False))
        except Exception as exc:
            mapped = _doc_too_large_from_api_error(exc)
            if mapped:
                raise mapped from exc
            raise
        return response.choices[0].message.content or ""

    def complete_vision(self, prompt: str, image_b64: str) -> str:
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                    },
                ],
            }
        ]
        response = self.client.chat.completions.create(**self._chat_kwargs(messages, json_mode=False))
        return response.choices[0].message.content or ""
