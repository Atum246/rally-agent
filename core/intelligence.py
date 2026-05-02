"""
🟣 Rally Agent — Proactive Intelligence Engine
Thinks without being asked. Knows what you need before you do.
"""

import asyncio
import time
import json
import os
import re
from typing import Optional
from datetime import datetime, timedelta
from collections import defaultdict

from cli.theme import Theme


class ProactiveEngine:
    """Agent that thinks proactively — anticipates needs, acts without being asked"""

    def __init__(self, engine, config):
        self.engine = engine
        self.config = config
        self.data_dir = os.path.expanduser("~/.rally-agent/data")
        self.patterns_file = os.path.join(self.data_dir, "patterns.json")
        self.suggestions_file = os.path.join(self.data_dir, "suggestions.json")
        os.makedirs(self.data_dir, exist_ok=True)

        self.patterns: list[dict] = []
        self.suggestions: list[dict] = []
        self.user_habits: dict = defaultdict(list)
        self.pending_actions: list[dict] = []

        self._load()

    def _load(self):
        """Load patterns and suggestions"""
        if os.path.exists(self.patterns_file):
            try:
                with open(self.patterns_file) as f:
                    self.patterns = json.load(f)
            except Exception:
                self.patterns = []

        if os.path.exists(self.suggestions_file):
            try:
                with open(self.suggestions_file) as f:
                    self.suggestions = json.load(f)
            except Exception:
                self.suggestions = []

    def save(self):
        """Persist state"""
        with open(self.patterns_file, "w") as f:
            json.dump(self.patterns, f, indent=2)
        with open(self.suggestions_file, "w") as f:
            json.dump(self.suggestions, f, indent=2)

    def observe(self, user_input: str, response: str = ""):
        """Observe user behavior and extract patterns"""
        timestamp = datetime.now()

        # Extract time patterns
        hour = timestamp.hour
        day = timestamp.strftime("%A")

        self.user_habits["messages"].append({
            "hour": hour,
            "day": day,
            "input": user_input[:200],
            "timestamp": timestamp.isoformat(),
        })

        # Extract topic patterns
        topics = self._extract_topics(user_input)
        for topic in topics:
            self.user_habits["topics"].append({
                "topic": topic,
                "timestamp": timestamp.isoformat(),
            })

        # Extract tool usage patterns
        if user_input.startswith("!"):
            tool = user_input.split()[0][1:]
            self.user_habits["tools"].append({
                "tool": tool,
                "timestamp": timestamp.isoformat(),
            })

        # Keep only recent history
        for key in self.user_habits:
            if len(self.user_habits[key]) > 1000:
                self.user_habits[key] = self.user_habits[key][-500:]

    def _extract_topics(self, text: str) -> list[str]:
        """Extract topics from text"""
        topics = []
        text_lower = text.lower()

        topic_keywords = {
            "coding": ["code", "function", "class", "bug", "debug", "program", "api", "database"],
            "research": ["research", "find", "search", "compare", "analyze", "study"],
            "writing": ["write", "essay", "article", "blog", "story", "content"],
            "planning": ["plan", "schedule", "organize", "task", "project", "deadline"],
            "learning": ["learn", "understand", "explain", "teach", "tutorial"],
            "business": ["business", "startup", "revenue", "market", "customer"],
            "health": ["health", "exercise", "diet", "sleep", "wellness"],
            "finance": ["money", "budget", "invest", "stock", "crypto", "finance"],
            "creative": ["design", "art", "music", "creative", "idea", "brainstorm"],
        }

        for topic, keywords in topic_keywords.items():
            if any(kw in text_lower for kw in keywords):
                topics.append(topic)

        return topics

    def detect_patterns(self) -> list[dict]:
        """Detect user behavior patterns"""
        patterns = []

        # Time-based patterns
        hour_counts = defaultdict(int)
        for msg in self.user_habits.get("messages", []):
            hour_counts[msg["hour"]] += 1

        if hour_counts:
            peak_hour = max(hour_counts, key=hour_counts.get)
            if hour_counts[peak_hour] > 5:
                patterns.append({
                    "type": "time_pattern",
                    "description": f"You're most active around {peak_hour}:00",
                    "suggestion": f"I'll be most responsive during this time",
                    "confidence": min(hour_counts[peak_hour] / 20, 1.0),
                })

        # Topic patterns
        topic_counts = defaultdict(int)
        for topic_entry in self.user_habits.get("topics", []):
            topic_counts[topic_entry["topic"]] += 1

        if topic_counts:
            top_topics = sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)[:3]
            for topic, count in top_topics:
                if count > 3:
                    patterns.append({
                        "type": "topic_pattern",
                        "description": f"You frequently work on {topic}",
                        "suggestion": f"I can help automate {topic} tasks",
                        "confidence": min(count / 15, 1.0),
                    })

        # Tool patterns
        tool_counts = defaultdict(int)
        for tool_entry in self.user_habits.get("tools", []):
            tool_counts[tool_entry["tool"]] += 1

        if tool_counts:
            top_tool = max(tool_counts, key=tool_counts.get)
            if tool_counts[top_tool] > 3:
                patterns.append({
                    "type": "tool_pattern",
                    "description": f"You frequently use the {top_tool} tool",
                    "suggestion": f"I can pre-load {top_tool} for faster access",
                    "confidence": min(tool_counts[top_tool] / 10, 1.0),
                })

        self.patterns = patterns
        return patterns

    def generate_suggestions(self) -> list[str]:
        """Generate proactive suggestions"""
        suggestions = []
        patterns = self.detect_patterns()

        for pattern in patterns:
            if pattern["confidence"] > 0.3:
                suggestions.append(pattern["suggestion"])

        # Time-based suggestions
        now = datetime.now()
        hour = now.hour

        if 6 <= hour <= 9:
            suggestions.append("🌅 Good morning! Want me to check your schedule and emails?")
        elif 12 <= hour <= 13:
            suggestions.append("☀️ Midday check-in: Any tasks to prioritize this afternoon?")
        elif 17 <= hour <= 19:
            suggestions.append("🌆 End of day: Want a summary of what we accomplished?")
        elif 22 <= hour or hour <= 2:
            suggestions.append("🌙 Late night — remember to rest! I can handle tasks while you sleep.")

        # Frequency-based suggestions
        if len(self.engine.conversation) > 10:
            recent_topics = self._extract_topics(" ".join([
                m.get("content", "") for m in self.engine.conversation[-10:]
            ]))
            if "coding" in recent_topics:
                suggestions.append("💻 You've been coding a lot — want me to review your recent code or set up tests?")
            if "research" in recent_topics:
                suggestions.append("🔬 Research mode detected — I can deep-dive and compile a comprehensive report.")

        self.suggestions = [{"text": s, "timestamp": datetime.now().isoformat()} for s in suggestions]
        return suggestions

    def get_proactive_actions(self) -> list[dict]:
        """Get actions the agent should take proactively"""
        actions = []

        # Check if we should save memory
        if len(self.engine.conversation) > 0 and len(self.engine.conversation) % 20 == 0:
            actions.append({
                "type": "memory_save",
                "description": "Auto-saving conversation to memory",
                "priority": "low",
            })

        # Check if we should consolidate memory
        if self.engine.memory and self.engine.memory.count() > 100:
            actions.append({
                "type": "memory_consolidate",
                "description": "Memory is growing large, should consolidate",
                "priority": "low",
            })

        # Check if we should update patterns
        if len(self.user_habits.get("messages", [])) > 10:
            actions.append({
                "type": "pattern_update",
                "description": "Analyzing your behavior patterns",
                "priority": "low",
            })

        return actions

    async def run_proactive_cycle(self):
        """Run a proactive intelligence cycle"""
        while True:
            try:
                # Generate suggestions
                self.generate_suggestions()

                # Run proactive actions
                actions = self.get_proactive_actions()
                for action in actions:
                    if action["type"] == "memory_save" and self.engine.memory:
                        self.engine.memory.save()
                    elif action["type"] == "pattern_update":
                        self.detect_patterns()

                # Save state
                self.save()

            except Exception:
                pass

            # Run every 5 minutes
            await asyncio.sleep(300)


class LearningEngine:
    """Self-improving learning system — gets smarter every interaction"""

    def __init__(self, engine, config):
        self.engine = engine
        self.config = config
        self.data_dir = os.path.expanduser("~/.rally-agent/data")
        self.learnings_file = os.path.join(self.data_dir, "learnings.json")
        os.makedirs(self.data_dir, exist_ok=True)

        self.learnings: list[dict] = []
        self.corrections: list[dict] = []
        self.preferences: dict = {}
        self._load()

    def _load(self):
        if os.path.exists(self.learnings_file):
            try:
                with open(self.learnings_file) as f:
                    data = json.load(f)
                    self.learnings = data.get("learnings", [])
                    self.corrections = data.get("corrections", [])
                    self.preferences = data.get("preferences", {})
            except Exception:
                pass

    def save(self):
        data = {
            "learnings": self.learnings[-500:],
            "corrections": self.corrections[-200:],
            "preferences": self.preferences,
        }
        with open(self.learnings_file, "w") as f:
            json.dump(data, f, indent=2)

    def learn_from_interaction(self, user_input: str, response: str, feedback: str = ""):
        """Learn from each interaction"""
        learning = {
            "input": user_input[:300],
            "response_preview": response[:300],
            "timestamp": datetime.now().isoformat(),
            "topics": self._extract_topics(user_input),
        }

        self.learnings.append(learning)

        # Extract preferences
        if "prefer" in user_input.lower() or "i like" in user_input.lower():
            self._extract_preference(user_input)

        # Learn from corrections
        if any(word in user_input.lower() for word in ["no", "wrong", "actually", "incorrect", "that's not"]):
            self.corrections.append({
                "context": user_input[:300],
                "timestamp": datetime.now().isoformat(),
            })

        # Periodic save
        if len(self.learnings) % 10 == 0:
            self.save()

    def _extract_topics(self, text: str) -> list[str]:
        topics = []
        text_lower = text.lower()
        keyword_map = {
            "python": ["python", "pip", "django", "flask", "pandas"],
            "javascript": ["javascript", "js", "node", "react", "vue", "npm"],
            "devops": ["docker", "kubernetes", "deploy", "ci/cd", "server"],
            "ai": ["ai", "model", "machine learning", "neural", "llm"],
            "design": ["design", "ui", "ux", "figma", "css"],
        }
        for topic, keywords in keyword_map.items():
            if any(kw in text_lower for kw in keywords):
                topics.append(topic)
        return topics

    def _extract_preference(self, text: str):
        """Extract user preferences"""
        text_lower = text.lower()

        if "prefer" in text_lower:
            # Extract what they prefer
            match = re.search(r"prefer[s]?\s+(.+?)(?:\.|$)", text, re.IGNORECASE)
            if match:
                pref = match.group(1).strip()
                self.preferences.setdefault("preferences", []).append({
                    "text": pref,
                    "timestamp": datetime.now().isoformat(),
                })

        if "i like" in text_lower:
            match = re.search(r"i like[s]?\s+(.+?)(?:\.|$)", text, re.IGNORECASE)
            if match:
                pref = match.group(1).strip()
                self.preferences.setdefault("likes", []).append({
                    "text": pref,
                    "timestamp": datetime.now().isoformat(),
                })

    def get_context_for_task(self, task: str) -> str:
        """Get relevant learned context for a task"""
        task_lower = task.lower()
        relevant = []

        # Find relevant learnings
        for learning in self.learnings[-100:]:
            for topic in learning.get("topics", []):
                if topic in task_lower:
                    relevant.append(learning["input"][:100])
                    break

        # Find relevant corrections
        for correction in self.corrections[-50:]:
            if any(word in task_lower for word in correction["context"].lower().split()[:5]):
                relevant.append(f"Previously corrected: {correction['context'][:100]}")

        # Add preferences
        if self.preferences:
            for key, prefs in self.preferences.items():
                for pref in prefs[-3:]:
                    relevant.append(f"User {key}: {pref['text']}")

        return "\n".join(set(relevant[-10:])) if relevant else ""

    def get_learning_stats(self) -> dict:
        return {
            "total_learnings": len(self.learnings),
            "total_corrections": len(self.corrections),
            "preferences_stored": sum(len(v) for v in self.preferences.values()),
            "topics_learned": list(set(
                topic for l in self.learnings for topic in l.get("topics", [])
            )),
        }
