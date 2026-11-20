"""Independent OpenAI-Compatible AI Provider Module (Ollama, vLLM, LM Studio, OpenRouter)."""

from __future__ import annotations

from core.nexus_core.providers.openai_provider import OpenAIProvider
from sdk.python.nexus_sdk import AIProviderKind


class OpenAICompatibleProvider(OpenAIProvider):
    """OpenAI Chat Completions compatible adapter for local or third-party inference servers."""

    provider_kind = AIProviderKind.OPENAI_COMPATIBLE
    supports_streaming = True
    supports_tool_calling = True
    requires_credential = False

    def available_models(self) -> list[str]:
        return [self.config.model_id] if self.config.model_id else ["local-model"]
