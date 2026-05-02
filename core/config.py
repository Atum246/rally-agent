"""
🟣 Rally Agent — Configuration System
"""

import os
import sys
from pathlib import Path
from typing import Any, Optional
import json


class RallyConfig:
    """Configuration manager for Rally Agent"""

    DEFAULT_CONFIG = {
        "agent": {
            "name": "Rally",
            "version": "1.0.0",
            "default_model": "auto",
            "thinking": True,
            "max_context": 128000,
            "personality": "helpful",
        },
        "cli": {
            "theme": "hacker_purple",
            "animations": True,
            "banner": True,
            "compact": False,
            "syntax_highlight": True,
            "show_timestamps": True,
            "emoji": True,
        },
        "memory": {
            "backend": "hybrid",
            "vector_store": "local",
            "max_entries": 10000,
            "auto_consolidate": True,
            "encryption": True,
        },
        "security": {
            "confirm_dangerous": True,
            "audit_log": True,
            "max_file_ops": 100,
            "sandbox_exec": True,
            "blocked_commands": ["rm -rf /", "mkfs", "dd if="],
        },
        "tools": {
            "web_search": True,
            "file_ops": True,
            "exec": True,
            "browser": True,
            "code_exec": True,
        },
        "agents": {
            "max_parallel": 5,
            "auto_delegate": True,
            "orchestrator": True,
        },
        "providers": {},
    }

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or self._default_path()
        self.data: dict = {}
        self._load()

    @staticmethod
    def _default_path() -> str:
        home = Path.home()
        return str(home / ".rally-agent" / "config" / "rally.toml")

    @classmethod
    def load(cls, path: Optional[str] = None) -> "RallyConfig":
        return cls(path)

    def _load(self):
        """Load configuration from file"""
        if os.path.exists(self.config_path):
            try:
                import tomllib
                with open(self.config_path, "rb") as f:
                    self.data = tomllib.load(f)
            except ImportError:
                try:
                    import tomli
                    with open(self.config_path, "rb") as f:
                        self.data = tomli.load(f)
                except ImportError:
                    # Fallback to JSON parsing of TOML-like structure
                    self.data = self._parse_toml_fallback()
        else:
            self.data = self.DEFAULT_CONFIG.copy()
            self.save()

    def _parse_toml_fallback(self) -> dict:
        """Fallback TOML parser"""
        data = self.DEFAULT_CONFIG.copy()
        try:
            with open(self.config_path, "r") as f:
                current_section = None
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if line.startswith("[") and line.endswith("]"):
                        section = line[1:-1]
                        current_section = section
                        if section not in data:
                            data[section] = {}
                    elif "=" in line and current_section:
                        key, _, value = line.partition("=")
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        if current_section not in data:
                            data[current_section] = {}
                        data[current_section][key] = self._parse_value(value)
        except Exception:
            pass
        return data

    @staticmethod
    def _parse_value(value: str) -> Any:
        """Parse a TOML value"""
        if value.lower() in ("true", "yes", "on"):
            return True
        if value.lower() in ("false", "no", "off"):
            return False
        try:
            return int(value)
        except ValueError:
            pass
        try:
            return float(value)
        except ValueError:
            pass
        if value.startswith("[") and value.endswith("]"):
            return [v.strip().strip('"') for v in value[1:-1].split(",")]
        return value

    def save(self):
        """Save configuration to file"""
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        # Save as JSON for simplicity (TOML writing is complex)
        json_path = self.config_path.replace(".toml", ".json")
        with open(json_path, "w") as f:
            json.dump(self.data, f, indent=2)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a config value using dot notation"""
        keys = key.split(".")
        value = self.data
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
            if value is None:
                return default
        return value

    def set(self, key: str, value: Any):
        """Set a config value using dot notation"""
        keys = key.split(".")
        data = self.data
        for k in keys[:-1]:
            if k not in data:
                data[k] = {}
            data = data[k]
        data[keys[-1]] = value
        self.save()

    def get_provider_keys(self) -> dict:
        """Get configured API keys"""
        providers = self.get("providers", {})
        env_keys = {
            "openai": os.environ.get("OPENAI_API_KEY"),
            "anthropic": os.environ.get("ANTHROPIC_API_KEY"),
            "google": os.environ.get("GOOGLE_API_KEY"),
            "groq": os.environ.get("GROQ_API_KEY"),
            "mistral": os.environ.get("MISTRAL_API_KEY"),
            "deepseek": os.environ.get("DEEPSEEK_API_KEY"),
            "ollama": os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
        }
        for k, v in env_keys.items():
            if v and k not in providers:
                providers[k] = v
        return providers
