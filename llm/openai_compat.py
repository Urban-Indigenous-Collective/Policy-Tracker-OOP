import json
import os
import re

from openai import OpenAI


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
        messages = [
            {"role": "system", "content": system + schema_hint},
            {"role": "user", "content": user},
        ]
        try:
            response = self.client.chat.completions.create(
                **self._chat_kwargs(messages, json_mode=True)
            )
        except Exception:
            response = self.client.chat.completions.create(**self._chat_kwargs(messages, json_mode=False))
        content = response.choices[0].message.content or "{}"
        return self._parse_json_content(content)

    def complete_text(self, system: str, user: str) -> str:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        response = self.client.chat.completions.create(**self._chat_kwargs(messages, json_mode=False))
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
