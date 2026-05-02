"""
🟣 Rally Agent — Tools Package
Complete tool system with function calling, sandboxing, skills, and browser automation.
"""

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


def create_tool_registry(config=None) -> ToolRegistry:
    """
    Create a fully initialized ToolRegistry with all built-in tools and skills.
    This is the main entry point for setting up the tool system.
    """
    registry = ToolRegistry(config)

    # Register all skills (30+)
    skill_count = register_all_skills(registry)

    return registry


def create_full_tool_system(config=None, browser_profile: Optional[BrowserProfile] = None):
    """
    Create the complete tool system: registry + skills + browser.
    Returns (registry, browser_engine).
    """
    registry = create_tool_registry(config)

    # Register browser tools
    browser_engine = register_browser_tools(registry, config=config, profile=browser_profile)

    return registry, browser_engine


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
    # Factories
    "create_tool_registry",
    "create_full_tool_system",
]

# Re-export Optional for type hints used in function signatures
from typing import Optional
