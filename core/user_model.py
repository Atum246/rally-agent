"""
🟣 Rally Agent — Sophisticated User Model
==========================================
Builds a comprehensive digital twin of the user.
Learns personality, communication style, interests, expertise,
goals, routines, preferences, emotional patterns, and project context.

Every conversation makes the model sharper.
"""

import asyncio
import json
import os
import re
import time
import logging
import threading
from typing import Optional, Any, Dict, List, Set, Tuple
from datetime import datetime, timedelta
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger("rally.user_model")


# ═══════════════════════════════════════════════════════════════
# 📐 Constants & Helpers
# ═══════════════════════════════════════════════════════════════

# Decay factor: older signals matter less over time
DECAY_HALF_LIFE_DAYS = 30
MAX_HISTORY_ENTRIES = 500
MAX_CORRECTIONS = 200
MAX_GOALS = 100
MAX_PREFERENCES = 300
SAVE_INTERVAL = 10  # save every N observations
PRIVACY_DEFAULTS: Dict[str, bool] = {
    "track_personality": True,
    "track_interests": True,
    "track_expertise": True,
    "track_goals": True,
    "track_routines": True,
    "track_preferences": True,
    "track_corrections": True,
    "track_emotions": True,
    "track_projects": True,
}


def _time_decay(created_iso: str, half_life_days: float = DECAY_HALF_LIFE_DAYS) -> float:
    """Return a weight [0..1] based on exponential decay from creation time."""
    try:
        created = datetime.fromisoformat(created_iso)
    except (ValueError, TypeError):
        return 1.0
    age_days = (datetime.now() - created).total_seconds() / 86400
    return 0.5 ** (age_days / half_life_days)


def _weighted_score(count: int, created_iso: str, boost: float = 1.0) -> float:
    """Combine raw count with time-decay for importance scoring."""
    return count * _time_decay(created_iso) * boost


# ═══════════════════════════════════════════════════════════════
# 🧩 Data Containers
# ═══════════════════════════════════════════════════════════════

@dataclass
class TraitScore:
    """A single trait with score, confidence, and evidence."""
    score: float = 0.0          # 0.0 – 1.0
    confidence: float = 0.0     # based on sample size
    evidence_count: int = 0
    first_seen: str = ""
    last_seen: str = ""

    def to_dict(self) -> dict:
        return {
            "score": round(self.score, 4),
            "confidence": round(self.confidence, 4),
            "evidence_count": self.evidence_count,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TraitScore":
        return cls(
            score=d.get("score", 0),
            confidence=d.get("confidence", 0),
            evidence_count=d.get("evidence_count", 0),
            first_seen=d.get("first_seen", ""),
            last_seen=d.get("last_seen", ""),
        )


@dataclass
class TopicWeight:
    """A tracked topic with weighted importance."""
    topic: str = ""
    raw_count: int = 0
    weighted_score: float = 0.0
    first_seen: str = ""
    last_seen: str = ""
    subtopics: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "topic": self.topic,
            "raw_count": self.raw_count,
            "weighted_score": round(self.weighted_score, 4),
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "subtopics": self.subtopics,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TopicWeight":
        return cls(
            topic=d.get("topic", ""),
            raw_count=d.get("raw_count", 0),
            weighted_score=d.get("weighted_score", 0),
            first_seen=d.get("first_seen", ""),
            last_seen=d.get("last_seen", ""),
            subtopics=d.get("subtopics", {}),
        )


@dataclass
class Goal:
    """A tracked goal with progress and metadata."""
    goal_id: str = ""
    text: str = ""
    status: str = "active"      # active, paused, completed, abandoned
    priority: str = "medium"    # low, medium, high, critical
    progress: float = 0.0       # 0.0 – 1.0
    deadline: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    milestones: List[Dict[str, Any]] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    completed_at: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "goal_id": self.goal_id,
            "text": self.text,
            "status": self.status,
            "priority": self.priority,
            "progress": round(self.progress, 3),
            "deadline": self.deadline,
            "tags": self.tags,
            "milestones": self.milestones,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Goal":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class Correction:
    """A correction the user made to the agent's output."""
    correction_id: str = ""
    original_text: str = ""
    corrected_text: str = ""
    category: str = ""          # factual, style, preference, technical
    context: str = ""
    timestamp: str = ""

    def to_dict(self) -> dict:
        return {
            "correction_id": self.correction_id,
            "original_text": self.original_text,
            "corrected_text": self.corrected_text,
            "category": self.category,
            "context": self.context[:300],
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Correction":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class ProjectContext:
    """An active project the user is working on."""
    project_id: str = ""
    name: str = ""
    description: str = ""
    tech_stack: List[str] = field(default_factory=list)
    status: str = "active"      # active, paused, completed
    files_mentioned: List[str] = field(default_factory=list)
    last_discussed: str = ""
    created_at: str = ""

    def to_dict(self) -> dict:
        return {
            "project_id": self.project_id,
            "name": self.name,
            "description": self.description,
            "tech_stack": self.tech_stack,
            "status": self.status,
            "files_mentioned": self.files_mentioned[-20:],
            "last_discussed": self.last_discussed,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ProjectContext":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class EmotionalSnapshot:
    """Detected emotional state at a point in time."""
    timestamp: str = ""
    valence: float = 0.0        # -1 (negative) to +1 (positive)
    arousal: float = 0.0        # 0 (calm) to 1 (excited)
    dominant_emotion: str = ""  # happy, frustrated, curious, etc.
    signals: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "valence": round(self.valence, 3),
            "arousal": round(self.arousal, 3),
            "dominant_emotion": self.dominant_emotion,
            "signals": self.signals,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "EmotionalSnapshot":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ═══════════════════════════════════════════════════════════════
# 🧠 Personality & Communication Profiler
# ═══════════════════════════════════════════════════════════════

class PersonalityProfiler:
    """Infers personality traits from conversation patterns.

    Uses a Bayesian-inspired approach: each observation updates
    trait scores with exponential moving averages, and confidence
    grows with evidence count.
    """

    # Trait detection patterns — each maps to (regex, weight_direction)
    TRAIT_PATTERNS: Dict[str, List[Tuple[str, float]]] = {
        "analytical": [
            (r"\b(analyze|data|metrics|statistics|evidence|logic|reason|therefore|hence|consequently)\b", 1.0),
            (r"\b(gut feeling|vibes|idk|whatever)\b", -0.5),
        ],
        "creative": [
            (r"\b(create|design|idea|brainstorm|imagine|innovate|inspired|artistic)\b", 1.0),
        ],
        "detail_oriented": [
            (r"\b(detail|precise|exact|specific|careful|thorough|edge case|corner case)\b", 1.0),
        ],
        "ambitious": [
            (r"\b(build|ship|launch|scale|grow|massive|huge|disrupt|revolutionize)\b", 1.0),
        ],
        "pragmatic": [
            (r"\b(practical|simple|working|fast|quick|efficient|mvp|minimum viable)\b", 1.0),
        ],
        "curious": [
            (r"\b(how does|why does|what if|learn|understand|explore|discover|deep dive)\b", 1.0),
        ],
        "perfectionist": [
            (r"\b(perfect|best|flawless|optimal|clean code|refactor|polish)\b", 1.0),
        ],
        "collaborative": [
            (r"\b(we|our|together|team|pair|share|help each other)\b", 1.0),
        ],
        "independent": [
            (r"\b(I'll|I want|my way|just me|solo|on my own)\b", 1.0),
        ],
        "systematic": [
            (r"\b(process|workflow|pipeline|architecture|system|methodology|framework)\b", 1.0),
        ],
        "impatient": [
            (r"\b(asap|quickly|hurry|fast|now|immediately|just do it|skip)\b", 1.0),
            (r"\b(take your time|no rush|whenever|carefully)\b", -0.5),
        ],
    }

    def __init__(self):
        self.traits: Dict[str, TraitScore] = {}

    def observe(self, text: str) -> Dict[str, float]:
        """Analyze text and update trait scores. Returns delta changes."""
        text_lower = text.lower()
        now = datetime.now().isoformat()
        deltas: Dict[str, float] = {}

        for trait, patterns in self.TRAIT_PATTERNS.items():
            net_signal = 0.0
            for pattern, direction in patterns:
                matches = len(re.findall(pattern, text_lower))
                net_signal += matches * direction

            if net_signal == 0:
                continue

            ts = self.traits.get(trait)
            if ts is None:
                ts = TraitScore(first_seen=now)
                self.traits[trait] = ts

            # Exponential moving average update
            alpha = 1.0 / (1 + ts.evidence_count)
            signal = max(-1.0, min(1.0, net_signal * 0.1))
            new_score = ts.score + alpha * (signal - ts.score)
            ts.score = max(0.0, min(1.0, new_score))
            ts.evidence_count += 1
            ts.confidence = min(1.0, ts.evidence_count / 20)
            ts.last_seen = now
            deltas[trait] = signal

        return deltas

    def top_traits(self, n: int = 8) -> List[Tuple[str, TraitScore]]:
        """Return the top N traits sorted by score * confidence."""
        return sorted(
            self.traits.items(),
            key=lambda x: x[1].score * x[1].confidence,
            reverse=True,
        )[:n]

    def to_dict(self) -> dict:
        return {k: v.to_dict() for k, v in self.traits.items()}

    @classmethod
    def from_dict(cls, data: dict) -> "PersonalityProfiler":
        p = cls()
        for k, v in data.items():
            p.traits[k] = TraitScore.from_dict(v)
        return p


class CommunicationStyleAnalyzer:
    """Analyzes how the user communicates.

    Tracks formality, verbosity, technical level, tone,
    use of emoji, code-heavy vs text-heavy, question frequency.
    """

    def __init__(self):
        self.formality: float = 0.5        # 0=casual, 1=formal
        self.verbosity: float = 0.5        # 0=concise, 1=verbose
        self.technical_level: float = 0.5  # 0=simple, 1=technical
        self.emoji_usage: float = 0.0      # 0=none, 1=heavy
        self.question_ratio: float = 0.0   # fraction of messages that are questions
        self.code_ratio: float = 0.0       # fraction with code blocks
        self.avg_message_length: float = 0.0
        self._sample_count: int = 0

    def observe(self, text: str) -> None:
        """Update style metrics from a new message."""
        self._sample_count += 1
        n = self._sample_count
        alpha = 1.0 / min(n, 100)  # moving average, capped

        words = text.split()
        word_count = len(words)

        # Verbosity
        length_signal = min(1.0, word_count / 80)
        self.verbosity += alpha * (length_signal - self.verbosity)

        # Formality
        text_lower = text.lower()
        formal = len(re.findall(r"\b(please|kindly|would you|could you|shall|regards|sincerely)\b", text_lower))
        casual = len(re.findall(r"\b(hey|yo|sup|gonna|wanna|lol|lmao|bro|nah|yep|ok)\b", text_lower))
        if formal + casual > 0:
            form_signal = formal / (formal + casual)
            self.formality += alpha * (form_signal - self.formality)

        # Technical level
        tech_words = len(re.findall(
            r"\b(api|sdk|function|class|variable|algorithm|architecture|infrastructure|"
            r"async|await|thread|process|memory|stack|heap|binary|hex|regex|schema)\b",
            text_lower,
        ))
        tech_signal = min(1.0, tech_words / 5)
        self.technical_level += alpha * (tech_signal - self.technical_level)

        # Emoji usage
        emoji_count = len(re.findall(
            r"[\U0001f600-\U0001f64f\U0001f300-\U0001f5ff\U0001f680-\U0001f6ff"
            r"\U0001f900-\U0001f9ff\U00002702-\U000027b0\U0001fa00-\U0001fa6f"
            r"\U0001fa70-\U0001faff\U00002600-\U000026ff]",
            text,
        ))
        emoji_signal = min(1.0, emoji_count / 5)
        self.emoji_usage += alpha * (emoji_signal - self.emoji_usage)

        # Code ratio
        code_blocks = len(re.findall(r"```", text))
        has_code = 1.0 if code_blocks >= 2 or "    " in text else 0.0
        self.code_ratio += alpha * (has_code - self.code_ratio)

        # Question ratio
        is_question = 1.0 if "?" in text or re.search(r"\b(what|how|why|when|where|who|can you|could you)\b", text_lower) else 0.0
        self.question_ratio += alpha * (is_question - self.question_ratio)

        # Average message length
        self.avg_message_length += alpha * (word_count - self.avg_message_length)

    @property
    def style_label(self) -> str:
        """Human-readable style label."""
        parts = []
        parts.append("formal" if self.formality > 0.6 else "casual" if self.formality < 0.4 else "neutral")
        parts.append("verbose" if self.verbosity > 0.6 else "concise" if self.verbosity < 0.4 else "moderate")
        if self.technical_level > 0.6:
            parts.append("technical")
        if self.emoji_usage > 0.3:
            parts.append("emoji-rich")
        return ", ".join(parts)

    def to_dict(self) -> dict:
        return {
            "formality": round(self.formality, 4),
            "verbosity": round(self.verbosity, 4),
            "technical_level": round(self.technical_level, 4),
            "emoji_usage": round(self.emoji_usage, 4),
            "question_ratio": round(self.question_ratio, 4),
            "code_ratio": round(self.code_ratio, 4),
            "avg_message_length": round(self.avg_message_length, 1),
            "sample_count": self._sample_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CommunicationStyleAnalyzer":
        c = cls()
        c.formality = data.get("formality", 0.5)
        c.verbosity = data.get("verbosity", 0.5)
        c.technical_level = data.get("technical_level", 0.5)
        c.emoji_usage = data.get("emoji_usage", 0.0)
        c.question_ratio = data.get("question_ratio", 0.0)
        c.code_ratio = data.get("code_ratio", 0.0)
        c.avg_message_length = data.get("avg_message_length", 0.0)
        c._sample_count = data.get("sample_count", 0)
        return c


# ═══════════════════════════════════════════════════════════════
# 🎯 Interest & Expertise Tracker
# ═══════════════════════════════════════════════════════════════

class InterestTracker:
    """Tracks user interests with weighted topics and time-decay."""

    # Topic taxonomy with detection patterns
    TOPIC_PATTERNS: Dict[str, List[str]] = {
        "programming": [
            r"\b(code|function|class|variable|api|sdk|library|debug|compile|syntax|refactor|module)\b",
        ],
        "web_development": [
            r"\b(html|css|javascript|react|vue|angular|node|express|django|flask|nextjs|svelte)\b",
        ],
        "ai_ml": [
            r"\b(ai|machine learning|deep learning|model|neural|llm|gpt|claude|training|inference|transformer|diffusion)\b",
        ],
        "devops": [
            r"\b(docker|kubernetes|deploy|ci.cd|server|aws|azure|gcp|terraform|nginx|helm|argocd)\b",
        ],
        "data_science": [
            r"\b(data|analysis|statistics|pandas|numpy|visualization|chart|jupyter|notebook)\b",
        ],
        "security": [
            r"\b(security|encrypt|password|auth|vulnerability|firewall|zero.trust|pentest)\b",
        ],
        "design": [
            r"\b(design|ui|ux|figma|sketch|layout|color|typography|wireframe|prototype)\b",
        ],
        "business": [
            r"\b(business|startup|revenue|market|customer|product|launch|growth|strategy)\b",
        ],
        "writing": [
            r"\b(write|essay|article|blog|content|copy|documentation|copywriting|technical.writing)\b",
        ],
        "research": [
            r"\b(research|study|analyze|investigate|compare|evaluate|paper|arxiv|citation)\b",
        ],
        "gaming": [
            r"\b(game|gaming|unity|unreal|steam|esports|godot|shader|render)\b",
        ],
        "finance": [
            r"\b(money|invest|stock|crypto|bitcoin|budget|trading|portfolio|defi)\b",
        ],
        "health": [
            r"\b(health|exercise|diet|sleep|fitness|wellness|medical|nutrition)\b",
        ],
        "music": [
            r"\b(music|audio|song|beat|melody|producer|spotify|daw|synth)\b",
        ],
        "video": [
            r"\b(video|youtube|tiktok|edit|render|animation|premiere|after.effects)\b",
        ],
        "photography": [
            r"\b(photo|camera|lightroom|photoshop|portrait|landscape|exposure|aperture)\b",
        ],
        "philosophy": [
            r"\b(philosophy|ethics|morality|consciousness|existence|epistemology|ontology)\b",
        ],
        "science": [
            r"\b(physics|chemistry|biology|quantum|relativity|molecule|experiment|hypothesis)\b",
        ],
        "languages": [
            r"\b(language|translate|grammar|vocabulary|fluent|bilingual|linguistic)\b",
        ],
        "automation": [
            r"\b(automate|workflow|pipeline|script|bot|cron|schedule|trigger)\b",
        ],
    }

    # Programming language detection
    LANG_PATTERNS: Dict[str, str] = {
        "python": r"\b(python|pip|django|flask|pandas|numpy|pytest|asyncio|conda)\b",
        "javascript": r"\b(javascript|js|node|npm|react|vue|angular|typescript|ts|deno)\b",
        "rust": r"\b(rust|cargo|crate|rustc|tokio|wasm|clippy)\b",
        "go": r"\b(golang|go\b|goroutine|gofmt|gin)\b",
        "java": r"\b(java|spring|maven|gradle|jvm|kotlin|junit)\b",
        "c_cpp": r"\b(c\+\+|cpp|cmake|gcc|clang|makefile|header)\b",
        "ruby": r"\b(ruby|rails|gem|bundler|rspec)\b",
        "php": r"\b(php|laravel|composer|symfony)\b",
        "swift": r"\b(swift|ios|xcode|cocoapods|swiftui)\b",
        "kotlin": r"\b(kotlin|android|gradle|kmp)\b",
        "sql": r"\b(sql|postgres|mysql|sqlite|query|join|select|where)\b",
        "shell": r"\b(bash|shell|zsh|script|grep|awk|sed|pipe)\b",
    }

    # Framework detection
    FRAMEWORK_PATTERNS: Dict[str, str] = {
        "react": r"\b(react|jsx|tsx|next\.js|nextjs|remix)\b",
        "vue": r"\b(vue|nuxt|vite|pinia)\b",
        "svelte": r"\b(svelte|sveltekit)\b",
        "django": r"\b(django|drf)\b",
        "flask": r"\b(flask)\b",
        "fastapi": r"\b(fastapi|uvicorn|pydantic)\b",
        "express": r"\b(express|expressjs)\b",
        "tensorflow": r"\b(tensorflow|tf|keras)\b",
        "pytorch": r"\b(pytorch|torch|lightning)\b",
        "tailwind": r"\b(tailwind|tailwindcss)\b",
        "docker": r"\b(docker|dockerfile|compose)\b",
        "kubernetes": r"\b(kubernetes|k8s|kubectl|helm)\b",
    }

    def __init__(self):
        self.topics: Dict[str, TopicWeight] = {}
        self.languages: Dict[str, TopicWeight] = {}
        self.frameworks: Dict[str, TopicWeight] = {}
        self.keywords: Counter = Counter()
        self.tools_used: Counter = Counter()

    def observe(self, text: str) -> None:
        """Extract and weight topics from text."""
        text_lower = text.lower()
        now = datetime.now().isoformat()

        # Topics
        for topic, patterns in self.TOPIC_PATTERNS.items():
            hits = sum(len(re.findall(p, text_lower)) for p in patterns)
            if hits > 0:
                self._update_topic(self.topics, topic, hits, now)

        # Languages
        for lang, pattern in self.LANG_PATTERNS.items():
            hits = len(re.findall(pattern, text_lower))
            if hits > 0:
                self._update_topic(self.languages, lang, hits, now)

        # Frameworks
        for fw, pattern in self.FRAMEWORK_PATTERNS.items():
            hits = len(re.findall(pattern, text_lower))
            if hits > 0:
                self._update_topic(self.frameworks, fw, hits, now)

        # Keywords (top meaningful words)
        words = re.findall(r"\b[a-z]{4,}\b", text_lower)
        stopwords = {
            "this", "that", "with", "from", "have", "been", "will", "would",
            "could", "should", "about", "there", "their", "them", "they",
            "your", "just", "like", "what", "when", "which", "where", "some",
            "more", "than", "also", "into", "only", "very", "really", "does",
            "don't", "can't", "want", "need", "here", "well", "make", "sure",
            "think", "know", "time", "work", "file", "code", "help", "using",
            "want", "doesn't", "didn't", "isn't", "wasn't", "aren't",
        }
        for w in words:
            if w not in stopwords:
                self.keywords[w] += 1

        # Trim keywords to top 500
        if len(self.keywords) > 500:
            self.keywords = Counter(dict(self.keywords.most_common(500)))

    def _update_topic(self, store: Dict[str, TopicWeight], key: str, hits: int, now: str) -> None:
        if key not in store:
            store[key] = TopicWeight(topic=key, first_seen=now)
        tw = store[key]
        tw.raw_count += hits
        tw.last_seen = now
        tw.weighted_score = _weighted_score(tw.raw_count, tw.first_seen)

    def top_topics(self, n: int = 10) -> List[Tuple[str, float]]:
        """Return top N topics by weighted score."""
        all_topics = {**self.topics, **self.languages, **self.frameworks}
        return sorted(
            [(k, v.weighted_score) for k, v in all_topics.items()],
            key=lambda x: x[1],
            reverse=True,
        )[:n]

    def to_dict(self) -> dict:
        return {
            "topics": {k: v.to_dict() for k, v in self.topics.items()},
            "languages": {k: v.to_dict() for k, v in self.languages.items()},
            "frameworks": {k: v.to_dict() for k, v in self.frameworks.items()},
            "keywords": dict(self.keywords.most_common(200)),
            "tools_used": dict(self.tools_used.most_common(100)),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "InterestTracker":
        t = cls()
        for k, v in data.get("topics", {}).items():
            t.topics[k] = TopicWeight.from_dict(v)
        for k, v in data.get("languages", {}).items():
            t.languages[k] = TopicWeight.from_dict(v)
        for k, v in data.get("frameworks", {}).items():
            t.frameworks[k] = TopicWeight.from_dict(v)
        t.keywords = Counter(data.get("keywords", {}))
        t.tools_used = Counter(data.get("tools_used", {}))
        return t


# ═══════════════════════════════════════════════════════════════
# ⏰ Routine Detector
# ═══════════════════════════════════════════════════════════════

class RoutineDetector:
    """Detects user activity patterns and routines."""

    def __init__(self):
        self.hourly_activity: Counter = Counter()       # hour (0-23) -> count
        self.daily_activity: Counter = Counter()        # day name -> count
        self.session_lengths: List[float] = []          # in minutes
        self._session_start: Optional[float] = None
        self.common_commands: Counter = Counter()
        self.workflow_patterns: List[Dict[str, Any]] = []

    def observe(self, text: str, timestamp: Optional[datetime] = None) -> None:
        """Record an activity at the given time."""
        ts = timestamp or datetime.now()
        self.hourly_activity[ts.hour] += 1
        self.daily_activity[ts.strftime("%A")] += 1

        # Track command patterns
        if text.startswith(("!", "/", ">")):
            cmd = text.split()[0].lstrip("!/>")
            self.common_commands[cmd] += 1

    def start_session(self) -> None:
        self._session_start = time.time()

    def end_session(self) -> None:
        if self._session_start:
            duration = (time.time() - self._session_start) / 60
            self.session_lengths.append(round(duration, 1))
            if len(self.session_lengths) > 200:
                self.session_lengths = self.session_lengths[-200:]
            self._session_start = None

    @property
    def peak_hours(self) -> List[int]:
        """Hours with highest activity, sorted."""
        if not self.hourly_activity:
            return []
        return sorted(self.hourly_activity, key=self.hourly_activity.get, reverse=True)[:3]

    @property
    def avg_session_minutes(self) -> float:
        if not self.session_lengths:
            return 0.0
        return sum(self.session_lengths) / len(self.session_lengths)

    def to_dict(self) -> dict:
        return {
            "hourly_activity": dict(self.hourly_activity),
            "daily_activity": dict(self.daily_activity),
            "session_lengths": self.session_lengths[-100:],
            "common_commands": dict(self.common_commands.most_common(50)),
            "workflow_patterns": self.workflow_patterns[-20:],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RoutineDetector":
        r = cls()
        r.hourly_activity = Counter(data.get("hourly_activity", {}))
        r.daily_activity = Counter(data.get("daily_activity", {}))
        r.session_lengths = data.get("session_lengths", [])
        r.common_commands = Counter(data.get("common_commands", {}))
        r.workflow_patterns = data.get("workflow_patterns", [])
        return r


# ═══════════════════════════════════════════════════════════════
# 💭 Emotional Pattern Detector
# ═══════════════════════════════════════════════════════════════

class EmotionalDetector:
    """Detects emotional patterns from conversation text."""

    EMOTION_SIGNALS: Dict[str, Tuple[List[str], float, float]] = {
        # emotion: (patterns, valence, arousal)
        "happy":       ([r"\b(great|awesome|love|amazing|perfect|excellent|fantastic|wonderful|haha|lol|😂|🎉|❤️)\b"], 0.8, 0.5),
        "excited":     ([r"\b(excited|can't wait|incredible|wow|omg|🔥|🚀|!!)\b"], 0.7, 0.9),
        "satisfied":   ([r"\b(thanks|helpful|exactly|nice|good|works|solved)\b"], 0.6, 0.3),
        "frustrated":  ([r"\b(frustrated|annoying|broken|doesn't work|error|fail|bug|ugh|😤|😡)\b"], -0.7, 0.7),
        "confused":    ([r"\b(confused|don't understand|unclear|what\?|huh|lost)\b"], -0.3, 0.4),
        "anxious":     ([r"\b(worried|anxious|concerned|deadline|urgent|asap|behind)\b"], -0.5, 0.7),
        "curious":     ([r"\b(interesting|curious|wonder|explore|fascinating|hmm|🤔)\b"], 0.4, 0.6),
        "calm":        ([r"\b(calm|relaxed|peaceful|chill|easy|no rush|whenever)\b"], 0.3, 0.1),
        "disappointed": ([r"\b(disappointed|sad|unfortunately|too bad|可惜)\b"], -0.6, 0.3),
    }

    def __init__(self):
        self.history: List[EmotionalSnapshot] = []
        self.emotion_counts: Counter = Counter()

    def observe(self, text: str) -> Optional[EmotionalSnapshot]:
        """Detect emotional state from text."""
        text_lower = text.lower()
        best_emotion = ""
        best_score = 0.0
        valence_sum = 0.0
        arousal_sum = 0.0
        count = 0
        signals_found: List[str] = []

        for emotion, (patterns, val, aro) in self.EMOTION_SIGNALS.items():
            hits = sum(len(re.findall(p, text_lower)) for p in patterns)
            if hits > 0:
                score = hits * abs(val)
                if score > best_score:
                    best_score = score
                    best_emotion = emotion
                valence_sum += val * hits
                arousal_sum += aro * hits
                count += hits
                signals_found.append(emotion)

        if not best_emotion:
            return None

        snapshot = EmotionalSnapshot(
            timestamp=datetime.now().isoformat(),
            valence=max(-1, min(1, valence_sum / max(count, 1))),
            arousal=max(0, min(1, arousal_sum / max(count, 1))),
            dominant_emotion=best_emotion,
            signals=signals_found,
        )

        self.history.append(snapshot)
        self.emotion_counts[best_emotion] += 1

        # Keep bounded
        if len(self.history) > MAX_HISTORY_ENTRIES:
            self.history = self.history[-MAX_HISTORY_ENTRIES:]

        return snapshot

    @property
    def dominant_mood(self) -> str:
        if not self.emotion_counts:
            return "neutral"
        return self.emotion_counts.most_common(1)[0][0]

    @property
    def avg_valence(self) -> float:
        if not self.history:
            return 0.0
        recent = self.history[-50:]
        return sum(s.valence for s in recent) / len(recent)

    def to_dict(self) -> dict:
        return {
            "history": [s.to_dict() for s in self.history[-100:]],
            "emotion_counts": dict(self.emotion_counts),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EmotionalDetector":
        d = cls()
        d.history = [EmotionalSnapshot.from_dict(s) for s in data.get("history", [])]
        d.emotion_counts = Counter(data.get("emotion_counts", {}))
        return d


# ═══════════════════════════════════════════════════════════════
# 🔒 Privacy Controls
# ═══════════════════════════════════════════════════════════════

class PrivacyController:
    """Manages what the user model is allowed to track."""

    def __init__(self):
        self.settings: Dict[str, bool] = dict(PRIVACY_DEFAULTS)
        self.forget_topics: Set[str] = set()
        self.forget_keywords: Set[str] = set()

    def allow(self, category: str) -> bool:
        return self.settings.get(category, True)

    def set(self, category: str, enabled: bool) -> None:
        self.settings[category] = enabled

    def forget(self, topic: str) -> None:
        """Mark a topic to be excluded from tracking."""
        self.forget_topics.add(topic.lower())

    def should_track(self, text: str) -> bool:
        """Check if text contains topics that should be forgotten."""
        text_lower = text.lower()
        return not any(ft in text_lower for ft in self.forget_topics)

    def to_dict(self) -> dict:
        return {
            "settings": self.settings,
            "forget_topics": list(self.forget_topics),
            "forget_keywords": list(self.forget_keywords),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PrivacyController":
        p = cls()
        p.settings = {**PRIVACY_DEFAULTS, **data.get("settings", {})}
        p.forget_topics = set(data.get("forget_topics", []))
        p.forget_keywords = set(data.get("forget_keywords", []))
        return p


# ═══════════════════════════════════════════════════════════════
# 👤 The User Model — Digital Twin
# ═══════════════════════════════════════════════════════════════

class UserModel:
    """Comprehensive user model — a digital twin that learns and adapts.

    This is the core intelligence layer that makes every conversation
    context-aware. It builds a rich, multi-dimensional profile of the user
    from every interaction.
    """

    def __init__(self, config: Any = None, data_dir: Optional[str] = None):
        self.config = config
        self.data_dir = os.path.expanduser(data_dir or "~/.rally-agent/data")
        self.model_file = os.path.join(self.data_dir, "user_model.json")
        os.makedirs(self.data_dir, exist_ok=True)

        # Identity
        self.name: str = ""
        self.timezone: str = ""
        self.language: str = "en"
        self.created_at: str = datetime.now().isoformat()
        self.last_active: str = ""
        self.interaction_count: int = 0

        # Core subsystems
        self.personality = PersonalityProfiler()
        self.communication_style = CommunicationStyleAnalyzer()
        self.interests = InterestTracker()
        self.routines = RoutineDetector()
        self.emotions = EmotionalDetector()
        self.privacy = PrivacyController()

        # Data stores
        self.goals: List[Goal] = []
        self.corrections: List[Correction] = []
        self.preferences: List[Dict[str, Any]] = []
        self.projects: List[ProjectContext] = []
        self.notes: List[Dict[str, Any]] = []

        # Auto-save state
        self._dirty_count: int = 0
        self._save_lock = threading.Lock()

        # Load existing data
        self._load()

    # ───────────────────────────────────────────────────────
    # Persistence
    # ───────────────────────────────────────────────────────

    def _load(self) -> None:
        """Load user model from disk."""
        if not os.path.exists(self.model_file):
            return
        try:
            with open(self.model_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Identity
            self.name = data.get("name", "")
            self.timezone = data.get("timezone", "")
            self.language = data.get("language", "en")
            self.created_at = data.get("created_at", self.created_at)
            self.last_active = data.get("last_active", "")
            self.interaction_count = data.get("interaction_count", 0)

            # Subsystems
            self.personality = PersonalityProfiler.from_dict(data.get("personality", {}))
            self.communication_style = CommunicationStyleAnalyzer.from_dict(data.get("communication_style", {}))
            self.interests = InterestTracker.from_dict(data.get("interests", {}))
            self.routines = RoutineDetector.from_dict(data.get("routines", {}))
            self.emotions = EmotionalDetector.from_dict(data.get("emotions", {}))
            self.privacy = PrivacyController.from_dict(data.get("privacy", {}))

            # Data stores
            self.goals = [Goal.from_dict(g) for g in data.get("goals", [])]
            self.corrections = [Correction.from_dict(c) for c in data.get("corrections", [])]
            self.preferences = data.get("preferences", [])
            self.projects = [ProjectContext.from_dict(p) for p in data.get("projects", [])]
            self.notes = data.get("notes", [])

            logger.info(f"UserModel loaded: {self.interaction_count} interactions, {len(self.goals)} goals")
        except Exception as e:
            logger.error(f"Failed to load user model: {e}")

    def save(self) -> None:
        """Persist user model to disk with atomic write."""
        with self._save_lock:
            data = {
                "name": self.name,
                "timezone": self.timezone,
                "language": self.language,
                "created_at": self.created_at,
                "last_active": datetime.now().isoformat(),
                "interaction_count": self.interaction_count,
                "personality": self.personality.to_dict(),
                "communication_style": self.communication_style.to_dict(),
                "interests": self.interests.to_dict(),
                "routines": self.routines.to_dict(),
                "emotions": self.emotions.to_dict(),
                "privacy": self.privacy.to_dict(),
                "goals": [g.to_dict() for g in self.goals[-MAX_GOALS:]],
                "corrections": [c.to_dict() for c in self.corrections[-MAX_CORRECTIONS:]],
                "preferences": self.preferences[-MAX_PREFERENCES:],
                "projects": [p.to_dict() for p in self.projects],
                "notes": self.notes[-200:],
                "schema_version": 2,
            }
            # Atomic write: write to temp, then rename
            tmp = self.model_file + ".tmp"
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                os.replace(tmp, self.model_file)
                self._dirty_count = 0
                logger.debug("UserModel saved")
            except Exception as e:
                logger.error(f"Failed to save user model: {e}")
                try:
                    os.unlink(tmp)
                except OSError:
                    pass

    # ───────────────────────────────────────────────────────
    # Observation Pipeline
    # ───────────────────────────────────────────────────────

    def observe(
        self,
        user_input: str,
        response: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Observe a user-agent interaction and update all subsystems.

        This is the main entry point. Call this for every message exchange.
        Returns a summary of what was learned.
        """
        if not self.privacy.should_track(user_input):
            return {"skipped": True, "reason": "privacy_filter"}

        self.interaction_count += 1
        self.last_active = datetime.now().isoformat()
        meta = metadata or {}
        learned: Dict[str, Any] = {}

        # 1. Communication style (always)
        if self.privacy.allow("track_personality"):
            self.communication_style.observe(user_input)

        # 2. Personality traits
        if self.privacy.allow("track_personality"):
            trait_deltas = self.personality.observe(user_input)
            if trait_deltas:
                learned["traits"] = trait_deltas

        # 3. Interests & expertise
        if self.privacy.allow("track_interests"):
            self.interests.observe(user_input)

        # 4. Routines
        if self.privacy.allow("track_routines"):
            self.routines.observe(user_input)

        # 5. Emotions
        if self.privacy.allow("track_emotions"):
            emotion = self.emotions.observe(user_input)
            if emotion:
                learned["emotion"] = emotion.dominant_emotion

        # 6. Goals
        if self.privacy.allow("track_goals"):
            new_goals = self._extract_goals(user_input)
            if new_goals:
                learned["goals"] = new_goals

        # 7. Preferences
        if self.privacy.allow("track_preferences"):
            new_prefs = self._extract_preferences(user_input)
            if new_prefs:
                learned["preferences"] = new_prefs

        # 8. Corrections
        if self.privacy.allow("track_corrections"):
            correction = self._detect_correction(user_input)
            if correction:
                learned["correction"] = correction.category

        # 9. Project context
        if self.privacy.allow("track_projects"):
            self._extract_project_context(user_input, response)

        # 10. Tool usage tracking
        if user_input.startswith(("!", "/", ">")):
            tool = user_input.split()[0].lstrip("!/>")
            self.interests.tools_used[tool] += 1

        # Auto-save
        self._dirty_count += 1
        if self._dirty_count >= SAVE_INTERVAL:
            self.save()

        return learned

    # ───────────────────────────────────────────────────────
    # Extraction Methods
    # ───────────────────────────────────────────────────────

    def _extract_goals(self, text: str) -> List[str]:
        """Extract goal/intention statements from text."""
        patterns = [
            (r"i want to (.+?)(?:\.|$|,)", "active"),
            (r"i need to (.+?)(?:\.|$|,)", "active"),
            (r"my goal is (.+?)(?:\.|$)", "active"),
            (r"i'm working on (.+?)(?:\.|$)", "active"),
            (r"i'm building (.+?)(?:\.|$)", "active"),
            (r"i plan to (.+?)(?:\.|$)", "planned"),
            (r"hoping to (.+?)(?:\.|$)", "aspirational"),
        ]
        now = datetime.now().isoformat()
        found: List[str] = []

        for pattern, status in patterns:
            for match in re.findall(pattern, text.lower()):
                goal_text = match.strip()[:200]
                # Deduplicate: skip if similar goal exists
                if any(g.text.lower() == goal_text for g in self.goals):
                    continue
                goal = Goal(
                    goal_id=f"g_{int(time.time()*1000)}",
                    text=goal_text,
                    status=status,
                    created_at=now,
                    updated_at=now,
                )
                self.goals.append(goal)
                found.append(goal_text)

        # Trim
        if len(self.goals) > MAX_GOALS:
            # Keep completed goals separately, trim active
            active = [g for g in self.goals if g.status == "active"]
            inactive = [g for g in self.goals if g.status != "active"]
            self.goals = active[-MAX_GOALS//2:] + inactive[-MAX_GOALS//2:]

        return found

    def _extract_preferences(self, text: str) -> List[str]:
        """Extract explicit preference statements."""
        patterns = [
            r"i prefer (.+?)(?:\.|$|,)",
            r"i(?:'d)? like (.+?)(?:\.|$|,)",
            r"i love (.+?)(?:\.|$|,)",
            r"my favorite (.+?) is (.+?)(?:\.|$)",
            r"i always (.+?)(?:\.|$)",
            r"i usually (.+?)(?:\.|$)",
            r"don'?t (?:ever )?(.+?)(?:\.|$)",
            r"please (?:always |never )?(.+?)(?:\.|$)",
        ]
        now = datetime.now().isoformat()
        found: List[str] = []

        for pattern in patterns:
            for match in re.findall(pattern, text.lower()):
                pref_text = match.strip()[:200] if isinstance(match, str) else match[0].strip()[:200]
                if pref_text and len(pref_text) > 3:
                    self.preferences.append({
                        "text": pref_text,
                        "timestamp": now,
                        "source": "explicit",
                    })
                    found.append(pref_text)

        return found

    def _detect_correction(self, text: str) -> Optional[Correction]:
        """Detect if the user is correcting the agent."""
        correction_patterns = [
            (r"^(no|nah|wrong|incorrect)[,.]?\s*(.+)", "factual"),
            (r"^actually[,.]?\s*(.+)", "factual"),
            (r"that'?s (?:not |wrong|incorrect)", "factual"),
            (r"i (?:meant|mean) (.+)", "clarification"),
            (r"what i (?:really )?(?:want|need|meant) (?:is|was) (.+)", "preference"),
            (r"(?:can you|please) (?:stop|don't) (.+)", "behavior"),
            (r"not quite[,.]?\s*(.+)", "factual"),
            (r"let me (?:clarify|rephrase)[,:]? (.+)", "clarification"),
        ]
        now = datetime.now().isoformat()

        text_lower = text.lower().strip()
        for pattern, category in correction_patterns:
            m = re.search(pattern, text_lower)
            if m:
                corrected = m.group(m.lastindex or 1).strip()[:300] if m.lastindex else text[:300]
                correction = Correction(
                    correction_id=f"c_{int(time.time()*1000)}",
                    original_text=text[:300],
                    corrected_text=corrected,
                    category=category,
                    timestamp=now,
                )
                self.corrections.append(correction)
                return correction

        return None

    def _extract_project_context(self, text: str, response: str) -> None:
        """Detect and track active project context."""
        combined = f"{text} {response}".lower()

        # Detect project mentions
        project_patterns = [
            r"(?:project|repo|repository)\s+['\"]?(\w[\w\-]+)['\"]?",
            r"(?:working on|building|developing)\s+(.+?)(?:\.|$|,)",
            r"(?:in|at|from)\s+(?:the\s+)?(\w[\w\-]+)\s+(?:project|repo)",
        ]

        now = datetime.now().isoformat()
        for pattern in project_patterns:
            for match in re.findall(pattern, combined):
                name = match.strip()[:100]
                if len(name) < 3:
                    continue
                # Find existing or create new
                existing = next((p for p in self.projects if p.name.lower() == name.lower()), None)
                if existing:
                    existing.last_discussed = now
                else:
                    self.projects.append(ProjectContext(
                        project_id=f"p_{int(time.time()*1000)}",
                        name=name,
                        last_discussed=now,
                        created_at=now,
                    ))

        # Extract tech stack mentions
        for proj in self.projects:
            if proj.status != "active":
                continue
            for lang in self.interests.LANG_PATTERNS:
                if re.search(self.interests.LANG_PATTERNS[lang], combined):
                    if lang not in proj.tech_stack:
                        proj.tech_stack.append(lang)

    # ───────────────────────────────────────────────────────
    # Goal Management
    # ───────────────────────────────────────────────────────

    def update_goal(self, goal_id: str, **kwargs) -> bool:
        """Update a goal's properties."""
        goal = next((g for g in self.goals if g.goal_id == goal_id), None)
        if not goal:
            return False
        for key, value in kwargs.items():
            if hasattr(goal, key):
                setattr(goal, key, value)
        goal.updated_at = datetime.now().isoformat()
        if kwargs.get("status") == "completed":
            goal.completed_at = datetime.now().isoformat()
            goal.progress = 1.0
        return True

    def complete_goal(self, goal_id: str) -> bool:
        return self.update_goal(goal_id, status="completed", progress=1.0)

    def add_goal_milestone(self, goal_id: str, milestone: str) -> bool:
        goal = next((g for g in self.goals if g.goal_id == goal_id), None)
        if not goal:
            return False
        goal.milestones.append({
            "text": milestone,
            "timestamp": datetime.now().isoformat(),
            "completed": False,
        })
        return True

    @property
    def active_goals(self) -> List[Goal]:
        return [g for g in self.goals if g.status == "active"]

    # ───────────────────────────────────────────────────────
    # Context Generation (for LLM injection)
    # ───────────────────────────────────────────────────────

    def get_context_prompt(self) -> str:
        """Generate a rich context prompt about the user for the LLM.

        This is injected into every conversation so the AI always knows
        who it's talking to.
        """
        parts: List[str] = []

        # Identity
        if self.name:
            parts.append(f"User's name: {self.name}")
        if self.timezone:
            parts.append(f"Timezone: {self.timezone}")

        # Communication style
        style = self.communication_style
        if style._sample_count > 5:
            parts.append(f"Communication style: {style.style_label}")
            if style.avg_message_length > 0:
                parts.append(f"  Avg message: {style.avg_message_length:.0f} words")

        # Personality (top traits with confidence)
        top = self.personality.top_traits(5)
        if top:
            traits = [f"{t} ({s.score:.0%})" for t, s in top if s.confidence > 0.2]
            if traits:
                parts.append(f"Personality: {', '.join(traits)}")

        # Dominant mood
        mood = self.emotions.dominant_mood
        if mood != "neutral":
            avg_v = self.emotions.avg_valence
            mood_desc = f"{mood} (valence: {avg_v:+.2f})"
            parts.append(f"Recent mood: {mood_desc}")

        # Top interests
        top_topics = self.interests.top_topics(5)
        if top_topics:
            topics_str = ", ".join(t for t, _ in top_topics)
            parts.append(f"Top interests: {topics_str}")

        # Programming languages
        if self.interests.languages:
            top_langs = sorted(
                self.interests.languages.items(),
                key=lambda x: x[1].weighted_score,
                reverse=True,
            )[:5]
            langs = [f"{l} ({v.raw_count}x)" for l, v in top_langs]
            parts.append(f"Languages: {', '.join(langs)}")

        # Frameworks
        if self.interests.frameworks:
            top_fw = sorted(
                self.interests.frameworks.items(),
                key=lambda x: x[1].weighted_score,
                reverse=True,
            )[:3]
            fws = [f for f, _ in top_fw]
            parts.append(f"Frameworks: {', '.join(fws)}")

        # Active projects
        active_projects = [p for p in self.projects if p.status == "active"]
        if active_projects:
            proj_strs = []
            for p in active_projects[:3]:
                tech = f" [{', '.join(p.tech_stack)}]" if p.tech_stack else ""
                proj_strs.append(f"{p.name}{tech}")
            parts.append(f"Active projects: {'; '.join(proj_strs)}")

        # Active goals
        if self.active_goals:
            goal_strs = []
            for g in self.active_goals[:3]:
                progress = f" ({g.progress:.0%})" if g.progress > 0 else ""
                deadline = f" by {g.deadline}" if g.deadline else ""
                goal_strs.append(f"{g.text[:60]}{progress}{deadline}")
            parts.append(f"Current goals: {'; '.join(goal_strs)}")

        # Recent preferences
        if self.preferences:
            recent = self.preferences[-3:]
            prefs = [p.get("text", "")[:60] for p in recent if p.get("text")]
            if prefs:
                parts.append(f"Preferences: {'; '.join(prefs)}")

        # Recent corrections
        if self.corrections:
            recent_corr = self.corrections[-2:]
            corrs = [f"{c.category}: {c.corrected_text[:50]}" for c in recent_corr]
            if corrs:
                parts.append(f"Recent corrections: {'; '.join(corrs)}")

        # Activity patterns
        peaks = self.routines.peak_hours
        if peaks:
            parts.append(f"Active hours: {', '.join(f'{h}:00' for h in peaks)}")

        if not parts:
            return "No user model data yet. Learning from interactions..."

        return "\n".join(parts)

    # ───────────────────────────────────────────────────────
    # Dashboard & Visualization
    # ───────────────────────────────────────────────────────

    def get_profile_dashboard(self) -> Dict[str, Any]:
        """Generate a full profile dashboard for the web UI."""
        return {
            "identity": {
                "name": self.name,
                "timezone": self.timezone,
                "language": self.language,
                "created_at": self.created_at,
                "last_active": self.last_active,
                "interaction_count": self.interaction_count,
            },
            "personality": {
                "traits": {k: v.to_dict() for k, v in self.personality.traits.items()},
                "top_traits": [(t, s.to_dict()) for t, s in self.personality.top_traits(8)],
            },
            "communication_style": self.communication_style.to_dict(),
            "interests": {
                "topics": {k: v.to_dict() for k, v in self.interests.topics.items()},
                "languages": {k: v.to_dict() for k, v in self.interests.languages.items()},
                "frameworks": {k: v.to_dict() for k, v in self.interests.frameworks.items()},
                "top_topics": self.interests.top_topics(10),
                "keywords": dict(self.interests.keywords.most_common(30)),
            },
            "routines": {
                "hourly_activity": dict(self.routines.hourly_activity),
                "daily_activity": dict(self.routines.daily_activity),
                "peak_hours": self.routines.peak_hours,
                "avg_session_minutes": round(self.routines.avg_session_minutes, 1),
                "top_commands": dict(self.routines.common_commands.most_common(10)),
            },
            "emotions": {
                "dominant_mood": self.emotions.dominant_mood,
                "avg_valence": round(self.emotions.avg_valence, 3),
                "emotion_distribution": dict(self.emotions.emotion_counts),
                "recent_history": [s.to_dict() for s in self.emotions.history[-20:]],
            },
            "goals": {
                "active": [g.to_dict() for g in self.active_goals],
                "completed": [g.to_dict() for g in self.goals if g.status == "completed"][-10:],
                "total_active": len(self.active_goals),
                "total_completed": len([g for g in self.goals if g.status == "completed"]),
            },
            "projects": [p.to_dict() for p in self.projects if p.status == "active"],
            "preferences_count": len(self.preferences),
            "corrections_count": len(self.corrections),
            "privacy": self.privacy.to_dict(),
        }

    def get_profile_summary(self) -> str:
        """Get a human-readable profile summary."""
        lines: List[str] = []
        lines.append(f"👤 **User Profile — Digital Twin**")
        lines.append(f"📊 Interactions: {self.interaction_count}")
        lines.append(f"📅 Since: {self.created_at[:10]}")

        if self.name:
            lines.append(f"📛 Name: {self.name}")

        # Communication style
        style = self.communication_style
        if style._sample_count > 3:
            lines.append(f"\n💬 **Communication**")
            lines.append(f"  Style: {style.style_label}")
            lines.append(f"  Avg message: {style.avg_message_length:.0f} words")
            lines.append(f"  Questions: {style.question_ratio:.0%} of messages")
            if style.code_ratio > 0.1:
                lines.append(f"  Code-heavy: {style.code_ratio:.0%}")

        # Personality
        top = self.personality.top_traits(5)
        if top:
            lines.append(f"\n🧠 **Personality**")
            for trait, ts in top:
                if ts.confidence > 0.1:
                    bar = "█" * int(ts.score * 10) + "░" * (10 - int(ts.score * 10))
                    lines.append(f"  {trait}: {bar} {ts.score:.0%} (conf: {ts.confidence:.0%})")

        # Interests
        top_topics = self.interests.top_topics(5)
        if top_topics:
            lines.append(f"\n🎯 **Top Interests**")
            for topic, score in top_topics:
                lines.append(f"  • {topic}: {score:.1f}")

        # Languages & Frameworks
        if self.interests.languages:
            lines.append(f"\n💻 **Languages**")
            for lang, tw in sorted(self.interests.languages.items(), key=lambda x: x[1].weighted_score, reverse=True)[:5]:
                lines.append(f"  • {lang}: {tw.raw_count} mentions")

        if self.interests.frameworks:
            lines.append(f"\n🔧 **Frameworks**")
            for fw, tw in sorted(self.interests.frameworks.items(), key=lambda x: x[1].weighted_score, reverse=True)[:5]:
                lines.append(f"  • {fw}: {tw.raw_count} mentions")

        # Goals
        if self.active_goals:
            lines.append(f"\n🎯 **Active Goals** ({len(self.active_goals)})")
            for g in self.active_goals[:5]:
                progress = f" [{g.progress:.0%}]" if g.progress > 0 else ""
                lines.append(f"  • {g.text[:70]}{progress}")

        # Projects
        active_proj = [p for p in self.projects if p.status == "active"]
        if active_proj:
            lines.append(f"\n📂 **Active Projects**")
            for p in active_proj[:3]:
                tech = f" ({', '.join(p.tech_stack)})" if p.tech_stack else ""
                lines.append(f"  • {p.name}{tech}")

        # Emotions
        mood = self.emotions.dominant_mood
        if mood != "neutral":
            lines.append(f"\n💭 **Mood**: {mood} (valence: {self.emotions.avg_valence:+.2f})")

        # Routines
        peaks = self.routines.peak_hours
        if peaks:
            lines.append(f"\n⏰ **Active Hours**: {', '.join(f'{h}:00' for h in peaks)}")

        # Corrections
        if self.corrections:
            lines.append(f"\n📝 **Corrections**: {len(self.corrections)} total")
            cats = Counter(c.category for c in self.corrections)
            for cat, count in cats.most_common(3):
                lines.append(f"  • {cat}: {count}")

        return "\n".join(lines)

    def get_stats(self) -> Dict[str, Any]:
        """Quick stats overview."""
        return {
            "interactions": self.interaction_count,
            "topics_tracked": len(self.interests.topics),
            "languages_tracked": len(self.interests.languages),
            "frameworks_tracked": len(self.interests.frameworks),
            "personality_traits": len(self.personality.traits),
            "active_goals": len(self.active_goals),
            "total_goals": len(self.goals),
            "preferences": len(self.preferences),
            "corrections": len(self.corrections),
            "projects": len(self.projects),
            "emotions_recorded": len(self.emotions.history),
        }

    # ───────────────────────────────────────────────────────
    # Export / Import
    # ───────────────────────────────────────────────────────

    def export_profile(self, path: Optional[str] = None) -> str:
        """Export full profile to JSON. Returns the file path."""
        export_path = path or os.path.join(self.data_dir, "user_profile_export.json")
        data = self.get_profile_dashboard()
        data["exported_at"] = datetime.now().isoformat()
        data["schema_version"] = 2
        with open(export_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return export_path

    def import_profile(self, path: str) -> int:
        """Import a profile from JSON. Returns number of fields imported."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        imported = 0
        # Identity
        for key in ("name", "timezone", "language"):
            if key in data.get("identity", data):
                setattr(self, key, data["identity"].get(key, data.get(key, "")))
                imported += 1

        # Personality
        if "personality" in data:
            for trait, tdata in data["personality"].get("traits", {}).items():
                self.personality.traits[trait] = TraitScore.from_dict(tdata)
                imported += 1

        # Communication style
        if "communication_style" in data:
            self.communication_style = CommunicationStyleAnalyzer.from_dict(data["communication_style"])
            imported += 1

        # Interests
        if "interests" in data:
            for k, v in data["interests"].get("topics", {}).items():
                self.interests.topics[k] = TopicWeight.from_dict(v)
                imported += 1
            for k, v in data["interests"].get("languages", {}).items():
                self.interests.languages[k] = TopicWeight.from_dict(v)
                imported += 1

        # Goals
        if "goals" in data:
            for g in data["goals"].get("active", []):
                self.goals.append(Goal.from_dict(g))
                imported += 1

        self.save()
        return imported

    # ───────────────────────────────────────────────────────
    # Privacy: Forget & Purge
    # ───────────────────────────────────────────────────────

    def forget_topic(self, topic: str) -> None:
        """Remove a topic from all tracking."""
        topic_lower = topic.lower()
        self.privacy.forget(topic_lower)

        # Purge existing data
        self.interests.topics.pop(topic_lower, None)
        self.interests.languages.pop(topic_lower, None)
        self.interests.frameworks.pop(topic_lower, None)

        # Remove related keywords
        to_remove = [k for k in self.interests.keywords if topic_lower in k]
        for k in to_remove:
            del self.interests.keywords[k]

        self.save()

    def purge_all(self) -> None:
        """Delete all learned data. Nuclear option."""
        self.personality = PersonalityProfiler()
        self.communication_style = CommunicationStyleAnalyzer()
        self.interests = InterestTracker()
        self.routines = RoutineDetector()
        self.emotions = EmotionalDetector()
        self.goals.clear()
        self.corrections.clear()
        self.preferences.clear()
        self.projects.clear()
        self.notes.clear()
        self.interaction_count = 0
        self.save()
        logger.warning("UserModel: all data purged")

    # ───────────────────────────────────────────────────────
    # Lifecycle
    # ───────────────────────────────────────────────────────

    def shutdown(self) -> None:
        """Clean shutdown — save everything."""
        self.routines.end_session()
        self.save()
        logger.info("UserModel: shutdown complete")
