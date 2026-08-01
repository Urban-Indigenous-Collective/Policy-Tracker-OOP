"""Backward-compatible wrapper; prefer get_llm_provider() from llm.factory."""

from llm.factory import get_llm_provider


class LLMClient:
    def __init__(self, base_url=None, model=None):
        self._provider = get_llm_provider()
        if base_url or model:
            from llm.openai_compat import OpenAICompatProvider
            self._provider = OpenAICompatProvider(base_url=base_url, model=model)

    def reset_context(self):
        pass

    def get_chat_response(self, message):
        return self._provider.complete_text(
            "You are a precise legislative analysis assistant.",
            message,
        )

    def get_vision_response(self, prompt, image_base64):
        return self._provider.complete_vision(prompt, image_base64)

    @property
    def provider(self):
        return self._provider
