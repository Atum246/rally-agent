"""
🟣 Rally Agent — COMPLETE Provider Registry
Every AI model provider on the planet. ALL of them.
Enhanced with: streaming, function calling, retries, rate limiting, health checks, token counting.
"""

import os
import time
import asyncio
import logging
import json
import hashlib
from typing import Optional, Any, AsyncIterator, Callable
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger("rally.providers")


# ═══════════════════════════════════════════════════════════════
# 📊 Data Types
# ═══════════════════════════════════════════════════════════════

class ProviderStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class ProviderHealth:
    """Health state of a provider."""
    status: ProviderStatus = ProviderStatus.UNKNOWN
    last_check: float = 0.0
    last_success: float = 0.0
    last_failure: float = 0.0
    consecutive_failures: int = 0
    total_requests: int = 0
    total_failures: int = 0
    avg_latency_ms: float = 0.0
    _latencies: list[float] = field(default_factory=list)

    def record_success(self, latency_ms: float) -> None:
        self.status = ProviderStatus.HEALTHY
        self.last_success = time.time()
        self.last_check = self.last_success
        self.consecutive_failures = 0
        self.total_requests += 1
        self._latencies.append(latency_ms)
        if len(self._latencies) > 100:
            self._latencies = self._latencies[-50:]
        self.avg_latency_ms = sum(self._latencies) / len(self._latencies)

    def record_failure(self) -> None:
        self.last_failure = time.time()
        self.last_check = self.last_failure
        self.consecutive_failures += 1
        self.total_requests += 1
        self.total_failures += 1
        if self.consecutive_failures >= 3:
            self.status = ProviderStatus.UNHEALTHY
        elif self.consecutive_failures >= 1:
            self.status = ProviderStatus.DEGRADED

    @property
    def failure_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.total_failures / self.total_requests

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "consecutive_failures": self.consecutive_failures,
            "total_requests": self.total_requests,
            "total_failures": self.total_failures,
            "avg_latency_ms": round(self.avg_latency_ms, 1),
            "failure_rate": round(self.failure_rate, 3),
            "last_success": self.last_success,
            "last_failure": self.last_failure,
        }


@dataclass
class TokenUsage:
    """Token usage for a single request."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def to_dict(self) -> dict:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass
class ChatResponse:
    """Structured response from a provider."""
    content: str = ""
    finish_reason: str = ""
    token_usage: Optional[TokenUsage] = None
    model: str = ""
    provider: str = ""
    tool_calls: Optional[list[dict]] = None
    latency_ms: float = 0.0

    def to_dict(self) -> dict:
        result = {
            "content": self.content,
            "finish_reason": self.finish_reason,
            "model": self.model,
            "provider": self.provider,
            "latency_ms": round(self.latency_ms, 1),
        }
        if self.token_usage:
            result["token_usage"] = self.token_usage.to_dict()
        if self.tool_calls:
            result["tool_calls"] = self.tool_calls
        return result


# ── Function / Tool definitions ─────────────────────────────

@dataclass
class ToolDefinition:
    """A tool/function that the LLM can call."""
    name: str
    description: str
    parameters: dict  # JSON Schema

    def to_openai(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def to_anthropic(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }

    def to_google(self) -> dict:
        return {
            "function_declarations": [{
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            }]
        }


# ═══════════════════════════════════════════════════════════════
# ⏱️ Rate Limiter
# ═══════════════════════════════════════════════════════════════

class RateLimiter:
    """Token bucket rate limiter for API requests."""

    def __init__(self, requests_per_minute: int = 60, tokens_per_minute: int = 100000):
        self.rpm = requests_per_minute
        self.tpm = tokens_per_minute
        self._request_times: list[float] = []
        self._token_counts: list[tuple[float, int]] = []
        self._lock = asyncio.Lock()

    async def acquire(self, estimated_tokens: int = 1000) -> None:
        """Wait until a request can proceed within rate limits."""
        async with self._lock:
            now = time.time()
            cutoff = now - 60.0

            # Clean old entries
            self._request_times = [t for t in self._request_times if t > cutoff]
            self._token_counts = [(t, c) for t, c in self._token_counts if t > cutoff]

            # Check request limit
            while len(self._request_times) >= self.rpm:
                sleep_time = self._request_times[0] - cutoff + 0.01
                await asyncio.sleep(max(sleep_time, 0.05))
                now = time.time()
                cutoff = now - 60.0
                self._request_times = [t for t in self._request_times if t > cutoff]
                self._token_counts = [(t, c) for t, c in self._token_counts if t > cutoff]

            # Check token limit
            current_tokens = sum(c for _, c in self._token_counts)
            while current_tokens + estimated_tokens > self.tpm:
                sleep_time = self._token_counts[0][0] - cutoff + 0.01
                await asyncio.sleep(max(sleep_time, 0.05))
                now = time.time()
                cutoff = now - 60.0
                self._token_counts = [(t, c) for t, c in self._token_counts if t > cutoff]
                current_tokens = sum(c for _, c in self._token_counts)

            self._request_times.append(now)
            self._token_counts.append((now, estimated_tokens))

    def update_actual_tokens(self, tokens: int) -> None:
        """Update with actual token count after request."""
        if self._token_counts:
            last_time = self._token_counts[-1][0]
            self._token_counts[-1] = (last_time, tokens)


# ═══════════════════════════════════════════════════════════════
# 🔌 Base Provider
# ═══════════════════════════════════════════════════════════════

class BaseProvider(ABC):
    """Base class for all LLM providers.

    Enhanced with: streaming, function calling, retries, rate limiting,
    health checks, token counting.
    """
    name: str = "unknown"
    description: str = ""
    requires_key: bool = True
    default_model: str = ""
    models: list[str] = []
    supports_streaming: bool = True
    supports_function_calling: bool = False
    supports_vision: bool = False
    max_context_tokens: int = 128000
    rpm_limit: int = 60
    tpm_limit: int = 100000

    def __init__(self, api_key: str = "", **kwargs: Any):
        self.api_key = api_key
        self.base_url: str = kwargs.get("base_url", "")
        self.kwargs = kwargs
        self.health = ProviderHealth()
        self.rate_limiter = RateLimiter(
            requests_per_minute=self.rpm_limit,
            tokens_per_minute=self.tpm_limit,
        )
        self._retry_max = kwargs.get("retry_max", 3)
        self._retry_base = kwargs.get("retry_base", 1.0)
        self._retry_max_delay = kwargs.get("retry_max_delay", 60.0)

    # ── Abstract ─────────────────────────────────────────────

    @abstractmethod
    async def chat(self, messages: list[dict], model: str = "", **kwargs: Any) -> str:
        """Send a chat request and return the response text."""
        ...

    async def chat_stream(
        self, messages: list[dict], model: str = "", **kwargs: Any
    ) -> AsyncIterator[str]:
        """Stream a chat response token by token. Default: falls back to non-streaming."""
        result = await self.chat(messages, model=model, **kwargs)
        yield result

    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[ToolDefinition],
        model: str = "",
        **kwargs: Any,
    ) -> ChatResponse:
        """Chat with function/tool calling support. Default: ignores tools."""
        text = await self.chat(messages, model=model, **kwargs)
        return ChatResponse(
            content=text, model=model or self.default_model, provider=self.name
        )

    async def chat_structured(
        self, messages: list[dict], model: str = "", **kwargs: Any
    ) -> ChatResponse:
        """Chat returning a structured ChatResponse with token usage."""
        start = time.time()
        text = await self.chat(messages, model=model, **kwargs)
        latency = (time.time() - start) * 1000
        usage = self._estimate_tokens(messages, text)
        return ChatResponse(
            content=text,
            model=model or self.default_model,
            provider=self.name,
            token_usage=usage,
            latency_ms=latency,
        )

    # ── Retries ──────────────────────────────────────────────

    async def _retry_call(self, coro_factory: Callable, label: str = "") -> Any:
        """Execute an async callable with exponential backoff retries."""
        last_exc: Optional[Exception] = None
        for attempt in range(self._retry_max + 1):
            try:
                result = await coro_factory()
                return result
            except (asyncio.TimeoutError, ConnectionError, OSError) as e:
                last_exc = e
                if attempt < self._retry_max:
                    delay = min(
                        self._retry_base * (2 ** attempt),
                        self._retry_max_delay,
                    )
                    logger.warning(
                        f"[{self.name}] {label} attempt {attempt + 1} failed: {e}. "
                        f"Retrying in {delay:.1f}s"
                    )
                    await asyncio.sleep(delay)
            except Exception as e:
                # Non-retryable errors
                raise
        raise last_exc  # type: ignore[misc]

    # ── Health Check ─────────────────────────────────────────

    async def health_check(self) -> ProviderStatus:
        """Run a lightweight health check against this provider."""
        try:
            start = time.time()
            await self.chat(
                [{"role": "user", "content": "ping"}],
                model=self.default_model,
                max_tokens=1,
            )
            latency = (time.time() - start) * 1000
            self.health.record_success(latency)
            return ProviderStatus.HEALTHY
        except Exception as e:
            self.health.record_failure()
            logger.warning(f"[{self.name}] Health check failed: {e}")
            return self.health.status

    # ── Token Counting ───────────────────────────────────────

    @staticmethod
    def _count_text_tokens(text: str) -> int:
        """Estimate token count. ~4 chars per token for English, ~2 for CJK-heavy."""
        if not text:
            return 0
        # Simple heuristic: count codepoints and divide by ratio
        cjk_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff' or '\u3000' <= c <= '\u303f')
        ascii_chars = len(text) - cjk_chars
        return (ascii_chars // 4) + (cjk_chars // 2) + 1

    def _estimate_tokens(self, messages: list[dict], response: str = "") -> TokenUsage:
        """Estimate token usage for a conversation."""
        prompt = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                prompt += self._count_text_tokens(content)
            elif isinstance(content, list):
                # Multimodal content
                for part in content:
                    if isinstance(part, dict) and "text" in part:
                        prompt += self._count_text_tokens(part["text"])
            # System/role overhead
            prompt += 4  # message framing tokens
        prompt += 2  # conversation priming

        completion = self._count_text_tokens(response)
        return TokenUsage(
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=prompt + completion,
        )

    # ── Helpers ──────────────────────────────────────────────

    def get_models(self) -> list[str]:
        return list(self.models)

    def is_available(self) -> bool:
        if self.requires_key:
            return bool(self.api_key)
        return True

    def get_info(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "models": self.models,
            "available": self.is_available(),
            "requires_key": self.requires_key,
            "supports_streaming": self.supports_streaming,
            "supports_function_calling": self.supports_function_calling,
            "supports_vision": self.supports_vision,
            "max_context_tokens": self.max_context_tokens,
            "health": self.health.to_dict(),
        }


# ═══════════════════════════════════════════════════════════════
# 🟢 TIER 1 — Major Cloud Providers
# ═══════════════════════════════════════════════════════════════

class OpenAIProvider(BaseProvider):
    name = "openai"
    description = "OpenAI — GPT-4o, GPT-4, o1, o3"
    default_model = "gpt-4o"
    supports_function_calling = True
    supports_vision = True
    max_context_tokens = 128000
    rpm_limit = 500
    tpm_limit = 800000
    models = [
        "gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-4", "gpt-3.5-turbo",
        "o1", "o1-mini", "o1-pro", "o3", "o3-mini", "o4-mini",
        "gpt-4o-audio-preview", "gpt-4o-realtime-preview",
        "gpt-4o-search-preview", "gpt-4o-mini-search-preview",
        "chatgpt-4o-latest",
    ]

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _format_messages(self, messages: list[dict]) -> list[dict]:
        formatted = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            entry: dict[str, Any] = {"role": role, "content": content}
            # Pass through tool_calls if present
            if "tool_calls" in m:
                entry["tool_calls"] = m["tool_calls"]
            if "tool_call_id" in m:
                entry["tool_call_id"] = m["tool_call_id"]
            if "name" in m and role == "tool":
                entry["name"] = m["name"]
            formatted.append(entry)
        return formatted

    async def chat(self, messages: list[dict], model: str = "", **kwargs: Any) -> str:
        import httpx
        model = model or self.default_model
        await self.rate_limiter.acquire()
        body: dict[str, Any] = {
            "model": model,
            "messages": self._format_messages(messages),
            "max_tokens": kwargs.get("max_tokens", 4096),
            "temperature": kwargs.get("temperature", 0.7),
        }
        resp = await self._retry_call(
            lambda: self._do_request(body, model),
            label=f"chat({model})",
        )
        return resp

    async def _do_request(self, body: dict, model: str) -> str:
        import httpx
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers=self._headers(),
                json=body,
            )
            if r.status_code == 429:
                raise ConnectionError(f"Rate limited: {r.text}")
            r.raise_for_status()
            data = r.json()
            usage = data.get("usage", {})
            if usage:
                self.rate_limiter.update_actual_tokens(usage.get("total_tokens", 0))
            return data["choices"][0]["message"]["content"] or ""

    async def chat_stream(
        self, messages: list[dict], model: str = "", **kwargs: Any
    ) -> AsyncIterator[str]:
        import httpx
        model = model or self.default_model
        await self.rate_limiter.acquire()
        body: dict[str, Any] = {
            "model": model,
            "messages": self._format_messages(messages),
            "max_tokens": kwargs.get("max_tokens", 4096),
            "temperature": kwargs.get("temperature", 0.7),
            "stream": True,
        }
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream(
                "POST",
                "https://api.openai.com/v1/chat/completions",
                headers=self._headers(),
                json=body,
            ) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    payload = line[6:]
                    if payload.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(payload)
                        delta = chunk["choices"][0].get("delta", {})
                        text = delta.get("content", "")
                        if text:
                            yield text
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue

    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[ToolDefinition],
        model: str = "",
        **kwargs: Any,
    ) -> ChatResponse:
        import httpx
        model = model or self.default_model
        await self.rate_limiter.acquire()
        start = time.time()
        body: dict[str, Any] = {
            "model": model,
            "messages": self._format_messages(messages),
            "max_tokens": kwargs.get("max_tokens", 4096),
            "temperature": kwargs.get("temperature", 0.7),
            "tools": [t.to_openai() for t in tools],
            "tool_choice": kwargs.get("tool_choice", "auto"),
        }
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers=self._headers(),
                json=body,
            )
            r.raise_for_status()
            data = r.json()
            msg = data["choices"][0]["message"]
            usage = data.get("usage", {})
            token_usage = TokenUsage(
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
            ) if usage else self._estimate_tokens(messages, msg.get("content", ""))
            return ChatResponse(
                content=msg.get("content", "") or "",
                finish_reason=data["choices"][0].get("finish_reason", ""),
                token_usage=token_usage,
                model=model,
                provider=self.name,
                tool_calls=msg.get("tool_calls"),
                latency_ms=(time.time() - start) * 1000,
            )


class AnthropicProvider(BaseProvider):
    name = "anthropic"
    description = "Anthropic — Claude 4, Claude 3.5, Claude 3"
    default_model = "claude-sonnet-4-20250514"
    supports_function_calling = True
    supports_vision = True
    max_context_tokens = 200000
    rpm_limit = 1000
    tpm_limit = 400000
    models = [
        "claude-opus-4-20250514", "claude-sonnet-4-20250514",
        "claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022",
        "claude-3-opus-20240229", "claude-3-sonnet-20240229", "claude-3-haiku-20240307",
    ]

    def _headers(self) -> dict:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

    def _format_messages(self, messages: list[dict]) -> tuple[str, list[dict]]:
        system = ""
        formatted = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            if role == "system":
                system = content
            elif role == "tool":
                formatted.append({
                    "role": "user",
                    "content": [{"type": "tool_result", "tool_use_id": m.get("tool_call_id", ""), "content": content}],
                })
            else:
                entry: dict[str, Any] = {"role": role}
                if isinstance(content, str):
                    entry["content"] = content
                else:
                    entry["content"] = content
                # Pass through tool_use blocks
                if "tool_calls" in m:
                    # Convert OpenAI-style tool_calls to Anthropic tool_use content blocks
                    blocks = []
                    if content:
                        blocks.append({"type": "text", "text": content})
                    for tc in m["tool_calls"]:
                        fn = tc.get("function", {})
                        blocks.append({
                            "type": "tool_use",
                            "id": tc.get("id", ""),
                            "name": fn.get("name", ""),
                            "input": json.loads(fn.get("arguments", "{}")) if isinstance(fn.get("arguments"), str) else fn.get("arguments", {}),
                        })
                    entry["content"] = blocks
                formatted.append(entry)
        return system, formatted

    async def chat(self, messages: list[dict], model: str = "", **kwargs: Any) -> str:
        import httpx
        model = model or self.default_model
        await self.rate_limiter.acquire()
        system, formatted = self._format_messages(messages)
        body: dict[str, Any] = {
            "model": model,
            "max_tokens": kwargs.get("max_tokens", 4096),
            "messages": formatted,
        }
        if system:
            body["system"] = system
        if "temperature" in kwargs:
            body["temperature"] = kwargs["temperature"]

        async def _do() -> str:
            async with httpx.AsyncClient(timeout=120) as client:
                r = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers=self._headers(),
                    json=body,
                )
                if r.status_code == 429:
                    raise ConnectionError(f"Rate limited: {r.text}")
                r.raise_for_status()
                data = r.json()
                # Extract usage
                u = data.get("usage", {})
                if u:
                    self.rate_limiter.update_actual_tokens(
                        u.get("input_tokens", 0) + u.get("output_tokens", 0)
                    )
                content = data.get("content", [])
                return content[0]["text"] if content else ""

        return await self._retry_call(_do, label=f"chat({model})")

    async def chat_stream(
        self, messages: list[dict], model: str = "", **kwargs: Any
    ) -> AsyncIterator[str]:
        import httpx
        model = model or self.default_model
        await self.rate_limiter.acquire()
        system, formatted = self._format_messages(messages)
        body: dict[str, Any] = {
            "model": model,
            "max_tokens": kwargs.get("max_tokens", 4096),
            "messages": formatted,
            "stream": True,
        }
        if system:
            body["system"] = system
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream(
                "POST",
                "https://api.anthropic.com/v1/messages",
                headers=self._headers(),
                json=body,
            ) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    try:
                        event = json.loads(line[6:])
                        if event.get("type") == "content_block_delta":
                            delta = event.get("delta", {})
                            if delta.get("type") == "text_delta":
                                yield delta.get("text", "")
                    except (json.JSONDecodeError, KeyError):
                        continue

    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[ToolDefinition],
        model: str = "",
        **kwargs: Any,
    ) -> ChatResponse:
        import httpx
        model = model or self.default_model
        await self.rate_limiter.acquire()
        start = time.time()
        system, formatted = self._format_messages(messages)
        body: dict[str, Any] = {
            "model": model,
            "max_tokens": kwargs.get("max_tokens", 4096),
            "messages": formatted,
            "tools": [t.to_anthropic() for t in tools],
        }
        if system:
            body["system"] = system
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers=self._headers(),
                json=body,
            )
            r.raise_for_status()
            data = r.json()
            content_blocks = data.get("content", [])
            text_parts = []
            tool_calls = []
            for block in content_blocks:
                if block.get("type") == "text":
                    text_parts.append(block["text"])
                elif block.get("type") == "tool_use":
                    tool_calls.append({
                        "id": block.get("id", ""),
                        "type": "function",
                        "function": {
                            "name": block.get("name", ""),
                            "arguments": json.dumps(block.get("input", {})),
                        },
                    })
            u = data.get("usage", {})
            token_usage = TokenUsage(
                prompt_tokens=u.get("input_tokens", 0),
                completion_tokens=u.get("output_tokens", 0),
                total_tokens=u.get("input_tokens", 0) + u.get("output_tokens", 0),
            ) if u else self._estimate_tokens(messages, " ".join(text_parts))
            return ChatResponse(
                content="\n".join(text_parts),
                finish_reason=data.get("stop_reason", ""),
                token_usage=token_usage,
                model=model,
                provider=self.name,
                tool_calls=tool_calls or None,
                latency_ms=(time.time() - start) * 1000,
            )


class GoogleProvider(BaseProvider):
    name = "google"
    description = "Google — Gemini 2.5, Gemini 2.0, Gemini 1.5"
    default_model = "gemini-2.5-flash"
    supports_function_calling = True
    supports_vision = True
    max_context_tokens = 1000000
    rpm_limit = 1000
    tpm_limit = 4000000
    models = [
        "gemini-2.5-pro", "gemini-2.5-flash",
        "gemini-2.0-flash", "gemini-2.0-flash-lite",
        "gemini-1.5-pro", "gemini-1.5-flash", "gemini-1.5-flash-8b",
    ]

    def _format_messages(self, messages: list[dict]) -> tuple[Optional[str], list[dict]]:
        system = None
        formatted = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            if role == "system":
                system = content
            else:
                g_role = "user" if role == "user" else "model"
                parts: list[dict] = []
                if isinstance(content, str):
                    parts.append({"text": content})
                elif isinstance(content, list):
                    parts = content
                formatted.append({"role": g_role, "parts": parts})
        return system, formatted

    async def chat(self, messages: list[dict], model: str = "", **kwargs: Any) -> str:
        import httpx
        model = model or self.default_model
        await self.rate_limiter.acquire()
        system, formatted = self._format_messages(messages)
        body: dict[str, Any] = {"contents": formatted}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        gen_config: dict[str, Any] = {}
        if "max_tokens" in kwargs:
            gen_config["maxOutputTokens"] = kwargs["max_tokens"]
        if "temperature" in kwargs:
            gen_config["temperature"] = kwargs["temperature"]
        if gen_config:
            body["generationConfig"] = gen_config

        async def _do() -> str:
            async with httpx.AsyncClient(timeout=120) as client:
                r = await client.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.api_key}",
                    json=body,
                )
                if r.status_code == 429:
                    raise ConnectionError(f"Rate limited: {r.text}")
                r.raise_for_status()
                data = r.json()
                candidates = data.get("candidates", [])
                if not candidates:
                    return ""
                parts = candidates[0].get("content", {}).get("parts", [])
                return "".join(p.get("text", "") for p in parts)

        return await self._retry_call(_do, label=f"chat({model})")

    async def chat_stream(
        self, messages: list[dict], model: str = "", **kwargs: Any
    ) -> AsyncIterator[str]:
        import httpx
        model = model or self.default_model
        await self.rate_limiter.acquire()
        system, formatted = self._format_messages(messages)
        body: dict[str, Any] = {"contents": formatted}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream(
                "POST",
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent?alt=sse&key={self.api_key}",
                json=body,
            ) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    try:
                        chunk = json.loads(line[6:])
                        candidates = chunk.get("candidates", [])
                        if candidates:
                            parts = candidates[0].get("content", {}).get("parts", [])
                            for p in parts:
                                text = p.get("text", "")
                                if text:
                                    yield text
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue

    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[ToolDefinition],
        model: str = "",
        **kwargs: Any,
    ) -> ChatResponse:
        import httpx
        model = model or self.default_model
        await self.rate_limiter.acquire()
        start = time.time()
        system, formatted = self._format_messages(messages)
        body: dict[str, Any] = {"contents": formatted}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        # Google uses a different tool format
        tool_decls = []
        for t in tools:
            tool_decls.extend(t.to_google().get("function_declarations", []))
        body["tools"] = [{"function_declarations": tool_decls}]

        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.api_key}",
                json=body,
            )
            r.raise_for_status()
            data = r.json()
            candidates = data.get("candidates", [])
            if not candidates:
                return ChatResponse(content="", model=model, provider=self.name)
            parts = candidates[0].get("content", {}).get("parts", [])
            text_parts = []
            tool_calls = []
            for p in parts:
                if "text" in p:
                    text_parts.append(p["text"])
                if "functionCall" in p:
                    fc = p["functionCall"]
                    tool_calls.append({
                        "id": hashlib.md5(json.dumps(fc).encode()).hexdigest()[:16],
                        "type": "function",
                        "function": {
                            "name": fc.get("name", ""),
                            "arguments": json.dumps(fc.get("args", {})),
                        },
                    })
            usage_meta = data.get("usageMetadata", {})
            token_usage = TokenUsage(
                prompt_tokens=usage_meta.get("promptTokenCount", 0),
                completion_tokens=usage_meta.get("candidatesTokenCount", 0),
                total_tokens=usage_meta.get("totalTokenCount", 0),
            ) if usage_meta else self._estimate_tokens(messages, " ".join(text_parts))
            return ChatResponse(
                content="\n".join(text_parts),
                finish_reason=candidates[0].get("finishReason", ""),
                token_usage=token_usage,
                model=model,
                provider=self.name,
                tool_calls=tool_calls or None,
                latency_ms=(time.time() - start) * 1000,
            )


class GoogleVertexProvider(BaseProvider):
    name = "google_vertex"
    description = "Google Vertex AI — Enterprise Gemini"
    default_model = "gemini-2.5-pro"
    supports_function_calling = True
    max_context_tokens = 1000000
    models = ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash"]

    def __init__(self, api_key: str = "", **kwargs: Any):
        super().__init__(api_key, **kwargs)
        self.project_id: str = kwargs.get("project_id", "")
        self.location: str = kwargs.get("location", "us-central1")

    async def chat(self, messages: list[dict], model: str = "", **kwargs: Any) -> str:
        import httpx
        model = model or self.default_model
        await self.rate_limiter.acquire()
        formatted = []
        for m in messages:
            role = "user" if m.get("role") == "user" else "model"
            formatted.append({"role": role, "parts": [{"text": m.get("content", "")}]})
        body: dict[str, Any] = {"contents": formatted}
        url = (
            f"https://{self.location}-aiplatform.googleapis.com/v1/projects/"
            f"{self.project_id}/locations/{self.location}/publishers/google/"
            f"models/{model}:generateContent"
        )
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

        async def _do() -> str:
            async with httpx.AsyncClient(timeout=120) as client:
                r = await client.post(url, headers=headers, json=body)
                r.raise_for_status()
                return r.json()["candidates"][0]["content"]["parts"][0]["text"]

        return await self._retry_call(_do, label=f"vertex({model})")


# ═══════════════════════════════════════════════════════════════
# ⚡ TIER 2 — Fast Inference Providers
# ═══════════════════════════════════════════════════════════════

class GroqProvider(BaseProvider):
    name = "groq"
    description = "Groq — Ultra-fast LPU inference"
    default_model = "llama-3.3-70b-versatile"
    supports_function_calling = True
    rpm_limit = 30
    tpm_limit = 15000
    models = [
        "llama-3.3-70b-versatile", "llama-3.1-8b-instant",
        "mixtral-8x7b-32768", "gemma2-9b-it",
        "llama3-groq-8b-8192-tool-use-preview", "llama3-groq-70b-8192-tool-use-preview",
        "llama-guard-3-8b", "llama3-70b-8192", "llama3-8b-8192",
    ]

    async def chat(self, messages: list[dict], model: str = "", **kwargs: Any) -> str:
        import httpx
        model = model or self.default_model
        await self.rate_limiter.acquire()
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        body: dict[str, Any] = {
            "model": model, "messages": formatted,
            "max_tokens": kwargs.get("max_tokens", 4096), "temperature": kwargs.get("temperature", 0.7),
        }

        async def _do() -> str:
            async with httpx.AsyncClient(timeout=120) as client:
                r = await client.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=body)
                r.raise_for_status()
                return r.json()["choices"][0]["message"]["content"]

        return await self._retry_call(_do, label=f"groq({model})")

    async def chat_stream(
        self, messages: list[dict], model: str = "", **kwargs: Any
    ) -> AsyncIterator[str]:
        import httpx
        model = model or self.default_model
        await self.rate_limiter.acquire()
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        body = {"model": model, "messages": formatted, "max_tokens": 4096, "stream": True}
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream("POST", "https://api.groq.com/openai/v1/chat/completions", headers=headers, json=body) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    payload = line[6:]
                    if payload.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(payload)
                        text = chunk["choices"][0].get("delta", {}).get("content", "")
                        if text:
                            yield text
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue


class CerebrasProvider(BaseProvider):
    name = "cerebras"
    description = "Cerebras — Fastest inference on wafer-scale hardware"
    default_model = "llama-3.3-70b"
    models = ["llama-3.3-70b", "llama-3.1-8b"]

    async def chat(self, messages: list[dict], model: str = "", **kwargs: Any) -> str:
        import httpx
        model = model or self.default_model
        await self.rate_limiter.acquire()
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        body = {"model": model, "messages": formatted, "max_tokens": kwargs.get("max_tokens", 4096)}
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post("https://api.cerebras.ai/v1/chat/completions", headers=headers, json=body)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]


class SambaNovaProvider(BaseProvider):
    name = "sambanova"
    description = "SambaNova — Fast inference on RDU chips"
    default_model = "Meta-Llama-3.3-70B-Instruct"
    models = ["Meta-Llama-3.3-70B-Instruct", "Meta-Llama-3.1-8B-Instruct", "DeepSeek-V3-0324"]

    async def chat(self, messages: list[dict], model: str = "", **kwargs: Any) -> str:
        import httpx
        model = model or self.default_model
        await self.rate_limiter.acquire()
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        body = {"model": model, "messages": formatted, "max_tokens": kwargs.get("max_tokens", 4096)}
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post("https://api.sambanova.ai/v1/chat/completions", headers=headers, json=body)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]


class FireworksProvider(BaseProvider):
    name = "fireworks"
    description = "Fireworks AI — Fast open model inference"
    default_model = "accounts/fireworks/models/llama-v3p3-70b-instruct"
    models = [
        "accounts/fireworks/models/llama-v3p3-70b-instruct",
        "accounts/fireworks/models/llama-v3p1-8b-instruct",
        "accounts/fireworks/models/deepseek-v3",
        "accounts/fireworks/models/qwen2p5-72b-instruct",
        "accounts/fireworks/models/mixtral-8x22b-instruct",
    ]

    async def chat(self, messages: list[dict], model: str = "", **kwargs: Any) -> str:
        import httpx
        model = model or self.default_model
        await self.rate_limiter.acquire()
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        body = {"model": model, "messages": formatted, "max_tokens": kwargs.get("max_tokens", 4096)}
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post("https://api.fireworks.ai/inference/v1/chat/completions", headers=headers, json=body)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]


class TogetherProvider(BaseProvider):
    name = "together"
    description = "Together AI — Open model inference platform"
    default_model = "meta-llama/Llama-3.3-70B-Instruct-Turbo"
    models = [
        "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo",
        "deepseek-ai/DeepSeek-V3",
        "Qwen/Qwen2.5-72B-Instruct-Turbo",
        "mistralai/Mixtral-8x22B-Instruct-v0.1",
        "google/gemma-2-27b-it",
    ]

    async def chat(self, messages: list[dict], model: str = "", **kwargs: Any) -> str:
        import httpx
        model = model or self.default_model
        await self.rate_limiter.acquire()
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        body = {"model": model, "messages": formatted, "max_tokens": kwargs.get("max_tokens", 4096)}
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post("https://api.together.xyz/v1/chat/completions", headers=headers, json=body)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]


# ═══════════════════════════════════════════════════════════════
# 🔀 TIER 3 — Aggregators & Routers
# ═══════════════════════════════════════════════════════════════

class OpenRouterProvider(BaseProvider):
    name = "openrouter"
    description = "OpenRouter — 300+ models, one API"
    default_model = "anthropic/claude-sonnet-4"
    supports_function_calling = True
    models = [
        "anthropic/claude-sonnet-4", "anthropic/claude-opus-4",
        "anthropic/claude-3.5-sonnet", "openai/gpt-4o", "openai/gpt-4o-mini",
        "google/gemini-2.5-pro", "google/gemini-2.5-flash",
        "meta-llama/llama-3.3-70b-instruct", "deepseek/deepseek-chat",
        "mistralai/mistral-large", "qwen/qwen-2.5-72b-instruct",
        "cohere/command-r-plus", "perplexity/sonar-pro",
    ]

    async def chat(self, messages: list[dict], model: str = "", **kwargs: Any) -> str:
        import httpx
        model = model or self.default_model
        await self.rate_limiter.acquire()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://rally-agent.dev",
        }
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        body = {"model": model, "messages": formatted, "max_tokens": kwargs.get("max_tokens", 4096)}
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=body)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]


class UnifyProvider(BaseProvider):
    name = "unify"
    description = "Unify AI — Optimal model routing"
    default_model = "openai/gpt-4o"
    models = ["openai/gpt-4o", "anthropic/claude-3.5-sonnet", "google/gemini-2.0-flash", "meta-llama/llama-3.3-70b-instruct"]

    async def chat(self, messages: list[dict], model: str = "", **kwargs: Any) -> str:
        import httpx
        model = model or self.default_model
        await self.rate_limiter.acquire()
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        body = {"model": model, "messages": formatted, "max_tokens": kwargs.get("max_tokens", 4096)}
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post("https://api.unify.ai/v0/chat/completions", headers=headers, json=body)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]


class PortkeyProvider(BaseProvider):
    name = "portkey"
    description = "Portkey AI — Gateway to 200+ LLMs"
    default_model = "gpt-4o"
    models = ["gpt-4o", "claude-3.5-sonnet", "gemini-2.0-flash", "llama-3.3-70b"]

    async def chat(self, messages: list[dict], model: str = "", **kwargs: Any) -> str:
        import httpx
        model = model or self.default_model
        await self.rate_limiter.acquire()
        headers = {"x-portkey-api-key": self.api_key, "Content-Type": "application/json"}
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        body = {"model": model, "messages": formatted, "max_tokens": kwargs.get("max_tokens", 4096)}
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post("https://api.portkey.ai/v1/chat/completions", headers=headers, json=body)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]


# ═══════════════════════════════════════════════════════════════
# 🏠 TIER 4 — Local & Self-Hosted
# ═══════════════════════════════════════════════════════════════

class OllamaProvider(BaseProvider):
    name = "ollama"
    description = "Ollama — Run models locally"
    requires_key = False
    default_model = "llama3.2"
    rpm_limit = 120
    models = ["llama3.2", "llama3.1", "mistral", "mixtral", "codellama", "phi3", "gemma2", "qwen2.5", "deepseek-v2"]

    def __init__(self, api_key: str = "", **kwargs: Any):
        super().__init__(api_key, **kwargs)
        self.host: str = kwargs.get("host", "") or os.environ.get("OLLAMA_HOST", "http://localhost:11434")

    async def chat(self, messages: list[dict], model: str = "", **kwargs: Any) -> str:
        import httpx
        model = model or self.default_model
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        body = {"model": model, "messages": formatted, "stream": False}
        async with httpx.AsyncClient(timeout=300) as client:
            r = await client.post(f"{self.host}/api/chat", json=body)
            r.raise_for_status()
            return r.json()["message"]["content"]

    async def chat_stream(
        self, messages: list[dict], model: str = "", **kwargs: Any
    ) -> AsyncIterator[str]:
        import httpx
        model = model or self.default_model
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        body = {"model": model, "messages": formatted, "stream": True}
        async with httpx.AsyncClient(timeout=300) as client:
            async with client.stream("POST", f"{self.host}/api/chat", json=body) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                        text = chunk.get("message", {}).get("content", "")
                        if text:
                            yield text
                    except json.JSONDecodeError:
                        continue

    def get_models(self) -> list[str]:
        try:
            import httpx
            resp = httpx.get(f"{self.host}/api/tags", timeout=5)
            return [m["name"] for m in resp.json().get("models", [])]
        except Exception:
            return list(self.models)


class LMStudioProvider(BaseProvider):
    name = "lmstudio"
    description = "LM Studio — Local model server"
    requires_key = False
    default_model = "default"
    models = ["default"]

    def __init__(self, api_key: str = "", **kwargs: Any):
        super().__init__(api_key, **kwargs)
        self.base_url = kwargs.get("base_url", "") or "http://localhost:1234/v1"

    async def chat(self, messages: list[dict], model: str = "", **kwargs: Any) -> str:
        import httpx
        headers = {"Content-Type": "application/json"}
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        body = {"model": model or "default", "messages": formatted, "max_tokens": kwargs.get("max_tokens", 4096)}
        async with httpx.AsyncClient(timeout=300) as client:
            r = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=body)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]


class VLLMProvider(BaseProvider):
    name = "vllm"
    description = "vLLM — High-throughput LLM serving"
    requires_key = False
    default_model = "default"
    models = ["default"]

    def __init__(self, api_key: str = "", **kwargs: Any):
        super().__init__(api_key, **kwargs)
        self.base_url = kwargs.get("base_url", "") or "http://localhost:8000/v1"

    async def chat(self, messages: list[dict], model: str = "", **kwargs: Any) -> str:
        import httpx
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        body = {"model": model or "default", "messages": formatted, "max_tokens": kwargs.get("max_tokens", 4096)}
        async with httpx.AsyncClient(timeout=300) as client:
            r = await client.post(f"{self.base_url}/chat/completions", json=body)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]


class TextGenWebUIProvider(BaseProvider):
    name = "textgen"
    description = "text-generation-webui — Oobabooga local"
    requires_key = False
    default_model = "default"
    models = ["default"]

    def __init__(self, api_key: str = "", **kwargs: Any):
        super().__init__(api_key, **kwargs)
        self.base_url = kwargs.get("base_url", "") or "http://localhost:5000/v1"

    async def chat(self, messages: list[dict], model: str = "", **kwargs: Any) -> str:
        import httpx
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        body = {"mode": "instruct", "messages": formatted, "max_tokens": kwargs.get("max_tokens", 4096)}
        async with httpx.AsyncClient(timeout=300) as client:
            r = await client.post(f"{self.base_url}/chat/completions", json=body)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]


class JanProvider(BaseProvider):
    name = "jan"
    description = "Jan — Local AI platform"
    requires_key = False
    default_model = "default"
    models = ["default"]

    def __init__(self, api_key: str = "", **kwargs: Any):
        super().__init__(api_key, **kwargs)
        self.base_url = kwargs.get("base_url", "") or "http://localhost:1337/v1"

    async def chat(self, messages: list[dict], model: str = "", **kwargs: Any) -> str:
        import httpx
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        body = {"model": model or "default", "messages": formatted, "max_tokens": kwargs.get("max_tokens", 4096)}
        async with httpx.AsyncClient(timeout=300) as client:
            r = await client.post(f"{self.base_url}/chat/completions", json=body)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]


class GPT4AllProvider(BaseProvider):
    name = "gpt4all"
    description = "GPT4All — Local AI on any device"
    requires_key = False
    default_model = "default"
    models = ["default"]

    def __init__(self, api_key: str = "", **kwargs: Any):
        super().__init__(api_key, **kwargs)
        self.base_url = kwargs.get("base_url", "") or "http://localhost:4891/v1"

    async def chat(self, messages: list[dict], model: str = "", **kwargs: Any) -> str:
        import httpx
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        body = {"model": model or "default", "messages": formatted, "max_tokens": kwargs.get("max_tokens", 4096)}
        async with httpx.AsyncClient(timeout=300) as client:
            r = await client.post(f"{self.base_url}/chat/completions", json=body)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]


class LlamaCppProvider(BaseProvider):
    name = "llamacpp"
    description = "llama.cpp — C++ inference server"
    requires_key = False
    default_model = "default"
    models = ["default"]

    def __init__(self, api_key: str = "", **kwargs: Any):
        super().__init__(api_key, **kwargs)
        self.base_url = kwargs.get("base_url", "") or "http://localhost:8080/v1"

    async def chat(self, messages: list[dict], model: str = "", **kwargs: Any) -> str:
        import httpx
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        body = {"model": model or "default", "messages": formatted, "max_tokens": kwargs.get("max_tokens", 4096)}
        async with httpx.AsyncClient(timeout=300) as client:
            r = await client.post(f"{self.base_url}/chat/completions", json=body)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]


# ═══════════════════════════════════════════════════════════════
# 🌏 TIER 5 — International Providers
# ═══════════════════════════════════════════════════════════════

class MistralProvider(BaseProvider):
    name = "mistral"
    description = "Mistral AI — European AI leader"
    default_model = "mistral-large-latest"
    supports_function_calling = True
    models = [
        "mistral-large-latest", "mistral-medium-latest", "mistral-small-latest",
        "codestral-latest", "pixtral-large-latest",
        "open-mistral-nemo", "open-codestral-mamba",
    ]

    async def chat(self, messages: list[dict], model: str = "", **kwargs: Any) -> str:
        import httpx
        model = model or self.default_model
        await self.rate_limiter.acquire()
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        body = {"model": model, "messages": formatted, "max_tokens": kwargs.get("max_tokens", 4096)}
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post("https://api.mistral.ai/v1/chat/completions", headers=headers, json=body)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]

    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[ToolDefinition],
        model: str = "",
        **kwargs: Any,
    ) -> ChatResponse:
        import httpx
        model = model or self.default_model
        await self.rate_limiter.acquire()
        start = time.time()
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        body: dict[str, Any] = {
            "model": model, "messages": formatted, "max_tokens": kwargs.get("max_tokens", 4096),
            "tools": [t.to_openai() for t in tools],
        }
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post("https://api.mistral.ai/v1/chat/completions", headers=headers, json=body)
            r.raise_for_status()
            data = r.json()
            msg = data["choices"][0]["message"]
            return ChatResponse(
                content=msg.get("content", "") or "",
                finish_reason=data["choices"][0].get("finish_reason", ""),
                model=model, provider=self.name,
                tool_calls=msg.get("tool_calls"),
                latency_ms=(time.time() - start) * 1000,
            )


class DeepSeekProvider(BaseProvider):
    name = "deepseek"
    description = "DeepSeek — Chinese AI powerhouse"
    default_model = "deepseek-chat"
    supports_function_calling = True
    models = ["deepseek-chat", "deepseek-reasoner", "deepseek-coder"]

    async def chat(self, messages: list[dict], model: str = "", **kwargs: Any) -> str:
        import httpx
        model = model or self.default_model
        await self.rate_limiter.acquire()
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        body = {"model": model, "messages": formatted, "max_tokens": kwargs.get("max_tokens", 4096)}
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post("https://api.deepseek.com/v1/chat/completions", headers=headers, json=body)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]


class QwenProvider(BaseProvider):
    name = "qwen"
    description = "Alibaba Qwen — Chinese language models"
    default_model = "qwen-max"
    supports_function_calling = True
    models = ["qwen-max", "qwen-plus", "qwen-turbo", "qwen-long", "qwen2.5-72b-instruct"]

    async def chat(self, messages: list[dict], model: str = "", **kwargs: Any) -> str:
        import httpx
        model = model or self.default_model
        await self.rate_limiter.acquire()
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        body = {"model": model, "input": {"messages": formatted}, "parameters": {"max_tokens": kwargs.get("max_tokens", 4096)}}
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(
                "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation",
                headers=headers, json=body,
            )
            r.raise_for_status()
            return r.json()["output"]["choices"][0]["message"]["content"]


class BaiduProvider(BaseProvider):
    name = "baidu"
    description = "Baidu ERNIE — Chinese AI"
    default_model = "ernie-4.0-turbo"
    models = ["ernie-4.0-turbo", "ernie-4.0", "ernie-3.5", "ernie-speed"]

    async def chat(self, messages: list[dict], model: str = "", **kwargs: Any) -> str:
        import httpx
        model = model or self.default_model
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        body = {"messages": formatted}
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(
                f"https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/{model}?access_token={self.api_key}",
                json=body,
            )
            r.raise_for_status()
            return r.json()["result"]


class ZhipuProvider(BaseProvider):
    name = "zhipu"
    description = "Zhipu AI (GLM) — Chinese language models"
    default_model = "glm-4"
    models = ["glm-4", "glm-4-flash", "glm-4v", "glm-3-turbo"]

    async def chat(self, messages: list[dict], model: str = "", **kwargs: Any) -> str:
        import httpx
        model = model or self.default_model
        await self.rate_limiter.acquire()
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        body = {"model": model, "messages": formatted, "max_tokens": kwargs.get("max_tokens", 4096)}
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post("https://open.bigmodel.cn/api/paas/v4/chat/completions", headers=headers, json=body)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]


class MoonshotProvider(BaseProvider):
    name = "moonshot"
    description = "Moonshot AI (Kimi) — Long context Chinese AI"
    default_model = "moonshot-v1-128k"
    max_context_tokens = 128000
    models = ["moonshot-v1-128k", "moonshot-v1-32k", "moonshot-v1-8k"]

    async def chat(self, messages: list[dict], model: str = "", **kwargs: Any) -> str:
        import httpx
        model = model or self.default_model
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        body = {"model": model, "messages": formatted, "max_tokens": kwargs.get("max_tokens", 4096)}
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post("https://api.moonshot.cn/v1/chat/completions", headers=headers, json=body)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]


class YiProvider(BaseProvider):
    name = "yi"
    description = "01.AI Yi — Chinese language models"
    default_model = "yi-large"
    models = ["yi-large", "yi-medium", "yi-spark", "yi-large-turbo"]

    async def chat(self, messages: list[dict], model: str = "", **kwargs: Any) -> str:
        import httpx
        model = model or self.default_model
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        body = {"model": model, "messages": formatted, "max_tokens": kwargs.get("max_tokens", 4096)}
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post("https://api.lingyiwanwu.com/v1/chat/completions", headers=headers, json=body)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]


class CohereProvider(BaseProvider):
    name = "cohere"
    description = "Cohere — Enterprise AI platform"
    default_model = "command-r-plus"
    supports_function_calling = True
    models = ["command-r-plus", "command-r", "command", "command-nightly"]

    async def chat(self, messages: list[dict], model: str = "", **kwargs: Any) -> str:
        import httpx
        model = model or self.default_model
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        formatted = [{"role": m.get("role", "user"), "message": m.get("content", "")} for m in messages]
        body = {"model": model, "messages": formatted, "max_tokens": kwargs.get("max_tokens", 4096)}
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post("https://api.cohere.ai/v1/chat", headers=headers, json=body)
            r.raise_for_status()
            return r.json()["text"]


class VoyageProvider(BaseProvider):
    name = "voyage"
    description = "Voyage AI — Embeddings specialist"
    default_model = "voyage-3"
    models = ["voyage-3", "voyage-3-large", "voyage-code-3", "voyage-finance-2"]

    async def chat(self, messages: list[dict], model: str = "", **kwargs: Any) -> str:
        return "Voyage AI is an embeddings provider. Use for vector search, not chat."


class AI21Provider(BaseProvider):
    name = "ai21"
    description = "AI21 Labs — Jamba models"
    default_model = "jamba-1.5-large"
    models = ["jamba-1.5-large", "jamba-1.5-mini", "jamba-instruct"]

    async def chat(self, messages: list[dict], model: str = "", **kwargs: Any) -> str:
        import httpx
        model = model or self.default_model
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        body = {"model": model, "messages": formatted, "max_tokens": kwargs.get("max_tokens", 4096)}
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post("https://api.ai21.com/v1/chat/completions", headers=headers, json=body)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]


class PerplexityProvider(BaseProvider):
    name = "perplexity"
    description = "Perplexity AI — Search-augmented AI"
    default_model = "sonar-pro"
    models = ["sonar-pro", "sonar", "sonar-reasoning-pro", "sonar-reasoning", "sonar-deep-research"]

    async def chat(self, messages: list[dict], model: str = "", **kwargs: Any) -> str:
        import httpx
        model = model or self.default_model
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        body = {"model": model, "messages": formatted, "max_tokens": kwargs.get("max_tokens", 4096)}
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post("https://api.perplexity.ai/chat/completions", headers=headers, json=body)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]


class ReplicateProvider(BaseProvider):
    name = "replicate"
    description = "Replicate — Run any ML model"
    default_model = "meta/llama-3.3-70b-instruct"
    models = ["meta/llama-3.3-70b-instruct", "meta/llama-3.1-8b-instruct", "mistralai/mixtral-8x7b-instruct-v0.1"]

    async def chat(self, messages: list[dict], model: str = "", **kwargs: Any) -> str:
        import httpx
        model = model or self.default_model
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        body = {"input": {"prompt": messages[-1].get("content", ""), "max_tokens": kwargs.get("max_tokens", 4096)}}
        async with httpx.AsyncClient(timeout=300) as client:
            r = await client.post(f"https://api.replicate.com/v1/models/{model}/predictions", headers=headers, json=body)
            r.raise_for_status()
            return str(r.json().get("output", ""))


class HuggingFaceProvider(BaseProvider):
    name = "huggingface"
    description = "Hugging Face — Open model hub"
    default_model = "meta-llama/Llama-3.3-70B-Instruct"
    models = ["meta-llama/Llama-3.3-70B-Instruct", "mistralai/Mixtral-8x7B-Instruct-v0.1", "google/gemma-2-27b-it"]

    async def chat(self, messages: list[dict], model: str = "", **kwargs: Any) -> str:
        import httpx
        model = model or self.default_model
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        body = {"model": model, "messages": formatted, "max_tokens": kwargs.get("max_tokens", 4096)}
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(f"https://api-inference.huggingface.co/models/{model}/v1/chat/completions", headers=headers, json=body)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]


class XAIProvider(BaseProvider):
    name = "xai"
    description = "xAI (Grok) — Elon's AI"
    default_model = "grok-3"
    supports_function_calling = True
    models = ["grok-3", "grok-3-mini", "grok-2", "grok-2-mini"]

    async def chat(self, messages: list[dict], model: str = "", **kwargs: Any) -> str:
        import httpx
        model = model or self.default_model
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        body = {"model": model, "messages": formatted, "max_tokens": kwargs.get("max_tokens", 4096)}
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post("https://api.x.ai/v1/chat/completions", headers=headers, json=body)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]


class AmazonBedrockProvider(BaseProvider):
    name = "bedrock"
    description = "Amazon Bedrock — AWS AI platform"
    default_model = "anthropic.claude-sonnet-4-20250514-v1:0"
    models = ["anthropic.claude-sonnet-4-20250514-v1:0", "anthropic.claude-3-5-haiku-20241022-v1:0", "meta.llama3-3-70b-instruct-v1:0"]

    def __init__(self, api_key: str = "", **kwargs: Any):
        super().__init__(api_key, **kwargs)
        self.region: str = kwargs.get("region", "us-east-1")

    async def chat(self, messages: list[dict], model: str = "", **kwargs: Any) -> str:
        return "Amazon Bedrock requires AWS SDK (boto3). Configure AWS credentials separately."


class AzureOpenAIProvider(BaseProvider):
    name = "azure"
    description = "Azure OpenAI — Microsoft AI platform"
    default_model = "gpt-4o"
    supports_function_calling = True
    models = ["gpt-4o", "gpt-4", "gpt-35-turbo"]

    def __init__(self, api_key: str = "", **kwargs: Any):
        super().__init__(api_key, **kwargs)
        self.endpoint: str = kwargs.get("endpoint", "")
        self.api_version: str = kwargs.get("api_version", "2024-02-15-preview")

    async def chat(self, messages: list[dict], model: str = "", **kwargs: Any) -> str:
        import httpx
        model = model or self.default_model
        headers = {"api-key": self.api_key, "Content-Type": "application/json"}
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        body = {"messages": formatted, "max_tokens": kwargs.get("max_tokens", 4096)}
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(
                f"{self.endpoint}/openai/deployments/{model}/chat/completions?api-version={self.api_version}",
                headers=headers, json=body,
            )
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]


class NVIDIAProvider(BaseProvider):
    name = "nvidia"
    description = "NVIDIA NIM — Fast inference on NVIDIA GPUs"
    default_model = "meta/llama-3.1-70b-instruct"
    supports_function_calling = True
    max_context_tokens = 128000
    rpm_limit = 60
    tpm_limit = 100000
    models = [
        "meta/llama-3.1-405b-instruct", "meta/llama-3.1-70b-instruct",
        "meta/llama-3.1-8b-instruct", "meta/llama-3.3-70b-instruct",
        "mistralai/mistral-large-latest", "mistralai/mixtral-8x22b-instruct-v0.1",
        "google/gemma-2-27b-it", "deepseek-ai/deepseek-r1",
        "nvidia/llama-3.1-nemotron-70b-instruct", "nvidia/nemotron-mini-4b-instruct",
    ]

    async def chat(self, messages: list[dict], model: str = "", **kwargs: Any) -> str:
        import httpx
        model = model or self.default_model
        await self.rate_limiter.acquire()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        formatted = [
            {"role": m.get("role", "user"), "content": m.get("content", "")}
            for m in messages
        ]
        body: dict[str, Any] = {
            "model": model,
            "messages": formatted,
            "max_tokens": kwargs.get("max_tokens", 4096),
            "temperature": kwargs.get("temperature", 0.7),
        }

        async def _do() -> str:
            async with httpx.AsyncClient(timeout=120) as client:
                r = await client.post(
                    "https://integrate.api.nvidia.com/v1/chat/completions",
                    headers=headers,
                    json=body,
                )
                if r.status_code == 429:
                    raise ConnectionError(f"Rate limited: {r.text}")
                r.raise_for_status()
                data = r.json()
                usage = data.get("usage", {})
                if usage:
                    self.rate_limiter.update_actual_tokens(usage.get("total_tokens", 0))
                return data["choices"][0]["message"]["content"] or ""

        return await self._retry_call(_do, label=f"nvidia({model})")

    async def chat_stream(
        self, messages: list[dict], model: str = "", **kwargs: Any
    ) -> AsyncIterator[str]:
        import httpx
        model = model or self.default_model
        await self.rate_limiter.acquire()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        formatted = [
            {"role": m.get("role", "user"), "content": m.get("content", "")}
            for m in messages
        ]
        body: dict[str, Any] = {
            "model": model,
            "messages": formatted,
            "max_tokens": kwargs.get("max_tokens", 4096),
            "temperature": kwargs.get("temperature", 0.7),
            "stream": True,
        }
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream(
                "POST",
                "https://integrate.api.nvidia.com/v1/chat/completions",
                headers=headers,
                json=body,
            ) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    payload = line[6:]
                    if payload.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(payload)
                        text = chunk["choices"][0].get("delta", {}).get("content", "")
                        if text:
                            yield text
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue


class CustomOpenAIProvider(BaseProvider):
    name = "custom"
    description = "Custom — Any OpenAI-compatible endpoint"
    default_model = "default"
    models = ["default"]

    async def chat(self, messages: list[dict], model: str = "", **kwargs: Any) -> str:
        import httpx
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        formatted = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
        body = {"model": model or "default", "messages": formatted, "max_tokens": kwargs.get("max_tokens", 4096)}
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=body)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]


# ═══════════════════════════════════════════════════════════════
# 🎯 Provider Manager — Auto-selects best available
# ═══════════════════════════════════════════════════════════════

class ProviderManager:
    """Manages all LLM providers with fallback chains, circuit breakers,
    health checks, and streaming support.
    """

    ALL_PROVIDERS: dict[str, type[BaseProvider]] = {
        # Tier 1 — Major Cloud
        "openai": OpenAIProvider,
        "anthropic": AnthropicProvider,
        "google": GoogleProvider,
        "google_vertex": GoogleVertexProvider,
        # Tier 2 — Fast Inference
        "groq": GroqProvider,
        "cerebras": CerebrasProvider,
        "sambanova": SambaNovaProvider,
        "fireworks": FireworksProvider,
        "together": TogetherProvider,
        # Tier 3 — Aggregators
        "openrouter": OpenRouterProvider,
        "unify": UnifyProvider,
        "portkey": PortkeyProvider,
        # Tier 4 — Local
        "ollama": OllamaProvider,
        "lmstudio": LMStudioProvider,
        "vllm": VLLMProvider,
        "textgen": TextGenWebUIProvider,
        "jan": JanProvider,
        "gpt4all": GPT4AllProvider,
        "llamacpp": LlamaCppProvider,
        # Tier 5 — International
        "mistral": MistralProvider,
        "deepseek": DeepSeekProvider,
        "qwen": QwenProvider,
        "baidu": BaiduProvider,
        "zhipu": ZhipuProvider,
        "moonshot": MoonshotProvider,
        "yi": YiProvider,
        "cohere": CohereProvider,
        "voyage": VoyageProvider,
        "ai21": AI21Provider,
        "perplexity": PerplexityProvider,
        "replicate": ReplicateProvider,
        "huggingface": HuggingFaceProvider,
        "xai": XAIProvider,
        "nvidia": NVIDIAProvider,
        "bedrock": AmazonBedrockProvider,
        "azure": AzureOpenAIProvider,
        "custom": CustomOpenAIProvider,
    }

    def __init__(self, config: Any):
        self.config = config
        self.providers: dict[str, BaseProvider] = {}
        self._circuit_breakers: dict[str, _CircuitBreaker] = {}
        self._init_providers()

    def _init_providers(self) -> None:
        """Initialize all available providers."""
        keys = self.config.get_provider_keys() if hasattr(self.config, "get_provider_keys") else {}

        env_map = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "google": "GOOGLE_API_KEY",
            "groq": "GROQ_API_KEY",
            "cerebras": "CEREBRAS_API_KEY",
            "sambanova": "SAMBANOVA_API_KEY",
            "fireworks": "FIREWORKS_API_KEY",
            "together": "TOGETHER_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
            "unify": "UNIFY_API_KEY",
            "portkey": "PORTKEY_API_KEY",
            "mistral": "MISTRAL_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
            "qwen": "QWEN_API_KEY",
            "baidu": "BAIDU_API_KEY",
            "zhipu": "ZHIPU_API_KEY",
            "moonshot": "MOONSHOT_API_KEY",
            "yi": "YI_API_KEY",
            "cohere": "COHERE_API_KEY",
            "ai21": "AI21_API_KEY",
            "perplexity": "PERPLEXITY_API_KEY",
            "replicate": "REPLICATE_API_TOKEN",
            "huggingface": "HUGGINGFACE_API_KEY",
            "xai": "XAI_API_KEY",
            "nvidia": "NVIDIA_API_KEY",
            "bedrock": "AWS_BEARER_TOKEN",
            "azure": "AZURE_OPENAI_API_KEY",
        }

        for provider_name, provider_class in self.ALL_PROVIDERS.items():
            api_key = keys.get(provider_name, "")
            if not api_key:
                env_var = env_map.get(provider_name, "")
                if env_var:
                    api_key = os.environ.get(env_var, "")

            if provider_name == "custom":
                base_url = keys.get("custom_base_url", os.environ.get("CUSTOM_API_BASE", ""))
                if base_url:
                    provider = provider_class(api_key=api_key, base_url=base_url)
                    self.providers[provider_name] = provider
                    self._circuit_breakers[provider_name] = _CircuitBreaker(
                        self.config.get("engine.circuit_breaker_threshold", 5) if hasattr(self.config, "get") else 5,
                        self.config.get("engine.circuit_breaker_timeout", 60.0) if hasattr(self.config, "get") else 60.0,
                    )
                continue

            if api_key or not provider_class.requires_key:
                kwargs: dict[str, Any] = {}
                if provider_name == "google_vertex":
                    kwargs["project_id"] = keys.get("vertex_project_id", os.environ.get("VERTEX_PROJECT_ID", ""))
                    kwargs["location"] = keys.get("vertex_location", os.environ.get("VERTEX_LOCATION", "us-central1"))
                if provider_name == "azure":
                    kwargs["endpoint"] = keys.get("azure_endpoint", os.environ.get("AZURE_OPENAI_ENDPOINT", ""))
                if provider_name in ("ollama", "lmstudio", "vllm", "textgen", "jan", "gpt4all", "llamacpp"):
                    kwargs["host"] = keys.get(f"{provider_name}_host", "")
                    kwargs["base_url"] = keys.get(f"{provider_name}_base_url", "")

                provider = provider_class(api_key=api_key, **kwargs)
                self.providers[provider_name] = provider
                self._circuit_breakers[provider_name] = _CircuitBreaker(
                    self.config.get("engine.circuit_breaker_threshold", 5) if hasattr(self.config, "get") else 5,
                    self.config.get("engine.circuit_breaker_timeout", 60.0) if hasattr(self.config, "get") else 60.0,
                )

    def get_available(self) -> list[str]:
        return [name for name, p in self.providers.items() if p.is_available()]

    def get_all_info(self) -> list[dict]:
        result = []
        for name, provider_class in self.ALL_PROVIDERS.items():
            p = self.providers.get(name)
            info: dict[str, Any] = {
                "name": name,
                "description": provider_class.description,
                "models": provider_class.models,
                "available": p is not None and p.is_available(),
                "requires_key": provider_class.requires_key,
                "supports_streaming": provider_class.supports_streaming,
                "supports_function_calling": provider_class.supports_function_calling,
            }
            if p:
                info["health"] = p.health.to_dict()
                cb = self._circuit_breakers.get(name)
                if cb:
                    info["circuit_breaker"] = cb.to_dict()
            result.append(info)
        return result

    async def chat(self, messages: list[dict], model: str = "auto", **kwargs: Any) -> str:
        """Send chat using best available provider with fallback chain."""
        if model == "auto":
            return await self._auto_chat(messages, **kwargs)

        # Find provider for specific model
        for name, provider in self.providers.items():
            if model in provider.get_models():
                cb = self._circuit_breakers.get(name)
                if cb and not cb.allow_request():
                    continue
                try:
                    result = await provider.chat(messages, model=model, **kwargs)
                    provider.health.record_success(0)
                    if cb:
                        cb.record_success()
                    return result
                except Exception as e:
                    provider.health.record_failure()
                    if cb:
                        cb.record_failure()
                    logger.warning(f"[{name}] chat failed: {e}")

        # Try first available
        for name, provider in self.providers.items():
            cb = self._circuit_breakers.get(name)
            if cb and not cb.allow_request():
                continue
            try:
                result = await provider.chat(messages, model=model, **kwargs)
                provider.health.record_success(0)
                if cb:
                    cb.record_success()
                return result
            except Exception:
                provider.health.record_failure()
                if cb:
                    cb.record_failure()
                continue

        raise RuntimeError("No AI providers configured or all failed. Set an API key to get started.")

    async def _auto_chat(self, messages: list[dict], **kwargs: Any) -> str:
        """Auto-select best provider with circuit breaker awareness."""
        fallback_order = self.config.get("engine.fallback_order", [
            "anthropic", "openai", "google", "groq", "nvidia", "openrouter", "deepseek", "mistral", "together", "fireworks", "ollama",
        ]) if hasattr(self.config, "get") else [
            "anthropic", "openai", "google", "groq", "nvidia", "openrouter", "deepseek", "mistral", "together", "fireworks", "ollama",
        ]

        errors: list[str] = []

        for provider_name in fallback_order:
            if provider_name not in self.providers:
                continue
            provider = self.providers[provider_name]
            cb = self._circuit_breakers.get(provider_name)
            if cb and not cb.allow_request():
                logger.debug(f"[{provider_name}] circuit breaker OPEN, skipping")
                continue
            try:
                models = provider.get_models()
                model = models[0] if models else "default"
                result = await provider.chat(messages, model=model, **kwargs)
                provider.health.record_success(0)
                if cb:
                    cb.record_success()
                return result
            except Exception as e:
                provider.health.record_failure()
                if cb:
                    cb.record_failure()
                errors.append(f"{provider_name}: {e}")
                logger.warning(f"[{provider_name}] failed: {e}")
                continue

        # Last resort: try any remaining provider
        for name, provider in self.providers.items():
            if name in fallback_order:
                continue
            cb = self._circuit_breakers.get(name)
            if cb and not cb.allow_request():
                continue
            try:
                models = provider.get_models()
                model = models[0] if models else "default"
                result = await provider.chat(messages, model=model, **kwargs)
                provider.health.record_success(0)
                if cb:
                    cb.record_success()
                return result
            except Exception:
                provider.health.record_failure()
                if cb:
                    cb.record_failure()
                continue

        error_summary = "; ".join(errors[-5:]) if errors else "no providers available"
        raise RuntimeError(f"All providers failed. Errors: {error_summary}")

    async def chat_stream(
        self, messages: list[dict], model: str = "auto", **kwargs: Any
    ) -> AsyncIterator[str]:
        """Stream chat response. Falls back through providers."""
        if model == "auto":
            async for chunk in self._auto_stream(messages, **kwargs):
                yield chunk
            return

        # Specific model
        for name, provider in self.providers.items():
            if model in provider.get_models():
                cb = self._circuit_breakers.get(name)
                if cb and not cb.allow_request():
                    continue
                try:
                    async for chunk in provider.chat_stream(messages, model=model, **kwargs):
                        yield chunk
                    provider.health.record_success(0)
                    if cb:
                        cb.record_success()
                    return
                except Exception as e:
                    provider.health.record_failure()
                    if cb:
                        cb.record_failure()
                    logger.warning(f"[{name}] stream failed: {e}")

        # Fallback to non-streaming
        result = await self.chat(messages, model=model, **kwargs)
        yield result

    async def _auto_stream(self, messages: list[dict], **kwargs: Any) -> AsyncIterator[str]:
        """Auto-select provider and stream."""
        fallback_order = self.config.get("engine.fallback_order", [
            "anthropic", "openai", "google", "groq", "nvidia", "openrouter", "deepseek", "mistral", "together", "fireworks", "ollama",
        ]) if hasattr(self.config, "get") else [
            "anthropic", "openai", "google", "groq", "nvidia", "openrouter", "deepseek", "mistral", "together", "fireworks", "ollama",
        ]

        for provider_name in fallback_order:
            if provider_name not in self.providers:
                continue
            provider = self.providers[provider_name]
            cb = self._circuit_breakers.get(provider_name)
            if cb and not cb.allow_request():
                continue
            try:
                models = provider.get_models()
                m = models[0] if models else "default"
                async for chunk in provider.chat_stream(messages, model=m, **kwargs):
                    yield chunk
                provider.health.record_success(0)
                if cb:
                    cb.record_success()
                return
            except Exception as e:
                provider.health.record_failure()
                if cb:
                    cb.record_failure()
                logger.warning(f"[{provider_name}] stream failed: {e}")
                continue

        # Last resort non-streaming
        result = await self._auto_chat(messages, **kwargs)
        yield result

    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[ToolDefinition],
        model: str = "auto",
        **kwargs: Any,
    ) -> ChatResponse:
        """Chat with function calling. Falls back through providers that support it."""
        if model != "auto":
            for name, provider in self.providers.items():
                if model in provider.get_models() and provider.supports_function_calling:
                    cb = self._circuit_breakers.get(name)
                    if cb and not cb.allow_request():
                        continue
                    try:
                        resp = await provider.chat_with_tools(messages, tools, model=model, **kwargs)
                        provider.health.record_success(0)
                        if cb:
                            cb.record_success()
                        return resp
                    except Exception as e:
                        provider.health.record_failure()
                        if cb:
                            cb.record_failure()
                        logger.warning(f"[{name}] tool chat failed: {e}")

        # Auto: try providers that support function calling first
        fc_providers = [
            n for n, p in self.providers.items()
            if p.supports_function_calling and (not self._circuit_breakers.get(n) or self._circuit_breakers[n].allow_request())
        ]
        for name in fc_providers:
            provider = self.providers[name]
            cb = self._circuit_breakers.get(name)
            try:
                models = provider.get_models()
                m = models[0] if models else "default"
                resp = await provider.chat_with_tools(messages, tools, model=m, **kwargs)
                provider.health.record_success(0)
                if cb:
                    cb.record_success()
                return resp
            except Exception as e:
                provider.health.record_failure()
                if cb:
                    cb.record_failure()
                logger.warning(f"[{name}] tool chat failed: {e}")

        # Fallback: plain chat
        text = await self._auto_chat(messages, **kwargs)
        return ChatResponse(content=text)

    async def health_check_all(self) -> dict[str, ProviderStatus]:
        """Run health checks on all providers concurrently."""
        results: dict[str, ProviderStatus] = {}
        tasks = {}
        for name, provider in self.providers.items():
            tasks[name] = asyncio.create_task(provider.health_check())
        for name, task in tasks.items():
            try:
                results[name] = await task
            except Exception:
                results[name] = ProviderStatus.UNHEALTHY
        return results

    def get_provider(self, name: str) -> Optional[BaseProvider]:
        """Get a specific provider by name."""
        return self.providers.get(name)


# ═══════════════════════════════════════════════════════════════
# ⭕ Circuit Breaker
# ═══════════════════════════════════════════════════════════════

class _CircuitState(Enum):
    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Failing, reject requests
    HALF_OPEN = "half_open" # Testing recovery


class _CircuitBreaker:
    """Circuit breaker pattern for provider failure isolation.

    States:
    - CLOSED: normal, requests pass through
    - OPEN: too many failures, reject requests immediately
    - HALF_OPEN: timeout expired, allow one test request
    """

    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 60.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.state = _CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time: float = 0.0
        self.success_count = 0

    def allow_request(self) -> bool:
        """Check if a request should be allowed."""
        if self.state == _CircuitState.CLOSED:
            return True
        if self.state == _CircuitState.OPEN:
            # Check if recovery timeout has elapsed
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                self.state = _CircuitState.HALF_OPEN
                return True
            return False
        if self.state == _CircuitState.HALF_OPEN:
            return True
        return True

    def record_success(self) -> None:
        """Record a successful request."""
        if self.state == _CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= 2:
                # Recovery confirmed
                self.state = _CircuitState.CLOSED
                self.failure_count = 0
                self.success_count = 0
        elif self.state == _CircuitState.CLOSED:
            self.failure_count = max(0, self.failure_count - 1)

    def record_failure(self) -> None:
        """Record a failed request."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = _CircuitState.OPEN
            self.success_count = 0
        if self.state == _CircuitState.HALF_OPEN:
            # Failed during recovery, back to open
            self.state = _CircuitState.OPEN
            self.success_count = 0

    def to_dict(self) -> dict:
        return {
            "state": self.state.value,
            "failure_count": self.failure_count,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout,
            "last_failure_time": self.last_failure_time,
        }
