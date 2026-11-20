"""Independent Anthropic Claude AI Provider Module."""

from __future__ import annotations

from collections.abc import AsyncIterator
import json
from typing import Any

from core.nexus_core.errors import ProviderAuthError
from core.nexus_core.providers.base import (
    BaseAIProvider,
    ProviderCompletionRequest,
    ProviderCompletionResponse,
    ProviderStreamChunk,
    ProviderUsageMetadata,
    ProviderVerificationResult,
    http_json_request,
    http_sse_line_stream,
)
from core.nexus_core.providers.credentials import CredentialStore
from sdk.python.nexus_sdk import AIProviderKind, NexusStatus

CLAUDE_DEFAULT_MODELS: tuple[str, ...] = (
    "claude-sonnet-4-20250514",
    "claude-3-7-sonnet-latest",
    "claude-3-5-haiku-latest",
)


class AnthropicClaudeProvider(BaseAIProvider):
    """Anthropic Messages API adapter (/v1/messages with x-api-key auth)."""

    provider_kind = AIProviderKind.ANTHROPIC_CLAUDE
    supports_streaming = True
    supports_tool_calling = True
    requires_credential = True

    ANTHROPIC_VERSION = "2023-06-01"

    def available_models(self) -> list[str]:
        models = list(CLAUDE_DEFAULT_MODELS)
        if self.config.model_id and self.config.model_id not in models:
            models.insert(0, self.config.model_id)
        return models

    def _base_url(self) -> str:
        raw = self.config.endpoint_url.strip().rstrip("/")
        if raw.endswith("/messages"):
            return raw[: -len("/messages")]
        return raw or "https://api.anthropic.com/v1"

    def _require_key(self, vault: CredentialStore) -> str:
        secret = vault.resolve_secret(self.config.credential_ref)
        if not secret:
            raise ProviderAuthError(
                f"Anthropic Claude credential '{self.config.credential_ref}' is not configured.",
                details={"providerId": self.config.id, "credentialRef": self.config.credential_ref},
            )
        return secret

    def _build_payload(
        self, request: ProviderCompletionRequest, *, stream: bool
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": request.model or self.config.model_id,
            "max_tokens": int(request.max_tokens or self.config.max_tokens or 2048),
            "messages": [
                {
                    "role": "assistant" if m.get("role") == "assistant" else "user",
                    "content": str(m.get("content", "")),
                }
                for m in request.messages
            ],
            "stream": stream,
        }
        if request.system_instruction:
            payload["system"] = request.system_instruction
        if request.tools:
            payload["tools"] = request.tools
        if request.temperature is not None:
            payload["temperature"] = float(request.temperature)
        return payload

    async def verify_connection(
        self, vault: CredentialStore
    ) -> ProviderVerificationResult:
        secret = vault.resolve_secret(self.config.credential_ref)
        if not secret:
            return ProviderVerificationResult(
                provider_id=self.config.id,
                kind=self.provider_kind.value,
                verified=False,
                status=NexusStatus.DISCONNECTED,
                credential_configured=False,
                model_id=self.config.model_id,
                latency_ms=None,
                message="Anthropic credential reference is not populated in environment or vault.",
            )

        url = f"{self._base_url()}/models"
        try:
            status, _, latency = await http_json_request(
                method="GET",
                url=url,
                headers={
                    "x-api-key": secret,
                    "anthropic-version": self.ANTHROPIC_VERSION,
                },
                timeout=min(self.config.timeout_seconds, 15.0),
            )
            return ProviderVerificationResult(
                provider_id=self.config.id,
                kind=self.provider_kind.value,
                verified=200 <= status < 300,
                status=NexusStatus.CONNECTED if 200 <= status < 300 else NexusStatus.FAILED,
                credential_configured=True,
                model_id=self.config.model_id,
                latency_ms=latency,
                message="Verified Anthropic Claude API key and /v1/models endpoint.",
            )
        except Exception as exc:
            return ProviderVerificationResult(
                provider_id=self.config.id,
                kind=self.provider_kind.value,
                verified=False,
                status=NexusStatus.FAILED,
                credential_configured=True,
                model_id=self.config.model_id,
                latency_ms=None,
                message=str(exc),
            )

    async def generate(
        self, request: ProviderCompletionRequest, vault: CredentialStore
    ) -> ProviderCompletionResponse:
        secret = self._require_key(vault)
        url = f"{self._base_url()}/messages"
        _, body, latency = await http_json_request(
            method="POST",
            url=url,
            headers={
                "x-api-key": secret,
                "anthropic-version": self.ANTHROPIC_VERSION,
            },
            body=self._build_payload(request, stream=False),
            timeout=self.config.timeout_seconds,
        )
        content_blocks = body.get("content") or []
        text_chunks: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        for block in content_blocks:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    text_chunks.append(str(block.get("text", "")))
                elif block.get("type") == "tool_use":
                    tool_calls.append(
                        {
                            "id": block.get("id"),
                            "name": block.get("name"),
                            "arguments": block.get("input", {}),
                        }
                    )
        usage_raw = body.get("usage", {})
        input_tokens = int(usage_raw.get("input_tokens", 0))
        output_tokens = int(usage_raw.get("output_tokens", 0))
        return ProviderCompletionResponse(
            provider_id=self.config.id,
            provider_kind=self.provider_kind.value,
            model=str(body.get("model", request.model or self.config.model_id)),
            content="".join(text_chunks),
            finish_reason=str(body.get("stop_reason", "end_turn")),
            tool_calls=tool_calls,
            usage=ProviderUsageMetadata(
                prompt_tokens=input_tokens,
                completion_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
                latency_ms=latency,
            ),
            metadata={"messageId": body.get("id")},
        )

    async def stream(
        self, request: ProviderCompletionRequest, vault: CredentialStore
    ) -> AsyncIterator[ProviderStreamChunk]:
        secret = self._require_key(vault)
        url = f"{self._base_url()}/messages"
        async for line in http_sse_line_stream(
            method="POST",
            url=url,
            headers={
                "x-api-key": secret,
                "anthropic-version": self.ANTHROPIC_VERSION,
            },
            body=self._build_payload(request, stream=True),
            timeout=self.config.timeout_seconds,
        ):
            if not line.startswith("data:"):
                continue
            raw_json = line[5:].strip()
            if not raw_json or raw_json == "[DONE]":
                continue
            try:
                event = json.loads(raw_json)
            except json.JSONDecodeError:
                continue
            event_type = event.get("type")
            if event_type == "content_block_delta":
                delta_obj = event.get("delta", {})
                if delta_obj.get("type") == "text_delta":
                    yield ProviderStreamChunk(delta_text=str(delta_obj.get("text", "")))
            elif event_type == "message_delta":
                delta_obj = event.get("delta", {})
                usage_raw = event.get("usage", {})
                out_tok = int(usage_raw.get("output_tokens", 0))
                yield ProviderStreamChunk(
                    delta_text="",
                    done=True,
                    finish_reason=delta_obj.get("stop_reason", "end_turn"),
                    usage=ProviderUsageMetadata(completion_tokens=out_tok, total_tokens=out_tok),
                )
