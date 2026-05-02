"""
🟣 Rally Agent — Knowledge Graph
=================================
A lightweight, persistent knowledge graph that extracts entities and
relationships from conversations. Enables semantic queries like
"what relates to X?" and "when did we discuss Y?"

Storage: JSON-based graph with nodes (entities) and edges (relationships).
No external dependencies — pure Python graph engine.
"""

import asyncio
import json
import os
import re
import time
import uuid
import logging
import threading
from typing import Optional, Any, Dict, List, Set, Tuple, Iterator
from datetime import datetime, timedelta
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger("rally.knowledge_graph")


# ═══════════════════════════════════════════════════════════════
# 📐 Constants
# ═══════════════════════════════════════════════════════════════

MAX_NODES = 5000
MAX_EDGES = 20000
IMPORTANCE_DECAY_DAYS = 60
SAVE_INTERVAL = 20  # auto-save every N updates


class EntityType(str, Enum):
    PERSON = "person"
    PROJECT = "project"
    TOOL = "tool"
    CONCEPT = "concept"
    TECHNOLOGY = "technology"
    LANGUAGE = "language"
    FRAMEWORK = "framework"
    FILE = "file"
    ORGANIZATION = "organization"
    LOCATION = "location"
    EVENT = "event"
    URL = "url"
    UNKNOWN = "unknown"


class RelationType(str, Enum):
    USES = "uses"
    MENTIONS = "mentions"
    WORKS_ON = "works_on"
    RELATES_TO = "relates_to"
    DEPENDS_ON = "depends_on"
    PART_OF = "part_of"
    CREATED_BY = "created_by"
    REPLACES = "replaces"
    SIMILAR_TO = "similar_to"
    DISCUSSED_WITH = "discussed_with"
    LEARNED = "learned"
    MENTIONED_IN = "mentioned_in"


# ═══════════════════════════════════════════════════════════════
# 🧩 Data Structures
# ═══════════════════════════════════════════════════════════════

@dataclass
class Entity:
    """A node in the knowledge graph."""
    entity_id: str = ""
    name: str = ""
    entity_type: EntityType = EntityType.UNKNOWN
    aliases: List[str] = field(default_factory=list)
    description: str = ""
    properties: Dict[str, Any] = field(default_factory=dict)
    importance: float = 0.5          # 0.0 – 1.0
    mention_count: int = 0
    first_seen: str = ""
    last_seen: str = ""
    contexts: List[str] = field(default_factory=list)  # brief context snippets

    def to_dict(self) -> dict:
        return {
            "entity_id": self.entity_id,
            "name": self.name,
            "entity_type": self.entity_type.value if isinstance(self.entity_type, EntityType) else self.entity_type,
            "aliases": self.aliases,
            "description": self.description,
            "properties": self.properties,
            "importance": round(self.importance, 4),
            "mention_count": self.mention_count,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "contexts": self.contexts[-10:],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Entity":
        et = d.get("entity_type", "unknown")
        try:
            et = EntityType(et)
        except ValueError:
            et = EntityType.UNKNOWN
        return cls(
            entity_id=d.get("entity_id", ""),
            name=d.get("name", ""),
            entity_type=et,
            aliases=d.get("aliases", []),
            description=d.get("description", ""),
            properties=d.get("properties", {}),
            importance=d.get("importance", 0.5),
            mention_count=d.get("mention_count", 0),
            first_seen=d.get("first_seen", ""),
            last_seen=d.get("last_seen", ""),
            contexts=d.get("contexts", []),
        )


@dataclass
class Relationship:
    """An edge in the knowledge graph."""
    edge_id: str = ""
    source_id: str = ""
    target_id: str = ""
    relation_type: RelationType = RelationType.RELATES_TO
    weight: float = 1.0              # strength of relationship
    properties: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    last_seen: str = ""
    mention_count: int = 0
    contexts: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "edge_id": self.edge_id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relation_type": self.relation_type.value if isinstance(self.relation_type, RelationType) else self.relation_type,
            "weight": round(self.weight, 4),
            "properties": self.properties,
            "created_at": self.created_at,
            "last_seen": self.last_seen,
            "mention_count": self.mention_count,
            "contexts": self.contexts[-5:],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Relationship":
        rt = d.get("relation_type", "relates_to")
        try:
            rt = RelationType(rt)
        except ValueError:
            rt = RelationType.RELATES_TO
        return cls(
            edge_id=d.get("edge_id", ""),
            source_id=d.get("source_id", ""),
            target_id=d.get("target_id", ""),
            relation_type=rt,
            weight=d.get("weight", 1.0),
            properties=d.get("properties", {}),
            created_at=d.get("created_at", ""),
            last_seen=d.get("last_seen", ""),
            mention_count=d.get("mention_count", 0),
            contexts=d.get("contexts", []),
        )


# ═══════════════════════════════════════════════════════════════
# 🔍 Entity Extractor
# ═══════════════════════════════════════════════════════════════

class EntityExtractor:
    """Extracts entities from conversation text using pattern matching.

    This is the "cheap" extractor — fast, no external API calls.
    For higher quality, an LLM-based extractor can be layered on top.
    """

    # Technology/tool patterns
    TECH_PATTERNS: Dict[str, Tuple[EntityType, str]] = {
        # Languages
        "python": (EntityType.LANGUAGE, r"\b(python|pip|pypi)\b"),
        "javascript": (EntityType.LANGUAGE, r"\b(javascript|js|node\.?js|npm)\b"),
        "typescript": (EntityType.LANGUAGE, r"\b(typescript|ts)\b"),
        "rust": (EntityType.LANGUAGE, r"\b(rust|cargo|rustc)\b"),
        "go": (EntityType.LANGUAGE, r"\b(golang)\b"),
        "java": (EntityType.LANGUAGE, r"\b(java(?!\s*script)|jvm)\b"),
        "c++": (EntityType.LANGUAGE, r"\b(c\+\+|cpp)\b"),
        "ruby": (EntityType.LANGUAGE, r"\b(ruby)\b"),
        "php": (EntityType.LANGUAGE, r"\b(php)\b"),
        "swift": (EntityType.LANGUAGE, r"\b(swift)\b"),
        "kotlin": (EntityType.LANGUAGE, r"\b(kotlin)\b"),
        "sql": (EntityType.LANGUAGE, r"\b(sql)\b"),
        # Frameworks
        "react": (EntityType.FRAMEWORK, r"\b(react|reactjs|next\.?js|nextjs|remix)\b"),
        "vue": (EntityType.FRAMEWORK, r"\b(vue|vuejs|nuxt|nuxtjs)\b"),
        "svelte": (EntityType.FRAMEWORK, r"\b(svelte|sveltekit)\b"),
        "angular": (EntityType.FRAMEWORK, r"\b(angular)\b"),
        "django": (EntityType.FRAMEWORK, r"\b(django)\b"),
        "flask": (EntityType.FRAMEWORK, r"\b(flask)\b"),
        "fastapi": (EntityType.FRAMEWORK, r"\b(fastapi)\b"),
        "express": (EntityType.FRAMEWORK, r"\b(express)\b"),
        "tailwind": (EntityType.FRAMEWORK, r"\b(tailwind|tailwindcss)\b"),
        # Tools
        "docker": (EntityType.TOOL, r"\b(docker|dockerfile)\b"),
        "kubernetes": (EntityType.TOOL, r"\b(kubernetes|k8s|kubectl|helm)\b"),
        "terraform": (EntityType.TOOL, r"\b(terraform)\b"),
        "git": (EntityType.TOOL, r"\b(git|github|gitlab)\b"),
        "nginx": (EntityType.TOOL, r"\b(nginx)\b"),
        "redis": (EntityType.TOOL, r"\b(redis)\b"),
        "postgres": (EntityType.TOOL, r"\b(postgres|postgresql)\b"),
        "mysql": (EntityType.TOOL, r"\b(mysql)\b"),
        "sqlite": (EntityType.TOOL, r"\b(sqlite)\b"),
        "elasticsearch": (EntityType.TOOL, r"\b(elasticsearch|elastic)\b"),
        "kafka": (EntityType.TOOL, r"\b(kafka)\b"),
        "figma": (EntityType.TOOL, r"\b(figma)\b"),
        "vscode": (EntityType.TOOL, r"\b(vs\s*code|vscode)\b"),
        # AI/ML
        "tensorflow": (EntityType.TOOL, r"\b(tensorflow|tf)\b"),
        "pytorch": (EntityType.TOOL, r"\b(pytorch|torch)\b"),
        "openai": (EntityType.ORGANIZATION, r"\b(openai|gpt-[34]|chatgpt)\b"),
        "anthropic": (EntityType.ORGANIZATION, r"\b(anthropic|claude)\b"),
        # Cloud
        "aws": (EntityType.TOOL, r"\b(aws|amazon web services|s3|ec2|lambda|cloudfront)\b"),
        "gcp": (EntityType.TOOL, r"\b(gcp|google cloud)\b"),
        "azure": (EntityType.TOOL, r"\b(azure|microsoft cloud)\b"),
        "vercel": (EntityType.TOOL, r"\b(vercel)\b"),
        "netlify": (EntityType.TOOL, r"\b(netlify)\b"),
        "fly.io": (EntityType.TOOL, r"\b(fly\.io|flyio)\b"),
    }

    # URL pattern
    URL_RE = re.compile(r"https?://[^\s\)\]\}\"\']+")

    # File path pattern
    FILE_RE = re.compile(r"(?:^|\s)([\w\-./]+\.(?:py|js|ts|rs|go|java|rb|php|html|css|json|yaml|yml|toml|md|txt|sh|sql|xml|conf|cfg))\b")

    # "I" / "me" person patterns for extracting project names
    PROJECT_PATTERNS = [
        re.compile(r"(?:project|repo|repository)\s+['\"]?([\w\-]+)['\"]?", re.I),
        re.compile(r"(?:working on|building|developing)\s+([\w][\w\s\-]{2,30}?)(?:\s+(?:for|with|using|that)|\.|,|$)", re.I),
    ]

    # Concept patterns (abstract ideas discussed)
    CONCEPT_PATTERNS = {
        "microservices": (EntityType.CONCEPT, r"\b(microservice|micro.service)\b"),
        "monolith": (EntityType.CONCEPT, r"\b(monolith|monolithic)\b"),
        "api_design": (EntityType.CONCEPT, r"\b(api design|rest api|restful|graphql|grpc)\b"),
        "ci_cd": (EntityType.CONCEPT, r"\b(ci/cd|continuous integration|continuous deployment|pipeline)\b"),
        "testing": (EntityType.CONCEPT, r"\b(unit test|integration test|e2e|test driven|tdd|bdd)\b"),
        "security": (EntityType.CONCEPT, r"\b(authentication|authorization|oauth|jwt|encryption)\b"),
        "performance": (EntityType.CONCEPT, r"\b(performance|optimization|caching|latency|throughput)\b"),
        "scalability": (EntityType.CONCEPT, r"\b(scalab|horizontal scaling|vertical scaling|load balanc)\b"),
        "machine_learning": (EntityType.CONCEPT, r"\b(machine learning|deep learning|neural network|training model)\b"),
        "llm": (EntityType.CONCEPT, r"\b(llm|large language model|prompt engineering|fine.?tun)\b"),
        "database_design": (EntityType.CONCEPT, r"\b(database design|schema|migration|normalization)\b"),
        "devops": (EntityType.CONCEPT, r"\b(devops|infrastructure as code|observability|monitoring)\b"),
    }

    def extract(self, text: str) -> List[Tuple[str, EntityType, str]]:
        """Extract entities from text.

        Returns list of (name, entity_type, context_snippet).
        """
        found: List[Tuple[str, EntityType, str]] = []
        text_lower = text.lower()
        seen: Set[str] = set()

        # Technologies
        for name, (etype, pattern) in self.TECH_PATTERNS.items():
            if re.search(pattern, text_lower) and name not in seen:
                found.append((name, etype, self._snippet(text, pattern)))
                seen.add(name)

        # Concepts
        for name, (etype, pattern) in self.CONCEPT_PATTERNS.items():
            if re.search(pattern, text_lower) and name not in seen:
                found.append((name, etype, self._snippet(text, pattern)))
                seen.add(name)

        # URLs
        for url in self.URL_RE.findall(text):
            if url not in seen:
                found.append((url[:100], EntityType.URL, ""))
                seen.add(url)

        # File paths
        for filepath in self.FILE_RE.findall(text):
            if filepath not in seen:
                found.append((filepath, EntityType.FILE, ""))
                seen.add(filepath)

        # Project names
        for pattern in self.PROJECT_PATTERNS:
            for match in pattern.findall(text):
                name = match.strip()
                if name and len(name) > 2 and name.lower() not in seen:
                    found.append((name, EntityType.PROJECT, ""))
                    seen.add(name.lower())

        return found

    @staticmethod
    def _snippet(text: str, pattern: str, window: int = 60) -> str:
        """Extract a context snippet around a pattern match."""
        m = re.search(pattern, text, re.I)
        if not m:
            return ""
        start = max(0, m.start() - window)
        end = min(len(text), m.end() + window)
        snippet = text[start:end].strip()
        if start > 0:
            snippet = "..." + snippet
        if end < len(text):
            snippet = snippet + "..."
        return snippet[:200]


# ═══════════════════════════════════════════════════════════════
# 🕸️ Knowledge Graph
# ═══════════════════════════════════════════════════════════════

class KnowledgeGraph:
    """Persistent knowledge graph for entity and relationship tracking.

    Stores entities as nodes and relationships as edges in a JSON-based
    graph structure. Supports temporal queries, importance scoring,
    and visual graph data for web UI rendering.
    """

    def __init__(self, data_dir: Optional[str] = None):
        self.data_dir = os.path.expanduser(data_dir or "~/.rally-agent/data")
        self.graph_file = os.path.join(self.data_dir, "knowledge_graph.json")
        os.makedirs(self.data_dir, exist_ok=True)

        # Core graph
        self.entities: Dict[str, Entity] = {}       # entity_id -> Entity
        self.relationships: Dict[str, Relationship] = {}  # edge_id -> Relationship

        # Indexes for fast lookup
        self._name_index: Dict[str, str] = {}       # lowercase name -> entity_id
        self._alias_index: Dict[str, str] = {}      # lowercase alias -> entity_id
        self._type_index: Dict[str, Set[str]] = defaultdict(set)  # type -> {entity_ids}
        self._adjacency: Dict[str, Set[str]] = defaultdict(set)   # entity_id -> {edge_ids}

        # Temporal index: date -> {entity_ids mentioned that day}
        self._temporal_index: Dict[str, Set[str]] = defaultdict(set)

        # Extractor
        self.extractor = EntityExtractor()

        # Auto-save state
        self._dirty_count: int = 0
        self._save_lock = threading.Lock()

        # Load existing graph
        self._load()

    # ───────────────────────────────────────────────────────
    # Persistence
    # ───────────────────────────────────────────────────────

    def _load(self) -> None:
        """Load graph from disk."""
        if not os.path.exists(self.graph_file):
            return
        try:
            with open(self.graph_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Entities
            for edata in data.get("entities", []):
                entity = Entity.from_dict(edata)
                self.entities[entity.entity_id] = entity
                self._name_index[entity.name.lower()] = entity.entity_id
                for alias in entity.aliases:
                    self._alias_index[alias.lower()] = entity.entity_id
                self._type_index[entity.entity_type.value if isinstance(entity.entity_type, EntityType) else entity.entity_type].add(entity.entity_id)

            # Relationships
            for rdata in data.get("relationships", []):
                rel = Relationship.from_dict(rdata)
                self.relationships[rel.edge_id] = rel
                self._adjacency[rel.source_id].add(rel.edge_id)
                self._adjacency[rel.target_id].add(rel.edge_id)

            # Temporal index
            for date_str, eids in data.get("temporal_index", {}).items():
                self._temporal_index[date_str] = set(eids)

            logger.info(f"KnowledgeGraph loaded: {len(self.entities)} entities, {len(self.relationships)} relationships")
        except Exception as e:
            logger.error(f"Failed to load knowledge graph: {e}")

    def save(self) -> None:
        """Persist graph to disk with atomic write."""
        with self._save_lock:
            data = {
                "entities": [e.to_dict() for e in self.entities.values()],
                "relationships": [r.to_dict() for r in self.relationships.values()],
                "temporal_index": {k: list(v) for k, v in self._temporal_index.items()},
                "schema_version": 1,
                "saved_at": datetime.now().isoformat(),
            }
            tmp = self.graph_file + ".tmp"
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                os.replace(tmp, self.graph_file)
                self._dirty_count = 0
                logger.debug("KnowledgeGraph saved")
            except Exception as e:
                logger.error(f"Failed to save knowledge graph: {e}")
                try:
                    os.unlink(tmp)
                except OSError:
                    pass

    def _auto_save(self) -> None:
        self._dirty_count += 1
        if self._dirty_count >= SAVE_INTERVAL:
            self.save()

    # ───────────────────────────────────────────────────────
    # Entity Management
    # ───────────────────────────────────────────────────────

    def add_entity(
        self,
        name: str,
        entity_type: EntityType = EntityType.UNKNOWN,
        description: str = "",
        aliases: Optional[List[str]] = None,
        properties: Optional[Dict[str, Any]] = None,
        importance: float = 0.5,
        context: str = "",
    ) -> Entity:
        """Add or update an entity in the graph.

        If an entity with the same name (case-insensitive) exists, it gets
        updated. Otherwise a new entity is created.
        """
        now = datetime.now().isoformat()
        key = name.lower().strip()

        # Check existing via name index or alias index
        existing_id = self._name_index.get(key) or self._alias_index.get(key)

        if existing_id and existing_id in self.entities:
            entity = self.entities[existing_id]
            entity.mention_count += 1
            entity.last_seen = now
            entity.importance = self._recalc_importance(entity)
            if description and not entity.description:
                entity.description = description
            if properties:
                entity.properties.update(properties)
            if context:
                entity.contexts.append(context[:200])
                if len(entity.contexts) > 20:
                    entity.contexts = entity.contexts[-20:]
            # Add new aliases
            for alias in (aliases or []):
                if alias.lower() not in self._alias_index:
                    entity.aliases.append(alias)
                    self._alias_index[alias.lower()] = entity.entity_id
        else:
            # Create new entity
            eid = f"e_{uuid.uuid4().hex[:12]}"
            entity = Entity(
                entity_id=eid,
                name=name.strip(),
                entity_type=entity_type,
                aliases=[a.strip() for a in (aliases or [])],
                description=description,
                properties=properties or {},
                importance=importance,
                mention_count=1,
                first_seen=now,
                last_seen=now,
                contexts=[context[:200]] if context else [],
            )
            self.entities[eid] = entity
            self._name_index[key] = eid
            for alias in entity.aliases:
                self._alias_index[alias.lower()] = eid
            self._type_index[entity_type.value if isinstance(entity_type, EntityType) else str(entity_type)].add(eid)

        # Update temporal index
        date_str = datetime.now().strftime("%Y-%m-%d")
        self._temporal_index[date_str].add(entity.entity_id)

        self._auto_save()
        return entity

    def get_entity(self, name_or_id: str) -> Optional[Entity]:
        """Look up an entity by name or ID."""
        # Try ID first
        if name_or_id in self.entities:
            return self.entities[name_or_id]
        # Try name index
        key = name_or_id.lower().strip()
        eid = self._name_index.get(key) or self._alias_index.get(key)
        if eid:
            return self.entities.get(eid)
        return None

    def remove_entity(self, name_or_id: str) -> bool:
        """Remove an entity and all its relationships."""
        entity = self.get_entity(name_or_id)
        if not entity:
            return False

        eid = entity.entity_id

        # Remove all edges involving this entity
        edge_ids = list(self._adjacency.get(eid, set()))
        for e in edge_ids:
            self._remove_edge(e)

        # Remove from indexes
        self._name_index.pop(entity.name.lower(), None)
        for alias in entity.aliases:
            self._alias_index.pop(alias.lower(), None)
        etype = entity.entity_type.value if isinstance(entity.entity_type, EntityType) else str(entity.entity_type)
        self._type_index[etype].discard(eid)
        self._adjacency.pop(eid, None)

        # Remove entity
        del self.entities[eid]

        self._auto_save()
        return True

    def _remove_edge(self, edge_id: str) -> None:
        """Remove a relationship edge."""
        if edge_id not in self.relationships:
            return
        rel = self.relationships[edge_id]
        self._adjacency[rel.source_id].discard(edge_id)
        self._adjacency[rel.target_id].discard(edge_id)
        del self.relationships[edge_id]

    def _recalc_importance(self, entity: Entity) -> float:
        """Recalculate entity importance based on mentions and recency."""
        base = min(1.0, entity.mention_count / 20)
        # Recency boost
        try:
            last = datetime.fromisoformat(entity.last_seen)
            days_ago = (datetime.now() - last).total_seconds() / 86400
            recency = max(0.3, 1.0 - (days_ago / IMPORTANCE_DECAY_DAYS))
        except (ValueError, TypeError):
            recency = 0.5
        return round(min(1.0, base * recency + 0.2), 4)

    # ───────────────────────────────────────────────────────
    # Relationship Management
    # ───────────────────────────────────────────────────────

    def add_relationship(
        self,
        source: str,
        target: str,
        relation_type: RelationType = RelationType.RELATES_TO,
        weight: float = 1.0,
        properties: Optional[Dict[str, Any]] = None,
        context: str = "",
    ) -> Optional[Relationship]:
        """Add or strengthen a relationship between two entities.

        Both source and target can be names or IDs. Entities are auto-created
        if they don't exist.
        """
        now = datetime.now().isoformat()

        # Resolve entities
        src_entity = self.get_entity(source) or self.add_entity(source)
        tgt_entity = self.get_entity(target) or self.add_entity(target)

        if not src_entity or not tgt_entity:
            return None

        # Check for existing relationship of same type
        for edge_id in self._adjacency.get(src_entity.entity_id, set()):
            rel = self.relationships.get(edge_id)
            if (
                rel
                and rel.relation_type == relation_type
                and (
                    (rel.source_id == src_entity.entity_id and rel.target_id == tgt_entity.entity_id)
                    or (rel.source_id == tgt_entity.entity_id and rel.target_id == src_entity.entity_id)
                )
            ):
                # Strengthen existing relationship
                rel.mention_count += 1
                rel.weight = min(1.0, rel.weight + 0.1)
                rel.last_seen = now
                if context:
                    rel.contexts.append(context[:200])
                    if len(rel.contexts) > 10:
                        rel.contexts = rel.contexts[-10:]
                if properties:
                    rel.properties.update(properties)
                self._auto_save()
                return rel

        # Create new relationship
        rid = f"r_{uuid.uuid4().hex[:12]}"
        rel = Relationship(
            edge_id=rid,
            source_id=src_entity.entity_id,
            target_id=tgt_entity.entity_id,
            relation_type=relation_type,
            weight=weight,
            properties=properties or {},
            created_at=now,
            last_seen=now,
            mention_count=1,
            contexts=[context[:200]] if context else [],
        )
        self.relationships[rid] = rel
        self._adjacency[src_entity.entity_id].add(rid)
        self._adjacency[tgt_entity.entity_id].add(rid)

        self._auto_save()
        return rel

    # ───────────────────────────────────────────────────────
    # Conversation Processing
    # ───────────────────────────────────────────────────────

    def process_conversation(
        self,
        user_message: str,
        agent_response: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Process a conversation turn and update the graph.

        Extracts entities and relationships from both the user message
        and agent response, then updates the graph.
        """
        combined = f"{user_message} {agent_response}"
        now = datetime.now().isoformat()
        date_str = datetime.now().strftime("%Y-%m-%d")

        # Extract entities
        extracted = self.extractor.extract(combined)
        entities_added: List[str] = []
        entities_updated: List[str] = []

        for name, etype, context in extracted:
            existing = self.get_entity(name)
            if existing:
                self.add_entity(name, etype, context=context)
                entities_updated.append(name)
            else:
                self.add_entity(name, etype, context=context, importance=0.4)
                entities_added.append(name)

        # Detect co-occurrence relationships
        # Entities mentioned in the same message are likely related
        entity_ids = []
        for name, _, _ in extracted:
            e = self.get_entity(name)
            if e:
                entity_ids.append(e.entity_id)

        # Create co-occurrence edges (limited to avoid explosion)
        for i, eid1 in enumerate(entity_ids[:8]):
            for eid2 in entity_ids[i+1:8]:
                if eid1 != eid2:
                    e1 = self.entities.get(eid1)
                    e2 = self.entities.get(eid2)
                    if e1 and e2:
                        self.add_relationship(
                            e1.name, e2.name,
                            RelationType.RELATES_TO,
                            weight=0.3,
                            context=user_message[:150],
                        )

        # Detect specific relationship patterns
        self._detect_specific_relationships(user_message, extracted)

        # Update temporal index
        for eid in entity_ids:
            self._temporal_index[date_str].add(eid)

        self._auto_save()

        return {
            "entities_added": entities_added,
            "entities_updated": entities_updated,
            "total_entities": len(self.entities),
            "total_relationships": len(self.relationships),
        }

    def _detect_specific_relationships(
        self, text: str, extracted: List[Tuple[str, EntityType, str]]
    ) -> None:
        """Detect specific relationship patterns in text."""
        text_lower = text.lower()

        # "X uses Y" pattern
        for m in re.finditer(r"(\w+)\s+(?:uses?|using|with|via)\s+(\w+)", text_lower):
            src, tgt = m.group(1), m.group(2)
            if self.get_entity(src) and self.get_entity(tgt):
                self.add_relationship(src, tgt, RelationType.USES, context=text[:150])

        # "X for Y" pattern (tool for task)
        for m in re.finditer(r"(\w+)\s+for\s+(\w+[\w\s]{0,20})", text_lower):
            src, tgt = m.group(1).strip(), m.group(2).strip()
            if self.get_entity(src) and self.get_entity(tgt):
                self.add_relationship(src, tgt, RelationType.USES, context=text[:150])

        # "working on X" pattern
        for m in re.finditer(r"(?:working on|building|developing)\s+(\w+)", text_lower):
            proj = m.group(1)
            if self.get_entity(proj):
                self.add_relationship("user", proj, RelationType.WORKS_ON, context=text[:150])

    # ───────────────────────────────────────────────────────
    # Import from Memory
    # ───────────────────────────────────────────────────────

    def import_from_memory(self, memory_entries: List[Dict[str, Any]]) -> int:
        """Import entities and relationships from memory entries.

        Each entry should have at least 'text' or 'content' field.
        Returns the number of new entities created.
        """
        count = 0
        for entry in memory_entries:
            text = entry.get("text") or entry.get("content", "")
            if not text:
                continue
            result = self.process_conversation(text)
            count += len(result.get("entities_added", []))
        return count

    # ───────────────────────────────────────────────────────
    # Queries
    # ───────────────────────────────────────────────────────

    def get_related(
        self,
        name_or_id: str,
        relation_type: Optional[RelationType] = None,
        max_depth: int = 1,
        min_weight: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """Find entities related to the given entity.

        Supports multi-hop traversal up to max_depth.
        Returns list of {entity, relationship, depth}.
        """
        entity = self.get_entity(name_or_id)
        if not entity:
            return []

        results: List[Dict[str, Any]] = []
        visited: Set[str] = {entity.entity_id}
        queue: List[Tuple[str, int]] = [(entity.entity_id, 0)]

        while queue:
            current_id, depth = queue.pop(0)
            if depth >= max_depth:
                continue

            for edge_id in self._adjacency.get(current_id, set()):
                rel = self.relationships.get(edge_id)
                if not rel or rel.weight < min_weight:
                    continue
                if relation_type and rel.relation_type != relation_type:
                    continue

                # Get the neighbor
                neighbor_id = rel.target_id if rel.source_id == current_id else rel.source_id
                if neighbor_id in visited:
                    continue
                visited.add(neighbor_id)

                neighbor = self.entities.get(neighbor_id)
                if not neighbor:
                    continue

                results.append({
                    "entity": neighbor.to_dict(),
                    "relationship": rel.to_dict(),
                    "depth": depth + 1,
                })

                if depth + 1 < max_depth:
                    queue.append((neighbor_id, depth + 1))

        # Sort by weight descending
        results.sort(key=lambda x: x["relationship"]["weight"], reverse=True)
        return results

    def search_entities(
        self,
        query: str,
        entity_type: Optional[EntityType] = None,
        limit: int = 20,
    ) -> List[Entity]:
        """Search entities by name or description."""
        query_lower = query.lower()
        results: List[Tuple[float, Entity]] = []

        for entity in self.entities.values():
            if entity_type and entity.entity_type != entity_type:
                continue

            score = 0.0
            if query_lower in entity.name.lower():
                score += 2.0
            if query_lower in entity.description.lower():
                score += 1.0
            for alias in entity.aliases:
                if query_lower in alias.lower():
                    score += 1.5
                    break

            if score > 0:
                score *= entity.importance
                results.append((score, entity))

        results.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in results[:limit]]

    def get_entities_by_type(self, entity_type: EntityType) -> List[Entity]:
        """Get all entities of a given type."""
        eids = self._type_index.get(entity_type.value, set())
        return [self.entities[eid] for eid in eids if eid in self.entities]

    def get_by_date(self, date_str: str) -> List[Entity]:
        """Get entities mentioned on a specific date (YYYY-MM-DD)."""
        eids = self._temporal_index.get(date_str, set())
        return [self.entities[eid] for eid in eids if eid in self.entities]

    def get_recent(self, days: int = 7, limit: int = 20) -> List[Entity]:
        """Get recently mentioned entities."""
        cutoff = datetime.now() - timedelta(days=days)
        recent: List[Tuple[str, Entity]] = []
        for entity in self.entities.values():
            try:
                last = datetime.fromisoformat(entity.last_seen)
                if last >= cutoff:
                    recent.append((entity.last_seen, entity))
            except (ValueError, TypeError):
                continue
        recent.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in recent[:limit]]

    # ───────────────────────────────────────────────────────
    # Graph Statistics & Visualization
    # ───────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Get graph statistics."""
        type_counts = Counter()
        for entity in self.entities.values():
            etype = entity.entity_type.value if isinstance(entity.entity_type, EntityType) else str(entity.entity_type)
            type_counts[etype] += 1

        rel_counts = Counter()
        for rel in self.relationships.values():
            rtype = rel.relation_type.value if isinstance(rel.relation_type, RelationType) else str(rel.relation_type)
            rel_counts[rtype] += 1

        return {
            "total_entities": len(self.entities),
            "total_relationships": len(self.relationships),
            "entity_types": dict(type_counts),
            "relationship_types": dict(rel_counts),
            "dates_tracked": len(self._temporal_index),
            "most_connected": self._most_connected(5),
        }

    def _most_connected(self, n: int = 5) -> List[Dict[str, Any]]:
        """Find the most connected entities."""
        counts = [(eid, len(edges)) for eid, edges in self._adjacency.items()]
        counts.sort(key=lambda x: x[1], reverse=True)
        result = []
        for eid, degree in counts[:n]:
            entity = self.entities.get(eid)
            if entity:
                result.append({
                    "name": entity.name,
                    "type": entity.entity_type.value if isinstance(entity.entity_type, EntityType) else str(entity.entity_type),
                    "connections": degree,
                    "importance": entity.importance,
                })
        return result

    def get_visual_graph(
        self,
        center_entity: Optional[str] = None,
        max_nodes: int = 50,
        max_edges: int = 100,
    ) -> Dict[str, Any]:
        """Generate graph data for web UI visualization.

        Returns nodes and edges in a format compatible with D3.js,
        vis.js, or similar graph visualization libraries.
        """
        if center_entity:
            # Subgraph around a specific entity
            entity = self.get_entity(center_entity)
            if not entity:
                return {"nodes": [], "edges": []}
            related = self.get_related(center_entity, max_depth=2)
            node_ids = {entity.entity_id}
            nodes = [self._entity_to_vis_node(entity)]
            edges: List[Dict[str, Any]] = []

            for item in related[:max_nodes - 1]:
                e = Entity.from_dict(item["entity"])
                node_ids.add(e.entity_id)
                nodes.append(self._entity_to_vis_node(e))
                r = item["relationship"]
                if r["source_id"] in node_ids and r["target_id"] in node_ids:
                    edges.append(self._rel_to_vis_edge(r))
                    if len(edges) >= max_edges:
                        break
        else:
            # Full graph (limited)
            # Sort by importance and take top N
            sorted_entities = sorted(
                self.entities.values(),
                key=lambda e: e.importance * e.mention_count,
                reverse=True,
            )[:max_nodes]
            node_ids = {e.entity_id for e in sorted_entities}
            nodes = [self._entity_to_vis_node(e) for e in sorted_entities]
            edges = []
            for rel in self.relationships.values():
                if rel.source_id in node_ids and rel.target_id in node_ids:
                    edges.append(self._rel_to_vis_edge(rel))
                    if len(edges) >= max_edges:
                        break

        return {
            "nodes": nodes,
            "edges": edges,
            "stats": {
                "total_nodes": len(nodes),
                "total_edges": len(edges),
            },
        }

    @staticmethod
    def _entity_to_vis_node(entity: Entity) -> Dict[str, Any]:
        etype = entity.entity_type.value if isinstance(entity.entity_type, EntityType) else str(entity.entity_type)
        return {
            "id": entity.entity_id,
            "label": entity.name,
            "type": etype,
            "importance": entity.importance,
            "mentions": entity.mention_count,
            "size": max(8, min(40, entity.importance * 30 + entity.mention_count)),
            "description": entity.description[:100] if entity.description else "",
        }

    @staticmethod
    def _rel_to_vis_edge(rel: dict) -> Dict[str, Any]:
        return {
            "source": rel["source_id"],
            "target": rel["target_id"],
            "label": rel["relation_type"],
            "weight": rel["weight"],
            "width": max(1, min(6, rel["weight"] * 4)),
        }

    # ───────────────────────────────────────────────────────
    # Maintenance
    # ───────────────────────────────────────────────────────

    def prune(self, min_importance: float = 0.1, min_mentions: int = 1) -> int:
        """Remove low-importance, rarely-mentioned entities."""
        to_remove = []
        for eid, entity in self.entities.items():
            if entity.importance < min_importance and entity.mention_count <= min_mentions:
                # Check if it has significant relationships
                edge_count = len(self._adjacency.get(eid, set()))
                if edge_count <= 1:
                    to_remove.append(eid)

        for eid in to_remove:
            entity = self.entities.get(eid)
            if entity:
                self.remove_entity(entity.name)

        if to_remove:
            self.save()
            logger.info(f"Pruned {len(to_remove)} low-importance entities")

        return len(to_remove)

    def merge_entities(self, primary: str, secondary: str) -> bool:
        """Merge two entities, keeping the primary."""
        p = self.get_entity(primary)
        s = self.get_entity(secondary)
        if not p or not s:
            return False

        # Transfer relationships
        for edge_id in list(self._adjacency.get(s.entity_id, set())):
            rel = self.relationships.get(edge_id)
            if not rel:
                continue
            if rel.source_id == s.entity_id:
                rel.source_id = p.entity_id
            if rel.target_id == s.entity_id:
                rel.target_id = p.entity_id
            self._adjacency[p.entity_id].add(edge_id)

        # Merge data
        p.mention_count += s.mention_count
        p.importance = max(p.importance, s.importance)
        for alias in s.aliases:
            if alias.lower() not in self._alias_index:
                p.aliases.append(alias)
                self._alias_index[alias.lower()] = p.entity_id
        if s.description and not p.description:
            p.description = s.description
        p.properties.update(s.properties)
        p.contexts.extend(s.contexts)
        p.contexts = p.contexts[-20:]

        # Remove secondary
        self._name_index.pop(s.name.lower(), None)
        for alias in s.aliases:
            self._alias_index.pop(alias.lower(), None)
        etype = s.entity_type.value if isinstance(s.entity_type, EntityType) else str(s.entity_type)
        self._type_index[etype].discard(s.entity_id)
        self._adjacency.pop(s.entity_id, None)
        del self.entities[s.entity_id]

        self.save()
        return True

    def shutdown(self) -> None:
        """Clean shutdown."""
        self.save()
        logger.info("KnowledgeGraph: shutdown complete")
