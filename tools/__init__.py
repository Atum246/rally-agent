"""
🟣 Rally Agent — Tools Package
Complete tool system with function calling, sandboxing, skills, browser automation,
real computer use (desktop control), and system control.
"""

from typing import Optional

from tools.registry import (
    # Core
    ToolRegistry,
    BaseTool,
    ToolDefinition,
    ToolParameter,
    ToolCategory,
    PermissionLevel,
    # Execution
    UsageTracker,
    RateLimiter,
    PermissionManager,
    ToolCallRecord,
)

from tools.exec_sandbox import (
    ExecutionSandbox,
    SandboxResult,
    ResourceLimits,
    SandboxBackend,
    LANGUAGES,
)

from tools.skills import register_all_skills

from tools.browser import (
    BrowserEngine,
    BrowserProfile,
    register_browser_tools,
    PageStateMachine,
    PageState,
    NetworkInterceptor,
    TabManager,
    DownloadManager,
)

from tools.computer_use import (
    ComputerUseEngine,
    register_computer_use_tools,
    # Data types
    ScreenRegion,
    UIElement,
    WindowInfo,
    MonitorInfo,
    MouseButton,
    ScrollDirection,
)

from tools.system_control import (
    register_system_control_tools,
    # Managers (for direct use)
    ProcessManager,
    ServiceManager,
    FileSystemWatcher,
    NetworkControl,
    HardwareInfo,
    PackageManager,
    EnvironmentManager,
    ScheduledTasks,
    PowerManagement,
    AutoUpdater,
)


def create_tool_registry(config=None) -> ToolRegistry:
    """
    Create a fully initialized ToolRegistry with all built-in tools and skills.
    This is the main entry point for setting up the tool system.
    """
    registry = ToolRegistry(config)

    # Register all skills (30+)
    skill_count = register_all_skills(registry)

    # Register system control tools (10 tools)
    register_system_control_tools(registry)

    return registry


def create_full_tool_system(config=None, browser_profile: Optional[BrowserProfile] = None):
    """
    Create the complete tool system: registry + skills + browser + computer use.
    Returns (registry, browser_engine, computer_engine).
    """
    registry = create_tool_registry(config)

    # Register browser tools
    browser_engine = register_browser_tools(registry, config=config, profile=browser_profile)

    # Register computer use tools (10 tools)
    computer_engine = register_computer_use_tools(registry)

    return registry, browser_engine, computer_engine


__all__ = [
    # Registry
    "ToolRegistry",
    "BaseTool",
    "ToolDefinition",
    "ToolParameter",
    "ToolCategory",
    "PermissionLevel",
    "UsageTracker",
    "RateLimiter",
    "PermissionManager",
    "ToolCallRecord",
    # Sandbox
    "ExecutionSandbox",
    "SandboxResult",
    "ResourceLimits",
    "SandboxBackend",
    "LANGUAGES",
    # Skills
    "register_all_skills",
    # Browser
    "BrowserEngine",
    "BrowserProfile",
    "register_browser_tools",
    "PageStateMachine",
    "PageState",
    "NetworkInterceptor",
    "TabManager",
    "DownloadManager",
    # Computer Use
    "ComputerUseEngine",
    "register_computer_use_tools",
    "ScreenRegion",
    "UIElement",
    "WindowInfo",
    "MonitorInfo",
    "MouseButton",
    "ScrollDirection",
    # System Control
    "register_system_control_tools",
    "ProcessManager",
    "ServiceManager",
    "FileSystemWatcher",
    "NetworkControl",
    "HardwareInfo",
    "PackageManager",
    "EnvironmentManager",
    "ScheduledTasks",
    "PowerManagement",
    "AutoUpdater",
    # Factories
    "create_tool_registry",
    "create_full_tool_system",
]
