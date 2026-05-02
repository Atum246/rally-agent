"""
🟣 Rally Agent — Multi-Agent Orchestrator
Manages specialized AI agents that work together.
"""

import asyncio
import time
from typing import Optional
from abc import ABC, abstractmethod

from cli.theme import Theme, console, Colors


class BaseAgent(ABC):
    """Base class for specialized agents"""

    name: str = "unknown"
    agent_type: str = "general"
    description: str = ""
    capabilities: list[str] = []

    @abstractmethod
    async def process(self, task: str, context: dict = None) -> str:
        pass

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "type": self.agent_type,
            "description": self.description,
            "capabilities": self.capabilities,
            "status": "ready",
        }


# ═══════════════════════════════════════════════════════════════
# 🤖 Specialized Agents
# ═══════════════════════════════════════════════════════════════

class CodeAgent(BaseAgent):
    name = "Coder"
    agent_type = "code"
    description = "Expert programmer — writes, debugs, and reviews code"
    capabilities = ["coding", "debugging", "review", "refactoring"]

    async def process(self, task: str, context: dict = None) -> str:
        return f"[Code Agent] Processing: {task}\n\nI'll write clean, well-documented code for this task. Let me analyze the requirements and implement a solution."


class ResearchAgent(BaseAgent):
    name = "Researcher"
    agent_type = "research"
    description = "Deep research — gathers, analyzes, and synthesizes information"
    capabilities = ["research", "analysis", "summarization", "fact-checking"]

    async def process(self, task: str, context: dict = None) -> str:
        return f"[Research Agent] Researching: {task}\n\nI'll conduct thorough research, verify sources, and provide a comprehensive summary."


class CreativeAgent(BaseAgent):
    name = "Creator"
    agent_type = "creative"
    description = "Creative powerhouse — writing, design, content creation"
    capabilities = ["writing", "design", "brainstorming", "content"]

    async def process(self, task: str, context: dict = None) -> str:
        return f"[Creative Agent] Creating: {task}\n\nI'll approach this with creativity and original thinking."


class DataAgent(BaseAgent):
    name = "Analyst"
    agent_type = "data"
    description = "Data wizard — analysis, visualization, insights"
    capabilities = ["analysis", "visualization", "statistics", "insights"]

    async def process(self, task: str, context: dict = None) -> str:
        return f"[Data Agent] Analyzing: {task}\n\nI'll crunch the numbers and extract meaningful insights."


class PMAgent(BaseAgent):
    name = "Project Manager"
    agent_type = "pm"
    description = "Project management — planning, tracking, coordination"
    capabilities = ["planning", "tracking", "coordination", "delegation"]

    async def process(self, task: str, context: dict = None) -> str:
        return f"[PM Agent] Planning: {task}\n\nI'll break this down into actionable tasks and create an execution plan."


class SecurityAgent(BaseAgent):
    name = "Security"
    agent_type = "security"
    description = "Security expert — auditing, hardening, best practices"
    capabilities = ["security", "auditing", "hardening", "compliance"]

    async def process(self, task: str, context: dict = None) -> str:
        return f"[Security Agent] Reviewing: {task}\n\nI'll analyze for security implications and recommend best practices."


class DevOpsAgent(BaseAgent):
    name = "DevOps"
    agent_type = "devops"
    description = "DevOps engineer — CI/CD, deployment, infrastructure"
    capabilities = ["deployment", "cicd", "infrastructure", "monitoring"]

    async def process(self, task: str, context: dict = None) -> str:
        return f"[DevOps Agent] Setting up: {task}\n\nI'll handle the infrastructure and deployment aspects."


class WriterAgent(BaseAgent):
    name = "Writer"
    agent_type = "writer"
    description = "Technical writer — documentation, guides, tutorials"
    capabilities = ["documentation", "guides", "tutorials", "copywriting"]

    async def process(self, task: str, context: dict = None) -> str:
        return f"[Writer Agent] Writing: {task}\n\nI'll create clear, well-structured documentation."


class QAAgent(BaseAgent):
    name = "QA Tester"
    agent_type = "qa"
    description = "Quality assurance — testing, validation, bug finding"
    capabilities = ["testing", "validation", "bug-finding", "quality"]

    async def process(self, task: str, context: dict = None) -> str:
        return f"[QA Agent] Testing: {task}\n\nI'll thoroughly test and validate this."


class OrchestratorAgent(BaseAgent):
    name = "Orchestrator"
    agent_type = "orchestrator"
    description = "Meta-agent — coordinates all other agents"
    capabilities = ["coordination", "delegation", "planning", "synthesis"]

    async def process(self, task: str, context: dict = None) -> str:
        return f"[Orchestrator] Coordinating: {task}\n\nI'll analyze this task, break it down, and delegate to the right agents."


# ═══════════════════════════════════════════════════════════════
# 🎯 Agent Orchestrator
# ═══════════════════════════════════════════════════════════════

class AgentOrchestrator:
    """Orchestrates multiple specialized agents"""

    def __init__(self, config):
        self.config = config
        self.agents: dict[str, BaseAgent] = {}
        self.task_history: list[dict] = []
        self._register_agents()

    def _register_agents(self):
        """Register built-in agents"""
        agents = [
            CodeAgent(),
            ResearchAgent(),
            CreativeAgent(),
            DataAgent(),
            PMAgent(),
            SecurityAgent(),
            DevOpsAgent(),
            WriterAgent(),
            QAAgent(),
            OrchestratorAgent(),
        ]

        for agent in agents:
            self.agents[agent.agent_type] = agent

    def get_all(self) -> list[dict]:
        """Get all agents as dicts"""
        return [a.to_dict() for a in self.agents.values()]

    def get(self, agent_type: str) -> Optional[BaseAgent]:
        """Get agent by type"""
        return self.agents.get(agent_type)

    def spawn(self, agent_type: str) -> Optional[BaseAgent]:
        """Spawn (get) an agent"""
        agent = self.agents.get(agent_type)
        if agent:
            Theme.success(f"Spawned agent: {agent.name}")
        else:
            available = ", ".join(self.agents.keys())
            Theme.error(f"Unknown agent type: {agent_type}")
            Theme.info(f"Available: {available}")
        return agent

    async def execute_task(self, description: str) -> str:
        """Execute a task using the best agent(s)"""
        # Determine which agents to use
        selected = self._select_agents(description)

        if not selected:
            return "No suitable agents found for this task."

        # Execute with selected agents
        results = []
        for agent in selected:
            Theme.info(f"🤖 {agent.name} is working...")
            try:
                result = await agent.process(description)
                results.append(result)
            except Exception as e:
                results.append(f"[{agent.name}] Error: {e}")

        # Record task
        self.task_history.append({
            "description": description,
            "agents": [a.name for a in selected],
            "timestamp": time.time(),
        })

        return "\n\n".join(results)

    def _select_agents(self, task: str) -> list[BaseAgent]:
        """Select the best agents for a task"""
        task_lower = task.lower()
        selected = []

        # Keyword-based agent selection
        keyword_map = {
            "code|program|function|class|bug|debug|refactor|implement": "code",
            "research|investigate|find|search|compare|analyze": "research",
            "write|create|design|story|poem|content|blog": "creative",
            "data|chart|graph|statistics|numbers|metrics": "data",
            "plan|schedule|organize|coordinate|track": "pm",
            "security|secure|audit|vulnerability|encrypt": "security",
            "deploy|server|docker|kubernetes|ci/cd|infrastructure": "devops",
            "document|docs|readme|guide|tutorial|explain": "writer",
            "test|validate|check|verify|quality": "qa",
        }

        for pattern, agent_type in keyword_map.items():
            import re
            if re.search(pattern, task_lower):
                agent = self.agents.get(agent_type)
                if agent:
                    selected.append(agent)

        # If no specific match, use orchestrator
        if not selected:
            selected.append(self.agents["orchestrator"])

        return selected

    def show_agents(self):
        """Display available agents"""
        table = Theme.create_table("🤖 Available Agents")
        table.add_column("Agent", style="neon")
        table.add_column("Type", style="cyan")
        table.add_column("Description")
        table.add_column("Capabilities", style="dim")

        for agent in self.agents.values():
            table.add_row(
                agent.name,
                agent.agent_type,
                agent.description,
                ", ".join(agent.capabilities[:3]),
            )

        console.print()
        console.print(table)
        console.print()
