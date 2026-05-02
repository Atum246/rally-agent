"""
Rally Agent — Intelligence Engine
===================================
ProactiveEngine: cron-based tasks, anomaly detection, contextual suggestions, autonomous actions.
LearningEngine: corrections, preferences, workflows, expertise, feedback loops, analytics.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import threading
import time
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("rally.intelligence")


# ============================= Data Types ==================================

class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class FeedbackType(Enum):
    POSITIVE = "positive"   # 👍
    NEGATIVE = "negative"   # 👎
    NEUTRAL = "neutral"     # 🤷
    CORRECTION = "correction"


@dataclass
class BackgroundTask:
    task_id: str
    name: str
    schedule: str  # cron expression or interval like "30m", "2h", "1d"
    handler: str   # handler function name
    payload: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    last_run: Optional[float] = None
    last_status: TaskStatus = TaskStatus.PENDING
    last_error: Optional[str] = None
    next_run: Optional[float] = None
    run_count: int = 0


@dataclass
class Correction:
    correction_id: str
    timestamp: float
    context: str           # What the agent said/did
    correction: str        # What it should have said/done
    category: str          # e.g., "factual", "style", "preference"
    applied: bool = False
    source: str = "user"   # who made the correction


@dataclass
class UserPreference:
    key: str
    value: Any
    confidence: float      # 0.0–1.0
    source: str            # "explicit", "inferred", "corrected"
    last_updated: float = 0.0
    occurrences: int = 1


@dataclass
class WorkflowStep:
    step_id: str
    action: str
    params: Dict[str, Any]
    description: str


@dataclass
class Workflow:
    workflow_id: str
    name: str
    description: str
    steps: List[WorkflowStep]
    trigger_pattern: str    # regex or keyword pattern
    usage_count: int = 0
    created_at: float = 0.0
    last_used: Optional[float] = None


@dataclass
class ExpertiseProfile:
    domain: str
    level: float           # 0.0–1.0
    interactions: int
    last_interaction: float
    topics: List[str] = field(default_factory=list)


@dataclass
class FeedbackEntry:
    feedback_id: str
    timestamp: float
    feedback_type: FeedbackType
    response_id: str       # ID of the response being rated
    content: str           # The response content
    comment: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class UsageEvent:
    timestamp: float
    user_id: str
    action: str
    tool: Optional[str]
    duration_ms: float
    tokens_used: int = 0
    success: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Anomaly:
    anomaly_id: str
    timestamp: float
    category: str          # "usage_spike", "error_burst", "unusual_pattern", "cost_spike"
    severity: float        # 0.0–1.0
    description: str
    details: Dict[str, Any] = field(default_factory=dict)
    acknowledged: bool = False


@dataclass
class Suggestion:
    suggestion_id: str
    timestamp: float
    category: str          # "workflow", "optimization", "reminder", "insight"
    title: str
    description: str
    confidence: float
    actionable: bool = True
    action: Optional[str] = None  # Optional command/action to execute
    dismissed: bool = False


# ========================= Proactive Engine ================================

class ProactiveEngine:
    """
    Background intelligence that runs proactive tasks, detects anomalies,
    generates contextual suggestions, and can take autonomous actions.
    """

    def __init__(self, data_dir: str | Path = "~/.rally/intelligence") -> None:
        self._data_dir = Path(data_dir).expanduser()
        self._data_dir.mkdir(parents=True, exist_ok=True)

        # ---- Background tasks ----
        self._tasks: Dict[str, BackgroundTask] = {}
        self._task_handlers: Dict[str, Callable] = {}
        self._scheduler_running = False
        self._scheduler_thread: Optional[threading.Thread] = None
        self._scheduler_stop = threading.Event()
        self._load_tasks()

        # ---- Anomaly detection ----
        self._usage_events: List[UsageEvent] = []
        self._anomalies: List[Anomaly] = []
        self._baselines: Dict[str, Dict[str, float]] = {}
        self._load_anomalies()

        # ---- Contextual suggestions ----
        self._suggestions: List[Suggestion] = []
        self._suggestion_history: Set[str] = set()  # hash of past suggestions
        self._load_suggestions()

        # ---- Autonomous actions ----
        self._autonomous_enabled = False
        self._autonomous_whitelist: Set[str] = set()
        self._pending_actions: List[Dict[str, Any]] = []

    # ====================================================================
    #  Background Task Scheduler
    # ====================================================================

    def register_task(
        self,
        name: str,
        schedule: str,
        handler: Callable,
        payload: Optional[Dict[str, Any]] = None,
        enabled: bool = True,
    ) -> str:
        """Register a cron-like background task."""
        task_id = hashlib.md5(name.encode()).hexdigest()[:12]
        self._tasks[task_id] = BackgroundTask(
            task_id=task_id,
            name=name,
            schedule=schedule,
            handler=handler.__name__,
            payload=payload or {},
            enabled=enabled,
            next_run=self._compute_next_run(schedule),
        )
        self._task_handlers[handler.__name__] = handler
        self._save_tasks()
        logger.info("Registered task '%s' (id=%s) schedule=%s", name, task_id, schedule)
        return task_id

    def unregister_task(self, task_id: str) -> bool:
        if task_id in self._tasks:
            del self._tasks[task_id]
            self._save_tasks()
            return True
        return False

    def _compute_next_run(self, schedule: str, from_time: Optional[float] = None) -> float:
        """Compute next run time from schedule string."""
        now = from_time or time.time()

        # Simple interval format: "30m", "2h", "1d", "45s"
        interval = self._parse_interval(schedule)
        if interval is not None:
            return now + interval

        # Cron format: "m h dom mon dow"  (simplified)
        # For now, just parse basic cron fields
        try:
            parts = schedule.strip().split()
            if len(parts) == 5:
                return self._next_cron_time(parts, now)
        except Exception:
            pass

        # Default: run in 1 hour
        return now + 3600

    @staticmethod
    def _parse_interval(s: str) -> Optional[float]:
        """Parse interval strings like '30m', '2h', '1d', '45s'."""
        s = s.strip().lower()
        multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
        if s and s[-1] in multipliers and s[:-1].isdigit():
            return int(s[:-1]) * multipliers[s[-1]]
        return None

    @staticmethod
    def _next_cron_time(fields: List[str], from_time: float) -> float:
        """Very simplified cron parser — finds next matching minute."""
        # fields: minute, hour, dom, month, dow
        # For production, use `croniter` library
        from datetime import datetime as dt
        now = dt.fromtimestamp(from_time)

        # Simple case: all wildcards → next minute
        if all(f == "*" for f in fields):
            return from_time + 60

        # Try next 1440 minutes
        for offset in range(1, 1441):
            candidate = now + timedelta(minutes=offset)
            if _cron_match(fields, candidate):
                return candidate.timestamp()

        return from_time + 3600  # fallback

    def start_scheduler(self, poll_interval: float = 10.0) -> None:
        """Start the background task scheduler."""
        if self._scheduler_running:
            return
        self._scheduler_running = True
        self._scheduler_stop.clear()

        def _run():
            logger.info("Task scheduler started")
            while not self._scheduler_stop.is_set():
                try:
                    self._tick()
                except Exception as e:
                    logger.error("Scheduler tick error: %s", e)
                self._scheduler_stop.wait(poll_interval)
            logger.info("Task scheduler stopped")

        self._scheduler_thread = threading.Thread(target=_run, daemon=True, name="rally-scheduler")
        self._scheduler_thread.start()

    def stop_scheduler(self) -> None:
        self._scheduler_running = False
        self._scheduler_stop.set()
        if self._scheduler_thread:
            self._scheduler_thread.join(timeout=5)

    def _tick(self) -> None:
        """Run any tasks whose next_run has arrived."""
        now = time.time()
        for task in self._tasks.values():
            if not task.enabled:
                continue
            if task.next_run is None or task.next_run > now:
                continue
            self._run_task(task)

    def _run_task(self, task: BackgroundTask) -> None:
        """Execute a single background task."""
        handler = self._task_handlers.get(task.handler)
        if handler is None:
            logger.warning("No handler for task '%s' (handler=%s)", task.name, task.handler)
            task.last_status = TaskStatus.SKIPPED
            task.next_run = self._compute_next_run(task.schedule)
            return

        task.last_status = TaskStatus.RUNNING
        task.last_run = time.time()
        try:
            result = handler(task.payload)
            task.last_status = TaskStatus.COMPLETED
            task.run_count += 1
            task.last_error = None
            logger.info("Task '%s' completed: %s", task.name, result)
        except Exception as e:
            task.last_status = TaskStatus.FAILED
            task.last_error = str(e)
            logger.error("Task '%s' failed: %s", task.name, e)

        task.next_run = self._compute_next_run(task.schedule)
        self._save_tasks()

    def list_tasks(self) -> List[Dict[str, Any]]:
        return [
            {
                "task_id": t.task_id,
                "name": t.name,
                "schedule": t.schedule,
                "enabled": t.enabled,
                "last_run": t.last_run,
                "last_status": t.last_status.value,
                "next_run": t.next_run,
                "run_count": t.run_count,
                "last_error": t.last_error,
            }
            for t in self._tasks.values()
        ]

    # ====================================================================
    #  Anomaly Detection
    # ====================================================================

    def record_usage(self, event: UsageEvent) -> None:
        """Record a usage event for anomaly detection."""
        self._usage_events.append(event)
        # Keep last 10000 events
        if len(self._usage_events) > 10000:
            self._usage_events = self._usage_events[-10000:]
        self._check_anomalies(event)

    def _check_anomalies(self, event: UsageEvent) -> None:
        """Check for anomalies after recording an event."""
        now = event.timestamp

        # Check usage spike (events per minute in last 5 min)
        recent = [e for e in self._usage_events if now - e.timestamp < 300]
        rate = len(recent) / 5.0  # events per minute
        baseline = self._baselines.get("events_per_minute", {})
        mean = baseline.get("mean", 10)
        std = baseline.get("std", 5)
        if rate > mean + 3 * std and rate > 20:
            self._add_anomaly(
                "usage_spike",
                min(1.0, (rate - mean) / (mean + 1)),
                f"Usage rate spike: {rate:.1f} events/min (baseline: {mean:.1f})",
                {"rate": rate, "baseline_mean": mean},
            )

        # Check error burst
        recent_errors = [e for e in recent if not e.success]
        error_rate = len(recent_errors) / max(1, len(recent))
        if error_rate > 0.5 and len(recent_errors) > 5:
            self._add_anomaly(
                "error_burst",
                error_rate,
                f"Error burst: {len(recent_errors)} errors in last 5 min ({error_rate:.0%} rate)",
                {"error_count": len(recent_errors), "total": len(recent)},
            )

        # Check unusual tool usage
        tool_counts = Counter(e.tool for e in recent if e.tool)
        for tool, count in tool_counts.most_common(3):
            tool_baseline = self._baselines.get(f"tool_{tool}", {})
            tool_mean = tool_baseline.get("mean", 5)
            if count > tool_mean * 5 and count > 20:
                self._add_anomaly(
                    "unusual_pattern",
                    min(1.0, count / (tool_mean * 10)),
                    f"Unusual '{tool}' usage: {count} calls in 5 min (baseline: {tool_mean})",
                    {"tool": tool, "count": count},
                )

    def _add_anomaly(
        self,
        category: str,
        severity: float,
        description: str,
        details: Dict[str, Any],
    ) -> None:
        anomaly = Anomaly(
            anomaly_id=uuid.uuid4().hex[:12],
            timestamp=time.time(),
            category=category,
            severity=severity,
            description=description,
            details=details,
        )
        self._anomalies.append(anomaly)
        self._save_anomalies()
        logger.warning("Anomaly detected: [%s] %s (severity=%.2f)", category, description, severity)

    def get_anomalies(
        self,
        since: Optional[float] = None,
        category: Optional[str] = None,
        min_severity: float = 0.0,
        unacknowledged_only: bool = False,
    ) -> List[Dict[str, Any]]:
        result = []
        for a in self._anomalies:
            if since and a.timestamp < since:
                continue
            if category and a.category != category:
                continue
            if a.severity < min_severity:
                continue
            if unacknowledged_only and a.acknowledged:
                continue
            result.append({
                "anomaly_id": a.anomaly_id,
                "timestamp": a.timestamp,
                "category": a.category,
                "severity": a.severity,
                "description": a.description,
                "details": a.details,
                "acknowledged": a.acknowledged,
            })
        return result

    def acknowledge_anomaly(self, anomaly_id: str) -> bool:
        for a in self._anomalies:
            if a.anomaly_id == anomaly_id:
                a.acknowledged = True
                self._save_anomalies()
                return True
        return False

    def update_baselines(self) -> None:
        """Recompute baselines from recent usage data."""
        now = time.time()
        # Use last 24h of data
        recent = [e for e in self._usage_events if now - e.timestamp < 86400]
        if not recent:
            return

        # Events per minute (in 5-min windows)
        windows: Dict[int, int] = defaultdict(int)
        for e in recent:
            window_key = int(e.timestamp // 300)
            windows[window_key] += 1
        rates = [v / 5.0 for v in windows.values()]
        if rates:
            self._baselines["events_per_minute"] = {
                "mean": sum(rates) / len(rates),
                "std": _stddev(rates),
            }

        # Per-tool rates
        tool_events: Dict[str, List[int]] = defaultdict(list)
        for e in recent:
            if e.tool:
                tool_events[e.tool].append(int(e.timestamp // 300))
        for tool, windows_list in tool_events.items():
            counts = Counter(windows_list)
            rates = [v / 5.0 for v in counts.values()]
            self._baselines[f"tool_{tool}"] = {
                "mean": sum(rates) / len(rates),
                "std": _stddev(rates),
            }

        self._save_baselines()
        logger.info("Updated baselines: %s", list(self._baselines.keys()))

    # ====================================================================
    #  Contextual Suggestions
    # ====================================================================

    def generate_suggestions(
        self,
        *,
        current_time: Optional[datetime] = None,
        recent_actions: Optional[List[str]] = None,
        project_state: Optional[Dict[str, Any]] = None,
        user_preferences: Optional[Dict[str, Any]] = None,
    ) -> List[Suggestion]:
        """Generate contextual suggestions based on time, activity, and state."""
        now = current_time or datetime.now()
        suggestions: List[Suggestion] = []
        actions = recent_actions or []
        prefs = user_preferences or {}
        project = project_state or {}

        # Time-based suggestions
        hour = now.hour
        if 8 <= hour <= 10 and "morning_briefing" not in self._suggestion_history:
            suggestions.append(self._make_suggestion(
                "reminder", "Morning Briefing",
                "Start your day with a summary of emails, calendar, and news.",
                0.8, action="briefing:morning",
            ))

        if 17 <= hour <= 18 and "daily_summary" not in self._suggestion_history:
            suggestions.append(self._make_suggestion(
                "reminder", "Daily Summary",
                "Wrap up the day — here's what was accomplished and what's pending.",
                0.7, action="summary:daily",
            ))

        # Activity-based suggestions
        if actions:
            action_counts = Counter(actions)
            # Repetitive action → suggest automation
            for action, count in action_counts.items():
                if count >= 5 and f"auto:{action}" not in self._suggestion_history:
                    suggestions.append(self._make_suggestion(
                        "workflow", f"Automate '{action}'",
                        f"You've performed '{action}' {count} times. Want to create a workflow?",
                        0.75, action=f"workflow:create:{action}",
                    ))

            # Error-prone sequences
            error_actions = [a for a in actions if "error" in a.lower() or "fail" in a.lower()]
            if len(error_actions) >= 3:
                suggestions.append(self._make_suggestion(
                    "optimization", "Error Pattern Detected",
                    f"Multiple errors detected recently. Consider reviewing your workflow.",
                    0.6,
                ))

        # Project-state suggestions
        if project:
            git_dirty = project.get("git_dirty", False)
            branch = project.get("branch", "")
            if git_dirty and "commit_reminder" not in self._suggestion_history:
                suggestions.append(self._make_suggestion(
                    "reminder", "Uncommitted Changes",
                    "You have uncommitted changes. Consider committing before switching context.",
                    0.65, action="git:commit_suggest",
                ))

            open_issues = project.get("open_issues", 0)
            if open_issues > 10:
                suggestions.append(self._make_suggestion(
                    "insight", "Issue Backlog Growing",
                    f"{open_issues} issues open. Consider triaging or closing stale ones.",
                    0.5,
                ))

        # Preference-based suggestions
        if prefs.get("coding_language") and "scaffold" not in self._suggestion_history:
            lang = prefs["coding_language"]
            suggestions.append(self._make_suggestion(
                "optimization", f"{lang} Project Scaffolding",
                f"I can scaffold a new {lang} project with your preferred structure.",
                0.4, action=f"scaffold:{lang}",
            ))

        # Deduplicate
        seen = set()
        unique = []
        for s in suggestions:
            key = f"{s.category}:{s.title}"
            if key not in seen:
                seen.add(key)
                unique.append(s)

        return unique

    def _make_suggestion(
        self,
        category: str,
        title: str,
        description: str,
        confidence: float,
        action: Optional[str] = None,
    ) -> Suggestion:
        sid = uuid.uuid4().hex[:12]
        self._suggestion_history.add(f"{category}:{title}")
        return Suggestion(
            suggestion_id=sid,
            timestamp=time.time(),
            category=category,
            title=title,
            description=description,
            confidence=confidence,
            action=action,
        )

    def dismiss_suggestion(self, suggestion_id: str) -> bool:
        for s in self._suggestions:
            if s.suggestion_id == suggestion_id:
                s.dismissed = True
                return True
        return False

    # ====================================================================
    #  Autonomous Actions
    # ====================================================================

    def enable_autonomous(self, whitelist: Optional[Set[str]] = None) -> None:
        self._autonomous_enabled = True
        if whitelist:
            self._autonomous_whitelist = whitelist

    def disable_autonomous(self) -> None:
        self._autonomous_enabled = False

    def queue_autonomous_action(
        self,
        action: str,
        params: Dict[str, Any],
        reason: str,
    ) -> Optional[str]:
        """Queue an autonomous action for execution (requires approval if not whitelisted)."""
        if not self._autonomous_enabled:
            return None

        action_id = uuid.uuid4().hex[:12]
        entry = {
            "action_id": action_id,
            "action": action,
            "params": params,
            "reason": reason,
            "timestamp": time.time(),
            "approved": action in self._autonomous_whitelist,
        }
        self._pending_actions.append(entry)
        return action_id

    def approve_action(self, action_id: str) -> Optional[Dict[str, Any]]:
        """Approve a pending autonomous action."""
        for entry in self._pending_actions:
            if entry["action_id"] == action_id:
                entry["approved"] = True
                return entry
        return None

    def get_pending_actions(self) -> List[Dict[str, Any]]:
        return [a for a in self._pending_actions if not a.get("approved")]

    # ====================================================================
    #  Persistence
    # ====================================================================

    def _load_tasks(self) -> None:
        path = self._data_dir / "tasks.json"
        if path.exists():
            try:
                data = json.loads(path.read_text())
                for item in data:
                    task = BackgroundTask(**item)
                    task.last_status = TaskStatus(item["last_status"])
                    self._tasks[task.task_id] = task
            except Exception as e:
                logger.error("Failed to load tasks: %s", e)

    def _save_tasks(self) -> None:
        path = self._data_dir / "tasks.json"
        data = []
        for t in self._tasks.values():
            d = t.__dict__.copy()
            d["last_status"] = t.last_status.value
            data.append(d)
        path.write_text(json.dumps(data, indent=2, default=str))

    def _load_anomalies(self) -> None:
        path = self._data_dir / "anomalies.json"
        if path.exists():
            try:
                self._anomalies = [Anomaly(**a) for a in json.loads(path.read_text())]
            except Exception:
                self._anomalies = []

    def _save_anomalies(self) -> None:
        path = self._data_dir / "anomalies.json"
        path.write_text(json.dumps([a.__dict__ for a in self._anomalies], indent=2, default=str))

    def _load_suggestions(self) -> None:
        path = self._data_dir / "suggestions.json"
        if path.exists():
            try:
                self._suggestions = [Suggestion(**s) for s in json.loads(path.read_text())]
            except Exception:
                self._suggestions = []

    def _save_suggestions(self) -> None:
        path = self._data_dir / "suggestions.json"
        path.write_text(json.dumps([s.__dict__ for s in self._suggestions], indent=2, default=str))

    def _save_baselines(self) -> None:
        path = self._data_dir / "baselines.json"
        path.write_text(json.dumps(self._baselines, indent=2))


# =========================== Learning Engine ================================

class LearningEngine:
    """
    Learns from user interactions: corrections, preferences, workflows,
    expertise profiling, feedback loops, and analytics.
    """

    def __init__(self, data_dir: str | Path = "~/.rally/intelligence") -> None:
        self._data_dir = Path(data_dir).expanduser()
        self._data_dir.mkdir(parents=True, exist_ok=True)

        # ---- Corrections ----
        self._corrections: List[Correction] = []
        self._load_corrections()

        # ---- Preferences ----
        self._preferences: Dict[str, UserPreference] = {}
        self._load_preferences()

        # ---- Workflows ----
        self._workflows: Dict[str, Workflow] = {}
        self._load_workflows()

        # ---- Expertise ----
        self._expertise: Dict[str, ExpertiseProfile] = {}
        self._load_expertise()

        # ---- Feedback ----
        self._feedback: List[FeedbackEntry] = []
        self._load_feedback()

        # ---- Interaction recording ----
        self._interaction_buffer: List[Dict[str, Any]] = []
        self._record_lock = threading.Lock()

    # ====================================================================
    #  Correction Storage & Retrieval
    # ====================================================================

    def store_correction(
        self,
        context: str,
        correction: str,
        category: str = "general",
        source: str = "user",
    ) -> str:
        """Store a correction from the user."""
        cid = uuid.uuid4().hex[:12]
        c = Correction(
            correction_id=cid,
            timestamp=time.time(),
            context=context,
            correction=correction,
            category=category,
            source=source,
        )
        self._corrections.append(c)
        self._save_corrections()
        logger.info("Correction stored: %s (%s)", cid, category)
        return cid

    def apply_corrections(self, context: str, threshold: float = 0.6) -> List[str]:
        """Find and return relevant corrections for a given context."""
        relevant = []
        context_lower = context.lower()
        for c in self._corrections:
            if c.applied:
                continue
            # Simple similarity: word overlap
            similarity = self._text_similarity(context_lower, c.context.lower())
            if similarity >= threshold:
                relevant.append(c.correction)
                c.applied = True
        if relevant:
            self._save_corrections()
        return relevant

    def get_corrections(
        self,
        category: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        result = []
        for c in reversed(self._corrections):
            if category and c.category != category:
                continue
            result.append(c.__dict__)
            if len(result) >= limit:
                break
        return result

    def search_corrections(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search corrections by semantic similarity."""
        query_lower = query.lower()
        scored = []
        for c in self._corrections:
            sim = max(
                self._text_similarity(query_lower, c.context.lower()),
                self._text_similarity(query_lower, c.correction.lower()),
            )
            scored.append((sim, c))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [c.__dict__ for _, c in scored[:limit]]

    # ====================================================================
    #  Preference Extraction & Application
    # ====================================================================

    def set_preference(
        self,
        key: str,
        value: Any,
        source: str = "explicit",
        confidence: float = 1.0,
    ) -> None:
        """Set a user preference explicitly."""
        now = time.time()
        if key in self._preferences:
            pref = self._preferences[key]
            pref.value = value
            pref.source = source
            pref.confidence = confidence
            pref.last_updated = now
            pref.occurrences += 1
        else:
            self._preferences[key] = UserPreference(
                key=key,
                value=value,
                confidence=confidence,
                source=source,
                last_updated=now,
            )
        self._save_preferences()

    def infer_preference(self, key: str, value: Any, weight: float = 0.3) -> None:
        """Infer a preference from observed behavior (lower confidence)."""
        now = time.time()
        if key in self._preferences:
            pref = self._preferences[key]
            if pref.value == value:
                # Reinforce
                pref.confidence = min(1.0, pref.confidence + weight * 0.1)
                pref.occurrences += 1
                pref.last_updated = now
            else:
                # Conflict — reduce confidence of old, track new
                pref.confidence = max(0.1, pref.confidence - weight * 0.05)
                if pref.confidence < 0.3:
                    # Replace
                    pref.value = value
                    pref.confidence = weight
                    pref.source = "inferred"
                    pref.last_updated = now
        else:
            self._preferences[key] = UserPreference(
                key=key,
                value=value,
                confidence=weight,
                source="inferred",
                last_updated=now,
            )
        self._save_preferences()

    def get_preference(self, key: str, default: Any = None) -> Any:
        pref = self._preferences.get(key)
        if pref and pref.confidence >= 0.3:
            return pref.value
        return default

    def get_all_preferences(self, min_confidence: float = 0.0) -> Dict[str, Any]:
        return {
            k: p.value
            for k, p in self._preferences.items()
            if p.confidence >= min_confidence
        }

    def extract_preferences_from_text(self, text: str) -> Dict[str, Any]:
        """
        Extract preference signals from user text.
        e.g., "I prefer dark mode" → {"theme": "dark"}
        """
        extracted: Dict[str, Any] = {}
        text_lower = text.lower()

        # Simple pattern matching for common preferences
        patterns = {
            r"i (?:prefer|like|want|use)\s+(dark\s*mode|dark\s*theme)": ("theme", "dark"),
            r"i (?:prefer|like|want|use)\s+(light\s*mode|light\s*theme)": ("theme", "light"),
            r"i (?:prefer|like|want|use)\s+(\w+)\s+(?:for|as)\s+(?:coding|programming)": ("coding_language", None),
            r"(?:use|call me|my name is)\s+(\w+)": ("preferred_name", None),
            r"i('m| am)\s+(?:in|from)\s+(\w+(?:\s+\w+)?)\s+(?:timezone|time\s*zone)": ("timezone", None),
            r"speak\s+(?:to me )?(?:in\s+)?(english|chinese|spanish|french|german|japanese|korean)": ("language", None),
            r"i (?:prefer|like)\s+(brief|detailed|concise|verbose)\s+(?:responses?|answers?|replies?)": ("verbosity", None),
        }

        for pattern, (key, static_val) in patterns.items():
            m = re.search(pattern, text_lower)
            if m:
                value = static_val if static_val else m.group(1).strip()
                extracted[key] = value
                self.infer_preference(key, value, weight=0.5)

        return extracted

    # ====================================================================
    #  Workflow Recording & Automation
    # ====================================================================

    def start_recording(self) -> str:
        """Start recording a workflow. Returns recording ID."""
        recording_id = uuid.uuid4().hex[:12]
        with self._record_lock:
            self._interaction_buffer = []
        return recording_id

    def record_step(
        self,
        action: str,
        params: Dict[str, Any],
        description: str = "",
    ) -> None:
        """Record a step in the current workflow."""
        with self._record_lock:
            self._interaction_buffer.append({
                "action": action,
                "params": params,
                "description": description,
                "timestamp": time.time(),
            })

    def stop_recording(
        self,
        recording_id: str,
        name: str,
        trigger_pattern: str = "",
    ) -> Optional[str]:
        """Stop recording and save as a workflow."""
        with self._record_lock:
            steps = list(self._interaction_buffer)
            self._interaction_buffer = []

        if not steps:
            return None

        workflow_id = uuid.uuid4().hex[:12]
        workflow_steps = [
            WorkflowStep(
                step_id=uuid.uuid4().hex[:8],
                action=s["action"],
                params=s["params"],
                description=s["description"],
            )
            for s in steps
        ]

        workflow = Workflow(
            workflow_id=workflow_id,
            name=name,
            description=f"Recorded workflow with {len(steps)} steps",
            steps=workflow_steps,
            trigger_pattern=trigger_pattern or name.lower().replace(" ", "_"),
            created_at=time.time(),
        )
        self._workflows[workflow_id] = workflow
        self._save_workflows()
        logger.info("Workflow '%s' saved with %d steps", name, len(steps))
        return workflow_id

    def suggest_automation(self, recent_actions: List[str]) -> Optional[Dict[str, Any]]:
        """
        Analyze recent actions and suggest automation if a pattern is detected.
        """
        if len(recent_actions) < 5:
            return None

        # Look for repeated subsequences of length 2-5
        for seq_len in range(2, 6):
            for i in range(len(recent_actions) - seq_len * 2 + 1):
                seq = recent_actions[i:i + seq_len]
                # Check if this sequence appears again later
                for j in range(i + seq_len, len(recent_actions) - seq_len + 1):
                    if recent_actions[j:j + seq_len] == seq:
                        return {
                            "pattern": seq,
                            "suggestion": f"I noticed you repeat '{' → '.join(seq)}' frequently. Want me to automate it?",
                            "confidence": 0.7,
                        }
        return None

    def get_workflows(self) -> List[Dict[str, Any]]:
        return [w.__dict__ for w in self._workflows.values()]

    def execute_workflow(self, workflow_id: str) -> Optional[List[WorkflowStep]]:
        wf = self._workflows.get(workflow_id)
        if wf is None:
            return None
        wf.usage_count += 1
        wf.last_used = time.time()
        self._save_workflows()
        return wf.steps

    def find_matching_workflow(self, user_input: str) -> Optional[Workflow]:
        """Find a workflow that matches the user's input."""
        user_lower = user_input.lower()
        best_match = None
        best_score = 0.0

        for wf in self._workflows.values():
            if not wf.trigger_pattern:
                continue
            # Check keyword match
            keywords = wf.trigger_pattern.lower().replace("_", " ").split()
            matches = sum(1 for kw in keywords if kw in user_lower)
            score = matches / max(1, len(keywords))
            if score > best_score and score >= 0.5:
                best_score = score
                best_match = wf

        return best_match

    # ====================================================================
    #  Expertise Profiling
    # ====================================================================

    def update_expertise(self, domain: str, topics: List[str], interaction_count: int = 1) -> None:
        """Update expertise profile for a domain."""
        now = time.time()
        if domain in self._expertise:
            ep = self._expertise[domain]
            ep.interactions += interaction_count
            ep.last_interaction = now
            ep.topics = list(set(ep.topics + topics))[:50]  # Keep top 50
            # Level grows logarithmically
            ep.level = min(1.0, math.log1p(ep.interactions) / math.log1p(1000))
        else:
            self._expertise[domain] = ExpertiseProfile(
                domain=domain,
                level=0.1,
                interactions=interaction_count,
                last_interaction=now,
                topics=topics,
            )
        self._save_expertise()

    def get_expertise(self, domain: Optional[str] = None) -> Dict[str, Any]:
        if domain:
            ep = self._expertise.get(domain)
            return ep.__dict__ if ep else {}
        return {d: ep.__dict__ for d, ep in self._expertise.items()}

    def get_expertise_summary(self) -> Dict[str, float]:
        """Get domain → level mapping sorted by expertise level."""
        return dict(
            sorted(
                {d: ep.level for d, ep in self._expertise.items()}.items(),
                key=lambda x: x[1],
                reverse=True,
            )
        )

    # ====================================================================
    #  Feedback Loops
    # ====================================================================

    def record_feedback(
        self,
        response_id: str,
        feedback_type: FeedbackType,
        content: str = "",
        comment: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Record user feedback on a response."""
        fid = uuid.uuid4().hex[:12]
        entry = FeedbackEntry(
            feedback_id=fid,
            timestamp=time.time(),
            feedback_type=feedback_type,
            response_id=response_id,
            content=content,
            comment=comment,
            context=context or {},
        )
        self._feedback.append(entry)
        self._save_feedback()

        # If correction feedback, also store as correction
        if feedback_type == FeedbackType.CORRECTION and comment:
            self.store_correction(content, comment, category="feedback", source="user_feedback")

        return fid

    def get_feedback_stats(self, days: int = 30) -> Dict[str, Any]:
        """Get feedback statistics for the given period."""
        cutoff = time.time() - days * 86400
        recent = [f for f in self._feedback if f.timestamp >= cutoff]

        if not recent:
            return {"total": 0, "positive_rate": 0.0, "by_type": {}}

        by_type = Counter(f.feedback_type.value for f in recent)
        positive = by_type.get("positive", 0)
        total = len(recent)

        return {
            "total": total,
            "by_type": dict(by_type),
            "positive_rate": positive / total if total > 0 else 0.0,
            "negative_rate": by_type.get("negative", 0) / total if total > 0 else 0.0,
            "correction_count": by_type.get("correction", 0),
            "recent_comments": [
                f.comment for f in recent[-10:] if f.comment
            ],
        }

    def get_improvement_areas(self) -> List[Dict[str, Any]]:
        """Identify areas needing improvement based on negative feedback."""
        negative = [
            f for f in self._feedback
            if f.feedback_type in (FeedbackType.NEGATIVE, FeedbackType.CORRECTION)
        ]
        if not negative:
            return []

        # Group by context patterns
        categories: Dict[str, int] = Counter()
        for f in negative:
            ctx = f.context.get("category", "general")
            categories[ctx] += 1

        return [
            {"area": area, "negative_count": count, "priority": "high" if count > 5 else "medium"}
            for area, count in categories.most_common(10)
        ]

    # ====================================================================
    #  Learning Analytics
    # ====================================================================

    def get_analytics(self) -> Dict[str, Any]:
        """Comprehensive learning analytics."""
        now = time.time()
        day_ago = now - 86400
        week_ago = now - 7 * 86400

        recent_corrections = [c for c in self._corrections if c.timestamp >= week_ago]
        recent_feedback = [f for f in self._feedback if f.timestamp >= week_ago]

        # Preference coverage
        high_conf = sum(1 for p in self._preferences.values() if p.confidence >= 0.7)
        med_conf = sum(1 for p in self._preferences.values() if 0.3 <= p.confidence < 0.7)

        return {
            "corrections": {
                "total": len(self._corrections),
                "this_week": len(recent_corrections),
                "by_category": dict(Counter(c.category for c in self._corrections)),
                "applied_rate": (
                    sum(1 for c in self._corrections if c.applied) / max(1, len(self._corrections))
                ),
            },
            "preferences": {
                "total": len(self._preferences),
                "high_confidence": high_conf,
                "medium_confidence": med_conf,
                "sources": dict(Counter(p.source for p in self._preferences.values())),
            },
            "workflows": {
                "total": len(self._workflows),
                "most_used": sorted(
                    [(w.name, w.usage_count) for w in self._workflows.values()],
                    key=lambda x: x[1],
                    reverse=True,
                )[:5],
            },
            "expertise": {
                "domains": len(self._expertise),
                "top_domains": [
                    {"domain": d, "level": ep.level, "interactions": ep.interactions}
                    for d, ep in sorted(
                        self._expertise.items(),
                        key=lambda x: x[1].level,
                        reverse=True,
                    )[:5]
                ],
            },
            "feedback": self.get_feedback_stats(days=7),
            "improvement_areas": self.get_improvement_areas(),
        }

    # ====================================================================
    #  Text Similarity (simple, no external deps)
    # ====================================================================

    @staticmethod
    def _text_similarity(a: str, b: str) -> float:
        """Jaccard similarity on word sets."""
        words_a = set(a.lower().split())
        words_b = set(b.lower().split())
        if not words_a or not words_b:
            return 0.0
        intersection = words_a & words_b
        union = words_a | words_b
        return len(intersection) / len(union)

    # ====================================================================
    #  Persistence
    # ====================================================================

    def _load_corrections(self) -> None:
        path = self._data_dir / "corrections.json"
        if path.exists():
            try:
                self._corrections = [Correction(**c) for c in json.loads(path.read_text())]
            except Exception:
                self._corrections = []

    def _save_corrections(self) -> None:
        path = self._data_dir / "corrections.json"
        path.write_text(json.dumps([c.__dict__ for c in self._corrections], indent=2, default=str))

    def _load_preferences(self) -> None:
        path = self._data_dir / "preferences.json"
        if path.exists():
            try:
                data = json.loads(path.read_text())
                self._preferences = {k: UserPreference(**v) for k, v in data.items()}
            except Exception:
                self._preferences = {}

    def _save_preferences(self) -> None:
        path = self._data_dir / "preferences.json"
        path.write_text(json.dumps(
            {k: p.__dict__ for k, p in self._preferences.items()},
            indent=2, default=str,
        ))

    def _load_workflows(self) -> None:
        path = self._data_dir / "workflows.json"
        if path.exists():
            try:
                data = json.loads(path.read_text())
                for item in data:
                    steps = [WorkflowStep(**s) for s in item.pop("steps", [])]
                    wf = Workflow(**item, steps=steps)
                    self._workflows[wf.workflow_id] = wf
            except Exception:
                self._workflows = {}

    def _save_workflows(self) -> None:
        path = self._data_dir / "workflows.json"
        data = []
        for wf in self._workflows.values():
            d = wf.__dict__.copy()
            d["steps"] = [s.__dict__ for s in wf.steps]
            data.append(d)
        path.write_text(json.dumps(data, indent=2, default=str))

    def _load_expertise(self) -> None:
        path = self._data_dir / "expertise.json"
        if path.exists():
            try:
                data = json.loads(path.read_text())
                self._expertise = {k: ExpertiseProfile(**v) for k, v in data.items()}
            except Exception:
                self._expertise = {}

    def _save_expertise(self) -> None:
        path = self._data_dir / "expertise.json"
        path.write_text(json.dumps(
            {k: ep.__dict__ for k, ep in self._expertise.items()},
            indent=2, default=str,
        ))

    def _load_feedback(self) -> None:
        path = self._data_dir / "feedback.json"
        if path.exists():
            try:
                raw = json.loads(path.read_text())
                self._feedback = []
                for f in raw:
                    if isinstance(f.get("feedback_type"), str):
                        f["feedback_type"] = FeedbackType(f["feedback_type"])
                    self._feedback.append(FeedbackEntry(**f))
            except Exception:
                self._feedback = []

    def _save_feedback(self) -> None:
        path = self._data_dir / "feedback.json"
        path.write_text(json.dumps([f.__dict__ for f in self._feedback], indent=2, default=str))


# ============================= Helpers =====================================

def _cron_match(fields: List[str], dt: datetime) -> bool:
    """Check if a datetime matches cron fields (minute, hour, dom, month, dow)."""
    checks = [
        (fields[0], dt.minute),
        (fields[1], dt.hour),
        (fields[2], dt.day),
        (fields[3], dt.month),
        (fields[4], dt.weekday()),
    ]
    for field_str, value in checks:
        if field_str == "*":
            continue
        if "/" in field_str:
            base, step = field_str.split("/")
            if base == "*":
                if value % int(step) != 0:
                    return False
                continue
        if field_str.isdigit():
            if int(field_str) != value:
                return False
            continue
        if "," in field_str:
            if value not in [int(x) for x in field_str.split(",")]:
                return False
            continue
        return False
    return True


def _stddev(values: List[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
    return math.sqrt(variance)


# ============================= Convenience =================================

import re  # noqa: E402 (needed for extract_preferences_from_text)

_default_proactive: Optional[ProactiveEngine] = None
_default_learning: Optional[LearningEngine] = None
_instances_lock = threading.Lock()


def get_proactive_engine(**kwargs: Any) -> ProactiveEngine:
    global _default_proactive
    if _default_proactive is None:
        with _instances_lock:
            if _default_proactive is None:
                _default_proactive = ProactiveEngine(**kwargs)
    return _default_proactive


def get_learning_engine(**kwargs: Any) -> LearningEngine:
    global _default_learning
    if _default_learning is None:
        with _instances_lock:
            if _default_learning is None:
                _default_learning = LearningEngine(**kwargs)
    return _default_learning
