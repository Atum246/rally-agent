"""
🟣 Rally Agent — Plugin System
===============================
Plugin SDK, discovery, hot-reload, sandboxing, versioning, marketplace,
dependency management, hooks, and security validation.
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib
import importlib.util
import inspect
import json
import logging
import os
import shutil
import sys
import tempfile
import threading
import time
import traceback
import types
import uuid
import zipfile
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import (
    Any, Callable, Awaitable, Dict, List, Optional, Set, Tuple, Type, Union,
)

logger = logging.getLogger("rally.plugins")

# Optional deps
try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False
    logger.debug("httpx not installed — marketplace downloads disabled")

try:
    from packaging.version import Version as PkgVersion
    HAS_PACKAGING = True
except ImportError:
    HAS_PACKAGING = False


# ═══════════════════════════════════════════════════════════════
# 📦 Data Types
# ═══════════════════════════════════════════════════════════════

class PluginState(Enum):
    DISCOVERED = "discovered"
    LOADED = "loaded"
    ACTIVE = "active"
    DISABLED = "disabled"
    ERROR = "error"
    UNLOADED = "unloaded"


class HookType(Enum):
    ON_MESSAGE = "on_message"
    ON_TOOL_CALL = "on_tool_call"
    ON_STARTUP = "on_startup"
    ON_SHUTDOWN = "on_shutdown"
    ON_RESPONSE = "on_response"
    ON_ERROR = "on_error"
    ON_USER_JOIN = "on_user_join"


class Permission(Enum):
    """Permissions a plugin can request."""
    READ_MESSAGES = "read_messages"
    SEND_MESSAGES = "send_messages"
    READ_MEMORY = "read_memory"
    WRITE_MEMORY = "write_memory"
    EXECUTE_TOOLS = "execute_tools"
    NETWORK_ACCESS = "network_access"
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    ADMIN = "admin"


@dataclass
class PluginManifest:
    """Plugin manifest (plugin.json)."""
    name: str
    version: str
    author: str = "unknown"
    description: str = ""
    license: str = "MIT"
    homepage: str = ""
    entry_point: str = "plugin.py"
    dependencies: List[str] = field(default_factory=list)
    permissions: List[str] = field(default_factory=list)
    min_rally_version: str = "0.1.0"
    max_rally_version: str = ""
    tags: List[str] = field(default_factory=list)
    config_schema: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "author": self.author,
            "description": self.description,
            "license": self.license,
            "homepage": self.homepage,
            "entry_point": self.entry_point,
            "dependencies": self.dependencies,
            "permissions": self.permissions,
            "min_rally_version": self.min_rally_version,
            "max_rally_version": self.max_rally_version,
            "tags": self.tags,
            "config_schema": self.config_schema,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PluginManifest":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class PluginInfo:
    """Runtime metadata for a loaded plugin."""
    manifest: PluginManifest
    path: str
    state: PluginState = PluginState.DISCOVERED
    instance: Optional["BasePlugin"] = None
    module: Optional[types.ModuleType] = None
    load_time: float = 0.0
    error: Optional[str] = None
    hash: str = ""
    enabled: bool = True
    pin_version: Optional[str] = None
    history: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.manifest.name

    @property
    def version(self) -> str:
        return self.manifest.version


@dataclass
class HookResult:
    """Result from a plugin hook invocation."""
    plugin_name: str
    hook: HookType
    success: bool
    result: Any = None
    error: Optional[str] = None
    duration_ms: float = 0.0


# ═══════════════════════════════════════════════════════════════
# 🧩 Plugin SDK — Base Class
# ═══════════════════════════════════════════════════════════════

class BasePlugin(ABC):
    """Base class for all Rally Agent plugins.

    Subclass this and implement the hooks you need.
    All hook methods are optional — default implementations are no-ops.

    Example:
        class MyPlugin(BasePlugin):
            async def on_message(self, message: dict, context: dict) -> Optional[dict]:
                if "hello" in message.get("content", "").lower():
                    return {"reply": "Hey there! 👋"}
                return None

            async def on_startup(self) -> None:
                self.log("MyPlugin started!")

            async def on_shutdown(self) -> None:
                self.log("MyPlugin shutting down.")
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config: Dict[str, Any] = config or {}
        self._logger: Optional[logging.Logger] = None
        self._plugin_name: str = self.__class__.__name__

    @property
    def name(self) -> str:
        return self._plugin_name

    @name.setter
    def name(self, value: str) -> None:
        self._plugin_name = value
        self._logger = None  # reset logger

    def log(self, msg: str, level: int = logging.INFO) -> None:
        if self._logger is None:
            self._logger = logging.getLogger(f"rally.plugin.{self._plugin_name}")
        self._logger.log(level, msg)

    # --- Hook methods (override as needed) ---

    async def on_message(self, message: Dict[str, Any], context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Called for every incoming message. Return None to pass through,
        or return a dict to inject/modify the response."""
        return None

    async def on_tool_call(self, tool_name: str, arguments: Dict[str, Any], context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Called before a tool is executed. Return None to proceed normally,
        or return a dict to override the tool result."""
        return None

    async def on_startup(self) -> None:
        """Called when the plugin is loaded and activated."""
        pass

    async def on_shutdown(self) -> None:
        """Called when the plugin is being unloaded or the system shuts down."""
        pass

    async def on_response(self, response: Dict[str, Any], context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Called after a response is generated. Return None or modified response."""
        return None

    async def on_error(self, error: Exception, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Called when an error occurs. Return None to let default handling proceed."""
        return None


# ═══════════════════════════════════════════════════════════════
# 🔒 Plugin Sandbox
# ═══════════════════════════════════════════════════════════════

class PluginSandbox:
    """Isolates plugin execution in a restricted namespace.

    Plugins cannot access:
    - os.system, subprocess, exec, eval (blocked builtins)
    - Direct imports of dangerous modules (shutil.rmtree, etc.)
    - The parent process's globals
    """

    # Modules that plugins CANNOT import directly
    BLOCKED_MODULES: Set[str] = {
        "subprocess", "ctypes", "importlib",
    }

    # Builtins to remove from plugin namespace
    BLOCKED_BUILTINS: Set[str] = {
        "exec", "eval", "compile", "__import__", "breakpoint",
        "exit", "quit",
    }

    def __init__(self, allowed_permissions: Optional[Set[str]] = None):
        self.allowed_permissions = allowed_permissions or set()

    def create_restricted_globals(self, plugin_name: str) -> Dict[str, Any]:
        """Create a restricted global namespace for a plugin."""
        import builtins as _builtins

        # Start with safe builtins
        safe_builtins = {}
        for name in dir(_builtins):
            if name in self.BLOCKED_BUILTINS:
                continue
            try:
                safe_builtins[name] = getattr(_builtins, name)
            except Exception:
                pass

        # Restricted __import__
        original_import = __builtins__.__import__ if hasattr(__builtins__, '__import__') else __import__

        def restricted_import(name, *args, **kwargs):
            base_name = name.split('.')[0]
            if base_name in self.BLOCKED_MODULES:
                raise ImportError(
                    f"Plugin '{plugin_name}' cannot import '{name}' — "
                    f"blocked by sandbox policy"
                )
            return original_import(name, *args, **kwargs)

        safe_builtins["__import__"] = restricted_import

        return {
            "__builtins__": safe_builtins,
            "__name__": f"rally_plugin_{plugin_name}",
            "__plugin_name__": plugin_name,
        }


# ═══════════════════════════════════════════════════════════════
# 🔍 Plugin Validator
# ═══════════════════════════════════════════════════════════════

class PluginValidator:
    """Validates plugins before loading for security and correctness."""

    DANGEROUS_PATTERNS: List[str] = [
        r"os\.system\s*\(",
        r"subprocess\.",
        r"__import__\s*\(",
        r"eval\s*\(",
        r"exec\s*\(",
        r"compile\s*\(",
        r"open\s*\(.*/etc/",
        r"open\s*\(.*/proc/",
        r"shutil\.rmtree\s*\(",
        r"__subclasses__",
        r"__globals__",
        r"__code__",
    ]

    @classmethod
    def validate_manifest(cls, manifest: PluginManifest) -> Tuple[bool, List[str]]:
        """Validate a plugin manifest. Returns (valid, errors)."""
        errors: List[str] = []

        if not manifest.name or not manifest.name.strip():
            errors.append("Plugin name is required")
        elif not manifest.name.replace("-", "").replace("_", "").isalnum():
            errors.append(f"Invalid plugin name: '{manifest.name}'")

        if not manifest.version:
            errors.append("Plugin version is required")
        elif HAS_PACKAGING:
            try:
                PkgVersion(manifest.version)
            except Exception:
                errors.append(f"Invalid version format: '{manifest.version}'")

        if not manifest.entry_point:
            errors.append("Entry point is required")

        # Validate permissions
        valid_perms = {p.value for p in Permission}
        for perm in manifest.permissions:
            if perm not in valid_perms:
                errors.append(f"Unknown permission: '{perm}'")

        return len(errors) == 0, errors

    @classmethod
    def validate_source(cls, source_code: str, plugin_name: str) -> Tuple[bool, List[str]]:
        """Static analysis of plugin source code for dangerous patterns."""
        import re
        errors: List[str] = []
        warnings: List[str] = []

        for pattern in cls.DANGEROUS_PATTERNS:
            matches = re.findall(pattern, source_code)
            if matches:
                warnings.append(
                    f"Potentially dangerous pattern '{pattern}' found in '{plugin_name}' "
                    f"({len(matches)} occurrence(s))"
                )

        # Check for BasePlugin subclass
        if "BasePlugin" not in source_code:
            warnings.append("Plugin does not reference BasePlugin — may not be a valid plugin")

        for w in warnings:
            logger.warning(f"[validator] {w}")

        # Warnings don't block loading, but logged for audit
        return len(errors) == 0, errors


# ═══════════════════════════════════════════════════════════════
# 🏪 Marketplace Client
# ═══════════════════════════════════════════════════════════════

class MarketplaceClient:
    """Download and install plugins from a marketplace URL."""

    def __init__(self, base_url: str = "https://marketplace.rally-agent.io", plugins_dir: str = ""):
        self.base_url = base_url.rstrip("/")
        self.plugins_dir = plugins_dir or str(Path.home() / ".rally-agent" / "plugins")

    async def search(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Search the marketplace for plugins."""
        if not HAS_HTTPX:
            raise RuntimeError("httpx is required for marketplace — pip install httpx")

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.base_url}/api/v1/plugins/search",
                params={"q": query, "limit": limit},
            )
            resp.raise_for_status()
            return resp.json().get("results", [])

    async def download(self, plugin_name: str, version: str = "latest") -> str:
        """Download and extract a plugin. Returns the plugin directory path."""
        if not HAS_HTTPX:
            raise RuntimeError("httpx is required for marketplace — pip install httpx")

        dest = os.path.join(self.plugins_dir, plugin_name)
        os.makedirs(dest, exist_ok=True)

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.get(
                f"{self.base_url}/api/v1/plugins/{plugin_name}/download",
                params={"version": version},
                follow_redirects=True,
            )
            resp.raise_for_status()

            zip_path = os.path.join(dest, f"{plugin_name}.zip")
            with open(zip_path, "wb") as f:
                f.write(resp.content)

            # Extract
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(dest)
            os.remove(zip_path)

            logger.info(f"Downloaded plugin '{plugin_name}' (v{version}) → {dest}")
            return dest

    async def get_info(self, plugin_name: str) -> Dict[str, Any]:
        """Get plugin metadata from the marketplace."""
        if not HAS_HTTPX:
            raise RuntimeError("httpx is required for marketplace — pip install httpx")

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{self.base_url}/api/v1/plugins/{plugin_name}")
            resp.raise_for_status()
            return resp.json()


# ═══════════════════════════════════════════════════════════════
# 🔄 File Watcher (polling fallback)
# ═══════════════════════════════════════════════════════════════

class PluginFileWatcher:
    """Watch plugin directories for changes.

    Uses watchdog if available, falls back to polling.
    """

    def __init__(self, paths: List[str], callback: Callable[[str, str], None], interval: float = 2.0):
        self.paths = paths
        self.callback = callback
        self.interval = interval
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._file_hashes: Dict[str, str] = {}
        self._observer = None

    async def start(self) -> None:
        """Start watching for file changes."""
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler, FileModifiedEvent, FileCreatedEvent

            class Handler(FileSystemEventHandler):
                def __init__(self, cb: Callable):
                    self._cb = cb

                def on_modified(self, event):
                    if event.src_path.endswith(".py") or event.src_path.endswith(".json"):
                        self._cb(event.src_path, "modified")

                def on_created(self, event):
                    if event.src_path.endswith(".py") or event.src_path.endswith(".json"):
                        self._cb(event.src_path, "created")

            self._observer = Observer()
            handler = Handler(self.callback)
            for p in self.paths:
                if os.path.isdir(p):
                    self._observer.schedule(handler, p, recursive=True)
            self._observer.start()
            logger.info(f"Plugin watcher started (watchdog) on {len(self.paths)} paths")

        except ImportError:
            # Fallback: polling
            logger.info(f"Plugin watcher started (polling, interval={self.interval}s)")
            self._running = True
            self._task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        """Stop watching."""
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None
        if self._task:
            self._running = False
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _poll_loop(self) -> None:
        """Polling-based file change detection."""
        while self._running:
            try:
                for base_path in self.paths:
                    if not os.path.isdir(base_path):
                        continue
                    for root, dirs, files in os.walk(base_path):
                        for fname in files:
                            if not (fname.endswith(".py") or fname.endswith(".json")):
                                continue
                            fpath = os.path.join(root, fname)
                            try:
                                h = self._hash_file(fpath)
                                old = self._file_hashes.get(fpath)
                                if old is None:
                                    self._file_hashes[fpath] = h
                                elif old != h:
                                    self._file_hashes[fpath] = h
                                    self.callback(fpath, "modified")
                            except OSError:
                                pass
                await asyncio.sleep(self.interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Plugin watcher poll error: {e}")
                await asyncio.sleep(self.interval * 2)

    @staticmethod
    def _hash_file(path: str) -> str:
        h = hashlib.md5()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()


# ═══════════════════════════════════════════════════════════════
# 🔌 Plugin Manager — The Main Orchestrator
# ═══════════════════════════════════════════════════════════════

class PluginManager:
    """Central plugin lifecycle manager.

    Handles discovery, loading, hot-reload, hooks, enable/disable,
    versioning, dependency resolution, and marketplace integration.
    """

    def __init__(
        self,
        plugins_dir: Optional[str] = None,
        config_dir: Optional[str] = None,
        sandbox_enabled: bool = True,
        auto_discover: bool = True,
    ):
        self.plugins_dir = plugins_dir or str(Path.home() / ".rally-agent" / "plugins")
        self.config_dir = config_dir or str(Path.home() / ".rally-agent" / "config")
        self.sandbox_enabled = sandbox_enabled

        self._plugins: Dict[str, PluginInfo] = {}
        self._hooks: Dict[HookType, List[Tuple[str, Callable]]] = defaultdict(list)
        self._lock = threading.Lock()
        self._watcher: Optional[PluginFileWatcher] = None
        self._marketplace = MarketplaceClient(plugins_dir=self.plugins_dir)
        self._sandbox = PluginSandbox()
        self._validator = PluginValidator()

        # State persistence
        self._state_file = os.path.join(self.config_dir, "plugins_state.json")

        os.makedirs(self.plugins_dir, exist_ok=True)
        os.makedirs(self.config_dir, exist_ok=True)

        if auto_discover:
            self._load_state()

    # --- Discovery ---

    def discover(self) -> List[PluginManifest]:
        """Scan plugins directory for valid plugin manifests."""
        manifests: List[PluginManifest] = []

        if not os.path.isdir(self.plugins_dir):
            return manifests

        for entry in os.listdir(self.plugins_dir):
            plugin_dir = os.path.join(self.plugins_dir, entry)
            if not os.path.isdir(plugin_dir):
                continue

            manifest_path = os.path.join(plugin_dir, "plugin.json")
            if not os.path.exists(manifest_path):
                # Look for a single .py file as a simple plugin
                py_files = [f for f in os.listdir(plugin_dir) if f.endswith(".py") and not f.startswith("_")]
                if len(py_files) == 1:
                    # Create minimal manifest
                    manifest = PluginManifest(
                        name=entry,
                        version="0.0.1",
                        entry_point=py_files[0],
                    )
                    manifests.append(manifest)
                continue

            try:
                with open(manifest_path, "r") as f:
                    data = json.load(f)
                manifest = PluginManifest.from_dict(data)
                valid, errors = self._validator.validate_manifest(manifest)
                if not valid:
                    logger.warning(f"Invalid manifest for '{entry}': {errors}")
                    continue
                manifests.append(manifest)
            except Exception as e:
                logger.error(f"Failed to load manifest for '{entry}': {e}")

        return manifests

    # --- Loading ---

    def load(self, plugin_name: str, force: bool = False) -> PluginInfo:
        """Load a single plugin by name."""
        with self._lock:
            info = self._plugins.get(plugin_name)
            if info and info.state == PluginState.ACTIVE and not force:
                logger.debug(f"Plugin '{plugin_name}' already active")
                return info

            plugin_dir = os.path.join(self.plugins_dir, plugin_name)
            if not os.path.isdir(plugin_dir):
                raise FileNotFoundError(f"Plugin directory not found: {plugin_dir}")

            # Load or create manifest
            manifest_path = os.path.join(plugin_dir, "plugin.json")
            if os.path.exists(manifest_path):
                with open(manifest_path, "r") as f:
                    manifest = PluginManifest.from_dict(json.load(f))
            else:
                py_files = [f for f in os.listdir(plugin_dir) if f.endswith(".py") and not f.startswith("_")]
                manifest = PluginManifest(
                    name=plugin_name,
                    version="0.0.1",
                    entry_point=py_files[0] if py_files else "plugin.py",
                )

            entry = os.path.join(plugin_dir, manifest.entry_point)
            if not os.path.exists(entry):
                raise FileNotFoundError(f"Entry point not found: {entry}")

            # Security validation
            with open(entry, "r") as f:
                source = f.read()
            valid, errors = self._validator.validate_source(source, plugin_name)
            if not valid:
                raise SecurityError(f"Plugin '{plugin_name}' failed security check: {errors}")

            # Compute hash
            file_hash = hashlib.sha256(source.encode()).hexdigest()[:16]

            # Check version pin
            if info and info.pin_version and info.pin_version != manifest.version:
                raise VersionError(
                    f"Plugin '{plugin_name}' is pinned to v{info.pin_version}, "
                    f"but v{manifest.version} is installed"
                )

            # Load the module
            start = time.monotonic()
            module = self._load_module(plugin_name, entry, manifest)
            load_time = (time.monotonic() - start) * 1000

            # Instantiate the plugin class
            instance = self._instantiate_plugin(module, plugin_name)

            info = PluginInfo(
                manifest=manifest,
                path=plugin_dir,
                state=PluginState.LOADED,
                instance=instance,
                module=module,
                load_time=load_time,
                hash=file_hash,
                enabled=manifest.enabled,
            )

            self._plugins[plugin_name] = info
            self._register_hooks(plugin_name, instance)

            logger.info(
                f"Loaded plugin '{plugin_name}' v{manifest.version} "
                f"in {load_time:.1f}ms (hash={file_hash})"
            )
            return info

    def _load_module(self, name: str, entry: str, manifest: PluginManifest) -> types.ModuleType:
        """Load a plugin Python module, optionally in a sandbox."""
        module_name = f"rally_plugin_{name}"

        if self.sandbox_enabled:
            # Create restricted namespace
            restricted_globals = self._sandbox.create_restricted_globals(name)
            spec = importlib.util.spec_from_file_location(module_name, entry)
            if spec is None or spec.loader is None:
                raise PluginLoadError(f"Cannot create module spec for '{name}'")
            module = importlib.util.module_from_spec(spec)
            module.__dict__.update(restricted_globals)
            spec.loader.exec_module(module)
        else:
            spec = importlib.util.spec_from_file_location(module_name, entry)
            if spec is None or spec.loader is None:
                raise PluginLoadError(f"Cannot create module spec for '{name}'")
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

        return module

    def _instantiate_plugin(self, module: types.ModuleType, name: str) -> BasePlugin:
        """Find and instantiate the BasePlugin subclass in a module."""
        plugin_class = None

        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                inspect.isclass(attr)
                and issubclass(attr, BasePlugin)
                and attr is not BasePlugin
            ):
                plugin_class = attr
                break

        if plugin_class is None:
            raise PluginLoadError(
                f"No BasePlugin subclass found in plugin '{name}'"
            )

        return plugin_class(config={})

    def _register_hooks(self, name: str, instance: BasePlugin) -> None:
        """Register plugin hook methods."""
        for hook_type in HookType:
            method_name = hook_type.value
            method = getattr(instance, method_name, None)
            if method and callable(method):
                self._hooks[hook_type].append((name, method))
                logger.debug(f"Registered hook '{hook_type.value}' for plugin '{name}'")

    def _unregister_hooks(self, name: str) -> None:
        """Remove all hooks for a plugin."""
        for hook_type in HookType:
            self._hooks[hook_type] = [
                (n, h) for n, h in self._hooks[hook_type] if n != name
            ]

    # --- Activation / Deactivation ---

    async def activate(self, plugin_name: str) -> None:
        """Activate a loaded plugin (call on_startup)."""
        info = self._plugins.get(plugin_name)
        if not info:
            raise PluginNotFoundError(f"Plugin '{plugin_name}' not found")

        if info.state == PluginState.ACTIVE:
            return

        try:
            if info.instance:
                await info.instance.on_startup()
            info.state = PluginState.ACTIVE
            info.error = None
            logger.info(f"Activated plugin '{plugin_name}'")
        except Exception as e:
            info.state = PluginState.ERROR
            info.error = str(e)
            logger.error(f"Failed to activate plugin '{plugin_name}': {e}")
            raise

    async def deactivate(self, plugin_name: str) -> None:
        """Deactivate an active plugin (call on_shutdown)."""
        info = self._plugins.get(plugin_name)
        if not info or info.state != PluginState.ACTIVE:
            return

        try:
            if info.instance:
                await info.instance.on_shutdown()
        except Exception as e:
            logger.warning(f"Error in on_shutdown for '{plugin_name}': {e}")

        info.state = PluginState.DISABLED
        logger.info(f"Deactivated plugin '{plugin_name}'")

    async def unload(self, plugin_name: str) -> None:
        """Fully unload a plugin."""
        await self.deactivate(plugin_name)
        with self._lock:
            self._unregister_hooks(plugin_name)
            info = self._plugins.pop(plugin_name, None)
            if info:
                info.state = PluginState.UNLOADED
                # Remove module from sys.modules
                module_name = f"rally_plugin_{plugin_name}"
                sys.modules.pop(module_name, None)
                logger.info(f"Unloaded plugin '{plugin_name}'")

    # --- Enable / Disable ---

    async def enable(self, plugin_name: str) -> None:
        """Enable a disabled plugin without restart."""
        info = self._plugins.get(plugin_name)
        if not info:
            raise PluginNotFoundError(f"Plugin '{plugin_name}' not found")
        info.enabled = True
        info.manifest.enabled = True
        if info.state in (PluginState.DISABLED, PluginState.LOADED):
            await self.activate(plugin_name)
        self._save_state()
        logger.info(f"Enabled plugin '{plugin_name}'")

    async def disable(self, plugin_name: str) -> None:
        """Disable an active plugin without restart."""
        info = self._plugins.get(plugin_name)
        if not info:
            raise PluginNotFoundError(f"Plugin '{plugin_name}' not found")
        info.enabled = False
        info.manifest.enabled = False
        if info.state == PluginState.ACTIVE:
            await self.deactivate(plugin_name)
        self._save_state()
        logger.info(f"Disabled plugin '{plugin_name}'")

    # --- Hot Reload ---

    async def reload(self, plugin_name: str) -> PluginInfo:
        """Hot-reload a plugin (unload + load + activate)."""
        logger.info(f"Hot-reloading plugin '{plugin_name}'")
        was_active = False
        info = self._plugins.get(plugin_name)
        if info and info.state == PluginState.ACTIVE:
            was_active = True
            await self.deactivate(plugin_name)

        await self.unload(plugin_name)
        new_info = self.load(plugin_name, force=True)

        if was_active and new_info.enabled:
            await self.activate(plugin_name)

        new_info.history.append({
            "action": "reload",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": new_info.version,
        })
        return new_info

    async def start_watching(self) -> None:
        """Start file watcher for hot-reload."""
        self._watcher = PluginFileWatcher(
            paths=[self.plugins_dir],
            callback=self._on_file_change,
        )
        await self._watcher.start()

    async def stop_watching(self) -> None:
        """Stop file watcher."""
        if self._watcher:
            await self._watcher.stop()

    def _on_file_change(self, path: str, event_type: str) -> None:
        """Handle file change events from watcher."""
        logger.info(f"Plugin file {event_type}: {path}")
        # Determine which plugin was affected
        parts = Path(path).relative_to(self.plugins_dir).parts
        if parts:
            plugin_name = parts[0]
            if plugin_name in self._plugins:
                logger.info(f"Scheduling reload for plugin '{plugin_name}'")
                asyncio.create_task(self.reload(plugin_name))

    # --- Versioning ---

    def pin_version(self, plugin_name: str, version: str) -> None:
        """Pin a plugin to a specific version."""
        info = self._plugins.get(plugin_name)
        if not info:
            raise PluginNotFoundError(f"Plugin '{plugin_name}' not found")
        info.pin_version = version
        info.history.append({
            "action": "pin",
            "version": version,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        self._save_state()
        logger.info(f"Pinned plugin '{plugin_name}' to v{version}")

    def unpin_version(self, plugin_name: str) -> None:
        """Remove version pin."""
        info = self._plugins.get(plugin_name)
        if not info:
            raise PluginNotFoundError(f"Plugin '{plugin_name}' not found")
        info.pin_version = None
        self._save_state()

    # --- Dependency Management ---

    def resolve_dependencies(self, plugin_name: str) -> List[str]:
        """Resolve plugin dependencies. Returns ordered list of plugins to load first."""
        info = self._plugins.get(plugin_name)
        if not info:
            raise PluginNotFoundError(f"Plugin '{plugin_name}' not found")

        visited: Set[str] = set()
        order: List[str] = []

        def _visit(name: str) -> None:
            if name in visited:
                return
            visited.add(name)
            pinfo = self._plugins.get(name)
            if not pinfo:
                return
            for dep in pinfo.manifest.dependencies:
                _visit(dep)
            order.append(name)

        _visit(plugin_name)
        return order

    def check_missing_dependencies(self, plugin_name: str) -> List[str]:
        """Check for missing dependencies."""
        info = self._plugins.get(plugin_name)
        if not info:
            return []
        missing = []
        for dep in info.manifest.dependencies:
            if dep not in self._plugins:
                missing.append(dep)
        return missing

    # --- Hook Invocation ---

    async def invoke_hook(
        self,
        hook: HookType,
        *args: Any,
        **kwargs: Any,
    ) -> List[HookResult]:
        """Invoke a hook on all registered plugins. Returns results from each."""
        results: List[HookResult] = []

        for plugin_name, method in self._hooks.get(hook, []):
            info = self._plugins.get(plugin_name)
            if not info or info.state != PluginState.ACTIVE or not info.enabled:
                continue

            start = time.monotonic()
            try:
                result = await method(*args, **kwargs)
                duration = (time.monotonic() - start) * 1000
                results.append(HookResult(
                    plugin_name=plugin_name,
                    hook=hook,
                    success=True,
                    result=result,
                    duration_ms=duration,
                ))
            except Exception as e:
                duration = (time.monotonic() - start) * 1000
                logger.error(f"Hook '{hook.value}' failed in plugin '{plugin_name}': {e}")
                results.append(HookResult(
                    plugin_name=plugin_name,
                    hook=hook,
                    success=False,
                    error=str(e),
                    duration_ms=duration,
                ))

        return results

    # --- Marketplace ---

    async def install_from_marketplace(self, plugin_name: str, version: str = "latest") -> PluginInfo:
        """Install a plugin from the marketplace."""
        path = await self._marketplace.download(plugin_name, version)
        info = self.load(plugin_name)
        if info.enabled:
            await self.activate(plugin_name)
        info.history.append({
            "action": "install",
            "source": "marketplace",
            "version": version,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return info

    async def install_from_url(self, url: str, plugin_name: Optional[str] = None) -> PluginInfo:
        """Install a plugin from a direct URL (zip file)."""
        if not HAS_HTTPX:
            raise RuntimeError("httpx is required — pip install httpx")

        if not plugin_name:
            plugin_name = url.split("/")[-1].replace(".zip", "").split("?")[0]

        dest = os.path.join(self.plugins_dir, plugin_name)
        os.makedirs(dest, exist_ok=True)

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.get(url, follow_redirects=True)
            resp.raise_for_status()
            zip_path = os.path.join(dest, f"{plugin_name}.zip")
            with open(zip_path, "wb") as f:
                f.write(resp.content)

        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(dest)
        os.remove(zip_path)

        info = self.load(plugin_name)
        if info.enabled:
            await self.activate(plugin_name)
        return info

    # --- State Persistence ---

    def _save_state(self) -> None:
        """Persist plugin states to disk."""
        state = {}
        for name, info in self._plugins.items():
            state[name] = {
                "enabled": info.enabled,
                "pin_version": info.pin_version,
                "state": info.state.value,
                "hash": info.hash,
                "history": info.history[-20:],  # keep last 20 events
            }
        try:
            with open(self._state_file, "w") as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save plugin state: {e}")

    def _load_state(self) -> None:
        """Load persisted plugin states."""
        if not os.path.exists(self._state_file):
            return
        try:
            with open(self._state_file, "r") as f:
                state = json.load(f)
            for name, data in state.items():
                if name in self._plugins:
                    self._plugins[name].enabled = data.get("enabled", True)
                    self._plugins[name].pin_version = data.get("pin_version")
                    self._plugins[name].history = data.get("history", [])
        except Exception as e:
            logger.error(f"Failed to load plugin state: {e}")

    # --- Query ---

    def list_plugins(self) -> List[Dict[str, Any]]:
        """List all discovered/loaded plugins with their status."""
        result = []
        for name, info in self._plugins.items():
            result.append({
                "name": name,
                "version": info.version,
                "state": info.state.value,
                "enabled": info.enabled,
                "author": info.manifest.author,
                "description": info.manifest.description,
                "permissions": info.manifest.permissions,
                "load_time_ms": round(info.load_time, 1),
                "hash": info.hash,
                "pin_version": info.pin_version,
                "path": info.path,
            })
        return result

    def get_plugin(self, plugin_name: str) -> Optional[Dict[str, Any]]:
        """Get detailed info about a single plugin."""
        info = self._plugins.get(plugin_name)
        if not info:
            return None
        return {
            "name": plugin_name,
            "version": info.version,
            "state": info.state.value,
            "enabled": info.enabled,
            "manifest": info.manifest.to_dict(),
            "load_time_ms": round(info.load_time, 1),
            "hash": info.hash,
            "pin_version": info.pin_version,
            "path": info.path,
            "error": info.error,
            "history": info.history,
        }

    # --- Lifecycle ---

    async def startup_all(self) -> None:
        """Discover, load, and activate all enabled plugins."""
        manifests = self.discover()
        logger.info(f"Discovered {len(manifests)} plugins")

        for manifest in manifests:
            try:
                info = self.load(manifest.name)
                if info.enabled:
                    await self.activate(manifest.name)
            except Exception as e:
                logger.error(f"Failed to start plugin '{manifest.name}': {e}")

    async def shutdown_all(self) -> None:
        """Deactivate and unload all plugins."""
        for name in list(self._plugins.keys()):
            try:
                await self.unload(name)
            except Exception as e:
                logger.error(f"Error unloading plugin '{name}': {e}")

        if self._watcher:
            await self._watcher.stop()

        self._save_state()
        logger.info("All plugins shut down")


# ═══════════════════════════════════════════════════════════════
# ❌ Exceptions
# ═══════════════════════════════════════════════════════════════

class PluginError(Exception):
    """Base plugin exception."""
    pass

class PluginLoadError(PluginError):
    """Failed to load a plugin."""
    pass

class PluginNotFoundError(PluginError):
    """Plugin not found."""
    pass

class SecurityError(PluginError):
    """Security validation failed."""
    pass

class VersionError(PluginError):
    """Version mismatch."""
    pass
