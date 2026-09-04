from aide.llm.base import LLMProvider, LLMResponse, Message
from aide.llm.openai_provider import OpenAIProvider

__all__ = ["LLMProvider", "LLMResponse", "Message", "OpenAIProvider", "build_provider"]


def build_provider(config, usage_sink=None):
    """Fábrica: hoje só OpenAI, mas o resto do código fala com LLMProvider."""
    if config.llm.provider == "openai":
        return OpenAIProvider(config, usage_sink=usage_sink)
    raise ValueError(f"provider desconhecido: {config.llm.provider}")
