"""Independent OpenAI AI Provider Module."""

from __future__ import annotations

from collections.abc import AsyncIterator
import json
from typing import Any

from core.nexus_core.errors import ProviderAuthError, ProviderUpstreamError
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

OPENAI_DEFAULT_MODELS: tuple[str, ...] = (
    "gpt-4.1",
    "gpt-4.1-mini",
    "o4-mini",
)


class OpenAIProvider(BaseAIProvider):
    """OpenAI REST API adapter (/v1/chat/completions & /v1/models)."""

    provider_kind = AIProviderKind.OPENAI
    supports_streaming = True
    supports_tool_calling = True
    requires_credential = True

    def available_models(self) -> list[str]:
        models = list(OPENAI_DEFAULT_MODELS)
        if self.config.model_id and self.config.model_id not in models:
            models.insert(0, self.config.model_id)
        return models

    def _base_url(self) -> str:
        raw = self.config.endpoint_url.strip().rstrip("/")
        if raw.endswith("/chat/completions"):
            return raw[: -len("/chat/completions")]
        return raw or "https://api.openai.com/v1"

    def _auth_headers(self, vault: CredentialStore) -> dict[str, str]:
        secret = vault.resolve_secret(self.config.credential_ref)
        if self.requires_credential and not secret:
            raise ProviderAuthError(
                f"{self.provider_kind.value} credential '{self.config.credential_ref}' is not configured.",
                details={"providerId": self.config.id, "credentialRef": self.config.credential_ref},
            )
        headers: dict[str, str] = {}
        if secret:
            headers["Authorization"] = f"Bearer {secret}"
        extra = self.config.options.get("extraHeaders")
        if isinstance(extra, dict):
            for k, v in extra.items():
                headers[str(k)] = str(v)
        return headers

    def _build_payload(
        self, request: ProviderCompletionRequest, *, stream: bool
    ) -> dict[str, Any]:
        messages: list[dict[str, Any]] = []
        if request.system_instruction:
            messages.append({"role": "system", "content": request.system_instruction})
        for msg in request.messages:
            messages.append(
                {
                    "role": str(msg.get("role", "user")),
                    "content": str(msg.get("content", "")),
                }
            )
        payload: dict[str, Any] = {
            "model": request.model or self.config.model_id,
            "messages": messages,
            "stream": stream,
        }
        if request.max_tokens is not None:
            payload["max_tokens"] = int(request.max_tokens)
        if request.temperature is not None:
            payload["temperature"] = float(request.temperature)
        if request.tools:
            payload["tools"] = [
                {"type": "function", "function": tool} for tool in request.tools
            ]
        return payload

    async def verify_connection(
        self, vault: CredentialStore
    ) -> ProviderVerificationResult:
        secret = vault.resolve_secret(self.config.credential_ref)
        if self.requires_credential and not secret:
            return ProviderVerificationResult(
                provider_id=self.config.id,
                kind=self.provider_kind.value,
                verified=False,
                status=NexusStatus.DISCONNECTED,
                credential_configured=False,
                model_id=self.config.model_id,
                latency_ms=None,
                message="Provider credential reference is not populated in environment or vault.",
            )

        headers: dict[str, str] = {}
        if secret:
            headers["Authorization"] = f"Bearer {secret}"
        url = f"{self._base_url()}/models"
        try:
            status, body, latency = await http_json_request(
                method="GET",
                url=url,
                headers=headers,
                timeout=min(self.config.timeout_seconds, 15.0),
            )
            models_data = body.get("data")
            count_note = (
                f" ({len(models_data)} models listed)" if isinstance(models_data, list) else ""
            )
            return ProviderVerificationResult(
                provider_id=self.config.id,
                kind=self.provider_kind.value,
                verified=200 <= status < 300,
                status=NexusStatus.CONNECTED if 200 <= status < 300 else NexusStatus.FAILED,
                credential_configured=bool(secret),
                model_id=self.config.model_id,
                latency_ms=latency,
                message=f"Verified {self.provider_kind.value} /models endpoint{count_note}.",
            )
        except Exception as exc:
            return ProviderVerificationResult(
                provider_id=self.config.id,
                kind=self.provider_kind.value,
                verified=False,
                status=NexusStatus.FAILED,
                credential_configured=bool(secret),
                model_id=self.config.model_id,
                latency_ms=None,
                message=str(exc),
            )

    async def generate(
        self, request: ProviderCompletionRequest, vault: CredentialStore
    ) -> ProviderCompletionResponse:
        headers = self._auth_headers(vault)
        url = f"{self._base_url()}/chat/completions"
        _, body, latency = await http_json_request(
            method="POST",
            url=url,
            headers=headers,
            body=self._build_payload(request, stream=False),
            timeout=self.config.timeout_seconds,
        )
        choices = body.get("choices") or []
        if not choices:
            raise ProviderUpstreamError(
                f"{self.provider_kind.value} response returned no choices.",
                details={"model": request.model or self.config.model_id},
            )
        first = choices[0]
        message = first.get("message", {})
        usage_raw = body.get("usage", {})
        return ProviderCompletionResponse(
            provider_id=self.config.id,
            provider_kind=self.provider_kind.value,
            model=str(body.get("model", request.model or self.config.model_id)),
            content=str(message.get("content") or ""),
            finish_reason=str(first.get("finish_reason", "stop")),
            tool_calls=list(message.get("tool_calls") or []),
            usage=ProviderUsageMetadata(
                prompt_tokens=int(usage_raw.get("prompt_tokens", 0)),
                completion_tokens=int(usage_raw.get("completion_tokens", 0)),
                total_tokens=int(usage_raw.get("total_tokens", 0)),
                latency_ms=latency,
            ),
            metadata={"responseId": body.get("id")},
        )

    async def stream(
        self, request: ProviderCompletionRequest, vault: CredentialStore
    ) -> AsyncIterator[ProviderStreamChunk]:
        headers = self._auth_headers(vault)
        url = f"{self._base_url()}/chat/completions"
        async for line in http_sse_line_stream(
            method="POST",
            url=url,
            headers=headers,
            body=self._build_payload(request, stream=True),
            timeout=self.config.timeout_seconds,
        ):
            if not line.startswith("data:"):
                continue
            raw_json = line[5:].strip()
            if not raw_json:
                continue
            if raw_json == "[DONE]":
                yield ProviderStreamChunk(delta_text="", done=True, finish_reason="stop")
                break
            try:
                chunk_data = json.loads(raw_json)
            except json.JSONDecodeError:
                continue
            choices = chunk_data.get("choices") or []
            delta_text = ""
            finish_reason = None
            if choices:
                delta_text = str(choices[0].get("delta", {}).get("content") or "")
                finish_reason = choices[0].get("finish_reason")
            usage = None
            if isinstance(chunk_data.get("usage"), dict):
                u = chunk_data["usage"]
                usage = ProviderUsageMetadata(
                    prompt_tokens=int(u.get("prompt_tokens", 0)),
                    completion_tokens=int(u.get("completion_tokens", 0)),
                    total_tokens=int(u.get("total_tokens", 0)),
                )
            yield ProviderStreamChunk(
                delta_text=delta_text,
                done=bool(finish_reason),
                finish_reason=finish_reason,
                usage=usage,
            )
