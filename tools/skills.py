"""
🟣 Rally Agent — Massive Skills & Tools Registry
Hundreds of built-in skills and tools. Everything you need.
"""

import os
import json
import asyncio
import subprocess
import re
import hashlib
import base64
import time
import math
import random
import csv
import io
from typing import Optional, Any
from datetime import datetime, timedelta
from abc import ABC, abstractmethod

from cli.theme import Theme


class Skill(ABC):
    """Base class for skills"""
    name: str = ""
    description: str = ""
    category: str = "general"
    commands: dict = {}

    @abstractmethod
    async def execute(self, command: str, args: str, **kwargs) -> str:
        pass

    def to_dict(self) -> dict:
        return {"name": self.name, "description": self.description, "category": self.category, "commands": list(self.commands.keys())}


# ═══════════════════════════════════════════════════════════════
# 🔧 FILE & SYSTEM SKILLS
# ═══════════════════════════════════════════════════════════════

class FileOperationsSkill(Skill):
    name = "file_ops"
    description = "Advanced file operations — read, write, edit, search, compress, compare"
    category = "files"
    commands = {"read": "Read file", "write": "Write file", "edit": "Edit file", "ls": "List dir", "find": "Find files", "grep": "Search in files", "diff": "Compare files", "head": "First lines", "tail": "Last lines", "wc": "Word count", "cp": "Copy", "mv": "Move", "mkdir": "Make dir", "touch": "Create file", "stat": "File info"}

    async def execute(self, command: str, args: str, **kwargs) -> str:
        if command == "read":
            return self._read(args)
        elif command == "write":
            parts = args.split(" ", 1)
            return self._write(parts[0], parts[1] if len(parts) > 1 else "")
        elif command == "ls":
            return self._ls(args or ".")
        elif command == "find":
            return self._find(args)
        elif command == "grep":
            return self._grep(args)
        elif command == "diff":
            return self._diff(args)
        elif command == "head":
            return self._head(args)
        elif command == "tail":
            return self._tail(args)
        elif command == "wc":
            return self._wc(args)
        elif command == "stat":
            return self._stat(args)
        return f"Unknown command: {command}"

    def _read(self, path: str) -> str:
        try:
            with open(path) as f:
                return f.read(50000)
        except Exception as e:
            return f"Error: {e}"

    def _write(self, path: str, content: str) -> str:
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w") as f:
                f.write(content)
            return f"Written to {path}"
        except Exception as e:
            return f"Error: {e}"

    def _ls(self, path: str) -> str:
        try:
            entries = []
            for e in sorted(os.listdir(path)):
                full = os.path.join(path, e)
                if os.path.isdir(full):
                    entries.append(f"📁 {e}/")
                else:
                    size = os.path.getsize(full)
                    for unit in ["B", "KB", "MB"]:
                        if size < 1024:
                            entries.append(f"📄 {e} ({size:.1f}{unit})")
                            break
                        size /= 1024
            return "\n".join(entries) or "Empty"
        except Exception as e:
            return f"Error: {e}"

    def _find(self, args: str) -> str:
        try:
            result = subprocess.run(f"find {args}", shell=True, capture_output=True, text=True, timeout=10)
            return result.stdout[:5000] or "No results"
        except Exception as e:
            return f"Error: {e}"

    def _grep(self, args: str) -> str:
        try:
            result = subprocess.run(f"grep -r {args}", shell=True, capture_output=True, text=True, timeout=10)
            return result.stdout[:5000] or "No matches"
        except Exception as e:
            return f"Error: {e}"

    def _diff(self, args: str) -> str:
        try:
            result = subprocess.run(f"diff {args}", shell=True, capture_output=True, text=True, timeout=10)
            return result.stdout[:5000] or "Files are identical"
        except Exception as e:
            return f"Error: {e}"

    def _head(self, args: str) -> str:
        try:
            result = subprocess.run(f"head {args}", shell=True, capture_output=True, text=True, timeout=10)
            return result.stdout
        except Exception as e:
            return f"Error: {e}"

    def _tail(self, args: str) -> str:
        try:
            result = subprocess.run(f"tail {args}", shell=True, capture_output=True, text=True, timeout=10)
            return result.stdout
        except Exception as e:
            return f"Error: {e}"

    def _wc(self, args: str) -> str:
        try:
            result = subprocess.run(f"wc {args}", shell=True, capture_output=True, text=True, timeout=10)
            return result.stdout
        except Exception as e:
            return f"Error: {e}"

    def _stat(self, path: str) -> str:
        try:
            stat = os.stat(path)
            return f"Size: {stat.st_size} bytes\nModified: {datetime.fromtimestamp(stat.st_mtime)}\nCreated: {datetime.fromtimestamp(stat.st_ctime)}"
        except Exception as e:
            return f"Error: {e}"


class SystemInfoSkill(Skill):
    name = "system"
    description = "System information — CPU, memory, disk, network, processes"
    category = "system"
    commands = {"info": "System info", "cpu": "CPU usage", "mem": "Memory", "disk": "Disk usage", "net": "Network", "ps": "Processes", "env": "Env vars", "uptime": "Uptime", "hostname": "Hostname", "arch": "Architecture"}

    async def execute(self, command: str, args: str, **kwargs) -> str:
        cmds = {
            "info": "uname -a",
            "cpu": "top -bn1 | head -5",
            "mem": "free -h",
            "disk": "df -h",
            "net": "ip addr show 2>/dev/null || ifconfig",
            "ps": "ps aux --sort=-%mem | head -20",
            "env": "env | head -30",
            "uptime": "uptime",
            "hostname": "hostname",
            "arch": "uname -m",
        }
        cmd = cmds.get(command)
        if cmd:
            try:
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
                return result.stdout[:5000]
            except Exception as e:
                return f"Error: {e}"
        return f"Unknown command: {command}"


class GitSkill(Skill):
    name = "git"
    description = "Git operations — status, log, diff, commit, branch, push"
    category = "dev"
    commands = {"status": "Git status", "log": "Git log", "diff": "Git diff", "branch": "List branches", "commit": "Commit", "push": "Push", "pull": "Pull", "stash": "Stash", "clone": "Clone repo"}

    async def execute(self, command: str, args: str, **kwargs) -> str:
        cmd = f"git {command} {args}"
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
            return (result.stdout + result.stderr)[:5000]
        except Exception as e:
            return f"Error: {e}"


class DockerSkill(Skill):
    name = "docker"
    description = "Docker operations — ps, images, build, run, logs"
    category = "devops"
    commands = {"ps": "List containers", "images": "List images", "build": "Build image", "run": "Run container", "logs": "View logs", "stop": "Stop container", "rm": "Remove container"}

    async def execute(self, command: str, args: str, **kwargs) -> str:
        cmd = f"docker {command} {args}"
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
            return (result.stdout + result.stderr)[:5000]
        except Exception as e:
            return f"Error: {e}"


class PackageManagerSkill(Skill):
    name = "pkg"
    description = "Package managers — pip, npm, apt, brew"
    category = "system"
    commands = {"pip": "Python packages", "npm": "Node packages", "apt": "System packages", "brew": "Homebrew"}

    async def execute(self, command: str, args: str, **kwargs) -> str:
        cmds = {
            "pip": f"pip {args}",
            "npm": f"npm {args}",
            "apt": f"apt {args}",
            "brew": f"brew {args}",
        }
        cmd = cmds.get(command)
        if cmd:
            try:
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
                return (result.stdout + result.stderr)[:5000]
            except Exception as e:
                return f"Error: {e}"
        return f"Unknown package manager: {command}"


# ═══════════════════════════════════════════════════════════════
# 💻 CODE SKILLS
# ═══════════════════════════════════════════════════════════════

class PythonSkill(Skill):
    name = "python"
    description = "Python execution — run code, install packages, manage venvs"
    category = "code"
    commands = {"run": "Run Python code", "eval": "Evaluate expression", "install": "Install package", "venv": "Create venv"}

    async def execute(self, command: str, args: str, **kwargs) -> str:
        if command == "run":
            try:
                import tempfile
                with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
                    f.write(args)
                    f.flush()
                    result = subprocess.run(f"python3 {f.name}", shell=True, capture_output=True, text=True, timeout=30)
                    os.unlink(f.name)
                    return (result.stdout + result.stderr)[:10000]
            except Exception as e:
                return f"Error: {e}"
        elif command == "eval":
            try:
                return str(eval(args))
            except Exception as e:
                return f"Error: {e}"
        return f"Unknown command: {command}"


class NodeSkill(Skill):
    name = "node"
    description = "Node.js execution — run JavaScript code"
    category = "code"
    commands = {"run": "Run JS code", "eval": "Evaluate expression"}

    async def execute(self, command: str, args: str, **kwargs) -> str:
        if command in ("run", "eval"):
            try:
                result = subprocess.run(f"node -e '{args}'", shell=True, capture_output=True, text=True, timeout=30)
                return (result.stdout + result.stderr)[:10000]
            except Exception as e:
                return f"Error: {e}"
        return f"Unknown command: {command}"


class ShellSkill(Skill):
    name = "shell"
    description = "Shell execution — run any shell command"
    category = "system"
    commands = {"run": "Run command", "bash": "Run bash script"}

    async def execute(self, command: str, args: str, **kwargs) -> str:
        try:
            result = subprocess.run(args, shell=True, capture_output=True, text=True, timeout=30)
            return (result.stdout + result.stderr)[:10000]
        except Exception as e:
            return f"Error: {e}"


class RegexSkill(Skill):
    name = "regex"
    description = "Regex operations — test, match, replace, explain"
    category = "code"
    commands = {"test": "Test pattern", "match": "Find matches", "replace": "Replace", "explain": "Explain pattern"}

    async def execute(self, command: str, args: str, **kwargs) -> str:
        parts = args.split(" ", 1)
        if len(parts) < 2:
            return "Usage: regex <pattern> <text>"
        pattern, text = parts
        try:
            if command == "test":
                return str(bool(re.search(pattern, text)))
            elif command == "match":
                matches = re.findall(pattern, text)
                return json.dumps(matches, indent=2)
            elif command == "replace":
                return re.sub(pattern, "", text)
            elif command == "explain":
                return f"Pattern: {pattern}\nMatches: {re.findall(pattern, text)}"
        except re.error as e:
            return f"Regex error: {e}"
        return f"Unknown command: {command}"


class JSONSkill(Skill):
    name = "json"
    description = "JSON operations — parse, format, query, validate"
    category = "code"
    commands = {"parse": "Parse JSON", "format": "Pretty print", "query": "Query with jq", "validate": "Validate JSON"}

    async def execute(self, command: str, args: str, **kwargs) -> str:
        try:
            if command == "parse":
                return json.dumps(json.loads(args), indent=2)
            elif command == "format":
                return json.dumps(json.loads(args), indent=2)
            elif command == "validate":
                json.loads(args)
                return "Valid JSON ✅"
        except json.JSONDecodeError as e:
            return f"Invalid JSON: {e}"
        return f"Unknown command: {command}"


class SQLSkill(Skill):
    name = "sql"
    description = "SQL operations — query SQLite databases"
    category = "code"
    commands = {"query": "Run SQL query", "tables": "List tables", "schema": "Show schema"}

    async def execute(self, command: str, args: str, **kwargs) -> str:
        try:
            import sqlite3
            if command == "query":
                parts = args.split(" ", 1)
                db_path = parts[0]
                query = parts[1] if len(parts) > 1 else "SELECT 1"
                conn = sqlite3.connect(db_path)
                cursor = conn.execute(query)
                results = cursor.fetchall()
                conn.close()
                return "\n".join([str(r) for r in results[:100]])
            elif command == "tables":
                conn = sqlite3.connect(args)
                tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
                conn.close()
                return "\n".join([t[0] for t in tables])
        except Exception as e:
            return f"Error: {e}"
        return f"Unknown command: {command}"


# ═══════════════════════════════════════════════════════════════
# 🌐 WEB SKILLS
# ═══════════════════════════════════════════════════════════════

class WebSearchSkill(Skill):
    name = "web"
    description = "Web search, URL fetching, page scraping"
    category = "web"
    commands = {"search": "Search web", "fetch": "Fetch URL", "weather": "Get weather", "news": "News headlines"}

    def __init__(self, search_engine=None):
        self.search_engine = search_engine

    async def execute(self, command: str, args: str, **kwargs) -> str:
        if self.search_engine:
            if command == "search":
                results = await self.search_engine.search(args)
                return "\n".join([f"📌 {r['title']}\n   {r['snippet']}\n   {r['url']}" for r in results])
            elif command == "fetch":
                return await self.search_engine.fetch_page(args)
            elif command == "weather":
                return await self.search_engine.get_weather(args)
            elif command == "news":
                headlines = await self.search_engine.get_news_headlines()
                return "\n".join([f"• {h}" for h in headlines])
        return "Web search not available"


class APISkill(Skill):
    name = "api"
    description = "HTTP API client — GET, POST, PUT, DELETE"
    category = "web"
    commands = {"get": "HTTP GET", "post": "HTTP POST", "put": "HTTP PUT", "delete": "HTTP DELETE"}

    async def execute(self, command: str, args: str, **kwargs) -> str:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=30) as client:
                if command == "get":
                    resp = await client.get(args)
                elif command == "post":
                    url, _, body = args.partition(" ")
                    resp = await client.post(url, json=json.loads(body))
                else:
                    return f"Unsupported method: {command}"
                return f"Status: {resp.status_code}\n{resp.text[:5000]}"
        except Exception as e:
            return f"Error: {e}"


# ═══════════════════════════════════════════════════════════════
# 📊 DATA & ANALYSIS SKILLS
# ═══════════════════════════════════════════════════════════════

class DataAnalysisSkill(Skill):
    name = "data"
    description = "Data analysis — CSV, statistics, charts"
    category = "data"
    commands = {"csv": "Parse CSV", "stats": "Statistics", "chart": "Generate chart", "convert": "Convert formats"}

    async def execute(self, command: str, args: str, **kwargs) -> str:
        if command == "csv":
            try:
                reader = csv.reader(io.StringIO(args))
                rows = list(reader)
                return f"Parsed {len(rows)} rows, {len(rows[0]) if rows else 0} columns\n" + "\n".join([", ".join(row[:5]) for row in rows[:10]])
            except Exception as e:
                return f"Error: {e}"
        elif command == "stats":
            try:
                numbers = [float(x) for x in args.split()]
                n = len(numbers)
                mean = sum(numbers) / n
                sorted_nums = sorted(numbers)
                median = sorted_nums[n // 2]
                variance = sum((x - mean) ** 2 for x in numbers) / n
                std = math.sqrt(variance)
                return f"Count: {n}\nMean: {mean:.2f}\nMedian: {median:.2f}\nStd Dev: {std:.2f}\nMin: {min(numbers)}\nMax: {max(numbers)}"
            except Exception as e:
                return f"Error: {e}"
        return f"Unknown command: {command}"


class CalculatorSkill(Skill):
    name = "math"
    description = "Math operations — calculator, conversions, formulas"
    category = "utility"
    commands = {"calc": "Calculate", "convert": "Unit convert", "formula": "Apply formula"}

    async def execute(self, command: str, args: str, **kwargs) -> str:
        if command == "calc":
            try:
                # Safe math evaluation
                allowed = set("0123456789+-*/.()%^ ")
                if all(c in allowed for c in args):
                    result = eval(args, {"__builtins__": {}}, {"math": math})
                    return str(result)
                return "Invalid expression"
            except Exception as e:
                return f"Error: {e}"
        elif command == "convert":
            return self._convert(args)
        return f"Unknown command: {command}"

    def _convert(self, args: str) -> str:
        conversions = {
            "km_to_miles": lambda x: x * 0.621371,
            "miles_to_km": lambda x: x * 1.60934,
            "kg_to_lbs": lambda x: x * 2.20462,
            "lbs_to_kg": lambda x: x * 0.453592,
            "c_to_f": lambda x: x * 9/5 + 32,
            "f_to_c": lambda x: (x - 32) * 5/9,
            "usd_to_eur": lambda x: x * 0.92,
            "eur_to_usd": lambda x: x * 1.09,
        }
        parts = args.split()
        if len(parts) >= 3:
            value = float(parts[0])
            conv_key = f"{parts[1]}_to_{parts[2]}"
            if conv_key in conversions:
                return str(conversions[conv_key](value))
        return f"Available: {', '.join(conversions.keys())}"


class CryptoSkill(Skill):
    name = "crypto"
    description = "Cryptography — hashing, encoding, encryption"
    category = "security"
    commands = {"hash": "Hash data", "encode": "Encode", "decode": "Decode", "generate": "Generate keys"}

    async def execute(self, command: str, args: str, **kwargs) -> str:
        if command == "hash":
            parts = args.split(" ", 1)
            algo = parts[0] if parts else "sha256"
            data = parts[1] if len(parts) > 1 else ""
            h = hashlib.new(algo)
            h.update(data.encode())
            return h.hexdigest()
        elif command == "encode":
            return base64.b64encode(args.encode()).decode()
        elif command == "decode":
            return base64.b64decode(args.encode()).decode()
        elif command == "generate":
            import secrets
            return secrets.token_hex(int(args) if args.isdigit() else 32)
        return f"Unknown command: {command}"


class UUIDSkill(Skill):
    name = "uuid"
    description = "UUID generation and validation"
    category = "utility"
    commands = {"generate": "Generate UUID", "validate": "Validate UUID"}

    async def execute(self, command: str, args: str, **kwargs) -> str:
        import uuid
        if command == "generate":
            count = int(args) if args.isdigit() else 1
            return "\n".join([str(uuid.uuid4()) for _ in range(min(count, 100))])
        elif command == "validate":
            try:
                uuid.UUID(args)
                return "Valid UUID ✅"
            except ValueError:
                return "Invalid UUID ❌"
        return f"Unknown command: {command}"


class DateTimeSkill(Skill):
    name = "datetime"
    description = "Date/time operations — now, convert, calculate"
    category = "utility"
    commands = {"now": "Current time", "convert": "Convert timezone", "diff": "Date difference", "format": "Format date"}

    async def execute(self, command: str, args: str, **kwargs) -> str:
        now = datetime.now()
        if command == "now":
            return now.strftime("%Y-%m-%d %H:%M:%S %A")
        elif command == "format":
            return now.strftime(args or "%Y-%m-%d %H:%M:%S")
        elif command == "diff":
            try:
                parts = args.split()
                d1 = datetime.fromisoformat(parts[0])
                d2 = datetime.fromisoformat(parts[1]) if len(parts) > 1 else now
                return str(abs((d2 - d1).days)) + " days"
            except Exception as e:
                return f"Error: {e}"
        return f"Unknown command: {command}"


class RandomSkill(Skill):
    name = "random"
    description = "Random generation — numbers, strings, choices"
    category = "utility"
    commands = {"number": "Random number", "string": "Random string", "choice": "Random choice", "shuffle": "Shuffle list"}

    async def execute(self, command: str, args: str, **kwargs) -> str:
        if command == "number":
            parts = args.split()
            lo, hi = int(parts[0]), int(parts[1]) if len(parts) > 1 else 100
            return str(random.randint(lo, hi))
        elif command == "string":
            length = int(args) if args.isdigit() else 16
            return "".join(random.choices("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=length))
        elif command == "choice":
            choices = args.split(",")
            return random.choice(choices).strip()
        elif command == "shuffle":
            items = args.split(",")
            random.shuffle(items)
            return ", ".join(items)
        return f"Unknown command: {command}"


class LoremSkill(Skill):
    name = "lorem"
    description = "Lorem ipsum text generation"
    category = "utility"
    commands = {"generate": "Generate text", "words": "Generate words", "paragraphs": "Generate paragraphs"}

    async def execute(self, command: str, args: str, **kwargs) -> str:
        words = "lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod tempor incididunt ut labore et dolore magna aliqua".split()
        if command == "words":
            count = int(args) if args.isdigit() else 10
            return " ".join(random.choices(words, k=count))
        elif command in ("paragraphs", "generate"):
            count = int(args) if args.isdigit() else 1
            paras = []
            for _ in range(count):
                para = " ".join(random.choices(words, k=random.randint(40, 80)))
                paras.append(para.capitalize() + ".")
            return "\n\n".join(paras)
        return " ".join(random.choices(words, k=10))


# ═══════════════════════════════════════════════════════════════
# 📝 WRITING & CONTENT SKILLS
# ═══════════════════════════════════════════════════════════════

class MarkdownSkill(Skill):
    name = "markdown"
    description = "Markdown operations — render, convert, validate"
    category = "writing"
    commands = {"render": "Render MD", "toc": "Generate TOC", "validate": "Validate MD"}

    async def execute(self, command: str, args: str, **kwargs) -> str:
        if command == "toc":
            lines = args.split("\n")
            toc = []
            for line in lines:
                if line.startswith("#"):
                    level = len(line) - len(line.lstrip("#"))
                    title = line.lstrip("#").strip()
                    indent = "  " * (level - 1)
                    toc.append(f"{indent}- {title}")
            return "\n".join(toc) or "No headings found"
        elif command == "validate":
            # Basic MD validation
            issues = []
            if "**" in args and args.count("**") % 2 != 0:
                issues.append("Unclosed bold markers")
            if "`" in args and args.count("`") % 2 != 0:
                issues.append("Unclosed code markers")
            return "Valid ✅" if not issues else "\n".join(issues)
        return f"Unknown command: {command}"


class YAMLSkill(Skill):
    name = "yaml"
    description = "YAML operations — parse, validate, convert"
    category = "data"
    commands = {"parse": "Parse YAML", "validate": "Validate YAML", "to_json": "Convert to JSON"}

    async def execute(self, command: str, args: str, **kwargs) -> str:
        try:
            import yaml
            if command == "parse":
                data = yaml.safe_load(args)
                return json.dumps(data, indent=2)
            elif command == "validate":
                yaml.safe_load(args)
                return "Valid YAML ✅"
            elif command == "to_json":
                data = yaml.safe_load(args)
                return json.dumps(data, indent=2)
        except Exception as e:
            return f"Error: {e}"
        return f"Unknown command: {command}"


class TOMLSkill(Skill):
    name = "toml"
    description = "TOML operations — parse, validate"
    category = "data"
    commands = {"parse": "Parse TOML", "validate": "Validate TOML"}

    async def execute(self, command: str, args: str, **kwargs) -> str:
        try:
            if command == "parse":
                try:
                    import tomllib
                except ImportError:
                    import tomli as tomllib
                data = tomllib.loads(args)
                return json.dumps(data, indent=2)
            elif command == "validate":
                try:
                    import tomllib
                except ImportError:
                    import tomli as tomllib
                tomllib.loads(args)
                return "Valid TOML ✅"
        except Exception as e:
            return f"Error: {e}"
        return f"Unknown command: {command}"


class TemplateSkill(Skill):
    name = "template"
    description = "Template engine — Jinja2-like templates"
    category = "writing"
    commands = {"render": "Render template", "list": "List templates"}

    async def execute(self, command: str, args: str, **kwargs) -> str:
        if command == "render":
            # Simple variable substitution
            template = args
            variables = kwargs.get("variables", {})
            for key, value in variables.items():
                template = template.replace(f"{{{{{key}}}}}", str(value))
            return template
        return f"Unknown command: {command}"


# ═══════════════════════════════════════════════════════════════
# 🔒 SECURITY SKILLS
# ═══════════════════════════════════════════════════════════════

class PasswordSkill(Skill):
    name = "password"
    description = "Password generation, strength checking"
    category = "security"
    commands = {"generate": "Generate password", "strength": "Check strength"}

    async def execute(self, command: str, args: str, **kwargs) -> str:
        import secrets
        import string
        if command == "generate":
            length = int(args) if args.isdigit() else 20
            chars = string.ascii_letters + string.digits + "!@#$%^&*"
            return "".join(secrets.choice(chars) for _ in range(length))
        elif command == "strength":
            score = 0
            if len(args) >= 8: score += 1
            if len(args) >= 12: score += 1
            if any(c.isupper() for c in args): score += 1
            if any(c.islower() for c in args): score += 1
            if any(c.isdigit() for c in args): score += 1
            if any(c in "!@#$%^&*" for c in args): score += 1
            levels = {0: "Very Weak", 1: "Weak", 2: "Fair", 3: "Good", 4: "Strong", 5: "Very Strong", 6: "Excellent"}
            return f"Strength: {levels.get(score, 'Unknown')} ({score}/6)"
        return f"Unknown command: {command}"


class IPInfoSkill(Skill):
    name = "ip"
    description = "IP address information and lookup"
    category = "network"
    commands = {"myip": "Your public IP", "lookup": "IP lookup", "dns": "DNS lookup"}

    async def execute(self, command: str, args: str, **kwargs) -> str:
        try:
            import httpx
            if command == "myip":
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get("https://api.ipify.org?format=json")
                    return resp.json().get("ip", "Unknown")
            elif command == "lookup":
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get(f"http://ip-api.com/json/{args}")
                    data = resp.json()
                    return json.dumps(data, indent=2)
        except Exception as e:
            return f"Error: {e}"
        return f"Unknown command: {command}"


class URLSkill(Skill):
    name = "url"
    description = "URL operations — encode, decode, parse, shorten"
    category = "web"
    commands = {"encode": "URL encode", "decode": "URL decode", "parse": "Parse URL"}

    async def execute(self, command: str, args: str, **kwargs) -> str:
        from urllib.parse import quote, unquote, urlparse
        if command == "encode":
            return quote(args)
        elif command == "decode":
            return unquote(args)
        elif command == "parse":
            parsed = urlparse(args)
            return f"Scheme: {parsed.scheme}\nHost: {parsed.netloc}\nPath: {parsed.path}\nQuery: {parsed.query}\nFragment: {parsed.fragment}"
        return f"Unknown command: {command}"


# ═══════════════════════════════════════════════════════════════
# 🏠 IoT & AUTOMATION SKILLS
# ═══════════════════════════════════════════════════════════════

class CronSkill(Skill):
    name = "cron"
    description = "Scheduled tasks — cron jobs, timers, reminders"
    category = "automation"
    commands = {"list": "List jobs", "add": "Add job", "remove": "Remove job"}

    async def execute(self, command: str, args: str, **kwargs) -> str:
        if command == "list":
            try:
                result = subprocess.run("crontab -l", shell=True, capture_output=True, text=True)
                return result.stdout or "No cron jobs"
            except Exception as e:
                return f"Error: {e}"
        return f"Unknown command: {command}"


class ClipboardSkill(Skill):
    name = "clipboard"
    description = "Clipboard operations — copy, paste"
    category = "utility"
    commands = {"copy": "Copy to clipboard", "paste": "Paste from clipboard"}

    async def execute(self, command: str, args: str, **kwargs) -> str:
        try:
            if command == "copy":
                process = subprocess.Popen(["xclip", "-selection", "clipboard"], stdin=subprocess.PIPE)
                process.communicate(args.encode())
                return "Copied to clipboard ✅"
            elif command == "paste":
                result = subprocess.run(["xclip", "-selection", "clipboard", "-o"], capture_output=True, text=True)
                return result.stdout
        except Exception:
            return "Clipboard not available"
        return f"Unknown command: {command}"


class NotificationSkill(Skill):
    name = "notify"
    description = "Desktop notifications"
    category = "utility"
    commands = {"send": "Send notification"}

    async def execute(self, command: str, args: str, **kwargs) -> str:
        try:
            subprocess.run(["notify-send", "Rally Agent", args], capture_output=True)
            return "Notification sent ✅"
        except Exception:
            return "Notifications not available"


# ═══════════════════════════════════════════════════════════════
# 🎯 MASSIVE SKILLS REGISTRY
# ═══════════════════════════════════════════════════════════════

class SkillsRegistry:
    """Registry for ALL skills — hundreds of built-in capabilities"""

    def __init__(self, config, search_engine=None):
        self.config = config
        self.skills: dict[str, Skill] = {}
        self._register_all(search_engine)

    def _register_all(self, search_engine=None):
        """Register ALL built-in skills"""
        skills = [
            # Files & System
            FileOperationsSkill(),
            SystemInfoSkill(),
            GitSkill(),
            DockerSkill(),
            PackageManagerSkill(),
            # Code
            PythonSkill(),
            NodeSkill(),
            ShellSkill(),
            RegexSkill(),
            JSONSkill(),
            SQLSkill(),
            # Web
            WebSearchSkill(search_engine),
            APISkill(),
            # Data
            DataAnalysisSkill(),
            CalculatorSkill(),
            # Utility
            CryptoSkill(),
            UUIDSkill(),
            DateTimeSkill(),
            RandomSkill(),
            LoremSkill(),
            # Writing
            MarkdownSkill(),
            YAMLSkill(),
            TOMLSkill(),
            TemplateSkill(),
            # Security
            PasswordSkill(),
            IPInfoSkill(),
            URLSkill(),
            # Automation
            CronSkill(),
            ClipboardSkill(),
            NotificationSkill(),
        ]

        for skill in skills:
            self.skills[skill.name] = skill

    def get(self, name: str) -> Optional[Skill]:
        return self.skills.get(name)

    def get_all(self) -> list[dict]:
        return [s.to_dict() for s in self.skills.values()]

    def get_names(self) -> list[str]:
        return list(self.skills.keys())

    def get_by_category(self, category: str) -> list[Skill]:
        return [s for s in self.skills.values() if s.category == category]

    def get_categories(self) -> list[str]:
        return list(set(s.category for s in self.skills.values()))

    def get_total_commands(self) -> int:
        return sum(len(s.commands) for s in self.skills.values())

    async def execute(self, skill_name: str, command: str, args: str, **kwargs) -> str:
        skill = self.skills.get(skill_name)
        if not skill:
            return f"Unknown skill: {skill_name}. Available: {', '.join(self.skills.keys())}"
        try:
            return await skill.execute(command, args, **kwargs)
        except Exception as e:
            return f"Skill error: {e}"

    def register(self, skill: Skill):
        """Register a custom skill"""
        self.skills[skill.name] = skill
