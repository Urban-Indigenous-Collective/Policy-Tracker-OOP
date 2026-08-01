import os

from llm.gateway import GatewayProvider
from llm.openai_compat import OpenAICompatProvider


def get_llm_provider():
    gateway_url = os.getenv("LLM_GATEWAY_URL")
    if gateway_url:
        return GatewayProvider(gateway_url=gateway_url)
    return OpenAICompatProvider()
