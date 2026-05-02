"""
🟣 Rally Agent — Core Engine
The brain that powers everything.
"""

import asyncio
import time
import os
import json
from typing import Optional, Any
from datetime import datetime

from cli.theme import Theme, console, Colors
from core.config import RallyConfig


class RallyEngine:
    """Core engine for Rally Agent — orchestrates everything"""

    def __init__(self, config: RallyConfig):
        self.config = config
        self.start_time = time.time()
        self.initialized = False
        self.conversation: list[dict] = []
        self.providers: dict = {}
        self.memory = None
        self.tools = None
        self.agents = None
        self.current_model = config.get("agent.default_model", "auto")
        self.thinking_enabled = config.get("agent.thinking", True)
        self.compact_mode = False

    def initialize(self):
        """Initialize all subsystems"""
        if self.initialized:
            return

        Theme.step("⚡ Initializing Rally Agent")

        # Memory
        self._init_memory()

        # Tools
        self._init_tools()

        # Agents
        self._init_agents()

        # Providers
        self._init_providers()

        self.initialized = True
        Theme.success("Rally Agent ready! 🚀")

    def _init_memory(self):
        """Initialize memory system"""
        from memory.store import MemoryStore
        self.memory = MemoryStore(self.config)
        Theme.success(f"Memory: {self.memory.backend}")

    def _init_tools(self):
        """Initialize tool system"""
        from tools.registry import ToolRegistry
        self.tools = ToolRegistry(self.config)
        count = len(self.tools.get_all())
        Theme.success(f"Tools: {count} loaded")

    def _init_agents(self):
        """Initialize agent system"""
        from agents.orchestrator import AgentOrchestrator
        self.agents = AgentOrchestrator(self.config)
        Theme.success(f"Agents: {len(self.agents.get_all())} available")

    def _init_providers(self):
        """Initialize LLM providers"""
        from core.providers import ProviderManager
        self.providers = ProviderManager(self.config)
        available = self.providers.get_available()
        if available:
            Theme.success(f"Providers: {', '.join(available)}")
        else:
            Theme.warning("No API keys configured — using local fallback")
            Theme.info("Set OPENAI_API_KEY or ANTHROPIC_API_KEY to enable cloud AI")

    async def chat(self, message: str) -> Optional[str]:
        """Process a chat message and return response"""
        if not self.initialized:
            self.initialize()

        # Add to conversation
        self.conversation.append({
            "role": "user",
            "content": message,
            "timestamp": datetime.now().isoformat(),
        })

        # Store in memory
        if self.memory:
            self.memory.add("user", message)

        # Check if it's a tool call
        if message.startswith("!"):
            return await self._handle_tool_call(message[1:])

        # Get response from provider
        try:
            response = await self.providers.chat(
                messages=self.conversation[-50:],  # Last 50 messages for context
                model=self.current_model,
                thinking=self.thinking_enabled,
            )

            # Add response to conversation
            self.conversation.append({
                "role": "assistant",
                "content": response,
                "timestamp": datetime.now().isoformat(),
            })

            # Store in memory
            if self.memory:
                self.memory.add("assistant", response)

            return response

        except Exception as e:
            Theme.error(f"Provider error: {e}")
            return self._fallback_response(message)

    def _fallback_response(self, message: str) -> str:
        """Fallback when no provider is available"""
        # Check if we can handle it locally
        msg_lower = message.lower()

        if any(w in msg_lower for w in ["hello", "hi", "hey", "sup"]):
            return "Hey! 👋 I'm Rally, your AI agent. I'd love to help, but I need an API key to think. Set OPENAI_API_KEY or ANTHROPIC_API_KEY to get started! 🚀"

        if "help" in msg_lower:
            return "I need an API key to provide intelligent responses. Set one of: OPENAI_API_KEY, ANTHROPIC_API_KEY, or GOOGLE_API_KEY. You can also use local models with Ollama! 🧠"

        return (
            f"I received your message but I need an AI provider configured to respond intelligently.\n\n"
            f"Options:\n"
            f"  1. Set OPENAI_API_KEY for GPT-4\n"
            f"  2. Set ANTHROPIC_API_KEY for Claude\n"
            f"  3. Set GOOGLE_API_KEY for Gemini\n"
            f"  4. Install Ollama for local models\n\n"
            f"Your message was: \"{message[:100]}...\""
        )

    async def _handle_tool_call(self, command: str) -> str:
        """Handle direct tool calls with ! prefix"""
        parts = command.split(maxsplit=1)
        tool_name = parts[0] if parts else ""
        args = parts[1] if len(parts) > 1 else ""

        if not self.tools:
            return "Tool system not initialized"

        tool = self.tools.get(tool_name)
        if not tool:
            available = ", ".join(self.tools.get_names())
            return f"Unknown tool: {tool_name}\nAvailable: {available}"

        try:
            result = await tool.execute(args)
            return str(result)
        except Exception as e:
            return f"Tool error: {e}"

    async def run_task(self, description: str) -> str:
        """Run an autonomous task"""
        if not self.agents:
            return "Agent system not initialized"

        Theme.step(f"🎯 Task: {description}")
        result = await self.agents.execute_task(description)
        return result

    def spawn_agent(self, agent_type: str):
        """Spawn a sub-agent"""
        if self.agents:
            self.agents.spawn(agent_type)

    def show_status(self):
        """Show system status"""
        uptime = time.time() - self.start_time
        uptime_str = self._format_uptime(uptime)

        table = Theme.create_table("⚡ Rally Agent Status")
        table.add_column("Property", style="cyan", width=20)
        table.add_column("Value", style="neon_green")

        table.add_row("🟢 Status", "[green]Running[/]")
        table.add_row("🧠 Model", self.current_model)
        table.add_row("💭 Thinking", "ON" if self.thinking_enabled else "OFF")
        table.add_row("💬 Messages", str(len(self.conversation)))
        table.add_row("⏱️ Uptime", uptime_str)
        table.add_row("🔧 Tools", str(len(self.tools.get_all())) if self.tools else "0")
        table.add_row("🤖 Agents", str(len(self.agents.get_all())) if self.agents else "0")

        if self.memory:
            table.add_row("🧩 Memory", f"{self.memory.count()} entries")

        console.print()
        console.print(table)
        console.print()

    def show_agents(self):
        """Show available agents"""
        if not self.agents:
            Theme.warning("Agent system not initialized")
            return

        agents = self.agents.get_all()
        table = Theme.create_table("🤖 Available Agents")
        table.add_column("Agent", style="neon")
        table.add_column("Type", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Description")

        for agent in agents:
            table.add_row(
                agent["name"],
                agent["type"],
                agent.get("status", "ready"),
                agent.get("description", ""),
            )

        console.print()
        console.print(table)
        console.print()

    def show_memory_stats(self):
        """Show memory statistics"""
        if not self.memory:
            Theme.warning("Memory not initialized")
            return
        self.memory.show_stats()

    def search_memory(self, query: str):
        """Search memory"""
        if not self.memory:
            Theme.warning("Memory not initialized")
            return
        results = self.memory.search(query)
        if results:
            for r in results:
                console.print(f"  [purple]{r['content'][:100]}[/]")
        else:
            Theme.info("No results found")

    def clear_memory(self):
        """Clear memory"""
        if self.memory:
            self.memory.clear()
            Theme.success("Memory cleared")

    def show_tools(self):
        """Show available tools"""
        if not self.tools:
            Theme.warning("Tools not initialized")
            return

        tools = self.tools.get_all()
        table = Theme.create_table("🔧 Available Tools")
        table.add_column("Tool", style="neon")
        table.add_column("Category", style="cyan")
        table.add_column("Description")

        for tool in tools:
            table.add_row(
                tool["name"],
                tool.get("category", "general"),
                tool.get("description", ""),
            )

        console.print()
        console.print(table)
        console.print()

    def show_config(self):
        """Show configuration"""
        table = Theme.create_table("⚙️ Configuration")
        table.add_column("Key", style="cyan")
        table.add_column("Value", style="neon_green")

        for section, values in self.config.data.items():
            if isinstance(values, dict):
                for k, v in values.items():
                    table.add_row(f"{section}.{k}", str(v))
            else:
                table.add_row(section, str(values))

        console.print()
        console.print(table)
        console.print()

    def set_config(self, key: str, value: str):
        """Set a config value"""
        self.config.set(key, value)
        Theme.success(f"Set {key} = {value}")

    def show_model(self):
        """Show current model"""
        Theme.info(f"Current model: [neon]{self.current_model}[/]")

    def set_model(self, model: str):
        """Switch model"""
        self.current_model = model
        Theme.success(f"Switched to model: [neon]{model}[/]")

    def toggle_thinking(self):
        """Toggle thinking mode"""
        self.thinking_enabled = not self.thinking_enabled
        state = "ON" if self.thinking_enabled else "OFF"
        Theme.success(f"Thinking: [neon]{state}[/]")

    def set_thinking(self, enabled: bool):
        """Set thinking mode"""
        self.thinking_enabled = enabled
        state = "ON" if enabled else "OFF"
        Theme.success(f"Thinking: [neon]{state}[/]")

    def toggle_compact(self):
        """Toggle compact mode"""
        self.compact_mode = not self.compact_mode
        state = "ON" if self.compact_mode else "OFF"
        Theme.success(f"Compact mode: [neon]{state}[/]")

    def save_conversation(self, path: str):
        """Save conversation to file"""
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.conversation, f, indent=2)
        Theme.success(f"Conversation saved to {path}")

    def load_conversation(self, path: str):
        """Load conversation from file"""
        if os.path.exists(path):
            with open(path) as f:
                self.conversation = json.load(f)
            Theme.success(f"Loaded {len(self.conversation)} messages from {path}")
        else:
            Theme.error(f"File not found: {path}")

    def shutdown(self):
        """Graceful shutdown"""
        if self.memory:
            self.memory.save()
        Theme.info("Rally Agent shutdown complete")

    @staticmethod
    def _format_uptime(seconds: float) -> str:
        """Format uptime in human-readable format"""
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            return f"{int(seconds // 60)}m {int(seconds % 60)}s"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f"{hours}h {minutes}m"
