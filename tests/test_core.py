"""
Rally Agent — Core Component Tests
Tests for TokenCounter, ConversationTree, RateLimiter, CircuitBreaker,
SSEEvent, ToolExecutor, ProviderHealth, and RallyConfig.
"""
import asyncio
import json
import time
import pytest

from core.engine import TokenCounter, ConversationTree, SSEEvent, ToolExecutor, RequestQueue
from core.providers import RateLimiter, _CircuitBreaker, ProviderHealth, ProviderStatus
from core.config import RallyConfig


# ═══════════════════════════════════════════════════════════════
# TokenCounter Tests
# ═══════════════════════════════════════════════════════════════

class TestTokenCounter:
    def setup_method(self):
        self.tc = TokenCounter(max_context=128000, max_output=4096)

    def test_empty_string(self):
        assert self.tc.estimate_tokens("") == 0

    def test_none_returns_zero(self):
        assert self.tc.estimate_tokens(None) == 0

    def test_ascii_text(self):
        tokens = self.tc.estimate_tokens("Hello world")
        assert tokens > 0
        assert tokens < 10

    def test_cjk_text(self):
        tokens = self.tc.estimate_tokens("你好世界")
        assert tokens > 0

    def test_long_text(self):
        long = "word " * 1000
        tokens = self.tc.estimate_tokens(long)
        assert tokens > 100

    def test_trim_empty_messages(self):
        result = self.tc.trim_messages([], reserved_output=1000)
        assert result == []

    def test_trim_system_only(self):
        msgs = [{"role": "system", "content": "You are helpful"}]
        result = self.tc.trim_messages(msgs, reserved_output=1000)
        assert len(result) == 1

    def test_trim_preserves_system(self):
        msgs = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
        ]
        result = self.tc.trim_messages(msgs, reserved_output=1000)
        assert result[0]["role"] == "system"

    def test_trim_preserves_recent(self):
        msgs = [
            {"role": "system", "content": "System"},
            {"role": "user", "content": "First"},
            {"role": "assistant", "content": "Reply 1"},
            {"role": "user", "content": "Second"},
            {"role": "assistant", "content": "Reply 2"},
        ]
        result = self.tc.trim_messages(msgs, reserved_output=1000, system_tokens=50)
        # Should keep at least the most recent messages
        assert len(result) >= 2  # system + at least one pair

    def test_record_usage(self):
        self.tc.record_usage(100, 50)
        assert self.tc.total_prompt_tokens == 100
        assert self.tc.total_completion_tokens == 50
        assert self.tc.total_tokens_used == 150
        assert self.tc.total_requests == 1

    def test_record_multiple(self):
        self.tc.record_usage(100, 50)
        self.tc.record_usage(200, 100)
        assert self.tc.total_tokens_used == 450
        assert self.tc.total_requests == 2

    def test_to_dict(self):
        self.tc.record_usage(100, 50)
        d = self.tc.to_dict()
        assert d["max_context"] == 128000
        assert d["max_output"] == 4096
        assert d["total_tokens_used"] == 150

    def test_estimate_messages_tokens(self):
        msgs = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        tokens = self.tc.estimate_messages_tokens(msgs)
        assert tokens > 0


# ═══════════════════════════════════════════════════════════════
# ConversationTree Tests
# ═══════════════════════════════════════════════════════════════

class TestConversationTree:
    def setup_method(self):
        self.tree = ConversationTree()

    def test_initial_branch_is_main(self):
        assert self.tree.current_branch_name == "main"

    def test_initially_empty(self):
        assert len(self.tree.messages) == 0

    def test_add_messages(self):
        self.tree.messages.append({"role": "user", "content": "Hello"})
        assert len(self.tree.messages) == 1

    def test_branch_creates_new(self):
        bid = self.tree.branch("test")
        assert bid is not None
        assert self.tree.current_branch_name == "test"

    def test_branch_copies_messages(self):
        self.tree.messages.append({"role": "user", "content": "Hello"})
        self.tree.branch("copy")
        assert len(self.tree.messages) == 1

    def test_branch_independence(self):
        self.tree.messages.append({"role": "user", "content": "Original"})
        self.tree.branch("fork")
        self.tree.messages.append({"role": "user", "content": "Fork only"})
        assert len(self.tree.messages) == 2
        self.tree.checkout("main")
        assert len(self.tree.messages) == 1

    def test_checkout_by_name(self):
        self.tree.branch("test")
        self.tree.checkout("main")
        assert self.tree.current_branch_name == "main"

    def test_checkout_by_id(self):
        bid = self.tree.branch("test")
        self.tree.checkout("main")
        assert self.tree.checkout(bid) is True
        assert self.tree.current_branch_name == "test"

    def test_checkout_nonexistent(self):
        assert self.tree.checkout("nonexistent") is False

    def test_delete_branch(self):
        self.tree.branch("to-delete")
        self.tree.checkout("main")
        assert self.tree.delete_branch("to-delete") is True

    def test_delete_main_fails(self):
        assert self.tree.delete_branch("main") is False

    def test_delete_current_fails(self):
        self.tree.branch("current")
        assert self.tree.delete_branch("current") is False

    def test_merge_branches(self):
        self.tree.messages.append({"role": "user", "content": "Hello"})
        self.tree.branch("feature")
        self.tree.messages.append({"role": "user", "content": "Feature work"})
        self.tree.checkout("main")
        result = self.tree.merge("feature")
        assert result is True
        assert len(self.tree.messages) > 1

    def test_merge_nonexistent(self):
        assert self.tree.merge("nonexistent") is False

    def test_list_branches(self):
        self.tree.branch("a")
        self.tree.branch("b")
        self.tree.checkout("main")
        branches = self.tree.list_branches()
        assert len(branches) == 3  # main, a, b

    def test_get_branch_messages(self):
        self.tree.messages.append({"role": "user", "content": "Hello"})
        self.tree.branch("test")
        self.tree.messages.append({"role": "user", "content": "In branch"})
        msgs = self.tree.get_branch_messages("test")
        assert len(msgs) == 2

    def test_to_dict(self):
        d = self.tree.to_dict()
        assert "current_branch" in d
        assert "branches" in d

    def test_auto_branch_name(self):
        bid = self.tree.branch()
        assert self.tree.current_branch_name.startswith("branch-")


# ═══════════════════════════════════════════════════════════════
# RateLimiter Tests
# ═══════════════════════════════════════════════════════════════

class TestRateLimiter:
    def test_init(self):
        rl = RateLimiter(requests_per_minute=60, tokens_per_minute=100000)
        assert rl.rpm == 60
        assert rl.tpm == 100000

    @pytest.mark.asyncio
    async def test_acquire_within_limits(self):
        rl = RateLimiter(requests_per_minute=60, tokens_per_minute=100000)
        await rl.acquire(100)  # Should not block

    @pytest.mark.asyncio
    async def test_multiple_acquires(self):
        rl = RateLimiter(requests_per_minute=60, tokens_per_minute=100000)
        for _ in range(5):
            await rl.acquire(100)

    def test_update_actual_tokens(self):
        rl = RateLimiter(requests_per_minute=60, tokens_per_minute=100000)
        rl._token_counts = [(time.time(), 1000)]
        rl.update_actual_tokens(500)
        assert rl._token_counts[-1][1] == 500


# ═══════════════════════════════════════════════════════════════
# CircuitBreaker Tests
# ═══════════════════════════════════════════════════════════════

class TestCircuitBreaker:
    def test_initial_state_closed(self):
        cb = _CircuitBreaker(failure_threshold=3, recovery_timeout=5.0)
        assert cb.state.value == "closed"

    def test_allow_request_closed(self):
        cb = _CircuitBreaker()
        assert cb.allow_request() is True

    def test_opens_after_threshold(self):
        cb = _CircuitBreaker(failure_threshold=3)
        for _ in range(3):
            cb.record_failure()
        assert cb.state.value == "open"
        assert cb.allow_request() is False

    def test_recovery_to_half_open(self):
        cb = _CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)
        cb.record_failure()
        cb.record_failure()
        assert cb.state.value == "open"
        time.sleep(0.15)
        assert cb.allow_request() is True
        assert cb.state.value == "half_open"

    def test_success_resets_failure_count(self):
        cb = _CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.failure_count < 2

    def test_to_dict(self):
        cb = _CircuitBreaker()
        d = cb.to_dict()
        assert "state" in d
        assert "failure_count" in d

    def test_half_open_failure_reopens(self):
        cb = _CircuitBreaker(failure_threshold=2, recovery_timeout=0.01)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.02)
        cb.allow_request()  # moves to half_open
        cb.record_failure()
        assert cb.state.value == "open"


# ═══════════════════════════════════════════════════════════════
# ProviderHealth Tests
# ═══════════════════════════════════════════════════════════════

class TestProviderHealth:
    def test_initial_state(self):
        ph = ProviderHealth()
        assert ph.status == ProviderStatus.UNKNOWN

    def test_record_success(self):
        ph = ProviderHealth()
        ph.record_success(150.0)
        assert ph.status == ProviderStatus.HEALTHY
        assert ph.total_requests == 1
        assert ph.consecutive_failures == 0

    def test_record_failure(self):
        ph = ProviderHealth()
        ph.record_failure()
        assert ph.total_failures == 1

    def test_degraded_after_failure(self):
        ph = ProviderHealth()
        ph.record_failure()
        assert ph.status == ProviderStatus.DEGRADED

    def test_unhealthy_after_three_failures(self):
        ph = ProviderHealth()
        ph.record_failure()
        ph.record_failure()
        ph.record_failure()
        assert ph.status == ProviderStatus.UNHEALTHY

    def test_success_resets_consecutive(self):
        ph = ProviderHealth()
        ph.record_failure()
        ph.record_success(100.0)
        assert ph.consecutive_failures == 0

    def test_failure_rate(self):
        ph = ProviderHealth()
        ph.record_success(100.0)
        ph.record_failure()
        assert ph.failure_rate == 0.5

    def test_failure_rate_zero_requests(self):
        ph = ProviderHealth()
        assert ph.failure_rate == 0.0

    def test_avg_latency(self):
        ph = ProviderHealth()
        ph.record_success(100.0)
        ph.record_success(200.0)
        assert ph.avg_latency_ms == 150.0

    def test_to_dict(self):
        ph = ProviderHealth()
        ph.record_success(100.0)
        d = ph.to_dict()
        assert "status" in d
        assert "avg_latency_ms" in d


# ═══════════════════════════════════════════════════════════════
# SSEEvent Tests
# ═══════════════════════════════════════════════════════════════

class TestSSEEvent:
    def test_token_event(self):
        e = SSEEvent.token("hello", "req-1")
        encoded = e.encode()
        assert "event: token" in encoded
        assert "data:" in encoded
        assert "hello" in encoded

    def test_done_event(self):
        e = SSEEvent.done("req-1")
        encoded = e.encode()
        assert "event: done" in encoded
        assert "done" in encoded

    def test_error_event(self):
        e = SSEEvent.error("something broke", "req-1")
        encoded = e.encode()
        assert "event: error" in encoded
        assert "something broke" in encoded

    def test_tool_call_event(self):
        calls = [{"id": "1", "function": {"name": "test", "arguments": "{}"}}]
        e = SSEEvent.tool_call(calls, "req-1")
        encoded = e.encode()
        assert "event: tool_calls" in encoded

    def test_multiline_data(self):
        e = SSEEvent("line1\nline2\nline3")
        encoded = e.encode()
        data_lines = [l for l in encoded.split("\n") if l.startswith("data:")]
        assert len(data_lines) == 3

    def test_empty_data(self):
        e = SSEEvent("")
        encoded = e.encode()
        assert "data: \n" in encoded

    def test_done_with_usage(self):
        usage = {"total_tokens": 100}
        e = SSEEvent.done("req-1", usage=usage)
        encoded = e.encode()
        assert "total_tokens" in encoded


# ═══════════════════════════════════════════════════════════════
# ToolExecutor Tests
# ═══════════════════════════════════════════════════════════════

class TestToolExecutor:
    @pytest.mark.asyncio
    async def test_empty_execute(self):
        te = ToolExecutor()
        results = await te.execute([])
        assert results == []

    @pytest.mark.asyncio
    async def test_register_and_execute(self):
        te = ToolExecutor()
        te.register_sync("echo", lambda text="": f"echo: {text}")
        calls = [{"id": "1", "function": {"name": "echo", "arguments": '{"text": "hello"}'}}]
        results = await te.execute(calls)
        assert len(results) == 1
        assert results[0].result == "echo: hello"

    @pytest.mark.asyncio
    async def test_unknown_tool(self):
        te = ToolExecutor()
        calls = [{"id": "1", "function": {"name": "nonexistent", "arguments": "{}"}}]
        results = await te.execute(calls)
        assert len(results) == 1
        assert results[0].error is not None

    @pytest.mark.asyncio
    async def test_tool_error(self):
        te = ToolExecutor()
        te.register_sync("fail", lambda: 1 / 0)
        calls = [{"id": "1", "function": {"name": "fail", "arguments": "{}"}}]
        results = await te.execute(calls)
        assert results[0].error is not None

    @pytest.mark.asyncio
    async def test_async_handler(self):
        te = ToolExecutor()

        async def async_echo(text=""):
            return f"async: {text}"

        te.register("echo", async_echo)
        calls = [{"id": "1", "function": {"name": "echo", "arguments": '{"text": "test"}'}}]
        results = await te.execute(calls)
        assert results[0].result == "async: test"

    def test_available_tools(self):
        te = ToolExecutor()
        te.register_sync("a", lambda: "a")
        te.register_sync("b", lambda: "b")
        assert set(te.available_tools) == {"a", "b"}

    @pytest.mark.asyncio
    async def test_multiple_calls(self):
        te = ToolExecutor()
        te.register_sync("add", lambda a=0, b=0: str(int(a) + int(b)))
        calls = [
            {"id": "1", "function": {"name": "add", "arguments": '{"a": "1", "b": "2"}'}},
            {"id": "2", "function": {"name": "add", "arguments": '{"a": "3", "b": "4"}'}},
        ]
        results = await te.execute(calls)
        assert len(results) == 2
        assert results[0].result == "3"
        assert results[1].result == "7"

    @pytest.mark.asyncio
    async def test_latency_tracking(self):
        te = ToolExecutor()
        te.register_sync("echo", lambda: "ok")
        calls = [{"id": "1", "function": {"name": "echo", "arguments": "{}"}}]
        results = await te.execute(calls)
        assert results[0].latency_ms >= 0


# ═══════════════════════════════════════════════════════════════
# RallyConfig Tests
# ═══════════════════════════════════════════════════════════════

class TestRallyConfig:
    def test_default_config(self):
        config = RallyConfig()
        assert config.get("agent.name") == "Rally"
        assert config.get("agent.version") == "2.0.0"
        assert config.get("agent.default_model") == "auto"

    def test_get_with_default(self):
        config = RallyConfig()
        assert config.get("nonexistent.key", "default") == "default"

    def test_set_and_get(self):
        config = RallyConfig()
        config.set("agent.name", "TestBot")
        assert config.get("agent.name") == "TestBot"

    def test_nested_keys(self):
        config = RallyConfig()
        assert config.get("memory.backend") == "hybrid"
        assert config.get("security.audit_log") is True

    def test_data_dict(self):
        config = RallyConfig()
        assert "agent" in config.data
        assert "memory" in config.data
        assert "security" in config.data


# ═══════════════════════════════════════════════════════════════
# Integration: RallyEngine Tests
# ═══════════════════════════════════════════════════════════════

class TestRallyEngine:
    def setup_method(self):
        from core.engine import RallyEngine
        config = RallyConfig()
        self.engine = RallyEngine(config)

    def test_initialize(self):
        self.engine.initialize()
        assert self.engine.initialized is True

    def test_double_initialize(self):
        self.engine.initialize()
        self.engine.initialize()  # Should not error
        assert self.engine.initialized is True

    def test_branch_operations(self):
        self.engine.initialize()
        bid = self.engine.branch("test")
        assert bid is not None
        assert self.engine.checkout("test") is True
        self.engine.checkout("main")
        assert self.engine.delete_branch("test") is True

    def test_model_operations(self):
        self.engine.initialize()
        self.engine.set_model("gpt-4")
        assert self.engine.current_model == "gpt-4"
        self.engine.set_model("auto")

    def test_thinking_toggle(self):
        self.engine.initialize()
        original = self.engine.thinking_enabled
        self.engine.toggle_thinking()
        assert self.engine.thinking_enabled != original
        self.engine.toggle_thinking()
        assert self.engine.thinking_enabled == original

    def test_compact_toggle(self):
        self.engine.initialize()
        assert self.engine.compact_mode is False
        self.engine.toggle_compact()
        assert self.engine.compact_mode is True
        self.engine.toggle_compact()
        assert self.engine.compact_mode is False

    def test_save_load_conversation(self):
        import tempfile, os
        self.engine.initialize()
        self.engine.conversation.messages.append({"role": "user", "content": "test"})
        tmp = tempfile.mktemp(suffix=".json")
        self.engine.save_conversation(tmp)
        self.engine.load_conversation(tmp)
        os.unlink(tmp)

    def test_shutdown(self):
        self.engine.initialize()
        self.engine.shutdown()

    def test_cron_operations(self):
        self.engine.initialize()
        jobs = self.engine.list_cron_jobs()
        assert isinstance(jobs, list)

    def test_get_user_profile(self):
        self.engine.initialize()
        profile = self.engine.get_user_profile()
        assert isinstance(profile, dict)

    def test_get_knowledge_graph_stats(self):
        self.engine.initialize()
        stats = self.engine.get_knowledge_graph_stats()
        assert isinstance(stats, dict)

    def test_get_improvement_report(self):
        self.engine.initialize()
        report = self.engine.get_improvement_report()
        assert isinstance(report, dict)
