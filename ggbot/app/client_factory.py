from __future__ import annotations

from .config import Settings
from ..providers.litellm_client import LiteLLMClient
from ..providers.types import ChatCompletionClient


def make_llm_client(settings: Settings) -> ChatCompletionClient:
    # LiteLLM supports many providers; credential discovery is typically via env vars.
    # We still pass OPENAI_* settings as defaults because they are useful for
    # OpenAI and OpenAI-compatible gateways.
    return LiteLLMClient(
        model=settings.openai_model,
        api_base=settings.openai_base_url,
        api_key=settings.openai_api_key,
    )
