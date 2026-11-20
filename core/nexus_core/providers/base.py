"""NEXUS Shared AI Provider Interface & Async HTTP Transport Helpers."""

from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
from collections.abc import AsyncIterator
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from core.nexus_core.errors import (
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderUpstreamError,
    ValidationError,
)
from core.nexus_core.providers.credentials import CredentialStore
from sdk.python.nexus_sdk import AIProviderKind, NexusStatus


@dataclass(slots=True)
class ProviderConfig:
    id: str
    name: str
    kind: AIProviderKind
    enabled: bool
    model_id: str
    endpoint_url: str
    credential_ref: str
    timeout_seconds: float = 30.0
    max_tokens: int = 2048
    options: dict[str, Any] = field(default_factory=dict)
    is_custom: bool = False
    notes: str = ""

    def to_safe_dict(self, vault: CredentialStore) -> dict[str, Any]:
        cred = vault.describe_credential(self.credential_ref)
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind.value,
            "enabled": self.enabled,
            "modelId": self.model_id,
            "endpointUrl": self.endpoint_url,
            "credentialRef": cred["credentialRef"],
            "credentialConfigured": cred["credentialConfigured"],
            "credentialBackend": cred["credentialBackend"],
            "timeoutSeconds": self.timeout_seconds,
            "maxTokens": self.max_tokens,
            "options": self.options,
            "isCustom": self.is_custom,
            "notes": self.notes,
        }


@dataclass(slots=True)
class ProviderCompletionRequest:
    messages: list[dict[str, Any]]
    model: str | None = None
    system_instruction: str | None = None
    tools: list[dict[str, Any]] | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    stream: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ProviderUsageMetadata:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ProviderCompletionResponse:
    provider_id: str
    provider_kind: str
    model: str
    content: str
    finish_reason: str = "stop"
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    usage: ProviderUsageMetadata = field(default_factory=ProviderUsageMetadata)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "providerId": self.provider_id,
            "providerKind": self.provider_kind,
            "model": self.model,
            "content": self.content,
            "finishReason": self.finish_reason,
            "toolCalls": self.tool_calls,
            "usage": self.usage.to_dict(),
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class ProviderStreamChunk:
    delta_text: str
    done: bool = False
    finish_reason: str | None = None
    usage: ProviderUsageMetadata | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "deltaText": self.delta_text,
            "done": self.done,
            "finishReason": self.finish_reason,
            "usage": self.usage.to_dict() if self.usage else None,
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class ProviderVerificationResult:
    provider_id: str
    kind: str
    verified: bool
    status: NexusStatus
    credential_configured: bool
    model_id: str
    latency_ms: int | None
    message: str
    checked_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "providerId": self.provider_id,
            "kind": self.kind,
            "verified": self.verified,
            "status": self.status.value,
            "credentialConfigured": self.credential_configured,
            "modelId": self.model_id,
            "latencyMs": self.latency_ms,
            "message": self.message,
            "checkedAt": self.checked_at,
        }


async def http_json_request(
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    body: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> tuple[int, dict[str, Any], int]:
    """Performs an async HTTP/HTTPS JSON request via stdlib urllib in a worker thread."""
    if not (url.startswith("http://") or url.startswith("https://")):
        raise ValidationError(
            "Provider endpointUrl must use http:// or https://.",
            details={"endpointUrl": url},
        )

    def _call() -> tuple[int, dict[str, Any], int]:
        started = time.perf_counter()
        encoded_body = (
            json.dumps(body, ensure_ascii=True).encode("utf-8")
            if body is not None
            else None
        )
        req_headers = {"Accept": "application/json", **headers}
        if encoded_body is not None:
            req_headers.setdefault("Content-Type", "application/json")
        req = Request(url=url, data=encoded_body, headers=req_headers, method=method.upper())
        try:
            with urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                elapsed = int((time.perf_counter() - started) * 1000)
                parsed = json.loads(raw) if raw.strip() else {}
                return int(resp.status), parsed if isinstance(parsed, dict) else {"data": parsed}, elapsed
        except HTTPError as exc:
            elapsed = int((time.perf_counter() - started) * 1000)
            raw_err = exc.read().decode("utf-8", errors="replace")
            try:
                err_json = json.loads(raw_err)
            except json.JSONDecodeError:
                err_json = {"message": raw_err or exc.reason}
            if exc.code in {401, 403}:
                raise ProviderAuthError(
                    f"Provider authentication rejected with HTTP {exc.code}.",
                    details={"statusCode": exc.code, "upstream": err_json},
                ) from exc
            if exc.code == 429:
                raise ProviderRateLimitError(
                    "Provider rate limit exceeded (HTTP 429).",
                    details={"statusCode": 429, "upstream": err_json},
                ) from exc
            raise ProviderUpstreamError(
                f"Provider upstream returned HTTP {exc.code}.",
                details={"statusCode": exc.code, "upstream": err_json},
            ) from exc
        except URLError as exc:
            raise ProviderUpstreamError(
                f"Network error contacting provider endpoint: {exc.reason}",
                details={"endpointUrl": url},
            ) from exc

    return await asyncio.to_thread(_call)


async def http_sse_line_stream(
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    body: dict[str, Any],
    timeout: float = 30.0,
) -> AsyncIterator[str]:
    """Streams SSE response lines incrementally as they arrive from upstream HTTP."""
    if not (url.startswith("http://") or url.startswith("https://")):
        raise ValidationError(
            "Provider endpointUrl must use http:// or https://.",
            details={"endpointUrl": url},
        )

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()

    def _produce() -> None:
        encoded_body = json.dumps(body, ensure_ascii=True).encode("utf-8")
        req_headers = {
            "Accept": "text/event-stream",
            "Content-Type": "application/json",
            **headers,
        }
        req = Request(url=url, data=encoded_body, headers=req_headers, method=method.upper())
        try:
            with urlopen(req, timeout=timeout) as resp:
                for raw_line in resp:
                    decoded = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
                    loop.call_soon_threadsafe(queue.put_nowait, ("line", decoded))
        except HTTPError as exc:
            if exc.code in {401, 403}:
                err: Exception = ProviderAuthError(
                    f"Provider stream authentication failed (HTTP {exc.code}).",
                    details={"statusCode": exc.code},
                )
            elif exc.code == 429:
                err = ProviderRateLimitError(
                    "Provider stream rate limited (HTTP 429).",
                    details={"statusCode": 429},
                )
            else:
                err = ProviderUpstreamError(
                    f"Provider stream returned HTTP {exc.code}.",
                    details={"statusCode": exc.code},
                )
            loop.call_soon_threadsafe(queue.put_nowait, ("error", err))
        except URLError as exc:
            err = ProviderUpstreamError(
                f"Network error streaming from provider: {exc.reason}",
                details={"endpointUrl": url},
            )
            loop.call_soon_threadsafe(queue.put_nowait, ("error", err))
        except Exception as exc:  # pragma: no cover
            loop.call_soon_threadsafe(queue.put_nowait, ("error", exc))
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, ("done", None))

    producer_task = asyncio.create_task(asyncio.to_thread(_produce))
    try:
        while True:
            kind, payload = await queue.get()
            if kind == "line":
                yield str(payload)
            elif kind == "error":
                raise payload
            elif kind == "done":
                break
    finally:
        if not producer_task.done():
            await producer_task


async def http_sse_lines(
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    body: dict[str, Any],
    timeout: float = 30.0,
) -> list[str]:
    """Reads all SSE response lines using incremental http_sse_line_stream."""
    return [
        line
        async for line in http_sse_line_stream(
            method=method,
            url=url,
            headers=headers,
            body=body,
            timeout=timeout,
        )
    ]


class BaseAIProvider(ABC):
    """Shared contract implemented by every independent AI provider module."""

    provider_kind: AIProviderKind
    supports_streaming: bool = True
    supports_tool_calling: bool = True
    requires_credential: bool = True

    def __init__(self, config: ProviderConfig) -> None:
        self.config = config

    def configure(self, config: ProviderConfig) -> None:
        self.config = config

    @abstractmethod
    def available_models(self) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    async def verify_connection(
        self, vault: CredentialStore
    ) -> ProviderVerificationResult:
        raise NotImplementedError

    @abstractmethod
    async def generate(
        self, request: ProviderCompletionRequest, vault: CredentialStore
    ) -> ProviderCompletionResponse:
        raise NotImplementedError

    @abstractmethod
    async def stream(
        self, request: ProviderCompletionRequest, vault: CredentialStore
    ) -> AsyncIterator[ProviderStreamChunk]:
        raise NotImplementedError
        yield  # pragma: no cover
