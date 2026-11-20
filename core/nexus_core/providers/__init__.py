"""NEXUS Multi-Provider AI Package."""

from core.nexus_core.providers.base import (
    BaseAIProvider,
    ProviderCompletionRequest,
    ProviderCompletionResponse,
    ProviderConfig,
    ProviderStreamChunk,
    ProviderUsageMetadata,
    ProviderVerificationResult,
)
from core.nexus_core.providers.claude import AnthropicClaudeProvider
from core.nexus_core.providers.credentials import CredentialStore
from core.nexus_core.providers.custom import CustomProvider
from core.nexus_core.providers.gemini import GoogleGeminiProvider
from core.nexus_core.providers.openai_compatible import OpenAICompatibleProvider
from core.nexus_core.providers.openai_provider import OpenAIProvider
from core.nexus_core.providers.registry import AIProviderManager, build_provider_instance

__all__ = [
    "AIProviderManager",
    "AnthropicClaudeProvider",
    "BaseAIProvider",
    "CredentialStore",
    "CustomProvider",
    "GoogleGeminiProvider",
    "OpenAICompatibleProvider",
    "OpenAIProvider",
    "ProviderCompletionRequest",
    "ProviderCompletionResponse",
    "ProviderConfig",
    "ProviderStreamChunk",
    "ProviderUsageMetadata",
    "ProviderVerificationResult",
    "build_provider_instance",
]
