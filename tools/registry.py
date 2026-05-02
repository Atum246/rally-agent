"""
🟣 Rally Agent — Tool Registry
Manages all available tools for the agent.
"""

import os
import asyncio
import subprocess
from typing import Optional, Any
from abc import ABC, abstractmethod

from cli.theme import Theme


class BaseTool(ABC):
    """Base class for all tools"""

    name: str = "unknown"
    description: str = ""
    category: str = "general"

    @abstractmethod
    async def execute(self, args: str, **kwargs) -> str:
        pass

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
        }


# ═══════════════════════════════════════════════════════════════
# 🔧 Built-in Tools
# ═══════════════════════════════════════════════════════════════

class FileReadTool(BaseTool):
    name = "read"
    description = "Read file contents"
    category = "files"

    async def execute(self, args: str, **kwargs) -> str:
        path = args.strip()
        if not os.path.exists(path):
            return f"File not found: {path}"
        try:
            with open(path) as f:
                content = f.read()
            return content[:50000]  # Limit output
        except Exception as e:
            return f"Error reading file: {e}"


class FileWriteTool(BaseTool):
    name = "write"
    description = "Write content to a file"
    category = "files"

    async def execute(self, args: str, **kwargs) -> str:
        parts = args.split(maxsplit=1)
        if len(parts) < 2:
            return "Usage: write <path> <content>"
        path = parts[0]
        content = parts[1]
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w") as f:
                f.write(content)
            return f"Written to {path}"
        except Exception as e:
            return f"Error writing file: {e}"


class FileEditTool(BaseTool):
    name = "edit"
    description = "Edit a file (replace text)"
    category = "files"

    async def execute(self, args: str, **kwargs) -> str:
        return "File edit tool — use: edit <path> <old_text> <new_text>"


class FileListTool(BaseTool):
    name = "ls"
    description = "List directory contents"
    category = "files"

    async def execute(self, args: str, **kwargs) -> str:
        path = args.strip() or "."
        try:
            entries = os.listdir(path)
            result = []
            for e in sorted(entries):
                full = os.path.join(path, e)
                if os.path.isdir(full):
                    result.append(f"📁 {e}/")
                else:
                    size = os.path.getsize(full)
                    result.append(f"📄 {e} ({self._format_size(size)})")
            return "\n".join(result) if result else "Empty directory"
        except Exception as e:
            return f"Error: {e}"

    @staticmethod
    def _format_size(size: int) -> str:
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f}{unit}"
            size /= 1024
        return f"{size:.1f}TB"


class ExecTool(BaseTool):
    name = "exec"
    description = "Execute a shell command"
    category = "system"

    BLOCKED = ["rm -rf /", "mkfs", "dd if=", ":(){:|:&};:" ]

    async def execute(self, args: str, **kwargs) -> str:
        # Safety check
        for blocked in self.BLOCKED:
            if blocked in args:
                return f"⛔ Blocked dangerous command: {args}"

        try:
            result = subprocess.run(
                args,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            output = result.stdout + result.stderr
            return output[:10000] if output else "(no output)"
        except subprocess.TimeoutExpired:
            return "Command timed out (30s limit)"
        except Exception as e:
            return f"Error: {e}"


class WebSearchTool(BaseTool):
    name = "search"
    description = "Search the web"
    category = "web"

    async def execute(self, args: str, **kwargs) -> str:
        try:
            import httpx
        except ImportError:
            return "httpx not installed — run: pip install httpx"

        # Use DuckDuckGo instant answers
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    "https://api.duckduckgo.com/",
                    params={"q": args, "format": "json", "no_redirect": "1"},
                )
                data = resp.json()

                results = []
                if data.get("Abstract"):
                    results.append(f"📌 {data['Abstract']}")
                if data.get("RelatedTopics"):
                    for topic in data["RelatedTopics"][:5]:
                        if isinstance(topic, dict) and topic.get("Text"):
                            results.append(f"• {topic['Text'][:200]}")

                return "\n".join(results) if results else f"No results for: {args}"
        except Exception as e:
            return f"Search error: {e}"


class WebFetchTool(BaseTool):
    name = "fetch"
    description = "Fetch a URL and extract content"
    category = "web"

    async def execute(self, args: str, **kwargs) -> str:
        try:
            import httpx
        except ImportError:
            return "httpx not installed"

        url = args.strip()
        if not url.startswith("http"):
            url = "https://" + url

        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                resp = await client.get(url)
                content = resp.text
                # Basic HTML stripping
                import re
                content = re.sub(r"<[^>]+>", " ", content)
                content = re.sub(r"\s+", " ", content).strip()
                return content[:10000]
        except Exception as e:
            return f"Fetch error: {e}"


class PythonExecTool(BaseTool):
    name = "python"
    description = "Execute Python code"
    category = "code"

    async def execute(self, args: str, **kwargs) -> str:
        try:
            import io
            import contextlib

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exec(args, {"__builtins__": __builtins__})
            return output.getvalue()[:10000] or "(no output)"
        except Exception as e:
            return f"Python error: {e}"


class CalculatorTool(BaseTool):
    name = "calc"
    description = "Calculate math expressions"
    category = "utility"

    async def execute(self, args: str, **kwargs) -> str:
        try:
            # Safe math evaluation
            import ast
            import operator

            ops = {
                ast.Add: operator.add,
                ast.Sub: operator.sub,
                ast.Mult: operator.mul,
                ast.Div: operator.truediv,
                ast.Pow: operator.pow,
                ast.Mod: operator.mod,
            }

            def eval_expr(node):
                if isinstance(node, ast.Expression):
                    return eval_expr(node.body)
                elif isinstance(node, ast.Constant):
                    return node.value
                elif isinstance(node, ast.BinOp):
                    return ops[type(node.op)](eval_expr(node.left), eval_expr(node.right))
                elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
                    return -eval_expr(node.operand)
                else:
                    raise ValueError(f"Unsupported operation")

            tree = ast.parse(args.strip(), mode="eval")
            result = eval_expr(tree)
            return str(result)
        except Exception as e:
            return f"Calc error: {e}"


class DateTimeTool(BaseTool):
    name = "datetime"
    description = "Get current date/time"
    category = "utility"

    async def execute(self, args: str, **kwargs) -> str:
        from datetime import datetime
        now = datetime.now()
        return now.strftime("%Y-%m-%d %H:%M:%S %A")


class HashTool(BaseTool):
    name = "hash"
    description = "Generate hash (md5, sha256)"
    category = "utility"

    async def execute(self, args: str, **kwargs) -> str:
        import hashlib
        parts = args.split(maxsplit=1)
        algo = parts[0] if parts else "sha256"
        data = parts[1] if len(parts) > 1 else ""

        if algo == "md5":
            return hashlib.md5(data.encode()).hexdigest()
        elif algo == "sha256":
            return hashlib.sha256(data.encode()).hexdigest()
        elif algo == "sha1":
            return hashlib.sha1(data.encode()).hexdigest()
        else:
            return f"Unknown algo: {algo}. Use md5, sha256, or sha1"


class JSONTool(BaseTool):
    name = "json"
    description = "Parse/format JSON"
    category = "utility"

    async def execute(self, args: str, **kwargs) -> str:
        import json
        try:
            data = json.loads(args)
            return json.dumps(data, indent=2)
        except json.JSONDecodeError:
            return f"Invalid JSON: {args[:100]}"


class RegexTool(BaseTool):
    name = "regex"
    description = "Test regex patterns"
    category = "utility"

    async def execute(self, args: str, **kwargs) -> str:
        import re
        parts = args.split(maxsplit=1)
        if len(parts) < 2:
            return "Usage: regex <pattern> <text>"
        pattern, text = parts
        try:
            matches = re.findall(pattern, text)
            return f"Matches: {matches}" if matches else "No matches"
        except re.error as e:
            return f"Invalid regex: {e}"


class UUIDTool(BaseTool):
    name = "uuid"
    description = "Generate UUID"
    category = "utility"

    async def execute(self, args: str, **kwargs) -> str:
        import uuid
        count = 1
        if args.strip().isdigit():
            count = min(int(args.strip()), 100)
        return "\n".join(str(uuid.uuid4()) for _ in range(count))


class Base64Tool(BaseTool):
    name = "base64"
    description = "Encode/decode base64"
    category = "utility"

    async def execute(self, args: str, **kwargs) -> str:
        import base64
        parts = args.split(maxsplit=1)
        action = parts[0] if parts else "encode"
        data = parts[1] if len(parts) > 1 else ""

        if action == "encode":
            return base64.b64encode(data.encode()).decode()
        elif action == "decode":
            return base64.b64decode(data.encode()).decode()
        else:
            return "Usage: base64 encode|decode <data>"


# ═══════════════════════════════════════════════════════════════
# 🔧 Tool Registry
# ═══════════════════════════════════════════════════════════════

class ToolRegistry:
    """Registry for all available tools"""

    def __init__(self, config):
        self.config = config
        self.tools: dict[str, BaseTool] = {}
        self._register_builtins()

    def _register_builtins(self):
        """Register built-in tools"""
        tools = [
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

        for tool in tools:
            self.tools[tool.name] = tool

    def get(self, name: str) -> Optional[BaseTool]:
        """Get a tool by name"""
        return self.tools.get(name)

    def get_all(self) -> list[dict]:
        """Get all tools as dicts"""
        return [t.to_dict() for t in self.tools.values()]

    def get_names(self) -> list[str]:
        """Get all tool names"""
        return list(self.tools.keys())

    def register(self, tool: BaseTool):
        """Register a custom tool"""
        self.tools[tool.name] = tool

    def unregister(self, name: str):
        """Unregister a tool"""
        self.tools.pop(name, None)

    def get_by_category(self, category: str) -> list[BaseTool]:
        """Get tools by category"""
        return [t for t in self.tools.values() if t.category == category]
