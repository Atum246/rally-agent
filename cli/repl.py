"""
🟣 Rally Agent — Interactive REPL (Read-Eval-Print Loop)
"""

import asyncio
import sys
from typing import Optional

from cli.theme import Theme, console, Colors
from core.engine import RallyEngine


class RallyREPL:
    """Interactive command-line interface for Rally Agent"""

    def __init__(self, engine: RallyEngine):
        self.engine = engine
        self.running = True
        self.history: list[str] = []
        self.multiline_buffer: list[str] = []

    def run(self):
        """Main REPL loop"""
        try:
            import prompt_toolkit
            self._run_advanced()
        except ImportError:
            self._run_basic()

    def _run_basic(self):
        """Basic REPL without prompt_toolkit"""
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

                # Check for multiline
                if user_input.endswith("\\"):
                    self.multiline_buffer.append(user_input[:-1])
                    continue

                if self.multiline_buffer:
                    self.multiline_buffer.append(user_input)
                    user_input = "\n".join(self.multiline_buffer)
                    self.multiline_buffer = []

                self.history.append(user_input)
                asyncio.run(self._process_input(user_input))

            except EOFError:
                console.print("\n[dim]Goodbye! 👋[/]")
                break
            except KeyboardInterrupt:
                console.print("\n[dim]Use 'exit' to quit[/]")

    def _run_advanced(self):
        """Advanced REPL with prompt_toolkit"""
        from prompt_toolkit import PromptSession
        from prompt_toolkit.history import FileHistory
        from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
        from prompt_toolkit.styles import Style
        import os

        style = Style.from_dict({
            "": "#c084fc",
            "prompt": "#a855f7",
        })

        history_file = os.path.expanduser("~/.rally-agent/data/history.txt")
        os.makedirs(os.path.dirname(history_file), exist_ok=True)

        session = PromptSession(
            history=FileHistory(history_file),
            auto_suggest=AutoSuggestFromHistory(),
            style=style,
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

                self.history.append(user_input)
                asyncio.run(self._process_input(user_input))

            except KeyboardInterrupt:
                continue
            except EOFError:
                console.print("\n[dim]Goodbye! 👋[/]")
                break

    def _get_prompt(self) -> str:
        """Get basic prompt string"""
        name = self.engine.config.get("agent.name", "Rally")
        return f"  ⚡ {name} ❯❯ "

    def _get_prompt_ptk(self) -> list:
        """Get prompt_toolkit formatted prompt"""
        from prompt_toolkit.formatted_text import HTML
        return HTML("  <ansimagenta>⚡</ansimagenta> <ansibrightmagenta>Rally</ansibrightmagenta> <ansimagenta>❯❯</ansimagenta> ")

    async def _process_input(self, user_input: str):
        """Process user input through the engine"""
        Theme.separator()

        try:
            response = await self.engine.chat(user_input)

            if response:
                console.print()
                Theme.agent_response()
                console.print(f"  {response}")
                console.print()

        except Exception as e:
            Theme.error(f"Error: {e}")

    def _handle_command(self, cmd: str):
        """Handle slash commands"""
        parts = cmd[1:].split()
        command = parts[0].lower() if parts else ""
        args = parts[1:]

        commands = {
            "help": self._cmd_help,
            "exit": self._cmd_exit,
            "quit": self._cmd_exit,
            "clear": self._cmd_clear,
            "history": self._cmd_history,
            "status": self._cmd_status,
            "agents": self._cmd_agents,
            "memory": self._cmd_memory,
            "tools": self._cmd_tools,
            "config": self._cmd_config,
            "model": self._cmd_model,
            "think": self._cmd_think,
            "save": self._cmd_save,
            "load": self._cmd_load,
            "task": self._cmd_task,
            "spawn": self._cmd_spawn,
            "compact": self._cmd_compact,
        }

        handler = commands.get(command)
        if handler:
            handler(args)
        else:
            Theme.warning(f"Unknown command: /{command}")
            Theme.info("Type /help for available commands")

    def _cmd_help(self, args):
        """Show help"""
        help_text = """
[cyan]Chat:[/]
  Just type naturally — Rally understands context and remembers everything.

[cyan]Slash Commands:[/]
  /help              Show this help
  /status            System status
  /agents            List active agents
  /memory            Memory operations
  /tools             List available tools
  /config            Configuration
  /model <name>      Switch model
  /think [on|off]    Toggle thinking mode
  /clear             Clear screen
  /history           Show command history
  /save <file>       Save conversation
  /load <file>       Load conversation
  /task <desc>       Run autonomous task
  /spawn <agent>     Spawn a sub-agent
  /compact           Toggle compact mode
  /exit              Exit Rally
"""
        console.print(Panel(
            help_text.strip(),
            title="[bold #c084fc]📚 Commands[/]",
            border_style=Colors.PURPLE,
            box=box.HEAVY,
        ))

    def _cmd_exit(self, args):
        """Exit"""
        self.running = False
        console.print("[dim]Shutting down... 👋[/]")

    def _cmd_clear(self, args):
        """Clear screen"""
        import os
        os.system("cls" if os.name == "nt" else "clear")

    def _cmd_history(self, args):
        """Show history"""
        for i, h in enumerate(self.history[-20:], 1):
            console.print(f"  [dim]{i:3}[/] [purple]{h}[/]")

    def _cmd_status(self, args):
        """Show status"""
        self.engine.show_status()

    def _cmd_agents(self, args):
        """List agents"""
        self.engine.show_agents()

    def _cmd_memory(self, args):
        """Memory operations"""
        if not args:
            self.engine.show_memory_stats()
        elif args[0] == "search":
            query = " ".join(args[1:])
            self.engine.search_memory(query)
        elif args[0] == "clear":
            self.engine.clear_memory()

    def _cmd_tools(self, args):
        """List tools"""
        self.engine.show_tools()

    def _cmd_config(self, args):
        """Config operations"""
        if not args:
            self.engine.show_config()
        elif args[0] == "set" and len(args) >= 3:
            self.engine.set_config(args[1], args[2])

    def _cmd_model(self, args):
        """Switch model"""
        if args:
            self.engine.set_model(args[0])
        else:
            self.engine.show_model()

    def _cmd_think(self, args):
        """Toggle thinking"""
        if args:
            mode = args[0].lower() in ("on", "true", "1", "yes")
            self.engine.set_thinking(mode)
        else:
            self.engine.toggle_thinking()

    def _cmd_save(self, args):
        """Save conversation"""
        path = args[0] if args else "conversation.json"
        self.engine.save_conversation(path)

    def _cmd_load(self, args):
        """Load conversation"""
        path = args[0] if args else "conversation.json"
        self.engine.load_conversation(path)

    def _cmd_task(self, args):
        """Run autonomous task"""
        task = " ".join(args)
        if task:
            asyncio.run(self.engine.run_task(task))
        else:
            Theme.warning("Usage: /task <description>")

    def _cmd_spawn(self, args):
        """Spawn sub-agent"""
        agent_type = args[0] if args else "general"
        self.engine.spawn_agent(agent_type)

    def _cmd_compact(self, args):
        """Toggle compact mode"""
        self.engine.toggle_compact()
