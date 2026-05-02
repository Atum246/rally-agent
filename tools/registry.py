"""
🟣 Rally Agent — Tool Registry
Complete rewrite with function calling schema generation, sandboxing, rate limiting,
permissions, parallel execution, usage tracking, and dynamic plugin registration.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import time
import uuid
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Coroutine, Optional

from cli.theme import Theme


# ═══════════════════════════════════════════════════════════════
# Type Definitions
# ═══════════════════════════════════════════════════════════════

class ToolCategory(str, Enum):
    FILES = "files"
    SYSTEM = "system"
    WEB = "web"
    CODE = "code"
    DATA = "data"
    UTILITY = "utility"
    SECURITY = "security"
    DEVOPS = "devops"
    DATABASE = "database"
    MEDIA = "media"
    AUTOMATION = "automation"
    GENERAL = "general"


class PermissionLevel(str, Enum):
    PUBLIC = "public"        # Anyone can use
    AUTHENTICATED = "auth"   # Requires authenticated user
    PRIVILEGED = "privileged"  # Requires elevated permissions
    ADMIN = "admin"          # Admin only


@dataclass
class ToolParameter:
    """Schema for a single tool parameter."""
    name: str
    type: str  # "string", "integer", "number", "boolean", "array", "object"
    description: str
    required: bool = False
    default: Any = None
    enum: Optional[list[str]] = None
    items: Optional[dict[str, Any]] = None  # For array types
    properties: Optional[dict[str, Any]] = None  # For object types
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    pattern: Optional[str] = None  # Regex pattern for validation

    def to_schema(self) -> dict[str, Any]:
        """Convert to OpenAI function parameter schema."""
        schema: dict[str, Any] = {"type": self.type}
        if self.description:
            schema["description"] = self.description
        if self.enum:
            schema["enum"] = self.enum
        if self.items:
            schema["items"] = self.items
        if self.properties:
            schema["properties"] = self.properties
        return schema


@dataclass
class ToolDefinition:
    """Complete tool definition with schema and metadata."""
    name: str
    description: str
    category: ToolCategory
    parameters: list[ToolParameter] = field(default_factory=list)
    permission: PermissionLevel = PermissionLevel.PUBLIC
    tags: list[str] = field(default_factory=list)
    version: str = "1.0.0"
    author: str = "rally"
    rate_limit_per_minute: int = 60
    timeout_seconds: int = 30
    dangerous: bool = False
    requires_confirmation: bool = False
    examples: list[dict[str, Any]] = field(default_factory=list)

    def to_function_schema(self) -> dict[str, Any]:
        """Generate OpenAI-compatible function calling schema."""
        properties = {}
        required = []

        for param in self.parameters:
            properties[param.name] = param.to_schema()
            if param.default is not None:
                properties[param.name]["default"] = param.default
            if param.required:
                required.append(param.name)

        parameters_schema = {
            "type": "object",
            "properties": properties,
        }
        if required:
            parameters_schema["required"] = required

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": parameters_schema,
            },
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category.value,
            "permission": self.permission.value,
            "parameters": [
                {"name": p.name, "type": p.type, "description": p.description, "required": p.required}
                for p in self.parameters
            ],
            "tags": self.tags,
            "version": self.version,
            "rate_limit_per_minute": self.rate_limit_per_minute,
            "dangerous": self.dangerous,
        }


# ═══════════════════════════════════════════════════════════════
# Usage Tracking
# ═══════════════════════════════════════════════════════════════

@dataclass
class ToolCallRecord:
    """Record of a single tool invocation."""
    tool_name: str
    timestamp: float
    arguments: dict[str, Any]
    success: bool
    execution_time_ms: float
    user_id: Optional[str] = None
    agent_id: Optional[str] = None
    error: Optional[str] = None


class UsageTracker:
    """Tracks tool usage for analytics and debugging."""

    def __init__(self, max_history: int = 10000):
        self._history: list[ToolCallRecord] = []
        self._max_history = max_history
        self._counts: dict[str, int] = defaultdict(int)
        self._errors: dict[str, int] = defaultdict(int)
        self._total_time: dict[str, float] = defaultdict(float)

    def record(self, record: ToolCallRecord):
        """Record a tool call."""
        self._history.append(record)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        self._counts[record.tool_name] += 1
        if not record.success:
            self._errors[record.tool_name] += 1
        self._total_time[record.tool_name] += record.execution_time_ms

    def get_stats(self, tool_name: Optional[str] = None) -> dict[str, Any]:
        """Get usage statistics."""
        if tool_name:
            count = self._counts.get(tool_name, 0)
            errors = self._errors.get(tool_name, 0)
            total_time = self._total_time.get(tool_name, 0)
            return {
                "tool": tool_name,
                "total_calls": count,
                "errors": errors,
                "error_rate": errors / count if count > 0 else 0,
                "avg_time_ms": total_time / count if count > 0 else 0,
                "total_time_ms": total_time,
            }

        return {
            "total_calls": sum(self._counts.values()),
            "total_errors": sum(self._errors.values()),
            "tools": {
                name: self.get_stats(name)
                for name in self._counts
            },
        }

    def get_recent(self, limit: int = 20) -> list[dict[str, Any]]:
        """Get recent tool calls."""
        return [
            {
                "tool": r.tool_name,
                "timestamp": r.timestamp,
                "success": r.success,
                "time_ms": r.execution_time_ms,
                "user": r.user_id,
            }
            for r in self._history[-limit:]
        ]


# ═══════════════════════════════════════════════════════════════
# Rate Limiting
# ═══════════════════════════════════════════════════════════════

class RateLimiter:
    """Per-tool rate limiter using sliding window."""

    def __init__(self):
        self._windows: dict[str, list[float]] = defaultdict(list)

    def check(self, tool_name: str, limit_per_minute: int, user_id: Optional[str] = None) -> bool:
        """Check if a call is allowed under the rate limit."""
        key = f"{tool_name}:{user_id}" if user_id else tool_name
        now = time.time()
        window = self._windows[key]

        # Remove entries older than 60 seconds
        cutoff = now - 60
        self._windows[key] = [t for t in window if t > cutoff]

        if len(self._windows[key]) >= limit_per_minute:
            return False

        self._windows[key].append(now)
        return True

    def get_remaining(self, tool_name: str, limit_per_minute: int, user_id: Optional[str] = None) -> int:
        """Get remaining calls in the current window."""
        key = f"{tool_name}:{user_id}" if user_id else tool_name
        now = time.time()
        window = self._windows.get(key, [])
        recent = [t for t in window if t > now - 60]
        return max(0, limit_per_minute - len(recent))


# ═══════════════════════════════════════════════════════════════
# Permission System
# ═══════════════════════════════════════════════════════════════

class PermissionManager:
    """Manages tool access permissions per user/agent."""

    def __init__(self):
        self._user_permissions: dict[str, set[str]] = defaultdict(set)
        self._agent_permissions: dict[str, set[str]] = defaultdict(set)
        self._user_level: dict[str, PermissionLevel] = {}

    def set_user_level(self, user_id: str, level: PermissionLevel):
        self._user_level[user_id] = level

    def grant_user_tool(self, user_id: str, tool_name: str):
        self._user_permissions[user_id].add(tool_name)

    def grant_agent_tool(self, agent_id: str, tool_name: str):
        self._agent_permissions[agent_id].add(tool_name)

    def check_permission(
        self,
        tool_def: ToolDefinition,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> tuple[bool, str]:
        """Check if a user/agent has permission to use a tool."""
        # Public tools are always allowed
        if tool_def.permission == PermissionLevel.PUBLIC:
            return True, "Allowed"

        # Agent check
        if agent_id:
            if tool_def.name in self._agent_permissions.get(agent_id, set()):
                return True, "Allowed (agent grant)"
            # Agents inherit their tool permissions from registration

        # User check
        if user_id:
            user_level = self._user_level.get(user_id, PermissionLevel.PUBLIC)

            # Level hierarchy: admin > privileged > auth > public
            level_order = {
                PermissionLevel.PUBLIC: 0,
                PermissionLevel.AUTHENTICATED: 1,
                PermissionLevel.PRIVILEGED: 2,
                PermissionLevel.ADMIN: 3,
            }

            if level_order.get(user_level, 0) >= level_order.get(tool_def.permission, 0):
                return True, "Allowed (level)"

            # Check explicit user grant
            if tool_def.name in self._user_permissions.get(user_id, set()):
                return True, "Allowed (explicit grant)"

        return False, f"Permission denied: requires {tool_def.permission.value}"


# ═══════════════════════════════════════════════════════════════
# Base Tool
# ═══════════════════════════════════════════════════════════════

class BaseTool(ABC):
    """Base class for all Rally tools. Subclasses define schema + execute logic."""

    @abstractmethod
    def definition(self) -> ToolDefinition:
        """Return the tool definition with schema."""
        ...

    @abstractmethod
    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> Any:
        """
        Execute the tool with validated arguments.

        Args:
            arguments: Validated, typed arguments matching the tool schema.
            context: Optional execution context (user_id, agent_id, etc).

        Returns:
            Tool result (will be serialized to string).
        """
        ...

    def validate_arguments(self, arguments: dict[str, Any]) -> tuple[bool, str, dict[str, Any]]:
        """
        Validate arguments against the tool definition.
        Returns (valid, error_message, sanitized_args).
        """
        defn = self.definition()
        sanitized = {}
        errors = []

        # Check required parameters
        for param in defn.parameters:
            if param.required and param.name not in arguments:
                errors.append(f"Missing required parameter: {param.name}")
                continue

            value = arguments.get(param.name, param.default)
            if value is None:
                continue

            # Type validation
            valid, msg = self._validate_type(param, value)
            if not valid:
                errors.append(f"Parameter '{param.name}': {msg}")
                continue

            sanitized[param.name] = value

        if errors:
            return False, "; ".join(errors), {}

        return True, "", sanitized

    @staticmethod
    def _validate_type(param: ToolParameter, value: Any) -> tuple[bool, str]:
        """Validate a single parameter type."""
        type_checks = {
            "string": lambda v: isinstance(v, str),
            "integer": lambda v: isinstance(v, int),
            "number": lambda v: isinstance(v, (int, float)),
            "boolean": lambda v: isinstance(v, bool),
            "array": lambda v: isinstance(v, list),
            "object": lambda v: isinstance(v, dict),
        }

        check = type_checks.get(param.type)
        if check and not check(value):
            return False, f"Expected {param.type}, got {type(value).__name__}"

        # Enum check
        if param.enum and value not in param.enum:
            return False, f"Value must be one of: {param.enum}"

        # Range check
        if param.min_value is not None and isinstance(value, (int, float)):
            if value < param.min_value:
                return False, f"Value must be >= {param.min_value}"
        if param.max_value is not None and isinstance(value, (int, float)):
            if value > param.max_value:
                return False, f"Value must be <= {param.max_value}"

        return True, ""


# ═══════════════════════════════════════════════════════════════
# Built-in Tools (function calling compatible)
# ═══════════════════════════════════════════════════════════════

class FileReadTool(BaseTool):
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="read_file",
            description="Read the contents of a file at the given path.",
            category=ToolCategory.FILES,
            parameters=[
                ToolParameter("path", "string", "Absolute or relative file path", required=True),
                ToolParameter("offset", "integer", "Line number to start from (1-indexed)"),
                ToolParameter("limit", "integer", "Maximum number of lines to read"),
            ],
            tags=["file", "read", "io"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        path = arguments["path"]
        offset = arguments.get("offset", 1)
        limit = arguments.get("limit", 5000)

        if not os.path.exists(path):
            return json.dumps({"error": f"File not found: {path}"})
        try:
            with open(path, "r", errors="replace") as f:
                lines = f.readlines()
            selected = lines[offset - 1 : offset - 1 + limit]
            return json.dumps({
                "path": path,
                "total_lines": len(lines),
                "returned_lines": len(selected),
                "content": "".join(selected),
            })
        except Exception as e:
            return json.dumps({"error": str(e)})


class FileWriteTool(BaseTool):
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="write_file",
            description="Write content to a file. Creates parent directories if needed.",
            category=ToolCategory.FILES,
            parameters=[
                ToolParameter("path", "string", "File path to write to", required=True),
                ToolParameter("content", "string", "Content to write", required=True),
                ToolParameter("append", "boolean", "Append to file instead of overwriting"),
            ],
            tags=["file", "write", "io"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        path = arguments["path"]
        content = arguments["content"]
        append = arguments.get("append", False)

        try:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            mode = "a" if append else "w"
            with open(path, mode) as f:
                f.write(content)
            return json.dumps({"success": True, "path": path, "bytes_written": len(content)})
        except Exception as e:
            return json.dumps({"error": str(e)})


class FileEditTool(BaseTool):
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="edit_file",
            description="Edit a file by replacing exact text. The old_text must match exactly.",
            category=ToolCategory.FILES,
            parameters=[
                ToolParameter("path", "string", "File path to edit", required=True),
                ToolParameter("old_text", "string", "Exact text to find and replace", required=True),
                ToolParameter("new_text", "string", "New text to insert", required=True),
            ],
            tags=["file", "edit", "io"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        path = arguments["path"]
        old_text = arguments["old_text"]
        new_text = arguments["new_text"]

        if not os.path.exists(path):
            return json.dumps({"error": f"File not found: {path}"})
        try:
            with open(path, "r") as f:
                content = f.read()
            if old_text not in content:
                return json.dumps({"error": "old_text not found in file", "path": path})
            count = content.count(old_text)
            new_content = content.replace(old_text, new_text, 1)
            with open(path, "w") as f:
                f.write(new_content)
            return json.dumps({"success": True, "path": path, "occurrences_replaced": 1, "total_occurrences": count})
        except Exception as e:
            return json.dumps({"error": str(e)})


class FileListTool(BaseTool):
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="list_directory",
            description="List contents of a directory with file sizes and types.",
            category=ToolCategory.FILES,
            parameters=[
                ToolParameter("path", "string", "Directory path (defaults to current dir)"),
                ToolParameter("show_hidden", "boolean", "Include hidden files"),
                ToolParameter("pattern", "string", "Glob pattern to filter (e.g. '*.py')"),
            ],
            tags=["file", "ls", "directory"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        path = arguments.get("path", ".")
        show_hidden = arguments.get("show_hidden", False)
        pattern = arguments.get("pattern")

        try:
            entries = []
            for name in sorted(os.listdir(path)):
                if not show_hidden and name.startswith("."):
                    continue
                if pattern:
                    import fnmatch
                    if not fnmatch.fnmatch(name, pattern):
                        continue
                full = os.path.join(path, name)
                entry = {"name": name, "type": "directory" if os.path.isdir(full) else "file"}
                if entry["type"] == "file":
                    entry["size"] = os.path.getsize(full)
                entries.append(entry)
            return json.dumps({"path": path, "count": len(entries), "entries": entries})
        except Exception as e:
            return json.dumps({"error": str(e)})


class ExecTool(BaseTool):
    BLOCKED = ["rm -rf /", "mkfs", "dd if=", ":(){:|:&};:", "> /dev/sda"]

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="exec",
            description="Execute a shell command and return its output.",
            category=ToolCategory.SYSTEM,
            parameters=[
                ToolParameter("command", "string", "Shell command to execute", required=True),
                ToolParameter("timeout", "integer", "Timeout in seconds (default 30)"),
                ToolParameter("working_directory", "string", "Working directory"),
            ],
            permission=PermissionLevel.AUTHENTICATED,
            dangerous=True,
            rate_limit_per_minute=30,
            tags=["shell", "exec", "system"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        command = arguments["command"]
        timeout = arguments.get("timeout", 30)
        cwd = arguments.get("working_directory")

        for blocked in self.BLOCKED:
            if blocked in command:
                return json.dumps({"error": f"Blocked dangerous command: {command}"})

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                proc.kill()
                return json.dumps({"error": f"Command timed out ({timeout}s)"})

            return json.dumps({
                "exit_code": proc.returncode,
                "stdout": stdout.decode("utf-8", errors="replace")[:50000],
                "stderr": stderr.decode("utf-8", errors="replace")[:10000],
            })
        except Exception as e:
            return json.dumps({"error": str(e)})


class WebSearchTool(BaseTool):
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="web_search",
            description="Search the web using DuckDuckGo and return results.",
            category=ToolCategory.WEB,
            parameters=[
                ToolParameter("query", "string", "Search query", required=True),
                ToolParameter("num_results", "integer", "Number of results (1-10)"),
            ],
            rate_limit_per_minute=20,
            tags=["search", "web", "internet"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        query = arguments["query"]
        num = min(arguments.get("num_results", 5), 10)

        try:
            import httpx
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    "https://api.duckduckgo.com/",
                    params={"q": query, "format": "json", "no_redirect": "1", "no_html": "1"},
                )
                data = resp.json()
                results = []

                if data.get("Abstract"):
                    results.append({
                        "title": data.get("Heading", "Result"),
                        "snippet": data["Abstract"],
                        "url": data.get("AbstractURL", ""),
                    })

                for topic in data.get("RelatedTopics", [])[:num]:
                    if isinstance(topic, dict) and topic.get("Text"):
                        results.append({
                            "title": topic.get("Text", "")[:100],
                            "snippet": topic.get("Text", ""),
                            "url": topic.get("FirstURL", ""),
                        })

                return json.dumps({"query": query, "results": results[:num]})
        except Exception as e:
            return json.dumps({"error": str(e)})


class WebFetchTool(BaseTool):
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="web_fetch",
            description="Fetch a URL and extract readable text content.",
            category=ToolCategory.WEB,
            parameters=[
                ToolParameter("url", "string", "URL to fetch", required=True),
                ToolParameter("max_chars", "integer", "Maximum characters to return"),
            ],
            rate_limit_per_minute=30,
            tags=["fetch", "web", "scrape"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        import re
        url = arguments["url"]
        max_chars = arguments.get("max_chars", 10000)

        if not url.startswith("http"):
            url = "https://" + url

        try:
            import httpx
            headers = {"User-Agent": "Mozilla/5.0 (compatible; RallyAgent/1.0)"}
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                resp = await client.get(url, headers=headers)
                content = resp.text

                # Strip scripts/styles, then tags
                content = re.sub(r"<script[^>]*>.*?</script>", "", content, flags=re.DOTALL)
                content = re.sub(r"<style[^>]*>.*?</style>", "", content, flags=re.DOTALL)
                content = re.sub(r"<[^>]+>", " ", content)
                content = re.sub(r"\s+", " ", content).strip()

                return json.dumps({
                    "url": str(resp.url),
                    "status": resp.status_code,
                    "content": content[:max_chars],
                    "truncated": len(content) > max_chars,
                })
        except Exception as e:
            return json.dumps({"error": str(e)})


class PythonExecTool(BaseTool):
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="python_exec",
            description="Execute Python code in a sandboxed environment and return output.",
            category=ToolCategory.CODE,
            parameters=[
                ToolParameter("code", "string", "Python code to execute", required=True),
                ToolParameter("timeout", "integer", "Timeout in seconds"),
            ],
            permission=PermissionLevel.AUTHENTICATED,
            rate_limit_per_minute=20,
            tags=["python", "code", "execute"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        from tools.exec_sandbox import ExecutionSandbox, ResourceLimits

        code = arguments["code"]
        timeout = arguments.get("timeout", 30)

        sandbox = ExecutionSandbox(limits=ResourceLimits(timeout_seconds=timeout))
        result = await sandbox.execute(code, language="python")

        return json.dumps({
            "success": result.success,
            "exit_code": result.exit_code,
            "stdout": result.stdout[:10000],
            "stderr": result.stderr[:5000],
            "execution_time_ms": result.execution_time_ms,
        })


class CalculatorTool(BaseTool):
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="calculator",
            description="Evaluate a mathematical expression safely.",
            category=ToolCategory.UTILITY,
            parameters=[
                ToolParameter("expression", "string", "Math expression to evaluate (e.g. '2 + 3 * 4')", required=True),
            ],
            tags=["math", "calc", "calculate"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        import ast
        import operator

        expr = arguments["expression"]
        ops = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.Mult: operator.mul,
            ast.Div: operator.truediv,
            ast.Pow: operator.pow,
            ast.Mod: operator.mod,
            ast.FloorDiv: operator.floordiv,
        }

        def eval_node(node):
            if isinstance(node, ast.Expression):
                return eval_node(node.body)
            elif isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
                return node.value
            elif isinstance(node, ast.BinOp):
                return ops[type(node.op)](eval_node(node.left), eval_node(node.right))
            elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
                return -eval_node(node.operand)
            else:
                raise ValueError(f"Unsupported expression element: {type(node).__name__}")

        try:
            tree = ast.parse(expr, mode="eval")
            result = eval_node(tree)
            return json.dumps({"expression": expr, "result": result})
        except Exception as e:
            return json.dumps({"error": str(e)})


class DateTimeTool(BaseTool):
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="datetime",
            description="Get current date/time or parse/format dates.",
            category=ToolCategory.UTILITY,
            parameters=[
                ToolParameter("action", "string", "Action: 'now', 'format', 'parse', 'diff'", enum=["now", "format", "parse", "diff"]),
                ToolParameter("value", "string", "Date string or format pattern"),
                ToolParameter("value2", "string", "Second date for diff operation"),
            ],
            tags=["date", "time", "datetime"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        action = arguments.get("action", "now")
        value = arguments.get("value", "")
        value2 = arguments.get("value2", "")

        now = datetime.now()
        try:
            if action == "now":
                return json.dumps({"datetime": now.isoformat(), "formatted": now.strftime("%Y-%m-%d %H:%M:%S %A")})
            elif action == "format":
                fmt = value or "%Y-%m-%d %H:%M:%S"
                return json.dumps({"formatted": now.strftime(fmt)})
            elif action == "parse":
                dt = datetime.fromisoformat(value)
                return json.dumps({"parsed": dt.isoformat()})
            elif action == "diff":
                d1 = datetime.fromisoformat(value)
                d2 = datetime.fromisoformat(value2) if value2 else now
                delta = d2 - d1
                return json.dumps({"days": delta.days, "seconds": delta.seconds, "total_seconds": delta.total_seconds()})
            else:
                return json.dumps({"error": f"Unknown action: {action}"})
        except Exception as e:
            return json.dumps({"error": str(e)})


class HashTool(BaseTool):
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="hash",
            description="Generate a hash of the given data.",
            category=ToolCategory.SECURITY,
            parameters=[
                ToolParameter("data", "string", "Data to hash", required=True),
                ToolParameter("algorithm", "string", "Hash algorithm", enum=["md5", "sha1", "sha256", "sha512"]),
            ],
            tags=["hash", "crypto", "digest"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        import hashlib
        data = arguments["data"]
        algo = arguments.get("algorithm", "sha256")

        try:
            h = hashlib.new(algo)
            h.update(data.encode("utf-8"))
            return json.dumps({"algorithm": algo, "hex_digest": h.hexdigest()})
        except Exception as e:
            return json.dumps({"error": str(e)})


class JSONTool(BaseTool):
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="json_op",
            description="Parse, format, or validate JSON data.",
            category=ToolCategory.UTILITY,
            parameters=[
                ToolParameter("action", "string", "Action: 'parse', 'format', 'validate'", enum=["parse", "format", "validate"]),
                ToolParameter("data", "string", "JSON string to process", required=True),
                ToolParameter("indent", "integer", "Indentation level for formatting"),
            ],
            tags=["json", "parse", "format"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        action = arguments.get("action", "parse")
        data = arguments["data"]
        indent = arguments.get("indent", 2)

        try:
            parsed = json.loads(data)
            if action == "validate":
                return json.dumps({"valid": True})
            return json.dumps({"formatted": json.dumps(parsed, indent=indent)}, ensure_ascii=False)
        except json.JSONDecodeError as e:
            return json.dumps({"valid": False, "error": str(e)})


class RegexTool(BaseTool):
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="regex",
            description="Test a regex pattern against text.",
            category=ToolCategory.UTILITY,
            parameters=[
                ToolParameter("pattern", "string", "Regex pattern", required=True),
                ToolParameter("text", "string", "Text to match against", required=True),
                ToolParameter("action", "string", "Action: 'match', 'findall', 'replace', 'test'", enum=["match", "findall", "replace", "test"]),
                ToolParameter("replacement", "string", "Replacement string for 'replace' action"),
            ],
            tags=["regex", "pattern", "match"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        import re
        pattern = arguments["pattern"]
        text = arguments["text"]
        action = arguments.get("action", "findall")
        replacement = arguments.get("replacement", "")

        try:
            if action == "test":
                match = re.search(pattern, text)
                return json.dumps({"matches": bool(match), "span": match.span() if match else None})
            elif action == "match":
                match = re.search(pattern, text)
                if match:
                    return json.dumps({"match": match.group(), "groups": list(match.groups()), "span": match.span()})
                return json.dumps({"match": None})
            elif action == "findall":
                matches = re.findall(pattern, text)
                return json.dumps({"matches": matches, "count": len(matches)})
            elif action == "replace":
                result = re.sub(pattern, replacement, text)
                return json.dumps({"result": result})
            else:
                return json.dumps({"error": f"Unknown action: {action}"})
        except re.error as e:
            return json.dumps({"error": f"Invalid regex: {e}"})


class UUIDTool(BaseTool):
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="uuid_generate",
            description="Generate one or more UUIDs.",
            category=ToolCategory.UTILITY,
            parameters=[
                ToolParameter("count", "integer", "Number of UUIDs to generate (1-100)"),
                ToolParameter("version", "integer", "UUID version (4 default)", enum=["4"]),
            ],
            tags=["uuid", "generate", "random"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        count = min(arguments.get("count", 1), 100)
        uuids = [str(uuid.uuid4()) for _ in range(count)]
        return json.dumps({"uuids": uuids, "count": len(uuids)})


class Base64Tool(BaseTool):
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="base64",
            description="Encode or decode base64 data.",
            category=ToolCategory.UTILITY,
            parameters=[
                ToolParameter("action", "string", "Encode or decode", enum=["encode", "decode"], required=True),
                ToolParameter("data", "string", "Data to encode/decode", required=True),
            ],
            tags=["base64", "encode", "decode"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        import base64 as b64
        action = arguments["action"]
        data = arguments["data"]

        try:
            if action == "encode":
                result = b64.b64encode(data.encode()).decode()
            else:
                result = b64.b64decode(data.encode()).decode()
            return json.dumps({"action": action, "result": result})
        except Exception as e:
            return json.dumps({"error": str(e)})


# ═══════════════════════════════════════════════════════════════
# Tool Registry — Central Hub
# ═══════════════════════════════════════════════════════════════

class ToolRegistry:
    """
    Central registry for all tools.
    Manages registration, lookup, schema generation, execution, rate limiting, permissions, and tracking.
    """

    def __init__(self, config: Any = None):
        self.config = config
        self._tools: dict[str, BaseTool] = {}
        self._definitions: dict[str, ToolDefinition] = {}
        self._categories: dict[ToolCategory, list[str]] = defaultdict(list)

        # Subsystems
        self.usage = UsageTracker()
        self.rate_limiter = RateLimiter()
        self.permissions = PermissionManager()

        # Register built-in tools
        self._register_builtins()

    def _register_builtins(self):
        """Register all built-in tools."""
        builtins = [
            FileReadTool(),
            FileWriteTool(),
            FileEditTool(),
            FileListTool(),
            ExecTool(),
            WebSearchTool(),
            WebFetchTool(),
            PythonExecTool(),
            CalculatorTool(),
            DateTimeTool(),
            HashTool(),
            JSONTool(),
            RegexTool(),
            UUIDTool(),
            Base64Tool(),
        ]
        for tool in builtins:
            self.register(tool)

    # ── Registration ──────────────────────────────────────────

    def register(self, tool: BaseTool) -> ToolDefinition:
        """Register a tool and return its definition."""
        defn = tool.definition()
        self._tools[defn.name] = tool
        self._definitions[defn.name] = defn
        self._categories[defn.category].append(defn.name)
        return defn

    def unregister(self, name: str):
        """Unregister a tool."""
        defn = self._definitions.pop(name, None)
        self._tools.pop(name, None)
        if defn and name in self._categories.get(defn.category, []):
            self._categories[defn.category].remove(name)

    def register_function(
        self,
        name: str,
        description: str,
        func: Callable[..., Coroutine[Any, Any, str]],
        category: ToolCategory = ToolCategory.GENERAL,
        parameters: Optional[list[ToolParameter]] = None,
        permission: PermissionLevel = PermissionLevel.PUBLIC,
        **kwargs,
    ) -> ToolDefinition:
        """Register a plain async function as a tool (plugin convenience)."""

        class FunctionTool(BaseTool):
            def definition(self_inner) -> ToolDefinition:
                return ToolDefinition(
                    name=name,
                    description=description,
                    category=category,
                    parameters=parameters or [],
                    permission=permission,
                    **kwargs,
                )

            async def execute(self_inner, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
                return await func(**arguments)

        return self.register(FunctionTool())

    # ── Lookup ────────────────────────────────────────────────

    def get(self, name: str) -> Optional[BaseTool]:
        return self._tools.get(name)

    def get_definition(self, name: str) -> Optional[ToolDefinition]:
        return self._definitions.get(name)

    def get_all_definitions(self) -> list[ToolDefinition]:
        return list(self._definitions.values())

    def get_names(self) -> list[str]:
        return list(self._tools.keys())

    def get_by_category(self, category: ToolCategory) -> list[ToolDefinition]:
        return [self._definitions[n] for n in self._categories.get(category, []) if n in self._definitions]

    def get_categories(self) -> list[str]:
        return list(set(cat.value for cat in self._categories if self._categories[cat]))

    # ── Schema Generation ─────────────────────────────────────

    def get_function_schemas(self, filter_tags: Optional[list[str]] = None) -> list[dict[str, Any]]:
        """
        Get OpenAI-compatible function calling schemas for all registered tools.
        Optionally filter by tags.
        """
        schemas = []
        for defn in self._definitions.values():
            if filter_tags and not any(t in defn.tags for t in filter_tags):
                continue
            schemas.append(defn.to_function_schema())
        return schemas

    def get_schema_for_tools(self, tool_names: list[str]) -> list[dict[str, Any]]:
        """Get schemas for specific tools by name."""
        return [
            self._definitions[name].to_function_schema()
            for name in tool_names
            if name in self._definitions
        ]

    # ── Execution ─────────────────────────────────────────────

    async def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        skip_rate_limit: bool = False,
        skip_permission_check: bool = False,
    ) -> dict[str, Any]:
        """
        Execute a tool by name with full validation, permission check, rate limiting, and tracking.

        Returns:
            dict with 'success', 'result', 'error', 'execution_time_ms', 'tool'.
        """
        start_time = time.monotonic()

        # 1. Look up tool
        tool = self._tools.get(tool_name)
        if not tool:
            return {
                "success": False,
                "error": f"Unknown tool: {tool_name}",
                "available": list(self._tools.keys()),
            }

        defn = self._definitions[tool_name]

        # 2. Permission check
        if not skip_permission_check:
            allowed, reason = self.permissions.check_permission(defn, user_id=user_id, agent_id=agent_id)
            if not allowed:
                return {"success": False, "error": reason, "tool": tool_name}

        # 3. Rate limit check
        if not skip_rate_limit:
            if not self.rate_limiter.check(tool_name, defn.rate_limit_per_minute, user_id=user_id):
                remaining = self.rate_limiter.get_remaining(tool_name, defn.rate_limit_per_minute, user_id)
                return {
                    "success": False,
                    "error": f"Rate limit exceeded for {tool_name}. {remaining} calls remaining.",
                    "tool": tool_name,
                }

        # 4. Validate arguments
        valid, error, sanitized_args = tool.validate_arguments(arguments)
        if not valid:
            return {"success": False, "error": error, "tool": tool_name}

        # 5. Execute with timeout
        context = {"user_id": user_id, "agent_id": agent_id}
        try:
            result = await asyncio.wait_for(
                tool.execute(sanitized_args, context=context),
                timeout=defn.timeout_seconds,
            )
            elapsed = (time.monotonic() - start_time) * 1000

            # 6. Record usage
            self.usage.record(ToolCallRecord(
                tool_name=tool_name,
                timestamp=time.time(),
                arguments=arguments,
                success=True,
                execution_time_ms=elapsed,
                user_id=user_id,
                agent_id=agent_id,
            ))

            return {
                "success": True,
                "result": result,
                "tool": tool_name,
                "execution_time_ms": elapsed,
            }

        except asyncio.TimeoutError:
            elapsed = (time.monotonic() - start_time) * 1000
            self.usage.record(ToolCallRecord(
                tool_name=tool_name,
                timestamp=time.time(),
                arguments=arguments,
                success=False,
                execution_time_ms=elapsed,
                user_id=user_id,
                agent_id=agent_id,
                error="Timeout",
            ))
            return {"success": False, "error": f"Tool timed out ({defn.timeout_seconds}s)", "tool": tool_name}

        except Exception as e:
            elapsed = (time.monotonic() - start_time) * 1000
            self.usage.record(ToolCallRecord(
                tool_name=tool_name,
                timestamp=time.time(),
                arguments=arguments,
                success=False,
                execution_time_ms=elapsed,
                user_id=user_id,
                agent_id=agent_id,
                error=str(e),
            ))
            return {"success": False, "error": str(e), "tool": tool_name}

    # ── Parallel Execution ────────────────────────────────────

    async def execute_parallel(
        self,
        calls: list[dict[str, Any]],
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        max_concurrency: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Execute multiple tools in parallel.

        Args:
            calls: List of {"tool": "name", "arguments": {...}} dicts.
            user_id: User context.
            agent_id: Agent context.
            max_concurrency: Max parallel executions.

        Returns:
            List of results in the same order as calls.
        """
        semaphore = asyncio.Semaphore(max_concurrency)

        async def _run(idx: int, call: dict) -> tuple[int, dict]:
            async with semaphore:
                result = await self.execute(
                    tool_name=call["tool"],
                    arguments=call.get("arguments", {}),
                    user_id=user_id,
                    agent_id=agent_id,
                )
                return idx, result

        tasks = [_run(i, call) for i, call in enumerate(calls)]
        results_with_idx = await asyncio.gather(*tasks, return_exceptions=True)

        # Sort by original index
        sorted_results: list[dict[str, Any]] = [None] * len(calls)  # type: ignore
        for item in results_with_idx:
            if isinstance(item, Exception):
                continue
            idx, result = item
            sorted_results[idx] = result

        # Fill in any None results from exceptions
        for i, r in enumerate(sorted_results):
            if r is None:
                sorted_results[i] = {"success": False, "error": "Execution failed"}

        return sorted_results

    # ── Plugin Registration ───────────────────────────────────

    def load_plugin(self, plugin_path: str) -> int:
        """
        Load a plugin file and register its tools.
        Plugin must export a list of BaseTool instances as `tools` or a `register(registry)` function.
        """
        import importlib.util

        if not os.path.exists(plugin_path):
            raise FileNotFoundError(f"Plugin not found: {plugin_path}")

        spec = importlib.util.spec_from_file_location("plugin", plugin_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        count = 0

        # Method 1: module exports `tools` list
        if hasattr(module, "tools"):
            for tool in module.tools:
                if isinstance(tool, BaseTool):
                    self.register(tool)
                    count += 1

        # Method 2: module exports `register(registry)` function
        if hasattr(module, "register"):
            module.register(self)
            count += 1

        return count

    def load_plugins_from_directory(self, directory: str) -> int:
        """Load all plugin .py files from a directory."""
        total = 0
        if not os.path.isdir(directory):
            return 0
        for fname in sorted(os.listdir(directory)):
            if fname.endswith(".py") and not fname.startswith("_"):
                try:
                    total += self.load_plugin(os.path.join(directory, fname))
                except Exception as e:
                    Theme.warning(f"Failed to load plugin {fname}: {e}")
        return total

    # ── Analytics ─────────────────────────────────────────────

    def get_usage_stats(self, tool_name: Optional[str] = None) -> dict[str, Any]:
        return self.usage.get_stats(tool_name)

    def get_recent_calls(self, limit: int = 20) -> list[dict[str, Any]]:
        return self.usage.get_recent(limit)

    # ── Summary ───────────────────────────────────────────────

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of the registry state."""
        return {
            "total_tools": len(self._tools),
            "categories": {cat.value: len(tools) for cat, tools in self._categories.items() if tools},
            "tools": [
                {"name": d.name, "category": d.category.value, "permission": d.permission.value}
                for d in self._definitions.values()
            ],
            "usage": self.usage.get_stats(),
        }

    def to_dict(self) -> list[dict[str, Any]]:
        """Get all tools as dicts (backward compatible)."""
        return [d.to_dict() for d in self._definitions.values()]
