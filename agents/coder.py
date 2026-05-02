"""
🟣 Rally Agent — Autonomous Coding Agent
Full autonomous development loop: Plan → Code → Test → PR

Capabilities:
- Repository understanding (file tree, deps, structure)
- Code generation with iterative refinement
- Auto-generated unit and integration tests
- Code review with correctness/style/security/performance feedback
- Bug reproduction and fixing
- Intelligent refactoring
- Git integration (branch, commit, push, PR)
- Semantic code search
- Dependency analysis
- Architecture documentation generation
"""

from __future__ import annotations

import ast
import asyncio
import hashlib
import json
import logging
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Coroutine, Dict, List, Optional, Tuple

from cli.theme import Theme, console

logger = logging.getLogger("rally.agent.coder")


# ═══════════════════════════════════════════════════════════════
# Data Types
# ═══════════════════════════════════════════════════════════════

class TaskPhase(str, Enum):
    """Phases of the autonomous development loop."""
    ANALYZE = "analyze"
    PLAN = "plan"
    CODE = "code"
    TEST = "test"
    REVIEW = "review"
    REFACTOR = "refactor"
    DOCUMENT = "document"
    COMMIT = "commit"
    DONE = "done"


class Severity(str, Enum):
    """Issue severity for code reviews."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class IssueCategory(str, Enum):
    """Code review issue categories."""
    CORRECTNESS = "correctness"
    STYLE = "style"
    SECURITY = "security"
    PERFORMANCE = "performance"
    MAINTAINABILITY = "maintainability"
    TESTING = "testing"
    DOCUMENTATION = "documentation"


@dataclass
class CodeIssue:
    """A single issue found during code review."""
    file_path: str
    line: int
    category: IssueCategory
    severity: Severity
    message: str
    suggestion: str = ""

    def to_dict(self) -> dict:
        return {
            "file": self.file_path,
            "line": self.line,
            "category": self.category.value,
            "severity": self.severity.value,
            "message": self.message,
            "suggestion": self.suggestion,
        }


@dataclass
class RepoAnalysis:
    """Analysis of a repository's structure and dependencies."""
    root_path: str
    languages: Dict[str, int] = field(default_factory=dict)  # lang -> file count
    file_tree: List[dict] = field(default_factory=list)
    dependencies: Dict[str, List[str]] = field(default_factory=dict)  # lang -> deps
    entry_points: List[str] = field(default_factory=list)
    test_files: List[str] = field(default_factory=list)
    config_files: List[str] = field(default_factory=list)
    total_files: int = 0
    total_lines: int = 0
    structure_summary: str = ""

    def to_dict(self) -> dict:
        return {
            "root": self.root_path,
            "languages": self.languages,
            "total_files": self.total_files,
            "total_lines": self.total_lines,
            "dependencies": self.dependencies,
            "entry_points": self.entry_points,
            "test_files": self.test_files[:20],
            "config_files": self.config_files,
            "summary": self.structure_summary,
        }


@dataclass
class DevelopmentPlan:
    """A plan for implementing a feature or fix."""
    task_description: str
    steps: List[dict] = field(default_factory=list)  # [{action, target, details}]
    files_to_create: List[str] = field(default_factory=list)
    files_to_modify: List[str] = field(default_factory=list)
    tests_to_write: List[str] = field(default_factory=list)
    estimated_complexity: str = "medium"  # low, medium, high
    risks: List[str] = field(default_factory=list)


@dataclass
class TestResult:
    """Result of running tests."""
    success: bool
    total: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    output: str = ""
    duration_seconds: float = 0.0


@dataclass
class CommitInfo:
    """Information about a git commit."""
    hash: str
    message: str
    author: str
    timestamp: str
    files_changed: List[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════
# Tool Interface (injected by engine)
# ═══════════════════════════════════════════════════════════════

class CoderTools:
    """Interface for tools the coding agent can use.

    The engine injects real tool implementations at runtime.
    This class provides the contract the agent expects.
    """

    async def read_file(self, path: str, offset: int = 1, limit: int = 5000) -> dict:
        """Read a file and return {path, total_lines, content}."""
        ...

    async def write_file(self, path: str, content: str, append: bool = False) -> dict:
        """Write content to a file."""
        ...

    async def edit_file(self, path: str, old_text: str, new_text: str) -> dict:
        """Replace exact text in a file."""
        ...

    async def exec_command(self, command: str, timeout: int = 60, cwd: str = None) -> dict:
        """Execute a shell command and return {exit_code, stdout, stderr}."""
        ...

    async def python_exec(self, code: str, timeout: int = 30) -> dict:
        """Execute Python code and return output."""
        ...

    async def list_directory(self, path: str, pattern: str = None) -> dict:
        """List directory contents."""
        ...

    async def web_search(self, query: str, num_results: int = 5) -> dict:
        """Search the web."""
        ...

    async def chat(self, messages: list, system: str = "") -> str:
        """Send messages to the LLM and get a response."""
        ...


# ═══════════════════════════════════════════════════════════════
# System Prompt
# ═══════════════════════════════════════════════════════════════

CODER_SYSTEM_PROMPT = """You are Rally Coder — an autonomous software development agent.

## Your Identity
You are a senior software engineer with deep expertise across languages, frameworks, and architectures.
You write production-quality code: clean, well-documented, tested, secure, and performant.

## Core Principles
1. **Read before writing** — Always understand existing code before modifying it
2. **Test everything** — Write tests for all new code; verify existing tests still pass
3. **Minimal changes** — Make the smallest change that solves the problem correctly
4. **Explain your reasoning** — Document why you made each decision
5. **Security first** — Never introduce vulnerabilities; sanitize inputs, validate data
6. **Respect conventions** — Match the existing code style, patterns, and architecture

## Autonomous Development Loop
When given a task, follow this loop:
1. **ANALYZE** — Understand the codebase, read relevant files, identify patterns
2. **PLAN** — Break the task into concrete steps, identify risks
3. **CODE** — Implement changes with clean, tested code
4. **TEST** — Write and run tests, fix failures
5. **REVIEW** — Self-review for correctness, style, security, performance
6. **REFACTOR** — Clean up if needed (DRY, naming, structure)
7. **DOCUMENT** — Update docs, comments, and commit messages
8. **COMMIT** — Git commit with descriptive message

## Tool Usage
You have access to these tools — USE THEM to actually do things:
- `read_file(path, offset, limit)` — Read file contents
- `write_file(path, content)` — Create or overwrite files
- `edit_file(path, old_text, new_text)` — Surgical text replacement
- `exec_command(command, timeout, cwd)` — Run shell commands (git, npm, pytest, etc.)
- `python_exec(code, timeout)` — Execute Python snippets
- `list_directory(path, pattern)` — Browse directory structure
- `web_search(query)` — Search for documentation/examples

## Code Quality Standards
- Functions: max 50 lines, single responsibility
- Files: max 500 lines, split into modules if larger
- Naming: descriptive, consistent with project conventions
- Error handling: always handle edge cases and failures
- Types: use type hints (Python), TypeScript types, etc.
- Comments: explain WHY, not WHAT (code should be self-documenting)

## When Stuck
- Search the web for solutions
- Break the problem into smaller pieces
- Try a different approach
- Ask for clarification if requirements are ambiguous

## Output Format
When reporting progress, use this structure:
- 📋 **Analysis**: What you found
- 📝 **Plan**: What you'll do
- 💻 **Code**: What you wrote/changed
- ✅ **Tests**: What you tested
- 🔍 **Review**: Self-review findings
- 📦 **Commit**: Git commit details
"""


# ═══════════════════════════════════════════════════════════════
# Repository Analyzer
# ═══════════════════════════════════════════════════════════════

class RepoAnalyzer:
    """Analyzes a repository to understand its structure, languages, and dependencies."""

    LANGUAGE_EXTENSIONS: Dict[str, str] = {
        ".py": "python", ".js": "javascript", ".ts": "typescript",
        ".tsx": "typescript", ".jsx": "javascript", ".go": "go",
        ".rs": "rust", ".rb": "ruby", ".java": "java",
        ".c": "c", ".cpp": "cpp", ".h": "c", ".hpp": "cpp",
        ".cs": "csharp", ".php": "php", ".swift": "swift",
        ".kt": "kotlin", ".scala": "scala", ".sh": "shell",
        ".bash": "shell", ".zsh": "shell", ".sql": "sql",
        ".html": "html", ".css": "css", ".scss": "css",
        ".json": "json", ".yaml": "yaml", ".yml": "yaml",
        ".toml": "toml", ".xml": "xml", ".md": "markdown",
        ".rst": "rst", ".txt": "text", ".dockerfile": "docker",
    }

    SKIP_DIRS = {
        ".git", "__pycache__", "node_modules", ".venv", "venv",
        ".tox", ".mypy_cache", ".pytest_cache", "dist", "build",
        ".eggs", "*.egg-info", ".next", ".nuxt", "target",
        ".idea", ".vscode", ".DS_Store",
    }

    ENTRY_PATTERNS = {
        "python": ["main.py", "app.py", "manage.py", "cli.py", "__main__.py", "setup.py", "pyproject.toml"],
        "javascript": ["index.js", "main.js", "app.js", "server.js", "package.json"],
        "typescript": ["index.ts", "main.ts", "app.ts", "server.ts", "tsconfig.json"],
        "go": ["main.go", "go.mod"],
        "rust": ["main.rs", "lib.rs", "Cargo.toml"],
        "java": ["Main.java", "Application.java", "pom.xml", "build.gradle"],
    }

    TEST_PATTERNS = [
        r"test_.*\.py$", r".*_test\.py$", r"tests?/",
        r".*\.test\.(js|ts|tsx|jsx)$", r".*\.spec\.(js|ts|tsx|jsx)$",
        r"__tests__/", r"spec/",
    ]

    DEP_FILES = {
        "python": ["requirements.txt", "setup.py", "pyproject.toml", "Pipfile", "poetry.lock"],
        "javascript": ["package.json", "yarn.lock", "package-lock.json", "pnpm-lock.yaml"],
        "go": ["go.mod", "go.sum"],
        "rust": ["Cargo.toml", "Cargo.lock"],
        "java": ["pom.xml", "build.gradle", "build.gradle.kts"],
    }

    def __init__(self, tools: CoderTools):
        self.tools = tools

    async def analyze(self, root_path: str = ".") -> RepoAnalysis:
        """Perform full repository analysis."""
        analysis = RepoAnalysis(root_path=os.path.abspath(root_path))

        # Build file tree
        analysis.file_tree = await self._build_file_tree(root_path, depth=3)

        # Count files and lines
        await self._count_stats(root_path, analysis)

        # Detect languages
        self._detect_languages(analysis)

        # Find entry points
        analysis.entry_points = self._find_entry_points(analysis)

        # Find test files
        analysis.test_files = self._find_test_files(analysis)

        # Find config files
        analysis.config_files = self._find_config_files(analysis)

        # Parse dependencies
        analysis.dependencies = await self._parse_dependencies(root_path, analysis)

        # Generate summary
        analysis.structure_summary = self._generate_summary(analysis)

        return analysis

    async def _build_file_tree(self, path: str, depth: int = 3, prefix: str = "") -> List[dict]:
        """Build a file tree representation."""
        if depth <= 0:
            return []

        tree = []
        try:
            result = await self.tools.list_directory(path)
            entries = result.get("entries", [])
        except Exception:
            return []

        for entry in entries:
            name = entry.get("name", "")
            if name in self.SKIP_DIRS or name.startswith("."):
                continue

            entry_type = entry.get("type", "file")
            full_path = os.path.join(path, name)

            node = {
                "name": name,
                "type": entry_type,
                "path": full_path,
            }

            if entry_type == "directory":
                node["children"] = await self._build_file_tree(full_path, depth - 1, prefix + "  ")

            tree.append(node)

        return tree

    async def _count_stats(self, root: str, analysis: RepoAnalysis) -> None:
        """Count total files and lines of code."""
        try:
            result = await self.tools.exec_command(
                f'find "{root}" -type f '
                f'{" ".join(f"-not -path" + chr(34) + f"*/{d}/*" + chr(34) for d in self.SKIP_DIRS)} '
                f'| wc -l',
                timeout=10,
            )
            analysis.total_files = int(result.get("stdout", "0").strip() or 0)
        except Exception:
            analysis.total_files = 0

        try:
            result = await self.tools.exec_command(
                f'find "{root}" -type f -name "*.py" -o -name "*.js" -o -name "*.ts" '
                f'-o -name "*.go" -o -name "*.rs" -o -name "*.java" '
                f'| head -500 | xargs wc -l 2>/dev/null | tail -1',
                timeout=10,
            )
            line_str = result.get("stdout", "0").strip().split()[0]
            analysis.total_lines = int(line_str or 0)
        except Exception:
            analysis.total_lines = 0

    def _detect_languages(self, analysis: RepoAnalysis) -> None:
        """Detect programming languages from file tree."""
        lang_counts: Dict[str, int] = {}

        def walk_tree(nodes: List[dict]):
            for node in nodes:
                if node["type"] == "file":
                    ext = Path(node["name"]).suffix.lower()
                    lang = self.LANGUAGE_EXTENSIONS.get(ext)
                    if lang:
                        lang_counts[lang] = lang_counts.get(lang, 0) + 1
                elif "children" in node:
                    walk_tree(node["children"])

        walk_tree(analysis.file_tree)
        analysis.languages = dict(sorted(lang_counts.items(), key=lambda x: -x[1]))

    def _find_entry_points(self, analysis: RepoAnalysis) -> List[str]:
        """Identify likely entry points."""
        all_files = []

        def collect_files(nodes: List[dict], prefix: str = ""):
            for node in nodes:
                if node["type"] == "file":
                    all_files.append(node["name"])
                elif "children" in node:
                    collect_files(node["children"], prefix + node["name"] + "/")

        collect_files(analysis.file_tree)

        entry_points = []
        primary_lang = next(iter(analysis.languages), "python")
        patterns = self.ENTRY_PATTERNS.get(primary_lang, [])

        for pattern in patterns:
            if pattern in all_files:
                entry_points.append(pattern)

        return entry_points

    def _find_test_files(self, analysis: RepoAnalysis) -> List[str]:
        """Find test files."""
        all_paths = []

        def collect_paths(nodes: List[dict], prefix: str = ""):
            for node in nodes:
                path = prefix + node["name"]
                if node["type"] == "file":
                    all_paths.append(path)
                elif "children" in node:
                    collect_paths(node["children"], path + "/")

        collect_paths(analysis.file_tree)

        test_files = []
        for path in all_paths:
            for pattern in self.TEST_PATTERNS:
                if re.search(pattern, path, re.IGNORECASE):
                    test_files.append(path)
                    break

        return test_files

    def _find_config_files(self, analysis: RepoAnalysis) -> List[str]:
        """Find configuration files."""
        config_patterns = [
            "pyproject.toml", "setup.py", "setup.cfg", "tox.ini", ".flake8",
            "package.json", "tsconfig.json", ".eslintrc", ".prettierrc",
            "Cargo.toml", "go.mod", "Makefile", "Dockerfile", "docker-compose.yml",
            ".env", ".env.example", "README.md", "CONTRIBUTING.md",
            ".github/workflows", ".gitlab-ci.yml", "Jenkinsfile",
        ]

        all_names = []

        def collect_names(nodes: List[dict]):
            for node in nodes:
                if node["type"] == "file":
                    all_names.append(node["name"])
                elif "children" in node:
                    collect_names(node["children"])

        collect_names(analysis.file_tree)

        return [n for n in all_names if n in config_patterns]

    async def _parse_dependencies(self, root: str, analysis: RepoAnalysis) -> Dict[str, List[str]]:
        """Parse dependency files."""
        deps: Dict[str, List[str]] = {}

        for lang, dep_files in self.DEP_FILES.items():
            if lang not in analysis.languages:
                continue

            for dep_file in dep_files:
                file_path = os.path.join(root, dep_file)
                try:
                    result = await self.tools.read_file(file_path, limit=200)
                    content = result.get("content", "")

                    if dep_file == "requirements.txt":
                        deps[lang] = self._parse_requirements(content)
                    elif dep_file == "pyproject.toml":
                        deps[lang] = self._parse_pyproject_deps(content)
                    elif dep_file == "package.json":
                        deps[lang] = self._parse_package_json_deps(content)
                    elif dep_file == "go.mod":
                        deps[lang] = self._parse_go_mod(content)
                    elif dep_file == "Cargo.toml":
                        deps[lang] = self._parse_cargo_toml(content)
                except Exception:
                    continue

        return deps

    @staticmethod
    def _parse_requirements(content: str) -> List[str]:
        deps = []
        for line in content.strip().split("\n"):
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("-"):
                # Extract package name (before version specifier)
                name = re.split(r"[><=!~]", line)[0].strip()
                if name:
                    deps.append(name)
        return deps

    @staticmethod
    def _parse_pyproject_deps(content: str) -> List[str]:
        deps = []
        in_deps = False
        for line in content.split("\n"):
            if "dependencies" in line and "[" in line:
                in_deps = True
                continue
            if in_deps:
                if line.strip().startswith("]"):
                    break
                match = re.search(r'"([^"><=!~]+)', line)
                if match:
                    deps.append(match.group(1).strip())
        return deps

    @staticmethod
    def _parse_package_json_deps(content: str) -> List[str]:
        try:
            data = json.loads(content)
            deps = list(data.get("dependencies", {}).keys())
            deps += list(data.get("devDependencies", {}).keys())
            return deps
        except json.JSONDecodeError:
            return []

    @staticmethod
    def _parse_go_mod(content: str) -> List[str]:
        deps = []
        in_require = False
        for line in content.split("\n"):
            if line.strip().startswith("require ("):
                in_require = True
                continue
            if in_require:
                if line.strip() == ")":
                    break
                parts = line.strip().split()
                if parts:
                    deps.append(parts[0])
        return deps

    @staticmethod
    def _parse_cargo_toml(content: str) -> List[str]:
        deps = []
        in_deps = False
        for line in content.split("\n"):
            if line.strip() in ("[dependencies]", "[dev-dependencies]"):
                in_deps = True
                continue
            if in_deps:
                if line.strip().startswith("["):
                    break
                match = re.match(r'^(\w+)', line.strip())
                if match:
                    deps.append(match.group(1))
        return deps

    @staticmethod
    def _generate_summary(analysis: RepoAnalysis) -> str:
        """Generate a human-readable repository summary."""
        parts = []

        # Languages
        if analysis.languages:
            top_langs = list(analysis.languages.items())[:3]
            lang_str = ", ".join(f"{lang} ({count} files)" for lang, count in top_langs)
            parts.append(f"Languages: {lang_str}")

        # Size
        parts.append(f"Size: {analysis.total_files} files, ~{analysis.total_lines:,} lines")

        # Dependencies
        if analysis.dependencies:
            total_deps = sum(len(v) for v in analysis.dependencies.values())
            parts.append(f"Dependencies: {total_deps} packages")

        # Tests
        if analysis.test_files:
            parts.append(f"Tests: {len(analysis.test_files)} test files found")
        else:
            parts.append("Tests: none found ⚠️")

        # Entry points
        if analysis.entry_points:
            parts.append(f"Entry points: {', '.join(analysis.entry_points[:5])}")

        return " | ".join(parts)


# ═══════════════════════════════════════════════════════════════
# Code Search Engine
# ═══════════════════════════════════════════════════════════════

class CodeSearchEngine:
    """Semantic and keyword code search across a repository."""

    def __init__(self, tools: CoderTools):
        self.tools = tools
        self._index: Dict[str, List[dict]] = {}  # keyword -> [{file, line, context}]
        self._file_cache: Dict[str, str] = {}

    async def search_keyword(self, query: str, root: str = ".", file_pattern: str = None) -> List[dict]:
        """Keyword search across the codebase using grep."""
        pattern_arg = f'--include="{file_pattern}"' if file_pattern else ""
        result = await self.tools.exec_command(
            f'grep -rn --include="*.py" --include="*.js" --include="*.ts" '
            f'--include="*.go" --include="*.rs" --include="*.java" '
            f'{pattern_arg} "{query}" "{root}" 2>/dev/null | head -50',
            timeout=15,
        )

        matches = []
        for line in result.get("stdout", "").strip().split("\n"):
            if not line:
                continue
            parts = line.split(":", 2)
            if len(parts) >= 3:
                matches.append({
                    "file": parts[0],
                    "line": int(parts[1]) if parts[1].isdigit() else 0,
                    "content": parts[2].strip(),
                })

        return matches

    async def search_symbol(self, symbol: str, root: str = ".") -> List[dict]:
        """Find definitions of a symbol (function, class, variable)."""
        # Search for definitions
        patterns = [
            f"(def|function|func|fn|pub fn)\\s+{re.escape(symbol)}",
            f"(class|struct|interface|type)\\s+{re.escape(symbol)}",
            f"^\\s*{re.escape(symbol)}\\s*[:=]",
        ]

        all_matches = []
        for pattern in patterns:
            result = await self.tools.exec_command(
                f'grep -rn -E "{pattern}" "{root}" --include="*.py" --include="*.js" '
                f'--include="*.ts" --include="*.go" --include="*.rs" 2>/dev/null | head -20',
                timeout=10,
            )
            for line in result.get("stdout", "").strip().split("\n"):
                if not line:
                    continue
                parts = line.split(":", 2)
                if len(parts) >= 3:
                    all_matches.append({
                        "file": parts[0],
                        "line": int(parts[1]) if parts[1].isdigit() else 0,
                        "content": parts[2].strip(),
                        "type": "definition",
                    })

        return all_matches

    async def find_references(self, symbol: str, root: str = ".") -> List[dict]:
        """Find all references to a symbol."""
        result = await self.tools.exec_command(
            f'grep -rn --include="*.py" --include="*.js" --include="*.ts" '
            f'--include="*.go" --include="*.rs" "\\b{re.escape(symbol)}\\b" "{root}" 2>/dev/null | head -50',
            timeout=15,
        )

        refs = []
        for line in result.get("stdout", "").strip().split("\n"):
            if not line:
                continue
            parts = line.split(":", 2)
            if len(parts) >= 3:
                refs.append({
                    "file": parts[0],
                    "line": int(parts[1]) if parts[1].isdigit() else 0,
                    "content": parts[2].strip(),
                })

        return refs


# ═══════════════════════════════════════════════════════════════
# Git Integration
# ═══════════════════════════════════════════════════════════════

class GitManager:
    """Git operations for the coding agent."""

    def __init__(self, tools: CoderTools, repo_root: str = "."):
        self.tools = tools
        self.repo_root = repo_root

    async def is_git_repo(self) -> bool:
        """Check if current directory is a git repo."""
        result = await self.tools.exec_command(
            "git rev-parse --is-inside-work-tree 2>/dev/null",
            cwd=self.repo_root,
        )
        return result.get("stdout", "").strip() == "true"

    async def status(self) -> dict:
        """Get git status."""
        result = await self.tools.exec_command(
            "git status --porcelain",
            cwd=self.repo_root,
        )
        files = []
        for line in result.get("stdout", "").strip().split("\n"):
            if line:
                status = line[:2].strip()
                path = line[3:].strip()
                files.append({"status": status, "path": path})

        return {"files": files, "clean": len(files) == 0}

    async def current_branch(self) -> str:
        """Get current branch name."""
        result = await self.tools.exec_command(
            "git branch --show-current",
            cwd=self.repo_root,
        )
        return result.get("stdout", "").strip()

    async def create_branch(self, name: str) -> bool:
        """Create and checkout a new branch."""
        result = await self.tools.exec_command(
            f"git checkout -b {name}",
            cwd=self.repo_root,
        )
        return result.get("exit_code", 1) == 0

    async def checkout(self, branch: str) -> bool:
        """Switch to a branch."""
        result = await self.tools.exec_command(
            f"git checkout {branch}",
            cwd=self.repo_root,
        )
        return result.get("exit_code", 1) == 0

    async def stage_all(self) -> bool:
        """Stage all changes."""
        result = await self.tools.exec_command(
            "git add -A",
            cwd=self.repo_root,
        )
        return result.get("exit_code", 1) == 0

    async def commit(self, message: str) -> Optional[CommitInfo]:
        """Create a commit."""
        result = await self.tools.exec_command(
            f'git commit -m "{message}"',
            cwd=self.repo_root,
        )
        if result.get("exit_code", 1) != 0:
            logger.error(f"Commit failed: {result.get('stderr', '')}")
            return None

        # Get commit hash
        hash_result = await self.tools.exec_command(
            "git rev-parse HEAD",
            cwd=self.repo_root,
        )
        return CommitInfo(
            hash=hash_result.get("stdout", "").strip()[:8],
            message=message,
            author="Rally Coder",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    async def push(self, remote: str = "origin", branch: str = None) -> bool:
        """Push to remote."""
        if branch is None:
            branch = await self.current_branch()
        result = await self.tools.exec_command(
            f"git push {remote} {branch}",
            cwd=self.repo_root,
            timeout=60,
        )
        return result.get("exit_code", 1) == 0

    async def log(self, limit: int = 10) -> List[CommitInfo]:
        """Get recent commit history."""
        result = await self.tools.exec_command(
            f'git log --oneline -{limit} --format="%H|%s|%an|%ai"',
            cwd=self.repo_root,
        )
        commits = []
        for line in result.get("stdout", "").strip().split("\n"):
            if not line:
                continue
            parts = line.split("|", 3)
            if len(parts) >= 4:
                commits.append(CommitInfo(
                    hash=parts[0][:8],
                    message=parts[1],
                    author=parts[2],
                    timestamp=parts[3],
                ))
        return commits

    async def diff(self, staged: bool = False) -> str:
        """Get diff of changes."""
        cmd = "git diff --cached" if staged else "git diff"
        result = await self.tools.exec_command(cmd, cwd=self.repo_root)
        return result.get("stdout", "")

    async def diff_stat(self) -> str:
        """Get diff stat summary."""
        result = await self.tools.exec_command(
            "git diff --stat",
            cwd=self.repo_root,
        )
        return result.get("stdout", "")


# ═══════════════════════════════════════════════════════════════
# Test Runner
# ═══════════════════════════════════════════════════════════════

class TestRunner:
    """Runs and parses test results for various frameworks."""

    FRAMEWORKS = {
        "python": {
            "pytest": "python -m pytest -v --tb=short {path} 2>&1",
            "unittest": "python -m unittest {path} -v 2>&1",
        },
        "javascript": {
            "jest": "npx jest --verbose {path} 2>&1",
            "vitest": "npx vitest run {path} 2>&1",
            "mocha": "npx mocha {path} 2>&1",
        },
        "go": {
            "go test": "go test -v ./... 2>&1",
        },
        "rust": {
            "cargo test": "cargo test 2>&1",
        },
    }

    def __init__(self, tools: CoderTools):
        self.tools = tools

    async def detect_framework(self, root: str = ".") -> Optional[Tuple[str, str]]:
        """Detect the test framework used in the project."""
        # Python
        for fw_cmd in ["pytest", "unittest"]:
            check = await self.tools.exec_command(
                f"grep -r 'pytest\\|unittest' {root}/pyproject.toml {root}/setup.py {root}/tox.ini 2>/dev/null | head -5",
                timeout=5,
            )
            if check.get("stdout", "").strip():
                return ("python", fw_cmd)

        # Check for pytest.ini or conftest.py
        for f in ["pytest.ini", "conftest.py", "setup.cfg"]:
            check = await self.tools.exec_command(f"test -f {root}/{f}", timeout=5)
            if check.get("exit_code") == 0:
                return ("python", "pytest")

        # JavaScript
        for fw in ["jest", "vitest", "mocha"]:
            check = await self.tools.exec_command(
                f"grep -q '\"{fw}\"' {root}/package.json 2>/dev/null",
                timeout=5,
            )
            if check.get("exit_code") == 0:
                return ("javascript", fw)

        # Go
        check = await self.tools.exec_command(f"test -f {root}/go.mod", timeout=5)
        if check.get("exit_code") == 0:
            return ("go", "go test")

        # Rust
        check = await self.tools.exec_command(f"test -f {root}/Cargo.toml", timeout=5)
        if check.get("exit_code") == 0:
            return ("rust", "cargo test")

        return None

    async def run_tests(self, path: str = ".", framework: Tuple[str, str] = None) -> TestResult:
        """Run tests and parse results."""
        if framework is None:
            framework = await self.detect_framework(path)

        if framework is None:
            return TestResult(
                success=False,
                output="No test framework detected. Please specify one.",
            )

        lang, fw = framework
        cmd_template = self.FRAMEWORKS.get(lang, {}).get(fw)
        if not cmd_template:
            return TestResult(success=False, output=f"Unknown framework: {fw}")

        cmd = cmd_template.format(path=path)
        start = time.time()
        result = await self.tools.exec_command(cmd, timeout=120, cwd=path)
        duration = time.time() - start

        stdout = result.get("stdout", "") + result.get("stderr", "")
        exit_code = result.get("exit_code", 1)

        # Parse results
        passed, failed, errors, skipped = self._parse_test_output(stdout, lang, fw)

        total = passed + failed + errors + skipped
        return TestResult(
            success=exit_code == 0 and failed == 0,
            total=total,
            passed=passed,
            failed=failed,
            errors=errors,
            skipped=skipped,
            output=stdout[-5000:],  # Last 5k chars
            duration_seconds=duration,
        )

    @staticmethod
    def _parse_test_output(output: str, lang: str, fw: str) -> Tuple[int, int, int, int]:
        """Parse test output to extract counts."""
        passed = failed = errors = skipped = 0

        if lang == "python":
            # pytest output: "X passed, Y failed, Z errors, W skipped"
            match = re.search(
                r"(\d+) passed(?:.*?(\d+) failed)?(?:.*?(\d+) error)?(?:.*?(\d+) skipped)?",
                output,
            )
            if match:
                passed = int(match.group(1) or 0)
                failed = int(match.group(2) or 0)
                errors = int(match.group(3) or 0)
                skipped = int(match.group(4) or 0)
            elif "PASSED" in output:
                passed = output.count("PASSED")
                failed = output.count("FAILED")
                errors = output.count("ERROR")
        elif lang == "javascript":
            passed = len(re.findall(r"[✓✔√]", output)) + len(re.findall(r"PASS", output))
            failed = len(re.findall(r"[✗✘×]", output)) + len(re.findall(r"FAIL", output))
        elif lang == "go":
            passed = len(re.findall(r"--- PASS", output))
            failed = len(re.findall(r"--- FAIL", output))
        elif lang == "rust":
            passed = len(re.findall(r"test .* ok", output))
            failed = len(re.findall(r"test .* FAILED", output))

        return passed, failed, errors, skipped


# ═══════════════════════════════════════════════════════════════
# Code Reviewer
# ═══════════════════════════════════════════════════════════════

class CodeReviewer:
    """Reviews code for correctness, style, security, and performance."""

    SECURITY_PATTERNS = [
        (r"eval\s*\(", Severity.CRITICAL, "Use of eval() — potential code injection"),
        (r"exec\s*\(", Severity.HIGH, "Use of exec() — potential code injection"),
        (r"subprocess\.call\s*\(\s*['\"]", Severity.HIGH, "Shell injection risk — use list args"),
        (r"os\.system\s*\(", Severity.HIGH, "os.system() — use subprocess instead"),
        (r"pickle\.loads?\s*\(", Severity.HIGH, "Pickle deserialization — potential RCE"),
        (r"yaml\.load\s*\([^)]*\)", Severity.HIGH, "Unsafe YAML loading — use safe_load()"),
        (r"SELECT\s+.*\s+FROM\s+.*\s+WHERE\s+.*['\"]?\s*\+", Severity.CRITICAL, "Potential SQL injection — use parameterized queries"),
        (r"password\s*=\s*['\"]", Severity.CRITICAL, "Hardcoded password detected"),
        (r"api[_-]?key\s*=\s*['\"]", Severity.CRITICAL, "Hardcoded API key detected"),
        (r"secret\s*=\s*['\"]", Severity.HIGH, "Hardcoded secret detected"),
        (r"verify\s*=\s*False", Severity.MEDIUM, "SSL verification disabled"),
        (r"0\.0\.0\.0", Severity.MEDIUM, "Binding to all interfaces"),
    ]

    PERFORMANCE_PATTERNS = [
        (r"for\s+.*\s+in\s+.*:\s*\n\s+.*\.append\(", Severity.LOW, "Consider list comprehension"),
        (r"\.join\s*\(\s*\[.*for\s+.*\s+in\s+", Severity.LOW, "Generator may be more memory-efficient"),
        (r"time\.sleep\s*\(\s*[^)]*\)", Severity.INFO, "Blocking sleep in potentially async code"),
        (r"requests\.get\s*\(", Severity.LOW, "Consider using async httpx/aiohttp"),
    ]

    STYLE_PATTERNS = [
        (r"^\s*#\s*TODO", Severity.INFO, "TODO comment found"),
        (r"^\s*#\s*FIXME", Severity.LOW, "FIXME comment found"),
        (r"^\s*#\s*HACK", Severity.MEDIUM, "HACK comment found"),
        (r"^\s*pass\s*$", Severity.INFO, "Empty pass statement"),
        (r"except\s*:", Severity.MEDIUM, "Bare except — catch specific exceptions"),
    ]

    def __init__(self, tools: CoderTools):
        self.tools = tools

    async def review_file(self, file_path: str) -> List[CodeIssue]:
        """Review a single file for issues."""
        result = await self.tools.read_file(file_path)
        content = result.get("content", "")
        lines = content.split("\n")

        issues: List[CodeIssue] = []

        # Pattern-based checks
        for pattern, severity, message in self.SECURITY_PATTERNS:
            for i, line in enumerate(lines, 1):
                if re.search(pattern, line, re.IGNORECASE):
                    issues.append(CodeIssue(
                        file_path=file_path,
                        line=i,
                        category=IssueCategory.SECURITY,
                        severity=severity,
                        message=message,
                    ))

        for pattern, severity, message in self.PERFORMANCE_PATTERNS:
            for i, line in enumerate(lines, 1):
                if re.search(pattern, line):
                    issues.append(CodeIssue(
                        file_path=file_path,
                        line=i,
                        category=IssueCategory.PERFORMANCE,
                        severity=severity,
                        message=message,
                    ))

        for pattern, severity, message in self.STYLE_PATTERNS:
            for i, line in enumerate(lines, 1):
                if re.search(pattern, line):
                    issues.append(CodeIssue(
                        file_path=file_path,
                        line=i,
                        category=IssueCategory.STYLE,
                        severity=severity,
                        message=message,
                    ))

        # Python-specific AST checks
        if file_path.endswith(".py"):
            issues.extend(self._review_python_ast(file_path, content))

        # Check for long functions
        issues.extend(self._check_function_length(file_path, lines))

        # Check for long files
        if len(lines) > 500:
            issues.append(CodeIssue(
                file_path=file_path,
                line=1,
                category=IssueCategory.MAINTAINABILITY,
                severity=Severity.LOW,
                message=f"File is {len(lines)} lines — consider splitting into modules",
            ))

        return issues

    @staticmethod
    def _review_python_ast(file_path: str, content: str) -> List[CodeIssue]:
        """Python AST-based code review."""
        issues = []
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return [CodeIssue(
                file_path=file_path,
                line=1,
                category=IssueCategory.CORRECTNESS,
                severity=Severity.CRITICAL,
                message="Syntax error — file cannot be parsed",
            )]

        for node in ast.walk(tree):
            # Check for bare except
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                issues.append(CodeIssue(
                    file_path=file_path,
                    line=node.lineno,
                    category=IssueCategory.CORRECTNESS,
                    severity=Severity.MEDIUM,
                    message="Bare except clause — catch specific exceptions",
                ))

            # Check for mutable default arguments
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for default in node.args.defaults + node.args.kw_defaults:
                    if default is None:
                        continue
                    if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                        issues.append(CodeIssue(
                            file_path=file_path,
                            line=node.lineno,
                            category=IssueCategory.CORRECTNESS,
                            severity=Severity.MEDIUM,
                            message=f"Mutable default argument in '{node.name}()' — use None and assign inside",
                        ))
                        break

            # Check for broad exception handling
            if isinstance(node, ast.ExceptHandler):
                if node.type and isinstance(node.type, ast.Name) and node.type.id == "Exception":
                    # This is acceptable but worth noting
                    pass

        return issues

    @staticmethod
    def _check_function_length(file_path: str, lines: List[str]) -> List[CodeIssue]:
        """Check for overly long functions."""
        issues = []
        func_start = None
        func_name = None
        indent_level = None

        for i, line in enumerate(lines, 1):
            stripped = line.lstrip()
            if stripped.startswith(("def ", "async def ")):
                # End of previous function
                if func_start and i - func_start > 50:
                    issues.append(CodeIssue(
                        file_path=file_path,
                        line=func_start,
                        category=IssueCategory.MAINTAINABILITY,
                        severity=Severity.LOW,
                        message=f"Function '{func_name}' is {i - func_start} lines — consider splitting",
                    ))

                func_start = i
                match = re.match(r"(?:async\s+)?def\s+(\w+)", stripped)
                func_name = match.group(1) if match else "unknown"
                indent_level = len(line) - len(stripped)

        # Check last function
        if func_start and len(lines) - func_start > 50:
            issues.append(CodeIssue(
                file_path=file_path,
                line=func_start,
                category=IssueCategory.MAINTAINABILITY,
                severity=Severity.LOW,
                message=f"Function '{func_name}' is {len(lines) - func_start} lines — consider splitting",
            ))

        return issues

    async def review_diff(self, diff: str) -> List[CodeIssue]:
        """Review a git diff for issues."""
        issues = []
        current_file = None

        for line in diff.split("\n"):
            if line.startswith("+++ b/"):
                current_file = line[6:]
            elif line.startswith("+") and not line.startswith("+++"):
                # Added line — check for issues
                content = line[1:]
                for pattern, severity, message in self.SECURITY_PATTERNS:
                    if re.search(pattern, content, re.IGNORECASE):
                        issues.append(CodeIssue(
                            file_path=current_file or "unknown",
                            line=0,
                            category=IssueCategory.SECURITY,
                            severity=severity,
                            message=f"[in diff] {message}",
                        ))

        return issues


# ═══════════════════════════════════════════════════════════════
# Architecture Documenter
# ═══════════════════════════════════════════════════════════════

class ArchitectureDocumenter:
    """Generates architecture documentation from code analysis."""

    def __init__(self, tools: CoderTools, analyzer: RepoAnalyzer):
        self.tools = tools
        self.analyzer = analyzer

    async def generate_docs(self, root: str = ".", output_path: str = None) -> str:
        """Generate architecture documentation."""
        analysis = await self.analyzer.analyze(root)

        doc_parts = [
            f"# Architecture Documentation",
            f"",
            f"Auto-generated by Rally Coder on {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"",
            f"## Overview",
            f"",
            f"{analysis.structure_summary}",
            f"",
            f"## Languages",
            f"",
        ]

        for lang, count in analysis.languages.items():
            doc_parts.append(f"- **{lang}**: {count} files")

        doc_parts.extend([
            f"",
            f"## Entry Points",
            f"",
        ])
        for ep in analysis.entry_points:
            doc_parts.append(f"- `{ep}`")

        doc_parts.extend([
            f"",
            f"## Dependencies",
            f"",
        ])
        for lang, deps in analysis.dependencies.items():
            doc_parts.append(f"### {lang.title()}")
            for dep in deps[:20]:
                doc_parts.append(f"- {dep}")
            if len(deps) > 20:
                doc_parts.append(f"- ... and {len(deps) - 20} more")
            doc_parts.append("")

        if analysis.test_files:
            doc_parts.extend([
                f"## Test Files",
                f"",
            ])
            for tf in analysis.test_files[:30]:
                doc_parts.append(f"- `{tf}`")

        doc_parts.extend([
            f"",
            f"## Configuration",
            f"",
        ])
        for cf in analysis.config_files:
            doc_parts.append(f"- `{cf}`")

        doc_parts.extend([
            f"",
            f"## File Tree (Top 3 Levels)",
            f"",
            f"```",
        ])
        doc_parts.extend(self._format_tree(analysis.file_tree))
        doc_parts.append("```")

        doc = "\n".join(doc_parts)

        # Save if output path specified
        if output_path:
            await self.tools.write_file(output_path, doc)

        return doc

    @staticmethod
    def _format_tree(nodes: List[dict], prefix: str = "") -> List[str]:
        """Format file tree as text."""
        lines = []
        for i, node in enumerate(nodes):
            is_last = i == len(nodes) - 1
            connector = "└── " if is_last else "├── "
            name = node["name"]
            if node["type"] == "directory":
                name += "/"
            lines.append(f"{prefix}{connector}{name}")

            if "children" in node:
                extension = "    " if is_last else "│   "
                lines.extend(
                    ArchitectureDocumenter._format_tree(node["children"], prefix + extension)
                )

        return lines


# ═══════════════════════════════════════════════════════════════
# Autonomous Coding Agent — Main Class
# ═══════════════════════════════════════════════════════════════

class CoderAgent:
    """
    Autonomous coding agent that follows the Plan → Code → Test → PR loop.

    Usage:
        agent = CoderAgent(tools=my_tools)
        result = await agent.execute("Add user authentication with JWT")
    """

    def __init__(self, tools: CoderTools, repo_root: str = ".", providers=None):
        self.tools = tools
        self.repo_root = os.path.abspath(repo_root)
        self.providers = providers

        # Subsystems
        self.analyzer = RepoAnalyzer(tools)
        self.search = CodeSearchEngine(tools)
        self.git = GitManager(tools, repo_root)
        self.test_runner = TestRunner(tools)
        self.reviewer = CodeReviewer(tools)
        self.documenter = ArchitectureDocumenter(tools, self.analyzer)

        # State
        self._repo_analysis: Optional[RepoAnalysis] = None
        self._current_phase = TaskPhase.ANALYZE
        self._task_history: List[dict] = []
        self._iteration = 0
        self._max_iterations = 10

    @property
    def current_phase(self) -> TaskPhase:
        return self._current_phase

    # ── Main Execution Loop ───────────────────────────────────

    async def execute(self, task: str, auto_commit: bool = True) -> dict:
        """
        Execute an autonomous development task.

        Args:
            task: Description of what to build/fix/change
            auto_commit: Whether to auto-commit changes

        Returns:
            dict with {success, summary, commits, issues, tests}
        """
        Theme.step(f"🚀 Coder Agent: {task[:80]}")

        result = {
            "task": task,
            "success": False,
            "phases_completed": [],
            "summary": "",
            "commits": [],
            "issues_found": [],
            "tests": None,
            "files_changed": [],
        }

        try:
            # Phase 1: ANALYZE
            self._current_phase = TaskPhase.ANALYZE
            Theme.info("📋 Phase 1: Analyzing codebase...")
            analysis = await self._phase_analyze(task)
            self._repo_analysis = analysis
            result["phases_completed"].append("analyze")

            # Phase 2: PLAN
            self._current_phase = TaskPhase.PLAN
            Theme.info("📝 Phase 2: Planning implementation...")
            plan = await self._phase_plan(task, analysis)
            result["phases_completed"].append("plan")

            # Phase 3: CODE (iterative)
            self._current_phase = TaskPhase.CODE
            Theme.info("💻 Phase 3: Writing code...")
            code_result = await self._phase_code(task, plan)
            result["files_changed"] = code_result.get("files_changed", [])
            result["phases_completed"].append("code")

            # Phase 4: TEST
            self._current_phase = TaskPhase.TEST
            Theme.info("✅ Phase 4: Running tests...")
            test_result = await self._phase_test(task)
            result["tests"] = test_result
            result["phases_completed"].append("test")

            # Phase 5: REVIEW
            self._current_phase = TaskPhase.REVIEW
            Theme.info("🔍 Phase 5: Code review...")
            issues = await self._phase_review(result["files_changed"])
            result["issues_found"] = [i.to_dict() for i in issues]
            result["phases_completed"].append("review")

            # Phase 6: COMMIT
            if auto_commit and result["files_changed"]:
                self._current_phase = TaskPhase.COMMIT
                Theme.info("📦 Phase 6: Committing changes...")
                commit = await self._phase_commit(task, result)
                if commit:
                    result["commits"].append(commit)
                result["phases_completed"].append("commit")

            self._current_phase = TaskPhase.DONE
            result["success"] = True
            result["summary"] = self._generate_summary(result)

        except Exception as e:
            logger.error(f"Coder agent error: {e}", exc_info=True)
            result["summary"] = f"Error during {self._current_phase.value}: {e}"
            Theme.error(f"Failed at {self._current_phase.value}: {e}")

        # Record task
        self._task_history.append(result)
        return result

    # ── Phase Implementations ─────────────────────────────────

    async def _phase_analyze(self, task: str) -> RepoAnalysis:
        """Analyze the codebase to understand its structure."""
        analysis = await self.analyzer.analyze(self.repo_root)
        Theme.info(f"  Found: {analysis.structure_summary}")

        # Also search for task-relevant code
        keywords = self._extract_keywords(task)
        for keyword in keywords[:3]:
            matches = await self.search.search_keyword(keyword, self.repo_root)
            if matches:
                Theme.info(f"  Related to '{keyword}': {len(matches)} matches")

        return analysis

    async def _phase_plan(self, task: str, analysis: RepoAnalysis) -> DevelopmentPlan:
        """Create an implementation plan."""
        # Build context for LLM
        context = f"""
Task: {task}

Repository Analysis:
- Languages: {', '.join(analysis.languages.keys())}
- Total files: {analysis.total_files}
- Entry points: {', '.join(analysis.entry_points)}
- Dependencies: {json.dumps({k: v[:10] for k, v in analysis.dependencies.items()}, indent=2)}

Create a detailed implementation plan. For each step, specify:
1. Action (create/modify/delete/test)
2. Target file path
3. Details of what to do

Output as JSON: {{"steps": [...], "files_to_create": [...], "files_to_modify": [...], "tests_to_write": [...], "risks": [...]}}
"""

        messages = [
            {"role": "system", "content": CODER_SYSTEM_PROMPT},
            {"role": "user", "content": context},
        ]

        if self.providers:
            try:
                response = await self.providers.chat(messages)
                plan = self._parse_plan(response)
                if plan:
                    Theme.info(f"  Plan: {len(plan.steps)} steps, {len(plan.files_to_create)} new files")
                    return plan
            except Exception as e:
                logger.warning(f"LLM planning failed: {e}")

        # Fallback: simple plan
        plan = DevelopmentPlan(
            task_description=task,
            steps=[{"action": "implement", "target": "auto", "details": task}],
            estimated_complexity="medium",
        )
        return plan

    async def _phase_code(self, task: str, plan: DevelopmentPlan) -> dict:
        """Execute the coding phase — implement the plan."""
        files_changed = []

        context = f"""
Task: {task}

Plan:
{json.dumps(plan.steps, indent=2)}

Files to create: {plan.files_to_create}
Files to modify: {plan.files_to_modify}

Implement the plan step by step. For each file:
1. Read existing content first (if modifying)
2. Write the code
3. Verify it compiles/parses

Use the tools to actually create/modify files. Output the file paths you changed.
"""

        messages = [
            {"role": "system", "content": CODER_SYSTEM_PROMPT},
            {"role": "user", "content": context},
        ]

        if self.providers:
            try:
                response = await self.providers.chat(messages)
                # Extract file paths from response
                files_changed = self._extract_file_paths(response)
            except Exception as e:
                logger.warning(f"LLM coding failed: {e}")

        return {"files_changed": files_changed}

    async def _phase_test(self, task: str) -> TestResult:
        """Run and/or generate tests."""
        # Try to detect and run existing tests
        framework = await self.test_runner.detect_framework(self.repo_root)

        if framework:
            Theme.info(f"  Running {framework[1]} tests...")
            result = await self.test_runner.run_tests(self.repo_root, framework)

            if result.success:
                Theme.success(f"  Tests passed: {result.passed}/{result.total}")
            else:
                Theme.warning(f"  Tests failed: {result.failed} failed, {result.passed} passed")

            return result
        else:
            Theme.info("  No test framework detected — skipping test run")
            return TestResult(success=True, output="No tests to run")

    async def _phase_review(self, files: List[str]) -> List[CodeIssue]:
        """Review changed files for issues."""
        all_issues: List[CodeIssue] = []

        for file_path in files:
            # Resolve relative to repo root
            full_path = file_path if os.path.isabs(file_path) else os.path.join(self.repo_root, file_path)
            if os.path.exists(full_path):
                issues = await self.reviewer.review_file(full_path)
                all_issues.extend(issues)

        # Also review the diff
        diff = await self.git.diff(staged=True)
        if diff:
            diff_issues = await self.reviewer.review_diff(diff)
            all_issues.extend(diff_issues)

        # Report
        critical = [i for i in all_issues if i.severity == Severity.CRITICAL]
        high = [i for i in all_issues if i.severity == Severity.HIGH]
        medium = [i for i in all_issues if i.severity == Severity.MEDIUM]

        if critical:
            Theme.error(f"  🚨 {len(critical)} critical issues found!")
            for issue in critical[:5]:
                Theme.error(f"    {issue.file_path}:{issue.line} — {issue.message}")
        if high:
            Theme.warning(f"  ⚠️ {len(high)} high-severity issues")
        if medium:
            Theme.info(f"  ℹ️ {len(medium)} medium-severity issues")

        if not critical and not high:
            Theme.success("  ✅ No critical issues found")

        return all_issues

    async def _phase_commit(self, task: str, result: dict) -> Optional[CommitInfo]:
        """Create a git commit with the changes."""
        # Check if there are changes to commit
        status = await self.git.status()
        if status["clean"]:
            Theme.info("  No changes to commit")
            return None

        # Stage all changes
        await self.git.stage_all()

        # Generate commit message
        commit_msg = f"feat: {task[:60]}\n\nImplemented by Rally Coder Agent\n"
        commit_msg += f"Files changed: {len(result.get('files_changed', []))}\n"
        if result.get("tests", {}):
            tests = result["tests"]
            commit_msg += f"Tests: {tests.passed}/{tests.total} passed\n"

        commit = await self.git.commit(commit_msg)
        if commit:
            Theme.success(f"  Committed: {commit.hash} — {commit.message[:50]}")
        return commit

    # ── Public API Methods ────────────────────────────────────

    async def review_pr(self, branch: str = None) -> List[CodeIssue]:
        """Review a PR (diff between branch and main)."""
        if branch:
            diff = await self.tools.exec_command(
                f"git diff main...{branch}",
                cwd=self.repo_root,
            )
        else:
            diff = await self.git.diff()

        return await self.reviewer.review_diff(diff.get("stdout", "") if isinstance(diff, dict) else diff)

    async def reproduce_bug(self, bug_report: str) -> dict:
        """Given a bug report, try to reproduce and diagnose the issue."""
        Theme.step(f"🐛 Bug Reproduction: {bug_report[:60]}")

        # Search for relevant code
        keywords = self._extract_keywords(bug_report)
        relevant_code = {}
        for kw in keywords[:5]:
            matches = await self.search.search_keyword(kw, self.repo_root)
            if matches:
                relevant_code[kw] = matches[:5]

        # Analyze
        context = f"""
Bug Report: {bug_report}

Relevant code found:
{json.dumps(relevant_code, indent=2)}

Steps to diagnose:
1. Identify the likely root cause from the code
2. Write a minimal reproduction case
3. Propose a fix

Use the tools to read relevant files and write a test that reproduces the bug.
"""

        messages = [
            {"role": "system", "content": CODER_SYSTEM_PROMPT},
            {"role": "user", "content": context},
        ]

        if self.providers:
            try:
                response = await self.providers.chat(messages)
                return {"diagnosis": response, "relevant_code": relevant_code}
            except Exception as e:
                return {"error": str(e), "relevant_code": relevant_code}

        return {"relevant_code": relevant_code, "diagnosis": "LLM not available"}

    async def refactor(self, target: str, description: str) -> dict:
        """Refactor code at the specified target."""
        Theme.step(f"🔧 Refactoring: {target}")

        # Read the target
        result = await self.tools.read_file(target)
        content = result.get("content", "")

        context = f"""
Refactor the following code:

File: {target}
Description: {description}

Current code:
```
{content}
```

Refactoring instructions:
1. Read and understand the current code
2. Apply the requested refactoring
3. Ensure the refactored code is equivalent (same behavior)
4. Improve code quality (naming, structure, DRY, etc.)
5. Write the refactored code back

Use the tools to edit the file.
"""

        messages = [
            {"role": "system", "content": CODER_SYSTEM_PROMPT},
            {"role": "user", "content": context},
        ]

        if self.providers:
            try:
                response = await self.providers.chat(messages)
                return {"result": response, "file": target}
            except Exception as e:
                return {"error": str(e), "file": target}

        return {"error": "LLM not available", "file": target}

    async def generate_tests(self, target: str) -> str:
        """Generate tests for a file or module."""
        Theme.step(f"🧪 Generating tests: {target}")

        result = await self.tools.read_file(target)
        content = result.get("content", "")

        context = f"""
Generate comprehensive tests for:

File: {target}

Code:
```
{content}
```

Requirements:
1. Test all public functions/methods
2. Test edge cases and error conditions
3. Use the project's existing test framework
4. Follow existing test patterns in the project
5. Aim for high coverage of the main code paths

Write the test file using the tools.
"""

        messages = [
            {"role": "system", "content": CODER_SYSTEM_PROMPT},
            {"role": "user", "content": context},
        ]

        if self.providers:
            try:
                response = await self.providers.chat(messages)
                return response
            except Exception as e:
                return f"Error: {e}"

        return "LLM not available"

    async def document_code(self, target: str = None) -> str:
        """Generate documentation for code."""
        if target:
            return await self.documenter.generate_docs(self.repo_root, target)
        return await self.documenter.generate_docs(self.repo_root)

    async def search_code(self, query: str) -> List[dict]:
        """Search code by semantic meaning (keyword-based fallback)."""
        return await self.search.search_keyword(query, self.repo_root)

    async def find_symbol(self, symbol: str) -> List[dict]:
        """Find definitions of a symbol."""
        return await self.search.search_symbol(symbol, self.repo_root)

    async def analyze_deps(self) -> dict:
        """Analyze project dependencies."""
        if not self._repo_analysis:
            self._repo_analysis = await self.analyzer.analyze(self.repo_root)
        return self._repo_analysis.dependencies

    # ── Multi-Agent Collaboration ─────────────────────────────

    async def collaborative_task(self, task: str, agent_roles: List[str] = None) -> dict:
        """
        Execute a task using multiple specialized perspectives.

        agent_roles: e.g. ["architect", "developer", "reviewer", "tester"]
        """
        if agent_roles is None:
            agent_roles = ["architect", "developer", "reviewer"]

        results = {}
        for role in agent_roles:
            context = f"""
You are acting as a {role} in a collaborative development session.

Task: {task}

Previous perspectives:
{json.dumps(results, indent=2)}

Provide your {role}-specific analysis and recommendations.
"""

            messages = [
                {"role": "system", "content": CODER_SYSTEM_PROMPT},
                {"role": "user", "content": context},
            ]

            if self.providers:
                try:
                    response = await self.providers.chat(messages)
                    results[role] = response
                except Exception as e:
                    results[role] = f"Error: {e}"

        return results

    # ── Helpers ───────────────────────────────────────────────

    @staticmethod
    def _extract_keywords(text: str) -> List[str]:
        """Extract meaningful keywords from text."""
        # Remove common stop words
        stop_words = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "being", "have", "has", "had", "do", "does", "did", "will",
            "would", "could", "should", "may", "might", "can", "to",
            "of", "in", "for", "on", "with", "at", "by", "from",
            "and", "or", "but", "not", "this", "that", "it", "i",
            "we", "you", "they", "he", "she", "my", "your", "our",
            "add", "create", "make", "fix", "update", "change", "implement",
        }
        words = re.findall(r"\b[a-zA-Z_]\w{2,}\b", text.lower())
        return [w for w in words if w not in stop_words][:10]

    @staticmethod
    def _parse_plan(response: str) -> Optional[DevelopmentPlan]:
        """Parse an LLM response into a DevelopmentPlan."""
        try:
            # Try to extract JSON from response
            json_match = re.search(r"\{.*\}", response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                return DevelopmentPlan(
                    task_description=data.get("task", ""),
                    steps=data.get("steps", []),
                    files_to_create=data.get("files_to_create", []),
                    files_to_modify=data.get("files_to_modify", []),
                    tests_to_write=data.get("tests_to_write", []),
                    estimated_complexity=data.get("estimated_complexity", "medium"),
                    risks=data.get("risks", []),
                )
        except (json.JSONDecodeError, AttributeError):
            pass
        return None

    @staticmethod
    def _extract_file_paths(response: str) -> List[str]:
        """Extract file paths from an LLM response."""
        paths = []
        # Look for file paths in code blocks or mentions
        patterns = [
            r"`([a-zA-Z0-9_/.\-]+\.[a-zA-Z]{1,10})`",
            r"(?:file|path|created?|modified?|wrote):\s*([^\s,]+)",
            r"(?:write_file|edit_file|read_file)\([^)]*['\"]([^'\"]+)['\"]",
        ]
        for pattern in patterns:
            matches = re.findall(pattern, response)
            paths.extend(matches)

        # Deduplicate and filter
        seen = set()
        filtered = []
        for p in paths:
            if p not in seen and "." in p and not p.startswith("http"):
                seen.add(p)
                filtered.append(p)
        return filtered

    def _generate_summary(self, result: dict) -> str:
        """Generate a human-readable summary of the task result."""
        parts = [f"## Task: {result['task'][:80]}"]
        parts.append(f"**Status:** {'✅ Success' if result['success'] else '❌ Failed'}")
        parts.append(f"**Phases:** {', '.join(result.get('phases_completed', []))}")

        if result.get("files_changed"):
            parts.append(f"**Files changed:** {len(result['files_changed'])}")
            for f in result["files_changed"][:10]:
                parts.append(f"  - `{f}`")

        if result.get("tests"):
            tests = result["tests"]
            parts.append(f"**Tests:** {tests.passed}/{tests.total} passed ({tests.duration_seconds:.1f}s)")

        if result.get("issues_found"):
            issues = result["issues_found"]
            parts.append(f"**Issues:** {len(issues)} found")
            for cat in set(i["category"] for i in issues):
                count = sum(1 for i in issues if i["category"] == cat)
                parts.append(f"  - {cat}: {count}")

        if result.get("commits"):
            for c in result["commits"]:
                parts.append(f"**Commit:** `{c.hash}` — {c.message[:50]}")

        return "\n".join(parts)

    def get_status(self) -> dict:
        """Get current agent status."""
        return {
            "phase": self._current_phase.value,
            "repo_root": self.repo_root,
            "tasks_completed": len(self._task_history),
            "repo_analysis": self._repo_analysis.to_dict() if self._repo_analysis else None,
        }
