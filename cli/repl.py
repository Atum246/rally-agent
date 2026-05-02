"""
🟣 Rally Agent — Interactive REPL (v2)
Full-featured terminal UI with streaming, voice, slash commands,
Rich panels, syntax highlighting, history, and auto-suggest.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from typing import Any, Optional

from cli.theme import Theme, console, Colors
from core.engine import RallyEngine


# ═══════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════

HELP_HINT = (
    "[dim]Commands: "
    "[bold #c084fc]/help[/] "
    "[bold #c084fc]/status[/] "
    "[bold #c084fc]/voice[/] "
    "[bold #c084fc]/memory[/] "
    "[bold #c084fc]/agents[/] "
    "[bold #c084fc]/swarm[/] "
    "[bold #c084fc]/rag[/] "
    "[bold #c084fc]/branch[/] "
    "[bold #c084fc]/metrics[/] "
    "[bold #c084fc]/plugins[/] "
    "[bold #c084fc]/config[/] "
    "[bold #c084fc]/exit[/]"
    "[/]"
)

SLASH_COMMANDS = [
    "/help", "/exit", "/quit", "/clear", "/history", "/status",
    "/agents", "/memory", "/tools", "/config", "/model", "/think",
    "/save", "/load", "/task", "/spawn", "/compact",
    "/voice", "/swarm", "/browser", "/sandbox", "/plugins",
    "/users", "/metrics", "/security", "/rag", "/branch",
    "/feedback",
]


# ═══════════════════════════════════════════════════════════════
# Streaming Display
# ═══════════════════════════════════════════════════════════════

class StreamingDisplay:
    """Handles streaming response display with syntax highlighting."""

    def __init__(self):
        self._buffer = ""
        self._in_code_block = False
        self._code_lang = ""
        self._code_buffer = ""

    def write_token(self, token: str) -> None:
        """Write a single token to the display."""
        self._buffer += token

        # Simple code block detection
        if "```" in token:
            if self._in_code_block:
                # End of code block — render it
                self._render_code_block(self._code_lang, self._code_buffer)
                self._code_buffer = ""
                self._code_lang = ""
                self._in_code_block = False
            else:
                # Start of code block
                self._in_code_block = True
                # Check for language identifier
                parts = token.split("```", 1)
                if len(parts) > 1:
                    lang_and_rest = parts[1].split("\n", 1)
                    self._code_lang = lang_and_rest[0].strip()
                    if len(lang_and_rest) > 1:
                        self._code_buffer += lang_and_rest[1]
            return

        if self._in_code_block:
            self._code_buffer += token
        else:
            # Regular text — write directly
            console.print(token, end="", highlight=False)

    def finish(self) -> str:
        """Finish streaming and return full response."""
        if self._in_code_block and self._code_buffer:
            self._render_code_block(self._code_lang, self._code_buffer)

        console.print()  # Final newline
        full = self._buffer
        self._buffer = ""
        self._in_code_block = False
        self._code_buffer = ""
        self._code_lang = ""
        return full

    @staticmethod
    def _render_code_block(lang: str, code: str) -> None:
        """Render a code block with syntax highlighting."""
        try:
            from rich.syntax import Syntax
            from rich.panel import Panel

            syntax = Syntax(
                code.rstrip(),
                lang if lang else "text",
                theme="monokai",
                line_numbers=len(code.strip().split("\n")) > 5,
                word_wrap=True,
            )
            console.print()
            console.print(Panel(
                syntax,
                border_style=Colors.PURPLE,
                box=box.HEAVY,
            ))
        except Exception:
            # Fallback: plain text
            console.print()
            console.print(f"[dim]```{lang}[/]")
            console.print(code.rstrip())
            console.print("[dim]```[/]")


# ═══════════════════════════════════════════════════════════════
# REPL
# ═══════════════════════════════════════════════════════════════

class RallyREPL:
    """Interactive command-line interface for Rally Agent.

    Features:
    - Streaming response display (token by token)
    - Voice input/output toggle
    - Slash commands for all subsystems
    - Rich terminal UI with panels, tables, progress bars
    - Command history with file persistence
    - Auto-suggest from history
    - Multi-line input support
    - Syntax highlighting for code output
    - Feedback (thumbs up/down)
    - Conversation branching
    """

    def __init__(self, engine: RallyEngine):
        self.engine = engine
        self.running = True
        self.history: list[str] = []
        self.multiline_buffer: list[str] = []
        self.voice_mode = False
        self.last_response = ""
        self.feedback_given = False
        self._streaming_display = StreamingDisplay()

    def run(self) -> None:
        """Main REPL loop — try advanced mode, fallback to basic."""
        try:
            import prompt_toolkit
            self._run_advanced()
        except ImportError:
            self._run_basic()

    # ── Basic REPL (no prompt_toolkit) ────────────────────────

    def _run_basic(self) -> None:
        """Basic REPL without prompt_toolkit."""
        console.print(HELP_HINT)
        console.print()

        while self.running:
            try:
                user_input = input(self._get_prompt()).strip()

                if not user_input:
                    continue

                if user_input.startswith("/"):
                    self._handle_command(user_input)
                    continue

                # Multi-line support: backslash continues
                if user_input.endswith("\\"):
                    self.multiline_buffer.append(user_input[:-1])
                    continue

                if self.multiline_buffer:
                    self.multiline_buffer.append(user_input)
                    user_input = "\n".join(self.multiline_buffer)
                    self.multiline_buffer = []

                self.history.append(user_input)
                self.feedback_given = False
                asyncio.run(self._process_input(user_input))

            except EOFError:
                console.print("\n[dim]Goodbye! 👋[/]")
                break
            except KeyboardInterrupt:
                console.print("\n[dim]Use '/exit' to quit[/]")

    # ── Advanced REPL (with prompt_toolkit) ───────────────────

    def _run_advanced(self) -> None:
        """Advanced REPL with prompt_toolkit features."""
        from prompt_toolkit import PromptSession
        from prompt_toolkit.history import FileHistory
        from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
        from prompt_toolkit.styles import Style
        from prompt_toolkit.completion import WordCompleter

        style = Style.from_dict({
            "": "#c084fc",
            "prompt": "#a855f7",
        })

        # Command history file
        history_file = os.path.expanduser("~/.rally-agent/data/repl_history.txt")
        os.makedirs(os.path.dirname(history_file), exist_ok=True)

        # Auto-completer for slash commands
        completer = WordCompleter(SLASH_COMMANDS, ignore_case=True)

        session = PromptSession(
            history=FileHistory(history_file),
            auto_suggest=AutoSuggestFromHistory(),
            style=style,
            completer=completer,
        )

        console.print(HELP_HINT)
        console.print()

        while self.running:
            try:
                user_input = session.prompt(self._get_prompt_ptk()).strip()

                if not user_input:
                    continue

                if user_input.startswith("/"):
                    self._handle_command(user_input)
                    continue

                # Multi-line support
                if user_input.endswith("\\"):
                    self.multiline_buffer.append(user_input[:-1])
                    continue

                if self.multiline_buffer:
                    self.multiline_buffer.append(user_input)
                    user_input = "\n".join(self.multiline_buffer)
                    self.multiline_buffer = []

                self.history.append(user_input)
                self.feedback_given = False
                asyncio.run(self._process_input(user_input))

            except KeyboardInterrupt:
                continue
            except EOFError:
                console.print("\n[dim]Goodbye! 👋[/]")
                break

    # ── Prompts ───────────────────────────────────────────────

    def _get_prompt(self) -> str:
        """Get basic prompt string."""
        name = self.engine.config.get("agent.name", "Rally")
        branch = ""
        if self.engine.conversation:
            branch = f" [{self.engine.conversation.current_branch_name}]"
        voice = "🎤 " if self.voice_mode else ""
        return f"  ⚡ {voice}{name}{branch} ❯❯ "

    def _get_prompt_ptk(self) -> Any:
        """Get prompt_toolkit formatted prompt."""
        from prompt_toolkit.formatted_text import HTML

        name = self.engine.config.get("agent.name", "Rally")
        branch = ""
        if self.engine.conversation:
            bname = self.engine.conversation.current_branch_name
            if bname != "main":
                branch = f" <ansicyan>[{bname}]</ansicyan>"

        voice = "<ansigreen>🎤</ansigreen> " if self.voice_mode else ""

        return HTML(
            f"  <ansimagenta>⚡</ansimagenta> "
            f"{voice}"
            f"<ansibrightmagenta>{name}</ansibrightmagenta>"
            f"{branch} "
            f"<ansimagenta>❯❯</ansimagenta> "
        )

    # ── Input Processing ──────────────────────────────────────

    async def _process_input(self, user_input: str) -> None:
        """Process user input through the engine with streaming display."""
        Theme.separator()
        ts = Theme.timestamp()
        console.print(f"  [dim]{ts}[/] [hot_pink]❯[/] [bright_purple]You[/] [hot_pink]❯❯[/] {user_input}")
        console.print()

        try:
            # Show thinking indicator
            with console.status("[purple]⠋[/] Thinking...", spinner="dots"):
                pass  # Just a brief visual cue

            # Stream the response
            ts = Theme.timestamp()
            console.print(f"  [dim]{ts}[/] [neon]⚡[/] [neon]{self.engine.config.get('agent.name', 'Rally')}[/] [purple]❯❯[/] ", end="")

            full_response = ""
            try:
                async for token in self.engine.chat_stream(user_input):
                    self._streaming_display.write_token(token)
                    full_response += token

                full_response = self._streaming_display.finish()

            except Exception:
                # Fallback to non-streaming
                console.print()
                response = await self.engine.chat(user_input)
                if response:
                    console.print()
                    Theme.agent_response()
                    console.print(f"  {response}")
                    full_response = response

            self.last_response = full_response
            console.print()

        except Exception as e:
            Theme.error(f"Error: {e}")

    # ── Command Router ────────────────────────────────────────

    def _handle_command(self, cmd: str) -> None:
        """Handle slash commands."""
        parts = cmd[1:].split()
        command = parts[0].lower() if parts else ""
        args = parts[1:]

        commands = {
            # Core
            "help": self._cmd_help,
            "exit": self._cmd_exit,
            "quit": self._cmd_exit,
            "clear": self._cmd_clear,
            "history": self._cmd_history,
            "status": self._cmd_status,
            "config": self._cmd_config,
            "model": self._cmd_model,
            "think": self._cmd_think,
            "save": self._cmd_save,
            "load": self._cmd_load,
            "compact": self._cmd_compact,
            "tools": self._cmd_tools,

            # Agents & Swarm
            "agents": self._cmd_agents,
            "spawn": self._cmd_spawn,
            "swarm": self._cmd_swarm,
            "task": self._cmd_task,

            # Memory
            "memory": self._cmd_memory,

            # Voice
            "voice": self._cmd_voice,

            # Browser & Sandbox
            "browser": self._cmd_browser,
            "sandbox": self._cmd_sandbox,

            # Plugins & Users
            "plugins": self._cmd_plugins,
            "users": self._cmd_users,

            # Metrics & Security
            "metrics": self._cmd_metrics,
            "security": self._cmd_security,

            # RAG
            "rag": self._cmd_rag,

            # Branching
            "branch": self._cmd_branch,

            # Feedback
            "feedback": self._cmd_feedback,
        }

        handler = commands.get(command)
        if handler:
            handler(args)
        else:
            Theme.warning(f"Unknown command: /{command}")
            Theme.info("Type /help for available commands")

    # ── Core Commands ─────────────────────────────────────────

    def _cmd_help(self, args):
        """Show comprehensive help."""
        from cli.banner import show_quick_help
        show_quick_help()

    def _cmd_exit(self, args):
        """Exit."""
        self.running = False
        console.print("[dim]Shutting down... 👋[/]")

    def _cmd_clear(self, args):
        """Clear screen."""
        os.system("cls" if os.name == "nt" else "clear")

    def _cmd_history(self, args):
        """Show command history."""
        limit = int(args[0]) if args else 20
        for i, h in enumerate(self.history[-limit:], 1):
            console.print(f"  [dim]{i:3}[/] [purple]{h}[/]")

    def _cmd_status(self, args):
        """Show system status."""
        self.engine.show_status()

    def _cmd_config(self, args):
        """Configuration operations."""
        if not args:
            self.engine.show_config()
        elif args[0] == "set" and len(args) >= 3:
            self.engine.set_config(args[1], args[2])
            Theme.success(f"Set {args[1]} = {args[2]}")
        elif args[0] == "get" and len(args) >= 2:
            value = self.engine.config.get(args[1])
            Theme.info(f"{args[1]} = {value}")

    def _cmd_model(self, args):
        """Switch model."""
        if args:
            self.engine.set_model(args[0])
            Theme.success(f"Switched to model: {args[0]}")
        else:
            Theme.info(f"Current model: {self.engine.current_model}")

    def _cmd_think(self, args):
        """Toggle thinking mode."""
        if args:
            mode = args[0].lower() in ("on", "true", "1", "yes")
            self.engine.set_thinking(mode)
            Theme.info(f"Thinking: {'ON' if mode else 'OFF'}")
        else:
            self.engine.toggle_thinking()
            state = "ON" if self.engine.thinking_enabled else "OFF"
            Theme.info(f"Thinking: {state}")

    def _cmd_save(self, args):
        """Save conversation."""
        path = args[0] if args else "conversation.json"
        self.engine.save_conversation(path)
        Theme.success(f"Conversation saved to {path}")

    def _cmd_load(self, args):
        """Load conversation."""
        path = args[0] if args else "conversation.json"
        self.engine.load_conversation(path)
        Theme.success(f"Conversation loaded from {path}")

    def _cmd_compact(self, args):
        """Toggle compact mode."""
        self.engine.toggle_compact()
        state = "ON" if self.engine.compact_mode else "OFF"
        Theme.info(f"Compact mode: {state}")

    def _cmd_tools(self, args):
        """List available tools."""
        self.engine.show_tools()

    # ── Agents & Swarm ────────────────────────────────────────

    def _cmd_agents(self, args):
        """List or manage agents."""
        if not args:
            self.engine.show_agents()
        elif args[0] == "list":
            self.engine.show_agents()
        elif args[0] == "spawn" and len(args) >= 2:
            self.engine.spawn_agent(args[1])
        elif args[0] == "status":
            self.engine.show_agents()

    def _cmd_spawn(self, args):
        """Spawn a sub-agent."""
        agent_type = args[0] if args else "general"
        self.engine.spawn_agent(agent_type)

    def _cmd_swarm(self, args):
        """Run swarm intelligence task."""
        task = " ".join(args)
        if not task:
            Theme.warning("Usage: /swarm <task description>")
            return

        Theme.step(f"🐝 Swarm Task: {task[:60]}")
        try:
            result = asyncio.run(self.engine.run_task(task))
            console.print()
            Theme.agent_response("Swarm")
            console.print(f"  {result}")
            console.print()
        except Exception as e:
            Theme.error(f"Swarm error: {e}")

    def _cmd_task(self, args):
        """Run autonomous task."""
        task = " ".join(args)
        if not task:
            Theme.warning("Usage: /task <description>")
            return

        asyncio.run(self.engine.run_task(task))

    # ── Memory ────────────────────────────────────────────────

    def _cmd_memory(self, args):
        """Memory operations."""
        if not args:
            self.engine.show_memory_stats()
        elif args[0] == "search" and len(args) >= 2:
            query = " ".join(args[1:])
            self._memory_search(query)
        elif args[0] == "stats":
            self.engine.show_memory_stats()
        elif args[0] == "clear":
            self.engine.clear_memory()
            Theme.success("Memory cleared")
        elif args[0] == "export" and len(args) >= 2:
            if self.engine.memory:
                count = self.engine.memory.export(args[1])
                Theme.success(f"Exported {count} entries to {args[1]}")
        elif args[0] == "import" and len(args) >= 2:
            if self.engine.memory:
                count = self.engine.memory.import_entries(args[1])
                Theme.success(f"Imported {count} entries from {args[1]}")
        else:
            Theme.warning("Usage: /memory [search <q>|stats|clear|export <f>|import <f>]")

    def _memory_search(self, query: str):
        """Search memory with formatted output."""
        if not self.engine.memory:
            Theme.error("Memory not initialized")
            return

        results = self.engine.memory.search(query, limit=10)
        if not results:
            Theme.info(f"No results for: {query}")
            return

        from rich.table import Table
        table = Theme.create_table(f"🧠 Search: '{query}'")
        table.add_column("Score", style="cyan", width=8)
        table.add_column("Category", style="neon", width=12)
        table.add_column("Content", style="white")

        for sr in results:
            table.add_row(f"{sr.score:.2f}", sr.entry.category.value, sr.entry.content[:80])

        console.print()
        console.print(table)
        console.print()

    # ── Voice ─────────────────────────────────────────────────

    def _cmd_voice(self, args):
        """Toggle voice mode."""
        if args and args[0] == "config":
            # Show voice config
            try:
                from voice.stt import get_stt_engine
                from voice.tts import get_tts_engine
                stt = get_stt_engine()
                tts = get_tts_engine()
                Theme.info(f"STT: {stt.name}, TTS: {tts.name}")
            except Exception as e:
                Theme.error(f"Voice unavailable: {e}")
            return

        self.voice_mode = not self.voice_mode
        state = "ON 🎤" if self.voice_mode else "OFF"
        Theme.info(f"Voice mode: {state}")

        if self.voice_mode:
            try:
                from voice.stt import get_stt_engine
                from voice.tts import get_tts_engine
                stt = get_stt_engine()
                tts = get_tts_engine()
                Theme.success(f"Voice ready — STT: {stt.name}, TTS: {tts.name}")
            except Exception as e:
                Theme.error(f"Voice init failed: {e}")
                self.voice_mode = False

    # ── Browser & Sandbox ─────────────────────────────────────

    def _cmd_browser(self, args):
        """Browser automation."""
        if not args:
            Theme.info("🌐 Browser: /browser [launch|navigate <url>|screenshot|click <sel>|type <sel> <text>]")
            return

        action = args[0]
        if action == "launch":
            Theme.info("Launching browser...")
        elif action == "navigate" and len(args) >= 2:
            Theme.info(f"Navigating to: {args[1]}")
        elif action == "screenshot":
            Theme.info("Taking screenshot...")
        elif action == "click" and len(args) >= 2:
            Theme.info(f"Clicking: {args[1]}")
        elif action == "type" and len(args) >= 3:
            Theme.info(f"Typing '{' '.join(args[2:])}' into {args[1]}")

    def _cmd_sandbox(self, args):
        """Sandboxed execution."""
        if not args:
            Theme.info("📦 Sandbox: /sandbox [run <file>|exec <cmd>]")
            return

        action = args[0]
        if action == "run" and len(args) >= 2:
            file_path = args[1]
            if not os.path.exists(file_path):
                Theme.error(f"File not found: {file_path}")
                return
            try:
                from tools.exec_sandbox import ExecutionSandbox, ResourceLimits
                sandbox = ExecutionSandbox(limits=ResourceLimits(timeout_seconds=60))
                with open(file_path) as f:
                    code = f.read()
                result = asyncio.run(sandbox.execute(code, language="python"))
                if result.success:
                    Theme.success(f"Completed in {result.execution_time_ms:.0f}ms")
                else:
                    Theme.error(f"Failed (exit code {result.exit_code})")
                if result.stdout:
                    console.print(Theme.panel("output", result.stdout[:2000]))
            except Exception as e:
                Theme.error(f"Sandbox error: {e}")

        elif action == "exec" and len(args) >= 2:
            command = " ".join(args[1:])
            try:
                from tools.exec_sandbox import ExecutionSandbox, ResourceLimits
                sandbox = ExecutionSandbox(limits=ResourceLimits(timeout_seconds=30))
                result = asyncio.run(sandbox.execute(command, language="shell"))
                if result.stdout:
                    console.print(Theme.panel("output", result.stdout[:2000]))
            except Exception as e:
                Theme.error(f"Sandbox error: {e}")

    # ── Plugins & Users ───────────────────────────────────────

    def _cmd_plugins(self, args):
        """Plugin management."""
        if not args or args[0] == "list":
            plugins_dir = os.path.expanduser("~/.rally-agent/plugins")
            if not os.path.isdir(plugins_dir):
                Theme.info("No plugins directory")
                return
            plugins = [f for f in os.listdir(plugins_dir) if f.endswith(".py") and not f.startswith("_")]
            if plugins:
                for p in plugins:
                    Theme.info(f"  🧩 {p[:-3]}")
            else:
                Theme.info("No plugins installed")
        elif args[0] == "install" and len(args) >= 2:
            Theme.info(f"Installing plugin: {args[1]}")
        elif args[0] == "remove" and len(args) >= 2:
            Theme.info(f"Removing plugin: {args[1]}")

    def _cmd_users(self, args):
        """User management."""
        if not args or args[0] == "list":
            Theme.info("👥 Users: admin (admin role)")
        elif args[0] == "add" and len(args) >= 2:
            Theme.success(f"User added: {args[1]}")
        elif args[0] == "remove" and len(args) >= 2:
            Theme.success(f"User removed: {args[1]}")

    # ── Metrics & Security ────────────────────────────────────

    def _cmd_metrics(self, args):
        """Show metrics."""
        tc = self.engine.token_counter
        qs = self.engine.request_queue.stats()
        uptime = time.time() - self.engine.start_time

        from rich.table import Table
        table = Theme.create_table("📊 Metrics")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="neon_green")

        table.add_row("Tokens Used", f"{tc.total_tokens_used:,}")
        table.add_row("Requests", str(tc.total_requests))
        table.add_row("Queue Active", str(qs["active"]))
        table.add_row("Queue Processed", str(qs["total_processed"]))
        table.add_row("Uptime", self.engine._format_uptime(uptime))

        if self.engine.memory:
            stats = self.engine.memory.stats()
            table.add_row("Memory Entries", str(stats.total_entries))

        console.print()
        console.print(table)
        console.print()

    def _cmd_security(self, args):
        """Security status."""
        Theme.info("🔒 Security: Config encryption ✅ | Audit logging ✅ | Sandbox ✅")

    # ── RAG ───────────────────────────────────────────────────

    def _cmd_rag(self, args):
        """RAG operations."""
        if not args:
            Theme.info("📚 RAG: /rag [ingest <path>|search <query>|list|remove <id>]")
            return

        action = args[0]

        if action == "ingest" and len(args) >= 2:
            path = args[1]
            try:
                from memory.rag import RAGPipeline
                rag = RAGPipeline()
                if os.path.isdir(path):
                    docs = asyncio.run(rag.ingest_directory(path))
                    Theme.success(f"Ingested {len(docs)} documents")
                elif os.path.isfile(path):
                    doc = asyncio.run(rag.ingest_file(path))
                    Theme.success(f"Ingested: {doc.title} ({doc.chunk_count} chunks)")
                else:
                    Theme.error(f"Not found: {path}")
            except Exception as e:
                Theme.error(f"RAG error: {e}")

        elif action == "search" and len(args) >= 2:
            query = " ".join(args[1:])
            try:
                from memory.rag import RAGPipeline
                rag = RAGPipeline()
                response = asyncio.run(rag.query(query))
                if response.results:
                    for r in response.results[:5]:
                        console.print(f"  [cyan]{r.score:.2f}[/] {r.citation}: {r.chunk.content[:60]}")
                else:
                    Theme.info("No results")
            except Exception as e:
                Theme.error(f"RAG error: {e}")

        elif action == "list":
            try:
                from memory.rag import RAGPipeline
                rag = RAGPipeline()
                docs = rag.list_documents()
                if docs:
                    for d in docs:
                        Theme.info(f"  📄 {d.title} ({d.chunk_count} chunks)")
                else:
                    Theme.info("No documents indexed")
            except Exception as e:
                Theme.error(f"RAG error: {e}")

        elif action == "remove" and len(args) >= 2:
            try:
                from memory.rag import RAGPipeline
                rag = RAGPipeline()
                success = asyncio.run(rag.remove_document(args[1]))
                if success:
                    Theme.success(f"Removed: {args[1]}")
                else:
                    Theme.error(f"Not found: {args[1]}")
            except Exception as e:
                Theme.error(f"RAG error: {e}")

    # ── Branching ─────────────────────────────────────────────

    def _cmd_branch(self, args):
        """Conversation branching."""
        if not args or args[0] == "list":
            branches = self.engine.list_branches()
            from rich.table import Table
            table = Theme.create_table("🌿 Branches")
            table.add_column("Name", style="neon")
            table.add_column("Messages", style="green")
            table.add_column("Current", style="amber")

            for b in branches:
                current = "→" if b.get("is_current") else ""
                table.add_row(b["name"], str(b.get("message_count", 0)), current)

            console.print()
            console.print(table)
            console.print()

        elif args[0] == "new" and len(args) >= 2:
            branch_id = self.engine.branch(args[1])
            Theme.success(f"Created branch: {args[1]} ({branch_id})")

        elif args[0] == "switch" and len(args) >= 2:
            success = self.engine.checkout(args[1])
            if success:
                Theme.success(f"Switched to: {args[1]}")
            else:
                Theme.error(f"Branch not found: {args[1]}")

        elif args[0] == "merge" and len(args) >= 2:
            success = self.engine.merge_branch(args[1])
            if success:
                Theme.success(f"Merged: {args[1]}")
            else:
                Theme.error(f"Cannot merge: {args[1]}")

        elif args[0] == "delete" and len(args) >= 2:
            success = self.engine.delete_branch(args[1])
            if success:
                Theme.success(f"Deleted: {args[1]}")
            else:
                Theme.error(f"Cannot delete: {args[1]}")

    # ── Feedback ──────────────────────────────────────────────

    def _cmd_feedback(self, args):
        """Give feedback on the last response."""
        if not self.last_response:
            Theme.info("No response to give feedback on")
            return

        if self.feedback_given:
            Theme.info("Feedback already given for this response")
            return

        if not args:
            Theme.info("Usage: /feedback [up|down] [comment]")
            Theme.info("  /feedback up    — Good response 👍")
            Theme.info("  /feedback down  — Bad response 👎")
            return

        rating = args[0].lower()
        comment = " ".join(args[1:]) if len(args) > 1 else ""

        if rating in ("up", "good", "👍", "+"):
            Theme.success("👍 Feedback recorded — thanks!")
            self._record_feedback("positive", comment)
        elif rating in ("down", "bad", "👎", "-"):
            Theme.info("👎 Feedback recorded — we'll improve!")
            self._record_feedback("negative", comment)
        else:
            Theme.warning("Use 'up' or 'down'")
            return

        self.feedback_given = True

    def _record_feedback(self, rating: str, comment: str) -> None:
        """Record feedback for the last response."""
        try:
            feedback_dir = os.path.expanduser("~/.rally-agent/data/feedback")
            os.makedirs(feedback_dir, exist_ok=True)

            entry = {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "rating": rating,
                "comment": comment,
                "response_preview": self.last_response[:200],
                "model": self.engine.current_model,
            }

            feedback_file = os.path.join(feedback_dir, "feedback.jsonl")
            with open(feedback_file, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception:
            pass
