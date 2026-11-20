"""NEXUS Multi-Provider Registry & Persistent Non-Secret Manager."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timezone
import json
from typing import Any
import uuid

from core.nexus_core.errors import NotFoundError, ValidationError
from core.nexus_core.event_manager import EventManager
from core.nexus_core.providers.base import (
    BaseAIProvider,
    ProviderCompletionRequest,
    ProviderCompletionResponse,
    ProviderConfig,
    ProviderStreamChunk,
    ProviderVerificationResult,
)
from core.nexus_core.providers.claude import AnthropicClaudeProvider
from core.nexus_core.providers.credentials import CredentialStore
from core.nexus_core.providers.custom import CustomProvider
from core.nexus_core.providers.gemini import GoogleGeminiProvider
from core.nexus_core.providers.openai_compatible import OpenAICompatibleProvider
from core.nexus_core.providers.openai_provider import OpenAIProvider
from core.nexus_core.storage import SQLiteStorageManager
from sdk.python.nexus_sdk import AIProviderKind

_PROVIDER_CLASSES: dict[AIProviderKind, type[BaseAIProvider]] = {
    AIProviderKind.GOOGLE_GEMINI: GoogleGeminiProvider,
    AIProviderKind.ANTHROPIC_CLAUDE: AnthropicClaudeProvider,
    AIProviderKind.OPENAI: OpenAIProvider,
    AIProviderKind.OPENAI_COMPATIBLE: OpenAICompatibleProvider,
    AIProviderKind.CUSTOM: CustomProvider,
}


def build_provider_instance(config: ProviderConfig) -> BaseAIProvider:
    cls = _PROVIDER_CLASSES.get(config.kind)
    if cls is None:
        raise ValidationError(
            f"Unsupported AI provider kind '{config.kind.value}'.",
            details={"kind": config.kind.value},
        )
    return cls(config)


def default_provider_configs() -> list[ProviderConfig]:
    return [
        ProviderConfig(
            id="conn-gemini",
            name="Google Gemini (API)",
            kind=AIProviderKind.GOOGLE_GEMINI,
            enabled=True,
            model_id="gemini-4-hydrogen",
            endpoint_url="https://generativelanguage.googleapis.com/v1beta",
            credential_ref="env://GEMINI_API_KEY",
            is_custom=False,
            notes="Built-in Gemini API client. Independent from external MCP apps.",
        ),
        ProviderConfig(
            id="conn-claude",
            name="Anthropic Claude (API)",
            kind=AIProviderKind.ANTHROPIC_CLAUDE,
            enabled=False,
            model_id="claude-sonnet-4-20250514",
            endpoint_url="https://api.anthropic.com/v1",
            credential_ref="wincred://nexus/anthropic_api_key",
            is_custom=False,
            notes="Direct Anthropic API connection. Does not automatically connect Claude Desktop MCP.",
        ),
        ProviderConfig(
            id="conn-openai",
            name="OpenAI (API)",
            kind=AIProviderKind.OPENAI,
            enabled=False,
            model_id="gpt-4.1",
            endpoint_url="https://api.openai.com/v1",
            credential_ref="wincred://nexus/openai_api_key",
            is_custom=False,
            notes="Direct OpenAI API connection. Separate from ChatGPT/Codex MCP clients.",
        ),
        ProviderConfig(
            id="conn-openai-compat",
            name="OpenAI-Compatible (Local / Custom Base URL)",
            kind=AIProviderKind.OPENAI_COMPATIBLE,
            enabled=False,
            model_id="llama3.2",
            endpoint_url="http://127.0.0.1:11434/v1",
            credential_ref="vault://nexus/openai_compatible_key",
            is_custom=False,
            notes="Compatible with local Ollama, LM Studio, vLLM, or OpenRouter endpoints.",
        ),
    ]


class AIProviderManager:
    """Persists non-secret provider configs in SQLite and dispatches verification & inference."""

    def __init__(
        self,
        storage: SQLiteStorageManager,
        vault: CredentialStore,
        events: EventManager | None = None,
    ) -> None:
        self.storage = storage
        self.vault = vault
        self.events = events

    async def seed_defaults(self) -> None:
        existing = await self.storage.execute("SELECT id FROM ai_providers LIMIT 1")
        if existing:
            return
        for cfg in default_provider_configs():
            await self._upsert_config(cfg)

    async def _upsert_config(self, cfg: ProviderConfig) -> None:
        now = datetime.now(timezone.utc).isoformat()
        await self.storage.execute(
            """
            INSERT INTO ai_providers (
                id, name, kind, enabled, model_id, endpoint_url, credential_ref,
                options_json, is_custom, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                kind = excluded.kind,
                enabled = excluded.enabled,
                model_id = excluded.model_id,
                endpoint_url = excluded.endpoint_url,
                credential_ref = excluded.credential_ref,
                options_json = excluded.options_json,
                updated_at = excluded.updated_at
            """,
            (
                cfg.id,
                cfg.name,
                cfg.kind.value,
                1 if cfg.enabled else 0,
                cfg.model_id,
                cfg.endpoint_url,
                cfg.credential_ref,
                json.dumps(cfg.options, ensure_ascii=True),
                1 if cfg.is_custom else 0,
                now,
            ),
        )

    @staticmethod
    def _row_to_config(row: dict[str, Any]) -> ProviderConfig:
        kind = AIProviderKind(str(row["kind"]))
        try:
            options = json.loads(str(row.get("options_json") or "{}"))
            if not isinstance(options, dict):
                options = {}
        except json.JSONDecodeError:
            options = {}
        return ProviderConfig(
            id=str(row["id"]),
            name=str(row["name"]),
            kind=kind,
            enabled=bool(row["enabled"]),
            model_id=str(row["model_id"]),
            endpoint_url=str(row["endpoint_url"]),
            credential_ref=str(row["credential_ref"]),
            options=options,
            is_custom=bool(row["is_custom"]),
        )

    async def list_providers(self) -> list[dict[str, Any]]:
        rows = await self.storage.execute(
            "SELECT * FROM ai_providers ORDER BY is_custom ASC, id ASC"
        )
        items: list[dict[str, Any]] = []
        for row in rows:
            cfg = self._row_to_config(row)
            instance = build_provider_instance(cfg)
            item = cfg.to_safe_dict(self.vault)
            item["availableModels"] = instance.available_models()
            item["supportsStreaming"] = instance.supports_streaming
            item["supportsToolCalling"] = instance.supports_tool_calling
            items.append(item)
        return items

    async def get_provider_config(self, provider_id: str) -> ProviderConfig:
        rows = await self.storage.execute(
            "SELECT * FROM ai_providers WHERE id = ?", (provider_id,)
        )
        if not rows:
            raise NotFoundError(
                f"AI provider '{provider_id}' not found.",
                details={"providerId": provider_id},
            )
        return self._row_to_config(rows[0])

    async def register_provider(
        self,
        *,
        name: str,
        kind: str,
        model_id: str,
        endpoint_url: str,
        credential_ref: str,
        enabled: bool = True,
        options: dict[str, Any] | None = None,
        is_custom: bool = True,
        provider_id: str | None = None,
    ) -> dict[str, Any]:
        if not name.strip():
            raise ValidationError("Provider name cannot be empty.")
        try:
            parsed_kind = AIProviderKind(kind)
        except ValueError as exc:
            raise ValidationError(
                f"Unsupported provider kind '{kind}'.",
                details={"kind": kind},
            ) from exc
        validated_ref = self.vault.validate_credential_ref(credential_ref)
        pid = provider_id or f"conn-{uuid.uuid4().hex[:10]}"
        cfg = ProviderConfig(
            id=pid,
            name=name.strip(),
            kind=parsed_kind,
            enabled=enabled,
            model_id=model_id.strip() or "custom-model",
            endpoint_url=endpoint_url.strip(),
            credential_ref=validated_ref,
            options=options or {},
            is_custom=is_custom,
        )
        build_provider_instance(cfg)
        await self._upsert_config(cfg)
        await self.storage.record_audit("daemon", "provider.register", "success", target=pid)
        return cfg.to_safe_dict(self.vault)

    async def update_provider(
        self,
        provider_id: str,
        *,
        enabled: bool | None = None,
        model_id: str | None = None,
        endpoint_url: str | None = None,
        credential_ref: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        cfg = await self.get_provider_config(provider_id)
        if enabled is not None:
            cfg.enabled = enabled
        if model_id is not None and model_id.strip():
            cfg.model_id = model_id.strip()
        if endpoint_url is not None and endpoint_url.strip():
            cfg.endpoint_url = endpoint_url.strip()
        if credential_ref is not None:
            cfg.credential_ref = self.vault.validate_credential_ref(credential_ref)
        if options is not None:
            cfg.options = options
        await self._upsert_config(cfg)
        await self.storage.record_audit("daemon", "provider.update", "success", target=provider_id)
        return cfg.to_safe_dict(self.vault)

    async def delete_provider(self, provider_id: str) -> None:
        cfg = await self.get_provider_config(provider_id)
        if not cfg.is_custom:
            raise ValidationError(
                f"Built-in provider '{provider_id}' cannot be deleted; disable it instead.",
                details={"providerId": provider_id},
            )
        await self.storage.execute("DELETE FROM ai_providers WHERE id = ?", (provider_id,))
        if not cfg.credential_ref.startswith("env://"):
            self.vault.delete_secret(cfg.credential_ref)
        await self.storage.record_audit("daemon", "provider.delete", "success", target=provider_id)

    async def store_provider_secret(self, provider_id: str, secret: str) -> dict[str, Any]:
        cfg = await self.get_provider_config(provider_id)
        backend = self.vault.store_secret(cfg.credential_ref, secret)
        await self.storage.record_audit(
            "daemon", "provider.secret_stored", "success", target=provider_id
        )
        return {
            "providerId": provider_id,
            "credentialRef": cfg.credential_ref,
            "credentialConfigured": True,
            "credentialBackend": backend,
        }

    async def verify_provider(self, provider_id: str) -> ProviderVerificationResult:
        cfg = await self.get_provider_config(provider_id)
        instance = build_provider_instance(cfg)
        result = await instance.verify_connection(self.vault)
        await self.storage.record_audit(
            "daemon",
            "provider.verify",
            "success" if result.verified else "failed",
            target=provider_id,
            detail={"verified": result.verified, "status": result.status.value},
        )
        if self.events:
            await self.events.publish(
                "bridge.status",
                "provider_manager",
                result.to_dict(),
            )
        return result

    async def generate(
        self, provider_id: str, request: ProviderCompletionRequest
    ) -> ProviderCompletionResponse:
        cfg = await self.get_provider_config(provider_id)
        if not cfg.enabled:
            raise ValidationError(
                f"AI provider '{cfg.name}' is currently disabled.",
                details={"providerId": provider_id},
            )
        instance = build_provider_instance(cfg)
        response = await instance.generate(request, self.vault)
        await self.storage.record_audit(
            "daemon",
            "provider.generate",
            "success",
            target=provider_id,
            detail={"model": response.model, "totalTokens": response.usage.total_tokens},
        )
        return response

    async def stream(
        self, provider_id: str, request: ProviderCompletionRequest
    ) -> AsyncIterator[ProviderStreamChunk]:
        cfg = await self.get_provider_config(provider_id)
        if not cfg.enabled:
            raise ValidationError(
                f"AI provider '{cfg.name}' is currently disabled.",
                details={"providerId": provider_id},
            )
        instance = build_provider_instance(cfg)
        async for chunk in instance.stream(request, self.vault):
            yield chunk
