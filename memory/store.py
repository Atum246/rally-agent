"""
🟣 Rally Agent — Memory System
Hybrid memory: local files + semantic search
"""

import os
import json
import time
import hashlib
from pathlib import Path
from typing import Optional
from datetime import datetime

from cli.theme import Theme, console, Colors


class MemoryEntry:
    """Single memory entry"""

    def __init__(self, role: str, content: str, metadata: dict = None):
        self.id = hashlib.md5(f"{time.time()}{content}".encode()).hexdigest()[:12]
        self.role = role
        self.content = content
        self.metadata = metadata or {}
        self.timestamp = datetime.now().isoformat()
        self.embedding = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MemoryEntry":
        entry = cls(data["role"], data["content"], data.get("metadata", {}))
        entry.id = data.get("id", entry.id)
        entry.timestamp = data.get("timestamp", entry.timestamp)
        return entry


class MemoryStore:
    """Hybrid memory store with local persistence and semantic search"""

    def __init__(self, config):
        self.config = config
        self.backend = config.get("memory.backend", "hybrid")
        self.max_entries = config.get("memory.max_entries", 10000)
        self.entries: list[MemoryEntry] = []
        self.data_dir = os.path.expanduser("~/.rally-agent/data")
        os.makedirs(self.data_dir, exist_ok=True)
        self.store_file = os.path.join(self.data_dir, "memory.json")
        self._load()

    def _load(self):
        """Load memory from disk"""
        if os.path.exists(self.store_file):
            try:
                with open(self.store_file) as f:
                    data = json.load(f)
                self.entries = [MemoryEntry.from_dict(e) for e in data]
            except Exception:
                self.entries = []

    def save(self):
        """Save memory to disk"""
        data = [e.to_dict() for e in self.entries[-self.max_entries:]]
        with open(self.store_file, "w") as f:
            json.dump(data, f, indent=2)

    def add(self, role: str, content: str, metadata: dict = None):
        """Add a memory entry"""
        entry = MemoryEntry(role, content, metadata)
        self.entries.append(entry)

        # Auto-consolidate if too many entries
        if len(self.entries) > self.max_entries:
            self._consolidate()

        # Periodic save
        if len(self.entries) % 10 == 0:
            self.save()

    def search(self, query: str, limit: int = 10) -> list[dict]:
        """Search memory using keyword matching + relevance scoring"""
        if not self.entries:
            return []

        query_lower = query.lower()
        query_words = set(query_lower.split())

        scored = []
        for entry in self.entries:
            content_lower = entry.content.lower()
            score = 0

            # Exact match bonus
            if query_lower in content_lower:
                score += 10

            # Word match scoring
            for word in query_words:
                if word in content_lower:
                    score += 2

            # Recency bonus (more recent = higher score)
            try:
                entry_time = datetime.fromisoformat(entry.timestamp)
                age_hours = (datetime.now() - entry_time).total_seconds() / 3600
                recency_bonus = max(0, 5 - (age_hours / 24))
                score += recency_bonus
            except Exception:
                pass

            if score > 0:
                scored.append((score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [e.to_dict() for _, e in scored[:limit]]

    def get_recent(self, limit: int = 20) -> list[dict]:
        """Get recent memory entries"""
        return [e.to_dict() for e in self.entries[-limit:]]

    def get_by_role(self, role: str, limit: int = 20) -> list[dict]:
        """Get entries by role"""
        return [e.to_dict() for e in self.entries if e.role == role][-limit:]

    def count(self) -> int:
        """Get total entry count"""
        return len(self.entries)

    def clear(self):
        """Clear all memory"""
        self.entries = []
        self.save()

    def _consolidate(self):
        """Consolidate old entries to save space"""
        # Keep recent entries, summarize old ones
        if len(self.entries) <= self.max_entries:
            return

        # Keep last 80% of entries
        keep_count = int(self.max_entries * 0.8)
        old_entries = self.entries[:-keep_count]
        self.entries = self.entries[-keep_count:]

        # Save summary of old entries
        summary_file = os.path.join(self.data_dir, f"memory_archive_{int(time.time())}.json")
        with open(summary_file, "w") as f:
            json.dump([e.to_dict() for e in old_entries], f, indent=2)

        self.save()

    def show_stats(self):
        """Show memory statistics"""
        table = Theme.create_table("🧠 Memory Statistics")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="neon_green")

        table.add_row("Total Entries", str(len(self.entries)))
        table.add_row("User Messages", str(len([e for e in self.entries if e.role == "user"])))
        table.add_row("Assistant Messages", str(len([e for e in self.entries if e.role == "assistant"])))
        table.add_row("Backend", self.backend)
        table.add_row("Max Entries", str(self.max_entries))
        table.add_row("Store File", self.store_file)

        if self.entries:
            table.add_row("Oldest", self.entries[0].timestamp[:19])
            table.add_row("Newest", self.entries[-1].timestamp[:19])

        console.print()
        console.print(table)
        console.print()

    def export(self, path: str):
        """Export memory to file"""
        data = [e.to_dict() for e in self.entries]
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        Theme.success(f"Exported {len(data)} entries to {path}")

    def import_entries(self, path: str):
        """Import memory from file"""
        with open(path) as f:
            data = json.load(f)
        for entry_data in data:
            entry = MemoryEntry.from_dict(entry_data)
            self.entries.append(entry)
        self.save()
        Theme.success(f"Imported {len(data)} entries")
