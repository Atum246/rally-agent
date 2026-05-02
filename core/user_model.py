"""
🟣 Rally Agent — User Model Engine
Builds a comprehensive model of YOU. Learns who you are, what you like, how you think.
"""

import os
import json
import time
import re
from typing import Optional
from datetime import datetime
from collections import defaultdict, Counter

from cli.theme import Theme


class UserPersonality:
    """Personality traits inferred from interactions"""

    def __init__(self):
        self.traits: dict[str, float] = {}
        self.communication_style: dict[str, float] = {}
        self.expertise_areas: dict[str, float] = {}
        self.work_patterns: dict[str, any] = {}
        self.emotional_patterns: dict[str, float] = {}

    def to_dict(self) -> dict:
        return {
            "traits": self.traits,
            "communication_style": self.communication_style,
            "expertise_areas": self.expertise_areas,
            "work_patterns": self.work_patterns,
            "emotional_patterns": self.emotional_patterns,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "UserPersonality":
        p = cls()
        p.traits = data.get("traits", {})
        p.communication_style = data.get("communication_style", {})
        p.expertise_areas = data.get("expertise_areas", {})
        p.work_patterns = data.get("work_patterns", {})
        p.emotional_patterns = data.get("emotional_patterns", {})
        return p


class UserInterests:
    """Tracks user interests and topics"""

    def __init__(self):
        self.topics: dict[str, int] = Counter()
        self.keywords: dict[str, int] = Counter()
        self.questions_asked: list[str] = []
        self.tools_used: dict[str, int] = Counter()
        self.websites_visited: dict[str, int] = Counter()
        self.programming_languages: dict[str, int] = Counter()
        self.frameworks: dict[str, int] = Counter()

    def to_dict(self) -> dict:
        return {
            "topics": dict(self.topics),
            "keywords": dict(self.keywords.most_common(100)),
            "questions_asked": self.questions_asked[-50:],
            "tools_used": dict(self.tools_used),
            "websites_visited": dict(self.websites_visited),
            "programming_languages": dict(self.programming_languages),
            "frameworks": dict(self.frameworks),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "UserInterests":
        i = cls()
        i.topics = Counter(data.get("topics", {}))
        i.keywords = Counter(data.get("keywords", {}))
        i.questions_asked = data.get("questions_asked", [])
        i.tools_used = Counter(data.get("tools_used", {}))
        i.websites_visited = Counter(data.get("websites_visited", {}))
        i.programming_languages = Counter(data.get("programming_languages", {}))
        i.frameworks = Counter(data.get("frameworks", {}))
        return i


class UserGoals:
    """Tracks user goals and projects"""

    def __init__(self):
        self.active_goals: list[dict] = []
        self.completed_goals: list[dict] = []
        self.projects: list[dict] = []
        self.deadlines: list[dict] = []
        self.ideas: list[dict] = []

    def to_dict(self) -> dict:
        return {
            "active_goals": self.active_goals,
            "completed_goals": self.completed_goals,
            "projects": self.projects,
            "deadlines": self.deadlines,
            "ideas": self.ideas,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "UserGoals":
        g = cls()
        g.active_goals = data.get("active_goals", [])
        g.completed_goals = data.get("completed_goals", [])
        g.projects = data.get("projects", [])
        g.deadlines = data.get("deadlines", [])
        g.ideas = data.get("ideas", [])
        return g


class UserRoutines:
    """Tracks user routines and habits"""

    def __init__(self):
        self.active_hours: dict[int, int] = Counter()  # hour -> count
        self.active_days: dict[str, int] = Counter()  # day -> count
        self.session_lengths: list[float] = []
        self.common_commands: dict[str, int] = Counter()
        self.workflows: list[dict] = []

    def to_dict(self) -> dict:
        return {
            "active_hours": dict(self.active_hours),
            "active_days": dict(self.active_days),
            "session_lengths": self.session_lengths[-100:],
            "common_commands": dict(self.common_commands),
            "workflows": self.workflows[-20:],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "UserRoutines":
        r = cls()
        r.active_hours = Counter(data.get("active_hours", {}))
        r.active_days = Counter(data.get("active_days", {}))
        r.session_lengths = data.get("session_lengths", [])
        r.common_commands = Counter(data.get("common_commands", {}))
        r.workflows = data.get("workflows", [])
        return r


class UserModel:
    """Comprehensive user model — builds a digital twin of YOU"""

    def __init__(self, config):
        self.config = config
        self.data_dir = os.path.expanduser("~/.rally-agent/data")
        self.model_file = os.path.join(self.data_dir, "user_model.json")
        os.makedirs(self.data_dir, exist_ok=True)

        # Core components
        self.name: str = ""
        self.timezone: str = ""
        self.language: str = "en"
        self.created_at: str = datetime.now().isoformat()
        self.last_active: str = ""
        self.interaction_count: int = 0

        # Sub-models
        self.personality = UserPersonality()
        self.interests = UserInterests()
        self.goals = UserGoals()
        self.routines = UserRoutines()

        # Context memory
        self.preferences: list[dict] = []
        self.corrections: list[dict] = []
        self.feedback: list[dict] = []
        self.notes: list[dict] = []

        # Load existing model
        self._load()

    def _load(self):
        """Load user model from disk"""
        if os.path.exists(self.model_file):
            try:
                with open(self.model_file) as f:
                    data = json.load(f)

                self.name = data.get("name", "")
                self.timezone = data.get("timezone", "")
                self.language = data.get("language", "en")
                self.created_at = data.get("created_at", self.created_at)
                self.interaction_count = data.get("interaction_count", 0)

                self.personality = UserPersonality.from_dict(data.get("personality", {}))
                self.interests = UserInterests.from_dict(data.get("interests", {}))
                self.goals = UserGoals.from_dict(data.get("goals", {}))
                self.routines = UserRoutines.from_dict(data.get("routines", {}))

                self.preferences = data.get("preferences", [])
                self.corrections = data.get("corrections", [])
                self.feedback = data.get("feedback", [])
                self.notes = data.get("notes", [])

            except Exception:
                pass

    def save(self):
        """Save user model to disk"""
        data = {
            "name": self.name,
            "timezone": self.timezone,
            "language": self.language,
            "created_at": self.created_at,
            "last_active": datetime.now().isoformat(),
            "interaction_count": self.interaction_count,
            "personality": self.personality.to_dict(),
            "interests": self.interests.to_dict(),
            "goals": self.goals.to_dict(),
            "routines": self.routines.to_dict(),
            "preferences": self.preferences[-200:],
            "corrections": self.corrections[-100:],
            "feedback": self.feedback[-100:],
            "notes": self.notes[-100:],
        }
        with open(self.model_file, "w") as f:
            json.dump(data, f, indent=2)

    def observe(self, user_input: str, response: str = "", metadata: dict = None):
        """Observe an interaction and update the model"""
        self.interaction_count += 1
        now = datetime.now()

        # Update activity patterns
        self.routines.active_hours[now.hour] += 1
        self.routines.active_days[now.strftime("%A")] += 1

        # Extract topics
        self._extract_topics(user_input)

        # Extract expertise
        self._extract_expertise(user_input)

        # Extract personality traits
        self._extract_traits(user_input)

        # Extract communication style
        self._extract_style(user_input)

        # Check for preferences
        self._extract_preferences(user_input)

        # Check for corrections
        self._extract_corrections(user_input)

        # Check for goals
        self._extract_goals(user_input)

        # Track tool usage
        if user_input.startswith("!"):
            tool = user_input.split()[0][1:]
            self.interests.tools_used[tool] += 1
            self.routines.common_commands[tool] += 1

        # Periodic save
        if self.interaction_count % 10 == 0:
            self.save()

    def _extract_topics(self, text: str):
        """Extract topics from text"""
        text_lower = text.lower()

        topic_patterns = {
            "programming": r"\b(code|function|class|variable|api|sdk|library|framework|debug|compile|syntax)\b",
            "web_development": r"\b(html|css|javascript|react|vue|angular|node|express|django|flask)\b",
            "ai_ml": r"\b(ai|machine learning|model|neural|llm|gpt|claude|training|inference)\b",
            "devops": r"\b(docker|kubernetes|deploy|ci/cd|server|aws|azure|gcp|terraform)\b",
            "data_science": r"\b(data|analysis|statistics|pandas|numpy|visualization|chart)\b",
            "security": r"\b(security|encrypt|password|auth|vulnerability|hack|firewall)\b",
            "design": r"\b(design|ui|ux|figma|sketch|layout|color|typography)\b",
            "business": r"\b(business|startup|revenue|market|customer|product|launch)\b",
            "writing": r"\b(write|essay|article|blog|content|copy|documentation)\b",
            "research": r"\b(research|study|analyze|investigate|compare|evaluate)\b",
            "gaming": r"\b(game|gaming|unity|unreal|steam|esports)\b",
            "finance": r"\b(money|invest|stock|crypto|bitcoin|budget|trading)\b",
            "health": r"\b(health|exercise|diet|sleep|fitness|wellness|medical)\b",
            "music": r"\b(music|audio|song|beat|melody|producer|spotify)\b",
            "video": r"\b(video|youtube|tiktok|edit|render|animation)\b",
            "photography": r"\b(photo|camera|lightroom|photoshop|portrait|landscape)\b",
        }

        for topic, pattern in topic_patterns.items():
            matches = len(re.findall(pattern, text_lower))
            if matches > 0:
                self.interests.topics[topic] += matches

    def _extract_expertise(self, text: str):
        """Extract expertise areas"""
        text_lower = text.lower()

        # Programming languages
        langs = {
            "python": r"\b(python|pip|django|flask|pandas|numpy|pytest)\b",
            "javascript": r"\b(javascript|js|node|npm|react|vue|angular|typescript)\b",
            "rust": r"\b(rust|cargo|crate|rustc|tokio)\b",
            "go": r"\b(golang|go\b|goroutine|gofmt)\b",
            "java": r"\b(java|spring|maven|gradle|jvm)\b",
            "c_cpp": r"\b(c\+\+|cpp|cmake|gcc|clang)\b",
            "ruby": r"\b(ruby|rails|gem|bundler)\b",
            "php": r"\b(php|laravel|composer)\b",
            "swift": r"\b(swift|ios|xcode|cocoapods)\b",
            "kotlin": r"\b(kotlin|android|gradle)\b",
        }

        for lang, pattern in langs.items():
            matches = len(re.findall(pattern, text_lower))
            if matches > 0:
                self.interests.programming_languages[lang] += matches

        # Frameworks
        frameworks = {
            "react": r"\b(react|jsx|tsx|next\.js|nextjs)\b",
            "vue": r"\b(vue|nuxt|vite)\b",
            "django": r"\b(django|drf)\b",
            "flask": r"\b(flask)\b",
            "fastapi": r"\b(fastapi|uvicorn)\b",
            "express": r"\b(express|expressjs)\b",
            "tensorflow": r"\b(tensorflow|tf)\b",
            "pytorch": r"\b(pytorch|torch)\b",
        }

        for fw, pattern in frameworks.items():
            matches = len(re.findall(pattern, text_lower))
            if matches > 0:
                self.interests.frameworks[fw] += matches

    def _extract_traits(self, text: str):
        """Extract personality traits"""
        text_lower = text.lower()

        trait_indicators = {
            "analytical": r"\b(analyze|data|metrics|statistics|evidence|logic|reason)\b",
            "creative": r"\b(create|design|idea|brainstorm|imagine|innovate)\b",
            "detail_oriented": r"\b(detail|precise|exact|specific|careful|thorough)\b",
            "ambitious": r"\b(build|ship|launch|scale|grow|massive|huge)\b",
            "pragmatic": r"\b(practical|simple|working|fast|quick|efficient)\b",
            "curious": r"\b(how|why|what|learn|understand|explore|discover)\b",
            "perfectionist": r"\b(perfect|best|flawless|optimal|extreme)\b",
            "collaborative": r"\b(we|our|together|team|share|help)\b",
        }

        for trait, pattern in trait_indicators.items():
            matches = len(re.findall(pattern, text_lower))
            if matches > 0:
                current = self.personality.traits.get(trait, 0)
                self.personality.traits[trait] = min(1.0, current + matches * 0.05)

    def _extract_style(self, text: str):
        """Extract communication style"""
        text_lower = text.lower()

        # Formality
        formal_indicators = len(re.findall(r"\b(please|kindly|would|could|shall)\b", text_lower))
        casual_indicators = len(re.findall(r"\b(hey|yo|sup|gonna|wanna|lol|lmao|bro)\b", text_lower))

        if formal_indicators > casual_indicators:
            self.personality.communication_style["formality"] = min(1.0, self.personality.communication_style.get("formality", 0.5) + 0.05)
        elif casual_indicators > formal_indicators:
            self.personality.communication_style["formality"] = max(0.0, self.personality.communication_style.get("formality", 0.5) - 0.05)

        # Verbosity
        word_count = len(text.split())
        if word_count > 50:
            self.personality.communication_style["verbosity"] = min(1.0, self.personality.communication_style.get("verbosity", 0.5) + 0.02)
        elif word_count < 10:
            self.personality.communication_style["verbosity"] = max(0.0, self.personality.communication_style.get("verbosity", 0.5) - 0.02)

        # Technical level
        tech_words = len(re.findall(r"\b(api|sdk|function|class|variable|algorithm|architecture|infrastructure)\b", text_lower))
        if tech_words > 2:
            self.personality.communication_style["technical_level"] = min(1.0, self.personality.communication_style.get("technical_level", 0.5) + 0.05)

    def _extract_preferences(self, text: str):
        """Extract user preferences"""
        text_lower = text.lower()

        pref_patterns = [
            r"i prefer (.+?)(?:\.|$)",
            r"i like (.+?)(?:\.|$)",
            r"i love (.+?)(?:\.|$)",
            r"i want (.+?)(?:\.|$)",
            r"i need (.+?)(?:\.|$)",
            r"my favorite (.+?) is (.+?)(?:\.|$)",
            r"i always (.+?)(?:\.|$)",
            r"i usually (.+?)(?:\.|$)",
        ]

        for pattern in pref_patterns:
            matches = re.findall(pattern, text_lower)
            for match in matches:
                pref_text = match if isinstance(match, str) else match[0]
                self.preferences.append({
                    "text": pref_text.strip()[:200],
                    "timestamp": datetime.now().isoformat(),
                })

    def _extract_corrections(self, text: str):
        """Extract corrections (user telling the agent it was wrong)"""
        correction_patterns = [
            r"no,?\s*(.+)",
            r"that'?s wrong",
            r"actually,?\s*(.+)",
            r"incorrect",
            r"not quite",
            r"i meant (.+)",
            r"let me clarify",
            r"what i really want is (.+)",
        ]

        text_lower = text.lower()
        for pattern in correction_patterns:
            if re.search(pattern, text_lower):
                self.corrections.append({
                    "text": text[:300],
                    "timestamp": datetime.now().isoformat(),
                })
                break

    def _extract_goals(self, text: str):
        """Extract goals and projects"""
        goal_patterns = [
            r"i want to (.+?)(?:\.|$)",
            r"i need to (.+?)(?:\.|$)",
            r"my goal is (.+?)(?:\.|$)",
            r"i'm working on (.+?)(?:\.|$)",
            r"i'm building (.+?)(?:\.|$)",
            r"let'?s (.+?)(?:\.|$)",
            r"plan (.+?)(?:\.|$)",
        ]

        text_lower = text.lower()
        for pattern in goal_patterns:
            matches = re.findall(pattern, text_lower)
            for match in matches:
                self.goals.active_goals.append({
                    "text": match.strip()[:200],
                    "timestamp": datetime.now().isoformat(),
                    "status": "active",
                })

        # Keep only recent goals
        self.goals.active_goals = self.goals.active_goals[-50:]

    def get_context_prompt(self) -> str:
        """Generate a context prompt about the user for the AI"""
        parts = []

        if self.name:
            parts.append(f"User's name: {self.name}")

        # Personality
        if self.personality.traits:
            top_traits = sorted(self.personality.traits.items(), key=lambda x: x[1], reverse=True)[:5]
            traits_str = ", ".join([f"{t} ({v:.0%})" for t, v in top_traits])
            parts.append(f"Personality traits: {traits_str}")

        # Communication style
        style = self.personality.communication_style
        if style:
            style_parts = []
            if style.get("formality", 0.5) > 0.6:
                style_parts.append("formal")
            elif style.get("formality", 0.5) < 0.4:
                style_parts.append("casual")
            if style.get("technical_level", 0.5) > 0.6:
                style_parts.append("technical")
            if style.get("verbosity", 0.5) > 0.6:
                style_parts.append("verbose")
            elif style.get("verbosity", 0.5) < 0.4:
                style_parts.append("concise")
            if style_parts:
                parts.append(f"Communication style: {', '.join(style_parts)}")

        # Interests
        if self.interests.topics:
            top_topics = sorted(self.interests.topics.items(), key=lambda x: x[1], reverse=True)[:5]
            topics_str = ", ".join([t for t, _ in top_topics])
            parts.append(f"Main interests: {topics_str}")

        # Programming languages
        if self.interests.programming_languages:
            top_langs = sorted(self.interests.programming_languages.items(), key=lambda x: x[1], reverse=True)[:3]
            langs_str = ", ".join([l for l, _ in top_langs])
            parts.append(f"Programming languages: {langs_str}")

        # Active goals
        if self.goals.active_goals:
            recent_goals = self.goals.active_goals[-3:]
            goals_str = "; ".join([g["text"][:80] for g in recent_goals])
            parts.append(f"Current goals: {goals_str}")

        # Preferences
        if self.preferences:
            recent_prefs = self.preferences[-5:]
            prefs_str = "; ".join([p["text"][:80] for p in recent_prefs])
            parts.append(f"Preferences: {prefs_str}")

        # Routines
        if self.routines.active_hours:
            peak_hour = max(self.routines.active_hours, key=self.routines.active_hours.get)
            parts.append(f"Most active around: {peak_hour}:00")

        return "\n".join(parts) if parts else "No user model data yet. Learning from interactions..."

    def get_profile_summary(self) -> str:
        """Get a human-readable profile summary"""
        lines = []
        lines.append(f"👤 **User Profile**")
        lines.append(f"📊 Interactions: {self.interaction_count}")
        lines.append(f"📅 Model created: {self.created_at[:10]}")

        if self.name:
            lines.append(f"📛 Name: {self.name}")

        # Personality
        if self.personality.traits:
            lines.append(f"\n🧠 **Personality**")
            for trait, value in sorted(self.personality.traits.items(), key=lambda x: x[1], reverse=True)[:5]:
                bar = "█" * int(value * 10) + "░" * (10 - int(value * 10))
                lines.append(f"  {trait}: {bar} {value:.0%}")

        # Interests
        if self.interests.topics:
            lines.append(f"\n🎯 **Top Interests**")
            for topic, count in sorted(self.interests.topics.items(), key=lambda x: x[1], reverse=True)[:5]:
                lines.append(f"  • {topic}: {count} mentions")

        # Languages
        if self.interests.programming_languages:
            lines.append(f"\n💻 **Programming Languages**")
            for lang, count in sorted(self.interests.programming_languages.items(), key=lambda x: x[1], reverse=True)[:5]:
                lines.append(f"  • {lang}: {count} mentions")

        # Goals
        if self.goals.active_goals:
            lines.append(f"\n🎯 **Active Goals**")
            for goal in self.goals.active_goals[-5:]:
                lines.append(f"  • {goal['text'][:80]}")

        # Routines
        if self.routines.active_hours:
            peak = max(self.routines.active_hours, key=self.routines.active_hours.get)
            lines.append(f"\n⏰ **Routines**")
            lines.append(f"  • Most active: {peak}:00")
            if self.routines.common_commands:
                top_cmd = max(self.routines.common_commands, key=self.routines.common_commands.get)
                lines.append(f"  • Most used tool: {top_cmd}")

        return "\n".join(lines)

    def get_stats(self) -> dict:
        return {
            "interactions": self.interaction_count,
            "topics_tracked": len(self.interests.topics),
            "preferences_stored": len(self.preferences),
            "corrections_stored": len(self.corrections),
            "goals_tracked": len(self.goals.active_goals),
            "personality_traits": len(self.personality.traits),
        }
