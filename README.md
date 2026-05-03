<p align="center">
  <pre>
    ██████╗  █████╗ ██╗     ██╗     ██╗   ██╗
    ██╔══██╗██╔══██╗██║     ██║     ╚██╗ ██╔╝
    ██████╔╝███████║██║     ██║      ╚████╔╝
    ██╔══██╗██╔══██║██║     ██║       ╚██╔╝
    ██║  ██║██║  ██║███████╗███████╗   ██║
    ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝╚══════╝   ╚═╝
           █████╗  ██████╗ ███████╗███╗   ██╗████████╗
          ██╔══██╗██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝
          ███████║██║  ███╗█████╗  ██╔██╗ ██║   ██║
          ██╔══██║██║   ██║██╔══╝  ██║╚██╗██║   ██║
          ██║  ██║╚██████╔╝███████╗██║ ╚████║   ██║
          ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝
  </pre>
</p>

<h1 align="center">🟣 Rally Agent v2.0</h1>
<p align="center"><strong>Your AI. Your Rules. Your Data.</strong></p>
<p align="center">
  A fully-featured, self-hosted AI agent platform with multi-provider support,<br>
  persistent memory, multi-agent orchestration, voice, browser automation, and more.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/version-2.0.0-purple?style=flat-square" alt="Version">
  <img src="https://img.shields.io/badge/python-3.10+-blue?style=flat-square" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="License">
  <img src="https://img.shields.io/badge/providers-36-orange?style=flat-square" alt="Providers">
  <img src="https://img.shields.io/badge/channels-52-cyan?style=flat-square" alt="Channels">
  <img src="https://img.shields.io/badge/agents-10-yellow?style=flat-square" alt="Agents">
  <img src="https://img.shields.io/badge/tools-30+-red?style=flat-square" alt="Tools">
</p>

---

## ⚡ One-Line Install

**Linux / macOS:**

```bash
curl -fsSL https://raw.githubusercontent.com/Atum246/rally-agent/main/install.sh | bash
```

**Windows (PowerShell):**

```powershell
irm https://raw.githubusercontent.com/Atum246/rally-agent/main/install.ps1 | iex
```

**Docker:**

```bash
docker-compose up -d
```

---

## 🎯 What Is Rally Agent?

Rally Agent is a **self-hosted AI agent platform** that runs entirely on your infrastructure. It connects to 36+ AI model providers, interfaces with 52+ messaging channels, orchestrates 10 specialized agents, and includes persistent memory, browser automation, voice support, cron scheduling, and a beautiful web UI — all in a single Python package.

**Why self-host?**

| Problem | Rally's Solution |
|---|---|
| 🔒 Cloud AI sees your data | Everything runs locally. Your data stays your data. |
| 💰 AI subscriptions are expensive | Use any provider, including free local models via Ollama |
| 🤖 Chatbots are stateless | Persistent memory that learns and grows over time |
| 🔌 Limited integrations | 52 messaging channels — connect everywhere |
| ⏰ AI only responds when you ask | Proactive intelligence with cron automation |
| 🛠️ Need multiple tools | 30+ built-in skills with hundreds of commands |

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        🌐 Web UI (FastAPI)                       │
│                    http://localhost:8778                          │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐    │
│  │ 🎨 CLI   │  │ 💬 Chat  │  │ 📡 API   │  │ 🔌 Channels  │    │
│  │ (Rich)   │  │ (SSE)    │  │ (REST)   │  │ (52 targets) │    │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └──────┬───────┘    │
│       │              │              │               │            │
│  ┌────▼──────────────▼──────────────▼───────────────▼───────┐   │
│  │              ⚡ Rally Engine (Core)                       │   │
│  │  ┌─────────┐ ┌──────────┐ ┌──────────┐ ┌─────────────┐  │   │
│  │  │Provider │ │Conversation│ │  Token   │ │  Request    │  │   │
│  │  │Manager  │ │  Tree     │ │ Counter  │ │   Queue     │  │   │
│  │  │(36 LLMs)│ │ (branch) │ │(context) │ │ (priority)  │  │   │
│  │  └────┬────┘ └──────────┘ └──────────┘ └─────────────┘  │   │
│  └───────┼──────────────────────────────────────────────────┘   │
│          │                                                       │
│  ┌───────┼────────────────────────────────────────────────────┐ │
│  │       │         🧠 Subsystems                               │ │
│  │  ┌────▼─────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐  │ │
│  │  │🤖 Agents │ │🧠 Memory │ │🔧 Tools  │ │📊 Observ.   │  │ │
│  │  │(10 specs)│ │(vec+BM25)│ │(30+ skills│ │(metrics/cost)│  │ │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────────┘  │ │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐  │ │
│  │  │⏰ Cron   │ │🔄 Workf. │ │🕸️ Know.  │ │🛡️ Security │  │ │
│  │  │(10 types)│ │(record/  │ │  Graph   │ │(RBAC/JWT)   │  │ │
│  │  │          │ │ replay)  │ │(entities)│ │              │  │ │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────────┘  │ │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐  │ │
│  │  │🎤 Voice  │ │🌐 Browser│ │🖥️ Comp.  │ │🔌 Plugins   │  │ │
│  │  │(STT/TTS) │ │(Playwr.) │ │  Use     │ │(SDK/hot-    │  │ │
│  │  │          │ │          │ │(screen)  │ │  reload)    │  │ │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────────┘  │ │
│  └────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### 1. Install

```bash
# Clone and install
git clone https://github.com/Atum246/rally-agent.git
cd rally-agent
pip install .

# Or install with all optional features
pip install .[all]
```

### 2. Configure

Set at least one AI provider API key:

```bash
# Pick any provider (or multiple for fallback)
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
export GOOGLE_API_KEY="AIza..."

# Or use local models — no API key needed
# Install Ollama: https://ollama.ai
ollama pull llama3.2
```

### 3. Run

```bash
rally              # Interactive CLI mode
rally web          # Start web UI at http://localhost:8778
rally status       # Check system status
rally --help       # See all commands
```

---

## 🧠 Features

### 🔌 AI Providers (36)

Every major provider. Real implementations with streaming, function calling, retries, and circuit breakers.

#### 🟢 Tier 1 — Major Cloud

| Provider | Models | Streaming | Function Calling | Vision |
|---|---|---|---|---|
| **OpenAI** | GPT-4o, GPT-4, o1, o3, o4-mini | ✅ | ✅ | ✅ |
| **Anthropic** | Claude Opus 4, Claude Sonnet 4, Claude 3.5 | ✅ | ✅ | ✅ |
| **Google** | Gemini 2.5 Pro/Flash, Gemini 2.0, 1.5 | ✅ | ✅ | ✅ |
| **Google Vertex** | Enterprise Gemini models | ✅ | ✅ | ✅ |

#### ⚡ Tier 2 — Fast Inference

| Provider | Models | Speed |
|---|---|---|
| **Groq** | Llama 3.3, Mixtral, Gemma 2 | 🚀 Ultra-fast |
| **Cerebras** | Llama 3.3, Llama 3.1 | 🚀 Ultra-fast |
| **SambaNova** | Llama 3.3, DeepSeek V3 | 🚀 Ultra-fast |
| **Fireworks** | Llama, DeepSeek, Qwen, Mixtral | 🚀 Ultra-fast |
| **Together** | Llama, DeepSeek, Qwen, Mistral, Gemma | 🚀 Ultra-fast |

#### 🔀 Tier 3 — Aggregators

| Provider | Description |
|---|---|
| **OpenRouter** | 300+ models via one API |
| **Unify** | Optimal model routing |
| **Portkey** | Gateway to 200+ LLMs |

#### 🏠 Tier 4 — Local & Self-Hosted (No API Key Needed)

| Provider | Description |
|---|---|
| **Ollama** | Run any local model (Llama, Mistral, Qwen, etc.) |
| **LM Studio** | Local model server |
| **vLLM** | High-throughput LLM serving |
| **text-generation-webui** | Oobabooga local |
| **Jan** | Local AI platform |
| **GPT4All** | Local AI on any device |
| **llama.cpp** | C++ inference server |

#### 🌏 Tier 5 — International

| Provider | Models |
|---|---|
| **Mistral** | Large, Medium, Small, Codestral, Pixtral |
| **DeepSeek** | Chat, Reasoner, Coder |
| **Qwen (Alibaba)** | Max, Plus, Turbo, Long |
| **Baidu** | ERNIE 4.0, 3.5, Speed |
| **Zhipu (GLM)** | GLM-4, GLM-4V, GLM-3 |
| **Moonshot (Kimi)** | 128K, 32K, 8K context |
| **Yi (01.AI)** | Large, Medium, Spark |
| **Cohere** | Command R+, Command R |
| **AI21** | Jamba 1.5 Large, Mini |
| **Perplexity** | Sonar Pro, Sonar, Deep Research |

#### 🔧 Tier 6 — Platform & Custom

| Provider | Description |
|---|---|
| **Replicate** | Run any ML model |
| **Hugging Face** | Open model hub |
| **xAI (Grok)** | Grok 3, Grok 2 |
| **Amazon Bedrock** | AWS AI platform |
| **Azure OpenAI** | Microsoft AI platform |
| **Custom** | Any OpenAI-compatible endpoint |

**Provider features:** Automatic fallback chain, circuit breaker pattern, rate limiting, health checks, token counting, retry with exponential backoff.

---

### 📡 Messaging Channels (52)

Connect Rally to every messaging platform. Each channel is a separate module with `connect()`, `send()`, and `receive()` methods.

#### 📱 Major Messaging (9)

| Channel | Protocol |
|---|---|
| 📱 WhatsApp | WhatsApp Business API |
| ✈️ Telegram | Bot API |
| 🎮 Discord | Bot & Webhook |
| 💼 Slack | Bot & Webhook |
| 🔒 Signal | signal-cli REST API |
| 🍎 iMessage | BlueBubbles/pypush |
| 🟢 LINE | Messaging API |
| 💜 Viber | Bot API |
| 💬 WeChat | WeCom/企业微信 API |

#### 🏢 Enterprise (9)

| Channel | Protocol |
|---|---|
| 👥 Microsoft Teams | Bot Framework |
| 🔵 Google Chat | Workspace API |
| 📡 IRC | IRC Protocol |
| 🟩 Matrix | Matrix API |
| 🔵 Mattermost | REST API |
| 🚀 Rocket.Chat | REST API |
| 🔵 Zulip | REST API |
| 🐑 Flock | Bot API |
| 🌀 Twist | API |

#### 📧 Email (3)

| Channel | Protocol |
|---|---|
| 📧 Email | SMTP/IMAP |
| 📨 SendGrid | Email API |
| 🔫 Mailgun | Email API |

#### 🐦 Social Media (8)

| Channel | Protocol |
|---|---|
| 🐦 Twitter/X | API v2 |
| 🔴 Reddit | PRAW/API |
| 🐘 Mastodon | Mastodon.py |
| 💼 LinkedIn | API |
| 📘 Facebook | Messenger Platform |
| 📸 Instagram | Graph API |
| 🎵 TikTok | API |
| 📺 YouTube | Data API |

#### 🔧 Developer (4)

| Channel | Protocol |
|---|---|
| 🐙 GitHub | Issues, PRs, Discussions |
| 🦊 GitLab | Issues, MRs |
| 🔗 Webhook | HTTP POST |
| ⚡ Zapier | Webhook |

#### 🔔 Notifications (5)

| Channel | Protocol |
|---|---|
| 🔔 ntfy | Push notifications |
| 📢 Gotify | Self-hosted push |
| 📲 Pushover | Push API |
| 📢 Apprise | Universal library |
| 📡 Shoutrrr | Go notification router |

#### 📞 Voice/SMS (4)

| Channel | Protocol |
|---|---|
| 📞 Twilio SMS | SMS & Voice |
| 📱 Twilio WhatsApp | WhatsApp via Twilio |
| 📞 Vonage | SMS & Voice |
| ☁️ Amazon SNS | Push & SMS |

#### 🏠 IoT (4)

| Channel | Protocol |
|---|---|
| 🏠 Home Assistant | REST API |
| 📡 MQTT | IoT protocol |
| 🔵 Alexa | Voice API |
| 🔴 Google Home | Smart Home API |

#### 📋 Project Management (4)

| Channel | Protocol |
|---|---|
| 📋 Jira | REST API |
| 📐 Linear | GraphQL API |
| 📝 Notion | API |
| 📊 Airtable | API |

#### 🎮 Gaming (2)

| Channel | Protocol |
|---|---|
| 🎮 Twitch | IRC/API |
| 🎮 Steam | Web API |

---

### 🤖 AI Agents (10)

Specialized agents that work together. The orchestrator automatically selects the right agent(s) for each task using keyword-based routing.

| Agent | Type | Specialty |
|---|---|---|
| 🔬 **Researcher** | `research` | Deep research, fact-finding, source verification |
| 💻 **Coder** | `code` | Programming, debugging, architecture, code review |
| 🎨 **Creator** | `creative` | Writing, design, brainstorming, content creation |
| 📊 **Analyst** | `data` | Data analysis, pattern recognition, statistics |
| 🎯 **Project Manager** | `pm` | Planning, tracking, coordination, delegation |
| 🛡️ **Security** | `security` | Security analysis, hardening, auditing, compliance |
| ⚙️ **DevOps** | `devops` | CI/CD, deployment, infrastructure, monitoring |
| ✍️ **Writer** | `writer` | Documentation, guides, tutorials, copywriting |
| 🧪 **QA Tester** | `qa` | Testing, validation, bug finding, quality |
| 🧩 **Orchestrator** | `orchestrator` | Coordinates all other agents, task decomposition |

```bash
# In CLI
!agents                          # List all agents
# Or just ask naturally:
"Research the latest Python 3.13 features"  # → Researcher agent
"Write a REST API in FastAPI"               # → Coder agent
"Plan a product launch"                      # → PM agent
```

---

### 🔧 Tools & Skills (30+)

Built-in skills with proper function calling schemas, input validation, and error handling.

#### 📁 Files & System

| Skill | Commands |
|---|---|
| **file_ops** | `read`, `write`, `edit`, `ls`, `find`, `grep`, `diff`, `head`, `tail`, `wc`, `stat` |
| **system** | `info`, `cpu`, `mem`, `disk`, `net`, `ps`, `env`, `uptime`, `hostname`, `arch` |
| **git** | `status`, `log`, `diff`, `branch`, `commit`, `push`, `pull`, `stash`, `clone` |
| **docker** | `ps`, `images`, `build`, `run`, `logs`, `stop`, `rm` |
| **pkg** | `pip`, `npm`, `apt`, `brew` |

#### 💻 Code

| Skill | Commands |
|---|---|
| **python** | `run`, `eval`, `install`, `venv` |
| **node** | `run`, `eval` |
| **shell** | `run`, `bash` |
| **regex** | `test`, `match`, `replace`, `explain` |
| **json** | `parse`, `format`, `query`, `validate` |
| **sql** | `query`, `tables`, `schema` |

#### 🌐 Web

| Skill | Commands |
|---|---|
| **web** | `search`, `fetch`, `weather`, `news` |
| **api** | `get`, `post`, `put`, `delete` |
| **url** | `encode`, `decode`, `parse` |

#### 📊 Data

| Skill | Commands |
|---|---|
| **data** | `csv`, `stats`, `chart`, `convert` |
| **math** | `calc`, `convert`, `formula` |
| **yaml** | `parse`, `validate`, `to_json` |
| **toml** | `parse`, `validate` |

#### 🔒 Security

| Skill | Commands |
|---|---|
| **crypto** | `hash`, `encode`, `decode`, `generate` |
| **password** | `generate`, `strength` |
| **ip** | `myip`, `lookup`, `dns` |

#### 📝 Utility

| Skill | Commands |
|---|---|
| **markdown** | `render`, `toc`, `validate` |
| **template** | `render`, `list` |
| **uuid** | `generate`, `validate` |
| **datetime** | `now`, `convert`, `diff`, `format` |
| **random** | `number`, `string`, `choice`, `shuffle` |
| **notify** | `send` |

---

### 🧠 Memory & RAG

A hybrid memory system combining vector embeddings with BM25 keyword search.

**Features:**
- **Vector search** — Sentence-transformers embeddings (`all-MiniLM-L6-v2`) with ChromaDB or in-memory store
- **BM25 keyword search** — Okapi BM25 scorer for precise text matching
- **Hybrid ranking** — Combines vector similarity + BM25 + recency + importance scoring
- **Document ingestion** — Auto-chunks long text with overlap, breaks at paragraph/sentence boundaries
- **RAG context injection** — `build_context()` retrieves relevant memories for LLM prompts
- **Memory categories** — `conversation`, `knowledge`, `preferences`, `corrections`, `goals`
- **Consolidation** — Automatic summarization of old memories via LLM
- **Encryption at rest** — XOR obfuscation for sensitive entries (preferences, corrections)
- **Binary embedding index** — Compact `.embidx` format for fast loading
- **Export/import** — Full JSON backup with optional encryption

```python
# Search memories
results = memory.search("Python async patterns", limit=5, mode="hybrid")

# Build RAG context
context = memory.build_context("How do I use FastAPI?", max_tokens=2000)

# Add a memory
memory.add("user", "I prefer dark mode UIs", category="preferences", importance=0.8)
```

---

### 🌐 Browser Automation

Playwright-based browser control with stealth capabilities.

```bash
!browser open https://example.com
!browser screenshot
!browser click "#login-button"
!browser type "#email" "user@example.com"
!browser navigate https://dashboard.example.com
```

**Features:**
- Playwright engine with async support
- Stealth mode (avoids bot detection)
- Screenshot capture (full page or element)
- Form filling and clicking
- Multi-tab management
- Content extraction

Install: `pip install rally-agent[browser]`

---

### 🖥️ Computer Use

Screen capture, mouse/keyboard control, and OCR for desktop automation.

```python
# Take screenshot and analyze
result = await engine.computer_use_screenshot()

# Click at coordinates
await engine.computer_use_click(500, 300)

# Type text
await engine.computer_use_type("Hello World")
```

**Features:**
- Screen capture (full screen or region)
- Mouse click/move/drag at coordinates
- Keyboard input simulation
- OCR text extraction from screenshots
- Platform-aware (X11, Wayland, macOS, Windows)

---

### 🎤 Voice Interface

Full voice pipeline: speech-to-text, text-to-speech, and wake word detection.

```bash
# Start voice mode
rally voice

# Or configure in config.yaml
voice:
  stt_engine: whisper     # whisper | vosk
  tts_engine: edge-tts    # edge-tts | coqui
  wake_word: "hey rally"
  language: en
```

**STT Engines:**
- **Whisper** (local, highest quality) — via `openai-whisper`
- **Vosk** (local, lightweight) — offline recognition

**TTS Engines:**
- **Edge TTS** — Microsoft's free TTS with 300+ voices
- **Coqui TTS** — Local neural TTS

**Wake Word:**
- **openWakeWord** — Custom wake word detection

Install: `pip install rally-agent[voice]` (basic) or `pip install rally-agent[voice-full]` (all engines)

---

### ⏰ Cron & Automation

10 job types with cron expression parsing, persistent job store, and concurrent execution.

```bash
# Add a cron job
!cron add "0 9 * * *" "Check my email" --type agentTurn
!cron add "@every 30m" "System health check" --type healthCheck
!cron add "@daily" "Consolidate memory" --type memoryConsolidate

# List jobs
!cron list

# View history
!cron history
```

**Job Types:**

| Type | Description |
|---|---|
| `systemEvent` | Inject text into main session |
| `agentTurn` | Run agent with a message (isolated session) |
| `shellCommand` | Run shell command on schedule |
| `webhook` | HTTP POST to URL on schedule |
| `fileWatch` | Trigger when file changes |
| `emailCheck` | Check email on schedule |
| `newsGather` | Gather news on schedule |
| `healthCheck` | Check system health on schedule |
| `memoryConsolidate` | Consolidate memory periodically |
| `patternAnalysis` | Analyze user patterns periodically |

**Cron syntax:** Standard 5-field cron plus human aliases (`@daily`, `@hourly`, `@every 30m`, etc.)

---

### 🔄 Self-Improvement

Learns from every interaction. Captures corrections, preferences, failures, and successes.

**What it tracks:**
- **Corrections** — When you correct the agent, it remembers forever
- **Preferences** — Extracts your style, tools, patterns
- **Success/failure patterns** — Mines what works and what doesn't
- **Knowledge graph** — Entities and relationships from conversations
- **Confidence scoring** — Tracks how confident it is in different areas
- **Conversation quality metrics** — Measures interaction effectiveness

```bash
# View improvement report
!improve report

# View learned preferences
!improve preferences
```

---

### 🕸️ Knowledge Graph

Lightweight, persistent knowledge graph that extracts entities and relationships from conversations.

**Entity types:** Person, Project, Tool, Concept, Technology, Language, Framework, File, Organization, Location, Event, URL

**Relation types:** Uses, Mentions, Works On, Relates To, Depends On

```bash
# Search the knowledge graph
!knowledge search "Python web frameworks"

# View stats
!knowledge stats
```

Storage: JSON-based graph with nodes and edges. No external dependencies — pure Python.

---

### 🔄 Workflow Engine

Record, replay, and automate user workflows. Detects repeated patterns and suggests automation.

```bash
# Start recording
!workflow record "deploy-to-staging"

# ... do your work ...

# Stop recording
!workflow stop

# Replay later
!workflow replay "deploy-to-staging"

# List all workflows
!workflow list
```

**Step types:** command, file_op, api_call, llm_prompt, condition, loop, wait, user_input, transform, custom

**Triggers:** manual, cron, file_change, webhook, event

---

### 🛡️ Security

```bash
# Security features:
# - ⛔ Command blocking — dangerous commands are blocked
# - 🔒 File protection — sensitive files can't be accessed
# - 🛡️ Injection detection — prompt injection attempts caught
# - 📋 Audit logging — all actions logged
# - 🔐 Output sanitization — API keys auto-redacted
# - 🔑 Encryption — memory encrypted at rest
# - 🧱 Sandboxing — tools run in isolation
```

**Configurable security manager** with policies for:
- Command allowlists/denylists
- File access restrictions
- Network request filtering
- Prompt injection detection patterns

---

### 👥 Multi-User

JWT authentication with bcrypt password hashing, RBAC, shared workspaces, and per-user quotas.

**Roles:**

| Role | Permissions |
|---|---|
| `viewer` | Read-only access |
| `user` | Standard operations |
| `admin` | Full system access |

**Features:**
- JWT token authentication (PyJWT with fallback)
- bcrypt password hashing (with hashlib fallback)
- Per-user conversation history and memory
- Shared workspaces with access control
- Per-user configuration overrides
- Usage quotas and rate limiting
- Activity logging and session management

---

### 📊 Observability

Full metrics, cost tracking, and alerting system.

```bash
# View metrics
!metrics

# Cost tracking
!cost daily
!cost weekly
!cost monthly

# Alerts
!alerts list
```

**What's tracked:**
- Token usage per provider/conversation/user
- Latency metrics (p50, p95, p99)
- Cost estimation per provider
- Agent status monitoring
- Memory health stats
- Error tracking with stack traces
- System resource monitoring (CPU, memory, disk)
- Prometheus export format
- Configurable alerts (info, warning, critical)

---

### 🔌 Plugin System

Full plugin SDK with discovery, hot-reload, sandboxing, versioning, and marketplace support.

```python
# Create a plugin
from core.plugins import PluginBase

class MyPlugin(PluginBase):
    name = "my-plugin"
    version = "1.0.0"
    description = "Does something cool"

    async def on_load(self):
        # Register tools, hooks, etc.
        pass

    async def on_message(self, message):
        # Handle messages
        pass
```

**Features:**
- Plugin SDK with base class
- Auto-discovery from `~/.rally-agent/plugins/`
- Hot-reload on file change
- Sandboxed execution (restricted globals)
- Version management with semver
- Dependency resolution
- Hook system (on_load, on_message, on_tool_call, etc.)
- Marketplace for sharing plugins
- Security validation (code scanning)

---

### 🎨 Web UI

FastAPI-powered web interface with real-time WebSocket chat.

```bash
rally web  # http://localhost:8778
```

**Pages:**

| Page | Description |
|---|---|
| 💬 **Chat** | Real-time SSE/WebSocket chat with streaming |
| 📊 **Dashboard** | Stats, metrics, system overview |
| 🤖 **Agents** | Browse all 10 specialized agents |
| 🔧 **Tools** | Browse all 30+ built-in skills |
| 🧠 **Memory** | View, search, manage persistent memory |
| 🌐 **Providers** | All 36 AI providers with status |
| 📡 **Channels** | All 52 channels with config status |
| 📁 **File Manager** | Browse, navigate, download files |
| ⬇️ **Downloads** | Agent-created files, one-click download |
| ⚙️ **Configuration** | Full config editor |

**Design:** Dark purple hacker theme with neon accents, smooth animations, fully responsive.

---

### 💬 CLI Commands

Full command reference for the interactive REPL:

```bash
# Core
rally                    # Start interactive CLI
rally web                # Start web UI
rally status             # System status
rally --help             # Help

# In REPL
!help                    # Show all commands
!status                  # System status
!model <name>            # Switch AI model
!think on/off            # Toggle thinking mode
!compact on/off          # Toggle compact mode

# Providers
!providers               # List all providers
!health                  # Provider health checks

# Agents
!agents                  # List agents
!spawn <type>            # Spawn an agent

# Tools
!tools                   # List all tools
!<tool> <args>           # Direct tool call (e.g., !git status)

# Memory
!memory                  # Memory stats
!search <query>          # Search memory
!memory clear            # Clear memory

# Conversation
!save <path>             # Save conversation
!load <path>             # Load conversation
!branch [name]           # Create branch
!checkout <name>         # Switch branch
!merge <name>            # Merge branch
!branches                # List branches

# Automation
!cron list               # List cron jobs
!cron add <sched> <task> # Add cron job
!cron remove <id>        # Remove job
!cron history            # Job history

# Workflows
!workflow record <name>  # Start recording
!workflow stop           # Stop recording
!workflow replay <name>  # Replay workflow
!workflow list           # List workflows

# Config
!config                  # Show config
!config set <key> <val>  # Set config value
```

---

## 📖 Usage

### Usage Examples

```bash
rally
> What's the weather in Tokyo?
> Write a Python script to scrape Hacker News
> Explain quantum computing like I'm 10
```

### Direct Tool Calls

```bash
rally
> !git status
> !system cpu
> !web search "latest Python features"
> !python run "print('hello')"
```

### Multi-Agent Tasks

```bash
rally
> Research the best Python web frameworks, write a comparison, and create a decision matrix
# → Researcher + Coder + Analyst agents collaborate
```

### Voice Mode

```bash
rally voice
# Speak naturally, Rally listens and responds
```

### Web UI

```bash
rally web
# Open http://localhost:8778 in your browser
```

---

## ⚙️ Configuration

Rally uses a YAML config file at `~/.rally-agent/config.yaml`:

```yaml
# ── AI Provider Keys ────────────────────────────────────
providers:
  openai:
    api_key: "sk-..."
  anthropic:
    api_key: "sk-ant-..."
  google:
    api_key: "AIza..."
  ollama:
    host: "http://localhost:11434"

# ── Agent Settings ──────────────────────────────────────
agent:
  default_model: "auto"        # auto | provider/model-name
  max_context: 128000
  max_tokens: 4096
  thinking: true

# ── Engine ──────────────────────────────────────────────
engine:
  fallback_order:
    - anthropic
    - openai
    - google
    - groq
    - openrouter
    - ollama
  retry_max_attempts: 3
  circuit_breaker_threshold: 5
  circuit_breaker_timeout: 60.0

# ── Memory ──────────────────────────────────────────────
memory:
  max_entries: 10000
  auto_consolidate: true
  encryption: false
  backend: "hybrid"            # hybrid | vector | keyword

# ── Web UI ──────────────────────────────────────────────
web:
  host: "0.0.0.0"
  port: 8778

# ── Voice ───────────────────────────────────────────────
voice:
  stt_engine: "whisper"        # whisper | vosk
  tts_engine: "edge-tts"       # edge-tts | coqui
  wake_word: "hey rally"
  language: "en"
```

### Environment Variables

All config values can be overridden with environment variables:

```bash
# Provider keys
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=AIza...
GROQ_API_KEY=gsk_...
DEEPSEEK_API_KEY=sk-...

# Rally settings
RALLY_DATA=~/.rally-agent/data
RALLY_PORT=8778
RALLY_LOG_LEVEL=info
RALLY_DEFAULT_MODEL=auto
RALLY_SECRET_KEY=your-secret-key
```

---

## 🐳 Docker

### Start & Stop

```bash
# Start
docker-compose up -d

# View logs
docker-compose logs -f rally

# Stop
docker-compose down

# Full rebuild
docker-compose build --no-cache && docker-compose up -d
```

### Environment File

Create a `.env` file:

```bash
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
RALLY_DEFAULT_MODEL=auto
RALLY_LOG_LEVEL=info
```

### Volumes

- `rally-data:/data` — Persistent data (memory, config, workflows)
- Config can be mounted at `/data/config`

### Resource Limits

Default: 4GB memory, 2 CPU cores. Adjust in `docker-compose.yml`:

```yaml
deploy:
  resources:
    limits:
      memory: 4G
      cpus: "2.0"
```

---

## 🛠️ Development

### Setup

```bash
git clone https://github.com/Atum246/rally-agent.git
cd rally-agent
pip install -e ".[dev]"
```

### Code Quality

```bash
# Lint
ruff check .

# Format
black .

# Type check
mypy .

# Sort imports
isort .
```

### Testing

```bash
pytest
pytest --cov=core --cov=tools --cov=agents
```

### Project Structure

```
rally-agent/
├── rally.py              # Entry point & CLI
├── core/                 # Core engine
│   ├── engine.py         # Main orchestrator
│   ├── providers.py      # 36 LLM providers
│   ├── config.py         # Configuration
│   ├── automation.py     # Cron scheduler
│   ├── intelligence.py   # Proactive intelligence
│   ├── self_improve.py   # Self-improvement engine
│   ├── knowledge_graph.py# Entity/relationship graph
│   ├── workflow_engine.py# Record/replay workflows
│   ├── computer_use.py   # Screen control
│   ├── system_control.py # System management
│   ├── multiuser.py      # Auth & RBAC
│   ├── observability.py  # Metrics & cost tracking
│   ├── plugins.py        # Plugin system
│   └── user_model.py     # User profiling
├── agents/               # Multi-agent system
│   ├── orchestrator.py   # 10 specialized agents
│   ├── swarm.py          # Swarm intelligence
│   └── coder.py          # Code agent
├── memory/               # Memory system
│   ├── store.py          # Hybrid vector+BM25 store
│   └── rag.py            # RAG context injection
├── tools/                # Tool system
│   ├── registry.py       # Tool registry
│   ├── skills.py         # 30+ built-in skills
│   ├── web_search.py     # Web search
│   ├── browser.py        # Browser automation
│   ├── computer_use.py   # Computer control
│   ├── exec_sandbox.py   # Sandboxed execution
│   └── system_control.py # System tools
├── integrations/         # Channel system
│   └── channels.py       # 52 messaging channels
├── security/             # Security layer
│   └── manager.py        # Policies & enforcement
├── voice/                # Voice interface
│   ├── stt.py            # Speech-to-text
│   ├── tts.py            # Text-to-speech
│   └── wakeword.py       # Wake word detection
├── web/                  # Web UI
│   └── server.py         # FastAPI application
├── cli/                  # CLI interface
│   ├── banner.py         # ASCII art
│   ├── theme.py          # Purple hacker theme
│   ├── repl.py           # Interactive REPL
│   └── commands.py       # Command router
├── marketplace/          # Plugin marketplace
├── docker-compose.yml    # Docker config
├── setup.py              # Package setup
└── pyproject.toml        # Project config
```

---

## 📦 Optional Dependencies

Install only what you need:

```bash
pip install rally-agent              # Core only
pip install rally-agent[browser]     # + Playwright browser automation
pip install rally-agent[voice]       # + Edge TTS
pip install rally-agent[voice-full]  # + Whisper, Coqui, wake word
pip install rally-agent[rag]         # + ChromaDB, sentence-transformers
pip install rally-agent[docs]        # + PDF, DOCX, Markdown parsing
pip install rally-agent[data]        # + NumPy, Pandas
pip install rally-agent[db]          # + PostgreSQL, Redis
pip install rally-agent[image]       # + Pillow, ReportLab
pip install rally-agent[finetune]    # + PyTorch, Transformers, PEFT
pip install rally-agent[all]         # Everything
pip install rally-agent[dev]         # Dev tools (pytest, black, ruff, mypy)
```

---

## 📄 License

MIT License — use it, fork it, ship it. 🚀

See [LICENSE](LICENSE) for details.

---

## ❓ Troubleshooting

### Install: "destination path already exists and is not an empty directory"

This happens when a previous install left behind a non-empty `~/.rally-agent` directory.

**Windows (PowerShell):**
```powershell
Remove-Item -Recurse -Force ~/.rally-agent
irm https://raw.githubusercontent.com/Atum246/rally-agent/main/install.ps1 | iex
```

**Windows (Command Prompt — cmd.exe):**
```cmd
rmdir /s /q "%USERPROFILE%\.rally-agent"
```
Then run the installer from PowerShell (not Command Prompt).

**Linux / macOS:**
```bash
rm -rf ~/.rally-agent
curl -fsSL https://raw.githubusercontent.com/Atum246/rally-agent/main/install.sh | bash
```

> **Note:** The install script is a PowerShell script (`.ps1`). You must run it from **PowerShell**, not Command Prompt. If you're in `cmd.exe`, type `powershell` first to switch.

---

### Install: "'Remove-Item' is not recognized"

You're in **Command Prompt** (cmd.exe), not PowerShell. The install script requires PowerShell.

```cmd
:: Switch to PowerShell first
powershell

:: Then run the installer
irm https://raw.githubusercontent.com/Atum246/rally-agent/main/install.ps1 | iex
```

---

### Install: "Python not found" or "python is not recognized"

Rally Agent requires Python 3.10+. Install it from [python.org](https://python.org/downloads/) and make sure to check **"Add Python to PATH"** during installation.

**Verify Python is installed:**
```powershell
python --version
```

If you have Python installed but it's not found, try:
```powershell
py --version
```

---

### Install: "pip is not trusted" or "externally-managed-environment"

This happens on newer Python versions with PEP 668. Use a virtual environment:

```bash
python -m venv ~/.rally-agent/.venv
source ~/.rally-agent/.venv/bin/activate  # Linux/macOS
# or
~\.rally-agent\.\Scripts\activate  # Windows

pip install -e .
```

---

### Web UI: "Web UI requires: pip install fastapi uvicorn python-multipart pyjwt"

Install the web dependencies:
```bash
pip install fastapi uvicorn python-multipart pyjwt
```

Or install everything at once:
```bash
pip install -e ".[all]"
```

---

### Runtime: "No AI providers configured"

Set at least one API key:
```bash
export OPENAI_API_KEY="sk-..."
# or
export ANTHROPIC_API_KEY="sk-ant-..."
# or
export GOOGLE_API_KEY="AIza..."
```

Or use local models with Ollama (no API key needed):
```bash
ollama pull llama3.2
```

---

### Runtime: "Rate limited" errors

You've hit the API rate limit for your provider. Solutions:
1. **Add more providers** — Rally automatically falls back to the next available provider
2. **Use a faster provider** — Groq, Cerebras, or SambaNova have higher limits
3. **Use local models** — Ollama has no rate limits

---

### Docker: "port is already allocated"

Another service is using port 8778. Change the port:
```bash
RALLY_PORT=9000 docker-compose up -d
```

Or edit `docker-compose.yml` and change the port mapping.

---

### General: "command not found: rally"

The `rally` command isn't in your PATH. Either:
1. **Activate the virtual environment:**
   ```bash
   source ~/.rally-agent/.venv/bin/activate
   ```
2. **Run directly:**
   ```bash
   python ~/.rally-agent/rally.py
   ```

---

### Still stuck?

- 📖 [Documentation](https://github.com/Atum246/rally-agent#readme)
- 🐛 [Report a Bug](https://github.com/Atum246/rally-agent/issues)
- 💬 [Discussions](https://github.com/Atum246/rally-agent/discussions)

---

## 🙏 Credits

Built with 💜 by the Rally Labs team.

**Key dependencies:**
- [httpx](https://github.com/encode/httpx) — Async HTTP client
- [Rich](https://github.com/Textualize/rich) — Terminal formatting
- [FastAPI](https://github.com/tiangolo/fastapi) — Web framework
- [Playwright](https://github.com/microsoft/playwright-python) — Browser automation
- [sentence-transformers](https://github.com/UKPLab/sentence-transformers) — Embeddings
- [ChromaDB](https://github.com/chroma-core/chroma) — Vector database
- [Edge TTS](https://github.com/rany2/edge-tts) — Text-to-speech
- [Whisper](https://github.com/openai/whisper) — Speech-to-text

---

<p align="center">
  <strong>⭐ Star this repo if Rally Agent made your life better! ⭐</strong>
</p>

<p align="center">
  <sub>⚡ Your AI. Your Rules. Your Data. ⚡</sub>
</p>
