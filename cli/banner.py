"""
🟣 Rally Agent — ASCII Art Banners
"""

from cli.theme import console, Colors


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

MINI_BANNER = "[bold #a855f7]⚡ Rally Agent[/] [dim]|[/] [dim]The OpenClaw Killer 💀[/]"

SUBTITLE = "[#d946ef]━━━ Your AI. Your Rules. Your Data. ━━━[/]"

VERSION_LINE = "[dim]v1.0.0[/] [#22d3ee]•[/] [dim]Type [bold #c084fc]help[/] for commands, [bold #c084fc]exit[/] to quit[/]"

HELP_HINT = "[dim]Commands: [bold #c084fc]chat[/] [bold #c084fc]status[/] [bold #c084fc]agents[/] [bold #c084fc]memory[/] [bold #c084fc]tools[/] [bold #c084fc]skills[/] [bold #c084fc]config[/] [bold #c084fc]help[/][/]"


def show_banner():
    """Full startup banner"""
    console.print()
    console.print(BANNER_ART)
    console.print()
    console.print(f"    {SUBTITLE}")
    console.print(f"    {VERSION_LINE}")
    console.print()


def show_mini_banner():
    """Compact banner for subcommands"""
    console.print()
    console.print(f"  {MINI_banner}")
    console.print()


def show_status_banner(agents: list, memory_entries: int, uptime: str):
    """Status dashboard banner"""
    table = Table(
        box=box.HEAVY,
        border_style=Colors.PURPLE,
        header_style=f"bold {Colors.BRIGHT_PURPLE}",
        pad_edge=True,
    )
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="neon_green")

    table.add_row("🟢 Status", "Running")
    table.add_row("🤖 Agents", str(len(agents)))
    table.add_row("🧠 Memory", f"{memory_entries} entries")
    table.add_row("⏱️ Uptime", uptime)
    table.add_row("💻 Platform", "Linux/macOS")
    table.add_row("🔗 Version", "1.0.0")

    console.print()
    console.print(Panel(
        table,
        title="[bold #c084fc]⚡ Rally Agent Status[/]",
        border_style=Colors.PURPLE,
        box=box.DOUBLE,
    ))
    console.print()
