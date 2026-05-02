"""
🟣 Rally Agent — Hacker Purple Theme
"""

from rich.console import Console
from rich.theme import Theme as RichTheme
from rich.style import Style
from rich.text import Text
from rich.panel import Panel
from rich.table import Table
from rich import box
import datetime


# ═══════════════════════════════════════════════════════════════
# 🎨 Color Palette — Hacker Purple
# ═══════════════════════════════════════════════════════════════

class Colors:
    """Rally Agent color constants"""
    # Primary purples
    PURPLE = "#a855f7"
    BRIGHT_PURPLE = "#c084fc"
    DARK_PURPLE = "#7c3aed"
    DEEP_PURPLE = "#581c87"
    NEON_PURPLE = "#d946ef"

    # Accents
    CYAN = "#22d3ee"
    NEON_GREEN = "#4ade80"
    HOT_PINK = "#f472b6"
    ELECTRIC_BLUE = "#60a5fa"
    AMBER = "#fbbf24"
    RED = "#ef4444"

    # Neutrals
    WHITE = "#ffffff"
    LIGHT_GRAY = "#d1d5db"
    GRAY = "#6b7280"
    DARK_GRAY = "#374151"
    BG_DARK = "#0f0a1a"
    BG_PANEL = "#1a0e2e"

    # Semantic
    SUCCESS = "#4ade80"
    WARNING = "#fbbf24"
    ERROR = "#ef4444"
    INFO = "#22d3ee"
    DEBUG = "#6b7280"


# ── Rich Theme ────────────────────────────────────────────────

RALLY_THEME = RichTheme({
    "purple": f"bold {Colors.PURPLE}",
    "bright_purple": f"bold {Colors.BRIGHT_PURPLE}",
    "dark_purple": Colors.DARK_PURPLE,
    "neon": f"bold {Colors.NEON_PURPLE}",
    "cyan": f"bold {Colors.CYAN}",
    "neon_green": f"bold {Colors.NEON_GREEN}",
    "hot_pink": f"bold {Colors.HOT_PINK}",
    "electric": Colors.ELECTRIC_BLUE,
    "amber": f"bold {Colors.AMBER}",
    "danger": f"bold {Colors.RED}",
    "success": f"bold {Colors.SUCCESS}",
    "warning": f"bold {Colors.WARNING}",
    "error": f"bold {Colors.ERROR}",
    "info": f"bold {Colors.INFO}",
    "debug": Colors.DEBUG,
    "muted": Colors.GRAY,
    "panel_title": f"bold {Colors.BRIGHT_PURPLE}",
    "dim": f"dim {Colors.GRAY}",
})

console = Console(theme=RALLY_THEME)


# ═══════════════════════════════════════════════════════════════
# 🎨 Theme Utilities
# ═══════════════════════════════════════════════════════════════

class Theme:
    """Rally Agent theme utilities"""

    @staticmethod
    def info(msg: str):
        console.print(f"  [cyan]ℹ[/] {msg}")

    @staticmethod
    def success(msg: str):
        console.print(f"  [neon_green]✓[/] {msg}")

    @staticmethod
    def warning(msg: str):
        console.print(f"  [amber]⚠[/] {msg}")

    @staticmethod
    def error(msg: str):
        console.print(f"  [danger]✗[/] {msg}")

    @staticmethod
    def step(msg: str):
        console.print(f"\n  [bright_purple]━━━ {msg} ━━━[/]")

    @staticmethod
    def muted(msg: str):
        console.print(f"  [dim]{msg}[/]")

    @staticmethod
    def version_info():
        from core.version import __version__
        console.print(f"\n  [bright_purple]Rally Agent[/] [cyan]v{__version__}[/]")
        console.print(f"  [dim]The OpenClaw Killer 💀⚡[/]\n")

    @staticmethod
    def purple(text: str) -> str:
        return f"[purple]{text}[/]"

    @staticmethod
    def neon(text: str) -> str:
        return f"[neon]{text}[/]"

    @staticmethod
    def cyan(text: str) -> str:
        return f"[cyan]{text}[/]"

    @staticmethod
    def panel(title: str, content: str, **kwargs) -> Panel:
        return Panel(
            content,
            title=f"[panel_title]{title}[/]",
            border_style=Colors.PURPLE,
            box=box.HEAVY,
            **kwargs
        )

    @staticmethod
    def create_table(title: str = None, show_header: bool = True) -> Table:
        t = Table(
            title=f"[panel_title]{title}[/]" if title else None,
            box=box.HEAVY,
            border_style=Colors.PURPLE,
            header_style=f"bold {Colors.BRIGHT_PURPLE}",
            show_header=show_header,
            pad_edge=True,
            expand=True,
        )
        return t

    @staticmethod
    def timestamp() -> str:
        return datetime.datetime.now().strftime("%H:%M:%S")

    @staticmethod
    def user_prompt(name: str = "You") -> str:
        ts = Theme.timestamp()
        return f"[dim]{ts}[/] [hot_pink]❯[/] [bright_purple]{name}[/] [hot_pink]❯❯[/] "

    @staticmethod
    def agent_response(name: str = "Rally") -> str:
        ts = Theme.timestamp()
        return f"[dim]{ts}[/] [neon]⚡[/] [neon]{name}[/] [purple]❯❯[/] "

    @staticmethod
    def thinking_indicator():
        return "[dim][purple]⠋[/] Thinking...[/]"

    @staticmethod
    def tool_call(name: str, args: str = ""):
        ts = Theme.timestamp()
        console.print(f"  [dim]{ts}[/] [cyan]🔧 {name}[/] [dim]{args}[/]")

    @staticmethod
    def separator():
        console.print(f"  [dim]{'─' * 60}[/]")

    @staticmethod
    def box_border(text: str) -> Panel:
        return Panel(
            f"[bright_purple]{text}[/]",
            border_style=Colors.NEON_PURPLE,
            box=box.DOUBLE,
        )
