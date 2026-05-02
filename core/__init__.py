"""
🟣 Rally Agent — Core
======================
The brain that powers everything.
"""

# Engine
from core.engine import (
    TokenCounter,
    RallyEngine,
)

# Providers
from core.providers import (
    ProviderManager,
    ChatResponse,
    TokenUsage,
    ToolDefinition,
    ProviderStatus,
)

# Plugin System
from core.plugins import (
    BasePlugin,
    PluginManager,
    PluginManifest,
    PluginInfo,
    PluginState,
    HookType,
    HookResult,
    Permission as PluginPermission,
    PluginValidator,
    PluginSandbox,
    MarketplaceClient,
    PluginError,
    PluginLoadError,
    PluginNotFoundError,
    SecurityError,
    VersionError,
)

# Observability
from core.observability import (
    ObservabilityManager,
    MetricsCollector,
    CostEstimator,
    TokenUsageRecord,
    LatencyRecord,
    AgentActivity,
    AgentStatus,
    MemoryHealthMetrics,
    ErrorRecord,
    Alert,
    AlertRule,
    AlertSeverity,
    MetricType,
)

# Multi-User System
from core.multiuser import (
    MultiUserManager,
    UserProfile,
    Role,
    SessionInfo,
    ConversationMeta,
    Workspace,
    ActivityLogEntry,
    UsageQuotaSnapshot,
    PasswordHasher,
    TokenManager,
    UserStore,
    ROLE_HIERARCHY,
    ROLE_PERMISSIONS,
)

__all__ = [
    # Engine
    "TokenCounter",
    "RallyEngine",
    # Providers
    "ProviderManager",
    "ChatResponse",
    "TokenUsage",
    "ToolDefinition",
    "ProviderStatus",
    # Plugins
    "BasePlugin",
    "PluginManager",
    "PluginManifest",
    "PluginInfo",
    "PluginState",
    "HookType",
    "HookResult",
    "PluginPermission",
    "PluginValidator",
    "PluginSandbox",
    "MarketplaceClient",
    "PluginError",
    "PluginLoadError",
    "PluginNotFoundError",
    "SecurityError",
    "VersionError",
    # Observability
    "ObservabilityManager",
    "MetricsCollector",
    "CostEstimator",
    "TokenUsageRecord",
    "LatencyRecord",
    "AgentActivity",
    "AgentStatus",
    "MemoryHealthMetrics",
    "ErrorRecord",
    "Alert",
    "AlertRule",
    "AlertSeverity",
    "MetricType",
    # Multi-User
    "MultiUserManager",
    "UserProfile",
    "Role",
    "SessionInfo",
    "ConversationMeta",
    "Workspace",
    "ActivityLogEntry",
    "UsageQuotaSnapshot",
    "PasswordHasher",
    "TokenManager",
    "UserStore",
    "ROLE_HIERARCHY",
    "ROLE_PERMISSIONS",
]
