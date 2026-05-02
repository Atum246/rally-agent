"""
🟣 Rally Agent — Core Engine
The brain that powers everything.
Rewritten with: streaming, function calling, circuit breakers, request queuing,
conversation branching, token management, and proper error handling.
"""

import asyncio
import time
import os
import json
import uuid
import logging
import hashlib
from typing import Optional, Any, AsyncIterator, Callable, Awaitable
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
from collections import deque

from core.config import RallyConfig
from core.providers import (
    ProviderManager, ChatResponse, TokenUsage,
    ToolDefinition, ProviderStatus,
)

logger = logging.getLogger("rally.engine")


# ═══════════════════════════════════════════════════════════════
# 📊 Token Counter & Context Window Manager
# ═══════════════════════════════════════════════════════════════

class TokenCounter:
    """Tracks token usage and manages context windows."""

    def __init__(self, max_context: int = 128000, max_output: int = 4096):
        self.max_context = max_context
        self.max_output = max_output
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_requests = 0

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Estimate token count for a string."""
        if not text:
            return 0
        cjk = sum(1 for c in text if '\u4e00' <= c <= '\u9fff' or '\u3000' <= c <= '\u303f')
        ascii_chars = len(text) - cjk
        return (ascii_chars // 4) + (cjk // 2) + 1

    def estimate_messages_tokens(self, messages: list[dict]) -> int:
        """Estimate total tokens for a message list."""
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += self.estimate_tokens(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and "text" in part:
                        total += self.estimate_tokens(part["text"])
            total += 4  # message framing
        total += 2  # conversation priming
        return total

    def trim_messages(
        self, messages: list[dict], reserved_output: int = 0, system_tokens: int = 0
    ) -> list[dict]:
        """Trim messages to fit within context window.
        
        Preserves the system message and most recent messages.
        """
        if not messages:
            return messages

        available = self.max_context - (reserved_output or self.max_output) - system_tokens
        if available <= 0:
            available = self.max_context // 2

        # Separate system messages from conversation
        system_msgs = [m for m in messages if m.get("role") == "system"]
        conv_msgs = [m for m in messages if m.get("role") != "system"]

        # Always keep system messages
        system_tokens_used = self.estimate_messages_tokens(system_msgs)

        # Trim conversation from the front, keeping recent messages
        kept: list[dict] = []
        used = 0
        for msg in reversed(conv_msgs):
            msg_tokens = self.estimate_messages_tokens([msg])
            if used + msg_tokens > available - system_tokens_used:
                break
            kept.append(msg)
            used += msg_tokens

        kept.reverse()
        return system_msgs + kept

    def record_usage(self, prompt_tokens: int, completion_tokens: int) -> None:
        """Record token usage from a completed request."""
        self.total_prompt_tokens += prompt_tokens
        self.total_completion_tokens += completion_tokens
        self.total_requests += 1

    @property
    def total_tokens_used(self) -> int:
        return self.total_prompt_tokens + self.total_completion_tokens

    def to_dict(self) -> dict:
        return {
            "max_context": self.max_context,
            "max_output": self.max_output,
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_tokens_used": self.total_tokens_used,
            "total_requests": self.total_requests,
        }


# ═══════════════════════════════════════════════════════════════
# 🌿 Conversation Branching
# ═══════════════════════════════════════════════════════════════

@dataclass
class ConversationBranch:
    """A branch in the conversation tree (like git branches)."""
    id: str
    name: str
    parent_id: Optional[str]
    messages: list[dict] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "parent_id": self.parent_id,
            "message_count": len(self.messages),
            "created_at": self.created_at,
            "metadata": self.metadata,
        }


class ConversationTree:
    """Git-like conversation branching system.

    Supports:
    - Multiple named branches
    - Branching from any point
    - Merging branches
    - Switching between branches
    """

    def __init__(self):
        main_id = str(uuid.uuid4())[:8]
        self._branches: dict[str, ConversationBranch] = {
            main_id: ConversationBranch(id=main_id, name="main", parent_id=None),
        }
        self._current_branch_id: str = main_id
        self._branch_point: dict[str, int] = {}  # branch_id -> message index at fork

    @property
    def current(self) -> ConversationBranch:
        return self._branches[self._current_branch_id]

    @property
    def current_branch_name(self) -> str:
        return self.current.name

    @property
    def messages(self) -> list[dict]:
        return self.current.messages

    @messages.setter
    def messages(self, value: list[dict]) -> None:
        self.current.messages = value

    def branch(self, name: Optional[str] = None) -> str:
        """Create a new branch from the current position.
        
        Returns the new branch ID.
        """
        current = self.current
        new_id = str(uuid.uuid4())[:8]
        if name is None:
            name = f"branch-{new_id}"
        new_branch = ConversationBranch(
            id=new_id,
            name=name,
            parent_id=self._current_branch_id,
            messages=list(current.messages),  # Deep copy of messages
        )
        self._branches[new_id] = new_branch
        self._branch_point[new_id] = len(current.messages)
        self._current_branch_id = new_id
        logger.info(f"Created branch '{name}' ({new_id}) from '{current.name}'")
        return new_id

    def checkout(self, branch_name_or_id: str) -> bool:
        """Switch to a branch by name or ID."""
        # Try by ID first
        if branch_name_or_id in self._branches:
            self._current_branch_id = branch_name_or_id
            return True
        # Try by name
        for bid, b in self._branches.items():
            if b.name == branch_name_or_id:
                self._current_branch_id = bid
                return True
        return False

    def delete_branch(self, branch_name_or_id: str) -> bool:
        """Delete a branch (cannot delete current or main)."""
        target_id = None
        for bid, b in self._branches.items():
            if bid == branch_name_or_id or b.name == branch_name_or_id:
                target_id = bid
                break
        if target_id is None:
            return False
        if target_id == self._current_branch_id:
            return False  # Cannot delete current branch
        if self._branches[target_id].name == "main":
            return False  # Cannot delete main
        del self._branches[target_id]
        return True

    def merge(self, source_name_or_id: str, message: str = "") -> bool:
        """Merge another branch into the current branch.
        
        Appends source messages after the branch point.
        """
        source = None
        for bid, b in self._branches.items():
            if bid == source_name_or_id or b.name == source_name_or_id:
                source = b
                break
        if source is None or source.id == self._current_branch_id:
            return False

        current = self.current
        # Find common ancestor point
        fork_point = self._branch_point.get(source.id, 0)
        # Append source messages after fork point
        new_messages = source.messages[fork_point:]
        if message:
            new_messages.insert(0, {"role": "system", "content": f"[Merged from branch '{source.name}']: {message}"})
        current.messages.extend(new_messages)
        logger.info(f"Merged '{source.name}' into '{current.name}' (+{len(new_messages)} messages)")
        return True

    def list_branches(self) -> list[dict]:
        """List all branches."""
        result = []
        for bid, b in self._branches.items():
            info = b.to_dict()
            info["is_current"] = bid == self._current_branch_id
            result.append(info)
        return result

    def get_branch_messages(self, branch_name_or_id: str) -> list[dict]:
        """Get messages from a specific branch."""
        for bid, b in self._branches.items():
            if bid == branch_name_or_id or b.name == branch_name_or_id:
                return list(b.messages)
        return []

    def to_dict(self) -> dict:
        return {
            "current_branch": self._current_branch_id,
            "branches": {bid: b.to_dict() for bid, b in self._branches.items()},
        }


# ═══════════════════════════════════════════════════════════════
# 📬 Request Queue
# ═══════════════════════════════════════════════════════════════

@dataclass
class QueuedRequest:
    """A queued chat request."""
    id: str
    messages: list[dict]
    model: str
    kwargs: dict
    future: asyncio.Future
    created_at: float = field(default_factory=time.time)
    priority: int = 0  # lower = higher priority

    def __lt__(self, other: "QueuedRequest") -> bool:
        return self.priority < other.priority


class RequestQueue:
    """Async request queue with priority support and concurrency limiting."""

    def __init__(self, max_size: int = 100, max_concurrent: int = 5):
        self.max_size = max_size
        self.max_concurrent = max_concurrent
        self._queue: asyncio.PriorityQueue[QueuedRequest] = asyncio.PriorityQueue(maxsize=max_size)
        self._active: int = 0
        self._total_processed: int = 0
        self._total_rejected: int = 0
        self._processing = False
        self._process_task: Optional[asyncio.Task] = None
        self._handler: Optional[Callable[[QueuedRequest], Awaitable[None]]] = None

    def set_handler(self, handler: Callable[[QueuedRequest], Awaitable[None]]) -> None:
        """Set the request handler function."""
        self._handler = handler

    async def enqueue(
        self,
        messages: list[dict],
        model: str = "auto",
        priority: int = 0,
        **kwargs: Any,
    ) -> str:
        """Enqueue a chat request. Returns request ID."""
        if self._queue.qsize() >= self.max_size:
            self._total_rejected += 1
            raise RuntimeError(f"Request queue full ({self.max_size})")

        request_id = str(uuid.uuid4())[:12]
        future: asyncio.Future[str] = asyncio.get_event_loop().create_future()
        request = QueuedRequest(
            id=request_id,
            messages=messages,
            model=model,
            kwargs=kwargs,
            future=future,
            priority=priority,
        )
        await self._queue.put(request)
        logger.debug(f"Enqueued request {request_id} (queue size: {self._queue.qsize()})")

        # Start processing if not already running
        if not self._processing:
            self._start_processing()

        return request_id

    async def enqueue_and_wait(
        self,
        messages: list[dict],
        model: str = "auto",
        priority: int = 0,
        timeout: float = 300.0,
        **kwargs: Any,
    ) -> str:
        """Enqueue and wait for result."""
        request_id = str(uuid.uuid4())[:12]
        future: asyncio.Future[str] = asyncio.get_event_loop().create_future()
        request = QueuedRequest(
            id=request_id,
            messages=messages,
            model=model,
            kwargs=kwargs,
            future=future,
            priority=priority,
        )
        await self._queue.put(request)

        if not self._processing:
            self._start_processing()

        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            raise RuntimeError(f"Request {request_id} timed out after {timeout}s")

    def _start_processing(self) -> None:
        """Start the background processing task."""
        if self._processing:
            return
        self._processing = True
        try:
            loop = asyncio.get_event_loop()
            self._process_task = loop.create_task(self._process_loop())
        except RuntimeError:
            # No event loop (e.g. during import)
            self._processing = False

    async def _process_loop(self) -> None:
        """Background loop that processes queued requests."""
        try:
            while not self._queue.empty() or self._active > 0:
                if self._active >= self.max_concurrent:
                    await asyncio.sleep(0.05)
                    continue
                try:
                    request = await asyncio.wait_for(self._queue.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    if self._active == 0:
                        break
                    continue

                self._active += 1
                asyncio.create_task(self._process_request(request))
        except Exception as e:
            logger.error(f"Queue processing error: {e}")
        finally:
            self._processing = False

    async def _process_request(self, request: QueuedRequest) -> None:
        """Process a single queued request."""
        try:
            if self._handler:
                result = await self._handler(request)
                if not request.future.done():
                    request.future.set_result(result)
            else:
                if not request.future.done():
                    request.future.set_exception(RuntimeError("No handler set"))
        except Exception as e:
            if not request.future.done():
                request.future.set_exception(e)
        finally:
            self._active -= 1
            self._total_processed += 1

    def stats(self) -> dict:
        return {
            "queue_size": self._queue.qsize(),
            "active": self._active,
            "max_size": self.max_size,
            "max_concurrent": self.max_concurrent,
            "total_processed": self._total_processed,
            "total_rejected": self._total_rejected,
        }


# ═══════════════════════════════════════════════════════════════
# 🔄 Retry Logic
# ═══════════════════════════════════════════════════════════════

async def retry_with_backoff(
    func: Callable[..., Awaitable[Any]],
    *args: Any,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    retryable_exceptions: tuple = (ConnectionError, TimeoutError, OSError),
    **kwargs: Any,
) -> Any:
    """Execute an async function with exponential backoff retry.
    
    Args:
        func: Async function to call
        max_attempts: Maximum number of attempts (0 = no retry)
        base_delay: Base delay in seconds
        max_delay: Maximum delay in seconds
        retryable_exceptions: Exception types that trigger retry
    """
    last_exc: Optional[Exception] = None
    for attempt in range(max_attempts + 1):
        try:
            return await func(*args, **kwargs)
        except retryable_exceptions as e:
            last_exc = e
            if attempt < max_attempts:
                delay = min(base_delay * (2 ** attempt), max_delay)
                logger.warning(
                    f"Attempt {attempt + 1}/{max_attempts + 1} failed: {e}. "
                    f"Retrying in {delay:.1f}s"
                )
                await asyncio.sleep(delay)
            else:
                logger.error(f"All {max_attempts + 1} attempts failed: {e}")
        except Exception:
            raise
    raise last_exc  # type: ignore[misc]


# ═══════════════════════════════════════════════════════════════
# 📡 SSE (Server-Sent Events) for Web Streaming
# ═══════════════════════════════════════════════════════════════

class SSEEvent:
    """Server-Sent Event for web streaming."""

    def __init__(
        self,
        data: str,
        event: str = "message",
        id: Optional[str] = None,
        retry: Optional[int] = None,
    ):
        self.data = data
        self.event = event
        self.id = id
        self.retry = retry

    def encode(self) -> str:
        """Encode as SSE wire format."""
        lines = []
        if self.event:
            lines.append(f"event: {self.event}")
        if self.id:
            lines.append(f"id: {self.id}")
        if self.retry:
            lines.append(f"retry: {self.retry}")
        for line in self.data.split("\n"):
            lines.append(f"data: {line}")
        lines.append("")
        lines.append("")
        return "\n".join(lines)

    @staticmethod
    def token(text: str, request_id: str = "") -> "SSEEvent":
        return SSEEvent(
            data=json.dumps({"type": "token", "content": text, "request_id": request_id}),
            event="token",
            id=request_id,
        )

    @staticmethod
    def done(request_id: str = "", usage: Optional[dict] = None) -> "SSEEvent":
        payload: dict[str, Any] = {"type": "done", "request_id": request_id}
        if usage:
            payload["usage"] = usage
        return SSEEvent(
            data=json.dumps(payload),
            event="done",
            id=request_id,
        )

    @staticmethod
    def error(message: str, request_id: str = "") -> "SSEEvent":
        return SSEEvent(
            data=json.dumps({"type": "error", "error": message, "request_id": request_id}),
            event="error",
            id=request_id,
        )

    @staticmethod
    def tool_call(tool_calls: list[dict], request_id: str = "") -> "SSEEvent":
        return SSEEvent(
            data=json.dumps({"type": "tool_calls", "tool_calls": tool_calls, "request_id": request_id}),
            event="tool_calls",
            id=request_id,
        )


# ═══════════════════════════════════════════════════════════════
# 🔧 Tool / Function Calling Integration
# ═══════════════════════════════════════════════════════════════

@dataclass
class ToolCallResult:
    """Result of executing a tool call."""
    tool_call_id: str
    name: str
    result: str
    error: Optional[str] = None
    latency_ms: float = 0.0


class ToolExecutor:
    """Executes tool calls from LLM responses."""

    def __init__(self):
        self._handlers: dict[str, Callable[..., Awaitable[str]]] = {}

    def register(self, name: str, handler: Callable[..., Awaitable[str]]) -> None:
        """Register a tool handler. handler(**kwargs) -> str result."""
        self._handlers[name] = handler
        logger.debug(f"Registered tool handler: {name}")

    def register_sync(self, name: str, handler: Callable[..., str]) -> None:
        """Register a synchronous tool handler."""
        async def async_handler(**kwargs: Any) -> str:
            return handler(**kwargs)
        self._handlers[name] = async_handler

    async def execute(self, tool_calls: list[dict]) -> list[ToolCallResult]:
        """Execute a list of tool calls and return results."""
        results: list[ToolCallResult] = []
        for tc in tool_calls:
            func = tc.get("function", {})
            name = func.get("name", "")
            call_id = tc.get("id", "")
            args_raw = func.get("arguments", "{}")

            if isinstance(args_raw, str):
                try:
                    args = json.loads(args_raw)
                except json.JSONDecodeError:
                    args = {}
            else:
                args = args_raw

            handler = self._handlers.get(name)
            if handler is None:
                results.append(ToolCallResult(
                    tool_call_id=call_id, name=name, result="",
                    error=f"Unknown tool: {name}",
                ))
                continue

            start = time.time()
            try:
                result = await handler(**args)
                results.append(ToolCallResult(
                    tool_call_id=call_id, name=name, result=result,
                    latency_ms=(time.time() - start) * 1000,
                ))
            except Exception as e:
                results.append(ToolCallResult(
                    tool_call_id=call_id, name=name, result="",
                    error=str(e), latency_ms=(time.time() - start) * 1000,
                ))
        return results

    @property
    def available_tools(self) -> list[str]:
        return list(self._handlers.keys())


# ═══════════════════════════════════════════════════════════════
# ⚡ Rally Engine — The Brain
# ═══════════════════════════════════════════════════════════════

class RallyEngine:
    """Core engine for Rally Agent.

    Features:
    - Streaming responses (SSE for web, token-by-token for CLI)
    - Proper async conversation loop with function calling
    - Retry logic with exponential backoff
    - Automatic provider fallback chain
    - Circuit breaker pattern for dead providers
    - Request queuing
    - Conversation branching (like git branches)
    - Token counting and context window management
    """

    def __init__(self, config: RallyConfig):
        self.config = config
        self.start_time = time.time()
        self.initialized = False

        # Core systems
        self.conversation = ConversationTree()
        self.token_counter = TokenCounter(
            max_context=config.get("agent.max_context", 128000),
            max_output=config.get("agent.max_tokens", 4096),
        )
        self.providers: Optional[ProviderManager] = None
        self.request_queue = RequestQueue(
            max_size=config.get("engine.request_queue_size", 100),
            max_concurrent=5,
        )
        self.tool_executor = ToolExecutor()
        self.tool_definitions: list[ToolDefinition] = []

        # Subsystems (lazy init)
        self.memory: Any = None
        self.tools: Any = None
        self.agents: Any = None

        # State
        self.current_model = config.get("agent.default_model", "auto")
        self.thinking_enabled = config.get("agent.thinking", True)
        self.compact_mode = False

        # Retry config
        self._retry_max = config.get("engine.retry_max_attempts", 3)
        self._retry_base = config.get("engine.retry_base_delay", 1.0)
        self._retry_max_delay = config.get("engine.retry_max_delay", 60.0)

        # Set up request queue handler
        self.request_queue.set_handler(self._process_queued_request)

    # ── Initialization ───────────────────────────────────────

    def initialize(self) -> None:
        """Initialize all subsystems."""
        if self.initialized:
            return

        try:
            from cli.theme import Theme
            Theme.step("⚡ Initializing Rally Agent")
            _theme = Theme
        except ImportError:
            _theme = None
            logger.info("⚡ Initializing Rally Agent")

        self._init_memory()
        self._init_tools()
        self._init_agents()
        self._init_providers()

        self.initialized = True
        if _theme:
            _theme.success("Rally Agent ready! 🚀")
        else:
            logger.info("Rally Agent ready! 🚀")

    def _init_memory(self) -> None:
        try:
            from memory.store import MemoryStore
            self.memory = MemoryStore(self.config)
        except Exception as e:
            logger.warning(f"Memory init failed: {e}")

    def _init_tools(self) -> None:
        try:
            from tools.registry import ToolRegistry
            self.tools = ToolRegistry(self.config)
            count = len(self.tools.get_all()) if self.tools else 0
            logger.info(f"Tools: {count} loaded")
        except Exception as e:
            logger.warning(f"Tools init failed: {e}")

    def _init_agents(self) -> None:
        try:
            from agents.orchestrator import AgentOrchestrator
            self.agents = AgentOrchestrator(self.config)
        except Exception as e:
            logger.warning(f"Agents init failed: {e}")

    def _init_providers(self) -> None:
        from core.providers import ProviderManager
        self.providers = ProviderManager(self.config)
        available = self.providers.get_available()
        if available:
            logger.info(f"Providers: {', '.join(available)}")
        else:
            logger.warning("No API keys configured — using local fallback")

    # ── Chat (Non-Streaming) ─────────────────────────────────

    async def chat(self, message: str, **kwargs: Any) -> str:
        """Process a chat message and return the full response."""
        if not self.initialized:
            self.initialize()

        # Add to conversation
        self.conversation.messages.append({
            "role": "user",
            "content": message,
            "timestamp": datetime.now().isoformat(),
        })

        # Store in memory
        if self.memory:
            try:
                self.memory.add("user", message)
            except Exception:
                pass

        # Check if it's a tool call
        if message.startswith("!"):
            return await self._handle_tool_call(message[1:])

        # Get system context
        system_prompt = self._build_system_prompt()

        # Build messages for provider
        messages = self._build_messages(system_prompt)

        # Get response with retry + fallback
        try:
            response = await self._chat_with_retry(messages, **kwargs)

            # Add to conversation
            self.conversation.messages.append({
                "role": "assistant",
                "content": response,
                "timestamp": datetime.now().isoformat(),
            })

            # Store in memory
            if self.memory:
                try:
                    self.memory.add("assistant", response)
                except Exception:
                    pass

            return response

        except Exception as e:
            logger.error(f"Chat error: {e}")
            return self._fallback_response(message)

    # ── Streaming Chat (Token-by-Token) ──────────────────────

    async def chat_stream(self, message: str, **kwargs: Any) -> AsyncIterator[str]:
        """Process a chat message and stream the response token by token.
        
        Yields string tokens as they arrive from the provider.
        """
        if not self.initialized:
            self.initialize()

        # Add to conversation
        self.conversation.messages.append({
            "role": "user",
            "content": message,
            "timestamp": datetime.now().isoformat(),
        })
        if self.memory:
            try:
                self.memory.add("user", message)
            except Exception:
                pass

        if message.startswith("!"):
            result = await self._handle_tool_call(message[1:])
            yield result
            return

        system_prompt = self._build_system_prompt()
        messages = self._build_messages(system_prompt)

        full_response = ""
        try:
            async for token in self._stream_with_fallback(messages, **kwargs):
                full_response += token
                yield token

            # Add complete response to conversation
            self.conversation.messages.append({
                "role": "assistant",
                "content": full_response,
                "timestamp": datetime.now().isoformat(),
            })
            if self.memory:
                try:
                    self.memory.add("assistant", full_response)
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"Stream error: {e}")
            fallback = self._fallback_response(message)
            if full_response:
                fallback = full_response + "\n\n" + fallback
            yield fallback

    # ── SSE Streaming (for Web) ──────────────────────────────

    async def chat_sse(self, message: str, **kwargs: Any) -> AsyncIterator[SSEEvent]:
        """Process a chat message and yield SSE events for web clients.
        
        Events: token, done, error, tool_calls
        """
        request_id = str(uuid.uuid4())[:12]

        if not self.initialized:
            self.initialize()

        self.conversation.messages.append({
            "role": "user",
            "content": message,
            "timestamp": datetime.now().isoformat(),
        })
        if self.memory:
            try:
                self.memory.add("user", message)
            except Exception:
                pass

        if message.startswith("!"):
            result = await self._handle_tool_call(message[1:])
            yield SSEEvent.token(result, request_id)
            yield SSEEvent.done(request_id)
            return

        system_prompt = self._build_system_prompt()
        messages = self._build_messages(system_prompt)

        full_response = ""
        try:
            async for token in self._stream_with_fallback(messages, **kwargs):
                full_response += token
                yield SSEEvent.token(token, request_id)

            # Check for tool calls in the response
            tool_calls = self._extract_tool_calls(full_response)
            if tool_calls:
                yield SSEEvent.tool_call(tool_calls, request_id)

                # Execute tools and continue
                tool_results = await self.tool_executor.execute(tool_calls)
                for tr in tool_results:
                    if tr.error:
                        yield SSEEvent.token(f"\n\n⚠️ Tool error ({tr.name}): {tr.error}", request_id)
                    else:
                        # Add tool result to conversation and continue
                        self.conversation.messages.append({
                            "role": "assistant",
                            "content": full_response,
                            "tool_calls": tool_calls,
                        })
                        self.conversation.messages.append({
                            "role": "tool",
                            "content": tr.result,
                            "tool_call_id": tr.tool_call_id,
                            "name": tr.name,
                        })

                        # Get follow-up response
                        messages = self._build_messages(system_prompt)
                        followup = ""
                        async for token in self._stream_with_fallback(messages, **kwargs):
                            followup += token
                            yield SSEEvent.token(token, request_id)
                        full_response += followup

            usage = self.token_counter.to_dict()
            yield SSEEvent.done(request_id, usage=usage)

            # Add complete response to conversation
            self.conversation.messages.append({
                "role": "assistant",
                "content": full_response,
                "timestamp": datetime.now().isoformat(),
            })
            if self.memory:
                try:
                    self.memory.add("assistant", full_response)
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"SSE error: {e}")
            yield SSEEvent.error(str(e), request_id)

    # ── Function Calling Chat ────────────────────────────────

    async def chat_with_tools(
        self,
        message: str,
        tools: Optional[list[ToolDefinition]] = None,
        max_rounds: int = 5,
        **kwargs: Any,
    ) -> ChatResponse:
        """Chat with function calling support.
        
        Handles multi-round tool calling automatically.
        """
        if not self.initialized:
            self.initialize()

        self.conversation.messages.append({
            "role": "user",
            "content": message,
            "timestamp": datetime.now().isoformat(),
        })
        if self.memory:
            try:
                self.memory.add("user", message)
            except Exception:
                pass

        active_tools = tools or self.tool_definitions
        if not active_tools:
            # No tools, plain chat
            text = await self.chat(message, **kwargs)
            return ChatResponse(content=text)

        system_prompt = self._build_system_prompt()
        messages = self._build_messages(system_prompt)

        # Multi-round tool calling loop
        for round_num in range(max_rounds):
            try:
                response = await self.providers.chat_with_tools(
                    messages, active_tools, model=self.current_model, **kwargs
                )
            except Exception as e:
                logger.error(f"Tool chat round {round_num} failed: {e}")
                break

            # Record token usage
            if response.token_usage:
                self.token_counter.record_usage(
                    response.token_usage.prompt_tokens,
                    response.token_usage.completion_tokens,
                )

            # If no tool calls, we're done
            if not response.tool_calls:
                # Add to conversation
                self.conversation.messages.append({
                    "role": "assistant",
                    "content": response.content,
                    "timestamp": datetime.now().isoformat(),
                })
                if self.memory:
                    try:
                        self.memory.add("assistant", response.content)
                    except Exception:
                        pass
                return response

            # Execute tool calls
            tool_results = await self.tool_executor.execute(response.tool_calls)

            # Add assistant message with tool calls
            self.conversation.messages.append({
                "role": "assistant",
                "content": response.content,
                "tool_calls": response.tool_calls,
            })

            # Add tool results
            for tr in tool_results:
                content = tr.result if not tr.error else f"Error: {tr.error}"
                self.conversation.messages.append({
                    "role": "tool",
                    "content": content,
                    "tool_call_id": tr.tool_call_id,
                    "name": tr.name,
                })

            # Update messages for next round
            messages = self._build_messages(system_prompt)

        # If we exhausted rounds, return last response
        return response  # type: ignore[possibly-undefined]

    # ── Queued Chat ──────────────────────────────────────────

    async def chat_queued(
        self, message: str, priority: int = 0, timeout: float = 300.0, **kwargs: Any
    ) -> str:
        """Submit a chat request to the queue and wait for the result."""
        if not self.initialized:
            self.initialize()

        self.conversation.messages.append({
            "role": "user",
            "content": message,
            "timestamp": datetime.now().isoformat(),
        })

        system_prompt = self._build_system_prompt()
        messages = self._build_messages(system_prompt)

        return await self.request_queue.enqueue_and_wait(
            messages, model=self.current_model, priority=priority, timeout=timeout, **kwargs
        )

    async def _process_queued_request(self, request: QueuedRequest) -> str:
        """Handler for queued requests."""
        try:
            response = await self._chat_with_retry(request.messages, **request.kwargs)
            self.conversation.messages.append({
                "role": "assistant",
                "content": response,
                "timestamp": datetime.now().isoformat(),
            })
            return response
        except Exception as e:
            logger.error(f"Queued request {request.id} failed: {e}")
            raise

    # ── Internal Chat Logic ──────────────────────────────────

    async def _chat_with_retry(self, messages: list[dict], **kwargs: Any) -> str:
        """Send chat with retry and provider fallback."""
        if not self.providers:
            raise RuntimeError("No providers initialized")

        async def _do_chat() -> str:
            return await self.providers.chat(
                messages, model=self.current_model, **kwargs
            )

        return await retry_with_backoff(
            _do_chat,
            max_attempts=self._retry_max,
            base_delay=self._retry_base,
            max_delay=self._retry_max_delay,
        )

    async def _stream_with_fallback(
        self, messages: list[dict], **kwargs: Any
    ) -> AsyncIterator[str]:
        """Stream with provider fallback."""
        if not self.providers:
            raise RuntimeError("No providers initialized")

        try:
            async for chunk in self.providers.chat_stream(
                messages, model=self.current_model, **kwargs
            ):
                yield chunk
        except Exception as e:
            logger.warning(f"Streaming failed, falling back to non-stream: {e}")
            result = await self._chat_with_retry(messages, **kwargs)
            yield result

    # ── Message Building ─────────────────────────────────────

    def _build_system_prompt(self) -> str:
        """Build the system prompt with context."""
        parts = ["You are Rally, a helpful AI agent."]

        # Add user model context if available
        try:
            from core.user_model import UserModel
            if hasattr(self, '_user_model') and self._user_model:
                context = self._user_model.get_context_prompt()
                if context and "No user model" not in context:
                    parts.append(f"\nUser context:\n{context}")
        except Exception:
            pass

        # Add thinking instruction
        if self.thinking_enabled:
            parts.append("\nThink step by step before responding. Show your reasoning.")

        return "\n".join(parts)

    def _build_messages(self, system_prompt: str) -> list[dict]:
        """Build the message list for the provider, with context trimming."""
        messages: list[dict] = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        # Add conversation history
        conv = list(self.conversation.messages)
        messages.extend(conv)

        # Trim to fit context window
        messages = self.token_counter.trim_messages(messages)
        return messages

    def _extract_tool_calls(self, text: str) -> list[dict]:
        """Try to extract tool calls from LLM response text.
        
        Looks for JSON blocks that match tool call format.
        This is a fallback for providers that don't support native tool calling.
        """
        tool_calls: list[dict] = []
        # Look for ```json blocks
        import re
        json_blocks = re.findall(r'```json\s*(\{.*?\})\s*```', text, re.DOTALL)
        for block in json_blocks:
            try:
                data = json.loads(block)
                if "name" in data and ("arguments" in data or "parameters" in data):
                    tool_calls.append({
                        "id": hashlib.md5(block.encode()).hexdigest()[:16],
                        "type": "function",
                        "function": {
                            "name": data["name"],
                            "arguments": json.dumps(data.get("arguments", data.get("parameters", {}))),
                        },
                    })
            except json.JSONDecodeError:
                continue
        return tool_calls

    # ── Fallback ─────────────────────────────────────────────

    def _fallback_response(self, message: str) -> str:
        """Fallback when no provider is available."""
        msg_lower = message.lower()
        if any(w in msg_lower for w in ["hello", "hi", "hey", "sup"]):
            return "Hey! 👋 I'm Rally, your AI agent. I'd love to help, but I need an API key to think. Set OPENAI_API_KEY or ANTHROPIC_API_KEY to get started! 🚀"
        if "help" in msg_lower:
            return "I need an API key to provide intelligent responses. Set one of: OPENAI_API_KEY, ANTHROPIC_API_KEY, or GOOGLE_API_KEY. You can also use local models with Ollama! 🧠"
        return (
            f"I received your message but I need an AI provider configured to respond intelligently.\n\n"
            f"Options:\n"
            f"  1. Set OPENAI_API_KEY for GPT-4\n"
            f"  2. Set ANTHROPIC_API_KEY for Claude\n"
            f"  3. Set GOOGLE_API_KEY for Gemini\n"
            f"  4. Install Ollama for local models\n\n"
            f'Your message was: "{message[:100]}..."'
        )

    # ── Tool Calls ───────────────────────────────────────────

    async def _handle_tool_call(self, command: str) -> str:
        """Handle direct tool calls with ! prefix."""
        parts = command.split(maxsplit=1)
        tool_name = parts[0] if parts else ""
        args = parts[1] if len(parts) > 1 else ""

        if not self.tools:
            return "Tool system not initialized"

        tool = self.tools.get(tool_name)
        if not tool:
            available = ", ".join(self.tools.get_names()) if hasattr(self.tools, "get_names") else "none"
            return f"Unknown tool: {tool_name}\nAvailable: {available}"

        try:
            result = await tool.execute(args)
            return str(result)
        except Exception as e:
            return f"Tool error: {e}"

    # ── Conversation Branching ───────────────────────────────

    def branch(self, name: Optional[str] = None) -> str:
        """Create a new conversation branch."""
        return self.conversation.branch(name)

    def checkout(self, branch: str) -> bool:
        """Switch to a conversation branch."""
        return self.conversation.checkout(branch)

    def merge_branch(self, source: str, message: str = "") -> bool:
        """Merge a branch into the current branch."""
        return self.conversation.merge(source, message)

    def delete_branch(self, branch: str) -> bool:
        """Delete a conversation branch."""
        return self.conversation.delete_branch(branch)

    def list_branches(self) -> list[dict]:
        """List all conversation branches."""
        return self.conversation.list_branches()

    # ── Task Execution ───────────────────────────────────────

    async def run_task(self, description: str) -> str:
        """Run an autonomous task."""
        if not self.agents:
            return "Agent system not initialized"
        return await self.agents.execute_task(description)

    def spawn_agent(self, agent_type: str) -> None:
        """Spawn a sub-agent."""
        if self.agents:
            self.agents.spawn(agent_type)

    # ── Status ───────────────────────────────────────────────

    def show_status(self) -> None:
        """Show system status."""
        try:
            from cli.theme import Theme, console
            _has_theme = True
        except ImportError:
            _has_theme = False

        uptime = time.time() - self.start_time
        uptime_str = self._format_uptime(uptime)

        info = {
            "Status": "Running",
            "Model": self.current_model,
            "Branch": self.conversation.current_branch_name,
            "Thinking": "ON" if self.thinking_enabled else "OFF",
            "Messages": str(len(self.conversation.messages)),
            "Uptime": uptime_str,
            "Tools": str(len(self.tools.get_all())) if self.tools else "0",
            "Agents": str(len(self.agents.get_all())) if self.agents else "0",
            "Tokens": str(self.token_counter.total_tokens_used),
            "Queue": f"{self.request_queue.stats()['active']}/{self.request_queue.stats()['max_size']}",
        }

        if self.memory:
            try:
                info["Memory"] = f"{self.memory.count()} entries"
            except Exception:
                pass

        if _has_theme:
            table = Theme.create_table("⚡ Rally Agent Status")
            table.add_column("Property", style="cyan", width=20)
            table.add_column("Value", style="neon_green")
            for k, v in info.items():
                table.add_row(f"📊 {k}", v)
            console.print()
            console.print(table)
            console.print()
        else:
            for k, v in info.items():
                logger.info(f"  {k}: {v}")

    def show_providers(self) -> None:
        """Show provider status."""
        if not self.providers:
            return
        for info in self.providers.get_all_info():
            status = "✅" if info["available"] else "❌"
            health = info.get("health", {}).get("status", "unknown")
            logger.info(f"  {status} {info['name']}: {info['description']} [{health}]")

    def show_branches(self) -> None:
        """Show conversation branches."""
        for b in self.conversation.list_branches():
            current = "→ " if b["is_current"] else "  "
            logger.info(f"{current}{b['name']} ({b['id']}): {b['message_count']} messages")

    # ── Config ───────────────────────────────────────────────

    def show_config(self) -> None:
        """Show configuration."""
        try:
            from cli.theme import Theme, console
            table = Theme.create_table("⚙️ Configuration")
            table.add_column("Key", style="cyan")
            table.add_column("Value", style="neon_green")
            for section, values in self.config.data.items():
                if isinstance(values, dict):
                    for k, v in values.items():
                        # Mask secrets
                        v_str = str(v)
                        if isinstance(v, str) and len(v) > 20 and any(
                            kw in k.lower() for kw in ["key", "token", "secret", "password"]
                        ):
                            v_str = v_str[:4] + "..." + v_str[-4:]
                        table.add_row(f"{section}.{k}", v_str)
                else:
                    table.add_row(section, str(values))
            console.print()
            console.print(table)
            console.print()
        except ImportError:
            for section, values in self.config.data.items():
                if isinstance(values, dict):
                    for k, v in values.items():
                        logger.info(f"  {section}.{k} = {v}")

    def set_config(self, key: str, value: str) -> None:
        """Set a config value."""
        self.config.set(key, value)

    def show_model(self) -> None:
        """Show current model."""
        logger.info(f"Current model: {self.current_model}")

    def set_model(self, model: str) -> None:
        """Switch model."""
        self.current_model = model
        logger.info(f"Switched to model: {model}")

    def toggle_thinking(self) -> None:
        """Toggle thinking mode."""
        self.thinking_enabled = not self.thinking_enabled

    def set_thinking(self, enabled: bool) -> None:
        """Set thinking mode."""
        self.thinking_enabled = enabled

    def toggle_compact(self) -> None:
        """Toggle compact mode."""
        self.compact_mode = not self.compact_mode

    # ── Persistence ──────────────────────────────────────────

    def save_conversation(self, path: str) -> None:
        """Save conversation to file."""
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
        data = {
            "branches": self.conversation.to_dict(),
            "messages": self.conversation.messages,
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    def load_conversation(self, path: str) -> None:
        """Load conversation from file."""
        if os.path.exists(path):
            with open(path) as f:
                data = json.load(f)
            if isinstance(data, list):
                # Legacy format
                self.conversation.messages = data
            elif isinstance(data, dict):
                self.conversation.messages = data.get("messages", [])

    # ── Memory ───────────────────────────────────────────────

    def show_memory_stats(self) -> None:
        if not self.memory:
            return
        try:
            self.memory.show_stats()
        except Exception:
            pass

    def search_memory(self, query: str) -> None:
        if not self.memory:
            return
        try:
            results = self.memory.search(query)
            for r in results:
                logger.info(f"  {r.get('content', '')[:100]}")
        except Exception:
            pass

    def clear_memory(self) -> None:
        if self.memory:
            try:
                self.memory.clear()
            except Exception:
                pass

    def show_tools(self) -> None:
        if not self.tools:
            return
        try:
            tools = self.tools.get_all()
            for t in tools:
                logger.info(f"  {t.get('name', '?')}: {t.get('description', '')}")
        except Exception:
            pass

    def show_agents(self) -> None:
        if not self.agents:
            return
        try:
            agents = self.agents.get_all()
            for a in agents:
                logger.info(f"  {a.get('name', '?')}: {a.get('description', '')}")
        except Exception:
            pass

    # ── Shutdown ─────────────────────────────────────────────

    def shutdown(self) -> None:
        """Graceful shutdown."""
        if self.memory:
            try:
                self.memory.save()
            except Exception:
                pass
        logger.info("Rally Agent shutdown complete")

    # ── Helpers ──────────────────────────────────────────────

    @staticmethod
    def _format_uptime(seconds: float) -> str:
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            return f"{int(seconds // 60)}m {int(seconds % 60)}s"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f"{hours}h {minutes}m"
