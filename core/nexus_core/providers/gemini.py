"""Independent Google Gemini AI Provider Module."""

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

GEMINI_ACTIVE_MODELS: tuple[str, ...] = (
    "gemini-4-hydrogen",
    "gemini-4-argon",
    "gemini-4-carbon",
    "gemini-3.1-flash-lite",
)


class GoogleGeminiProvider(BaseAIProvider):
    """Google Gemini API adapter (v1beta REST with x-goog-api-key header auth)."""

    provider_kind = AIProviderKind.GOOGLE_GEMINI
    supports_streaming = True
    supports_tool_calling = True
    requires_credential = True

    def available_models(self) -> list[str]:
        models = list(GEMINI_ACTIVE_MODELS)
        if self.config.model_id and self.config.model_id not in models:
            models.insert(0, self.config.model_id)
        return models

    def _base_url(self) -> str:
        raw = self.config.endpoint_url.strip().rstrip("/")
        if not raw or raw.startswith("/api/"):
            return "https://generativelanguage.googleapis.com/v1beta"
        return raw

    def _require_key(self, vault: CredentialStore) -> str:
        secret = vault.resolve_secret(self.config.credential_ref)
        if not secret:
            raise ProviderAuthError(
                f"Google Gemini credential '{self.config.credential_ref}' is not configured.",
                details={"providerId": self.config.id, "credentialRef": self.config.credential_ref},
            )
        return secret

    def _build_payload(self, request: ProviderCompletionRequest) -> dict[str, Any]:
        contents: list[dict[str, Any]] = []
        for msg in request.messages:
            role = "model" if msg.get("role") == "assistant" else "user"
            text = str(msg.get("content", ""))
            contents.append({"role": role, "parts": [{"text": text}]})

        payload: dict[str, Any] = {"contents": contents}
        if request.system_instruction:
            payload["systemInstruction"] = {
                "parts": [{"text": request.system_instruction}]
            }
        if request.tools:
            payload["tools"] = [{"functionDeclarations": request.tools}]
        if request.max_tokens is not None:
            payload["generationConfig"] = {"maxOutputTokens": int(request.max_tokens)}
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
                message="Gemini credential reference is not populated in environment or vault.",
            )

        url = f"{self._base_url()}/models/{self.config.model_id}"
        try:
            status, body, latency = await http_json_request(
                method="GET",
                url=url,
                headers={"x-goog-api-key": secret},
                timeout=min(self.config.timeout_seconds, 15.0),
            )
            return ProviderVerificationResult(
                provider_id=self.config.id,
                kind=self.provider_kind.value,
                verified=200 <= status < 300,
                status=NexusStatus.CONNECTED if 200 <= status < 300 else NexusStatus.FAILED,
                credential_configured=True,
                model_id=str(body.get("name", self.config.model_id)).split("/")[-1],
                latency_ms=latency,
                message=f"Verified Gemini model endpoint ({self.config.model_id}).",
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
        model = request.model or self.config.model_id
        url = f"{self._base_url()}/models/{model}:generateContent"
        _, body, latency = await http_json_request(
            method="POST",
            url=url,
            headers={"x-goog-api-key": secret},
            body=self._build_payload(request),
            timeout=self.config.timeout_seconds,
        )
        candidates = body.get("candidates") or []
        if not candidates:
            raise ProviderUpstreamError(
                "Gemini response contained no candidates.",
                details={"model": model},
            )
        first = candidates[0]
        parts = first.get("content", {}).get("parts", [])
        text_chunks: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        for part in parts:
            if isinstance(part, dict):
                if "text" in part:
                    text_chunks.append(str(part["text"]))
                elif "functionCall" in part:
                    tool_calls.append(dict(part["functionCall"]))

        usage_raw = body.get("usageMetadata", {})
        usage = ProviderUsageMetadata(
            prompt_tokens=int(usage_raw.get("promptTokenCount", 0)),
            completion_tokens=int(usage_raw.get("candidatesTokenCount", 0)),
            total_tokens=int(usage_raw.get("totalTokenCount", 0)),
            latency_ms=latency,
        )
        return ProviderCompletionResponse(
            provider_id=self.config.id,
            provider_kind=self.provider_kind.value,
            model=model,
            content="".join(text_chunks),
            finish_reason=str(first.get("finishReason", "STOP")),
            tool_calls=tool_calls,
            usage=usage,
            metadata={"modelVersion": body.get("modelVersion", model)},
        )

    async def stream(
        self, request: ProviderCompletionRequest, vault: CredentialStore
    ) -> AsyncIterator[ProviderStreamChunk]:
        secret = self._require_key(vault)
        model = request.model or self.config.model_id
        url = f"{self._base_url()}/models/{model}:streamGenerateContent?alt=sse"
        async for line in http_sse_line_stream(
            method="POST",
            url=url,
            headers={"x-goog-api-key": secret},
            body=self._build_payload(request),
            timeout=self.config.timeout_seconds,
        ):
            if not line.startswith("data:"):
                continue
            raw_json = line[5:].strip()
            if not raw_json or raw_json == "[DONE]":
                continue
            try:
                chunk_data = json.loads(raw_json)
            except json.JSONDecodeError:
                continue
            candidates = chunk_data.get("candidates") or []
            delta = ""
            finish_reason = None
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                delta = "".join(str(p.get("text", "")) for p in parts if isinstance(p, dict))
                finish_reason = candidates[0].get("finishReason")
            usage = None
            if "usageMetadata" in chunk_data:
                u = chunk_data["usageMetadata"]
                usage = ProviderUsageMetadata(
                    prompt_tokens=int(u.get("promptTokenCount", 0)),
                    completion_tokens=int(u.get("candidatesTokenCount", 0)),
                    total_tokens=int(u.get("totalTokenCount", 0)),
                )
            yield ProviderStreamChunk(
                delta_text=delta,
                done=bool(finish_reason),
                finish_reason=finish_reason,
                usage=usage,
            )
