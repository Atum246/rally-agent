"""
🟣 Rally Agent — Swarm Intelligence Engine
Spawns tens of AI agents that share knowledge, learn, and think together.
"""

import asyncio
import time
import json
import os
import hashlib
from typing import Optional, Any
from datetime import datetime
from collections import defaultdict

from cli.theme import Theme, console, Colors


class SharedKnowledge:
    """Shared knowledge base that all swarm agents can read/write"""

    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.kb_file = os.path.join(data_dir, "swarm_knowledge.json")
        os.makedirs(data_dir, exist_ok=True)
        self.entries: list[dict] = []
        self.index: dict[str, list[int]] = defaultdict(list)  # keyword -> entry indices
        self._load()

    def _load(self):
        if os.path.exists(self.kb_file):
            try:
                with open(self.kb_file) as f:
                    self.entries = json.load(f)
                self._rebuild_index()
            except Exception:
                self.entries = []

    def _rebuild_index(self):
        self.index.clear()
        for i, entry in enumerate(self.entries):
            for word in entry.get("content", "").lower().split():
                if len(word) > 3:
                    self.index[word].append(i)

    def add(self, content: str, source: str = "", category: str = "general", confidence: float = 1.0):
        """Add knowledge to the shared pool"""
        entry = {
            "id": hashlib.md5(f"{time.time()}{content}".encode()).hexdigest()[:12],
            "content": content,
            "source": source,
            "category": category,
            "confidence": confidence,
            "timestamp": datetime.now().isoformat(),
            "access_count": 0,
            "useful_count": 0,
        }
        self.entries.append(entry)
        idx = len(self.entries) - 1
        for word in content.lower().split():
            if len(word) > 3:
                self.index[word].append(idx)

        # Periodic save
        if len(self.entries) % 20 == 0:
            self.save()

    def search(self, query: str, limit: int = 10) -> list[dict]:
        """Search shared knowledge"""
        query_words = set(query.lower().split())
        scored = []

        for word in query_words:
            for idx in self.index.get(word, []):
                if idx < len(self.entries):
                    entry = self.entries[idx]
                    # Score based on word match + confidence + usefulness
                    score = sum(1 for w in query_words if w in entry["content"].lower())
                    score *= entry.get("confidence", 1.0)
                    score *= (1 + entry.get("useful_count", 0) * 0.1)
                    scored.append((score, entry))

        # Deduplicate
        seen = set()
        results = []
        scored.sort(key=lambda x: x[0], reverse=True)
        for score, entry in scored:
            if entry["id"] not in seen:
                seen.add(entry["id"])
                entry["access_count"] = entry.get("access_count", 0) + 1
                results.append(entry)
                if len(results) >= limit:
                    break

        return results

    def mark_useful(self, entry_id: str):
        """Mark knowledge as useful (feedback loop)"""
        for entry in self.entries:
            if entry["id"] == entry_id:
                entry["useful_count"] = entry.get("useful_count", 0) + 1
                break

    def get_stats(self) -> dict:
        return {
            "total_entries": len(self.entries),
            "categories": list(set(e.get("category", "general") for e in self.entries)),
            "most_useful": sorted(self.entries, key=lambda x: x.get("useful_count", 0), reverse=True)[:5],
        }

    def save(self):
        with open(self.kb_file, "w") as f:
            json.dump(self.entries, f, indent=2)


class SwarmAgent:
    """Individual agent in the swarm"""

    def __init__(self, agent_id: str, specialty: str, knowledge: SharedKnowledge, providers):
        self.agent_id = agent_id
        self.specialty = specialty
        self.knowledge = knowledge
        self.providers = providers
        self.memory: list[dict] = []
        self.task_count = 0
        self.success_count = 0
        self.created_at = datetime.now().isoformat()
        self.last_active = None

    async def think(self, task: str, context: dict = None) -> str:
        """Process a task using shared knowledge"""
        self.last_active = datetime.now().isoformat()
        self.task_count += 1

        # Search shared knowledge first
        relevant_knowledge = self.knowledge.search(task, limit=5)
        knowledge_context = ""
        if relevant_knowledge:
            knowledge_context = "\n".join([f"- {k['content']}" for k in relevant_knowledge])

        # Build prompt with specialty and knowledge
        system_prompt = f"""You are {self.agent_id}, a specialized {self.specialty} agent in a swarm intelligence system.

Your role: {self.specialty}
Relevant knowledge from the swarm:
{knowledge_context if knowledge_context else "No prior knowledge on this topic."}

Think step by step. Be precise and actionable. Learn from the task and contribute back to the shared knowledge."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task},
        ]

        # Add conversation context
        if context:
            context_str = json.dumps(context, indent=2)
            messages.insert(1, {"role": "system", "content": f"Additional context:\n{context_str}"})

        # Get response
        try:
            response = await self.providers.chat(messages)
            self.success_count += 1

            # Store learned knowledge
            self.knowledge.add(
                content=f"Task: {task[:200]} → Result: {response[:200]}",
                source=self.agent_id,
                category=self.specialty,
                confidence=self.success_count / max(self.task_count, 1),
            )

            self.memory.append({"task": task, "response": response[:500], "timestamp": datetime.now().isoformat()})
            return response

        except Exception as e:
            return f"[{self.agent_id}] Error: {e}"

    def get_stats(self) -> dict:
        return {
            "id": self.agent_id,
            "specialty": self.specialty,
            "tasks_completed": self.task_count,
            "success_rate": self.success_count / max(self.task_count, 1),
            "last_active": self.last_active,
        }


class SwarmQueen:
    """Orchestrates the swarm — the queen bee 🐝"""

    SPECIALTIES = {
        "researcher": "Deep research, fact-finding, source verification",
        "analyst": "Data analysis, pattern recognition, statistical thinking",
        "coder": "Programming, debugging, architecture, code review",
        "creative": "Writing, design, brainstorming, content creation",
        "strategist": "Planning, strategy, decision-making, risk assessment",
        "critic": "Quality assurance, error detection, constructive criticism",
        "synthesizer": "Combining information, summarizing, connecting ideas",
        "executor": "Task execution, automation, workflow management",
        "learner": "Pattern extraction, knowledge building, insight discovery",
        "communicator": "Clear explanation, teaching, presentation",
        "optimizer": "Performance improvement, efficiency, resource management",
        "security": "Security analysis, risk assessment, hardening",
        "devops": "Infrastructure, deployment, monitoring, scaling",
        "scientist": "Scientific thinking, hypothesis testing, experimentation",
        "philosopher": "Ethical reasoning, philosophical analysis, values alignment",
        "economist": "Cost analysis, resource allocation, economic thinking",
        "designer": "UX/UI design, user research, interface architecture",
        "marketer": "Growth, positioning, messaging, audience understanding",
        "diagnostician": "Problem diagnosis, root cause analysis, debugging",
        "architect": "System design, scalability, architecture patterns",
    }

    def __init__(self, providers, data_dir: str = "~/.rally-agent/data"):
        self.providers = providers
        self.data_dir = os.path.expanduser(data_dir)
        self.knowledge = SharedKnowledge(self.data_dir)
        self.swarm: dict[str, SwarmAgent] = {}
        self.task_history: list[dict] = []
        self.learning_patterns: list[dict] = []

    def spawn_swarm(self, size: int = 10, specialties: list[str] = None) -> list[str]:
        """Spawn a swarm of agents"""
        if not specialties:
            specialties = list(self.SPECIALTIES.keys())[:size]

        spawned = []
        for i, specialty in enumerate(specialties):
            agent_id = f"swarm-{specialty}-{i+1}"
            if agent_id not in self.swarm:
                agent = SwarmAgent(
                    agent_id=agent_id,
                    specialty=specialty,
                    knowledge=self.knowledge,
                    providers=self.providers,
                )
                self.swarm[agent_id] = agent
                spawned.append(agent_id)

        Theme.success(f"🐝 Swarm spawned: {len(spawned)} agents")
        return spawned

    async def execute_swarm_task(self, task: str, swarm_size: int = 10) -> str:
        """Execute a task using the swarm"""
        if not self.swarm:
            self.spawn_swarm(swarm_size)

        Theme.step(f"🐝 Swarm Task: {task[:80]}...")

        # Select best agents for the task
        selected = self._select_agents(task)
        Theme.info(f"Selected {len(selected)} agents for this task")

        # Phase 1: Individual thinking (parallel)
        individual_results = await asyncio.gather(
            *[agent.think(task) for agent in selected],
            return_exceptions=True,
        )

        # Phase 2: Cross-pollination — agents see each other's results
        combined_results = []
        for i, result in enumerate(individual_results):
            if isinstance(result, Exception):
                combined_results.append(f"[Agent {i}] Error: {result}")
            else:
                combined_results.append(result)

        cross_pollination_prompt = f"""You are the Swarm Synthesizer. Multiple specialized agents have analyzed this task:

TASK: {task}

AGENT RESULTS:
{chr(10).join([f"[{selected[i].specialty}]: {r[:300]}" for i, r in enumerate(combined_results) if not isinstance(r, Exception)])}

Synthesize the BEST possible answer by combining the strengths of each agent's response. 
Identify agreements, resolve contradictions, and produce a superior final answer."""

        # Phase 3: Synthesis
        synthesis_messages = [
            {"role": "system", "content": "You are the master synthesizer. Combine multiple expert perspectives into one superior answer."},
            {"role": "user", "content": cross_pollination_prompt},
        ]

        try:
            final_response = await self.providers.chat(synthesis_messages)
        except Exception:
            # Fallback to best individual result
            final_response = combined_results[0] if combined_results else "Swarm processing failed."

        # Store learning
        self.knowledge.add(
            content=f"Swarm task: {task[:200]} → Synthesized: {final_response[:200]}",
            source="swarm-synthesis",
            category="swarm-learning",
            confidence=0.9,
        )

        self.task_history.append({
            "task": task,
            "agents_used": [a.agent_id for a in selected],
            "timestamp": datetime.now().isoformat(),
        })

        return final_response

    def _select_agents(self, task: str) -> list[SwarmAgent]:
        """Select the best agents for a task"""
        task_lower = task.lower()
        scored = []

        keyword_map = {
            "research|find|search|investigate|compare": "researcher",
            "analyze|data|statistics|numbers|metrics|chart": "analyst",
            "code|program|function|bug|debug|implement|build": "coder",
            "write|create|design|story|poem|content|blog": "creative",
            "plan|strategy|decide|choose|evaluate|assess": "strategist",
            "review|check|quality|error|test|verify": "critic",
            "combine|summarize|connect|integrate|merge": "synthesizer",
            "execute|run|automate|deploy|ship|do": "executor",
            "learn|pattern|insight|trend|discover": "learner",
            "explain|teach|present|communicate|describe": "communicator",
            "optimize|improve|faster|efficient|performance": "optimizer",
            "security|secure|protect|vulnerability|safe": "security",
            "server|deploy|docker|infrastructure|scale": "devops",
            "experiment|test|hypothesis|scientific|measure": "scientist",
            "ethics|moral|values|philosophy|meaning": "philosopher",
            "cost|budget|price|economic|resource": "economist",
            "ui|ux|interface|user|design|layout": "designer",
            "marketing|growth|audience|message|brand": "marketer",
            "diagnose|root cause|why|problem|issue": "diagnostician",
            "architecture|system|design|scalable|structure": "architect",
        }

        for pattern, specialty in keyword_map.items():
            import re
            if re.search(pattern, task_lower):
                agent_id = next((aid for aid, a in self.swarm.items() if a.specialty == specialty), None)
                if agent_id:
                    agent = self.swarm[agent_id]
                    score = agent.success_count / max(agent.task_count, 1) + 0.5
                    scored.append((score, agent))

        # Sort by score, take top agents
        scored.sort(key=lambda x: x[0], reverse=True)
        selected = [agent for _, agent in scored[:min(5, len(scored))]]

        # Always include at least 2 agents
        if len(selected) < 2:
            available = list(self.swarm.values())
            for agent in available:
                if agent not in selected:
                    selected.append(agent)
                if len(selected) >= 3:
                    break

        return selected or list(self.swarm.values())[:3]

    def get_swarm_stats(self) -> dict:
        return {
            "total_agents": len(self.swarm),
            "total_tasks": len(self.task_history),
            "knowledge_entries": len(self.knowledge.entries),
            "agents": [a.get_stats() for a in self.swarm.values()],
        }

    def save(self):
        """Persist swarm state"""
        self.knowledge.save()
        state = {
            "agents": {aid: a.get_stats() for aid, a in self.swarm.items()},
            "task_history": self.task_history[-100:],
        }
        state_file = os.path.join(self.data_dir, "swarm_state.json")
        with open(state_file, "w") as f:
            json.dump(state, f, indent=2)
