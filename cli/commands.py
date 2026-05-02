"""
🟣 Rally Agent — CLI Command Router
Handles all CLI subcommands.
"""

import os
import sys
import json
from typing import Optional

from cli.theme import Theme, console, Colors


class CommandRouter:
    """Routes CLI commands to appropriate handlers"""

    def __init__(self, engine):
        self.engine = engine

    def show_help(self):
        """Show comprehensive help"""
        help_text = """
[bold #c084fc]⚡ RALLY AGENT — Command Reference[/]

[#22d3ee]━━━ Core Commands ━━━[/]
  rally                     Start interactive mode
  rally chat                Start chat session
  rally status              Show system status
  rally version             Show version

[#22d3ee]━━━ Management ━━━[/]
  rally config              Show configuration
  rally config set <k> <v>  Set config value
  rally agents              List available agents
  rally memory              Memory statistics
  rally memory search <q>   Search memory
  rally tools               List available tools
  rally skills              List installed skills

[#22d3ee]━━━ Execution ━━━[/]
  rally task <description>  Run autonomous task
  rally serve               Start API server
  rally web                 Start web UI
  rally daemon start|stop   Manage background daemon

[#22d3ee]━━━ Network ━━━[/]
  rally nodes               List paired nodes
  rally node pair           Pair a new device

[#22d3ee]━━━ Marketplace ━━━[/]
  rally marketplace         Browse skills
  rally marketplace install Install a skill

[#22d3ee]━━━ Shell ━━━[/]
  rally completions         Generate shell completions
  rally init                Initialize project config

[dim]Options:
  --help, -h     Show this help
  --version, -v  Show version
  --config, -c   Custom config file path[/]
"""
        console.print(help_text)

    def show_status(self):
        """Show system status"""
        self.engine.initialize()
        self.engine.show_status()

    def manage_config(self, args: list):
        """Manage configuration"""
        if not args:
            self.engine.show_config()
        elif args[0] == "set" and len(args) >= 3:
            key = args[1]
            value = args[2]
            self.engine.set_config(key, value)
        elif args[0] == "get" and len(args) >= 2:
            value = self.engine.config.get(args[1])
            Theme.info(f"{args[1]} = {value}")
        elif args[0] == "path":
            Theme.info(self.engine.config.config_path)
        else:
            Theme.warning("Usage: rally config [set <key> <value> | get <key> | path]")

    def manage_agents(self, args: list):
        """Manage agents"""
        self.engine.initialize()
        if not args:
            self.engine.show_agents()
        elif args[0] == "spawn" and len(args) >= 2:
            self.engine.spawn_agent(args[1])
        elif args[0] == "list":
            self.engine.show_agents()
        else:
            Theme.warning("Usage: rally agents [list | spawn <type>]")

    def manage_memory(self, args: list):
        """Manage memory"""
        self.engine.initialize()
        if not args:
            self.engine.show_memory_stats()
        elif args[0] == "search" and len(args) >= 2:
            query = " ".join(args[1:])
            self.engine.search_memory(query)
        elif args[0] == "clear":
            self.engine.clear_memory()
        elif args[0] == "export" and len(args) >= 2:
            self.engine.memory.export(args[1])
        elif args[0] == "import" and len(args) >= 2:
            self.engine.memory.import_entries(args[1])
        else:
            Theme.warning("Usage: rally memory [search <query> | clear | export <file> | import <file>]")

    def manage_tools(self, args: list):
        """Manage tools"""
        self.engine.initialize()
        if not args:
            self.engine.show_tools()
        elif args[0] == "list":
            self.engine.show_tools()
        else:
            Theme.warning("Usage: rally tools [list]")

    def manage_skills(self, args: list):
        """Manage skills"""
        self.engine.initialize()
        if not args:
            self._list_skills()
        elif args[0] == "list":
            self._list_skills()
        elif args[0] == "install" and len(args) >= 2:
            self._install_skill(args[1])
        elif args[0] == "remove" and len(args) >= 2:
            self._remove_skill(args[1])
        else:
            Theme.warning("Usage: rally skills [list | install <name> | remove <name>]")

    def _list_skills(self):
        """List installed skills"""
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
            table.add_row(skill, "✓ installed")

        console.print()
        console.print(table)
        console.print()

    def _install_skill(self, name: str):
        """Install a skill"""
        Theme.info(f"Installing skill: {name}")
        # Marketplace integration would go here
        Theme.warning("Marketplace not yet connected. Install skills manually to ~/.rally-agent/skills/")

    def _remove_skill(self, name: str):
        """Remove a skill"""
        skills_dir = os.path.expanduser("~/.rally-agent/skills")
        skill_path = os.path.join(skills_dir, name)
        if os.path.exists(skill_path):
            import shutil
            shutil.rmtree(skill_path)
            Theme.success(f"Removed skill: {name}")
        else:
            Theme.error(f"Skill not found: {name}")

    def start_server(self, args: list):
        """Start API server"""
        port = int(args[0]) if args else 8777
        Theme.step(f"🌐 Starting API server on port {port}")
        Theme.warning("API server feature coming in v1.1 — use 'rally chat' for now")

    def start_web_ui(self, args: list):
        """Start web UI"""
        port = int(args[0]) if args else 8778
        self.engine.initialize()
        Theme.step(f"🌐 Starting Web UI on port {port}")
        Theme.info(f"Open http://localhost:{port} in your browser")
        from web.server import start_web_server
        start_web_server(self.engine, port)

    def manage_nodes(self, args: list):
        """Manage paired nodes"""
        if not args:
            self._list_nodes()
        elif args[0] == "pair":
            Theme.info("Node pairing — use rally node pair from the device you want to connect")
        elif args[0] == "list":
            self._list_nodes()
        else:
            Theme.warning("Usage: rally nodes [list | pair]")

    def _list_nodes(self):
        """List paired nodes"""
        Theme.info("No nodes paired yet")
        Theme.info("Pair devices with: rally node pair")

    def marketplace(self, args: list):
        """Marketplace operations"""
        if not args:
            Theme.info("🏪 Rally Marketplace")
            Theme.info("Browse skills at: rally marketplace browse")
            Theme.warning("Marketplace coming in v1.1")
        elif args[0] == "browse":
            Theme.info("Marketplace browsing coming in v1.1")
        elif args[0] == "install" and len(args) >= 2:
            self._install_skill(args[1])
        else:
            Theme.warning("Usage: rally marketplace [browse | install <name>]")

    def shell_completions(self):
        """Generate shell completions"""
        completions = '''# Rally Agent completions
_rally_completions() {
    local commands="chat status config agents memory tools skills help version serve web daemon task node marketplace"
    COMPREPLY=($(compgen -W "$commands" "${COMP_WORDS[1]}"))
}
complete -F _rally_completions rally
'''
        print(completions)

    def init_project(self, args: list):
        """Initialize a project config"""
        path = args[0] if args else "."
        config_path = os.path.join(path, ".rally.toml")

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

        import json
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)

        Theme.success(f"Project initialized at {config_path}")

    def daemon(self, args: list):
        """Manage background daemon"""
        action = args[0] if args else "status"

        if action == "start":
            Theme.info("Starting Rally daemon...")
            Theme.warning("Daemon mode coming in v1.1 — use 'rally chat' for interactive mode")
        elif action == "stop":
            Theme.info("Stopping Rally daemon...")
        elif action == "status":
            Theme.info("Daemon: not running")
        else:
            Theme.warning("Usage: rally daemon [start | stop | status]")

    def run_task(self, args: list):
        """Run an autonomous task"""
        import asyncio
        task = " ".join(args)
        if not task:
            Theme.warning("Usage: rally task <description>")
            return

        self.engine.initialize()
        result = asyncio.run(self.engine.run_task(task))
        console.print(f"\n{result}\n")
