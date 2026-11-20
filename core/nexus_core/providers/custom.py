"""Independent Custom AI Provider Module."""

from __future__ import annotations

from collections.abc import AsyncIterator
import json
from typing import Any

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


class CustomProvider(BaseAIProvider):
    """Flexible HTTP JSON / SSE adapter for user-defined inference endpoints."""

    provider_kind = AIProviderKind.CUSTOM
    supports_streaming = True
    supports_tool_calling = False
    requires_credential = False

    def available_models(self) -> list[str]:
        return [self.config.model_id] if self.config.model_id else ["custom-model"]

    def _headers(self, vault: CredentialStore) -> dict[str, str]:
        headers: dict[str, str] = {}
        secret = (
            vault.resolve_secret(self.config.credential_ref)
            if self.config.credential_ref
            else None
        )
        if secret:
            header_name = str(self.config.options.get("authHeader", "Authorization"))
            prefix = str(self.config.options.get("authPrefix", "Bearer "))
            headers[header_name] = f"{prefix}{secret}" if prefix else secret
        extra = self.config.options.get("extraHeaders")
        if isinstance(extra, dict):
            for k, v in extra.items():
                headers[str(k)] = str(v)
        return headers

    def _build_url(self, suffix: str) -> str:
        base = self.config.endpoint_url.strip().rstrip("/")
        if not suffix:
            return base
        return f"{base}/{suffix.lstrip('/')}"

    async def verify_connection(
        self, vault: CredentialStore
    ) -> ProviderVerificationResult:
        health_path = str(self.config.options.get("healthPath", ""))
        url = self._build_url(health_path)
        cred_configured = bool(
            self.config.credential_ref
            and vault.resolve_secret(self.config.credential_ref) is not None
        )
        try:
            status, _, latency = await http_json_request(
                method="GET",
                url=url,
                headers=self._headers(vault),
                timeout=min(self.config.timeout_seconds, 15.0),
            )
            ok = 200 <= status < 300
            return ProviderVerificationResult(
                provider_id=self.config.id,
                kind=self.provider_kind.value,
                verified=ok,
                status=NexusStatus.CONNECTED if ok else NexusStatus.FAILED,
                credential_configured=cred_configured,
                model_id=self.config.model_id,
                latency_ms=latency,
                message=f"Custom endpoint responded with HTTP {status}.",
            )
        except Exception as exc:
            return ProviderVerificationResult(
                provider_id=self.config.id,
                kind=self.provider_kind.value,
                verified=False,
                status=NexusStatus.DISCONNECTED,
                credential_configured=cred_configured,
                model_id=self.config.model_id,
                latency_ms=None,
                message=str(exc),
            )

    async def generate(
        self, request: ProviderCompletionRequest, vault: CredentialStore
    ) -> ProviderCompletionResponse:
        chat_path = str(self.config.options.get("chatPath", ""))
        url = self._build_url(chat_path)
        body: dict[str, Any] = {
            "model": request.model or self.config.model_id,
            "messages": request.messages,
            "systemInstruction": request.system_instruction,
            "stream": False,
        }
        _, res, latency = await http_json_request(
            method="POST",
            url=url,
            headers=self._headers(vault),
            body=body,
            timeout=self.config.timeout_seconds,
        )
        text = str(
            res.get("content")
            or res.get("output")
            or res.get("text")
            or (res.get("choices") or [{}])[0].get("message", {}).get("content", "")
        )
        usage_raw = res.get("usage") if isinstance(res.get("usage"), dict) else {}
        return ProviderCompletionResponse(
            provider_id=self.config.id,
            provider_kind=self.provider_kind.value,
            model=str(res.get("model", request.model or self.config.model_id)),
            content=text,
            finish_reason=str(res.get("finishReason", "stop")),
            usage=ProviderUsageMetadata(
                prompt_tokens=int(usage_raw.get("prompt_tokens", usage_raw.get("promptTokens", 0))),
                completion_tokens=int(
                    usage_raw.get("completion_tokens", usage_raw.get("completionTokens", 0))
                ),
                total_tokens=int(usage_raw.get("total_tokens", usage_raw.get("totalTokens", 0))),
                latency_ms=latency,
            ),
            metadata={"endpoint": url},
        )

    async def stream(
        self, request: ProviderCompletionRequest, vault: CredentialStore
    ) -> AsyncIterator[ProviderStreamChunk]:
        chat_path = str(self.config.options.get("chatPath", ""))
        url = self._build_url(chat_path)
        body: dict[str, Any] = {
            "model": request.model or self.config.model_id,
            "messages": request.messages,
            "systemInstruction": request.system_instruction,
            "stream": True,
        }
        async for line in http_sse_line_stream(
            method="POST",
            url=url,
            headers=self._headers(vault),
            body=body,
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
                chunk = json.loads(raw_json)
            except json.JSONDecodeError:
                continue
            delta = str(chunk.get("deltaText") or chunk.get("content") or chunk.get("text") or "")
            yield ProviderStreamChunk(delta_text=delta, done=bool(chunk.get("done")))
