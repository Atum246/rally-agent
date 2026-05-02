"""
🟣 Rally Agent — Workflow Engine
=================================
Records, replays, and automates user workflows.
Detects repeated patterns and suggests automation.
Supports conditional branching, triggers, and a visual workflow format.

Workflows are stored as JSON and can be shared via the marketplace.
"""

import asyncio
import json
import os
import re
import time
import uuid
import logging
import threading
from typing import Optional, Any, Dict, List, Set, Tuple, Callable, Awaitable
from datetime import datetime, timedelta
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger("rally.workflow")


# ═══════════════════════════════════════════════════════════════
# 📐 Constants
# ═══════════════════════════════════════════════════════════════

MAX_WORKFLOWS = 200
MAX_STEP_HISTORY = 1000
PATTERN_MIN_OCCURRENCES = 3  # minimum repeats to suggest automation
SAVE_INTERVAL = 10


# ═══════════════════════════════════════════════════════════════
# 🧩 Enumerations & Data Structures
# ═══════════════════════════════════════════════════════════════

class StepType(str, Enum):
    COMMAND = "command"         # Shell/CLI command
    FILE_OP = "file_op"         # File read/write/edit
    API_CALL = "api_call"       # HTTP request
    LLM_PROMPT = "llm_prompt"   # AI prompt
    CONDITION = "condition"     # If/else branch
    LOOP = "loop"               # Repeat block
    WAIT = "wait"               # Delay
    USER_INPUT = "user_input"   # Wait for user
    TRANSFORM = "transform"     # Data transformation
    CUSTOM = "custom"           # Plugin-defined step


class TriggerType(str, Enum):
    MANUAL = "manual"           # User-initiated
    CRON = "cron"               # Time-based schedule
    FILE_CHANGE = "file_change" # File system event
    WEBHOOK = "webhook"         # HTTP trigger
    EVENT = "event"             # Internal event
    MESSAGE = "message"         # Chat message pattern


class WorkflowStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    ARCHIVED = "archived"


@dataclass
class WorkflowStep:
    """A single step in a workflow."""
    step_id: str = ""
    name: str = ""
    step_type: StepType = StepType.COMMAND
    config: Dict[str, Any] = field(default_factory=dict)
    # For conditions
    condition: Optional[str] = None      # Expression to evaluate
    then_steps: List["WorkflowStep"] = field(default_factory=list)
    else_steps: List["WorkflowStep"] = field(default_factory=list)
    # For loops
    loop_items: Optional[str] = None     # Expression yielding iterable
    loop_body: List["WorkflowStep"] = field(default_factory=list)
    loop_max: int = 100                  # Safety limit
    # Metadata
    timeout_seconds: int = 300
    retry_count: int = 0
    on_failure: str = "stop"             # stop, skip, abort
    description: str = ""
    order: int = 0

    def to_dict(self) -> dict:
        d: Dict[str, Any] = {
            "step_id": self.step_id,
            "name": self.name,
            "step_type": self.step_type.value if isinstance(self.step_type, StepType) else self.step_type,
            "config": self.config,
            "timeout_seconds": self.timeout_seconds,
            "retry_count": self.retry_count,
            "on_failure": self.on_failure,
            "description": self.description,
            "order": self.order,
        }
        if self.condition:
            d["condition"] = self.condition
            d["then_steps"] = [s.to_dict() for s in self.then_steps]
            d["else_steps"] = [s.to_dict() for s in self.else_steps]
        if self.loop_items:
            d["loop_items"] = self.loop_items
            d["loop_body"] = [s.to_dict() for s in self.loop_body]
            d["loop_max"] = self.loop_max
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "WorkflowStep":
        st = d.get("step_type", "command")
        try:
            st = StepType(st)
        except ValueError:
            st = StepType.CUSTOM
        step = cls(
            step_id=d.get("step_id", ""),
            name=d.get("name", ""),
            step_type=st,
            config=d.get("config", {}),
            timeout_seconds=d.get("timeout_seconds", 300),
            retry_count=d.get("retry_count", 0),
            on_failure=d.get("on_failure", "stop"),
            description=d.get("description", ""),
            order=d.get("order", 0),
        )
        if "condition" in d:
            step.condition = d["condition"]
            step.then_steps = [cls.from_dict(s) for s in d.get("then_steps", [])]
            step.else_steps = [cls.from_dict(s) for s in d.get("else_steps", [])]
        if "loop_items" in d:
            step.loop_items = d["loop_items"]
            step.loop_body = [cls.from_dict(s) for s in d.get("loop_body", [])]
            step.loop_max = d.get("loop_max", 100)
        return step


@dataclass
class WorkflowTrigger:
    """Defines when a workflow should auto-execute."""
    trigger_type: TriggerType = TriggerType.MANUAL
    config: Dict[str, Any] = field(default_factory=dict)
    # cron config: {"expression": "0 9 * * 1-5", "timezone": "UTC"}
    # file_change config: {"path": "/path/to/watch", "pattern": "*.py"}
    # webhook config: {"path": "/api/trigger/my-workflow"}
    # event config: {"event_name": "conversation.start"}
    # message config: {"pattern": "deploy.*"}

    def to_dict(self) -> dict:
        return {
            "trigger_type": self.trigger_type.value if isinstance(self.trigger_type, TriggerType) else self.trigger_type,
            "config": self.config,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "WorkflowTrigger":
        tt = d.get("trigger_type", "manual")
        try:
            tt = TriggerType(tt)
        except ValueError:
            tt = TriggerType.MANUAL
        return cls(trigger_type=tt, config=d.get("config", {}))


@dataclass
class WorkflowRun:
    """A single execution of a workflow."""
    run_id: str = ""
    workflow_id: str = ""
    status: str = "running"    # running, completed, failed, cancelled
    started_at: str = ""
    finished_at: Optional[str] = None
    steps_completed: int = 0
    steps_total: int = 0
    step_results: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
    variables: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "workflow_id": self.workflow_id,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "steps_completed": self.steps_completed,
            "steps_total": self.steps_total,
            "step_results": self.step_results[-50:],
            "error": self.error,
            "variables": self.variables,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "WorkflowRun":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class Workflow:
    """A complete workflow definition."""
    workflow_id: str = ""
    name: str = ""
    description: str = ""
    version: str = "1.0.0"
    author: str = "user"
    tags: List[str] = field(default_factory=list)
    steps: List[WorkflowStep] = field(default_factory=list)
    triggers: List[WorkflowTrigger] = field(default_factory=list)
    variables: Dict[str, Any] = field(default_factory=dict)  # Default vars
    status: WorkflowStatus = WorkflowStatus.DRAFT
    created_at: str = ""
    updated_at: str = ""
    run_count: int = 0
    last_run: Optional[str] = None
    avg_duration_seconds: float = 0.0
    # Marketplace
    is_public: bool = False
    downloads: int = 0
    rating: float = 0.0

    def to_dict(self) -> dict:
        return {
            "workflow_id": self.workflow_id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "author": self.author,
            "tags": self.tags,
            "steps": [s.to_dict() for s in self.steps],
            "triggers": [t.to_dict() for t in self.triggers],
            "variables": self.variables,
            "status": self.status.value if isinstance(self.status, WorkflowStatus) else self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "run_count": self.run_count,
            "last_run": self.last_run,
            "avg_duration_seconds": round(self.avg_duration_seconds, 1),
            "is_public": self.is_public,
            "downloads": self.downloads,
            "rating": self.rating,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Workflow":
        ws = d.get("status", "draft")
        try:
            ws = WorkflowStatus(ws)
        except ValueError:
            ws = WorkflowStatus.DRAFT
        return cls(
            workflow_id=d.get("workflow_id", ""),
            name=d.get("name", ""),
            description=d.get("description", ""),
            version=d.get("version", "1.0.0"),
            author=d.get("author", "user"),
            tags=d.get("tags", []),
            steps=[WorkflowStep.from_dict(s) for s in d.get("steps", [])],
            triggers=[WorkflowTrigger.from_dict(t) for t in d.get("triggers", [])],
            variables=d.get("variables", {}),
            status=ws,
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
            run_count=d.get("run_count", 0),
            last_run=d.get("last_run"),
            avg_duration_seconds=d.get("avg_duration_seconds", 0),
            is_public=d.get("is_public", False),
            downloads=d.get("downloads", 0),
            rating=d.get("rating", 0.0),
        )


# ═══════════════════════════════════════════════════════════════
# 📝 Workflow Recorder
# ═══════════════════════════════════════════════════════════════

class WorkflowRecorder:
    """Records user actions as workflow steps.

    Observes user interactions and builds a sequence of steps
    that can be saved as a reusable workflow.
    """

    def __init__(self):
        self._recording: bool = False
        self._current_steps: List[WorkflowStep] = []
        self._session_id: str = ""
        self._start_time: Optional[float] = None

    @property
    def is_recording(self) -> bool:
        return self._recording

    def start_recording(self, session_name: str = "") -> str:
        """Start recording a new workflow."""
        self._recording = True
        self._current_steps = []
        self._session_id = f"rec_{int(time.time()*1000)}"
        self._start_time = time.time()
        logger.info(f"Recording started: {self._session_id}")
        return self._session_id

    def record_step(self, step_type: StepType, name: str, config: Dict[str, Any]) -> WorkflowStep:
        """Record a single step."""
        if not self._recording:
            raise RuntimeError("Not recording. Call start_recording() first.")

        step = WorkflowStep(
            step_id=f"s_{uuid.uuid4().hex[:8]}",
            name=name,
            step_type=step_type,
            config=config,
            order=len(self._current_steps),
        )
        self._current_steps.append(step)
        return step

    def record_command(self, command: str, description: str = "") -> WorkflowStep:
        """Record a shell command."""
        return self.record_step(
            StepType.COMMAND,
            name=description or f"Run: {command[:40]}",
            config={"command": command},
        )

    def record_file_op(self, operation: str, path: str, content: str = "") -> WorkflowStep:
        """Record a file operation."""
        return self.record_step(
            StepType.FILE_OP,
            name=f"{operation}: {os.path.basename(path)}",
            config={"operation": operation, "path": path, "content": content[:1000]},
        )

    def record_prompt(self, prompt: str, model: str = "") -> WorkflowStep:
        """Record an LLM prompt."""
        return self.record_step(
            StepType.LLM_PROMPT,
            name=f"Ask: {prompt[:40]}",
            config={"prompt": prompt, "model": model},
        )

    def stop_recording(self) -> Optional[Workflow]:
        """Stop recording and return the workflow."""
        if not self._recording:
            return None

        self._recording = False
        duration = time.time() - (self._start_time or time.time())

        if not self._current_steps:
            return None

        workflow = Workflow(
            workflow_id=f"wf_{uuid.uuid4().hex[:12]}",
            name=f"Recorded workflow ({datetime.now().strftime('%Y-%m-%d %H:%M')})",
            description=f"Auto-recorded workflow with {len(self._current_steps)} steps, "
                       f"duration: {duration:.0f}s",
            steps=self._current_steps,
            status=WorkflowStatus.DRAFT,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
        )

        logger.info(f"Recording stopped: {len(self._current_steps)} steps captured")
        return workflow


# ═══════════════════════════════════════════════════════════════
# 🔍 Pattern Detector
# ═══════════════════════════════════════════════════════════════

class PatternDetector:
    """Detects repeated action sequences and suggests automation.

    Uses a sliding window approach to find common subsequences
    in the user's action history.
    """

    def __init__(self):
        self.action_history: List[Dict[str, Any]] = []
        self._sequence_buffer: List[str] = []  # normalized action strings
        self.detected_patterns: List[Dict[str, Any]] = []

    def observe(self, action_type: str, action_key: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Record an action for pattern detection."""
        entry = {
            "type": action_type,
            "key": action_key,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {},
        }
        self.action_history.append(entry)
        if len(self.action_history) > MAX_STEP_HISTORY:
            self.action_history = self.action_history[-MAX_STEP_HISTORY:]

        # Normalize for pattern matching
        normalized = f"{action_type}:{action_key}"
        self._sequence_buffer.append(normalized)
        if len(self._sequence_buffer) > 200:
            self._sequence_buffer = self._sequence_buffer[-200:]

    def detect_patterns(self, min_length: int = 2, max_length: int = 8) -> List[Dict[str, Any]]:
        """Detect repeated subsequences in the action history.

        Returns patterns sorted by frequency.
        """
        if len(self._sequence_buffer) < min_length * PATTERN_MIN_OCCURRENCES:
            return []

        pattern_counts: Dict[str, int] = {}
        pattern_examples: Dict[str, List[int]] = defaultdict(list)

        for length in range(min_length, max_length + 1):
            for i in range(len(self._sequence_buffer) - length + 1):
                seq = tuple(self._sequence_buffer[i:i + length])
                key = "|".join(seq)
                pattern_counts[key] = pattern_counts.get(key, 0) + 1
                pattern_examples[key].append(i)

        # Filter to significant patterns
        significant = []
        for key, count in pattern_counts.items():
            if count >= PATTERN_MIN_OCCURRENCES:
                steps = key.split("|")
                significant.append({
                    "steps": steps,
                    "occurrences": count,
                    "length": len(steps),
                    "positions": pattern_examples[key][:5],
                })

        significant.sort(key=lambda x: x["occurrences"] * x["length"], reverse=True)
        self.detected_patterns = significant[:20]
        return self.detected_patterns

    def suggest_automation(self, pattern: Dict[str, Any]) -> Workflow:
        """Convert a detected pattern into a workflow suggestion."""
        steps = []
        for i, action in enumerate(pattern["steps"]):
            parts = action.split(":", 1)
            action_type = parts[0] if parts else "custom"
            action_key = parts[1] if len(parts) > 1 else action

            # Map to step type
            step_type_map = {
                "command": StepType.COMMAND,
                "file": StepType.FILE_OP,
                "prompt": StepType.LLM_PROMPT,
                "api": StepType.API_CALL,
            }
            step_type = step_type_map.get(action_type, StepType.CUSTOM)

            steps.append(WorkflowStep(
                step_id=f"s_{uuid.uuid4().hex[:8]}",
                name=f"Step {i+1}: {action_key[:40]}",
                step_type=step_type,
                config={"action": action_key},
                order=i,
            ))

        return Workflow(
            workflow_id=f"wf_{uuid.uuid4().hex[:12]}",
            name=f"Suggested: {' → '.join(s.name.split(': ')[-1][:15] for s in steps[:3])}",
            description=f"Auto-suggested workflow based on {pattern['occurrences']} repeated patterns",
            steps=steps,
            status=WorkflowStatus.DRAFT,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
        )

    def to_dict(self) -> dict:
        return {
            "action_history": self.action_history[-200:],
            "detected_patterns": self.detected_patterns,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PatternDetector":
        p = cls()
        p.action_history = data.get("action_history", [])
        p.detected_patterns = data.get("detected_patterns", [])
        p._sequence_buffer = [
            f"{a['type']}:{a['key']}" for a in p.action_history
        ]
        return p


# ═══════════════════════════════════════════════════════════════
# 📚 Workflow Templates
# ═══════════════════════════════════════════════════════════════

BUILTIN_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "git_commit_push": {
        "name": "Git: Commit & Push",
        "description": "Stage all changes, commit with message, and push",
        "tags": ["git", "dev"],
        "steps": [
            {"step_type": "command", "name": "Git status", "config": {"command": "git status"}},
            {"step_type": "command", "name": "Stage all", "config": {"command": "git add -A"}},
            {"step_type": "command", "name": "Commit", "config": {"command": "git commit -m '{{message}}'"}},
            {"step_type": "command", "name": "Push", "config": {"command": "git push"}},
        ],
        "variables": {"message": {"type": "string", "description": "Commit message", "required": True}},
    },
    "python_test_lint": {
        "name": "Python: Test & Lint",
        "description": "Run pytest and ruff on the project",
        "tags": ["python", "testing", "dev"],
        "steps": [
            {"step_type": "command", "name": "Run tests", "config": {"command": "python -m pytest -v"}},
            {"step_type": "command", "name": "Lint check", "config": {"command": "ruff check ."}},
            {"step_type": "command", "name": "Format check", "config": {"command": "ruff format --check ."}},
        ],
    },
    "docker_build_deploy": {
        "name": "Docker: Build & Deploy",
        "description": "Build Docker image and push to registry",
        "tags": ["docker", "deploy", "devops"],
        "steps": [
            {"step_type": "command", "name": "Build image", "config": {"command": "docker build -t {{image_name}}:{{tag}} ."}},
            {"step_type": "command", "name": "Tag image", "config": {"command": "docker tag {{image_name}}:{{tag}} {{registry}}/{{image_name}}:{{tag}}"}},
            {"step_type": "command", "name": "Push image", "config": {"command": "docker push {{registry}}/{{image_name}}:{{tag}}"}},
        ],
        "variables": {
            "image_name": {"type": "string", "description": "Docker image name", "required": True},
            "tag": {"type": "string", "description": "Image tag", "default": "latest"},
            "registry": {"type": "string", "description": "Container registry", "required": True},
        },
    },
    "daily_report": {
        "name": "Daily Report",
        "description": "Generate a summary of today's work",
        "tags": ["productivity", "report"],
        "steps": [
            {"step_type": "llm_prompt", "name": "Summarize", "config": {
                "prompt": "Summarize today's conversations and actions into a daily report. "
                         "Include: tasks completed, issues encountered, plans for tomorrow.",
            }},
            {"step_type": "file_op", "name": "Save report", "config": {
                "operation": "write",
                "path": "~/reports/{{date}}.md",
            }},
        ],
    },
    "research_topic": {
        "name": "Research Topic",
        "description": "Deep-dive research on a topic",
        "tags": ["research", "learning"],
        "steps": [
            {"step_type": "llm_prompt", "name": "Overview", "config": {
                "prompt": "Give me a comprehensive overview of {{topic}}. Include key concepts, "
                         "current state, major players, and recent developments.",
            }},
            {"step_type": "llm_prompt", "name": "Deep dive", "config": {
                "prompt": "Now go deeper into the most important aspects. Provide technical details, "
                         "comparisons, and practical applications.",
            }},
            {"step_type": "file_op", "name": "Save notes", "config": {
                "operation": "write",
                "path": "~/research/{{topic}}.md",
            }},
        ],
        "variables": {
            "topic": {"type": "string", "description": "Topic to research", "required": True},
        },
    },
    "code_review": {
        "name": "Code Review",
        "description": "Review code changes with AI assistance",
        "tags": ["code", "review", "dev"],
        "steps": [
            {"step_type": "command", "name": "Get diff", "config": {"command": "git diff {{branch}}"}},
            {"step_type": "llm_prompt", "name": "Review", "config": {
                "prompt": "Review this code diff. Focus on: bugs, security issues, "
                         "performance, code style, and best practices.\n\n{{diff}}",
            }},
        ],
        "variables": {
            "branch": {"type": "string", "description": "Branch to compare against", "default": "main"},
        },
    },
}


# ═══════════════════════════════════════════════════════════════
# ⚡ Workflow Engine
# ═══════════════════════════════════════════════════════════════

class WorkflowEngine:
    """Manages workflows: create, run, schedule, and share.

    This is the main entry point for workflow operations.
    """

    def __init__(self, data_dir: Optional[str] = None):
        self.data_dir = os.path.expanduser(data_dir or "~/.rally-agent/data")
        self.workflows_file = os.path.join(self.data_dir, "workflows.json")
        self.runs_file = os.path.join(self.data_dir, "workflow_runs.json")
        os.makedirs(self.data_dir, exist_ok=True)

        # Storage
        self.workflows: Dict[str, Workflow] = {}
        self.runs: List[WorkflowRun] = []

        # Subsystems
        self.recorder = WorkflowRecorder()
        self.pattern_detector = PatternDetector()

        # Step executors (registered by plugins or integrations)
        self._step_executors: Dict[StepType, Callable] = {}

        # Auto-save
        self._dirty_count: int = 0
        self._save_lock = threading.Lock()

        # Load templates and saved data
        self._load_templates()
        self._load()

    # ───────────────────────────────────────────────────────
    # Persistence
    # ───────────────────────────────────────────────────────

    def _load_templates(self) -> None:
        """Load built-in workflow templates."""
        now = datetime.now().isoformat()
        for tid, tdata in BUILTIN_TEMPLATES.items():
            if tid not in self.workflows:
                steps = [WorkflowStep(
                    step_id=f"s_{uuid.uuid4().hex[:8]}",
                    name=s.get("name", ""),
                    step_type=StepType(s.get("step_type", "custom")),
                    config=s.get("config", {}),
                    order=i,
                ) for i, s in enumerate(tdata.get("steps", []))]

                self.workflows[tid] = Workflow(
                    workflow_id=tid,
                    name=tdata["name"],
                    description=tdata.get("description", ""),
                    tags=tdata.get("tags", []),
                    steps=steps,
                    variables=tdata.get("variables", {}),
                    status=WorkflowStatus.ACTIVE,
                    created_at=now,
                    updated_at=now,
                )

    def _load(self) -> None:
        """Load workflows from disk."""
        # Load workflows
        if os.path.exists(self.workflows_file):
            try:
                with open(self.workflows_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for wdata in data.get("workflows", []):
                    wf = Workflow.from_dict(wdata)
                    if wf.workflow_id not in self.workflows:
                        self.workflows[wf.workflow_id] = wf
                # Load pattern detector
                if "pattern_detector" in data:
                    self.pattern_detector = PatternDetector.from_dict(data["pattern_detector"])
                logger.info(f"Loaded {len(self.workflows)} workflows")
            except Exception as e:
                logger.error(f"Failed to load workflows: {e}")

        # Load runs
        if os.path.exists(self.runs_file):
            try:
                with open(self.runs_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.runs = [WorkflowRun.from_dict(r) for r in data.get("runs", [])]
            except Exception as e:
                logger.error(f"Failed to load workflow runs: {e}")

    def save(self) -> None:
        """Persist workflows to disk."""
        with self._save_lock:
            # Save workflows
            wf_data = {
                "workflows": [w.to_dict() for w in self.workflows.values()],
                "pattern_detector": self.pattern_detector.to_dict(),
                "schema_version": 1,
                "saved_at": datetime.now().isoformat(),
            }
            tmp = self.workflows_file + ".tmp"
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(wf_data, f, indent=2, ensure_ascii=False)
                os.replace(tmp, self.workflows_file)
            except Exception as e:
                logger.error(f"Failed to save workflows: {e}")
                try:
                    os.unlink(tmp)
                except OSError:
                    pass

            # Save runs (keep last 500)
            run_data = {
                "runs": [r.to_dict() for r in self.runs[-500:]],
                "schema_version": 1,
            }
            tmp = self.runs_file + ".tmp"
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(run_data, f, indent=2, ensure_ascii=False)
                os.replace(tmp, self.runs_file)
            except Exception as e:
                logger.error(f"Failed to save workflow runs: {e}")
                try:
                    os.unlink(tmp)
                except OSError:
                    pass

            self._dirty_count = 0

    def _auto_save(self) -> None:
        self._dirty_count += 1
        if self._dirty_count >= SAVE_INTERVAL:
            self.save()

    # ───────────────────────────────────────────────────────
    # Workflow CRUD
    # ───────────────────────────────────────────────────────

    def create_workflow(
        self,
        name: str,
        description: str = "",
        steps: Optional[List[WorkflowStep]] = None,
        tags: Optional[List[str]] = None,
        variables: Optional[Dict[str, Any]] = None,
    ) -> Workflow:
        """Create a new workflow."""
        now = datetime.now().isoformat()
        wf = Workflow(
            workflow_id=f"wf_{uuid.uuid4().hex[:12]}",
            name=name,
            description=description,
            steps=steps or [],
            tags=tags or [],
            variables=variables or {},
            status=WorkflowStatus.DRAFT,
            created_at=now,
            updated_at=now,
        )
        self.workflows[wf.workflow_id] = wf
        self._auto_save()
        return wf

    def get_workflow(self, workflow_id: str) -> Optional[Workflow]:
        return self.workflows.get(workflow_id)

    def update_workflow(self, workflow_id: str, **kwargs) -> bool:
        wf = self.workflows.get(workflow_id)
        if not wf:
            return False
        for key, value in kwargs.items():
            if hasattr(wf, key):
                setattr(wf, key, value)
        wf.updated_at = datetime.now().isoformat()
        self._auto_save()
        return True

    def delete_workflow(self, workflow_id: str) -> bool:
        if workflow_id in self.workflows:
            del self.workflows[workflow_id]
            self._auto_save()
            return True
        return False

    def list_workflows(
        self,
        status: Optional[WorkflowStatus] = None,
        tag: Optional[str] = None,
        limit: int = 50,
    ) -> List[Workflow]:
        """List workflows with optional filters."""
        results = list(self.workflows.values())
        if status:
            results = [w for w in results if w.status == status]
        if tag:
            results = [w for w in results if tag in w.tags]
        results.sort(key=lambda w: w.updated_at, reverse=True)
        return results[:limit]

    # ───────────────────────────────────────────────────────
    # Step Management
    # ───────────────────────────────────────────────────────

    def add_step(
        self,
        workflow_id: str,
        step_type: StepType,
        name: str,
        config: Dict[str, Any],
        after_step: Optional[str] = None,
    ) -> Optional[WorkflowStep]:
        """Add a step to a workflow."""
        wf = self.workflows.get(workflow_id)
        if not wf:
            return None

        step = WorkflowStep(
            step_id=f"s_{uuid.uuid4().hex[:8]}",
            name=name,
            step_type=step_type,
            config=config,
        )

        if after_step:
            # Insert after the specified step
            for i, s in enumerate(wf.steps):
                if s.step_id == after_step:
                    step.order = i + 1
                    wf.steps.insert(i + 1, step)
                    # Re-order remaining steps
                    for j in range(i + 2, len(wf.steps)):
                        wf.steps[j].order = j
                    break
            else:
                wf.steps.append(step)
                step.order = len(wf.steps) - 1
        else:
            step.order = len(wf.steps)
            wf.steps.append(step)

        wf.updated_at = datetime.now().isoformat()
        self._auto_save()
        return step

    def remove_step(self, workflow_id: str, step_id: str) -> bool:
        wf = self.workflows.get(workflow_id)
        if not wf:
            return False
        wf.steps = [s for s in wf.steps if s.step_id != step_id]
        for i, s in enumerate(wf.steps):
            s.order = i
        wf.updated_at = datetime.now().isoformat()
        self._auto_save()
        return True

    # ───────────────────────────────────────────────────────
    # Workflow Execution
    # ───────────────────────────────────────────────────────

    async def execute_workflow(
        self,
        workflow_id: str,
        variables: Optional[Dict[str, Any]] = None,
    ) -> WorkflowRun:
        """Execute a workflow. Returns a WorkflowRun with results."""
        wf = self.workflows.get(workflow_id)
        if not wf:
            raise ValueError(f"Workflow not found: {workflow_id}")

        now = datetime.now().isoformat()
        run = WorkflowRun(
            run_id=f"run_{uuid.uuid4().hex[:12]}",
            workflow_id=workflow_id,
            status="running",
            started_at=now,
            steps_total=len(wf.steps),
            variables={**wf.variables, **(variables or {})},
        )

        start_time = time.time()

        try:
            for i, step in enumerate(wf.steps):
                step_result = await self._execute_step(step, run.variables)
                run.step_results.append(step_result)
                run.steps_completed = i + 1

                if step_result.get("status") == "failed":
                    if step.on_failure == "stop":
                        run.status = "failed"
                        run.error = step_result.get("error", "Step failed")
                        break
                    elif step.on_failure == "skip":
                        continue
                    elif step.on_failure == "abort":
                        run.status = "failed"
                        run.error = f"Aborted at step: {step.name}"
                        break

                # Store output in variables for next steps
                if "output" in step_result:
                    run.variables[f"step_{i}_output"] = step_result["output"]

            if run.status == "running":
                run.status = "completed"

        except Exception as e:
            run.status = "failed"
            run.error = str(e)
            logger.error(f"Workflow execution failed: {e}")

        run.finished_at = datetime.now().isoformat()
        duration = time.time() - start_time

        # Update workflow stats
        wf.run_count += 1
        wf.last_run = now
        wf.avg_duration_seconds = (
            (wf.avg_duration_seconds * (wf.run_count - 1) + duration) / wf.run_count
        )

        self.runs.append(run)
        self._auto_save()

        return run

    async def _execute_step(
        self, step: WorkflowStep, variables: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a single workflow step."""
        # Resolve template variables in config
        resolved_config = self._resolve_variables(step.config, variables)

        result: Dict[str, Any] = {
            "step_id": step.step_id,
            "name": step.name,
            "status": "completed",
            "started_at": datetime.now().isoformat(),
        }

        try:
            # Check for registered executor
            executor = self._step_executors.get(step.step_type)
            if executor:
                if asyncio.iscoroutinefunction(executor):
                    output = await executor(step, resolved_config, variables)
                else:
                    output = executor(step, resolved_config, variables)
                result["output"] = output
            else:
                # Default handling — store for later execution
                result["output"] = {
                    "type": step.step_type.value if isinstance(step.step_type, StepType) else str(step.step_type),
                    "config": resolved_config,
                    "deferred": True,
                }

        except Exception as e:
            result["status"] = "failed"
            result["error"] = str(e)

        result["finished_at"] = datetime.now().isoformat()
        return result

    @staticmethod
    def _resolve_variables(
        config: Dict[str, Any], variables: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Resolve {{variable}} placeholders in config values."""
        resolved = {}
        for key, value in config.items():
            if isinstance(value, str):
                # Replace {{var}} patterns
                for var_name, var_value in variables.items():
                    value = value.replace(f"{{{{{var_name}}}}}", str(var_value))
                resolved[key] = value
            elif isinstance(value, dict):
                resolved[key] = WorkflowEngine._resolve_variables(value, variables)
            elif isinstance(value, list):
                resolved[key] = [
                    WorkflowEngine._resolve_variables(v, variables) if isinstance(v, dict)
                    else str(v).replace(f"{{{{{vn}}}}}", str(vv))
                    if isinstance(v, str) else v
                    for v in value
                    for vn, vv in variables.items()
                ] if value else value
            else:
                resolved[key] = value
        return resolved

    def register_executor(
        self,
        step_type: StepType,
        executor: Callable,
    ) -> None:
        """Register a step executor function.

        The executor receives (step, resolved_config, variables) and
        should return a result dict or value.
        """
        self._step_executors[step_type] = executor
        logger.info(f"Registered executor for step type: {step_type.value}")

    # ───────────────────────────────────────────────────────
    # Pattern Detection & Suggestions
    # ───────────────────────────────────────────────────────

    def observe_action(self, action_type: str, action_key: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Record an action for pattern detection."""
        self.pattern_detector.observe(action_type, action_key, metadata)

    def get_suggestions(self) -> List[Workflow]:
        """Get workflow suggestions based on detected patterns."""
        patterns = self.pattern_detector.detect_patterns()
        suggestions = []
        for p in patterns:
            wf = self.pattern_detector.suggest_automation(p)
            suggestions.append(wf)
        return suggestions

    # ───────────────────────────────────────────────────────
    # Workflow Replay with Variations
    # ───────────────────────────────────────────────────────

    def clone_workflow(
        self,
        workflow_id: str,
        new_name: Optional[str] = None,
        variable_overrides: Optional[Dict[str, Any]] = None,
    ) -> Optional[Workflow]:
        """Clone a workflow with optional modifications."""
        original = self.workflows.get(workflow_id)
        if not original:
            return None

        clone_data = original.to_dict()
        clone_data["workflow_id"] = f"wf_{uuid.uuid4().hex[:12]}"
        clone_data["name"] = new_name or f"{original.name} (copy)"
        clone_data["created_at"] = datetime.now().isoformat()
        clone_data["updated_at"] = datetime.now().isoformat()
        clone_data["run_count"] = 0
        clone_data["last_run"] = None

        if variable_overrides:
            clone_data["variables"].update(variable_overrides)

        clone = Workflow.from_dict(clone_data)

        # Generate new step IDs
        for step in clone.steps:
            step.step_id = f"s_{uuid.uuid4().hex[:8]}"

        self.workflows[clone.workflow_id] = clone
        self._auto_save()
        return clone

    # ───────────────────────────────────────────────────────
    # Triggers
    # ───────────────────────────────────────────────────────

    def add_trigger(
        self,
        workflow_id: str,
        trigger_type: TriggerType,
        config: Dict[str, Any],
    ) -> bool:
        """Add a trigger to a workflow."""
        wf = self.workflows.get(workflow_id)
        if not wf:
            return False

        trigger = WorkflowTrigger(trigger_type=trigger_type, config=config)
        wf.triggers.append(trigger)
        wf.updated_at = datetime.now().isoformat()
        self._auto_save()
        return True

    def remove_trigger(self, workflow_id: str, trigger_index: int) -> bool:
        wf = self.workflows.get(workflow_id)
        if not wf or trigger_index >= len(wf.triggers):
            return False
        wf.triggers.pop(trigger_index)
        wf.updated_at = datetime.now().isoformat()
        self._auto_save()
        return True

    def get_triggered_workflows(self, trigger_type: TriggerType) -> List[Workflow]:
        """Find all workflows with a specific trigger type."""
        return [
            wf for wf in self.workflows.values()
            if any(t.trigger_type == trigger_type for t in wf.triggers)
        ]

    # ───────────────────────────────────────────────────────
    # Marketplace
    # ───────────────────────────────────────────────────────

    def export_workflow(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """Export a workflow for sharing."""
        wf = self.workflows.get(workflow_id)
        if not wf:
            return None
        data = wf.to_dict()
        data["exported_at"] = datetime.now().isoformat()
        data["export_version"] = "1.0"
        return data

    def import_workflow(self, data: Dict[str, Any]) -> Optional[Workflow]:
        """Import a shared workflow."""
        try:
            wf = Workflow.from_dict(data)
            wf.workflow_id = f"wf_{uuid.uuid4().hex[:12]}"  # New ID to avoid conflicts
            wf.created_at = datetime.now().isoformat()
            wf.updated_at = datetime.now().isoformat()
            wf.run_count = 0
            wf.last_run = None
            self.workflows[wf.workflow_id] = wf
            self._auto_save()
            return wf
        except Exception as e:
            logger.error(f"Failed to import workflow: {e}")
            return None

    def publish_workflow(self, workflow_id: str) -> bool:
        """Mark a workflow as public for marketplace sharing."""
        wf = self.workflows.get(workflow_id)
        if not wf:
            return False
        wf.is_public = True
        wf.updated_at = datetime.now().isoformat()
        self._auto_save()
        return True

    def get_public_workflows(self) -> List[Workflow]:
        """Get all public workflows for marketplace."""
        return [wf for wf in self.workflows.values() if wf.is_public]

    # ───────────────────────────────────────────────────────
    # Visual Workflow Data (for web UI)
    # ───────────────────────────────────────────────────────

    def get_visual_workflow(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """Generate visual workflow data for the web UI editor."""
        wf = self.workflows.get(workflow_id)
        if not wf:
            return None

        nodes = []
        edges = []

        for i, step in enumerate(wf.steps):
            node = {
                "id": step.step_id,
                "type": self._step_to_node_type(step.step_type),
                "position": {"x": 250, "y": i * 120},
                "data": {
                    "label": step.name,
                    "step_type": step.step_type.value if isinstance(step.step_type, StepType) else str(step.step_type),
                    "config": step.config,
                    "description": step.description,
                },
            }
            nodes.append(node)

            # Edge from previous step
            if i > 0:
                edges.append({
                    "id": f"e_{wf.steps[i-1].step_id}_{step.step_id}",
                    "source": wf.steps[i-1].step_id,
                    "target": step.step_id,
                    "type": "smoothstep",
                })

            # Handle conditional branches
            if step.condition:
                for j, then_step in enumerate(step.then_steps):
                    nodes.append({
                        "id": then_step.step_id,
                        "type": self._step_to_node_type(then_step.step_type),
                        "position": {"x": 450, "y": i * 120 + j * 80},
                        "data": {
                            "label": f"[then] {then_step.name}",
                            "step_type": then_step.step_type.value if isinstance(then_step.step_type, StepType) else str(then_step.step_type),
                            "config": then_step.config,
                        },
                    })
                    if j == 0:
                        edges.append({
                            "id": f"e_{step.step_id}_{then_step.step_id}",
                            "source": step.step_id,
                            "target": then_step.step_id,
                            "type": "smoothstep",
                            "label": "yes",
                            "style": {"stroke": "#22c55e"},
                        })
                    elif j > 0:
                        edges.append({
                            "id": f"e_{step.then_steps[j-1].step_id}_{then_step.step_id}",
                            "source": step.then_steps[j-1].step_id,
                            "target": then_step.step_id,
                            "type": "smoothstep",
                        })

                for j, else_step in enumerate(step.else_steps):
                    nodes.append({
                        "id": else_step.step_id,
                        "type": self._step_to_node_type(else_step.step_type),
                        "position": {"x": 50, "y": i * 120 + j * 80},
                        "data": {
                            "label": f"[else] {else_step.name}",
                            "step_type": else_step.step_type.value if isinstance(else_step.step_type, StepType) else str(else_step.step_type),
                            "config": else_step.config,
                        },
                    })
                    if j == 0:
                        edges.append({
                            "id": f"e_{step.step_id}_{else_step.step_id}",
                            "source": step.step_id,
                            "target": else_step.step_id,
                            "type": "smoothstep",
                            "label": "no",
                            "style": {"stroke": "#ef4444"},
                        })
                    elif j > 0:
                        edges.append({
                            "id": f"e_{step.else_steps[j-1].step_id}_{else_step.step_id}",
                            "source": step.else_steps[j-1].step_id,
                            "target": else_step.step_id,
                            "type": "smoothstep",
                        })

        return {
            "workflow": wf.to_dict(),
            "nodes": nodes,
            "edges": edges,
            "metadata": {
                "total_steps": len(wf.steps),
                "has_conditions": any(s.condition for s in wf.steps),
                "has_loops": any(s.loop_items for s in wf.steps),
            },
        }

    @staticmethod
    def _step_to_node_type(step_type: StepType) -> str:
        """Map step type to visual node type."""
        mapping = {
            StepType.COMMAND: "command",
            StepType.FILE_OP: "file",
            StepType.API_CALL: "api",
            StepType.LLM_PROMPT: "ai",
            StepType.CONDITION: "decision",
            StepType.LOOP: "loop",
            StepType.WAIT: "timer",
            StepType.USER_INPUT: "input",
            StepType.TRANSFORM: "transform",
            StepType.CUSTOM: "custom",
        }
        return mapping.get(step_type, "default")

    # ───────────────────────────────────────────────────────
    # Statistics
    # ───────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Get workflow engine statistics."""
        total_runs = len(self.runs)
        successful = sum(1 for r in self.runs if r.status == "completed")
        failed = sum(1 for r in self.runs if r.status == "failed")

        return {
            "total_workflows": len(self.workflows),
            "active_workflows": sum(1 for w in self.workflows.values() if w.status == WorkflowStatus.ACTIVE),
            "total_runs": total_runs,
            "successful_runs": successful,
            "failed_runs": failed,
            "success_rate": round(successful / max(total_runs, 1), 3),
            "patterns_detected": len(self.pattern_detector.detected_patterns),
            "templates_available": len(BUILTIN_TEMPLATES),
            "most_used": self._most_used_workflows(5),
        }

    def _most_used_workflows(self, n: int = 5) -> List[Dict[str, Any]]:
        sorted_wf = sorted(
            self.workflows.values(),
            key=lambda w: w.run_count,
            reverse=True,
        )[:n]
        return [
            {"name": w.name, "runs": w.run_count, "avg_duration": round(w.avg_duration_seconds, 1)}
            for w in sorted_wf if w.run_count > 0
        ]

    def get_run_history(self, workflow_id: Optional[str] = None, limit: int = 20) -> List[WorkflowRun]:
        """Get workflow run history."""
        runs = self.runs
        if workflow_id:
            runs = [r for r in runs if r.workflow_id == workflow_id]
        return sorted(runs, key=lambda r: r.started_at, reverse=True)[:limit]

    # ───────────────────────────────────────────────────────
    # Lifecycle
    # ───────────────────────────────────────────────────────

    def shutdown(self) -> None:
        """Clean shutdown."""
        self.save()
        logger.info("WorkflowEngine: shutdown complete")
