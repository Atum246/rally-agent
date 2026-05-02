"""
🟣 Rally Agent — First-Run Setup Wizard
Beautiful interactive onboarding for terminal and web.
Guides users through provider selection, API key configuration, and personalization.
"""

import os
import json
import logging
import asyncio
from typing import Any, Optional

logger = logging.getLogger("rally.onboarding")


# ═══════════════════════════════════════════════════════════════
# 📋 Provider Setup Guides
# ═══════════════════════════════════════════════════════════════

PROVIDER_GUIDES: dict[str, dict] = {
    "openai": {
        "name": "OpenAI",
        "description": "GPT-4o, GPT-4, o1, o3 — The industry standard",
        "icon": "🟢",
        "url": "https://platform.openai.com/api-keys",
        "how_to_get_key": (
            "1. Go to platform.openai.com\n"
            "   2. Sign in or create an account\n"
            "   3. Navigate to API Keys\n"
            "   4. Click 'Create new secret key'\n"
            "   5. Copy the key (starts with 'sk-')"
        ),
        "env_var": "OPENAI_API_KEY",
        "key_prefix": "sk-",
        "models": [
            "gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "o1", "o3", "o3-mini", "o4-mini",
        ],
        "default_model": "gpt-4o",
    },
    "anthropic": {
        "name": "Anthropic",
        "description": "Claude 4, Claude 3.5 — Thoughtful & safe AI",
        "icon": "🟤",
        "url": "https://console.anthropic.com/settings/keys",
        "how_to_get_key": (
            "1. Go to console.anthropic.com\n"
            "   2. Sign in or create an account\n"
            "   3. Go to Settings → API Keys\n"
            "   4. Click 'Create Key'\n"
            "   5. Copy the key (starts with 'sk-ant-')"
        ),
        "env_var": "ANTHROPIC_API_KEY",
        "key_prefix": "sk-ant-",
        "models": [
            "claude-sonnet-4-20250514", "claude-opus-4-20250514",
            "claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022",
        ],
        "default_model": "claude-sonnet-4-20250514",
    },
    "google": {
        "name": "Google AI",
        "description": "Gemini 2.5, Gemini 2.0 — Massive context window",
        "icon": "🔵",
        "url": "https://aistudio.google.com/apikey",
        "how_to_get_key": (
            "1. Go to aistudio.google.com\n"
            "   2. Sign in with your Google account\n"
            "   3. Click 'Get API Key'\n"
            "   4. Create a new API key\n"
            "   5. Copy the key"
        ),
        "env_var": "GOOGLE_API_KEY",
        "key_prefix": "",
        "models": [
            "gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash",
        ],
        "default_model": "gemini-2.5-flash",
    },
    "groq": {
        "name": "Groq",
        "description": "Ultra-fast inference on LPU hardware",
        "icon": "⚡",
        "url": "https://console.groq.com/keys",
        "how_to_get_key": (
            "1. Go to console.groq.com\n"
            "   2. Sign in or create an account\n"
            "   3. Navigate to API Keys\n"
            "   4. Click 'Create API Key'\n"
            "   5. Copy the key (starts with 'gsk_')"
        ),
        "env_var": "GROQ_API_KEY",
        "key_prefix": "gsk_",
        "models": [
            "llama-3.3-70b-versatile", "llama-3.1-8b-instant",
            "mixtral-8x7b-32768", "gemma2-9b-it",
        ],
        "default_model": "llama-3.3-70b-versatile",
    },
    "nvidia": {
        "name": "NVIDIA NIM",
        "description": "Fast inference on NVIDIA GPUs — best open models",
        "icon": "🟢",
        "url": "https://build.nvidia.com/settings/api-keys",
        "how_to_get_key": (
            "1. Go to build.nvidia.com\n"
            "   2. Sign in or create an NVIDIA account\n"
            "   3. Go to Settings → API Keys\n"
            "   4. Generate a new API key\n"
            "   5. Copy the key (starts with 'nvapi-')"
        ),
        "env_var": "NVIDIA_API_KEY",
        "key_prefix": "nvapi-",
        "models": [
            "meta/llama-3.1-405b-instruct", "meta/llama-3.1-70b-instruct",
            "meta/llama-3.3-70b-instruct", "nvidia/llama-3.1-nemotron-70b-instruct",
            "deepseek-ai/deepseek-r1", "mistralai/mistral-large-latest",
        ],
        "default_model": "meta/llama-3.1-70b-instruct",
    },
    "deepseek": {
        "name": "DeepSeek",
        "description": "Chinese AI powerhouse — great reasoning models",
        "icon": "🐋",
        "url": "https://platform.deepseek.com/api_keys",
        "how_to_get_key": (
            "1. Go to platform.deepseek.com\n"
            "   2. Sign in or create an account\n"
            "   3. Navigate to API Keys\n"
            "   4. Create a new key\n"
            "   5. Copy the key (starts with 'sk-')"
        ),
        "env_var": "DEEPSEEK_API_KEY",
        "key_prefix": "sk-",
        "models": [
            "deepseek-chat", "deepseek-reasoner", "deepseek-coder",
        ],
        "default_model": "deepseek-chat",
    },
    "ollama": {
        "name": "Ollama",
        "description": "Run models locally — no API key needed",
        "icon": "🦙",
        "url": "https://ollama.com/download",
        "how_to_get_key": (
            "No API key needed! Ollama runs on your machine.\n\n"
            "   1. Install: curl -fsSL https://ollama.com/install.sh | sh\n"
            "   2. Pull a model: ollama pull llama3.2\n"
            "   3. It runs on http://localhost:11434 by default"
        ),
        "env_var": "",
        "key_prefix": "",
        "models": [
            "llama3.2", "llama3.1", "mistral", "mixtral",
            "codellama", "phi3", "gemma2", "qwen2.5", "deepseek-v2",
        ],
        "default_model": "llama3.2",
    },
    "openrouter": {
        "name": "OpenRouter",
        "description": "300+ models from every provider — one API key",
        "icon": "🔀",
        "url": "https://openrouter.ai/settings/keys",
        "how_to_get_key": (
            "1. Go to openrouter.ai\n"
            "   2. Sign in or create an account\n"
            "   3. Go to Settings → Keys\n"
            "   4. Create a new key\n"
            "   5. Copy the key (starts with 'sk-or-')"
        ),
        "env_var": "OPENROUTER_API_KEY",
        "key_prefix": "sk-or-",
        "models": [
            "anthropic/claude-sonnet-4", "openai/gpt-4o",
            "google/gemini-2.5-pro", "meta-llama/llama-3.3-70b-instruct",
            "deepseek/deepseek-chat",
        ],
        "default_model": "anthropic/claude-sonnet-4",
    },
}


# ═══════════════════════════════════════════════════════════════
# 🧙 Setup Wizard
# ═══════════════════════════════════════════════════════════════

class SetupWizard:
    """First-run setup wizard — guides user through initial configuration.

    Supports both interactive terminal mode and web API mode.
    """

    def __init__(self, config: Any):
        self.config = config

    def is_first_run(self) -> bool:
        """Check if this is the first run (no API keys configured)."""
        env_keys = [
            "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY",
            "GROQ_API_KEY", "NVIDIA_API_KEY", "DEEPSEEK_API_KEY",
            "OPENROUTER_API_KEY", "MISTRAL_API_KEY", "TOGETHER_API_KEY",
        ]
        for key in env_keys:
            if os.environ.get(key):
                return False

        # Check config for stored keys
        if hasattr(self.config, "get_provider_keys"):
            keys = self.config.get_provider_keys()
            if any(v for v in keys.values() if v):
                return False

        if hasattr(self.config, "get"):
            providers = self.config.get("providers", {})
            if isinstance(providers, dict):
                for provider_config in providers.values():
                    if isinstance(provider_config, dict):
                        if provider_config.get("api_key"):
                            return False

        # Check if setup has been completed before
        if hasattr(self.config, "get") and self.config.get("setup.completed", False):
            return False

        return True

    def mark_setup_complete(self) -> None:
        """Mark the setup as completed."""
        if hasattr(self.config, "set"):
            self.config.set("setup.completed", True)
        elif hasattr(self.config, "data") and isinstance(self.config.data, dict):
            self.config.data.setdefault("setup", {})["completed"] = True

    async def run_interactive(self) -> None:
        """Run the interactive setup wizard in terminal."""
        try:
            from rich.console import Console
            from rich.panel import Panel
            from rich.prompt import Prompt, Confirm, IntPrompt
            from rich.text import Text
            from rich.table import Table
            from rich.columns import Columns
            from rich import box
        except ImportError:
            print("⚠️  Rich library not found. Running basic wizard...\n")
            await self._run_basic_interactive()
            return

        console = Console()

        # ── Step 1: Welcome Banner ─────────────────────────────
        console.print()
        welcome = Text()
        welcome.append("⚡ ", style="bold yellow")
        welcome.append("Welcome to Rally Agent!", style="bold magenta")
        welcome.append("\n\n")
        welcome.append("Your self-hosted AI platform.", style="dim")
        welcome.append("\n")
        welcome.append("Let's get you set up in under 2 minutes.", style="dim")

        console.print(Panel(
            welcome,
            title="[bold magenta]🟣 Rally Agent Setup[/]",
            border_style="magenta",
            box=box.DOUBLE,
            padding=(1, 2),
        ))
        console.print()

        # ── Step 2: Choose Provider ────────────────────────────
        console.print("[bold cyan]Step 1/6:[/] Choose your AI provider\n")

        providers_table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold magenta")
        providers_table.add_column("#", style="dim", width=3)
        providers_table.add_column("Provider", style="bold")
        providers_table.add_column("Description")
        providers_table.add_column("Key Required", justify="center")

        provider_list = list(PROVIDER_GUIDES.items())
        for i, (key, guide) in enumerate(provider_list, 1):
            needs_key = "🔑" if guide.get("env_var") else "🆓"
            providers_table.add_row(
                str(i),
                f"{guide['icon']} {guide['name']}",
                guide["description"],
                needs_key,
            )

        console.print(providers_table)
        console.print()

        choice = IntPrompt.ask(
            "[bold]Pick a provider[/]",
            default=1,
            choices=[str(i) for i in range(1, len(provider_list) + 1)],
        )
        provider_key, provider_guide = provider_list[choice - 1]
        console.print(f"\n  ✅ Selected: [bold]{provider_guide['icon']} {provider_guide['name']}[/]\n")

        # ── Step 3: Enter API Key ──────────────────────────────
        api_key = ""
        if provider_guide.get("env_var"):
            console.print(f"[bold cyan]Step 2/6:[/] Configure API key\n")
            console.print(Panel(
                provider_guide["how_to_get_key"],
                title=f"[bold]{provider_guide['icon']} Get your {provider_guide['name']} API key[/]",
                border_style="cyan",
                padding=(1, 2),
            ))
            console.print(f"  🔗 [link={provider_guide['url']}]{provider_guide['url']}[/link]\n")

            api_key = Prompt.ask(
                "  [bold]Paste your API key[/]",
                password=True,
            )

            # Basic validation
            if provider_guide.get("key_prefix") and not api_key.startswith(provider_guide["key_prefix"]):
                console.print(f"  [yellow]⚠️  Key usually starts with '{provider_guide['key_prefix']}'. Proceeding anyway.[/]\n")

            # Save to environment
            os.environ[provider_guide["env_var"]] = api_key
            console.print("  ✅ API key configured!\n")
        else:
            console.print(f"  ℹ️  {provider_guide['name']} doesn't need an API key (runs locally).\n")

        # ── Step 4: Choose Default Model ───────────────────────
        console.print(f"[bold cyan]Step 3/6:[/] Choose default model\n")

        models = provider_guide.get("models", [])
        default_model = provider_guide.get("default_model", models[0] if models else "default")

        models_table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold magenta")
        models_table.add_column("#", style="dim", width=3)
        models_table.add_column("Model", style="bold")
        models_table.add_column("Default", justify="center")

        for i, model in enumerate(models, 1):
            is_default = "⭐" if model == default_model else ""
            models_table.add_row(str(i), model, is_default)

        console.print(models_table)
        console.print()

        model_choice = IntPrompt.ask(
            "[bold]Pick a model[/]",
            default=models.index(default_model) + 1 if default_model in models else 1,
            choices=[str(i) for i in range(1, len(models) + 1)],
        )
        selected_model = models[model_choice - 1]
        console.print(f"\n  ✅ Default model: [bold]{selected_model}[/]\n")

        # ── Step 5: Configure Voice (optional) ─────────────────
        console.print(f"[bold cyan]Step 4/6:[/] Voice (optional)\n")
        setup_voice = Confirm.ask("  Enable voice input/output?", default=False)
        voice_config = {}
        if setup_voice:
            voice_provider = Prompt.ask(
                "  Voice provider",
                choices=["openai", "elevenlabs", "local"],
                default="openai",
            )
            voice_config = {"enabled": True, "provider": voice_provider}
            console.print(f"  ✅ Voice enabled with {voice_provider}\n")
        else:
            console.print("  ⏭️  Skipping voice setup\n")

        # ── Step 6: Configure Browser (optional) ───────────────
        console.print(f"[bold cyan]Step 5/6:[/] Browser automation (optional)\n")
        setup_browser = Confirm.ask("  Enable browser automation?", default=False)
        browser_config = {}
        if setup_browser:
            browser_config = {"enabled": True, "headless": True}
            console.print("  ✅ Browser automation enabled\n")
        else:
            console.print("  ⏭️  Skipping browser setup\n")

        # ── Step 7: Set User Name ──────────────────────────────
        console.print(f"[bold cyan]Step 6/6:[/] Personalize\n")
        user_name = Prompt.ask("  What should we call you?", default="User")
        console.print(f"\n  ✅ Hello, [bold]{user_name}[/]! 👋\n")

        # ── Step 8: Save & Confirm ─────────────────────────────
        config_updates = {
            "providers": {
                provider_key: {
                    "api_key": api_key,
                    "default_model": selected_model,
                },
            },
            "engine": {
                "default_provider": provider_key,
                "default_model": selected_model,
                "fallback_order": [provider_key],
            },
            "user": {
                "name": user_name,
            },
            "setup": {
                "completed": True,
            },
        }
        if voice_config:
            config_updates["voice"] = voice_config
        if browser_config:
            config_updates["browser"] = browser_config

        # Apply config
        if hasattr(self.config, "update"):
            self.config.update(config_updates)
        elif hasattr(self.config, "data"):
            self.config.data.update(config_updates)

        # Save to disk
        if hasattr(self.config, "save"):
            self.config.save()

        self.mark_setup_complete()

        # Final message
        console.print(Panel(
            f"[bold green]🎉 Setup complete![/]\n\n"
            f"  Provider: {provider_guide['icon']} {provider_guide['name']}\n"
            f"  Model:    {selected_model}\n"
            f"  User:     {user_name}\n\n"
            f"[dim]Starting Rally Agent...[/]",
            title="[bold magenta]🟣 Ready to Rally[/]",
            border_style="green",
            box=box.DOUBLE,
            padding=(1, 2),
        ))
        console.print()

    async def _run_basic_interactive(self) -> None:
        """Fallback interactive wizard without Rich library."""
        print("=" * 50)
        print("  ⚡ Rally Agent — Setup Wizard")
        print("=" * 50)
        print()

        provider_list = list(PROVIDER_GUIDES.items())
        for i, (key, guide) in enumerate(provider_list, 1):
            needs_key = "🔑" if guide.get("env_var") else "🆓"
            print(f"  {i}. {guide['icon']} {guide['name']} — {guide['description']} {needs_key}")

        print()
        choice = int(input("Pick a provider [1]: ").strip() or "1")
        provider_key, provider_guide = provider_list[choice - 1]
        print(f"\n  ✅ Selected: {provider_guide['name']}\n")

        api_key = ""
        if provider_guide.get("env_var"):
            print(f"Get your key at: {provider_guide['url']}")
            api_key = input("Paste your API key: ").strip()
            os.environ[provider_guide["env_var"]] = api_key

        models = provider_guide.get("models", [])
        default_model = provider_guide.get("default_model", models[0] if models else "default")
        for i, m in enumerate(models, 1):
            marker = " ⭐" if m == default_model else ""
            print(f"  {i}. {m}{marker}")

        model_choice = int(input(f"\nPick a model [{models.index(default_model) + 1}]: ").strip() or str(models.index(default_model) + 1))
        selected_model = models[model_choice - 1]

        user_name = input("\nWhat should we call you? [User]: ").strip() or "User"

        config_updates = {
            "providers": {provider_key: {"api_key": api_key, "default_model": selected_model}},
            "engine": {"default_provider": provider_key, "default_model": selected_model},
            "user": {"name": user_name},
            "setup": {"completed": True},
        }
        if hasattr(self.config, "update"):
            self.config.update(config_updates)
        elif hasattr(self.config, "data"):
            self.config.data.update(config_updates)
        if hasattr(self.config, "save"):
            self.config.save()

        self.mark_setup_complete()
        print(f"\n  🎉 Setup complete! Welcome, {user_name}!\n")

    async def run_web(self) -> dict:
        """Return setup data for the web UI onboarding page.

        Returns a JSON-serializable dict with steps, provider options, etc.
        """
        providers = {}
        for key, guide in PROVIDER_GUIDES.items():
            providers[key] = {
                "name": guide["name"],
                "description": guide["description"],
                "icon": guide["icon"],
                "url": guide["url"],
                "how_to_get_key": guide["how_to_get_key"],
                "env_var": guide["env_var"],
                "key_prefix": guide.get("key_prefix", ""),
                "models": guide["models"],
                "default_model": guide["default_model"],
                "requires_key": bool(guide.get("env_var")),
            }

        return {
            "is_first_run": self.is_first_run(),
            "steps": [
                {"id": "welcome", "title": "Welcome to Rally Agent", "type": "info"},
                {"id": "provider", "title": "Choose AI Provider", "type": "select"},
                {"id": "api_key", "title": "Configure API Key", "type": "input"},
                {"id": "model", "title": "Choose Default Model", "type": "select"},
                {"id": "voice", "title": "Voice (Optional)", "type": "toggle"},
                {"id": "browser", "title": "Browser Automation (Optional)", "type": "toggle"},
                {"id": "name", "title": "Your Name", "type": "input"},
                {"id": "complete", "title": "All Set!", "type": "info"},
            ],
            "providers": providers,
        }

    async def complete_web_setup(self, data: dict) -> dict:
        """Process web onboarding completion data.

        Args:
            data: {
                "provider": "openai",
                "api_key": "sk-...",
                "model": "gpt-4o",
                "voice": {"enabled": false},
                "browser": {"enabled": false},
                "name": "User",
            }

        Returns:
            {"status": "ok", "config": {...}}
        """
        provider_key = data.get("provider", "")
        api_key = data.get("api_key", "")
        model = data.get("model", "")
        voice = data.get("voice", {})
        browser = data.get("browser", {})
        user_name = data.get("name", "User")

        if not provider_key:
            return {"status": "error", "error": "Provider is required"}

        guide = PROVIDER_GUIDES.get(provider_key)
        if not guide:
            return {"status": "error", "error": f"Unknown provider: {provider_key}"}

        # Validate API key requirement
        if guide.get("env_var") and not api_key:
            return {"status": "error", "error": f"{guide['name']} requires an API key"}

        # Set env var
        if guide.get("env_var") and api_key:
            os.environ[guide["env_var"]] = api_key

        if not model:
            model = guide.get("default_model", "")

        config_updates = {
            "providers": {
                provider_key: {
                    "api_key": api_key,
                    "default_model": model,
                },
            },
            "engine": {
                "default_provider": provider_key,
                "default_model": model,
                "fallback_order": [provider_key],
            },
            "user": {
                "name": user_name,
            },
            "setup": {
                "completed": True,
            },
        }
        if voice:
            config_updates["voice"] = voice
        if browser:
            config_updates["browser"] = browser

        if hasattr(self.config, "update"):
            self.config.update(config_updates)
        elif hasattr(self.config, "data"):
            self.config.data.update(config_updates)
        if hasattr(self.config, "save"):
            self.config.save()

        self.mark_setup_complete()

        return {
            "status": "ok",
            "provider": provider_key,
            "model": model,
            "name": user_name,
        }

    def get_provider_setup_guide(self, provider_name: str) -> dict:
        """Get setup guide for a specific provider.

        Returns:
            {name, description, how_to_get_key, url, env_var, models, ...}
        """
        guide = PROVIDER_GUIDES.get(provider_name)
        if not guide:
            return {
                "name": provider_name,
                "description": "Unknown provider",
                "how_to_get_key": "No guide available.",
                "url": "",
                "env_var": "",
                "models": [],
                "default_model": "",
            }
        return dict(guide)

    def get_all_provider_guides(self) -> dict[str, dict]:
        """Get all provider setup guides."""
        return {k: dict(v) for k, v in PROVIDER_GUIDES.items()}
