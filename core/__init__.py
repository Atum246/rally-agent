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

# Sophisticated User Model
from core.user_model import (
    UserModel,
    PersonalityProfiler,
    CommunicationStyleAnalyzer,
    InterestTracker,
    RoutineDetector,
    EmotionalDetector,
    PrivacyController,
    TraitScore,
    TopicWeight,
    Goal,
    Correction,
    ProjectContext,
    EmotionalSnapshot,
)

# Knowledge Graph
from core.knowledge_graph import (
    KnowledgeGraph,
    EntityExtractor,
    Entity,
    Relationship,
    EntityType,
    RelationType,
)

# Workflow Engine
from core.workflow_engine import (
    WorkflowEngine,
    WorkflowRecorder,
    PatternDetector,
    Workflow,
    WorkflowStep,
    WorkflowTrigger,
    WorkflowRun,
    StepType,
    TriggerType,
    WorkflowStatus,
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
    # User Model
    "UserModel",
    "PersonalityProfiler",
    "CommunicationStyleAnalyzer",
    "InterestTracker",
    "RoutineDetector",
    "EmotionalDetector",
    "PrivacyController",
    "TraitScore",
    "TopicWeight",
    "Goal",
    "Correction",
    "ProjectContext",
    "EmotionalSnapshot",
    # Knowledge Graph
    "KnowledgeGraph",
    "EntityExtractor",
    "Entity",
    "Relationship",
    "EntityType",
    "RelationType",
    # Workflow Engine
    "WorkflowEngine",
    "WorkflowRecorder",
    "PatternDetector",
    "Workflow",
    "WorkflowStep",
    "WorkflowTrigger",
    "WorkflowRun",
    "StepType",
    "TriggerType",
    "WorkflowStatus",
]
