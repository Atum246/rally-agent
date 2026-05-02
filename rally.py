#!/usr/bin/env python3
"""
╔═══════════════════════════════════════════════════════════════╗
║  🟣 RALLY AGENT — The OpenClaw Killer                        ║
║  Your AI. Your Rules. Your Data.                             ║
╚═══════════════════════════════════════════════════════════════╝
"""

import sys
import os
import asyncio
import signal

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cli.banner import show_banner, show_mini_banner
from cli.theme import Theme
from cli.repl import RallyREPL
from cli.commands import CommandRouter
from core.engine import RallyEngine
from core.config import RallyConfig


def setup_signal_handlers(engine: RallyEngine):
    """Graceful shutdown on Ctrl+C"""
    def handler(signum, frame):
        print()
        Theme.info("Shutting down Rally Agent...")
        engine.shutdown()
        sys.exit(0)
    signal.signal(signal.SIGINT, handler)


def main():
    """Main entry point for Rally Agent"""
    config = RallyConfig.load()
    engine = RallyEngine(config)
    setup_signal_handlers(engine)

    args = sys.argv[1:]

    # No args → interactive mode
    if not args:
        show_banner()
        engine.initialize()
        repl = RallyREPL(engine)
        repl.run()
        return

    # Command routing
    router = CommandRouter(engine)

    # Handle subcommands
    cmd = args[0].lower()

    if cmd in ("chat", "c"):
        show_mini_banner()
        engine.initialize()
        repl = RallyREPL(engine)
        repl.run()

    elif cmd in ("status", "s"):
        router.show_status()

    elif cmd in ("config", "cfg"):
        router.manage_config(args[1:])

    elif cmd in ("agents", "a"):
        router.manage_agents(args[1:])

    elif cmd in ("memory", "mem"):
        router.manage_memory(args[1:])

    elif cmd in ("tools", "t"):
        router.manage_tools(args[1:])

    elif cmd in ("skills", "sk"):
        router.manage_skills(args[1:])

    elif cmd in ("serve", "server"):
        router.start_server(args[1:])

    elif cmd in ("node", "nodes"):
        router.manage_nodes(args[1:])

    elif cmd in ("marketplace", "market", "mp"):
        router.marketplace(args[1:])

    elif cmd in ("completions",):
        router.shell_completions()

    elif cmd in ("version", "v", "--version", "-v"):
        Theme.version_info()

    elif cmd in ("help", "h", "--help", "-h"):
        router.show_help()

    elif cmd in ("init",):
        router.init_project(args[1:])

    elif cmd in ("daemon", "d"):
        router.daemon(args[1:])

    elif cmd in ("task",):
        router.run_task(args[1:])

    elif cmd in ("web",):
        router.start_web_ui(args[1:])

    else:
        # Try as a direct prompt
        show_mini_banner()
        engine.initialize()
        query = " ".join(args)
        asyncio.run(engine.chat(query))


if __name__ == "__main__":
    main()
