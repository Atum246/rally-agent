"""
🟣 Rally Agent — Cron & Automation System
==========================================
Production-grade scheduler with cron parsing, persistent job store,
concurrent execution, dependency tracking, retries, and full job lifecycle.

Job Types:
  - systemEvent: inject text into main session
  - agentTurn: run agent with message (isolated session)
  - shellCommand: run shell command on schedule
  - webhook: HTTP POST to URL on schedule
  - fileWatch: trigger when file changes
  - emailCheck: check email on schedule
  - newsGather: gather news on schedule
  - healthCheck: check system health on schedule
  - memoryConsolidate: consolidate memory periodically
  - patternAnalysis: analyze user patterns periodically
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import subprocess
import threading
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import (
    Any, Awaitable, Callable, Dict, List, Optional, Set, Tuple, Union,
)

logger = logging.getLogger("rally.automation")


# ═══════════════════════════════════════════════════════════════
# ⏱️ Cron Expression Parser
# ═══════════════════════════════════════════════════════════════

# Human-friendly aliases → cron
_ALIASES: Dict[str, str] = {
    "@yearly":   "0 0 1 1 *",
    "@annually": "0 0 1 1 *",
    "@monthly":  "0 0 1 * *",
    "@weekly":   "0 0 * * 0",
    "@daily":    "0 0 * * *",
    "@midnight": "0 0 * * *",
    "@hourly":   "0 * * * *",
    "@every_minute": "* * * * *",
}

# @every N<unit>  →  cron equivalent
_EVERY_RE = re.compile(
    r"^@every\s+(\d+)\s*(s|sec|second|seconds|m|min|minute|minutes|h|hr|hour|hours|d|day|days|w|week|weeks)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CronField:
    """Parsed representation of a single cron field."""
    raw: str
    values: frozenset  # set[int] of allowed values


@dataclass(frozen=True)
class CronExpression:
    """Fully parsed 5-field cron expression.

    Fields: minute  hour  day-of-month  month  day-of-week
    """
    minute: CronField
    hour: CronField
    day_of_month: CronField
    month: CronField
    day_of_week: CronField
    original: str

    # ── Matching ─────────────────────────────────────────────

    def matches(self, dt: datetime) -> bool:
        """Return True if *dt* matches every field."""
        # Python weekday: Mon=0 … Sun=6; cron dow: Sun=0 or 7, Mon=1 … Sat=6
        py_dow = (dt.weekday() + 1) % 7  # Sun=0, Mon=1, … Sat=6
        return (
            dt.minute in self.minute.values
            and dt.hour in self.hour.values
            and dt.day in self.day_of_month.values
            and dt.month in self.month.values
            and py_dow in self.day_of_week.values
        )

    def next_n(self, after: datetime, n: int = 1) -> List[datetime]:
        """Return the next *n* trigger times strictly after *after*."""
        results: List[datetime] = []
        # Start at the next whole minute
        cursor = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
        # Safety: don't scan more than 2 years of minutes
        max_iterations = 366 * 24 * 60
        for _ in range(max_iterations):
            if self.matches(cursor):
                results.append(cursor)
                if len(results) >= n:
                    break
            cursor += timedelta(minutes=1)
        return results

    def next(self, after: datetime) -> Optional[datetime]:
        """Return the next trigger time strictly after *after*."""
        hits = self.next_n(after, 1)
        return hits[0] if hits else None


# ── Parsing helpers ───────────────────────────────────────────

_RANGE_RE = re.compile(r"^(\d+)-(\d+)(?:/(\d+))?$")
_STEP_RE  = re.compile(r"^\*/(\d+)$")


def _parse_field(raw: str, lo: int, hi: int) -> CronField:
    """Parse a single cron field into a CronField."""
    values: Set[int] = set()

    for part in raw.split(","):
        part = part.strip()

        # Bare wildcard: *
        if part == "*":
            values.update(range(lo, hi + 1))
            continue

        # Step wildcard: */N
        m = _STEP_RE.match(part)
        if m:
            step_str = m.group(1)
            step = max(1, int(step_str)) if step_str else 1
            values.update(range(lo, hi + 1, step))
            continue

        # Range with optional step: A-B/N
        m = _RANGE_RE.match(part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            step = max(1, int(m.group(3))) if m.group(3) else 1
            values.update(range(a, b + 1, step))
            continue

        # Plain integer
        if part.isdigit():
            v = int(part)
            if lo <= v <= hi:
                values.add(v)
            continue

        raise ValueError(f"Invalid cron field segment: {part!r}")

    if not values:
        raise ValueError(f"Empty cron field: {raw!r}")

    return CronField(raw=raw, values=frozenset(values))


_WEEKDAY_MAP = {
    "sun": 0, "mon": 1, "tue": 2, "wed": 3,
    "thu": 4, "fri": 5, "sat": 6,
}


def _parse_dow_field(raw: str) -> CronField:
    """Parse day-of-week field, supporting names (sun, mon, …)."""
    normalised = raw.lower()
    for name, val in _WEEKDAY_MAP.items():
        normalised = normalised.replace(name, str(val))
    return _parse_field(normalised, 0, 7)


def parse_cron(expression: str) -> CronExpression:
    """Parse a cron expression or @alias into a CronExpression.

    Supports:
      - Standard 5-field cron:  "*/5 * * * *"
      - @aliases:               "@daily", "@hourly", "@weekly", …
      - @every intervals:       "@every 5m", "@every 2h", "@every 1d"
    """
    expr = expression.strip()

    # Resolve @every N<unit>
    m = _EVERY_RE.match(expr)
    if m:
        n = int(m.group(1))
        unit = m.group(2).lower()
        unit_seconds = {
            "s": 1, "sec": 1, "second": 1, "seconds": 1,
            "m": 60, "min": 60, "minute": 60, "minutes": 60,
            "h": 3600, "hr": 3600, "hour": 3600, "hours": 3600,
            "d": 86400, "day": 86400, "days": 86400,
            "w": 604800, "week": 604800, "weeks": 604800,
        }[unit]
        total = n * unit_seconds
        # Convert to cron fields
        if total < 60:
            # Sub-minute → run every minute (finest cron granularity)
            return parse_cron("* * * * *")
        if total % 3600 == 0:
            hours = total // 3600
            if hours >= 24 and hours % 24 == 0:
                days = hours // 24
                if days == 1:
                    return parse_cron("0 0 * * *")  # @daily equivalent
                return parse_cron(f"0 0 */{days} * *")
            return parse_cron(f"0 */{hours} * * *")
        if total % 60 == 0:
            minutes = total // 60
            if minutes >= 60:
                h, m = divmod(minutes, 60)
                return parse_cron(f"{m} */{h} * * *")
            return parse_cron(f"*/{minutes} * * * *")
        # Fallback: every minute
        return parse_cron("* * * * *")

    # Resolve @aliases
    if expr.lower() in _ALIASES:
        expr = _ALIASES[expr.lower()]

    fields = expr.split()
    if len(fields) != 5:
        raise ValueError(
            f"Cron expression must have 5 fields (got {len(fields)}): {expr!r}"
        )

    return CronExpression(
        minute=_parse_field(fields[0], 0, 59),
        hour=_parse_field(fields[1], 0, 23),
        day_of_month=_parse_field(fields[2], 1, 31),
        month=_parse_field(fields[3], 1, 12),
        day_of_week=_parse_dow_field(fields[4]),
        original=expression.strip(),
    )


# ═══════════════════════════════════════════════════════════════
# 📋 Job Data Model
# ═══════════════════════════════════════════════════════════════

class JobType(str, Enum):
    SYSTEM_EVENT        = "systemEvent"
    AGENT_TURN          = "agentTurn"
    SHELL_COMMAND       = "shellCommand"
    WEBHOOK             = "webhook"
    FILE_WATCH          = "fileWatch"
    EMAIL_CHECK         = "emailCheck"
    NEWS_GATHER         = "newsGather"
    HEALTH_CHECK        = "healthCheck"
    MEMORY_CONSOLIDATE  = "memoryConsolidate"
    PATTERN_ANALYSIS    = "patternAnalysis"


class JobStatus(str, Enum):
    ACTIVE    = "active"
    PAUSED    = "paused"
    DISABLED  = "disabled"
    RUNNING   = "running"
    FAILED    = "failed"
    COMPLETED = "completed"


@dataclass
class JobRunRecord:
    """Single execution record for a job."""
    run_id: str
    started_at: float          # epoch
    finished_at: Optional[float] = None
    status: str = "running"    # "running" | "success" | "failed" | "timeout"
    output: str = ""
    error: Optional[str] = None
    attempt: int = 1


@dataclass
class Job:
    """Persistent scheduled job definition."""
    job_id: str
    name: str
    job_type: JobType
    schedule: str               # cron expression or @alias
    payload: Dict[str, Any]     # type-specific parameters
    enabled: bool = True
    status: JobStatus = JobStatus.ACTIVE

    # ── Execution config ─────────────────────────────────────
    timeout: float = 300.0      # seconds
    max_retries: int = 0
    retry_delay: float = 30.0   # seconds between retries
    max_concurrent: int = 1     # max parallel runs of this job

    # ── Dependencies ─────────────────────────────────────────
    depends_on: List[str] = field(default_factory=list)  # job_ids that must succeed first

    # ── Tracking ─────────────────────────────────────────────
    created_at: float = field(default_factory=time.time)
    last_run: Optional[float] = None
    next_run: Optional[float] = None
    run_count: int = 0
    success_count: int = 0
    fail_count: int = 0
    history: List[JobRunRecord] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["job_type"] = self.job_type.value
        d["status"] = self.status.value
        d["history"] = [asdict(h) for h in self.history[-50:]]  # keep last 50
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Job":
        data = dict(data)  # copy
        data["job_type"] = JobType(data["job_type"])
        data["status"] = JobStatus(data["status"])
        history_raw = data.pop("history", [])
        job = cls(**{k: v for k, v in data.items() if k != "history"})
        job.history = [JobRunRecord(**h) for h in history_raw]
        return job


# ═══════════════════════════════════════════════════════════════
# 🔧 Built-in Job Handlers
# ═══════════════════════════════════════════════════════════════

# Type alias for handler functions
JobHandler = Callable[[Job], Awaitable[str]]


async def _handle_system_event(job: Job) -> str:
    """Inject text into the main session."""
    message = job.payload.get("message", "")
    channel = job.payload.get("channel", "main")
    logger.info("[systemEvent] Injecting into %s: %s", channel, message[:100])
    return f"Injected event into {channel}: {message[:100]}"


async def _handle_agent_turn(job: Job) -> str:
    """Run an agent with a message in an isolated session."""
    message = job.payload.get("message", "")
    agent_type = job.payload.get("agent_type", "orchestrator")
    logger.info("[agentTurn] Running %s agent: %s", agent_type, message[:100])
    return f"Agent turn ({agent_type}): {message[:100]}"


async def _handle_shell_command(job: Job) -> str:
    """Run a shell command with timeout."""
    command = job.payload.get("command", "echo 'no command'")
    cwd = job.payload.get("cwd", None)
    env = job.payload.get("env", None)

    proc = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
        env={**os.environ, **env} if env else None,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=job.timeout
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise TimeoutError(f"Command timed out after {job.timeout}s")

    out = stdout.decode(errors="replace").strip()
    err = stderr.decode(errors="replace").strip()

    if proc.returncode != 0:
        raise RuntimeError(f"Exit {proc.returncode}: {err or out}")

    return out or "(no output)"


async def _handle_webhook(job: Job) -> str:
    """HTTP POST to a URL."""
    import aiohttp  # optional dependency

    url = job.payload.get("url", "")
    if not url:
        raise ValueError("webhook job requires payload.url")

    headers = job.payload.get("headers", {})
    body = job.payload.get("body", {})
    method = job.payload.get("method", "POST").upper()

    timeout_obj = aiohttp.ClientTimeout(total=job.timeout)
    async with aiohttp.ClientSession(timeout=timeout_obj) as session:
        async with session.request(method, url, headers=headers, json=body) as resp:
            text = await resp.text()
            if resp.status >= 400:
                raise RuntimeError(f"HTTP {resp.status}: {text[:200]}")
            return f"HTTP {resp.status}: {text[:200]}"


async def _handle_file_watch(job: Job) -> str:
    """Check if a file has changed since last run."""
    path = Path(job.payload.get("path", "")).expanduser()
    if not path.exists():
        return f"File not found: {path}"

    mtime = path.stat().st_mtime
    last_known = job.payload.get("_last_mtime", 0)
    job.payload["_last_mtime"] = mtime

    if mtime > last_known:
        return f"File changed: {path} (mtime={mtime})"
    return f"No change: {path}"


async def _handle_email_check(job: Job) -> str:
    """Placeholder: check email."""
    logger.info("[emailCheck] Checking email…")
    return "Email check completed (stub)"


async def _handle_news_gather(job: Job) -> str:
    """Placeholder: gather news."""
    topics = job.payload.get("topics", ["technology"])
    logger.info("[newsGather] Gathering news on: %s", topics)
    return f"News gathered for: {', '.join(topics)} (stub)"


async def _handle_health_check(job: Job) -> str:
    """Run basic system health checks."""
    import shutil

    checks: List[str] = []

    # Disk usage
    usage = shutil.disk_usage("/")
    pct = (usage.used / usage.total) * 100
    checks.append(f"disk: {pct:.1f}% used ({usage.free // (1024**3)} GB free)")
    if pct > 95:
        raise RuntimeError(f"Disk critically full: {pct:.1f}%")

    # Memory (Linux)
    meminfo = Path("/proc/meminfo")
    if meminfo.exists():
        info = {}
        for line in meminfo.read_text().splitlines():
            parts = line.split(":")
            if len(parts) == 2:
                key = parts[0].strip()
                val = parts[1].strip().split()[0]
                info[key] = int(val)
        total = info.get("MemTotal", 0)
        avail = info.get("MemAvailable", 0)
        if total:
            used_pct = ((total - avail) / total) * 100
            checks.append(f"memory: {used_pct:.1f}% used ({avail // 1024} MB free)")

    # Load average
    try:
        load1, load5, load15 = os.getloadavg()
        checks.append(f"load: {load1:.2f} / {load5:.2f} / {load15:.2f}")
    except OSError:
        pass

    return " | ".join(checks)


async def _handle_memory_consolidate(job: Job) -> str:
    """Placeholder: consolidate memory files."""
    memory_dir = Path("~/.rally-agent/workspace/memory").expanduser()
    if not memory_dir.exists():
        return "No memory directory found"
    files = sorted(memory_dir.glob("*.md"))
    return f"Memory consolidation: {len(files)} files found (stub)"


async def _handle_pattern_analysis(job: Job) -> str:
    """Placeholder: analyze user patterns."""
    logger.info("[patternAnalysis] Analyzing patterns…")
    return "Pattern analysis completed (stub)"


# Handler registry
BUILT_IN_HANDLERS: Dict[str, JobHandler] = {
    "systemEvent":       _handle_system_event,
    "agentTurn":         _handle_agent_turn,
    "shellCommand":      _handle_shell_command,
    "webhook":           _handle_webhook,
    "fileWatch":         _handle_file_watch,
    "emailCheck":        _handle_email_check,
    "newsGather":        _handle_news_gather,
    "healthCheck":       _handle_health_check,
    "memoryConsolidate": _handle_memory_consolidate,
    "patternAnalysis":   _handle_pattern_analysis,
}


# ═══════════════════════════════════════════════════════════════
# 🗓️ Job Scheduler
# ═══════════════════════════════════════════════════════════════

class JobScheduler:
    """Persistent job scheduler with cron, retries, dependencies, and concurrency control.

    Persists all jobs to ~/.rally-agent/data/jobs.json.
    """

    def __init__(
        self,
        data_dir: Union[str, Path] = "~/.rally-agent/data",
        max_concurrent_jobs: int = 5,
    ) -> None:
        self._data_dir = Path(data_dir).expanduser()
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._jobs_path = self._data_dir / "jobs.json"

        self._jobs: Dict[str, Job] = {}
        self._handlers: Dict[str, JobHandler] = dict(BUILT_IN_HANDLERS)
        self._running_tasks: Dict[str, asyncio.Task] = {}
        self._max_concurrent = max_concurrent_jobs
        self._semaphore = asyncio.Semaphore(max_concurrent_jobs)

        self._scheduler_running = False
        self._scheduler_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

        self._load_jobs()
        logger.info("JobScheduler initialised with %d jobs", len(self._jobs))

    # ── Persistence ──────────────────────────────────────────

    def _load_jobs(self) -> None:
        if not self._jobs_path.exists():
            return
        try:
            raw = json.loads(self._jobs_path.read_text(encoding="utf-8"))
            for item in raw:
                job = Job.from_dict(item)
                self._jobs[job.job_id] = job
        except Exception as e:
            logger.error("Failed to load jobs: %s", e)

    def _save_jobs(self) -> None:
        try:
            data = [j.to_dict() for j in self._jobs.values()]
            self._jobs_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error("Failed to save jobs: %s", e)

    # ── Job CRUD ─────────────────────────────────────────────

    def add_job(
        self,
        name: str,
        job_type: Union[str, JobType],
        schedule: str,
        payload: Optional[Dict[str, Any]] = None,
        *,
        timeout: float = 300.0,
        max_retries: int = 0,
        retry_delay: float = 30.0,
        depends_on: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        enabled: bool = True,
    ) -> Job:
        """Create and register a new job."""
        if isinstance(job_type, str):
            job_type = JobType(job_type)

        # Validate schedule
        parse_cron(schedule)

        job_id = uuid.uuid4().hex[:12]
        job = Job(
            job_id=job_id,
            name=name,
            job_type=job_type,
            schedule=schedule,
            payload=payload or {},
            enabled=enabled,
            timeout=timeout,
            max_retries=max_retries,
            retry_delay=retry_delay,
            depends_on=depends_on or [],
            tags=tags or [],
        )
        job.next_run = self._compute_next_run(schedule)

        self._jobs[job_id] = job
        self._save_jobs()
        logger.info("Added job '%s' (id=%s) schedule=%s", name, job_id, schedule)
        return job

    def remove_job(self, job_id: str) -> bool:
        """Remove a job permanently."""
        if job_id not in self._jobs:
            return False
        # Cancel if running
        self._cancel_running(job_id)
        del self._jobs[job_id]
        self._save_jobs()
        logger.info("Removed job %s", job_id)
        return True

    def get_job(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def list_jobs(
        self,
        *,
        job_type: Optional[Union[str, JobType]] = None,
        status: Optional[Union[str, JobStatus]] = None,
        tag: Optional[str] = None,
        enabled_only: bool = False,
    ) -> List[Job]:
        """List jobs with optional filters."""
        result = list(self._jobs.values())
        if job_type:
            jt = job_type if isinstance(job_type, JobType) else JobType(job_type)
            result = [j for j in result if j.job_type == jt]
        if status:
            st = status if isinstance(status, JobStatus) else JobStatus(status)
            result = [j for j in result if j.status == st]
        if tag:
            result = [j for j in result if tag in j.tags]
        if enabled_only:
            result = [j for j in result if j.enabled]
        return sorted(result, key=lambda j: j.next_run or 0)

    # ── Job Control ──────────────────────────────────────────

    def enable_job(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if not job:
            return False
        job.enabled = True
        job.status = JobStatus.ACTIVE
        job.next_run = self._compute_next_run(job.schedule)
        self._save_jobs()
        return True

    def disable_job(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if not job:
            return False
        job.enabled = False
        job.status = JobStatus.DISABLED
        self._cancel_running(job_id)
        self._save_jobs()
        return True

    def pause_job(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if not job:
            return False
        job.status = JobStatus.PAUSED
        self._cancel_running(job_id)
        self._save_jobs()
        return True

    def resume_job(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if not job or job.status != JobStatus.PAUSED:
            return False
        job.status = JobStatus.ACTIVE
        job.enabled = True
        job.next_run = self._compute_next_run(job.schedule)
        self._save_jobs()
        return True

    def trigger_job(self, job_id: str) -> Optional[str]:
        """Manually trigger a job immediately (outside schedule)."""
        job = self._jobs.get(job_id)
        if not job:
            return None
        # Schedule for "now"
        job.next_run = time.time()
        return job_id

    def _cancel_running(self, job_id: str) -> None:
        task = self._running_tasks.get(job_id)
        if task and not task.done():
            task.cancel()

    # ── Custom Handlers ──────────────────────────────────────

    def register_handler(self, job_type: str, handler: JobHandler) -> None:
        """Register a custom job handler."""
        self._handlers[job_type] = handler
        logger.info("Registered handler for job type: %s", job_type)

    # ── Scheduler Loop ───────────────────────────────────────

    async def start(self, poll_interval: float = 5.0) -> None:
        """Start the async scheduler loop."""
        if self._scheduler_running:
            return
        self._scheduler_running = True
        self._stop_event.clear()
        self._scheduler_task = asyncio.create_task(
            self._scheduler_loop(poll_interval),
            name="job-scheduler",
        )
        logger.info("Job scheduler started (poll=%ss)", poll_interval)

    async def stop(self) -> None:
        """Stop the scheduler and cancel running jobs."""
        self._scheduler_running = False
        self._stop_event.set()
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
        # Cancel all running job tasks
        for task in list(self._running_tasks.values()):
            if not task.done():
                task.cancel()
        self._running_tasks.clear()
        logger.info("Job scheduler stopped")

    async def _scheduler_loop(self, poll_interval: float) -> None:
        while self._scheduler_running:
            try:
                await self._tick()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Scheduler tick error: %s", e, exc_info=True)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=poll_interval)
                break  # stop event was set
            except asyncio.TimeoutError:
                pass  # normal — just loop again

    async def _tick(self) -> None:
        now = time.time()
        for job in list(self._jobs.values()):
            if not job.enabled or job.status not in (JobStatus.ACTIVE, JobStatus.FAILED):
                continue
            if job.next_run is None or job.next_run > now:
                continue

            # Check concurrency limit for this specific job
            running_for_job = sum(
                1 for jid, t in self._running_tasks.items()
                if jid == job.job_id and not t.done()
            )
            if running_for_job >= job.max_concurrent:
                logger.debug("Job '%s' at max concurrency (%d)", job.name, job.max_concurrent)
                job.next_run = self._compute_next_run(job.schedule)
                continue

            # Check dependencies
            if not self._check_dependencies(job):
                logger.debug("Job '%s' waiting on dependencies", job.name)
                job.next_run = now + 30  # re-check in 30s
                continue

            # Launch
            task = asyncio.create_task(
                self._execute_job(job),
                name=f"job-{job.job_id}",
            )
            self._running_tasks[job.job_id] = task

    def _check_dependencies(self, job: Job) -> bool:
        """Return True if all dependency jobs succeeded on their last run."""
        for dep_id in job.depends_on:
            dep = self._jobs.get(dep_id)
            if dep is None:
                continue  # missing dep → skip (don't block forever)
            if dep.last_run is None:
                return False  # dep never ran
            # Find the last run record
            if dep.history:
                last = dep.history[-1]
                if last.status != "success":
                    return False
        return True

    # ── Job Execution ────────────────────────────────────────

    async def _execute_job(self, job: Job) -> None:
        """Execute a job with timeout and retry logic."""
        handler = self._handlers.get(job.job_type.value)
        if handler is None:
            logger.error("No handler for job type '%s'", job.job_type.value)
            job.status = JobStatus.FAILED
            job.fail_count += 1
            self._save_jobs()
            return

        attempt = 0
        max_attempts = 1 + job.max_retries

        while attempt < max_attempts:
            attempt += 1
            run_id = uuid.uuid4().hex[:10]
            record = JobRunRecord(
                run_id=run_id,
                started_at=time.time(),
                attempt=attempt,
            )
            job.status = JobStatus.RUNNING

            try:
                async with self._semaphore:
                    result = await asyncio.wait_for(
                        handler(job), timeout=job.timeout
                    )
                record.status = "success"
                record.output = result[:2000]  # truncate
                record.finished_at = time.time()

                job.status = JobStatus.ACTIVE
                job.success_count += 1
                job.last_run = time.time()
                job.history.append(record)
                job.run_count += 1
                job.next_run = self._compute_next_run(job.schedule)
                logger.info(
                    "Job '%s' succeeded (attempt %d): %s",
                    job.name, attempt, result[:200],
                )
                break  # success → exit retry loop

            except asyncio.TimeoutError:
                record.status = "timeout"
                record.error = f"Timed out after {job.timeout}s"
                record.finished_at = time.time()
                logger.warning("Job '%s' timed out (attempt %d)", job.name, attempt)

            except asyncio.CancelledError:
                record.status = "cancelled"
                record.error = "Cancelled"
                record.finished_at = time.time()
                job.history.append(record)
                return  # don't retry cancelled

            except Exception as e:
                record.status = "failed"
                record.error = str(e)[:1000]
                record.finished_at = time.time()
                logger.error(
                    "Job '%s' failed (attempt %d): %s",
                    job.name, attempt, e,
                )

            job.history.append(record)
            job.run_count += 1

            # Retry delay
            if attempt < max_attempts:
                delay = job.retry_delay * (2 ** (attempt - 1))  # exponential backoff
                logger.info("Retrying job '%s' in %.1fs", job.name, delay)
                await asyncio.sleep(delay)

        # After all attempts
        if job.history and job.history[-1].status != "success":
            job.fail_count += 1
            job.status = JobStatus.FAILED
            job.next_run = self._compute_next_run(job.schedule)

        self._save_jobs()

    # ── Schedule Computation ─────────────────────────────────

    @staticmethod
    def _compute_next_run(schedule: str, from_time: Optional[float] = None) -> float:
        """Compute next run epoch from a cron expression."""
        now = from_time or time.time()
        dt = datetime.fromtimestamp(now, tz=timezone.utc)
        cron = parse_cron(schedule)
        nxt = cron.next(dt)
        if nxt is None:
            return now + 3600  # fallback
        return nxt.timestamp()

    # ── Job History & Stats ──────────────────────────────────

    def get_job_history(
        self,
        job_id: str,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Return recent run history for a job."""
        job = self._jobs.get(job_id)
        if not job:
            return []
        records = job.history[-limit:]
        return [asdict(r) for r in reversed(records)]

    def get_stats(self) -> Dict[str, Any]:
        """Return global scheduler statistics."""
        total = len(self._jobs)
        active = sum(1 for j in self._jobs.values() if j.enabled and j.status == JobStatus.ACTIVE)
        running = sum(1 for j in self._jobs.values() if j.status == JobStatus.RUNNING)
        failed = sum(1 for j in self._jobs.values() if j.status == JobStatus.FAILED)
        paused = sum(1 for j in self._jobs.values() if j.status == JobStatus.PAUSED)
        total_runs = sum(j.run_count for j in self._jobs.values())
        total_success = sum(j.success_count for j in self._jobs.values())
        total_fail = sum(j.fail_count for j in self._jobs.values())

        return {
            "total_jobs": total,
            "active": active,
            "running": running,
            "failed": failed,
            "paused": paused,
            "disabled": total - active - running - failed - paused,
            "total_runs": total_runs,
            "total_success": total_success,
            "total_fail": total_fail,
            "success_rate": total_success / max(1, total_runs),
            "handlers": list(self._handlers.keys()),
            "scheduler_running": self._scheduler_running,
        }

    def get_status_table(self) -> List[Dict[str, Any]]:
        """Return a summary suitable for visual display."""
        rows = []
        for job in sorted(self._jobs.values(), key=lambda j: j.next_run or 0):
            rows.append({
                "id": job.job_id,
                "name": job.name,
                "type": job.job_type.value,
                "schedule": job.schedule,
                "status": job.status.value,
                "enabled": job.enabled,
                "runs": job.run_count,
                "success": job.success_count,
                "fail": job.fail_count,
                "last_run": (
                    datetime.fromtimestamp(job.last_run).isoformat()
                    if job.last_run else "never"
                ),
                "next_run": (
                    datetime.fromtimestamp(job.next_run).isoformat()
                    if job.next_run else "—"
                ),
                "tags": job.tags,
            })
        return rows

    # ── Dependency Graph ─────────────────────────────────────

    def get_dependency_graph(self) -> Dict[str, List[str]]:
        """Return job_id → [dependency_ids] mapping."""
        return {
            job.job_id: list(job.depends_on)
            for job in self._jobs.values()
            if job.depends_on
        }

    def add_dependency(self, job_id: str, depends_on_id: str) -> bool:
        """Add a dependency: job_id will not run until depends_on_id succeeds."""
        job = self._jobs.get(job_id)
        dep = self._jobs.get(depends_on_id)
        if not job or not dep:
            return False
        if depends_on_id not in job.depends_on:
            job.depends_on.append(depends_on_id)
            self._save_jobs()
        return True

    def remove_dependency(self, job_id: str, depends_on_id: str) -> bool:
        job = self._jobs.get(job_id)
        if not job or depends_on_id not in job.depends_on:
            return False
        job.depends_on.remove(depends_on_id)
        self._save_jobs()
        return True
