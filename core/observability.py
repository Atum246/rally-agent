"""
🟣 Rally Agent — Observability System
=======================================
Token tracking, latency metrics, agent monitoring, memory health,
error tracking, cost estimation, Prometheus export, alerting,
health checks, and system resource monitoring.
"""

from __future__ import annotations

import asyncio
import collections
import json
import logging
import os
import platform
import statistics
import threading
import time
import traceback
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("rally.observability")


# ═══════════════════════════════════════════════════════════════
# 📊 Data Types
# ═══════════════════════════════════════════════════════════════

class MetricType(Enum):
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"


class AlertSeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AgentStatus(Enum):
    IDLE = "idle"
    BUSY = "busy"
    ERROR = "error"
    OFFLINE = "offline"


@dataclass
class TokenUsageRecord:
    """A single token usage record."""
    timestamp: float
    conversation_id: str
    user_id: str
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float = 0.0


@dataclass
class LatencyRecord:
    """A single latency measurement."""
    timestamp: float
    provider: str
    operation: str
    latency_ms: float
    success: bool = True


@dataclass
class AgentActivity:
    """Current state of an agent."""
    agent_id: str
    name: str
    status: AgentStatus = AgentStatus.IDLE
    current_task: str = ""
    started_at: float = 0.0
    last_active: float = 0.0
    tasks_completed: int = 0
    tasks_failed: int = 0
    error: Optional[str] = None


@dataclass
class MemoryHealthMetrics:
    """Memory system health snapshot."""
    total_entries: int = 0
    total_size_bytes: int = 0
    hit_count: int = 0
    miss_count: int = 0
    hit_rate: float = 0.0
    avg_usefulness: float = 0.0
    oldest_entry_age_hours: float = 0.0
    newest_entry_age_hours: float = 0.0


@dataclass
class ErrorRecord:
    """Tracked error with context."""
    error_id: str
    timestamp: float
    source: str
    error_type: str
    message: str
    stack_trace: str
    context: Dict[str, Any] = field(default_factory=dict)
    user_id: Optional[str] = None
    conversation_id: Optional[str] = None
    resolved: bool = False


@dataclass
class Alert:
    """A triggered alert."""
    alert_id: str
    timestamp: float
    severity: AlertSeverity
    metric: str
    message: str
    value: float
    threshold: float
    resolved: bool = False
    resolved_at: Optional[float] = None


@dataclass
class AlertRule:
    """Configurable alert threshold."""
    name: str
    metric: str
    threshold: float
    severity: AlertSeverity = AlertSeverity.WARNING
    comparison: str = "gt"  # gt, lt, gte, lte, eq
    duration_seconds: float = 0  # how long condition must persist
    cooldown_seconds: float = 300  # min time between alerts
    enabled: bool = True
    last_triggered: float = 0.0
    callback: Optional[Callable] = None


# ═══════════════════════════════════════════════════════════════
# 💰 Cost Estimation
# ═══════════════════════════════════════════════════════════════

# Per-million-token costs by provider/model (USD)
DEFAULT_COST_TABLE: Dict[str, Dict[str, Tuple[float, float]]] = {
    "openai": {
        "gpt-4o": (2.50, 10.00),
        "gpt-4o-mini": (0.15, 0.60),
        "gpt-4-turbo": (10.00, 30.00),
        "gpt-3.5-turbo": (0.50, 1.50),
        "o1": (15.00, 60.00),
        "o3-mini": (1.10, 4.40),
    },
    "anthropic": {
        "claude-sonnet-4-20250514": (3.00, 15.00),
        "claude-3-5-haiku-20241022": (0.80, 4.00),
        "claude-3-opus-20240229": (15.00, 75.00),
    },
    "google": {
        "gemini-2.0-flash": (0.10, 0.40),
        "gemini-2.5-pro": (1.25, 10.00),
    },
    "deepseek": {
        "deepseek-chat": (0.14, 0.28),
        "deepseek-reasoner": (0.55, 2.19),
    },
    "xiaomi": {
        "mimo-v2.5-pro": (0.0, 0.0),
    },
}


class CostEstimator:
    """Estimates cost per provider/model based on token counts."""

    def __init__(self, custom_table: Optional[Dict[str, Dict[str, Tuple[float, float]]]] = None):
        self.table = custom_table or DEFAULT_COST_TABLE

    def estimate(self, provider: str, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        """Estimate cost in USD."""
        provider_key = provider.lower().replace(" ", "")
        model_key = model.lower().replace(" ", "")

        provider_costs = self.table.get(provider_key, {})
        # Try exact match, then partial
        costs = provider_costs.get(model_key)
        if costs is None:
            for k, v in provider_costs.items():
                if k in model_key or model_key in k:
                    costs = v
                    break

        if costs is None:
            # Unknown model — estimate at $1/M tokens
            return (prompt_tokens + completion_tokens) * 1.0 / 1_000_000

        prompt_rate, completion_rate = costs
        return (prompt_tokens * prompt_rate + completion_tokens * completion_rate) / 1_000_000

    def get_rates(self, provider: str, model: str) -> Tuple[float, float]:
        """Get prompt/completion rates per million tokens."""
        provider_key = provider.lower().replace(" ", "")
        model_key = model.lower().replace(" ", "")
        provider_costs = self.table.get(provider_key, {})
        costs = provider_costs.get(model_key)
        if costs is None:
            for k, v in provider_costs.items():
                if k in model_key or model_key in k:
                    return v
        return costs or (1.0, 1.0)


# ═══════════════════════════════════════════════════════════════
# 📈 Metrics Collector
# ═══════════════════════════════════════════════════════════════

class MetricsCollector:
    """Thread-safe in-memory metrics collection with time-series support."""

    def __init__(self, max_series_length: int = 10000):
        self._max_series = max_series_length
        self._lock = threading.Lock()

        # Token usage
        self._token_records: deque[TokenUsageRecord] = deque(maxlen=max_series_length)

        # Latency
        self._latency_records: deque[LatencyRecord] = deque(maxlen=max_series_length)

        # Errors
        self._errors: deque[ErrorRecord] = deque(maxlen=max_series_length)

        # Agents
        self._agents: Dict[str, AgentActivity] = {}

        # Memory health
        self._memory_health = MemoryHealthMetrics()

        # Custom counters/gauges
        self._counters: Dict[str, float] = defaultdict(float)
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))

        # Usage patterns — hourly buckets
        self._hourly_requests: Dict[int, int] = defaultdict(int)
        self._feature_usage: Dict[str, int] = defaultdict(int)

        # Alerts
        self._alert_rules: Dict[str, AlertRule] = {}
        self._active_alerts: List[Alert] = []
        self._alert_history: deque[Alert] = deque(maxlen=1000)

        # System resources
        self._system_metrics: Dict[str, float] = {}

    # --- Token Tracking ---

    def record_token_usage(
        self,
        conversation_id: str,
        user_id: str,
        provider: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: Optional[float] = None,
    ) -> TokenUsageRecord:
        """Record token usage for a request."""
        total = prompt_tokens + completion_tokens
        if cost_usd is None:
            cost_usd = CostEstimator().estimate(provider, model, prompt_tokens, completion_tokens)

        record = TokenUsageRecord(
            timestamp=time.time(),
            conversation_id=conversation_id,
            user_id=user_id,
            provider=provider,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total,
            cost_usd=cost_usd,
        )

        with self._lock:
            self._token_records.append(record)
            self._hourly_requests[datetime.now().hour] += 1
            self._counters["total_tokens"] += total
            self._counters["total_cost_usd"] += cost_usd
            self._counters["total_requests"] += 1

        return record

    def get_token_usage(
        self,
        user_id: Optional[str] = None,
        provider: Optional[str] = None,
        conversation_id: Optional[str] = None,
        since: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Get token usage summary, optionally filtered."""
        with self._lock:
            records = list(self._token_records)

        if since:
            records = [r for r in records if r.timestamp >= since]
        if user_id:
            records = [r for r in records if r.user_id == user_id]
        if provider:
            records = [r for r in records if r.provider == provider]
        if conversation_id:
            records = [r for r in records if r.conversation_id == conversation_id]

        if not records:
            return {"total_tokens": 0, "total_cost_usd": 0.0, "requests": 0, "by_provider": {}, "by_user": {}}

        total_tokens = sum(r.total_tokens for r in records)
        total_cost = sum(r.cost_usd for r in records)

        by_provider: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"tokens": 0, "cost": 0, "requests": 0})
        by_user: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"tokens": 0, "cost": 0, "requests": 0})

        for r in records:
            bp = by_provider[r.provider]
            bp["tokens"] += r.total_tokens
            bp["cost"] += r.cost_usd
            bp["requests"] += 1

            bu = by_user[r.user_id]
            bu["tokens"] += r.total_tokens
            bu["cost"] += r.cost_usd
            bu["requests"] += 1

        return {
            "total_tokens": total_tokens,
            "total_cost_usd": round(total_cost, 6),
            "requests": len(records),
            "by_provider": dict(by_provider),
            "by_user": dict(by_user),
        }

    # --- Latency Tracking ---

    def record_latency(self, provider: str, operation: str, latency_ms: float, success: bool = True) -> None:
        """Record a latency measurement."""
        record = LatencyRecord(
            timestamp=time.time(),
            provider=provider,
            operation=operation,
            latency_ms=latency_ms,
            success=success,
        )
        with self._lock:
            self._latency_records.append(record)

    def get_latency_stats(self, provider: Optional[str] = None, since: Optional[float] = None) -> Dict[str, Any]:
        """Get latency statistics (p50, p95, p99) per provider."""
        with self._lock:
            records = list(self._latency_records)

        if since:
            records = [r for r in records if r.timestamp >= since]
        if provider:
            records = [r for r in records if r.provider == provider]

        if not records:
            return {"p50": 0, "p95": 0, "p99": 0, "avg": 0, "count": 0, "by_provider": {}}

        latencies = sorted(r.latency_ms for r in records)

        def percentile(data: List[float], p: float) -> float:
            if not data:
                return 0.0
            k = (len(data) - 1) * (p / 100)
            f = int(k)
            c = f + 1
            if c >= len(data):
                return data[-1]
            return data[f] + (k - f) * (data[c] - data[f])

        by_provider: Dict[str, Dict[str, float]] = {}
        prov_records: Dict[str, List[float]] = defaultdict(list)
        for r in records:
            prov_records[r.provider].append(r.latency_ms)

        for prov, lats in prov_records.items():
            lats.sort()
            by_provider[prov] = {
                "p50": round(percentile(lats, 50), 1),
                "p95": round(percentile(lats, 95), 1),
                "p99": round(percentile(lats, 99), 1),
                "avg": round(statistics.mean(lats), 1),
                "count": len(lats),
            }

        return {
            "p50": round(percentile(latencies, 50), 1),
            "p95": round(percentile(latencies, 95), 1),
            "p99": round(percentile(latencies, 99), 1),
            "avg": round(statistics.mean(latencies), 1),
            "count": len(latencies),
            "by_provider": by_provider,
        }

    # --- Agent Activity ---

    def update_agent(self, agent_id: str, name: str, **kwargs: Any) -> None:
        """Update agent activity state."""
        with self._lock:
            if agent_id not in self._agents:
                self._agents[agent_id] = AgentActivity(agent_id=agent_id, name=name)
            agent = self._agents[agent_id]
            for k, v in kwargs.items():
                if hasattr(agent, k):
                    setattr(agent, k, v)
            agent.last_active = time.time()

    def agent_task_started(self, agent_id: str, task: str) -> None:
        """Mark an agent as busy with a task."""
        self.update_agent(
            agent_id,
            agent_id,
            status=AgentStatus.BUSY,
            current_task=task,
            started_at=time.time(),
        )

    def agent_task_completed(self, agent_id: str, success: bool = True) -> None:
        """Mark an agent task as completed."""
        with self._lock:
            agent = self._agents.get(agent_id)
            if agent:
                agent.status = AgentStatus.IDLE
                agent.current_task = ""
                agent.started_at = 0.0
                if success:
                    agent.tasks_completed += 1
                else:
                    agent.tasks_failed += 1

    def get_agent_activities(self) -> List[Dict[str, Any]]:
        """Get all agent activity states."""
        with self._lock:
            return [
                {
                    "agent_id": a.agent_id,
                    "name": a.name,
                    "status": a.status.value,
                    "current_task": a.current_task,
                    "started_at": a.started_at,
                    "last_active": a.last_active,
                    "tasks_completed": a.tasks_completed,
                    "tasks_failed": a.tasks_failed,
                    "error": a.error,
                    "uptime_hours": round((time.time() - a.started_at) / 3600, 2) if a.started_at else 0,
                }
                for a in self._agents.values()
            ]

    # --- Memory Health ---

    def update_memory_health(self, **kwargs: Any) -> None:
        """Update memory health metrics."""
        with self._lock:
            for k, v in kwargs.items():
                if hasattr(self._memory_health, k):
                    setattr(self._memory_health, k, v)
            # Recalculate hit rate
            total = self._memory_health.hit_count + self._memory_health.miss_count
            if total > 0:
                self._memory_health.hit_rate = self._memory_health.hit_count / total

    def get_memory_health(self) -> Dict[str, Any]:
        """Get memory health snapshot."""
        with self._lock:
            return {
                "total_entries": self._memory_health.total_entries,
                "total_size_bytes": self._memory_health.total_size_bytes,
                "total_size_mb": round(self._memory_health.total_size_bytes / (1024 * 1024), 2),
                "hit_count": self._memory_health.hit_count,
                "miss_count": self._memory_health.miss_count,
                "hit_rate": round(self._memory_health.hit_rate, 4),
                "avg_usefulness": round(self._memory_health.avg_usefulness, 2),
                "oldest_entry_age_hours": round(self._memory_health.oldest_entry_age_hours, 1),
                "newest_entry_age_hours": round(self._memory_health.newest_entry_age_hours, 1),
            }

    # --- Error Tracking ---

    def record_error(
        self,
        source: str,
        error: Exception,
        context: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> ErrorRecord:
        """Record an error with full stack trace."""
        record = ErrorRecord(
            error_id=str(uuid.uuid4())[:8],
            timestamp=time.time(),
            source=source,
            error_type=type(error).__name__,
            message=str(error),
            stack_trace=traceback.format_exc(),
            context=context or {},
            user_id=user_id,
            conversation_id=conversation_id,
        )

        with self._lock:
            self._errors.append(record)
            self._counters["total_errors"] += 1
            self._counters[f"errors.{source}"] = self._counters.get(f"errors.{source}", 0) + 1

        self._check_alerts("error_count", self._counters["total_errors"])
        return record

    def get_errors(
        self,
        source: Optional[str] = None,
        since: Optional[float] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Get recent errors."""
        with self._lock:
            errors = list(self._errors)

        if since:
            errors = [e for e in errors if e.timestamp >= since]
        if source:
            errors = [e for e in errors if e.source == source]

        errors.sort(key=lambda e: e.timestamp, reverse=True)
        return [
            {
                "error_id": e.error_id,
                "timestamp": e.timestamp,
                "source": e.source,
                "error_type": e.error_type,
                "message": e.message,
                "stack_trace": e.stack_trace,
                "context": e.context,
                "user_id": e.user_id,
                "resolved": e.resolved,
            }
            for e in errors[:limit]
        ]

    # --- Usage Patterns ---

    def record_feature_usage(self, feature: str) -> None:
        """Record usage of a feature."""
        with self._lock:
            self._feature_usage[feature] += 1

    def get_usage_patterns(self) -> Dict[str, Any]:
        """Get usage patterns — peak hours, most used features."""
        with self._lock:
            hourly = dict(self._hourly_requests)
            features = dict(sorted(
                self._feature_usage.items(),
                key=lambda x: x[1],
                reverse=True,
            )[:20])

        peak_hour = max(hourly, key=hourly.get) if hourly else 0

        return {
            "peak_hour": peak_hour,
            "hourly_requests": hourly,
            "top_features": features,
            "total_requests": int(self._counters.get("total_requests", 0)),
        }

    # --- Custom Metrics ---

    def increment(self, name: str, value: float = 1.0) -> None:
        """Increment a counter."""
        with self._lock:
            self._counters[name] += value

    def set_gauge(self, name: str, value: float) -> None:
        """Set a gauge value."""
        with self._lock:
            self._gauges[name] = value

    def record_histogram(self, name: str, value: float) -> None:
        """Record a histogram value."""
        with self._lock:
            self._histograms[name].append(value)

    # --- System Resources ---

    def collect_system_metrics(self) -> Dict[str, float]:
        """Collect CPU, memory, disk metrics."""
        metrics: Dict[str, float] = {}

        # CPU
        try:
            import psutil
            metrics["cpu_percent"] = psutil.cpu_percent(interval=0.1)
            metrics["cpu_count"] = psutil.cpu_count()
            mem = psutil.virtual_memory()
            metrics["memory_total_gb"] = round(mem.total / (1024**3), 2)
            metrics["memory_used_gb"] = round(mem.used / (1024**3), 2)
            metrics["memory_percent"] = mem.percent
            disk = psutil.disk_usage("/")
            metrics["disk_total_gb"] = round(disk.total / (1024**3), 2)
            metrics["disk_used_gb"] = round(disk.used / (1024**3), 2)
            metrics["disk_percent"] = disk.percent
        except ImportError:
            # Fallback: read from /proc
            try:
                with open("/proc/loadavg") as f:
                    parts = f.read().split()
                    metrics["load_1m"] = float(parts[0])
                    metrics["load_5m"] = float(parts[1])
                    metrics["load_15m"] = float(parts[2])
                with open("/proc/meminfo") as f:
                    meminfo = {}
                    for line in f:
                        k, v = line.split(":")[:2]
                        meminfo[k.strip()] = int(v.strip().split()[0])
                    total = meminfo.get("MemTotal", 0)
                    avail = meminfo.get("MemAvailable", 0)
                    metrics["memory_total_mb"] = round(total / 1024, 1)
                    metrics["memory_available_mb"] = round(avail / 1024, 1)
                    metrics["memory_percent"] = round((1 - avail / total) * 100, 1) if total else 0
            except Exception:
                metrics["cpu_percent"] = -1  # unavailable

        # Process info
        try:
            metrics["process_rss_mb"] = round(
                os.popen("ps -o rss= -p %d" % os.getpid()).read().strip() or "0"
            ) / 1024
        except Exception:
            pass

        with self._lock:
            self._system_metrics = metrics

        return metrics

    # --- Alerting ---

    def add_alert_rule(self, rule: AlertRule) -> None:
        """Add an alert rule."""
        self._alert_rules[rule.name] = rule
        logger.info(f"Added alert rule: {rule.name} ({rule.metric} {rule.comparison} {rule.threshold})")

    def remove_alert_rule(self, name: str) -> None:
        """Remove an alert rule."""
        self._alert_rules.pop(name, None)

    def _check_alerts(self, metric: str, value: float) -> None:
        """Check if any alert rules are triggered."""
        now = time.time()
        for rule in self._alert_rules.values():
            if not rule.enabled or rule.metric != metric:
                continue
            if now - rule.last_triggered < rule.cooldown_seconds:
                continue

            triggered = False
            if rule.comparison == "gt" and value > rule.threshold:
                triggered = True
            elif rule.comparison == "lt" and value < rule.threshold:
                triggered = True
            elif rule.comparison == "gte" and value >= rule.threshold:
                triggered = True
            elif rule.comparison == "lte" and value <= rule.threshold:
                triggered = True
            elif rule.comparison == "eq" and value == rule.threshold:
                triggered = True

            if triggered:
                rule.last_triggered = now
                alert = Alert(
                    alert_id=str(uuid.uuid4())[:8],
                    timestamp=now,
                    severity=rule.severity,
                    metric=metric,
                    message=f"Alert: {metric} = {value} ({rule.comparison} {rule.threshold})",
                    value=value,
                    threshold=rule.threshold,
                )
                self._active_alerts.append(alert)
                self._alert_history.append(alert)
                logger.warning(f"🚨 ALERT [{rule.severity.value}]: {alert.message}")

                if rule.callback:
                    try:
                        rule.callback(alert)
                    except Exception as e:
                        logger.error(f"Alert callback error: {e}")

    def get_alerts(self, active_only: bool = True) -> List[Dict[str, Any]]:
        """Get alerts."""
        alerts = self._active_alerts if active_only else list(self._alert_history)
        return [
            {
                "alert_id": a.alert_id,
                "timestamp": a.timestamp,
                "severity": a.severity.value,
                "metric": a.metric,
                "message": a.message,
                "value": a.value,
                "threshold": a.threshold,
                "resolved": a.resolved,
            }
            for a in alerts
        ]

    def resolve_alert(self, alert_id: str) -> bool:
        """Resolve an active alert."""
        for alert in self._active_alerts:
            if alert.alert_id == alert_id:
                alert.resolved = True
                alert.resolved_at = time.time()
                self._active_alerts.remove(alert)
                return True
        return False

    # --- Dashboard Data ---

    def get_dashboard_data(self) -> Dict[str, Any]:
        """Get comprehensive dashboard data (JSON API)."""
        now = time.time()
        hour_ago = now - 3600
        day_ago = now - 86400

        return {
            "timestamp": now,
            "tokens": self.get_token_usage(since=hour_ago),
            "tokens_24h": self.get_token_usage(since=day_ago),
            "latency": self.get_latency_stats(since=hour_ago),
            "latency_24h": self.get_latency_stats(since=day_ago),
            "agents": self.get_agent_activities(),
            "memory": self.get_memory_health(),
            "errors": self.get_errors(since=hour_ago, limit=10),
            "error_count_24h": len(self.get_errors(since=day_ago)),
            "usage_patterns": self.get_usage_patterns(),
            "system": self.collect_system_metrics(),
            "alerts": self.get_alerts(active_only=True),
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
        }

    # --- Prometheus Export ---

    def export_prometheus(self) -> str:
        """Export all metrics in Prometheus text format."""
        lines: List[str] = []

        # Counters
        for name, value in sorted(self._counters.items()):
            safe_name = name.replace(".", "_").replace("-", "_")
            lines.append(f"# TYPE rally_{safe_name} counter")
            lines.append(f"rally_{safe_name} {value}")

        # Gauges
        for name, value in sorted(self._gauges.items()):
            safe_name = name.replace(".", "_").replace("-", "_")
            lines.append(f"# TYPE rally_{safe_name} gauge")
            lines.append(f"rally_{safe_name} {value}")

        # System metrics
        sys_metrics = self.collect_system_metrics()
        for name, value in sorted(sys_metrics.items()):
            safe_name = name.replace(".", "_").replace("-", "_")
            lines.append(f"# TYPE rally_system_{safe_name} gauge")
            lines.append(f"rally_system_{safe_name} {value}")

        # Latency percentiles
        lat = self.get_latency_stats()
        lines.append(f"# TYPE rally_latency_ms gauge")
        lines.append(f'rally_latency_ms{{quantile="0.5"}} {lat["p50"]}')
        lines.append(f'rally_latency_ms{{quantile="0.95"}} {lat["p95"]}')
        lines.append(f'rally_latency_ms{{quantile="0.99"}} {lat["p99"]}')

        # Agent status
        for agent in self.get_agent_activities():
            lines.append(f'# TYPE rally_agent_status gauge')
            status_val = {"idle": 0, "busy": 1, "error": 2, "offline": 3}.get(agent["status"], -1)
            lines.append(f'rally_agent_status{{agent="{agent["agent_id"]}"}} {status_val}')

        return "\n".join(lines) + "\n"


# ═══════════════════════════════════════════════════════════════
# 🔍 Observability Manager — Top-level Facade
# ═══════════════════════════════════════════════════════════════

class ObservabilityManager:
    """Top-level observability facade.

    Provides convenient methods for all observability operations
    and coordinates the metrics collector, alerting, and health checks.
    """

    def __init__(
        self,
        enable_system_monitoring: bool = True,
        system_poll_interval: float = 30.0,
        metrics_retention_hours: int = 72,
    ):
        self.metrics = MetricsCollector()
        self.cost_estimator = CostEstimator()
        self._enable_system = enable_system_monitoring
        self._poll_interval = system_poll_interval
        self._retention_hours = metrics_retention_hours
        self._system_task: Optional[asyncio.Task] = None
        self._start_time = time.time()

        # Set up default alert rules
        self._setup_default_alerts()

    def _setup_default_alerts(self) -> None:
        """Configure sensible default alert rules."""
        self.metrics.add_alert_rule(AlertRule(
            name="high_error_rate",
            metric="error_count",
            threshold=100,
            severity=AlertSeverity.WARNING,
            comparison="gt",
            cooldown_seconds=600,
        ))
        self.metrics.add_alert_rule(AlertRule(
            name="high_cost",
            metric="total_cost_usd",
            threshold=10.0,
            severity=AlertSeverity.CRITICAL,
            comparison="gt",
            cooldown_seconds=3600,
        ))

    async def start(self) -> None:
        """Start background monitoring tasks."""
        if self._enable_system:
            self._system_task = asyncio.create_task(self._system_monitor_loop())
        logger.info("Observability system started")

    async def stop(self) -> None:
        """Stop background monitoring."""
        if self._system_task:
            self._system_task.cancel()
            try:
                await self._system_task
            except asyncio.CancelledError:
                pass
        logger.info("Observability system stopped")

    async def _system_monitor_loop(self) -> None:
        """Periodically collect system metrics."""
        while True:
            try:
                self.metrics.collect_system_metrics()
                await asyncio.sleep(self._poll_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"System monitor error: {e}")
                await asyncio.sleep(self._poll_interval * 2)

    # --- Convenience Methods ---

    def track_request(
        self,
        provider: str,
        model: str,
        conversation_id: str,
        user_id: str,
        prompt_tokens: int,
        completion_tokens: int,
        latency_ms: float,
        success: bool = True,
    ) -> Dict[str, Any]:
        """Track a complete API request (tokens + latency + cost)."""
        token_record = self.metrics.record_token_usage(
            conversation_id=conversation_id,
            user_id=user_id,
            provider=provider,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
        self.metrics.record_latency(provider, "chat", latency_ms, success)
        self.metrics.record_feature_usage(f"provider.{provider}")
        self.metrics.record_feature_usage(f"model.{model}")

        return {
            "tokens": token_record.total_tokens,
            "cost_usd": round(token_record.cost_usd, 6),
            "latency_ms": round(latency_ms, 1),
        }

    def track_error(self, source: str, error: Exception, **kwargs: Any) -> Dict[str, Any]:
        """Track an error occurrence."""
        record = self.metrics.record_error(source, error, **kwargs)
        return {"error_id": record.error_id, "type": record.error_type}

    def get_health(self) -> Dict[str, Any]:
        """Get overall system health status."""
        uptime = time.time() - self._start_time
        sys_metrics = self.metrics.collect_system_metrics()
        active_alerts = self.metrics.get_alerts(active_only=True)

        # Determine overall status
        status = "healthy"
        if any(a["severity"] == "critical" for a in active_alerts):
            status = "critical"
        elif active_alerts:
            status = "degraded"
        elif sys_metrics.get("cpu_percent", 0) > 90 or sys_metrics.get("memory_percent", 0) > 90:
            status = "degraded"

        return {
            "status": status,
            "uptime_seconds": round(uptime, 1),
            "uptime_human": self._format_uptime(uptime),
            "version": "0.1.0",
            "system": sys_metrics,
            "active_alerts": len(active_alerts),
            "total_requests": int(self.metrics._counters.get("total_requests", 0)),
            "total_errors": int(self.metrics._counters.get("total_errors", 0)),
            "total_tokens": int(self.metrics._counters.get("total_tokens", 0)),
            "total_cost_usd": round(self.metrics._counters.get("total_cost_usd", 0), 4),
        }

    @staticmethod
    def _format_uptime(seconds: float) -> str:
        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        minutes = int((seconds % 3600) // 60)
        if days > 0:
            return f"{days}d {hours}h {minutes}m"
        if hours > 0:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"
