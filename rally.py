#!/usr/bin/env python3
"""
╔═══════════════════════════════════════════════════════════════╗
║  🟣 RALLY AGENT v2.0 — The OpenClaw Killer                   ║
║  Your AI. Your Rules. Your Data.                             ║
║  36 providers • 52 channels • 12 agents • swarm intelligence ║
║  voice • browser automation • RAG • plugins • multi-user     ║
╚═══════════════════════════════════════════════════════════════╝
"""

import sys
import os
import asyncio
import signal
import logging

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── Logging ──────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("rally")


def setup_signal_handlers(engine):
    """Graceful shutdown on Ctrl+C"""
    def handler(signum, frame):
        print()
        logger.info("Shutting down Rally Agent...")
        engine.shutdown()
        sys.exit(0)
    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)


def main():
    """Main entry point for Rally Agent v2.0"""
    from core.config import RallyConfig
    from core.engine import RallyEngine

    config = RallyConfig.load()
    engine = RallyEngine(config)
    setup_signal_handlers(engine)

    args = sys.argv[1:]

    # No args → interactive mode
    if not args:
        from cli.banner import show_banner
        from cli.repl import RallyREPL
        show_banner()
        engine.initialize()
        repl = RallyREPL(engine)
        repl.run()
        return

    # Command routing
    cmd = args[0].lower()

    # ── Core Commands ─────────────────────────────────────────
    if cmd in ("chat", "c"):
        from cli.banner import show_mini_banner
        from cli.repl import RallyREPL
        show_mini_banner()
        engine.initialize()
        repl = RallyREPL(engine)
        repl.run()

    elif cmd in ("status", "s"):
        engine.initialize()
        engine.show_status()

    elif cmd in ("version", "v", "--version", "-v"):
        from cli.theme import Theme
        Theme.version_info()

    elif cmd in ("help", "h", "--help", "-h"):
        from cli.commands import CommandRouter
        router = CommandRouter(engine)
        router.show_help()

    # ── Configuration ─────────────────────────────────────────
    elif cmd in ("config", "cfg"):
        from cli.commands import CommandRouter
        router = CommandRouter(engine)
        router.manage_config(args[1:])

    # ── Agent System ──────────────────────────────────────────
    elif cmd in ("agents", "a"):
        engine.initialize()
        if len(args) > 1 and args[1] == "list":
            engine.show_agents()
        elif len(args) > 2 and args[1] == "spawn":
            engine.spawn_agent(args[2])
        else:
            engine.show_agents()

    elif cmd in ("swarm",):
        engine.initialize()
        task = " ".join(args[1:])
        if task:
            asyncio.run(engine.run_swarm_task(task))
        else:
            print("Usage: rally swarm <task description>")

    # ── Memory & RAG ──────────────────────────────────────────
    elif cmd in ("memory", "mem"):
        engine.initialize()
        if len(args) < 2:
            engine.show_memory_stats()
        elif args[1] == "search":
            query = " ".join(args[2:])
            engine.search_memory(query)
        elif args[1] == "clear":
            engine.clear_memory()
        elif args[1] == "export" and len(args) > 2:
            engine.memory.export(args[2])
        elif args[1] == "import" and len(args) > 2:
            engine.memory.import_entries(args[2])
        else:
            print("Usage: rally memory [search <q> | clear | export | import]")

    elif cmd in ("rag",):
        engine.initialize()
        if len(args) < 2:
            print("Usage: rally rag [ingest <path> | search <query> | list | remove <path>]")
        elif args[1] == "ingest" and len(args) > 2:
            path = " ".join(args[2:])
            asyncio.run(engine.ingest_document(path))
        elif args[1] == "search" and len(args) > 2:
            query = " ".join(args[2:])
            asyncio.run(engine.rag_search(query))
        elif args[1] == "list":
            engine.list_rag_documents()
        elif args[1] == "remove" and len(args) > 2:
            engine.remove_rag_document(args[2])

    # ── Tools ─────────────────────────────────────────────────
    elif cmd in ("tools", "t"):
        engine.initialize()
        engine.show_tools()

    elif cmd in ("skills", "sk"):
        engine.initialize()
        from cli.commands import CommandRouter
        router = CommandRouter(engine)
        router.manage_skills(args[1:])

    # ── Browser Automation ────────────────────────────────────
    elif cmd in ("browser", "br"):
        engine.initialize()
        if len(args) < 2:
            print("Usage: rally browser [launch | go <url> | screenshot | click <sel> | type <sel> <text> | close]")
        else:
            result = asyncio.run(engine.browser_command(args[1], " ".join(args[2:])))
            print(result)

    # ── Sandboxed Execution ───────────────────────────────────
    elif cmd in ("sandbox", "sb"):
        engine.initialize()
        if len(args) < 2:
            print("Usage: rally sandbox [run <lang> <code> | exec <command>]")
        else:
            result = asyncio.run(engine.sandbox_command(args[1], " ".join(args[2:])))
            print(result)

    # ── Voice ─────────────────────────────────────────────────
    elif cmd in ("voice",):
        engine.initialize()
        if len(args) < 2:
            print("Usage: rally voice [start | stop | config | speak <text>]")
        elif args[1] == "start":
            asyncio.run(engine.start_voice())
        elif args[1] == "stop":
            engine.stop_voice()
        elif args[1] == "speak":
            text = " ".join(args[2:])
            asyncio.run(engine.speak(text))

    # ── Plugins ───────────────────────────────────────────────
    elif cmd in ("plugins", "plugin", "mp"):
        engine.initialize()
        if len(args) < 2:
            engine.list_plugins()
        elif args[1] == "list":
            engine.list_plugins()
        elif args[1] == "install" and len(args) > 2:
            asyncio.run(engine.install_plugin(args[2]))
        elif args[1] == "remove" and len(args) > 2:
            engine.remove_plugin(args[2])
        elif args[1] == "enable" and len(args) > 2:
            engine.enable_plugin(args[2])
        elif args[1] == "disable" and len(args) > 2:
            engine.disable_plugin(args[2])

    # ── Users ─────────────────────────────────────────────────
    elif cmd in ("users", "user"):
        engine.initialize()
        if len(args) < 2:
            engine.list_users()
        elif args[1] == "list":
            engine.list_users()
        elif args[1] == "add" and len(args) > 2:
            engine.add_user(args[2])
        elif args[1] == "remove" and len(args) > 2:
            engine.remove_user(args[2])
        elif args[1] == "role" and len(args) > 3:
            engine.set_user_role(args[2], args[3])

    # ── Observability ─────────────────────────────────────────
    elif cmd in ("metrics", "met"):
        engine.initialize()
        if len(args) > 1 and args[1] == "export":
            engine.export_metrics()
        else:
            engine.show_metrics()

    elif cmd in ("security", "sec"):
        engine.initialize()
        engine.show_security_status()

    # ── Web UI ────────────────────────────────────────────────
    elif cmd in ("web",):
        engine.initialize()
        port = int(args[1]) if len(args) > 1 else 8778
        from web.server import start_web_server
        start_web_server(engine, port)

    elif cmd in ("serve", "server"):
        engine.initialize()
        port = int(args[1]) if len(args) > 1 else 8777
        from web.server import start_web_server
        start_web_server(engine, port)

    # ── Daemon ────────────────────────────────────────────────
    elif cmd in ("daemon", "d"):
        if len(args) > 1 and args[1] == "start":
            engine.initialize()
            logger.info("Starting Rally Agent daemon...")
            from web.server import start_web_server
            start_web_server(engine, 8778)
        else:
            print("Usage: rally daemon start")

    # ── Direct Prompt ─────────────────────────────────────────
    else:
        from cli.banner import show_mini_banner
        show_mini_banner()
        engine.initialize()
        query = " ".join(args)
        asyncio.run(engine.chat(query))


if __name__ == "__main__":
    main()
