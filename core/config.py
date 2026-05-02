"""
🟣 Rally Agent — Configuration System
Production-grade config with validation, encryption, hot-reload, and profiles.
"""

import os
import sys
import json
import time
import copy
import hashlib
import threading
import logging
from pathlib import Path
from typing import Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger("rally.config")


# ═══════════════════════════════════════════════════════════════
# 🔐 Encrypted Secrets Storage
# ═══════════════════════════════════════════════════════════════

class SecretStorage:
    """Encrypted storage for API keys and sensitive config values.
    
    Uses Fernet (AES-128-CBC) when cryptography is available,
    falls back to XOR-obfuscation + base64 when it's not.
    """

    def __init__(self, key_path: Optional[str] = None):
        self._key_path = key_path or str(
            Path.home() / ".rally-agent" / "config" / ".secret_key"
        )
        self._fernet = None
        self._fallback_key: bytes = b""
        self._init_crypto()

    def _init_crypto(self) -> None:
        """Initialize the encryption backend."""
        try:
            from cryptography.fernet import Fernet

            key_dir = os.path.dirname(self._key_path)
            os.makedirs(key_dir, exist_ok=True)

            if os.path.exists(self._key_path):
                with open(self._key_path, "rb") as f:
                    key = f.read().strip()
            else:
                key = Fernet.generate_key()
                with open(self._key_path, "wb") as f:
                    f.write(key)
                os.chmod(self._key_path, 0o600)

            self._fernet = Fernet(key)
            logger.debug("SecretStorage: using Fernet encryption")
        except ImportError:
            # Fallback: XOR + base64 (not truly secure, but obscures at rest)
            self._fallback_key = hashlib.sha256(
                b"rally-agent-default-secret-key-v1"
            ).digest()
            logger.warning(
                "SecretStorage: cryptography not installed, using XOR fallback. "
                "Install with: pip install cryptography"
            )

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a string value."""
        if not plaintext:
            return ""
        if self._fernet:
            token = self._fernet.encrypt(plaintext.encode("utf-8"))
            return "enc:" + token.decode("ascii")
        # XOR fallback
        import base64
        data = plaintext.encode("utf-8")
        key = self._fallback_key
        xored = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
        return "enc:" + base64.b64encode(xored).decode("ascii")

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt a string value."""
        if not ciphertext or not ciphertext.startswith("enc:"):
            return ciphertext
        raw = ciphertext[4:]  # strip "enc:" prefix
        if self._fernet:
            try:
                return self._fernet.decrypt(raw.encode("ascii")).decode("utf-8")
            except Exception as e:
                logger.error(f"Decryption failed: {e}")
                return ""
        # XOR fallback
        import base64
        try:
            data = base64.b64decode(raw)
            key = self._fallback_key
            xored = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
            return xored.decode("utf-8")
        except Exception as e:
            logger.error(f"Fallback decryption failed: {e}")
            return ""

    def is_encrypted(self, value: str) -> bool:
        """Check if a value is encrypted."""
        return isinstance(value, str) and value.startswith("enc:")


# ═══════════════════════════════════════════════════════════════
# 📋 Config Schema Validation
# ═══════════════════════════════════════════════════════════════

class ConfigFieldType(Enum):
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    LIST = "list"
    DICT = "dict"


@dataclass
class ConfigField:
    """Schema definition for a single config field."""
    name: str
    field_type: ConfigFieldType
    default: Any = None
    required: bool = False
    description: str = ""
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    allowed_values: Optional[list] = None
    env_override: Optional[str] = None  # env var name to override this field


@dataclass
class ConfigSchema:
    """Schema for validating configuration sections."""
    section: str
    fields: list[ConfigField] = field(default_factory=list)


# ── Built-in schemas ────────────────────────────────────────

SCHEMAS: list[ConfigSchema] = [
    ConfigSchema("agent", [
        ConfigField("name", ConfigFieldType.STRING, default="Rally", description="Agent display name"),
        ConfigField("version", ConfigFieldType.STRING, default="2.0.0", description="Agent version"),
        ConfigField("default_model", ConfigFieldType.STRING, default="auto", description="Default LLM model"),
        ConfigField("thinking", ConfigFieldType.BOOLEAN, default=True, description="Enable thinking mode"),
        ConfigField("max_context", ConfigFieldType.INTEGER, default=128000, min_value=1024, max_value=2000000,
                     description="Maximum context window in tokens"),
        ConfigField("personality", ConfigFieldType.STRING, default="helpful", description="Agent personality"),
        ConfigField("max_tokens", ConfigFieldType.INTEGER, default=4096, min_value=1, max_value=100000,
                     env_override="RALLY_MAX_TOKENS"),
        ConfigField("temperature", ConfigFieldType.FLOAT, default=0.7, min_value=0.0, max_value=2.0,
                     env_override="RALLY_TEMPERATURE"),
        ConfigField("stream", ConfigFieldType.BOOLEAN, default=True, env_override="RALLY_STREAM",
                     description="Enable streaming responses"),
    ]),
    ConfigSchema("cli", [
        ConfigField("theme", ConfigFieldType.STRING, default="hacker_purple"),
        ConfigField("animations", ConfigFieldType.BOOLEAN, default=True),
        ConfigField("banner", ConfigFieldType.BOOLEAN, default=True),
        ConfigField("compact", ConfigFieldType.BOOLEAN, default=False),
        ConfigField("syntax_highlight", ConfigFieldType.BOOLEAN, default=True),
        ConfigField("show_timestamps", ConfigFieldType.BOOLEAN, default=True),
        ConfigField("emoji", ConfigFieldType.BOOLEAN, default=True),
    ]),
    ConfigSchema("memory", [
        ConfigField("backend", ConfigFieldType.STRING, default="hybrid"),
        ConfigField("vector_store", ConfigFieldType.STRING, default="local"),
        ConfigField("max_entries", ConfigFieldType.INTEGER, default=10000, min_value=100),
        ConfigField("auto_consolidate", ConfigFieldType.BOOLEAN, default=True),
        ConfigField("encryption", ConfigFieldType.BOOLEAN, default=True),
    ]),
    ConfigSchema("security", [
        ConfigField("confirm_dangerous", ConfigFieldType.BOOLEAN, default=True),
        ConfigField("audit_log", ConfigFieldType.BOOLEAN, default=True),
        ConfigField("max_file_ops", ConfigFieldType.INTEGER, default=100, min_value=1),
        ConfigField("sandbox_exec", ConfigFieldType.BOOLEAN, default=True),
        ConfigField("blocked_commands", ConfigFieldType.LIST, default=["rm -rf /", "mkfs", "dd if="]),
    ]),
    ConfigSchema("tools", [
        ConfigField("web_search", ConfigFieldType.BOOLEAN, default=True),
        ConfigField("file_ops", ConfigFieldType.BOOLEAN, default=True),
        ConfigField("exec", ConfigFieldType.BOOLEAN, default=True),
        ConfigField("browser", ConfigFieldType.BOOLEAN, default=True),
        ConfigField("code_exec", ConfigFieldType.BOOLEAN, default=True),
    ]),
    ConfigSchema("agents", [
        ConfigField("max_parallel", ConfigFieldType.INTEGER, default=5, min_value=1, max_value=50),
        ConfigField("auto_delegate", ConfigFieldType.BOOLEAN, default=True),
        ConfigField("orchestrator", ConfigFieldType.BOOLEAN, default=True),
    ]),
    ConfigSchema("engine", [
        ConfigField("request_queue_size", ConfigFieldType.INTEGER, default=100, min_value=1,
                     description="Max queued requests"),
        ConfigField("retry_max_attempts", ConfigFieldType.INTEGER, default=3, min_value=0, max_value=10,
                     env_override="RALLY_RETRY_ATTEMPTS"),
        ConfigField("retry_base_delay", ConfigFieldType.FLOAT, default=1.0, min_value=0.1, max_value=60.0,
                     description="Base retry delay in seconds"),
        ConfigField("retry_max_delay", ConfigFieldType.FLOAT, default=60.0, min_value=1.0, max_value=300.0,
                     description="Max retry delay in seconds"),
        ConfigField("circuit_breaker_threshold", ConfigFieldType.INTEGER, default=5, min_value=1, max_value=100,
                     description="Failures before circuit opens"),
        ConfigField("circuit_breaker_timeout", ConfigFieldType.FLOAT, default=60.0, min_value=5.0, max_value=600.0,
                     description="Seconds before half-open"),
        ConfigField("fallback_order", ConfigFieldType.LIST,
                     default=["anthropic", "openai", "google", "groq", "openrouter",
                              "deepseek", "mistral", "together", "fireworks", "ollama"]),
    ]),
    ConfigSchema("providers", []),
]


def validate_config(data: dict) -> list[str]:
    """Validate configuration against schemas. Returns list of errors."""
    errors: list[str] = []

    for schema in SCHEMAS:
        section_data = data.get(schema.section, {})
        if not isinstance(section_data, dict):
            errors.append(f"Section '{schema.section}' must be a dict, got {type(section_data).__name__}")
            continue

        for field_def in schema.fields:
            value = section_data.get(field_def.name)

            # Required check
            if field_def.required and value is None:
                errors.append(f"{schema.section}.{field_def.name}: required but missing")
                continue

            if value is None:
                continue

            # Type check
            type_ok = True
            if field_def.field_type == ConfigFieldType.STRING and not isinstance(value, str):
                type_ok = False
            elif field_def.field_type == ConfigFieldType.INTEGER and not isinstance(value, int):
                type_ok = False
            elif field_def.field_type == ConfigFieldType.FLOAT and not isinstance(value, (int, float)):
                type_ok = False
            elif field_def.field_type == ConfigFieldType.BOOLEAN and not isinstance(value, bool):
                type_ok = False
            elif field_def.field_type == ConfigFieldType.LIST and not isinstance(value, list):
                type_ok = False
            elif field_def.field_type == ConfigFieldType.DICT and not isinstance(value, dict):
                type_ok = False

            if not type_ok:
                errors.append(
                    f"{schema.section}.{field_def.name}: expected {field_def.field_type.value}, "
                    f"got {type(value).__name__}"
                )
                continue

            # Range check
            if field_def.min_value is not None and isinstance(value, (int, float)):
                if value < field_def.min_value:
                    errors.append(
                        f"{schema.section}.{field_def.name}: {value} < min {field_def.min_value}"
                    )
            if field_def.max_value is not None and isinstance(value, (int, float)):
                if value > field_def.max_value:
                    errors.append(
                        f"{schema.section}.{field_def.name}: {value} > max {field_def.max_value}"
                    )

            # Allowed values check
            if field_def.allowed_values is not None:
                if value not in field_def.allowed_values:
                    errors.append(
                        f"{schema.section}.{field_def.name}: {value!r} not in {field_def.allowed_values}"
                    )

    return errors


def apply_defaults(data: dict) -> dict:
    """Apply default values from schemas to config data (non-destructive)."""
    result = copy.deepcopy(data)
    for schema in SCHEMAS:
        if schema.section not in result:
            result[schema.section] = {}
        for field_def in schema.fields:
            if field_def.name not in result[schema.section] and field_def.default is not None:
                result[schema.section][field_def.name] = copy.deepcopy(field_def.default)
    return result


# ═══════════════════════════════════════════════════════════════
# 🔥 Config Hot-Reload Watcher
# ═══════════════════════════════════════════════════════════════

class ConfigWatcher:
    """Watches config file for changes and triggers reload.
    
    Uses polling (no watchdog dependency). Checks every `interval` seconds.
    """

    def __init__(self, config_path: str, interval: float = 2.0):
        self.config_path = config_path
        self.interval = interval
        self._last_mtime: float = 0.0
        self._last_hash: str = ""
        self._callbacks: list[Callable] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def on_change(self, callback: Callable) -> None:
        """Register a callback for config changes."""
        self._callbacks.append(callback)

    def start(self) -> None:
        """Start the watcher in a background thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._watch_loop, daemon=True, name="config-watcher")
        self._thread.start()
        logger.info(f"ConfigWatcher started for {self.config_path}")

    def stop(self) -> None:
        """Stop the watcher."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=self.interval + 1)
            self._thread = None

    def _watch_loop(self) -> None:
        """Background loop that checks for file changes."""
        while self._running:
            try:
                if os.path.exists(self.config_path):
                    mtime = os.path.getmtime(self.config_path)
                    if mtime != self._last_mtime:
                        # Verify content actually changed (not just touch)
                        current_hash = self._file_hash()
                        if current_hash != self._last_hash:
                            self._last_mtime = mtime
                            self._last_hash = current_hash
                            self._notify()
            except Exception as e:
                logger.error(f"ConfigWatcher error: {e}")
            time.sleep(self.interval)

    def _file_hash(self) -> str:
        """Compute SHA-256 of config file content."""
        try:
            with open(self.config_path, "rb") as f:
                return hashlib.sha256(f.read()).hexdigest()
        except Exception:
            return ""

    def _notify(self) -> None:
        """Notify all registered callbacks."""
        logger.info("Config file changed, reloading...")
        for callback in self._callbacks:
            try:
                callback()
            except Exception as e:
                logger.error(f"Config change callback error: {e}")


# ═══════════════════════════════════════════════════════════════
# 👤 Per-User Config Profiles
# ═══════════════════════════════════════════════════════════════

class UserProfile:
    """Per-user configuration profile that overrides base config."""

    def __init__(self, name: str, data_dir: str):
        self.name = name
        self.profile_path = os.path.join(data_dir, "profiles", f"{name}.json")
        self.data: dict = {}
        self._load()

    def _load(self) -> None:
        """Load profile from disk."""
        if os.path.exists(self.profile_path):
            try:
                with open(self.profile_path) as f:
                    self.data = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load profile '{self.name}': {e}")

    def save(self) -> None:
        """Save profile to disk."""
        os.makedirs(os.path.dirname(self.profile_path), exist_ok=True)
        with open(self.profile_path, "w") as f:
            json.dump(self.data, f, indent=2)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value from this profile using dot notation."""
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

    def set(self, key: str, value: Any) -> None:
        """Set a value in this profile."""
        keys = key.split(".")
        data = self.data
        for k in keys[:-1]:
            if k not in data:
                data[k] = {}
            data = data[k]
        data[keys[-1]] = value
        self.save()

    def to_dict(self) -> dict:
        return copy.deepcopy(self.data)


# ═══════════════════════════════════════════════════════════════
# ⚙️ Main Config Class
# ═══════════════════════════════════════════════════════════════

class RallyConfig:
    """Production-grade configuration manager.

    Features:
    - TOML / JSON config file support
    - Environment variable overrides (RALLY_SECTION_KEY or field.env_override)
    - Encrypted secrets storage for API keys
    - Config validation against schemas
    - Hot-reload on file change
    - Per-user config profiles
    """

    DEFAULT_CONFIG = {
        "agent": {
            "name": "Rally",
            "version": "2.0.0",
            "default_model": "auto",
            "thinking": True,
            "max_context": 128000,
            "personality": "helpful",
            "max_tokens": 4096,
            "temperature": 0.7,
            "stream": True,
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
        "engine": {
            "request_queue_size": 100,
            "retry_max_attempts": 3,
            "retry_base_delay": 1.0,
            "retry_max_delay": 60.0,
            "circuit_breaker_threshold": 5,
            "circuit_breaker_timeout": 60.0,
            "fallback_order": [
                "anthropic", "openai", "google", "groq", "openrouter",
                "deepseek", "mistral", "together", "fireworks", "ollama",
            ],
        },
        "providers": {},
    }

    def __init__(self, config_path: Optional[str] = None, profile: Optional[str] = None):
        self.config_path = config_path or self._default_path()
        self.data: dict = {}
        self._secrets = SecretStorage()
        self._watcher: Optional[ConfigWatcher] = None
        self._profile: Optional[UserProfile] = None
        self._change_callbacks: list[Callable] = []
        self._validation_errors: list[str] = []

        # Load base config
        self._load()

        # Apply env overrides
        self._apply_env_overrides()

        # Apply defaults for missing fields
        self.data = apply_defaults(self.data)

        # Validate
        self._validation_errors = validate_config(self.data)
        if self._validation_errors:
            for err in self._validation_errors:
                logger.warning(f"Config validation: {err}")

        # Load profile if specified
        if profile:
            self.load_profile(profile)

    @staticmethod
    def _default_path() -> str:
        home = Path.home()
        return str(home / ".rally-agent" / "config" / "rally.toml")

    @classmethod
    def load(cls, path: Optional[str] = None, profile: Optional[str] = None) -> "RallyConfig":
        return cls(path, profile=profile)

    # ── Loading ──────────────────────────────────────────────

    def _load(self) -> None:
        """Load configuration from file."""
        if os.path.exists(self.config_path):
            try:
                if self.config_path.endswith(".toml"):
                    self.data = self._load_toml()
                elif self.config_path.endswith(".json"):
                    with open(self.config_path) as f:
                        self.data = json.load(f)
                else:
                    # Try TOML first, fallback to JSON
                    self.data = self._load_toml()
                logger.info(f"Loaded config from {self.config_path}")
            except Exception as e:
                logger.error(f"Failed to load config: {e}")
                self.data = copy.deepcopy(self.DEFAULT_CONFIG)
        else:
            self.data = copy.deepcopy(self.DEFAULT_CONFIG)
            self.save()

    def _load_toml(self) -> dict:
        """Load TOML file with best available parser."""
        try:
            import tomllib
            with open(self.config_path, "rb") as f:
                return tomllib.load(f)
        except ImportError:
            pass
        try:
            import tomli
            with open(self.config_path, "rb") as f:
                return tomli.load(f)
        except ImportError:
            pass
        # Fallback parser
        return self._parse_toml_fallback()

    def _parse_toml_fallback(self) -> dict:
        """Fallback TOML parser for environments without tomllib/tomli."""
        data = copy.deepcopy(self.DEFAULT_CONFIG)
        try:
            with open(self.config_path, "r") as f:
                current_section: Optional[str] = None
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if line.startswith("[") and line.endswith("]"):
                        current_section = line[1:-1]
                        if current_section not in data:
                            data[current_section] = {}
                    elif "=" in line and current_section:
                        key, _, value = line.partition("=")
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        data[current_section][key] = self._parse_value(value)
        except Exception as e:
            logger.error(f"TOML fallback parse error: {e}")
        return data

    @staticmethod
    def _parse_value(value: str) -> Any:
        """Parse a TOML value string into a Python type."""
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
            inner = value[1:-1].strip()
            if not inner:
                return []
            return [v.strip().strip('"').strip("'") for v in inner.split(",")]
        return value

    # ── Environment Variable Overrides ───────────────────────

    def _apply_env_overrides(self) -> None:
        """Override config values from environment variables.

        Priority: env var > config file > default.
        Two patterns supported:
        1. RALLY_SECTION_KEY  (e.g. RALLY_AGENT_TEMPERATURE)
        2. Field-specific env_override (e.g. RALLY_MAX_TOKENS)
        """
        for schema in SCHEMAS:
            for field_def in schema.fields:
                # Pattern 1: generic RALLY_SECTION_KEY
                env_key = f"RALLY_{schema.section.upper()}_{field_def.name.upper()}"
                env_val = os.environ.get(env_key)

                # Pattern 2: specific env_override takes priority
                if field_def.env_override:
                    specific = os.environ.get(field_def.env_override)
                    if specific is not None:
                        env_val = specific

                if env_val is not None:
                    parsed = self._coerce_env_value(env_val, field_def.field_type)
                    if schema.section not in self.data:
                        self.data[schema.section] = {}
                    self.data[schema.section][field_def.name] = parsed
                    logger.debug(f"Env override: {schema.section}.{field_def.name} = {parsed!r}")

        # Special: API keys from env (not in schema but well-known)
        self._apply_provider_key_overrides()

    def _apply_provider_key_overrides(self) -> None:
        """Apply provider API key environment variables."""
        if "providers" not in self.data:
            self.data["providers"] = {}

        env_map = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "google": "GOOGLE_API_KEY",
            "google_vertex": "VERTEX_API_KEY",
            "groq": "GROQ_API_KEY",
            "cerebras": "CEREBRAS_API_KEY",
            "sambanova": "SAMBANOVA_API_KEY",
            "fireworks": "FIREWORKS_API_KEY",
            "together": "TOGETHER_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
            "unify": "UNIFY_API_KEY",
            "portkey": "PORTKEY_API_KEY",
            "mistral": "MISTRAL_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
            "qwen": "QWEN_API_KEY",
            "baidu": "BAIDU_API_KEY",
            "zhipu": "ZHIPU_API_KEY",
            "moonshot": "MOONSHOT_API_KEY",
            "yi": "YI_API_KEY",
            "cohere": "COHERE_API_KEY",
            "ai21": "AI21_API_KEY",
            "perplexity": "PERPLEXITY_API_KEY",
            "replicate": "REPLICATE_API_TOKEN",
            "huggingface": "HUGGINGFACE_API_KEY",
            "xai": "XAI_API_KEY",
            "bedrock": "AWS_BEARER_TOKEN",
            "azure": "AZURE_OPENAI_API_KEY",
        }

        for provider, env_var in env_map.items():
            val = os.environ.get(env_var, "")
            if val:
                self.data["providers"][provider] = val

        # Custom provider base URL
        custom_base = os.environ.get("CUSTOM_API_BASE", "")
        if custom_base:
            self.data["providers"]["custom_base_url"] = custom_base

        # Vertex extras
        vertex_project = os.environ.get("VERTEX_PROJECT_ID", "")
        if vertex_project:
            self.data["providers"]["vertex_project_id"] = vertex_project
        vertex_location = os.environ.get("VERTEX_LOCATION", "")
        if vertex_location:
            self.data["providers"]["vertex_location"] = vertex_location

        # Azure endpoint
        azure_endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
        if azure_endpoint:
            self.data["providers"]["azure_endpoint"] = azure_endpoint

    @staticmethod
    def _coerce_env_value(value: str, field_type: ConfigFieldType) -> Any:
        """Coerce an environment variable string to the expected type."""
        if field_type == ConfigFieldType.BOOLEAN:
            return value.lower() in ("true", "1", "yes", "on")
        if field_type == ConfigFieldType.INTEGER:
            try:
                return int(value)
            except ValueError:
                return value
        if field_type == ConfigFieldType.FLOAT:
            try:
                return float(value)
            except ValueError:
                return value
        if field_type == ConfigFieldType.LIST:
            return [v.strip() for v in value.split(",") if v.strip()]
        return value

    # ── Hot-Reload ───────────────────────────────────────────

    def enable_hot_reload(self, interval: float = 2.0) -> None:
        """Enable automatic config file change detection."""
        if self._watcher:
            return
        self._watcher = ConfigWatcher(self.config_path, interval=interval)
        self._watcher.on_change(self._on_file_change)
        self._watcher.start()

    def disable_hot_reload(self) -> None:
        """Disable hot-reload."""
        if self._watcher:
            self._watcher.stop()
            self._watcher = None

    def _on_file_change(self) -> None:
        """Handle config file change event."""
        old_data = copy.deepcopy(self.data)
        self._load()
        self._apply_env_overrides()
        self.data = apply_defaults(self.data)
        self._validation_errors = validate_config(self.data)
        if self._validation_errors:
            for err in self._validation_errors:
                logger.warning(f"Config validation: {err}")
        logger.info("Config reloaded from disk")
        for callback in self._change_callbacks:
            try:
                callback(old_data, self.data)
            except Exception as e:
                logger.error(f"Config change callback error: {e}")

    def on_change(self, callback: Callable[[dict, dict], None]) -> None:
        """Register a callback for config changes. Signature: (old_data, new_data) -> None."""
        self._change_callbacks.append(callback)

    # ── Save ─────────────────────────────────────────────────

    def save(self) -> None:
        """Save configuration to file."""
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        # Always save as JSON for simplicity and cross-platform compat
        json_path = self.config_path.replace(".toml", ".json")
        try:
            with open(json_path, "w") as f:
                json.dump(self.data, f, indent=2)
            logger.debug(f"Config saved to {json_path}")
        except Exception as e:
            logger.error(f"Failed to save config: {e}")

    # ── Getters / Setters ────────────────────────────────────

    def get(self, key: str, default: Any = None) -> Any:
        """Get a config value using dot notation.
        
        Checks profile first (if loaded), then base config.
        For encrypted values, automatically decrypts.
        """
        # Check profile override first
        if self._profile:
            val = self._profile.get(key)
            if val is not None:
                if isinstance(val, str) and self._secrets.is_encrypted(val):
                    return self._secrets.decrypt(val)
                return val

        # Then base config
        keys = key.split(".")
        value: Any = self.data
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
            if value is None:
                return default

        # Decrypt if encrypted
        if isinstance(value, str) and self._secrets.is_encrypted(value):
            return self._secrets.decrypt(value)

        return value

    def set(self, key: str, value: Any, encrypt: bool = False) -> None:
        """Set a config value using dot notation.
        
        Args:
            key: Dot-notation key (e.g. "agent.temperature")
            value: Value to set
            encrypt: If True, encrypt the value before storing (for secrets)
        """
        if encrypt and isinstance(value, str):
            value = self._secrets.encrypt(value)

        keys = key.split(".")
        data = self.data
        for k in keys[:-1]:
            if k not in data:
                data[k] = {}
            data = data[k]
        data[keys[-1]] = value
        self.save()

    def set_secret(self, key: str, value: str) -> None:
        """Set an encrypted secret value."""
        self.set(key, value, encrypt=True)

    def get_secret(self, key: str, default: str = "") -> str:
        """Get and decrypt a secret value."""
        return self.get(key, default)

    # ── Provider Keys ────────────────────────────────────────

    def get_provider_keys(self) -> dict[str, str]:
        """Get configured API keys (decrypted)."""
        providers = self.get("providers", {})
        if not isinstance(providers, dict):
            return {}
        result: dict[str, str] = {}
        for k, v in providers.items():
            if isinstance(v, str):
                result[k] = self._secrets.decrypt(v) if self._secrets.is_encrypted(v) else v
        return result

    # ── User Profiles ────────────────────────────────────────

    def load_profile(self, profile_name: str) -> None:
        """Load a per-user config profile."""
        data_dir = os.path.expanduser("~/.rally-agent/data")
        self._profile = UserProfile(profile_name, data_dir)
        logger.info(f"Loaded profile: {profile_name}")

    def unload_profile(self) -> None:
        """Unload the current profile (revert to base config)."""
        self._profile = None

    def save_profile(self, profile_name: str) -> None:
        """Save current in-memory overrides as a profile."""
        data_dir = os.path.expanduser("~/.rally-agent/data")
        profile = UserProfile(profile_name, data_dir)
        profile.data = copy.deepcopy(self.data)
        profile.save()
        logger.info(f"Saved profile: {profile_name}")

    @staticmethod
    def list_profiles() -> list[str]:
        """List available config profiles."""
        profiles_dir = os.path.expanduser("~/.rally-agent/data/profiles")
        if not os.path.exists(profiles_dir):
            return []
        return [
            f.stem for f in Path(profiles_dir).iterdir()
            if f.suffix == ".json" and f.is_file()
        ]

    # ── Validation ───────────────────────────────────────────

    @property
    def validation_errors(self) -> list[str]:
        """Return current validation errors."""
        return list(self._validation_errors)

    def validate(self) -> bool:
        """Re-validate the current config. Returns True if valid."""
        self._validation_errors = validate_config(self.data)
        return len(self._validation_errors) == 0

    # ── Utility ──────────────────────────────────────────────

    def to_dict(self) -> dict:
        """Return a deep copy of the config data (decrypted)."""
        result = copy.deepcopy(self.data)
        # Decrypt any encrypted values in the copy
        self._decrypt_dict(result)
        return result

    def _decrypt_dict(self, d: dict) -> None:
        """Recursively decrypt values in a dict."""
        for k, v in d.items():
            if isinstance(v, str) and self._secrets.is_encrypted(v):
                d[k] = self._secrets.decrypt(v)
            elif isinstance(v, dict):
                self._decrypt_dict(v)

    def get_schema_docs(self) -> dict[str, list[dict]]:
        """Return schema documentation for all config sections."""
        docs: dict[str, list[dict]] = {}
        for schema in SCHEMAS:
            docs[schema.section] = [
                {
                    "name": f.name,
                    "type": f.field_type.value,
                    "default": f.default,
                    "description": f.description,
                    "env_override": f.env_override,
                    "min": f.min_value,
                    "max": f.max_value,
                    "allowed": f.allowed_values,
                }
                for f in schema.fields
            ]
        return docs
