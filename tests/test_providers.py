"""
Tests for providers: RateLimiter, CircuitBreaker, ChatResponse, TokenUsage, ToolDefinition.
"""

import pytest
import asyncio
import time
from core.providers import (
    RateLimiter,
    _CircuitBreaker,
    _CircuitState,
    ChatResponse,
    TokenUsage,
    ToolDefinition,
    ProviderHealth,
    ProviderStatus,
)


# ═══════════════════════════════════════════════════════════════
# RateLimiter Tests
# ═══════════════════════════════════════════════════════════════

class TestRateLimiter:
    def test_init(self):
        rl = RateLimiter(requests_per_minute=30, tokens_per_minute=50000)
        assert rl.rpm == 30
        assert rl.tpm == 50000

    @pytest.mark.asyncio
    async def test_acquire_within_limits(self):
        rl = RateLimiter(requests_per_minute=100, tokens_per_minute=1000000)
        # Should not block
        await rl.acquire(estimated_tokens=100)

    @pytest.mark.asyncio
    async def test_acquire_tracks_requests(self):
        rl = RateLimiter(requests_per_minute=100, tokens_per_minute=1000000)
        await rl.acquire(100)
        await rl.acquire(200)
        assert len(rl._request_times) == 2

    def test_update_actual_tokens(self):
        rl = RateLimiter()
        rl._token_counts = [(time.time(), 100)]
        rl.update_actual_tokens(500)
        assert rl._token_counts[-1][1] == 500


# ═══════════════════════════════════════════════════════════════
# CircuitBreaker Tests
# ═══════════════════════════════════════════════════════════════

class TestCircuitBreaker:
    def test_init(self):
        cb = _CircuitBreaker(failure_threshold=5, recovery_timeout=30.0)
        assert cb.failure_threshold == 5
        assert cb.recovery_timeout == 30.0
        assert cb.state == _CircuitState.CLOSED

    def test_allow_request_closed(self):
        cb = _CircuitBreaker()
        assert cb.allow_request() is True

    def test_record_failure_opens_circuit(self):
        cb = _CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == _CircuitState.CLOSED
        cb.record_failure()
        assert cb.state == _CircuitState.OPEN

    def test_open_circuit_rejects_requests(self):
        cb = _CircuitBreaker(failure_threshold=1)
        cb.record_failure()
        assert cb.state == _CircuitState.OPEN
        assert cb.allow_request() is False

    def test_half_open_after_timeout(self):
        cb = _CircuitBreaker(failure_threshold=1, recovery_timeout=0.01)
        cb.record_failure()
        assert cb.state == _CircuitState.OPEN
        time.sleep(0.02)
        assert cb.allow_request() is True
        assert cb.state == _CircuitState.HALF_OPEN

    def test_half_open_to_closed_on_success(self):
        cb = _CircuitBreaker(failure_threshold=1, recovery_timeout=0.01)
        cb.record_failure()
        time.sleep(0.02)
        cb.allow_request()  # transitions to HALF_OPEN
        cb.record_success()
        cb.record_success()
        assert cb.state == _CircuitState.CLOSED

    def test_half_open_to_open_on_failure(self):
        cb = _CircuitBreaker(failure_threshold=1, recovery_timeout=0.01)
        cb.record_failure()
        time.sleep(0.02)
        cb.allow_request()  # HALF_OPEN
        cb.record_failure()
        assert cb.state == _CircuitState.OPEN

    def test_success_decrements_failure_count(self):
        cb = _CircuitBreaker(failure_threshold=5)
        cb.record_failure()
        cb.record_failure()
        assert cb.failure_count == 2
        cb.record_success()
        assert cb.failure_count == 1

    def test_to_dict(self):
        cb = _CircuitBreaker()
        d = cb.to_dict()
        assert "state" in d
        assert "failure_count" in d
        assert d["state"] == "closed"


# ═══════════════════════════════════════════════════════════════
# Data Types Tests
# ═══════════════════════════════════════════════════════════════

class TestTokenUsage:
    def test_init(self):
        tu = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        assert tu.prompt_tokens == 100
        assert tu.completion_tokens == 50
        assert tu.total_tokens == 150

    def test_to_dict(self):
        tu = TokenUsage(100, 50, 150)
        d = tu.to_dict()
        assert d["prompt_tokens"] == 100
        assert d["total_tokens"] == 150


class TestChatResponse:
    def test_init(self):
        cr = ChatResponse(content="hello", model="gpt-4o", provider="openai")
        assert cr.content == "hello"
        assert cr.model == "gpt-4o"

    def test_to_dict(self):
        cr = ChatResponse(content="hello", model="gpt-4o")
        d = cr.to_dict()
        assert d["content"] == "hello"

    def test_to_dict_with_usage(self):
        cr = ChatResponse(
            content="hello",
            token_usage=TokenUsage(100, 50, 150),
        )
        d = cr.to_dict()
        assert "token_usage" in d

    def test_to_dict_with_tool_calls(self):
        cr = ChatResponse(
            content="",
            tool_calls=[{"name": "test"}],
        )
        d = cr.to_dict()
        assert "tool_calls" in d


class TestToolDefinition:
    def test_init(self):
        td = ToolDefinition(
            name="test",
            description="A test tool",
            parameters={"type": "object", "properties": {}},
        )
        assert td.name == "test"

    def test_to_openai(self):
        td = ToolDefinition(name="test", description="desc", parameters={"type": "object"})
        result = td.to_openai()
        assert result["type"] == "function"
        assert result["function"]["name"] == "test"

    def test_to_anthropic(self):
        td = ToolDefinition(name="test", description="desc", parameters={"type": "object"})
        result = td.to_anthropic()
        assert result["name"] == "test"
        assert "input_schema" in result


class TestProviderHealth:
    def test_init(self):
        ph = ProviderHealth()
        assert ph.status == ProviderStatus.UNKNOWN
        assert ph.total_requests == 0

    def test_record_success(self):
        ph = ProviderHealth()
        ph.record_success(100.0)
        assert ph.status == ProviderStatus.HEALTHY
        assert ph.total_requests == 1
        assert ph.consecutive_failures == 0
        assert ph.avg_latency_ms == 100.0

    def test_record_failure(self):
        ph = ProviderHealth()
        ph.record_failure()
        assert ph.total_failures == 1
        assert ph.consecutive_failures == 1
        assert ph.status == ProviderStatus.DEGRADED

    def test_record_multiple_failures(self):
        ph = ProviderHealth()
        ph.record_failure()
        ph.record_failure()
        ph.record_failure()
        assert ph.status == ProviderStatus.UNHEALTHY

    def test_failure_rate(self):
        ph = ProviderHealth()
        ph.record_success(100)
        ph.record_failure()
        assert ph.failure_rate == 0.5

    def test_failure_rate_no_requests(self):
        ph = ProviderHealth()
        assert ph.failure_rate == 0.0

    def test_to_dict(self):
        ph = ProviderHealth()
        d = ph.to_dict()
        assert "status" in d
        assert "total_requests" in d
