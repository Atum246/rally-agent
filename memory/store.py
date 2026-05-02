"""
🟣 Rally Agent — Memory Store
Vector-semantic memory with hybrid search, consolidation, and encryption.

Features:
- Vector embeddings (sentence-transformers) with TF-IDF fallback
- ChromaDB or in-memory vector store
- Conversation chunking for searchable segments
- RAG context injection for relevant memories
- Multi-signal ranking: recency + relevance + importance
- Periodic memory consolidation via LLM summarization
- Memory categories: conversation, knowledge, preferences, corrections, goals
- Export/import with encryption at rest
- Health stats: size, hit rate, usefulness tracking
- Persistent JSON + binary embedding index
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import struct
import time
import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import (
    Any,
    Callable,
    Coroutine,
    Dict,
    List,
    Literal,
    Optional,
    Protocol,
    Sequence,
    Tuple,
    TypeAlias,
    Union,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional-dependency imports with graceful fallbacks
# ---------------------------------------------------------------------------

try:
    import numpy as np

    HAS_NUMPY = True
except ImportError:
    np = None  # type: ignore[assignment]
    HAS_NUMPY = False

try:
    from sentence_transformers import SentenceTransformer

    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    SentenceTransformer = None  # type: ignore[assignment,misc]
    HAS_SENTENCE_TRANSFORMERS = False

try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings

    HAS_CHROMADB = True
except ImportError:
    chromadb = None  # type: ignore[assignment]
    HAS_CHROMADB = False

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

EmbeddingVector: TypeAlias = List[float]
JsonDict: TypeAlias = Dict[str, Any]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"
DEFAULT_CHUNK_SIZE = 512  # characters
DEFAULT_CHUNK_OVERLAP = 64
DEFAULT_TOP_K = 10
ENCRYPTION_MARKER = "__encrypted__"
EMBEDDING_INDEX_EXT = ".embidx"


# ---------------------------------------------------------------------------
# Enums & data classes
# ---------------------------------------------------------------------------


class MemoryCategory(str, Enum):
    """Semantic category for a memory entry."""

    CONVERSATION = "conversation"
    KNOWLEDGE = "knowledge"
    PREFERENCES = "preferences"
    CORRECTIONS = "corrections"
    GOALS = "goals"
    SYSTEM = "system"


@dataclass
class MemoryEntry:
    """Single memory entry with optional embedding."""

    content: str
    role: str = "system"
    category: MemoryCategory = MemoryCategory.CONVERSATION
    metadata: JsonDict = field(default_factory=dict)
    id: str = ""
    timestamp: str = ""
    embedding: Optional[EmbeddingVector] = None
    importance: float = 0.5  # 0.0 – 1.0
    access_count: int = 0
    last_accessed: str = ""
    source: str = ""  # e.g. file path, conversation id

    def __post_init__(self) -> None:
        if not self.id:
            raw = f"{time.time_ns()}{self.content}{self.role}"
            self.id = hashlib.sha256(raw.encode()).hexdigest()[:16]
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()
        if not self.last_accessed:
            self.last_accessed = self.timestamp

    # -- serialisation --------------------------------------------------------

    def to_dict(self, *, include_embedding: bool = False) -> JsonDict:
        d: JsonDict = {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "category": self.category.value,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
            "importance": self.importance,
            "access_count": self.access_count,
            "last_accessed": self.last_accessed,
            "source": self.source,
        }
        if include_embedding and self.embedding is not None:
            d["embedding"] = self.embedding
        return d

    @classmethod
    def from_dict(cls, data: JsonDict) -> "MemoryEntry":
        cat = data.get("category", "conversation")
        if isinstance(cat, str):
            try:
                cat = MemoryCategory(cat)
            except ValueError:
                cat = MemoryCategory.CONVERSATION
        return cls(
            content=data["content"],
            role=data.get("role", "system"),
            category=cat,
            metadata=data.get("metadata", {}),
            id=data.get("id", ""),
            timestamp=data.get("timestamp", ""),
            embedding=data.get("embedding"),
            importance=data.get("importance", 0.5),
            access_count=data.get("access_count", 0),
            last_accessed=data.get("last_accessed", ""),
            source=data.get("source", ""),
        )


@dataclass
class SearchResult:
    """A scored search result."""

    entry: MemoryEntry
    score: float
    match_type: str = "hybrid"  # vector | keyword | hybrid


@dataclass
class MemoryStats:
    """Health / usage statistics for the memory store."""

    total_entries: int = 0
    entries_by_category: Dict[str, int] = field(default_factory=dict)
    entries_by_role: Dict[str, int] = field(default_factory=dict)
    embedding_count: int = 0
    total_searches: int = 0
    cache_hits: int = 0
    avg_search_ms: float = 0.0
    store_size_bytes: int = 0
    oldest_entry: Optional[str] = None
    newest_entry: Optional[str] = None


# ---------------------------------------------------------------------------
# Embedding backends (pluggable)
# ---------------------------------------------------------------------------


class EmbeddingBackend(Protocol):
    """Protocol for embedding providers."""

    def encode(self, texts: List[str]) -> List[EmbeddingVector]: ...
    @property
    def dimension(self) -> int: ...
    @property
    def name(self) -> str: ...


class SentenceTransformerBackend:
    """Local sentence-transformers embedding."""

    def __init__(self, model_name: str = DEFAULT_EMBEDDING_MODEL) -> None:
        if not HAS_SENTENCE_TRANSFORMERS:
            raise RuntimeError("sentence-transformers not installed")
        logger.info("Loading embedding model: %s", model_name)
        self._model = SentenceTransformer(model_name)
        self._dim: int = self._model.get_sentence_embedding_dimension()

    def encode(self, texts: List[str]) -> List[EmbeddingVector]:
        vectors = self._model.encode(texts, show_progress_bar=False, normalize_embeddings=True)
        return [v.tolist() for v in vectors]

    @property
    def dimension(self) -> int:
        return self._dim

    @property
    def name(self) -> str:
        return f"sentence-transformers({DEFAULT_EMBEDDING_MODEL})"


class TFIDFBackend:
    """Lightweight TF-IDF fallback when sentence-transformers is unavailable."""

    def __init__(self, dim: int = 384) -> None:
        self._dim = dim
        self._idf: Dict[str, float] = {}
        self._vocab: Dict[str, int] = {}
        self._doc_count = 0

    def _tokenize(self, text: str) -> List[str]:
        return text.lower().split()

    def _build_vocab(self, texts: List[str]) -> None:
        df: Counter = Counter()
        for text in texts:
            tokens = set(self._tokenize(text))
            for t in tokens:
                df[t] += 1
        self._doc_count = len(texts)
        for term, freq in df.items():
            if term not in self._vocab:
                self._vocab[term] = len(self._vocab) % self._dim
            self._idf[term] = math.log((self._doc_count + 1) / (freq + 1)) + 1

    def _vectorize(self, text: str) -> EmbeddingVector:
        vec = [0.0] * self._dim
        tokens = self._tokenize(text)
        tf: Counter = Counter(tokens)
        total = len(tokens) or 1
        for term, count in tf.items():
            idx = self._vocab.get(term)
            if idx is not None:
                idf = self._idf.get(term, 1.0)
                vec[idx] = (count / total) * idf
        # L2 normalise
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]

    def encode(self, texts: List[str]) -> List[EmbeddingVector]:
        self._build_vocab(texts)
        return [self._vectorize(t) for t in texts]

    @property
    def dimension(self) -> int:
        return self._dim

    @property
    def name(self) -> str:
        return "tfidf-fallback"


def _get_embedding_backend(model_name: str = DEFAULT_EMBEDDING_MODEL) -> EmbeddingBackend:
    """Pick best available embedding backend."""
    if HAS_SENTENCE_TRANSFORMERS:
        try:
            return SentenceTransformerBackend(model_name)
        except Exception as exc:
            logger.warning("Failed to load sentence-transformers (%s), using TF-IDF fallback", exc)
    return TFIDFBackend()


# ---------------------------------------------------------------------------
# Vector store backends (pluggable)
# ---------------------------------------------------------------------------


class VectorStore(Protocol):
    """Protocol for vector storage backends."""

    def add(self, ids: List[str], vectors: List[EmbeddingVector], metadatas: List[JsonDict]) -> None: ...
    def query(self, vector: EmbeddingVector, top_k: int) -> Tuple[List[str], List[float]]: ...
    def delete(self, ids: List[str]) -> None: ...
    def count(self) -> int: ...
    def save(self) -> None: ...
    def load(self) -> None: ...


class InMemoryVectorStore:
    """Simple numpy-backed in-memory vector store with brute-force cosine search."""

    def __init__(self) -> None:
        self._ids: List[str] = []
        self._vectors: List[EmbeddingVector] = []
        self._metadatas: List[JsonDict] = []

    def add(self, ids: List[str], vectors: List[EmbeddingVector], metadatas: List[JsonDict]) -> None:
        for id_, vec, meta in zip(ids, vectors, metadatas):
            self._ids.append(id_)
            self._vectors.append(vec)
            self._metadatas.append(meta)

    def query(self, vector: EmbeddingVector, top_k: int = DEFAULT_TOP_K) -> Tuple[List[str], List[float]]:
        if not self._vectors:
            return [], []

        if HAS_NUMPY:
            q = np.array(vector, dtype=np.float32)
            mat = np.array(self._vectors, dtype=np.float32)
            sims = mat @ q  # cosine (already normalised)
            k = min(top_k, len(self._ids))
            idxs = np.argpartition(-sims, k)[:k]
            idxs = idxs[np.argsort(-sims[idxs])]
            return [self._ids[i] for i in idxs], [float(sims[i]) for i in idxs]

        # Pure Python fallback
        scores: List[Tuple[float, int]] = []
        for i, v in enumerate(self._vectors):
            dot = sum(a * b for a, b in zip(vector, v))
            scores.append((dot, i))
        scores.sort(reverse=True)
        top = scores[:top_k]
        return [self._ids[i] for _, i in top], [s for s, _ in top]

    def delete(self, ids: List[str]) -> None:
        id_set = set(ids)
        new_data = [
            (i, v, m)
            for i, v, m in zip(self._ids, self._vectors, self._metadatas)
            if i not in id_set
        ]
        if new_data:
            self._ids, self._vectors, self._metadatas = zip(*new_data)
            self._ids = list(self._ids)
            self._vectors = list(self._vectors)
            self._metadatas = list(self._metadatas)
        else:
            self._ids, self._vectors, self._metadatas = [], [], []

    def count(self) -> int:
        return len(self._ids)

    def save(self) -> None:
        pass  # In-memory; nothing to persist (embeddings stored in MemoryEntry)

    def load(self) -> None:
        pass


class ChromaVectorStore:
    """ChromaDB-backed persistent vector store."""

    COLLECTION_NAME = "rally_memories"

    def __init__(self, persist_dir: str) -> None:
        if not HAS_CHROMADB:
            raise RuntimeError("chromadb not installed")
        os.makedirs(persist_dir, exist_ok=True)
        self._client = chromadb.Client(
            ChromaSettings(
                chroma_db_impl="duckdb+parquet",
                persist_directory=persist_dir,
                anonymized_telemetry=False,
            )
        )
        self._collection = self._client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

    def add(self, ids: List[str], vectors: List[EmbeddingVector], metadatas: List[JsonDict]) -> None:
        self._collection.upsert(ids=ids, embeddings=vectors, metadatas=metadatas)

    def query(self, vector: EmbeddingVector, top_k: int = DEFAULT_TOP_K) -> Tuple[List[str], List[float]]:
        results = self._collection.query(query_embeddings=[vector], n_results=top_k)
        ids = results.get("ids", [[]])[0]
        dists = results.get("distances", [[]])[0]
        # ChromaDB returns distances; convert to similarity
        sims = [1.0 - d for d in dists]
        return ids, sims

    def delete(self, ids: List[str]) -> None:
        if ids:
            self._collection.delete(ids=ids)

    def count(self) -> int:
        return self._collection.count()

    def save(self) -> None:
        self._client.persist()

    def load(self) -> None:
        pass  # ChromaDB auto-loads


def _get_vector_store(persist_dir: str) -> VectorStore:
    """Pick best available vector store."""
    if HAS_CHROMADB:
        try:
            return ChromaVectorStore(persist_dir)
        except Exception as exc:
            logger.warning("ChromaDB init failed (%s), using in-memory store", exc)
    return InMemoryVectorStore()


# ---------------------------------------------------------------------------
# Encryption helpers
# ---------------------------------------------------------------------------


class _SimpleEncryptor:
    """XOR-based obfuscation (NOT cryptographically secure — for casual at-rest protection).

    For production, swap with Fernet / AES-GCM via the `cryptography` package.
    """

    def __init__(self, key: str = "rally-agent-default-key") -> None:
        self._key = key.encode()

    def encrypt(self, plaintext: str) -> str:
        data = plaintext.encode("utf-8")
        key_bytes = self._key
        encrypted = bytes(b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(data))
        import base64

        return ENCRYPTION_MARKER + base64.b64encode(encrypted).decode("ascii")

    def decrypt(self, ciphertext: str) -> str:
        if not ciphertext.startswith(ENCRYPTION_MARKER):
            return ciphertext
        import base64

        raw = base64.b64decode(ciphertext[len(ENCRYPTION_MARKER) :])
        key_bytes = self._key
        decrypted = bytes(b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(raw))
        return decrypted.decode("utf-8")

    @staticmethod
    def is_encrypted(text: str) -> bool:
        return text.startswith(ENCRYPTION_MARKER)


# ---------------------------------------------------------------------------
# Text chunking
# ---------------------------------------------------------------------------


def chunk_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> List[str]:
    """Split text into overlapping chunks by character count.

    Tries to break at paragraph or sentence boundaries when possible.
    """
    if len(text) <= chunk_size:
        return [text]
    chunks: List[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))

        # Try paragraph break
        if end < len(text):
            para_break = text.rfind("\n\n", start, end)
            if para_break > start + chunk_size // 2:
                end = para_break + 2
            else:
                # Try sentence boundary
                for delim in (". ", "! ", "? ", "\n"):
                    sent_break = text.rfind(delim, start + chunk_size // 2, end)
                    if sent_break > start:
                        end = sent_break + len(delim)
                        break

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = max(start + 1, end - chunk_overlap)
    return chunks


# ---------------------------------------------------------------------------
# BM25 keyword scorer
# ---------------------------------------------------------------------------


class BM25Scorer:
    """Okapi BM25 scorer for keyword search."""

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self._k1 = k1
        self._b = b
        self._doc_freqs: Dict[str, int] = {}
        self._doc_lens: List[int] = []
        self._avg_dl: float = 0.0
        self._num_docs: int = 0
        self._tf: List[Dict[str, int]] = []

    def index(self, documents: List[str]) -> None:
        self._num_docs = len(documents)
        self._doc_freqs.clear()
        self._doc_lens.clear()
        self._tf.clear()
        total_len = 0
        for doc in documents:
            tokens = doc.lower().split()
            self._doc_lens.append(len(tokens))
            total_len += len(tokens)
            tf: Counter = Counter(tokens)
            self._tf.append(dict(tf))
            for term in set(tokens):
                self._doc_freqs[term] = self._doc_freqs.get(term, 0) + 1
        self._avg_dl = total_len / self._num_docs if self._num_docs else 1.0

    def score(self, query: str, doc_idx: int) -> float:
        tokens = query.lower().split()
        dl = self._doc_lens[doc_idx]
        tf_map = self._tf[doc_idx]
        score = 0.0
        for term in tokens:
            if term not in tf_map:
                continue
            tf = tf_map[term]
            df = self._doc_freqs.get(term, 0)
            idf = math.log((self._num_docs - df + 0.5) / (df + 0.5) + 1.0)
            num = tf * (self._k1 + 1)
            denom = tf + self._k1 * (1 - self._b + self._b * dl / self._avg_dl)
            score += idf * (num / denom)
        return score


    def score_all(self, query: str) -> List[Tuple[int, float]]:
        """Score all indexed documents. Returns list of (index, score)."""
        results = []
        for i in range(self._num_docs):
            s = self.score(query, i)
            if s > 0:
                results.append((i, s))
        results.sort(key=lambda x: x[1], reverse=True)
        return results


# ---------------------------------------------------------------------------
# Memory Store — the main class
# ---------------------------------------------------------------------------


class MemoryStore:
    """Vector-semantic memory store with hybrid search, RAG injection,
    consolidation, encryption, and health stats."""

    def __init__(
        self,
        config: Any = None,
        *,
        data_dir: Optional[str] = None,
        embedding_model: str = DEFAULT_EMBEDDING_MODEL,
        encryption_key: Optional[str] = None,
        max_entries: int = 10_000,
        auto_consolidate: bool = True,
        enable_encryption: bool = False,
    ) -> None:
        # Accept either a RallyConfig object or plain kwargs
        if config is not None:
            self._data_dir = data_dir or os.path.expanduser("~/.rally-agent/data")
            self._max_entries = getattr(config, "get", lambda k, d=None: d)("memory.max_entries", max_entries)
            self._auto_consolidate = getattr(config, "get", lambda k, d=None: d)("memory.auto_consolidate", auto_consolidate)
            self._enable_encryption = getattr(config, "get", lambda k, d=None: d)("memory.encryption", enable_encryption)
            self._backend_name = getattr(config, "get", lambda k, d=None: d)("memory.backend", "hybrid")
        else:
            self._data_dir = data_dir or os.path.expanduser("~/.rally-agent/data")
            self._max_entries = max_entries
            self._auto_consolidate = auto_consolidate
            self._enable_encryption = enable_encryption
            self._backend_name = "hybrid"

        os.makedirs(self._data_dir, exist_ok=True)

        self._store_file = os.path.join(self._data_dir, "memory.json")
        self._index_file = os.path.join(self._data_dir, f"memory{EMBEDDING_INDEX_EXT}")

        # Entries
        self._entries: Dict[str, MemoryEntry] = {}
        self._entry_order: List[str] = []  # insertion order

        # Embedding / vector
        self._embedder: Optional[EmbeddingBackend] = None
        self._vector_store: Optional[VectorStore] = None
        self._embeddings_dirty = False

        # BM25 index
        self._bm25 = BM25Scorer()
        self._bm25_dirty = True

        # Encryption
        self._encryptor = _SimpleEncryptor(encryption_key) if encryption_key or self._enable_encryption else None

        # Stats
        self._stats = MemoryStats()
        self._search_times: List[float] = []

        # Load persisted data
        self._load()

        logger.info(
            "MemoryStore initialised: %d entries, backend=%s, encryption=%s",
            len(self._entries),
            self._backend_name,
            self._enable_encryption,
        )

    # -- lazy initialisation --------------------------------------------------

    def _ensure_embedder(self) -> EmbeddingBackend:
        if self._embedder is None:
            self._embedder = _get_embedding_backend()
            logger.info("Embedding backend: %s", self._embedder.name)
        return self._embedder

    def _ensure_vector_store(self) -> VectorStore:
        if self._vector_store is None:
            persist_dir = os.path.join(self._data_dir, "vectorstore")
            self._vector_store = _get_vector_store(persist_dir)
            # Re-index any entries that have embeddings
            self._reindex_vectors()
        return self._vector_store

    def _reindex_vectors(self) -> None:
        """Push all in-memory embeddings into the vector store."""
        ids: List[str] = []
        vecs: List[EmbeddingVector] = []
        metas: List[JsonDict] = []
        for entry in self._entries.values():
            if entry.embedding is not None:
                ids.append(entry.id)
                vecs.append(entry.embedding)
                metas.append({"category": entry.category.value, "role": entry.role})
        if ids:
            self._vector_store.add(ids, vecs, metas)
            logger.info("Reindexed %d vectors", len(ids))

    # -- persistence ----------------------------------------------------------

    def _load(self) -> None:
        """Load entries from JSON + optional binary embedding index."""
        if not os.path.exists(self._store_file):
            return
        try:
            with open(self._store_file, "r", encoding="utf-8") as f:
                data: List[JsonDict] = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("Failed to load memory store: %s", exc)
            return

        # Load embeddings from binary index if present
        embeddings: Dict[str, EmbeddingVector] = {}
        if os.path.exists(self._index_file):
            embeddings = self._load_embedding_index()

        for item in data:
            entry = MemoryEntry.from_dict(item)
            # Decrypt if needed
            if self._encryptor and _SimpleEncryptor.is_encrypted(entry.content):
                try:
                    entry.content = self._encryptor.decrypt(entry.content)
                except Exception:
                    pass
            # Attach embedding
            if entry.id in embeddings:
                entry.embedding = embeddings[entry.id]
            self._entries[entry.id] = entry
            self._entry_order.append(entry.id)

        self._bm25_dirty = True
        logger.info("Loaded %d memory entries", len(self._entries))

    def _load_embedding_index(self) -> Dict[str, EmbeddingVector]:
        """Load binary embedding index: {id: [float, ...]}."""
        embeddings: Dict[str, EmbeddingVector] = {}
        try:
            with open(self._index_file, "rb") as f:
                count = struct.unpack("<I", f.read(4))[0]
                for _ in range(count):
                    id_len = struct.unpack("<H", f.read(2))[0]
                    entry_id = f.read(id_len).decode("utf-8")
                    vec_len = struct.unpack("<I", f.read(4))[0]
                    vec = list(struct.unpack(f"<{vec_len}f", f.read(vec_len * 4)))
                    embeddings[entry_id] = vec
        except Exception as exc:
            logger.warning("Failed to load embedding index: %s", exc)
        return embeddings

    def save(self) -> None:
        """Persist entries to JSON and embeddings to binary index."""
        # Trim to max
        if len(self._entries) > self._max_entries:
            self._consolidate()

        # Prepare JSON data (without embeddings — too large for JSON)
        data = [e.to_dict(include_embedding=False) for e in self._ordered_entries()]

        # Encrypt sensitive content
        if self._encryptor:
            for item in data:
                if item.get("category") in ("preferences", "corrections"):
                    item["content"] = self._encryptor.encrypt(item["content"])

        tmp = self._store_file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, self._store_file)

        # Binary embedding index
        self._save_embedding_index()

        # Persist vector store
        if self._vector_store is not None:
            self._vector_store.save()

    def _save_embedding_index(self) -> None:
        """Write a compact binary file of entry-id → vector mappings."""
        entries_with_emb = [
            (e.id, e.embedding)
            for e in self._entries.values()
            if e.embedding is not None
        ]
        if not entries_with_emb:
            return
        tmp = self._index_file + ".tmp"
        with open(tmp, "wb") as f:
            f.write(struct.pack("<I", len(entries_with_emb)))
            for entry_id, vec in entries_with_emb:
                id_bytes = entry_id.encode("utf-8")
                f.write(struct.pack("<H", len(id_bytes)))
                f.write(id_bytes)
                f.write(struct.pack("<I", len(vec)))
                f.write(struct.pack(f"<{len(vec)}f", *vec))
        os.replace(tmp, self._index_file)

    # -- helpers --------------------------------------------------------------

    def _ordered_entries(self) -> List[MemoryEntry]:
        return [self._entries[eid] for eid in self._entry_order if eid in self._entries]

    def _ensure_bm25(self) -> None:
        if self._bm25_dirty:
            entries = self._ordered_entries()
            self._bm25.index([e.content for e in entries])
            self._bm25_dirty = False

    # -- public API: add / update / delete ------------------------------------

    def add(
        self,
        role: str,
        content: str,
        *,
        category: Union[MemoryCategory, str] = MemoryCategory.CONVERSATION,
        metadata: Optional[JsonDict] = None,
        importance: float = 0.5,
        source: str = "",
        chunk: bool = True,
    ) -> List[MemoryEntry]:
        """Add one or more memory entries (auto-chunks long content).

        Returns the created MemoryEntry objects.
        """
        if isinstance(category, str):
            try:
                category = MemoryCategory(category)
            except ValueError:
                category = MemoryCategory.CONVERSATION

        chunks = chunk_text(content) if chunk else [content]
        created: List[MemoryEntry] = []

        for chunk_text_str in chunks:
            entry = MemoryEntry(
                content=chunk_text_str,
                role=role,
                category=category,
                metadata=metadata or {},
                importance=importance,
                source=source,
            )
            self._entries[entry.id] = entry
            self._entry_order.append(entry.id)
            created.append(entry)

        self._bm25_dirty = True

        # Auto-consolidate
        if self._auto_consolidate and len(self._entries) > self._max_entries:
            self._consolidate()

        # Periodic save
        if len(self._entries) % 20 == 0:
            self.save()

        return created

    def update(self, entry_id: str, **kwargs: Any) -> bool:
        """Update fields on an existing entry."""
        entry = self._entries.get(entry_id)
        if entry is None:
            return False
        for key, value in kwargs.items():
            if hasattr(entry, key):
                setattr(entry, key, value)
        if "content" in kwargs:
            self._bm25_dirty = True
            entry.embedding = None  # invalidate
        return True

    def delete(self, entry_id: str) -> bool:
        """Delete a single entry."""
        if entry_id not in self._entries:
            return False
        del self._entries[entry_id]
        self._entry_order = [eid for eid in self._entry_order if eid != entry_id]
        if self._vector_store:
            self._vector_store.delete([entry_id])
        self._bm25_dirty = True
        return True

    def clear(self) -> int:
        """Clear all memory. Returns count of deleted entries."""
        count = len(self._entries)
        self._entries.clear()
        self._entry_order.clear()
        self._bm25 = BM25Scorer()
        self._bm25_dirty = True
        if self._vector_store:
            # Recreate
            persist_dir = os.path.join(self._data_dir, "vectorstore")
            self._vector_store = _get_vector_store(persist_dir)
        self.save()
        return count

    # -- public API: search ---------------------------------------------------

    def search(
        self,
        query: str,
        *,
        limit: int = DEFAULT_TOP_K,
        category: Optional[Union[MemoryCategory, str]] = None,
        role: Optional[str] = None,
        mode: Literal["hybrid", "vector", "keyword"] = "hybrid",
    ) -> List[SearchResult]:
        """Hybrid search combining vector similarity + BM25 keyword scoring.

        Returns SearchResult objects sorted by composite score.
        """
        t0 = time.monotonic()
        results: Dict[str, SearchResult] = {}

        entries = self._ordered_entries()

        # Apply filters
        if category:
            if isinstance(category, str):
                try:
                    category = MemoryCategory(category)
                except ValueError:
                    category = None
        if category:
            entries = [e for e in entries if e.category == category]
        if role:
            entries = [e for e in entries if e.role == role]

        entry_map = {e.id: e for e in entries}

        # -- Vector search --
        if mode in ("hybrid", "vector"):
            try:
                emb_results = self._vector_search(query, limit * 3)
                for entry_id, sim in emb_results:
                    entry = entry_map.get(entry_id)
                    if entry is None:
                        continue
                    results[entry_id] = SearchResult(
                        entry=entry,
                        score=sim,
                        match_type="vector",
                    )
            except Exception as exc:
                logger.debug("Vector search unavailable: %s", exc)
                if mode == "vector":
                    # Fall through to keyword
                    mode = "keyword"

        # -- Keyword / BM25 search --
        if mode in ("hybrid", "keyword"):
            self._ensure_bm25()
            bm25_scores: List[Tuple[str, float]] = []
            for i, eid in enumerate(self._entry_order):
                if eid not in entry_map:
                    continue
                s = self._bm25.score(query, i)
                if s > 0:
                    bm25_scores.append((eid, s))
            bm25_scores.sort(key=lambda x: x[1], reverse=True)

            # Normalise BM25 scores to 0-1
            if bm25_scores:
                max_bm25 = bm25_scores[0][1]
                for eid, s in bm25_scores[: limit * 3]:
                    normed = s / max_bm25 if max_bm25 > 0 else 0
                    if eid in results:
                        # Merge: weighted average
                        old = results[eid]
                        old.score = old.score * 0.6 + normed * 0.4
                        old.match_type = "hybrid"
                    else:
                        entry = entry_map.get(eid)
                        if entry:
                            results[eid] = SearchResult(
                                entry=entry,
                                score=normed * 0.4,
                                match_type="keyword",
                            )

        # -- Recency & importance boosting --
        now = datetime.now(timezone.utc)
        for sr in results.values():
            try:
                ts = datetime.fromisoformat(sr.entry.timestamp)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                age_hours = (now - ts).total_seconds() / 3600
                recency = max(0.0, 1.0 - age_hours / (24 * 30))  # decay over 30 days
            except Exception:
                recency = 0.0

            importance = sr.entry.importance
            sr.score = sr.score * 0.6 + recency * 0.2 + importance * 0.2

            # Track access
            sr.entry.access_count += 1
            sr.entry.last_accessed = now.isoformat()

        # Sort & trim
        sorted_results = sorted(results.values(), key=lambda r: r.score, reverse=True)[:limit]

        # Update stats
        elapsed = (time.monotonic() - t0) * 1000
        self._search_times.append(elapsed)
        self._stats.total_searches += 1

        return sorted_results

    def _vector_search(self, query: str, limit: int) -> List[Tuple[str, float]]:
        """Execute vector similarity search."""
        store = self._ensure_vector_store()
        embedder = self._ensure_embedder()

        # Ensure all entries have embeddings
        self._embed_pending()

        if store.count() == 0:
            return []

        q_vec = embedder.encode([query])[0]
        ids, scores = store.query(q_vec, limit)
        return list(zip(ids, scores))

    def _embed_pending(self) -> None:
        """Generate embeddings for entries that don't have them yet."""
        embedder = self._ensure_embedder()
        store = self._ensure_vector_store()

        pending = [e for e in self._entries.values() if e.embedding is None]
        if not pending:
            return

        # Batch encode
        texts = [e.content for e in pending]
        try:
            vectors = embedder.encode(texts)
        except Exception as exc:
            logger.error("Embedding generation failed: %s", exc)
            return

        ids: List[str] = []
        metas: List[JsonDict] = []
        for entry, vec in zip(pending, vectors):
            entry.embedding = vec
            ids.append(entry.id)
            metas.append({"category": entry.category.value, "role": entry.role})

        store.add(ids, vectors, metas)
        self._embeddings_dirty = True
        logger.debug("Embedded %d pending entries", len(pending))

    # -- public API: RAG context injection ------------------------------------

    def build_context(
        self,
        query: str,
        *,
        max_tokens: int = 2000,
        limit: int = DEFAULT_TOP_K,
        include_metadata: bool = True,
    ) -> str:
        """Build a RAG context string from relevant memories.

        Returns a formatted string suitable for injection into an LLM prompt.
        Estimates ~4 chars per token for budget control.
        """
        results = self.search(query, limit=limit)
        if not results:
            return ""

        char_budget = max_tokens * 4
        parts: List[str] = ["[Relevant Memories]"]
        used = len(parts[0])

        for sr in results:
            entry = sr.entry
            line = f"- [{entry.category.value}] {entry.content}"
            if include_metadata and entry.source:
                line += f" (source: {entry.source})"
            if used + len(line) > char_budget:
                break
            parts.append(line)
            used += len(line) + 1  # +1 for newline

        return "\n".join(parts)

    # -- public API: queries --------------------------------------------------

    def get_recent(self, limit: int = 20) -> List[MemoryEntry]:
        return self._ordered_entries()[-limit:]

    def get_by_role(self, role: str, limit: int = 20) -> List[MemoryEntry]:
        return [e for e in self._ordered_entries() if e.role == role][-limit:]

    def get_by_category(self, category: Union[MemoryCategory, str], limit: int = 50) -> List[MemoryEntry]:
        if isinstance(category, str):
            try:
                category = MemoryCategory(category)
            except ValueError:
                return []
        return [e for e in self._ordered_entries() if e.category == category][-limit:]

    def count(self) -> int:
        return len(self._entries)

    # -- public API: consolidation --------------------------------------------

    def consolidate(self, *, llm_fn: Optional[Callable[[str], Coroutine[Any, Any, str]]] = None) -> Optional[str]:
        """Summarise old memories to reclaim space.

        If ``llm_fn`` is provided (async callable: prompt → summary), it will be
        used to generate a human-readable summary of consolidated entries.
        Otherwise old entries are simply archived to a JSON file.

        Returns the summary text (or archive path).
        """
        return asyncio.get_event_loop().run_until_complete(
            self._consolidate_async(llm_fn=llm_fn)
        ) if not asyncio.get_event_loop().is_running() else None

    async def consolidate_async(self, *, llm_fn: Optional[Callable[[str], Coroutine[Any, Any, str]]] = None) -> str:
        """Async version of consolidate."""
        return await self._consolidate_async(llm_fn=llm_fn)

    async def _consolidate_async(self, *, llm_fn: Optional[Callable[[str], Coroutine[Any, Any, str]]] = None) -> str:
        entries = self._ordered_entries()
        if len(entries) <= self._max_entries * 0.8:
            return "No consolidation needed"

        # Keep the newest 80%, archive the rest
        keep_count = int(self._max_entries * 0.8)
        old_entries = entries[:-keep_count]
        keep_entries = entries[-keep_count:]

        summary_text = ""
        if llm_fn and old_entries:
            # Build summarisation prompt
            texts = [f"[{e.category.value}] {e.role}: {e.content[:200]}" for e in old_entries[:100]]
            prompt = (
                "Summarise the following memory entries into concise key facts. "
                "Preserve important information, preferences, corrections, and goals.\n\n"
                + "\n".join(texts)
            )
            try:
                summary_text = await llm_fn(prompt)
            except Exception as exc:
                logger.error("LLM summarisation failed: %s", exc)

        # Archive old entries
        archive_file = os.path.join(self._data_dir, f"memory_archive_{int(time.time())}.json")
        with open(archive_file, "w", encoding="utf-8") as f:
            json.dump([e.to_dict() for e in old_entries], f, indent=2, ensure_ascii=False)

        # If we got a summary, store it as a knowledge entry
        if summary_text:
            summary_entry = MemoryEntry(
                content=summary_text,
                role="system",
                category=MemoryCategory.KNOWLEDGE,
                importance=0.8,
                source=f"consolidation:{archive_file}",
                metadata={"consolidated_count": len(old_entries)},
            )
            self._entries[summary_entry.id] = summary_entry
            keep_entries.append(summary_entry)

        # Rebuild
        self._entries = {e.id: e for e in keep_entries}
        self._entry_order = [e.id for e in keep_entries]
        self._bm25_dirty = True

        # Re-index vectors
        if self._vector_store:
            old_ids = [e.id for e in old_entries]
            self._vector_store.delete(old_ids)

        self.save()
        logger.info("Consolidated %d entries, kept %d", len(old_entries), len(keep_entries))

        return summary_text or f"Archived {len(old_entries)} entries to {archive_file}"

    def _consolidate(self) -> None:
        """Sync wrapper for auto-consolidation (no LLM)."""
        entries = self._ordered_entries()
        if len(entries) <= self._max_entries:
            return
        keep_count = int(self._max_entries * 0.8)
        old_entries = entries[:-keep_count]
        keep_entries = entries[-keep_count:]

        archive_file = os.path.join(self._data_dir, f"memory_archive_{int(time.time())}.json")
        with open(archive_file, "w", encoding="utf-8") as f:
            json.dump([e.to_dict() for e in old_entries], f, indent=2, ensure_ascii=False)

        self._entries = {e.id: e for e in keep_entries}
        self._entry_order = [e.id for e in keep_entries]
        self._bm25_dirty = True
        self.save()

    # -- public API: export / import ------------------------------------------

    def export(
        self,
        path: str,
        *,
        include_embeddings: bool = False,
        encrypt_sensitive: bool = False,
    ) -> int:
        """Export memory to a JSON file. Returns count of exported entries."""
        entries = self._ordered_entries()
        data = [e.to_dict(include_embedding=include_embeddings) for e in entries]

        if encrypt_sensitive and self._encryptor:
            for item in data:
                if item.get("category") in ("preferences", "corrections"):
                    item["content"] = self._encryptor.encrypt(item["content"])

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return len(data)

    def import_entries(self, path: str, *, decrypt: bool = False) -> int:
        """Import memory from a JSON file. Returns count of imported entries."""
        with open(path, "r", encoding="utf-8") as f:
            data: List[JsonDict] = json.load(f)

        count = 0
        for item in data:
            entry = MemoryEntry.from_dict(item)
            if decrypt and self._encryptor and _SimpleEncryptor.is_encrypted(entry.content):
                try:
                    entry.content = self._encryptor.decrypt(entry.content)
                except Exception:
                    pass
            if entry.id not in self._entries:
                self._entries[entry.id] = entry
                self._entry_order.append(entry.id)
                count += 1

        self._bm25_dirty = True
        self.save()
        return count

    # -- public API: stats / health -------------------------------------------

    def stats(self) -> MemoryStats:
        """Compute and return health/usage statistics."""
        entries = self._ordered_entries()
        cat_counts: Dict[str, int] = defaultdict(int)
        role_counts: Dict[str, int] = defaultdict(int)
        emb_count = 0

        for e in entries:
            cat_counts[e.category.value] += 1
            role_counts[e.role] += 1
            if e.embedding is not None:
                emb_count += 1

        store_size = 0
        for fpath in [self._store_file, self._index_file]:
            if os.path.exists(fpath):
                store_size += os.path.getsize(fpath)

        avg_ms = (sum(self._search_times[-100:]) / len(self._search_times[-100:])) if self._search_times else 0.0

        return MemoryStats(
            total_entries=len(entries),
            entries_by_category=dict(cat_counts),
            entries_by_role=dict(role_counts),
            embedding_count=emb_count,
            total_searches=self._stats.total_searches,
            cache_hits=self._stats.cache_hits,
            avg_search_ms=round(avg_ms, 2),
            store_size_bytes=store_size,
            oldest_entry=entries[0].timestamp if entries else None,
            newest_entry=entries[-1].timestamp if entries else None,
        )

    def show_stats(self) -> None:
        """Pretty-print memory statistics (CLI)."""
        try:
            from cli.theme import Theme, console

            s = self.stats()
            table = Theme.create_table("🧠 Memory Statistics")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="neon_green")
            table.add_row("Total Entries", str(s.total_entries))
            table.add_row("Embeddings", str(s.embedding_count))
            table.add_row("Total Searches", str(s.total_searches))
            table.add_row("Avg Search (ms)", str(s.avg_search_ms))
            size_kb = s.store_size_bytes / 1024
            table.add_row("Store Size", f"{size_kb:.1f} KB")
            for cat, cnt in s.entries_by_category.items():
                table.add_row(f"  {cat}", str(cnt))
            if s.oldest_entry:
                table.add_row("Oldest", s.oldest_entry[:19])
            if s.newest_entry:
                table.add_row("Newest", s.newest_entry[:19])
            console.print()
            console.print(table)
            console.print()
        except ImportError:
            s = self.stats()
            print(f"🧠 Memory: {s.total_entries} entries, {s.embedding_count} embedded, {s.total_searches} searches")
