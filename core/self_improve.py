"""
🟣 Rally Agent — Self-Improvement Engine
==========================================
Learns from EVERY interaction. Captures corrections, preferences,
failures, and successes to build an ever-growing expertise profile.

Features:
  - Correction detection & learning
  - Preference extraction & tracking
  - Failure/success pattern mining
  - Knowledge graph (entities + relationships)
  - Expertise profile building
  - Conversation quality metrics
  - Confidence scoring
  - Improvement report generation
  - Auto-behaviour adjustment
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import time
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

logger = logging.getLogger("rally.self_improve")


# ═══════════════════════════════════════════════════════════════
# 📐 Data Models
# ═══════════════════════════════════════════════════════════════

class LearningType(str, Enum):
    CORRECTION  = "correction"
    PREFERENCE  = "preference"
    FAILURE     = "failure"
    SUCCESS     = "success"
    PATTERN     = "pattern"
    FEEDBACK    = "feedback"


class ConfidenceLevel(str, Enum):
    LOW      = "low"        # 0.0 – 0.3
    MEDIUM   = "medium"     # 0.3 – 0.6
    HIGH     = "high"       # 0.6 – 0.85
    CERTAIN  = "certain"    # 0.85 – 1.0


@dataclass
class Learning:
    """A single learning entry — the atomic unit of improvement."""
    learning_id: str
    timestamp: float
    learning_type: LearningType
    category: str               # e.g. "coding.style", "factual.history"
    content: str                # what was learned
    context: str                # surrounding conversation / trigger
    confidence: float           # 0.0 – 1.0
    source: str                 # "user", "self", "inferred"
    occurrences: int = 1
    last_seen: float = 0.0
    applied_count: int = 0
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["learning_type"] = self.learning_type.value
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Learning":
        data = dict(data)
        data["learning_type"] = LearningType(data["learning_type"])
        return cls(**data)


@dataclass
class Preference:
    """A tracked user preference."""
    key: str                    # e.g. "language", "theme", "code_style"
    value: Any                  # e.g. "python", "dark", "pep8"
    confidence: float           # 0.0 – 1.0
    source: str                 # "explicit", "inferred", "corrected"
    occurrences: int = 1
    first_seen: float = 0.0
    last_seen: float = 0.0
    examples: List[str] = field(default_factory=list)  # supporting quotes

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Preference":
        return cls(**data)


@dataclass
class ExpertiseArea:
    """A domain of expertise the agent has built up."""
    domain: str                 # e.g. "python", "devops", "design"
    level: float                # 0.0 – 1.0
    interactions: int = 0
    successes: int = 0
    failures: int = 0
    topics: List[str] = field(default_factory=list)
    last_interaction: float = 0.0
    notes: List[str] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        total = self.successes + self.failures
        return self.successes / total if total > 0 else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExpertiseArea":
        return cls(**data)


@dataclass
class KnowledgeNode:
    """A node in the knowledge graph."""
    node_id: str
    label: str                  # display name
    entity_type: str            # "person", "tool", "concept", "project", …
    properties: Dict[str, Any] = field(default_factory=dict)
    first_seen: float = 0.0
    last_seen: float = 0.0
    mention_count: int = 1


@dataclass
class KnowledgeEdge:
    """A directed edge in the knowledge graph."""
    source_id: str
    target_id: str
    relation: str               # "uses", "knows", "created", "related_to", …
    weight: float = 1.0
    first_seen: float = 0.0
    last_seen: float = 0.0


@dataclass
class ConversationMetrics:
    """Quality metrics for a single conversation turn."""
    turn_id: str
    timestamp: float
    user_message: str
    agent_response: str
    response_time_ms: float
    token_count: int = 0
    tools_used: List[str] = field(default_factory=list)
    quality_score: float = 0.0   # 0.0 – 1.0
    user_satisfied: Optional[bool] = None
    corrections_received: int = 0
    topics: List[str] = field(default_factory=list)


@dataclass
class ImprovementReport:
    """Periodic improvement summary."""
    report_id: str
    period_start: float
    period_end: float
    learnings_count: int = 0
    corrections_applied: int = 0
    preferences_updated: int = 0
    expertise_changes: Dict[str, float] = field(default_factory=dict)
    top_patterns: List[str] = field(default_factory=list)
    quality_trend: float = 0.0  # positive = improving
    recommendations: List[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════
# 🔍 Correction & Preference Detectors
# ═══════════════════════════════════════════════════════════════

# Patterns that signal a user correction
_CORRECTION_PATTERNS: List[re.Pattern] = [
    re.compile(r"\bno[,.]?\s*(that'?s?\s*)?(not|wrong|incorrect|bad)\b", re.I),
    re.compile(r"\bactually[,.]?\s*", re.I),
    re.compile(r"\b(please\s+)?(fix|correct|change)\s+(it|that|this)\b", re.I),
    re.compile(r"\bthat'?s?\s*(not\s+)?(right|correct|what\s+i\s+meant)\b", re.I),
    re.compile(r"\bi\s+(meant|mean|said)\s+", re.I),
    re.compile(r"\b(don'?t|do\s+not)\s+(do|use|say|write)\s+(it\s+)?that\s+way\b", re.I),
    re.compile(r"\binstead\s+of\b", re.I),
    re.compile(r"\btry\s+(again|doing)\b", re.I),
    re.compile(r"\bwrong\b", re.I),
    re.compile(r"\bnope\b", re.I),
]

# Patterns that signal a preference statement
_PREFERENCE_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"\bi\s+prefer\s+(.+?)(?:\.|$)", re.I), "preference"),
    (re.compile(r"\bmy\s+preferred?\s+(.+?)\s+(?:is|are)\s+(.+?)(?:\.|$)", re.I), "preference"),
    (re.compile(r"\buse\s+(\w+)\s+not\s+(\w+)\b", re.I), "preference"),
    (re.compile(r"\b(always|never)\s+(use|do|write|say)\s+(.+?)(?:\.|$)", re.I), "preference"),
    (re.compile(r"\bi\s+(like|love|hate|dislike)\s+(.+?)(?:\.|$)", re.I), "preference"),
    (re.compile(r"\bpreference:\s*(.+?)(?:\.|$)", re.I), "preference"),
    (re.compile(r"\bdefault\s+(?:to|should\s+be)\s+(.+?)(?:\.|$)", re.I), "preference"),
]


def detect_correction(message: str) -> Optional[Dict[str, str]]:
    """Detect if a message is correcting the agent.

    Returns {"detected": True, "category": "…", "raw": "…"} or None.
    """
    for pattern in _CORRECTION_PATTERNS:
        if pattern.search(message):
            return {
                "detected": True,
                "category": "correction",
                "raw": message,
            }
    return None


def detect_preferences(message: str) -> List[Dict[str, str]]:
    """Extract preference statements from a message."""
    found: List[Dict[str, str]] = []
    for pattern, category in _PREFERENCE_PATTERNS:
        m = pattern.search(message)
        if m:
            found.append({
                "category": category,
                "match": m.group(0),
                "value": m.group(m.lastindex) if m.lastindex else m.group(0),
                "raw": message,
            })
    return found


# Entity extraction (lightweight, no NLP library required)
_ENTITY_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b"), "person"),
    (re.compile(r"\b(python|javascript|typescript|rust|go|java|c\+\+|ruby|swift|kotlin)\b", re.I), "language"),
    (re.compile(r"\b(docker|kubernetes|k8s|nginx|redis|postgres|mysql|mongodb|aws|gcp|azure)\b", re.I), "tool"),
    (re.compile(r"\b(rally|openai|anthropic|google|microsoft|github|gitlab)\b", re.I), "org"),
]


def extract_entities(text: str) -> List[Dict[str, str]]:
    """Extract named entities from text."""
    entities: List[Dict[str, str]] = []
    seen: Set[str] = set()
    for pattern, etype in _ENTITY_PATTERNS:
        for m in pattern.finditer(text):
            label = m.group(1) if m.lastindex else m.group(0)
            key = f"{etype}:{label.lower()}"
            if key not in seen:
                seen.add(key)
                entities.append({"label": label, "type": etype})
    return entities


# ═══════════════════════════════════════════════════════════════
# 🧠 Self-Improvement Engine
# ═══════════════════════════════════════════════════════════════

class SelfImprovementEngine:
    """The brain that learns from every interaction.

    Persists all data to ~/.rally-agent/data/self_improve/.
    """

    def __init__(
        self,
        data_dir: Union[str, Path] = "~/.rally-agent/data/self_improve",
    ) -> None:
        self._data_dir = Path(data_dir).expanduser()
        self._data_dir.mkdir(parents=True, exist_ok=True)

        # ── Storage ──────────────────────────────────────────
        self._learnings: List[Learning] = []
        self._preferences: Dict[str, Preference] = {}
        self._expertise: Dict[str, ExpertiseArea] = {}
        self._knowledge_nodes: Dict[str, KnowledgeNode] = {}
        self._knowledge_edges: List[KnowledgeEdge] = []
        self._metrics: List[ConversationMetrics] = []
        self._reports: List[ImprovementReport] = []

        # ── Load persisted data ──────────────────────────────
        self._load_all()

        logger.info(
            "SelfImprovementEngine loaded: %d learnings, %d prefs, %d expertise, "
            "%d kg nodes, %d metrics",
            len(self._learnings), len(self._preferences),
            len(self._expertise), len(self._knowledge_nodes),
            len(self._metrics),
        )

    # ═════════════════════════════════════════════════════════
    # 📥 Ingest — Process Each Interaction
    # ═════════════════════════════════════════════════════════

    def on_interaction(
        self,
        user_message: str,
        agent_response: str,
        *,
        tools_used: Optional[List[str]] = None,
        response_time_ms: float = 0.0,
        token_count: int = 0,
        user_satisfied: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Process a single user↔agent interaction and learn from it.

        Call this after every turn. Returns a summary of what was learned.
        """
        now = time.time()
        learned: List[str] = []

        # 1. Detect corrections
        correction = detect_correction(user_message)
        if correction:
            self._learn_correction(user_message, agent_response, now)
            learned.append("correction")

        # 2. Detect preferences
        prefs = detect_preferences(user_message)
        for p in prefs:
            self._learn_preference(p, now)
            learned.append(f"preference:{p.get('value', '')[:30]}")

        # 3. Extract entities for knowledge graph
        entities = extract_entities(user_message + " " + agent_response)
        self._update_knowledge_graph(entities, now)

        # 4. Record conversation metrics
        turn_id = uuid.uuid4().hex[:10]
        topics = [e["label"] for e in entities[:5]]
        quality = self._score_quality(
            user_message, agent_response, response_time_ms, user_satisfied
        )
        metrics = ConversationMetrics(
            turn_id=turn_id,
            timestamp=now,
            user_message=user_message[:500],
            agent_response=agent_response[:500],
            response_time_ms=response_time_ms,
            token_count=token_count,
            tools_used=tools_used or [],
            quality_score=quality,
            user_satisfied=user_satisfied,
            corrections_received=1 if correction else 0,
            topics=topics,
        )
        self._metrics.append(metrics)
        # Keep last 5000 metrics
        if len(self._metrics) > 5000:
            self._metrics = self._metrics[-5000:]

        # 5. Update expertise based on topics
        for topic in topics:
            self._update_expertise(topic, quality, now)

        # 6. Auto-detect patterns
        self._detect_patterns(now)

        # 7. Persist
        self._save_all()

        return {
            "learned": learned,
            "quality_score": quality,
            "entities_found": len(entities),
            "total_learnings": len(self._learnings),
        }

    def on_feedback(
        self,
        turn_id: str,
        positive: bool,
        comment: Optional[str] = None,
    ) -> None:
        """Record explicit user feedback on a turn."""
        # Update the metrics record
        for m in self._metrics:
            if m.turn_id == turn_id:
                m.user_satisfied = positive
                break

        # If negative feedback on a recent turn, treat as implicit correction
        if not positive and comment:
            now = time.time()
            self._learn_correction(comment, "", now, source="feedback")
        self._save_all()

    # ═════════════════════════════════════════════════════════
    # 📝 Learning Capture
    # ═════════════════════════════════════════════════════════

    def _learn_correction(
        self,
        user_message: str,
        agent_response: str,
        now: float,
        source: str = "user",
    ) -> Learning:
        """Record a correction learning."""
        # Try to extract what was wrong and what's right
        category = "general"
        content = user_message

        # Categorise
        msg_lower = user_message.lower()
        if any(w in msg_lower for w in ["code", "function", "bug", "error", "syntax"]):
            category = "coding"
        elif any(w in msg_lower for w in ["style", "format", "indent", "prettier"]):
            category = "style"
        elif any(w in msg_lower for w in ["fact", "wrong", "actually", "incorrect"]):
            category = "factual"
        elif any(w in msg_lower for w in ["prefer", "like", "want", "use"]):
            category = "preference"

        learning = Learning(
            learning_id=uuid.uuid4().hex[:12],
            timestamp=now,
            learning_type=LearningType.CORRECTION,
            category=category,
            content=content[:500],
            context=agent_response[:500],
            confidence=0.9,  # corrections are high-confidence
            source=source,
            tags=[category],
        )
        self._learnings.append(learning)

        # Check for duplicates → boost confidence instead of adding
        self._deduplicate_learning(learning)

        logger.info("Learned correction [%s]: %s", category, content[:100])
        return learning

    def _learn_preference(self, pref_data: Dict[str, str], now: float) -> None:
        """Record or update a user preference."""
        value = pref_data.get("value", "").strip()
        if not value or len(value) > 200:
            return

        # Derive a key from the value
        key = self._derive_preference_key(pref_data.get("raw", ""), value)
        raw = pref_data.get("raw", "")

        if key in self._preferences:
            pref = self._preferences[key]
            pref.occurrences += 1
            pref.last_seen = now
            pref.confidence = min(1.0, pref.confidence + 0.1)
            if len(pref.examples) < 10:
                pref.examples.append(raw[:200])
            # Update value if different and new one mentioned more recently
            if value.lower() != str(pref.value).lower():
                pref.value = value
                pref.source = "corrected"
        else:
            self._preferences[key] = Preference(
                key=key,
                value=value,
                confidence=0.6,
                source="inferred",
                occurrences=1,
                first_seen=now,
                last_seen=now,
                examples=[raw[:200]],
            )

        # Also record as a learning
        learning = Learning(
            learning_id=uuid.uuid4().hex[:12],
            timestamp=now,
            learning_type=LearningType.PREFERENCE,
            category="preference",
            content=f"User prefers: {key} = {value}",
            context=raw[:500],
            confidence=self._preferences[key].confidence,
            source="user",
            tags=["preference", key],
        )
        self._learnings.append(learning)

        logger.info("Learned preference: %s = %s (confidence=%.2f)", key, value, self._preferences[key].confidence)

    def learn_from_failure(
        self,
        description: str,
        error: str,
        context: str = "",
        category: str = "general",
    ) -> Learning:
        """Explicitly record a failure for future improvement."""
        now = time.time()
        learning = Learning(
            learning_id=uuid.uuid4().hex[:12],
            timestamp=now,
            learning_type=LearningType.FAILURE,
            category=category,
            content=f"FAILURE: {description}\nError: {error}",
            context=context[:500],
            confidence=0.8,
            source="self",
            tags=["failure", category],
        )
        self._learnings.append(learning)
        self._save_all()
        logger.warning("Learned from failure [%s]: %s", category, description[:100])
        return learning

    def learn_from_success(
        self,
        description: str,
        context: str = "",
        category: str = "general",
    ) -> Learning:
        """Record a success pattern for reinforcement."""
        now = time.time()
        learning = Learning(
            learning_id=uuid.uuid4().hex[:12],
            timestamp=now,
            learning_type=LearningType.SUCCESS,
            category=category,
            content=f"SUCCESS: {description}",
            context=context[:500],
            confidence=0.7,
            source="self",
            tags=["success", category],
        )
        self._learnings.append(learning)
        self._save_all()
        logger.info("Learned from success [%s]: %s", category, description[:100])
        return learning

    # ═════════════════════════════════════════════════════════
    # 🔎 Pattern Detection
    # ═════════════════════════════════════════════════════════

    def _detect_patterns(self, now: float) -> None:
        """Auto-extract recurring patterns from recent learnings."""
        window = 86400 * 7  # last 7 days
        recent = [l for l in self._learnings if now - l.timestamp < window]
        if len(recent) < 5:
            return

        # Category frequency
        categories = Counter(l.category for l in recent)
        for cat, count in categories.most_common(3):
            if count >= 3:
                # Check if we already have this pattern
                existing = [
                    l for l in self._learnings
                    if l.learning_type == LearningType.PATTERN
                    and l.category == f"pattern:{cat}"
                ]
                if not existing:
                    pattern = Learning(
                        learning_id=uuid.uuid4().hex[:12],
                        timestamp=now,
                        learning_type=LearningType.PATTERN,
                        category=f"pattern:{cat}",
                        content=f"Recurring category: '{cat}' ({count} times in 7d)",
                        context="",
                        confidence=min(1.0, count / 10),
                        source="inferred",
                        tags=["pattern", cat],
                    )
                    self._learnings.append(pattern)
                    logger.info("Detected pattern: %s (%d occurrences)", cat, count)

        # Correction clusters (same area corrected multiple times)
        corrections = [l for l in recent if l.learning_type == LearningType.CORRECTION]
        correction_cats = Counter(l.category for l in corrections)
        for cat, count in correction_cats.items():
            if count >= 3:
                existing = [
                    l for l in self._learnings
                    if l.learning_type == LearningType.PATTERN
                    and l.category == f"repeated_correction:{cat}"
                ]
                if not existing:
                    pattern = Learning(
                        learning_id=uuid.uuid4().hex[:12],
                        timestamp=now,
                        learning_type=LearningType.PATTERN,
                        category=f"repeated_correction:{cat}",
                        content=f"Repeatedly corrected in '{cat}' ({count}x in 7d). Needs focused improvement.",
                        context="",
                        confidence=min(1.0, count / 5),
                        source="inferred",
                        tags=["pattern", "correction", cat],
                    )
                    self._learnings.append(pattern)

    # ═════════════════════════════════════════════════════════
    # 📊 Quality Scoring
    # ═════════════════════════════════════════════════════════

    @staticmethod
    def _score_quality(
        user_message: str,
        agent_response: str,
        response_time_ms: float,
        user_satisfied: Optional[bool],
    ) -> float:
        """Score the quality of a response (0.0 – 1.0)."""
        score = 0.5  # baseline

        # Length appropriateness (not too short, not too long)
        resp_len = len(agent_response)
        if resp_len > 20:
            score += 0.05
        if resp_len > 100:
            score += 0.05
        if resp_len > 5000:
            score -= 0.1  # probably too verbose

        # Response speed
        if response_time_ms < 2000:
            score += 0.1
        elif response_time_ms < 5000:
            score += 0.05
        elif response_time_ms > 30000:
            score -= 0.1

        # Explicit feedback overrides
        if user_satisfied is True:
            score += 0.3
        elif user_satisfied is False:
            score -= 0.3

        return max(0.0, min(1.0, score))

    # ═════════════════════════════════════════════════════════
    # 🌐 Knowledge Graph
    # ═════════════════════════════════════════════════════════

    def _update_knowledge_graph(self, entities: List[Dict[str, str]], now: float) -> None:
        """Add entities and co-occurrence edges to the knowledge graph."""
        node_ids: List[str] = []

        for ent in entities:
            node_id = self._entity_to_id(ent["label"], ent["type"])
            if node_id in self._knowledge_nodes:
                node = self._knowledge_nodes[node_id]
                node.mention_count += 1
                node.last_seen = now
            else:
                self._knowledge_nodes[node_id] = KnowledgeNode(
                    node_id=node_id,
                    label=ent["label"],
                    entity_type=ent["type"],
                    first_seen=now,
                    last_seen=now,
                )
            node_ids.append(node_id)

        # Create co-occurrence edges
        for i, src in enumerate(node_ids):
            for dst in node_ids[i + 1:]:
                self._add_edge(src, dst, "co_mentioned", now)

    def _add_edge(self, source: str, target: str, relation: str, now: float) -> None:
        """Add or strengthen an edge in the knowledge graph."""
        for edge in self._knowledge_edges:
            if edge.source_id == source and edge.target_id == target and edge.relation == relation:
                edge.weight = min(10.0, edge.weight + 0.1)
                edge.last_seen = now
                return
        self._knowledge_edges.append(KnowledgeEdge(
            source_id=source,
            target_id=target,
            relation=relation,
            weight=1.0,
            first_seen=now,
            last_seen=now,
        ))

    @staticmethod
    def _entity_to_id(label: str, etype: str) -> str:
        return f"{etype}:{label.lower().replace(' ', '_')}"

    def get_knowledge_graph(self) -> Dict[str, Any]:
        """Return the knowledge graph as a serialisable dict."""
        return {
            "nodes": [
                {
                    "id": n.node_id,
                    "label": n.label,
                    "type": n.entity_type,
                    "mentions": n.mention_count,
                }
                for n in self._knowledge_nodes.values()
            ],
            "edges": [
                {
                    "source": e.source_id,
                    "target": e.target_id,
                    "relation": e.relation,
                    "weight": round(e.weight, 2),
                }
                for e in self._knowledge_edges
            ],
        }

    # ═════════════════════════════════════════════════════════
    # 🎯 Expertise Tracking
    # ═════════════════════════════════════════════════════════

    def _update_expertise(self, topic: str, quality: float, now: float) -> None:
        """Update expertise level for a topic after an interaction."""
        topic_key = topic.lower()
        if topic_key in self._expertise:
            area = self._expertise[topic_key]
            area.interactions += 1
            area.last_interaction = now
            if quality >= 0.6:
                area.successes += 1
            else:
                area.failures += 1
            # Adjust level: slow EMA
            target = quality
            area.level = area.level * 0.9 + target * 0.1
            if topic not in area.topics:
                area.topics.append(topic)
                if len(area.topics) > 20:
                    area.topics = area.topics[-20:]
        else:
            self._expertise[topic_key] = ExpertiseArea(
                domain=topic_key,
                level=max(0.1, quality * 0.5),  # start conservatively
                interactions=1,
                successes=1 if quality >= 0.6 else 0,
                failures=0 if quality >= 0.6 else 1,
                topics=[topic],
                last_interaction=now,
            )

    def get_expertise_profile(self) -> List[Dict[str, Any]]:
        """Return the full expertise profile sorted by level."""
        areas = sorted(
            self._expertise.values(),
            key=lambda a: a.level,
            reverse=True,
        )
        return [
            {
                "domain": a.domain,
                "level": round(a.level, 3),
                "interactions": a.interactions,
                "success_rate": round(a.success_rate, 3),
                "topics": a.topics[:10],
            }
            for a in areas
        ]

    # ═════════════════════════════════════════════════════════
    # 💡 Confidence Scoring
    # ═════════════════════════════════════════════════════════

    def get_confidence(self, topic: str) -> float:
        """Return confidence level (0.0–1.0) for answering about a topic."""
        topic_key = topic.lower()
        area = self._expertise.get(topic_key)
        if area is None:
            return 0.3  # default low confidence
        return area.level

    def get_confidence_label(self, topic: str) -> ConfidenceLevel:
        """Return a human-readable confidence level."""
        c = self.get_confidence(topic)
        if c >= 0.85:
            return ConfidenceLevel.CERTAIN
        if c >= 0.6:
            return ConfidenceLevel.HIGH
        if c >= 0.3:
            return ConfidenceLevel.MEDIUM
        return ConfidenceLevel.LOW

    # ═════════════════════════════════════════════════════════
    # 🔄 Apply Learned Patterns
    # ═════════════════════════════════════════════════════════

    def get_relevant_learnings(
        self,
        context: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Return learnings relevant to the given context.

        Uses keyword overlap scoring to rank relevance.
        """
        context_words = set(context.lower().split())
        if not context_words:
            return []

        scored: List[Tuple[float, Learning]] = []
        for learning in self._learnings:
            if learning.learning_type == LearningType.PATTERN:
                continue  # skip meta-patterns

            learning_words = set(
                (learning.content + " " + learning.category).lower().split()
            )
            overlap = len(context_words & learning_words)
            if overlap == 0:
                continue

            # Score by overlap ratio + confidence + recency
            overlap_score = overlap / max(1, len(context_words))
            recency = 1.0 / (1.0 + (time.time() - learning.last_seen) / 86400)
            score = overlap_score * 0.5 + learning.confidence * 0.3 + recency * 0.2

            scored.append((score, learning))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {
                "learning_id": l.learning_id,
                "type": l.learning_type.value,
                "category": l.category,
                "content": l.content[:300],
                "confidence": l.confidence,
                "occurrences": l.occurrences,
            }
            for _, l in scored[:limit]
        ]

    def get_preferences_summary(self) -> Dict[str, Any]:
        """Return all tracked preferences."""
        return {
            key: {
                "value": pref.value,
                "confidence": round(pref.confidence, 2),
                "source": pref.source,
                "occurrences": pref.occurrences,
            }
            for key, pref in sorted(
                self._preferences.items(),
                key=lambda x: x[1].confidence,
                reverse=True,
            )
        }

    # ═════════════════════════════════════════════════════════
    # 📈 Improvement Reports
    # ═════════════════════════════════════════════════════════

    def generate_report(self, period_hours: int = 24) -> ImprovementReport:
        """Generate an improvement report for the given period."""
        now = time.time()
        start = now - (period_hours * 3600)

        recent_learnings = [l for l in self._learnings if l.timestamp >= start]
        recent_metrics = [m for m in self._metrics if m.timestamp >= start]

        # Corrections
        corrections = [l for l in recent_learnings if l.learning_type == LearningType.CORRECTION]
        prefs_updated = [l for l in recent_learnings if l.learning_type == LearningType.PREFERENCE]

        # Expertise changes (interactions in period)
        expertise_changes: Dict[str, float] = {}
        for area in self._expertise.values():
            if area.last_interaction >= start:
                expertise_changes[area.domain] = round(area.level, 3)

        # Top patterns
        patterns = [
            l for l in recent_learnings
            if l.learning_type == LearningType.PATTERN
        ]
        top_patterns = [p.content[:100] for p in patterns[:5]]

        # Quality trend
        if len(recent_metrics) >= 2:
            first_half = [m.quality_score for m in recent_metrics[:len(recent_metrics)//2]]
            second_half = [m.quality_score for m in recent_metrics[len(recent_metrics)//2:]]
            avg_first = sum(first_half) / len(first_half) if first_half else 0.5
            avg_second = sum(second_half) / len(second_half) if second_half else 0.5
            quality_trend = avg_second - avg_first
        else:
            quality_trend = 0.0

        # Recommendations
        recommendations = self._generate_recommendations(recent_learnings, recent_metrics)

        report = ImprovementReport(
            report_id=uuid.uuid4().hex[:10],
            period_start=start,
            period_end=now,
            learnings_count=len(recent_learnings),
            corrections_applied=len(corrections),
            preferences_updated=len(prefs_updated),
            expertise_changes=expertise_changes,
            top_patterns=top_patterns,
            quality_trend=round(quality_trend, 3),
            recommendations=recommendations,
        )
        self._reports.append(report)
        self._save_all()
        return report

    def _generate_recommendations(
        self,
        learnings: List[Learning],
        metrics: List[ConversationMetrics],
    ) -> List[str]:
        """Generate actionable recommendations from recent data."""
        recs: List[str] = []

        # High correction rate → recommend focus area
        corrections = [l for l in learnings if l.learning_type == LearningType.CORRECTION]
        if len(corrections) > 5:
            cats = Counter(l.category for l in corrections)
            top = cats.most_common(1)[0]
            recs.append(
                f"High correction rate in '{top[0]}' ({top[1]}x). "
                f"Consider reviewing patterns and adjusting approach."
            )

        # Low quality trend
        if metrics:
            avg_quality = sum(m.quality_score for m in metrics) / len(metrics)
            if avg_quality < 0.4:
                recs.append(
                    f"Average quality score is low ({avg_quality:.2f}). "
                    f"Review recent failures and adjust response strategy."
                )

        # Many preferences → summarise
        pref_learnings = [l for l in learnings if l.learning_type == LearningType.PREFERENCE]
        if len(pref_learnings) > 3:
            recs.append(
                f"{len(pref_learnings)} new preferences detected. "
                f"Review and consolidate preference list."
            )

        # Slow responses
        if metrics:
            avg_time = sum(m.response_time_ms for m in metrics) / len(metrics)
            if avg_time > 10000:
                recs.append(
                    f"Average response time is high ({avg_time:.0f}ms). "
                    f"Consider optimising or using faster models for simple tasks."
                )

        if not recs:
            recs.append("No issues detected. Keep up the good work! ✨")

        return recs

    # ═════════════════════════════════════════════════════════
    # 🧹 Utilities
    # ═════════════════════════════════════════════════════════

    def _derive_preference_key(self, raw: str, value: str) -> str:
        """Derive a short key from a preference statement."""
        raw_lower = raw.lower()

        # Common patterns
        key_map = {
            "dark mode": "theme",
            "light mode": "theme",
            "python": "language",
            "javascript": "language",
            "typescript": "language",
            "rust": "language",
            "go": "language",
            "vim": "editor",
            "vscode": "editor",
            "emacs": "editor",
            "tab": "indentation",
            "space": "indentation",
            "short": "verbosity",
            "verbose": "verbosity",
            "concise": "verbosity",
        }

        for keyword, key in key_map.items():
            if keyword in raw_lower:
                return key

        # Fallback: use the value itself as key (truncated)
        words = value.lower().split()
        if words:
            return words[0][:30]
        return "unknown"

    def _deduplicate_learning(self, new: Learning) -> None:
        """Merge duplicate learnings — boost confidence of existing one."""
        for existing in self._learnings:
            if (
                existing.learning_id != new.learning_id
                and existing.learning_type == new.learning_type
                and existing.category == new.category
            ):
                # Simple content similarity: word overlap
                existing_words = set(existing.content.lower().split())
                new_words = set(new.content.lower().split())
                if not existing_words or not new_words:
                    continue
                overlap = len(existing_words & new_words) / max(1, len(existing_words | new_words))
                if overlap > 0.6:
                    existing.occurrences += 1
                    existing.last_seen = new.timestamp
                    existing.confidence = min(1.0, existing.confidence + 0.05)

    # ═════════════════════════════════════════════════════════
    # 📊 Self-Evaluation
    # ═════════════════════════════════════════════════════════

    def self_evaluate(self) -> Dict[str, Any]:
        """Run a self-evaluation and return results."""
        now = time.time()
        window = 86400 * 7  # 7 days

        recent_metrics = [m for m in self._metrics if now - m.timestamp < window]
        recent_learnings = [l for l in self._learnings if now - l.timestamp < window]

        if not recent_metrics:
            return {"status": "insufficient_data", "message": "Not enough data to evaluate"}

        avg_quality = sum(m.quality_score for m in recent_metrics) / len(recent_metrics)
        corrections = sum(m.corrections_received for m in recent_metrics)
        satisfaction = [
            m.user_satisfied for m in recent_metrics
            if m.user_satisfied is not None
        ]
        satisfaction_rate = (
            sum(1 for s in satisfaction if s) / len(satisfaction)
            if satisfaction else None
        )

        # Identify strengths and weaknesses
        topic_quality: Dict[str, List[float]] = defaultdict(list)
        for m in recent_metrics:
            for t in m.topics:
                topic_quality[t].append(m.quality_score)

        strengths = []
        weaknesses = []
        for topic, scores in topic_quality.items():
            avg = sum(scores) / len(scores)
            if avg >= 0.7 and len(scores) >= 2:
                strengths.append(f"{topic} (avg={avg:.2f}, n={len(scores)})")
            elif avg < 0.4 and len(scores) >= 2:
                weaknesses.append(f"{topic} (avg={avg:.2f}, n={len(scores)})")

        return {
            "status": "ok",
            "period_days": 7,
            "interactions": len(recent_metrics),
            "avg_quality": round(avg_quality, 3),
            "corrections_received": corrections,
            "satisfaction_rate": (
                round(satisfaction_rate, 3) if satisfaction_rate is not None else None
            ),
            "learnings_count": len(recent_learnings),
            "strengths": strengths[:5],
            "weaknesses": weaknesses[:5],
            "preferences_tracked": len(self._preferences),
            "expertise_domains": len(self._expertise),
            "knowledge_graph_nodes": len(self._knowledge_nodes),
        }

    # ═════════════════════════════════════════════════════════
    # 💾 Persistence
    # ═════════════════════════════════════════════════════════

    def _load_all(self) -> None:
        """Load all persisted data."""
        self._load_learnings()
        self._load_preferences()
        self._load_expertise()
        self._load_knowledge_graph()
        self._load_metrics()
        self._load_reports()

    def _save_all(self) -> None:
        """Persist all data."""
        self._save_learnings()
        self._save_preferences()
        self._save_expertise()
        self._save_knowledge_graph()
        self._save_metrics()
        self._save_reports()

    def _load_learnings(self) -> None:
        path = self._data_dir / "learnings.json"
        if path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                self._learnings = [Learning.from_dict(item) for item in raw]
            except Exception as e:
                logger.error("Failed to load learnings: %s", e)

    def _save_learnings(self) -> None:
        path = self._data_dir / "learnings.json"
        try:
            # Keep last 10000 learnings
            data = self._learnings[-10000:]
            path.write_text(
                json.dumps([l.to_dict() for l in data], indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error("Failed to save learnings: %s", e)

    def _load_preferences(self) -> None:
        path = self._data_dir / "preferences.json"
        if path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                self._preferences = {
                    k: Preference.from_dict(v) for k, v in raw.items()
                }
            except Exception as e:
                logger.error("Failed to load preferences: %s", e)

    def _save_preferences(self) -> None:
        path = self._data_dir / "preferences.json"
        try:
            path.write_text(
                json.dumps(
                    {k: p.to_dict() for k, p in self._preferences.items()},
                    indent=2, ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error("Failed to save preferences: %s", e)

    def _load_expertise(self) -> None:
        path = self._data_dir / "expertise.json"
        if path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                self._expertise = {
                    k: ExpertiseArea.from_dict(v) for k, v in raw.items()
                }
            except Exception as e:
                logger.error("Failed to load expertise: %s", e)

    def _save_expertise(self) -> None:
        path = self._data_dir / "expertise.json"
        try:
            path.write_text(
                json.dumps(
                    {k: a.to_dict() for k, a in self._expertise.items()},
                    indent=2, ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error("Failed to save expertise: %s", e)

    def _load_knowledge_graph(self) -> None:
        path = self._data_dir / "knowledge_graph.json"
        if path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                for n in raw.get("nodes", []):
                    node = KnowledgeNode(**n)
                    self._knowledge_nodes[node.node_id] = node
                for e in raw.get("edges", []):
                    self._knowledge_edges.append(KnowledgeEdge(**e))
            except Exception as e:
                logger.error("Failed to load knowledge graph: %s", e)

    def _save_knowledge_graph(self) -> None:
        path = self._data_dir / "knowledge_graph.json"
        try:
            data = {
                "nodes": [
                    {
                        "node_id": n.node_id,
                        "label": n.label,
                        "entity_type": n.entity_type,
                        "properties": n.properties,
                        "first_seen": n.first_seen,
                        "last_seen": n.last_seen,
                        "mention_count": n.mention_count,
                    }
                    for n in self._knowledge_nodes.values()
                ],
                "edges": [
                    {
                        "source_id": e.source_id,
                        "target_id": e.target_id,
                        "relation": e.relation,
                        "weight": e.weight,
                        "first_seen": e.first_seen,
                        "last_seen": e.last_seen,
                    }
                    for e in self._knowledge_edges
                ],
            }
            path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error("Failed to save knowledge graph: %s", e)

    def _load_metrics(self) -> None:
        path = self._data_dir / "metrics.json"
        if path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                self._metrics = [ConversationMetrics(**m) for m in raw]
            except Exception as e:
                logger.error("Failed to load metrics: %s", e)

    def _save_metrics(self) -> None:
        path = self._data_dir / "metrics.json"
        try:
            data = self._metrics[-5000:]
            path.write_text(
                json.dumps([asdict(m) for m in data], indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error("Failed to save metrics: %s", e)

    def _load_reports(self) -> None:
        path = self._data_dir / "reports.json"
        if path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                self._reports = [ImprovementReport(**r) for r in raw]
            except Exception as e:
                logger.error("Failed to load reports: %s", e)

    def _save_reports(self) -> None:
        path = self._data_dir / "reports.json"
        try:
            data = [asdict(r) for r in self._reports[-100:]]
            path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error("Failed to save reports: %s", e)

    # ═════════════════════════════════════════════════════════
    # 🧹 Housekeeping
    # ═════════════════════════════════════════════════════════

    def prune(self, max_age_days: int = 90) -> int:
        """Remove old learnings and metrics beyond retention."""
        cutoff = time.time() - (max_age_days * 86400)
        before = len(self._learnings)
        self._learnings = [l for l in self._learnings if l.timestamp >= cutoff]
        pruned = before - len(self._learnings)

        # Prune metrics
        self._metrics = [m for m in self._metrics if m.timestamp >= cutoff]

        # Prune old edges
        self._knowledge_edges = [
            e for e in self._knowledge_edges if e.last_seen >= cutoff
        ]

        self._save_all()
        logger.info("Pruned %d old learnings", pruned)
        return pruned

    def export_data(self) -> Dict[str, Any]:
        """Export all data for backup or migration."""
        return {
            "learnings": [l.to_dict() for l in self._learnings],
            "preferences": {k: p.to_dict() for k, p in self._preferences.items()},
            "expertise": {k: a.to_dict() for k, a in self._expertise.items()},
            "knowledge_graph": self.get_knowledge_graph(),
            "metrics_count": len(self._metrics),
            "reports_count": len(self._reports),
        }
