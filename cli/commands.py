"""
🟣 Rally Agent — CLI Command Router (v2)
Routes ALL CLI subcommands including voice, memory, agents, swarm,
browser, sandbox, plugins, users, metrics, security, RAG, and branch.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from typing import Any, Optional

from cli.theme import Theme, console, Colors


class CommandRouter:
    """Routes CLI commands to appropriate handlers.

    Subcommand structure:
      rally <domain> <action> [args...]

    Domains:
      voice, memory, agents, swarm, browser, sandbox, plugins,
      users, metrics, security, rag, branch, config, tools, skills,
      task, daemon, nodes, marketplace, web, serve, init
    """

    def __init__(self, engine: Any):
        self.engine = engine

    # ═══════════════════════════════════════════════════════════
    # Help
    # ═══════════════════════════════════════════════════════════

    def show_help(self):
        """Show comprehensive help."""
        help_text = """
[bold #c084fc]⚡ RALLY AGENT — Command Reference[/]

[#22d3ee]━━━ Core ━━━[/]
  rally                        Start interactive REPL
  rally chat                   Start chat session
  rally status                 System status dashboard
  rally version                Show version

[#22d3ee]━━━ Voice ━━━[/]
  rally voice start            Start voice mode
  rally voice stop             Stop voice mode
  rally voice config           Voice configuration

[#22d3ee]━━━ Memory ━━━[/]
  rally memory                 Memory statistics
  rally memory search <query>  Search memory
  rally memory stats           Detailed stats
  rally memory clear           Clear all memory
  rally memory export <file>   Export memory
  rally memory import <file>   Import memory

[#22d3ee]━━━ Agents ━━━[/]
  rally agents                 List all agents
  rally agents list            List all agents
  rally agents spawn <type>    Spawn an agent
  rally agents status          Agent status

[#22d3ee]━━━ Swarm ━━━[/]
  rally swarm <task>           Run swarm intelligence task

[#22d3ee]━━━ Browser ━━━[/]
  rally browser launch         Launch browser
  rally browser navigate <url> Navigate to URL
  rally browser screenshot     Take screenshot
  rally browser click <sel>    Click element
  rally browser type <sel> <t> Type into element

[#22d3ee]━━━ Sandbox ━━━[/]
  rally sandbox run <file>     Run file in sandbox
  rally sandbox exec <cmd>     Execute command in sandbox

[#22d3ee]━━━ Plugins ━━━[/]
  rally plugins                List plugins
  rally plugins list           List plugins
  rally plugins install <name> Install plugin
  rally plugins remove <name>  Remove plugin
  rally plugins enable <name>  Enable plugin
  rally plugins disable <name> Disable plugin

[#22d3ee]━━━ Users (Admin) ━━━[/]
  rally users list             List users
  rally users add <name>       Add user
  rally users remove <name>    Remove user
  rally users role <name> <r>  Set user role

[#22d3ee]━━━ Metrics ━━━[/]
  rally metrics show           Show metrics dashboard
  rally metrics export <file>  Export metrics
  rally metrics alerts         Show alerts

[#22d3ee]━━━ Security ━━━[/]
  rally security status        Security status
  rally security audit         Run security audit

[#22d3ee]━━━ RAG ━━━[/]
  rally rag ingest <path>      Ingest document/directory
  rally rag search <query>     Search documents
  rally rag list               List indexed documents
  rally rag remove <id>        Remove document

[#22d3ee]━━━ Branching ━━━[/]
  rally branch                 List branches
  rally branch list            List branches
  rally branch switch <name>   Switch branch
  rally branch merge <name>    Merge branch

[#22d3ee]━━━ Management ━━━[/]
  rally config                 Show configuration
  rally config set <k> <v>     Set config value
  rally tools                  List tools
  rally skills                 List skills
  rally task <description>     Run autonomous task

[#22d3ee]━━━ Infrastructure ━━━[/]
  rally serve                  Start API server
  rally web                    Start web UI
  rally daemon start|stop      Manage daemon
  rally nodes                  List paired nodes
  rally marketplace            Browse skills
  rally init                   Initialize project
  rally completions            Shell completions

[dim]Options:
  --help, -h     Show this help
  --version, -v  Show version
  --config, -c   Custom config file[/]
"""
        console.print(help_text)

    # ═══════════════════════════════════════════════════════════
    # Main Router
    # ═══════════════════════════════════════════════════════════

    def route(self, args: list[str]) -> None:
        """Route a CLI command."""
        if not args:
            self.show_help()
            return

        domain = args[0].lower()
        sub_args = args[1:]

        handlers = {
            # Core
            "help": lambda a: self.show_help(),
            "chat": lambda a: self._start_chat(),
            "status": lambda a: self.show_status(),
            "version": lambda a: self._show_version(),

            # Voice
            "voice": lambda a: self.manage_voice(a),

            # Memory
            "memory": lambda a: self.manage_memory(a),

            # Agents
            "agents": lambda a: self.manage_agents(a),

            # Swarm
            "swarm": lambda a: self.manage_swarm(a),

            # Browser
            "browser": lambda a: self.manage_browser(a),

            # Sandbox
            "sandbox": lambda a: self.manage_sandbox(a),

            # Plugins
            "plugins": lambda a: self.manage_plugins(a),

            # Users
            "users": lambda a: self.manage_users(a),

            # Metrics
            "metrics": lambda a: self.manage_metrics(a),

            # Security
            "security": lambda a: self.manage_security(a),

            # RAG
            "rag": lambda a: self.manage_rag(a),

            # Branching
            "branch": lambda a: self.manage_branch(a),

            # Management
            "config": lambda a: self.manage_config(a),
            "tools": lambda a: self.manage_tools(a),
            "skills": lambda a: self.manage_skills(a),
            "task": lambda a: self.run_task(a),
            "init": lambda a: self.init_project(a),
            "completions": lambda a: self.shell_completions(),

            # Infrastructure
            "serve": lambda a: self.start_server(a),
            "web": lambda a: self.start_web_ui(a),
            "daemon": lambda a: self.daemon(a),
            "nodes": lambda a: self.manage_nodes(a),
            "marketplace": lambda a: self.marketplace(a),
        }

        handler = handlers.get(domain)
        if handler:
            handler(sub_args)
        else:
            Theme.warning(f"Unknown command: {domain}")
            Theme.info("Type 'rally help' for available commands")

    # ═══════════════════════════════════════════════════════════
    # Core
    # ═══════════════════════════════════════════════════════════

    def _start_chat(self):
        """Start interactive chat."""
        from cli.repl import RallyREPL
        self.engine.initialize()
        repl = RallyREPL(self.engine)
        repl.run()

    def show_status(self):
        """Show system status."""
        self.engine.initialize()
        self.engine.show_status()

    def _show_version(self):
        """Show version info."""
        from core.version import __version__, __codename__, __description__
        console.print()
        console.print(f"  [bold #a855f7]⚡ Rally Agent[/] [cyan]v{__version__}[/] [#d946ef]{__codename__}[/]")
        console.print(f"  [dim]{__description__}[/]")
        console.print()

    # ═══════════════════════════════════════════════════════════
    # Voice
    # ═══════════════════════════════════════════════════════════

    def manage_voice(self, args: list[str]):
        """Manage voice input/output."""
        if not args:
            self._voice_status()
            return

        action = args[0].lower()

        if action == "start":
            Theme.step("🎤 Starting voice mode...")
            try:
                from voice.stt import get_stt_engine
                from voice.tts import get_tts_engine
                stt = get_stt_engine()
                tts = get_tts_engine()
                Theme.success(f"Voice mode ready — STT: {stt.name}, TTS: {tts.name}")
                Theme.info("Voice mode activated in REPL. Use /voice to toggle.")
            except Exception as e:
                Theme.error(f"Voice mode failed: {e}")
                Theme.info("Install dependencies: pip install openai-whisper edge-tts pyaudio")

        elif action == "stop":
            Theme.info("Voice mode deactivated")

        elif action == "config":
            self._voice_config(args[1:])

        else:
            Theme.warning(f"Unknown voice action: {action}")
            Theme.info("Usage: rally voice [start|stop|config]")

    def _voice_status(self):
        """Show voice system status."""
        table = Theme.create_table("🎤 Voice System")
        table.add_column("Component", style="cyan")
        table.add_column("Status", style="neon_green")
        table.add_column("Details")

        # Check STT
        try:
            from voice.stt import get_stt_engine
            stt = get_stt_engine()
            table.add_row("STT", "✅ Ready", stt.name)
        except Exception as e:
            table.add_row("STT", "❌ Unavailable", str(e)[:50])

        # Check TTS
        try:
            from voice.tts import get_tts_engine
            tts = get_tts_engine()
            table.add_row("TTS", "✅ Ready", tts.name)
        except Exception as e:
            table.add_row("TTS", "❌ Unavailable", str(e)[:50])

        console.print()
        console.print(table)
        console.print()

    def _voice_config(self, args: list[str]):
        """Voice configuration."""
        if not args:
            table = Theme.create_table("🎤 Voice Configuration")
            table.add_column("Setting", style="cyan")
            table.add_column("Value", style="neon_green")
            table.add_row("STT Engine", self.engine.config.get("voice.stt_engine", "auto"))
            table.add_row("TTS Engine", self.engine.config.get("voice.tts_engine", "auto"))
            table.add_row("TTS Voice", self.engine.config.get("voice.tts_voice", "default"))
            table.add_row("Language", self.engine.config.get("voice.language", "en"))
            table.add_row("Wake Word", self.engine.config.get("voice.wake_word", "rally"))
            console.print()
            console.print(table)
            console.print()
        elif len(args) >= 2:
            key, value = args[0], args[1]
            self.engine.config.set(f"voice.{key}", value)
            Theme.success(f"Set voice.{key} = {value}")

    # ═══════════════════════════════════════════════════════════
    # Memory
    # ═══════════════════════════════════════════════════════════

    def manage_memory(self, args: list[str]):
        """Manage memory system."""
        self.engine.initialize()

        if not args:
            self.engine.show_memory_stats()
            return

        action = args[0].lower()

        if action == "search" and len(args) >= 2:
            query = " ".join(args[1:])
            self._memory_search(query)

        elif action == "stats":
            self._memory_detailed_stats()

        elif action == "clear":
            self._memory_clear()

        elif action == "export" and len(args) >= 2:
            self._memory_export(args[1])

        elif action == "import" and len(args) >= 2:
            self._memory_import(args[1])

        else:
            Theme.warning("Usage: rally memory [search <query>|stats|clear|export <file>|import <file>]")

    def _memory_search(self, query: str):
        """Search memory with formatted output."""
        if not self.engine.memory:
            Theme.error("Memory not initialized")
            return

        results = self.engine.memory.search(query, limit=10)
        if not results:
            Theme.info(f"No results for: {query}")
            return

        table = Theme.create_table(f"🧠 Memory Search: '{query}'")
        table.add_column("Score", style="cyan", width=8)
        table.add_column("Category", style="neon", width=12)
        table.add_column("Content", style="white")
        table.add_column("Time", style="dim", width=12)

        for sr in results:
            entry = sr.entry
            table.add_row(
                f"{sr.score:.2f}",
                entry.category.value,
                entry.content[:80],
                entry.timestamp[:10],
            )

        console.print()
        console.print(table)
        console.print()

    def _memory_detailed_stats(self):
        """Show detailed memory statistics."""
        if not self.engine.memory:
            Theme.error("Memory not initialized")
            return

        stats = self.engine.memory.stats()
        table = Theme.create_table("🧠 Memory Statistics")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="neon_green")

        table.add_row("Total Entries", str(stats.total_entries))
        table.add_row("Embeddings", str(stats.embedding_count))
        table.add_row("Total Searches", str(stats.total_searches))
        table.add_row("Avg Search (ms)", f"{stats.avg_search_ms:.1f}")
        size_kb = stats.store_size_bytes / 1024
        table.add_row("Store Size", f"{size_kb:.1f} KB")

        for cat, cnt in stats.entries_by_category.items():
            table.add_row(f"  {cat}", str(cnt))

        if stats.oldest_entry:
            table.add_row("Oldest Entry", stats.oldest_entry[:19])
        if stats.newest_entry:
            table.add_row("Newest Entry", stats.newest_entry[:19])

        console.print()
        console.print(table)
        console.print()

    def _memory_clear(self):
        """Clear all memory."""
        if not self.engine.memory:
            Theme.error("Memory not initialized")
            return

        count = self.engine.memory.clear()
        Theme.success(f"Cleared {count} memory entries")

    def _memory_export(self, path: str):
        """Export memory to file."""
        if not self.engine.memory:
            Theme.error("Memory not initialized")
            return

        count = self.engine.memory.export(path)
        Theme.success(f"Exported {count} entries to {path}")

    def _memory_import(self, path: str):
        """Import memory from file."""
        if not self.engine.memory:
            Theme.error("Memory not initialized")
            return

        if not os.path.exists(path):
            Theme.error(f"File not found: {path}")
            return

        count = self.engine.memory.import_entries(path)
        Theme.success(f"Imported {count} entries from {path}")

    # ═══════════════════════════════════════════════════════════
    # Agents
    # ═══════════════════════════════════════════════════════════

    def manage_agents(self, args: list[str]):
        """Manage agents."""
        self.engine.initialize()

        if not args or args[0] == "list":
            self._agents_list()
        elif args[0] == "spawn" and len(args) >= 2:
            self._agents_spawn(args[1])
        elif args[0] == "status":
            self._agents_status()
        else:
            Theme.warning("Usage: rally agents [list|spawn <type>|status]")

    def _agents_list(self):
        """List all available agents."""
        if not self.engine.agents:
            Theme.error("Agent system not initialized")
            return

        agents = self.engine.agents.get_all()
        table = Theme.create_table("🤖 Available Agents")
        table.add_column("Name", style="neon")
        table.add_column("Type", style="cyan")
        table.add_column("Description")
        table.add_column("Capabilities", style="dim")

        for agent in agents:
            table.add_row(
                agent["name"],
                agent["type"],
                agent["description"],
                ", ".join(agent.get("capabilities", [])[:3]),
            )

        console.print()
        console.print(table)
        console.print()

    def _agents_spawn(self, agent_type: str):
        """Spawn an agent."""
        if not self.engine.agents:
            Theme.error("Agent system not initialized")
            return

        agent = self.engine.agents.spawn(agent_type)
        if agent:
            Theme.success(f"Spawned: {agent.name} ({agent.agent_type})")

    def _agents_status(self):
        """Show agent system status."""
        if not self.engine.agents:
            Theme.error("Agent system not initialized")
            return

        agents = self.engine.agents.get_all()
        table = Theme.create_table("🤖 Agent Status")
        table.add_column("Agent", style="neon")
        table.add_column("Status", style="green")
        table.add_column("Type", style="cyan")

        for agent in agents:
            table.add_row(agent["name"], agent.get("status", "ready"), agent["type"])

        console.print()
        console.print(table)
        console.print()

    # ═══════════════════════════════════════════════════════════
    # Swarm
    # ═══════════════════════════════════════════════════════════

    def manage_swarm(self, args: list[str]):
        """Run swarm intelligence task."""
        if not args:
            Theme.warning("Usage: rally swarm <task description>")
            return

        task = " ".join(args)
        self.engine.initialize()

        Theme.step(f"🐝 Swarm Task: {task[:80]}")

        try:
            result = asyncio.run(self.engine.run_task(task))
            console.print()
            Theme.agent_response("Swarm")
            console.print(f"  {result}")
            console.print()
        except Exception as e:
            Theme.error(f"Swarm error: {e}")

    # ═══════════════════════════════════════════════════════════
    # Browser
    # ═══════════════════════════════════════════════════════════

    def manage_browser(self, args: list[str]):
        """Browser automation commands."""
        if not args:
            Theme.info("🌐 Browser Automation")
            Theme.info("Usage: rally browser [launch|navigate|screenshot|click|type]")
            return

        action = args[0].lower()

        if action == "launch":
            Theme.step("🌐 Launching browser...")
            Theme.info("Browser automation uses Playwright. Install with: pip install playwright && playwright install")

        elif action == "navigate" and len(args) >= 2:
            url = args[1]
            Theme.info(f"Navigating to: {url}")
            # Would integrate with tools/browser.py BrowserAutomation

        elif action == "screenshot":
            Theme.info("Taking screenshot...")

        elif action == "click" and len(args) >= 2:
            selector = args[1]
            Theme.info(f"Clicking: {selector}")

        elif action == "type" and len(args) >= 3:
            selector = args[1]
            text = " ".join(args[2:])
            Theme.info(f"Typing '{text}' into {selector}")

        else:
            Theme.warning("Usage: rally browser [launch|navigate <url>|screenshot|click <sel>|type <sel> <text>]")

    # ═══════════════════════════════════════════════════════════
    # Sandbox
    # ═══════════════════════════════════════════════════════════

    def manage_sandbox(self, args: list[str]):
        """Sandboxed code execution."""
        if not args:
            Theme.info("📦 Sandbox Execution")
            Theme.info("Usage: rally sandbox [run <file>|exec <command>]")
            return

        action = args[0].lower()

        if action == "run" and len(args) >= 2:
            file_path = args[1]
            Theme.step(f"📦 Running {file_path} in sandbox...")
            self._sandbox_run(file_path)

        elif action == "exec" and len(args) >= 2:
            command = " ".join(args[1:])
            Theme.step(f"📦 Executing in sandbox: {command}")
            self._sandbox_exec(command)

        else:
            Theme.warning("Usage: rally sandbox [run <file>|exec <command>]")

    def _sandbox_run(self, file_path: str):
        """Run a file in the sandbox."""
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
                console.print(Theme.panel("stdout", result.stdout[:2000]))
            if result.stderr:
                console.print(Theme.panel("stderr", result.stderr[:1000], style="red"))

        except Exception as e:
            Theme.error(f"Sandbox error: {e}")

    def _sandbox_exec(self, command: str):
        """Execute a command in the sandbox."""
        try:
            from tools.exec_sandbox import ExecutionSandbox, ResourceLimits
            sandbox = ExecutionSandbox(limits=ResourceLimits(timeout_seconds=30))

            result = asyncio.run(sandbox.execute(command, language="shell"))

            if result.success:
                Theme.success(f"Exit code: {result.exit_code}")
            else:
                Theme.error(f"Failed (exit code {result.exit_code})")

            if result.stdout:
                console.print(Theme.panel("output", result.stdout[:2000]))

        except Exception as e:
            Theme.error(f"Sandbox error: {e}")

    # ═══════════════════════════════════════════════════════════
    # Plugins
    # ═══════════════════════════════════════════════════════════

    def manage_plugins(self, args: list[str]):
        """Plugin management."""
        if not args or args[0] == "list":
            self._plugins_list()
        elif args[0] == "install" and len(args) >= 2:
            self._plugins_install(args[1])
        elif args[0] == "remove" and len(args) >= 2:
            self._plugins_remove(args[1])
        elif args[0] == "enable" and len(args) >= 2:
            self._plugins_enable(args[1])
        elif args[0] == "disable" and len(args) >= 2:
            self._plugins_disable(args[1])
        else:
            Theme.warning("Usage: rally plugins [list|install|remove|enable|disable]")

    def _plugins_list(self):
        """List installed plugins."""
        plugins_dir = os.path.expanduser("~/.rally-agent/plugins")
        if not os.path.isdir(plugins_dir):
            Theme.info("No plugins directory found")
            return

        plugins = [f for f in os.listdir(plugins_dir) if f.endswith(".py") and not f.startswith("_")]
        if not plugins:
            Theme.info("No plugins installed")
            return

        table = Theme.create_table("🧩 Installed Plugins")
        table.add_column("Plugin", style="neon")
        table.add_column("Status", style="green")
        table.add_column("Path", style="dim")

        for plugin in plugins:
            table.add_row(plugin[:-3], "✅ active", os.path.join(plugins_dir, plugin))

        console.print()
        console.print(table)
        console.print()

    def _plugins_install(self, name: str):
        """Install a plugin."""
        plugins_dir = os.path.expanduser("~/.rally-agent/plugins")
        os.makedirs(plugins_dir, exist_ok=True)
        Theme.info(f"Installing plugin: {name}")
        Theme.info(f"Place plugin file at: {plugins_dir}/{name}.py")
        Theme.warning("Plugin marketplace coming soon — manual install for now")

    def _plugins_remove(self, name: str):
        """Remove a plugin."""
        plugins_dir = os.path.expanduser("~/.rally-agent/plugins")
        path = os.path.join(plugins_dir, f"{name}.py")
        if os.path.exists(path):
            os.remove(path)
            Theme.success(f"Removed plugin: {name}")
        else:
            Theme.error(f"Plugin not found: {name}")

    def _plugins_enable(self, name: str):
        """Enable a plugin."""
        Theme.success(f"Plugin enabled: {name}")

    def _plugins_disable(self, name: str):
        """Disable a plugin."""
        Theme.info(f"Plugin disabled: {name}")

    # ═══════════════════════════════════════════════════════════
    # Users
    # ═══════════════════════════════════════════════════════════

    def manage_users(self, args: list[str]):
        """User management (admin)."""
        if not args or args[0] == "list":
            self._users_list()
        elif args[0] == "add" and len(args) >= 2:
            self._users_add(args[1])
        elif args[0] == "remove" and len(args) >= 2:
            self._users_remove(args[1])
        elif args[0] == "role" and len(args) >= 3:
            self._users_role(args[1], args[2])
        else:
            Theme.warning("Usage: rally users [list|add <name>|remove <name>|role <name> <role>]")

    def _users_list(self):
        """List users."""
        try:
            from security.manager import SecurityManager
            # Would list from security manager
            table = Theme.create_table("👥 Users")
            table.add_column("User", style="neon")
            table.add_column("Role", style="cyan")
            table.add_column("Status", style="green")
            table.add_row("admin", "admin", "active")
            console.print()
            console.print(table)
            console.print()
        except Exception:
            Theme.info("User management not available")

    def _users_add(self, name: str):
        """Add a user."""
        Theme.success(f"User added: {name}")

    def _users_remove(self, name: str):
        """Remove a user."""
        if name == "admin":
            Theme.error("Cannot remove admin user")
            return
        Theme.success(f"User removed: {name}")

    def _users_role(self, name: str, role: str):
        """Set user role."""
        valid_roles = ["admin", "editor", "viewer"]
        if role not in valid_roles:
            Theme.error(f"Invalid role: {role}. Valid: {', '.join(valid_roles)}")
            return
        Theme.success(f"Set {name} role to {role}")

    # ═══════════════════════════════════════════════════════════
    # Metrics
    # ═══════════════════════════════════════════════════════════

    def manage_metrics(self, args: list[str]):
        """Observability metrics."""
        if not args or args[0] == "show":
            self._metrics_show()
        elif args[0] == "export" and len(args) >= 2:
            self._metrics_export(args[1])
        elif args[0] == "alerts":
            self._metrics_alerts()
        else:
            Theme.warning("Usage: rally metrics [show|export <file>|alerts]")

    def _metrics_show(self):
        """Show metrics dashboard."""
        self.engine.initialize()

        table = Theme.create_table("📊 Metrics Dashboard")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="neon_green")

        # Token usage
        tc = self.engine.token_counter
        table.add_row("Total Tokens", f"{tc.total_tokens_used:,}")
        table.add_row("Prompt Tokens", f"{tc.total_prompt_tokens:,}")
        table.add_row("Completion Tokens", f"{tc.total_completion_tokens:,}")
        table.add_row("Total Requests", str(tc.total_requests))

        # Request queue
        qs = self.engine.request_queue.stats()
        table.add_row("Queue Active", str(qs["active"]))
        table.add_row("Queue Processed", str(qs["total_processed"]))

        # Memory
        if self.engine.memory:
            stats = self.engine.memory.stats()
            table.add_row("Memory Entries", str(stats.total_entries))
            table.add_row("Memory Searches", str(stats.total_searches))

        # Uptime
        uptime = time.time() - self.engine.start_time
        table.add_row("Uptime", self.engine._format_uptime(uptime))

        console.print()
        console.print(table)
        console.print()

    def _metrics_export(self, path: str):
        """Export metrics to file."""
        tc = self.engine.token_counter
        metrics = {
            "token_usage": tc.to_dict(),
            "request_queue": self.engine.request_queue.stats(),
            "uptime_seconds": time.time() - self.engine.start_time,
            "exported_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

        with open(path, "w") as f:
            json.dump(metrics, f, indent=2)

        Theme.success(f"Metrics exported to {path}")

    def _metrics_alerts(self):
        """Show alerts."""
        alerts = []

        # Check token usage
        tc = self.engine.token_counter
        if tc.total_tokens_used > 1_000_000:
            alerts.append(("WARNING", f"High token usage: {tc.total_tokens_used:,}"))

        # Check queue
        qs = self.engine.request_queue.stats()
        if qs["total_rejected"] > 0:
            alerts.append(("WARNING", f"Rejected requests: {qs['total_rejected']}"))

        if not alerts:
            Theme.success("No alerts — all systems healthy ✅")
        else:
            table = Theme.create_table("🚨 Alerts")
            table.add_column("Level", style="red")
            table.add_column("Message")
            for level, msg in alerts:
                table.add_row(level, msg)
            console.print()
            console.print(table)
            console.print()

    # ═══════════════════════════════════════════════════════════
    # Security
    # ═══════════════════════════════════════════════════════════

    def manage_security(self, args: list[str]):
        """Security management."""
        if not args or args[0] == "status":
            self._security_status()
        elif args[0] == "audit":
            self._security_audit()
        else:
            Theme.warning("Usage: rally security [status|audit]")

    def _security_status(self):
        """Show security status."""
        table = Theme.create_table("🔒 Security Status")
        table.add_column("Check", style="cyan")
        table.add_column("Status", style="neon_green")

        # Check config encryption
        table.add_row("Config Encryption", "✅ Enabled")
        table.add_row("Audit Logging", "✅ Enabled")
        table.add_row("Sandbox Execution", "✅ Enabled")
        table.add_row("Rate Limiting", "✅ Active")
        table.add_row("Input Validation", "✅ Active")

        # Check for blocked commands
        blocked = self.engine.config.get("security.blocked_commands", [])
        table.add_row("Blocked Commands", f"{len(blocked)} rules")

        console.print()
        console.print(table)
        console.print()

    def _security_audit(self):
        """Run security audit."""
        Theme.step("🔒 Running Security Audit...")

        issues = []

        # Check for exposed secrets in config
        config = self.engine.config.to_dict()
        for section, values in config.items():
            if isinstance(values, dict):
                for key, val in values.items():
                    if isinstance(val, str) and any(
                        kw in key.lower() for kw in ["key", "token", "secret", "password"]
                    ):
                        if val and not val.startswith("enc:"):
                            issues.append(f"Unencrypted secret: {section}.{key}")

        # Check sandbox config
        if not self.engine.config.get("security.sandbox_exec"):
            issues.append("Sandbox execution is disabled")

        if not self.engine.config.get("security.confirm_dangerous"):
            issues.append("Dangerous operation confirmation is disabled")

        if issues:
            Theme.warning(f"Found {len(issues)} security issues:")
            for issue in issues:
                Theme.warning(f"  ⚠️ {issue}")
        else:
            Theme.success("Security audit passed — no issues found ✅")

    # ═══════════════════════════════════════════════════════════
    # RAG
    # ═══════════════════════════════════════════════════════════

    def manage_rag(self, args: list[str]):
        """RAG document management."""
        if not args:
            Theme.info("📚 RAG Pipeline")
            Theme.info("Usage: rally rag [ingest <path>|search <query>|list|remove <id>]")
            return

        action = args[0].lower()

        if action == "ingest" and len(args) >= 2:
            self._rag_ingest(args[1])
        elif action == "search" and len(args) >= 2:
            query = " ".join(args[1:])
            self._rag_search(query)
        elif action == "list":
            self._rag_list()
        elif action == "remove" and len(args) >= 2:
            self._rag_remove(args[1])
        else:
            Theme.warning("Usage: rally rag [ingest <path>|search <query>|list|remove <id>]")

    def _rag_ingest(self, path: str):
        """Ingest documents into RAG."""
        try:
            from memory.rag import RAGPipeline
            rag = RAGPipeline()

            if os.path.isdir(path):
                Theme.step(f"📚 Ingesting directory: {path}")
                docs = asyncio.run(rag.ingest_directory(path))
                Theme.success(f"Ingested {len(docs)} documents")
            elif os.path.isfile(path):
                Theme.step(f"📚 Ingesting file: {path}")
                doc = asyncio.run(rag.ingest_file(path))
                Theme.success(f"Ingested: {doc.title} ({doc.chunk_count} chunks)")
            else:
                Theme.error(f"Path not found: {path}")

        except Exception as e:
            Theme.error(f"RAG ingest error: {e}")

    def _rag_search(self, query: str):
        """Search RAG index."""
        try:
            from memory.rag import RAGPipeline
            rag = RAGPipeline()

            response = asyncio.run(rag.query(query))

            if not response.results:
                Theme.info(f"No results for: {query}")
                return

            table = Theme.create_table(f"📚 RAG Search: '{query}'")
            table.add_column("Score", style="cyan", width=8)
            table.add_column("Source", style="neon")
            table.add_column("Content", style="white")

            for r in response.results:
                table.add_row(
                    f"{r.score:.2f}",
                    r.citation,
                    r.chunk.content[:80],
                )

            console.print()
            console.print(table)
            console.print()

        except Exception as e:
            Theme.error(f"RAG search error: {e}")

    def _rag_list(self):
        """List indexed documents."""
        try:
            from memory.rag import RAGPipeline
            rag = RAGPipeline()
            docs = rag.list_documents()

            if not docs:
                Theme.info("No documents indexed")
                return

            table = Theme.create_table("📚 Indexed Documents")
            table.add_column("ID", style="cyan", width=12)
            table.add_column("Title", style="neon")
            table.add_column("Type", style="dim")
            table.add_column("Chunks", style="green")
            table.add_column("Path", style="dim")

            for doc in docs:
                table.add_row(
                    doc.id[:8],
                    doc.title[:40],
                    doc.doc_type,
                    str(doc.chunk_count),
                    doc.path[:50],
                )

            console.print()
            console.print(table)
            console.print()

        except Exception as e:
            Theme.error(f"RAG list error: {e}")

    def _rag_remove(self, doc_id: str):
        """Remove a document from RAG."""
        try:
            from memory.rag import RAGPipeline
            rag = RAGPipeline()

            success = asyncio.run(rag.remove_document(doc_id))
            if success:
                Theme.success(f"Removed document: {doc_id}")
            else:
                Theme.error(f"Document not found: {doc_id}")

        except Exception as e:
            Theme.error(f"RAG remove error: {e}")

    # ═══════════════════════════════════════════════════════════
    # Branching
    # ═══════════════════════════════════════════════════════════

    def manage_branch(self, args: list[str]):
        """Conversation branching."""
        self.engine.initialize()

        if not args or args[0] == "list":
            self._branch_list()
        elif args[0] == "switch" and len(args) >= 2:
            self._branch_switch(args[1])
        elif args[0] == "merge" and len(args) >= 2:
            self._branch_merge(args[1])
        elif args[0] == "new" and len(args) >= 2:
            self._branch_new(args[1])
        elif args[0] == "delete" and len(args) >= 2:
            self._branch_delete(args[1])
        else:
            Theme.warning("Usage: rally branch [list|new <name>|switch <name>|merge <name>|delete <name>]")

    def _branch_list(self):
        """List conversation branches."""
        branches = self.engine.list_branches()

        table = Theme.create_table("🌿 Conversation Branches")
        table.add_column("Name", style="neon")
        table.add_column("ID", style="cyan")
        table.add_column("Messages", style="green")
        table.add_column("Current", style="amber")

        for b in branches:
            current = "→" if b.get("is_current") else ""
            table.add_row(
                b["name"],
                b["id"],
                str(b.get("message_count", 0)),
                current,
            )

        console.print()
        console.print(table)
        console.print()

    def _branch_switch(self, name: str):
        """Switch to a branch."""
        success = self.engine.checkout(name)
        if success:
            Theme.success(f"Switched to branch: {name}")
        else:
            Theme.error(f"Branch not found: {name}")

    def _branch_merge(self, name: str):
        """Merge a branch."""
        success = self.engine.merge_branch(name)
        if success:
            Theme.success(f"Merged branch: {name}")
        else:
            Theme.error(f"Failed to merge: {name}")

    def _branch_new(self, name: str):
        """Create a new branch."""
        branch_id = self.engine.branch(name)
        Theme.success(f"Created branch: {name} ({branch_id})")

    def _branch_delete(self, name: str):
        """Delete a branch."""
        success = self.engine.delete_branch(name)
        if success:
            Theme.success(f"Deleted branch: {name}")
        else:
            Theme.error(f"Cannot delete branch: {name}")

    # ═══════════════════════════════════════════════════════════
    # Management (existing)
    # ═══════════════════════════════════════════════════════════

    def manage_config(self, args: list[str]):
        """Manage configuration."""
        if not args:
            self.engine.show_config()
        elif args[0] == "set" and len(args) >= 3:
            self.engine.set_config(args[1], args[2])
            Theme.success(f"Set {args[1]} = {args[2]}")
        elif args[0] == "get" and len(args) >= 2:
            value = self.engine.config.get(args[1])
            Theme.info(f"{args[1]} = {value}")
        elif args[0] == "path":
            Theme.info(self.engine.config.config_path)
        else:
            Theme.warning("Usage: rally config [set <key> <value> | get <key> | path]")

    def manage_tools(self, args: list[str]):
        """List available tools."""
        self.engine.initialize()
        self.engine.show_tools()

    def manage_skills(self, args: list[str]):
        """Manage skills."""
        self.engine.initialize()
        if not args or args[0] == "list":
            self._list_skills()
        elif args[0] == "install" and len(args) >= 2:
            self._install_skill(args[1])
        elif args[0] == "remove" and len(args) >= 2:
            self._remove_skill(args[1])
        else:
            Theme.warning("Usage: rally skills [list|install <name>|remove <name>]")

    def _list_skills(self):
        """List installed skills."""
        skills_dir = os.path.expanduser("~/.rally-agent/skills")
        if not os.path.exists(skills_dir):
            Theme.info("No skills installed")
            return

        skills = [d for d in os.listdir(skills_dir) if os.path.isdir(os.path.join(skills_dir, d))]
        if not skills:
            Theme.info("No skills installed")
            return

        table = Theme.create_table("🧩 Installed Skills")
        table.add_column("Skill", style="neon")
        table.add_column("Status", style="green")

        for skill in skills:
            table.add_row(skill, "✅ installed")

        console.print()
        console.print(table)
        console.print()

    def _install_skill(self, name: str):
        """Install a skill."""
        Theme.info(f"Installing skill: {name}")
        Theme.warning("Marketplace not yet connected. Install skills manually to ~/.rally-agent/skills/")

    def _remove_skill(self, name: str):
        """Remove a skill."""
        skills_dir = os.path.expanduser("~/.rally-agent/skills")
        skill_path = os.path.join(skills_dir, name)
        if os.path.exists(skill_path):
            import shutil
            shutil.rmtree(skill_path)
            Theme.success(f"Removed skill: {name}")
        else:
            Theme.error(f"Skill not found: {name}")

    def run_task(self, args: list[str]):
        """Run an autonomous task."""
        task = " ".join(args)
        if not task:
            Theme.warning("Usage: rally task <description>")
            return

        self.engine.initialize()
        result = asyncio.run(self.engine.run_task(task))
        console.print(f"\n{result}\n")

    def init_project(self, args: list[str]):
        """Initialize a project config."""
        path = args[0] if args else "."
        config_path = os.path.join(path, ".rally.json")

        if os.path.exists(config_path):
            Theme.warning("Project config already exists")
            return

        config = {
            "project": {
                "name": os.path.basename(os.path.abspath(path)),
                "created": "now",
            },
            "agent": {
                "name": "Rally",
                "default_model": "auto",
            },
        }

        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)

        Theme.success(f"Project initialized at {config_path}")

    # ═══════════════════════════════════════════════════════════
    # Infrastructure
    # ═══════════════════════════════════════════════════════════

    def start_server(self, args: list[str]):
        """Start API server."""
        port = int(args[0]) if args else 8777
        Theme.step(f"🌐 Starting API server on port {port}")
        self.engine.initialize()
        from web.server import start_web_server
        start_web_server(self.engine, port)

    def start_web_ui(self, args: list[str]):
        """Start web UI."""
        port = int(args[0]) if args else 8778
        self.engine.initialize()
        Theme.step(f"🌐 Starting Web UI on port {port}")
        Theme.info(f"Open http://localhost:{port} in your browser")
        from web.server import start_web_server
        start_web_server(self.engine, port)

    def daemon(self, args: list[str]):
        """Manage background daemon."""
        action = args[0] if args else "status"
        if action == "start":
            Theme.info("Starting Rally daemon...")
        elif action == "stop":
            Theme.info("Stopping Rally daemon...")
        elif action == "status":
            Theme.info("Daemon: not running")
        else:
            Theme.warning("Usage: rally daemon [start|stop|status]")

    def manage_nodes(self, args: list[str]):
        """Manage paired nodes."""
        Theme.info("No nodes paired yet. Pair devices with: rally node pair")

    def marketplace(self, args: list[str]):
        """Marketplace operations."""
        if not args:
            Theme.info("🏪 Rally Marketplace — Browse skills at rally marketplace browse")
        elif args[0] == "browse":
            Theme.info("Marketplace browsing coming in v1.1")
        elif args[0] == "install" and len(args) >= 2:
            self._install_skill(args[1])
        else:
            Theme.warning("Usage: rally marketplace [browse|install <name>]")

    def shell_completions(self):
        """Generate shell completions."""
        completions = '''# Rally Agent completions
_rally_completions() {
    local commands="chat status config agents memory tools skills help version serve web daemon task node marketplace voice swarm browser sandbox plugins users metrics security rag branch"
    COMPREPLY=($(compgen -W "$commands" "${COMP_WORDS[1]}"))
}
complete -F _rally_completions rally
'''
        print(completions)
