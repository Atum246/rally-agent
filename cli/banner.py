"""
🟣 Rally Agent — ASCII Art Banners & System Info (v2)
Updated with new ASCII art, system info panel, and startup sequence.
"""

from __future__ import annotations

import os
import platform
import time
from typing import Optional

from cli.theme import console, Colors, Theme
from rich.panel import Panel
from rich.table import Table
from rich import box
from rich.text import Text


# ═══════════════════════════════════════════════════════════════
# ASCII Art
# ═══════════════════════════════════════════════════════════════

BANNER_ART = r"""
[bold #a855f7]
    ██████╗  █████╗ ██╗     ██╗     ██╗   ██╗
    ██╔══██╗██╔══██╗██║     ██║     ╚██╗ ██╔╝
    ██████╔╝███████║██║     ██║      ╚████╔╝
    ██╔══██╗██╔══██║██║     ██║       ╚██╔╝
    ██║  ██║██║  ██║███████╗███████╗   ██║
    ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝╚══════╝   ╚═╝
[/]
[bold #c084fc]
           █████╗  ██████╗ ███████╗███╗   ██╗████████╗
          ██╔══██╗██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝
          ███████║██║  ███╗█████╗  ██╔██╗ ██║   ██║
          ██╔══██║██║   ██║██╔══╝  ██║╚██╗██║   ██║
          ██║  ██║╚██████╔╝███████╗██║ ╚████║   ██║
          ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝
[/]"""

# Compact banner for subcommands and inline use
MINI_BANNER = "[bold #a855f7]⚡ Rally Agent[/] [dim]|[/] [dim]Your AI. Your Rules. Your Data.[/]"

# Tagline
SUBTITLE = "[#d946ef]━━━ Autonomous AI Development Platform ━━━[/]"

# Version line with command hints
VERSION_LINE = (
    "[dim]v1.0.0[/] [#22d3ee]•[/] "
    "[dim]Type [bold #c084fc]help[/] for commands, [bold #c084fc]exit[/] to quit[/]"
)

# Quick-start hint for REPL
HELP_HINT = (
    "[dim]Commands: "
    "[bold #c084fc]chat[/] "
    "[bold #c084fc]status[/] "
    "[bold #c084fc]agents[/] "
    "[bold #c084fc]memory[/] "
    "[bold #c084fc]voice[/] "
    "[bold #c084fc]swarm[/] "
    "[bold #c084fc]browser[/] "
    "[bold #c084fc]sandbox[/] "
    "[bold #c084fc]rag[/] "
    "[bold #c084fc]branch[/] "
    "[bold #c084fc]metrics[/] "
    "[bold #c084fc]plugins[/] "
    "[bold #c084fc]config[/] "
    "[bold #c084fc]help[/]"
    "[/]"
)

# Feature highlights for startup
FEATURES = [
    ("🧠", "Memory", "Vector-semantic memory with hybrid search"),
    ("🤖", "Agents", "10+ specialized AI agents + swarm intelligence"),
    ("🎤", "Voice", "STT/TTS with Whisper, Edge TTS, ElevenLabs"),
    ("🌐", "Browser", "Playwright-powered browser automation"),
    ("📦", "Sandbox", "Docker/subprocess sandboxed code execution"),
    ("🧩", "Plugins", "Dynamic plugin system with marketplace"),
    ("📚", "RAG", "Document ingestion, search, and citation"),
    ("🌿", "Branching", "Git-like conversation branching"),
    ("🔒", "Security", "RBAC, audit logs, secrets vault, sandboxing"),
    ("📊", "Metrics", "Token usage, request queue, observability"),
]


# ═══════════════════════════════════════════════════════════════
# Banner Functions
# ═══════════════════════════════════════════════════════════════

def show_banner() -> None:
    """Full startup banner with ASCII art, tagline, and feature list."""
    console.print()
    console.print(BANNER_ART)
    console.print()
    console.print(f"    {SUBTITLE}")
    console.print(f"    {VERSION_LINE}")
    console.print()

    # Feature grid
    table = Table(
        box=None,
        show_header=False,
        pad_edge=False,
        padding=(0, 2),
    )
    table.add_column(style="dim", width=2)
    table.add_column(style="bold #c084fc", width=10)
    table.add_column(style="dim", width=50)

    for emoji, name, desc in FEATURES:
        table.add_row(emoji, name, desc)

    console.print(Panel(
        table,
        title="[bold #c084fc]🚀 Capabilities[/]",
        border_style=Colors.PURPLE,
        box=box.HEAVY,
        padding=(0, 1),
    ))
    console.print()


def show_mini_banner() -> None:
    """Compact banner for subcommands."""
    console.print()
    console.print(f"  {MINI_BANNER}")
    console.print()


def show_startup_info(
    *,
    agents_count: int = 0,
    memory_entries: int = 0,
    tools_count: int = 0,
    model: str = "auto",
    voice_available: bool = False,
    rag_docs: int = 0,
) -> None:
    """Show startup system info panel."""
    table = Table(
        box=box.HEAVY,
        border_style=Colors.PURPLE,
        header_style=f"bold {Colors.BRIGHT_PURPLE}",
        pad_edge=True,
    )
    table.add_column("Component", style="cyan", width=16)
    table.add_column("Status", style="neon_green")
    table.add_column("Details", style="dim")

    # System
    table.add_row("🟢 System", "Running", platform.system())
    table.add_row("🧠 Model", model, "Auto-select enabled" if model == "auto" else "")
    table.add_row("🤖 Agents", str(agents_count), "Specialized + swarm")
    table.add_row("🧠 Memory", f"{memory_entries} entries", "Vector + BM25 hybrid")
    table.add_row("🔧 Tools", str(tools_count), "Function calling enabled")

    # Voice
    voice_status = "✅ Available" if voice_available else "❌ Not available"
    table.add_row("🎤 Voice", voice_status, "STT + TTS")

    # RAG
    table.add_row("📚 RAG", f"{rag_docs} documents", "PDF, DOCX, code, web")

    # Platform info
    table.add_row("💻 Platform", f"{platform.system()} {platform.machine()}", platform.node())

    console.print()
    console.print(Panel(
        table,
        title="[bold #c084fc]⚡ Rally Agent Status[/]",
        border_style=Colors.PURPLE,
        box=box.DOUBLE,
    ))
    console.print()


def show_status_banner(
    agents: list,
    memory_entries: int,
    uptime: str,
    model: str = "auto",
    branch: str = "main",
    tokens_used: int = 0,
) -> None:
    """Status dashboard banner with full system info."""
    table = Table(
        box=box.HEAVY,
        border_style=Colors.PURPLE,
        header_style=f"bold {Colors.BRIGHT_PURPLE}",
        pad_edge=True,
    )
    table.add_column("Property", style="cyan", width=18)
    table.add_column("Value", style="neon_green")

    table.add_row("🟢 Status", "Running")
    table.add_row("🧠 Model", model)
    table.add_row("🌿 Branch", branch)
    table.add_row("🤖 Agents", str(len(agents)))
    table.add_row("🧠 Memory", f"{memory_entries} entries")
    table.add_row("📊 Tokens Used", f"{tokens_used:,}")
    table.add_row("⏱️ Uptime", uptime)
    table.add_row("💻 Platform", f"{platform.system()} {platform.machine()}")
    table.add_row("🔗 Version", "1.0.0 NEXUS")

    console.print()
    console.print(Panel(
        table,
        title="[bold #c084fc]⚡ Rally Agent Status[/]",
        border_style=Colors.PURPLE,
        box=box.DOUBLE,
    ))
    console.print()


def show_quick_help() -> None:
    """Show quick help panel for REPL users."""
    help_text = """
[bold #c084fc]⚡ Quick Reference[/]

[cyan]Chat:[/]  Just type naturally — Rally understands context.

[cyan]Slash Commands (in REPL):[/]
  /help              Show full help
  /status            System status
  /voice             Toggle voice mode
  /memory            Memory operations
  /agents            List/spawn agents
  /swarm <task>      Run swarm task
  /browser           Browser automation
  /sandbox           Sandboxed execution
  /plugins           Plugin management
  /metrics           Observability dashboard
  /security          Security status
  /rag               Document search
  /branch            Conversation branching
  /feedback          Rate last response
  /model <name>      Switch model
  /think [on|off]    Toggle thinking mode
  /clear             Clear screen
  /history           Command history
  /save <file>       Save conversation
  /load <file>       Load conversation
  /config            Configuration
  /exit              Exit Rally
"""
    console.print(Panel(
        help_text.strip(),
        title="[bold #c084fc]📚 Commands[/]",
        border_style=Colors.PURPLE,
        box=box.HEAVY,
    ))


def show_welcome_sequence(
    *,
    agents_count: int = 10,
    memory_entries: int = 0,
    tools_count: int = 15,
    model: str = "auto",
    voice_available: bool = False,
    rag_docs: int = 0,
) -> None:
    """Full welcome sequence: banner + info + quick help hint."""
    show_banner()
    show_startup_info(
        agents_count=agents_count,
        memory_entries=memory_entries,
        tools_count=tools_count,
        model=model,
        voice_available=voice_available,
        rag_docs=rag_docs,
    )
