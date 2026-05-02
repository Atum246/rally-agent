"""
🟣 Rally Agent — Web Server
Full-featured web UI inspired by Manus AI.
Beautiful purple theme. No generic trash.
"""

import os
import json
import asyncio
import time
from pathlib import Path
from datetime import datetime

from cli.theme import Theme


# ═══════════════════════════════════════════════════════════════
# 🌐 Rally Web Server — FastAPI + WebSocket
# ═══════════════════════════════════════════════════════════════

def create_app(engine):
    """Create the Rally Agent web application"""
    try:
        from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
        from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
        from fastapi.staticfiles import StaticFiles
        import uvicorn
    except ImportError:
        raise RuntimeError("Web UI requires: pip install fastapi uvicorn")

    app = FastAPI(title="Rally Agent", version="1.0.0")

    # ── WebSocket connections ──────────────────────────────────
    active_connections: list[WebSocket] = []

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await websocket.accept()
        active_connections.append(websocket)
        try:
            while True:
                data = await websocket.receive_text()
                msg = json.loads(data)

                if msg.get("type") == "chat":
                    response = await engine.chat(msg.get("content", ""))
                    await websocket.send_json({
                        "type": "response",
                        "content": response,
                        "timestamp": datetime.now().isoformat(),
                    })
                elif msg.get("type") == "tool":
                    result = await engine._handle_tool_call(msg.get("command", ""))
                    await websocket.send_json({
                        "type": "tool_result",
                        "content": result,
                        "timestamp": datetime.now().isoformat(),
                    })
        except WebSocketDisconnect:
            active_connections.remove(websocket)

    # ── API Routes ─────────────────────────────────────────────
    @app.get("/api/status")
    async def get_status():
        uptime = time.time() - engine.start_time
        return {
            "status": "running",
            "version": "1.0.0",
            "model": engine.current_model,
            "thinking": engine.thinking_enabled,
            "messages": len(engine.conversation),
            "uptime": int(uptime),
            "tools": len(engine.tools.get_all()) if engine.tools else 0,
            "agents": len(engine.agents.get_all()) if engine.agents else 0,
            "memory": engine.memory.count() if engine.memory else 0,
        }

    @app.get("/api/agents")
    async def get_agents():
        if engine.agents:
            return {"agents": engine.agents.get_all()}
        return {"agents": []}

    @app.get("/api/tools")
    async def get_tools():
        if engine.tools:
            return {"tools": engine.tools.get_all()}
        return {"tools": []}

    @app.get("/api/memory")
    async def get_memory():
        if engine.memory:
            return {"entries": engine.memory.get_recent(100), "count": engine.memory.count()}
        return {"entries": [], "count": 0}

    @app.get("/api/memory/search")
    async def search_memory(q: str = ""):
        if engine.memory and q:
            return {"results": engine.memory.search(q)}
        return {"results": []}

    @app.get("/api/conversation")
    async def get_conversation():
        return {"messages": engine.conversation[-100:]}

    @app.get("/api/providers")
    async def get_providers():
        if engine.providers:
            return {"providers": engine.providers.get_all_info()}
        return {"providers": []}

    @app.get("/api/channels")
    async def get_channels():
        from integrations.channels import ChannelManager
        cm = ChannelManager(engine.config)
        return {"channels": cm.get_all_info()}

    @app.get("/api/config")
    async def get_config():
        return {"config": engine.config.data}

    @app.post("/api/config")
    async def set_config(request: Request):
        data = await request.json()
        key = data.get("key", "")
        value = data.get("value", "")
        if key:
            engine.config.set(key, value)
            return {"success": True}
        return {"success": False, "error": "Missing key"}

    @app.get("/api/files")
    async def list_files(path: str = "."):
        try:
            entries = []
            full_path = os.path.abspath(path)
            for entry in sorted(os.listdir(full_path)):
                entry_path = os.path.join(full_path, entry)
                is_dir = os.path.isdir(entry_path)
                size = 0 if is_dir else os.path.getsize(entry_path)
                entries.append({
                    "name": entry,
                    "path": entry_path,
                    "is_dir": is_dir,
                    "size": size,
                    "modified": datetime.fromtimestamp(os.path.getmtime(entry_path)).isoformat(),
                })
            return {"files": entries, "path": full_path}
        except Exception as e:
            return {"files": [], "error": str(e)}

    @app.get("/api/files/download")
    async def download_file(path: str):
        if os.path.exists(path) and os.path.isfile(path):
            return FileResponse(path, filename=os.path.basename(path))
        return JSONResponse({"error": "File not found"}, status_code=404)

    @app.get("/api/files/read")
    async def read_file(path: str):
        try:
            with open(path) as f:
                content = f.read(100000)
            return {"content": content, "path": path}
        except Exception as e:
            return {"error": str(e)}

    @app.post("/api/chat")
    async def chat_endpoint(request: Request):
        data = await request.json()
        message = data.get("message", "")
        if message:
            response = await engine.chat(message)
            return {"response": response, "timestamp": datetime.now().isoformat()}
        return {"error": "No message provided"}

    @app.post("/api/task")
    async def run_task(request: Request):
        data = await request.json()
        task = data.get("task", "")
        if task:
            result = await engine.run_task(task)
            return {"result": result}
        return {"error": "No task provided"}

    @app.get("/api/stats")
    async def get_stats():
        return {
            "total_messages": len(engine.conversation),
            "user_messages": len([m for m in engine.conversation if m.get("role") == "user"]),
            "assistant_messages": len([m for m in engine.conversation if m.get("role") == "assistant"]),
            "memory_entries": engine.memory.count() if engine.memory else 0,
            "tools_available": len(engine.tools.get_all()) if engine.tools else 0,
            "agents_available": len(engine.agents.get_all()) if engine.agents else 0,
            "providers_available": len(engine.providers.get_available()) if engine.providers else 0,
        }

    # ── Main Web UI ────────────────────────────────────────────
    @app.get("/", response_class=HTMLResponse)
    async def index():
        return WEB_UI_HTML

    @app.get("/app", response_class=HTMLResponse)
    async def app_page():
        return WEB_UI_HTML

    return app


def start_web_server(engine, port: int = 8778):
    """Start the web server"""
    try:
        import uvicorn
        app = create_app(engine)
        Theme.success(f"🌐 Web UI: http://localhost:{port}")
        uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
    except ImportError:
        Theme.error("Web UI requires: pip install fastapi uvicorn")
    except Exception as e:
        Theme.error(f"Web server error: {e}")


# ═══════════════════════════════════════════════════════════════
# 🎨 THE WEB UI — Manus AI Inspired, Purple Theme
# ═══════════════════════════════════════════════════════════════

WEB_UI_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Rally Agent — The OpenClaw Killer</title>
<style>
/* ═══════════════════════════════════════════════════════════════
   🟣 RALLY AGENT — Hacker Purple Theme
   Manus AI Inspired. Not generic trash.
   ═══════════════════════════════════════════════════════════════ */

:root {
  --purple-50: #faf5ff;
  --purple-100: #f3e8ff;
  --purple-200: #e9d5ff;
  --purple-300: #d8b4fe;
  --purple-400: #c084fc;
  --purple-500: #a855f7;
  --purple-600: #9333ea;
  --purple-700: #7c3aed;
  --purple-800: #6b21a8;
  --purple-900: #581c87;
  --purple-950: #3b0764;

  --bg-primary: #0a0612;
  --bg-secondary: #110b1f;
  --bg-tertiary: #1a0e2e;
  --bg-card: #150d24;
  --bg-hover: #1f1438;
  --bg-input: #0d0820;

  --text-primary: #f0e6ff;
  --text-secondary: #a78bcc;
  --text-muted: #6b5a80;
  --text-accent: #d8b4fe;

  --border: #2a1f42;
  --border-active: #7c3aed;

  --neon: #d946ef;
  --cyan: #22d3ee;
  --green: #4ade80;
  --amber: #fbbf24;
  --red: #ef4444;
  --pink: #f472b6;

  --radius: 12px;
  --radius-lg: 16px;
  --radius-xl: 24px;

  --shadow: 0 4px 24px rgba(88, 28, 135, 0.3);
  --shadow-lg: 0 8px 40px rgba(88, 28, 135, 0.4);
  --glow: 0 0 20px rgba(168, 85, 247, 0.3);
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  background: var(--bg-primary);
  color: var(--text-primary);
  min-height: 100vh;
  overflow: hidden;
}

/* ── Layout ──────────────────────────────────────────────────── */

.app {
  display: flex;
  height: 100vh;
}

/* ── Sidebar ─────────────────────────────────────────────────── */

.sidebar {
  width: 260px;
  background: var(--bg-secondary);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

.sidebar-header {
  padding: 20px;
  border-bottom: 1px solid var(--border);
}

.logo {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 20px;
  font-weight: 800;
  color: var(--purple-400);
  letter-spacing: -0.5px;
}

.logo-icon {
  width: 36px;
  height: 36px;
  background: linear-gradient(135deg, var(--purple-600), var(--neon));
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  box-shadow: var(--glow);
}

.nav {
  flex: 1;
  padding: 12px;
  overflow-y: auto;
}

.nav-section {
  margin-bottom: 8px;
}

.nav-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 1px;
  padding: 8px 12px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: var(--radius);
  cursor: pointer;
  transition: all 0.2s;
  font-size: 14px;
  color: var(--text-secondary);
  font-weight: 500;
}

.nav-item:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.nav-item.active {
  background: linear-gradient(135deg, rgba(168, 85, 247, 0.2), rgba(217, 70, 239, 0.1));
  color: var(--purple-300);
  border: 1px solid rgba(168, 85, 247, 0.3);
}

.nav-item .icon { font-size: 18px; width: 24px; text-align: center; }
.nav-item .badge {
  margin-left: auto;
  background: var(--purple-700);
  color: var(--purple-200);
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  font-weight: 600;
}

/* ── Main Content ────────────────────────────────────────────── */

.main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

/* ── Top Bar ─────────────────────────────────────────────────── */

.topbar {
  height: 56px;
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  padding: 0 24px;
  background: var(--bg-secondary);
  gap: 16px;
}

.topbar-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.topbar-status {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--green);
}

.topbar-status .dot {
  width: 8px;
  height: 8px;
  background: var(--green);
  border-radius: 50%;
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.topbar-right {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 12px;
}

.model-badge {
  background: var(--bg-tertiary);
  border: 1px solid var(--border);
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 12px;
  color: var(--purple-300);
  font-weight: 600;
}

/* ── Chat Area ───────────────────────────────────────────────── */

.chat-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  height: calc(100vh - 56px);
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  scroll-behavior: smooth;
}

.chat-messages::-webkit-scrollbar { width: 6px; }
.chat-messages::-webkit-scrollbar-track { background: transparent; }
.chat-messages::-webkit-scrollbar-thumb { background: var(--purple-800); border-radius: 3px; }

.message {
  display: flex;
  gap: 12px;
  margin-bottom: 24px;
  max-width: 800px;
  animation: fadeIn 0.3s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.message.user { margin-left: auto; flex-direction: row-reverse; }

.message-avatar {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  flex-shrink: 0;
}

.message.user .message-avatar {
  background: linear-gradient(135deg, var(--pink), var(--neon));
}

.message.assistant .message-avatar {
  background: linear-gradient(135deg, var(--purple-600), var(--purple-400));
  box-shadow: var(--glow);
}

.message-content {
  padding: 14px 18px;
  border-radius: var(--radius-lg);
  font-size: 14px;
  line-height: 1.6;
  max-width: 680px;
}

.message.user .message-content {
  background: linear-gradient(135deg, var(--purple-700), var(--purple-800));
  border: 1px solid var(--purple-600);
  color: var(--purple-100);
}

.message.assistant .message-content {
  background: var(--bg-card);
  border: 1px solid var(--border);
  color: var(--text-primary);
}

.message-content pre {
  background: var(--bg-primary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px;
  margin: 10px 0;
  overflow-x: auto;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-size: 13px;
  color: var(--cyan);
}

.message-content code {
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  background: rgba(168, 85, 247, 0.15);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 13px;
  color: var(--purple-300);
}

.message-time {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 6px;
}

/* ── Chat Input ──────────────────────────────────────────────── */

.chat-input-area {
  padding: 16px 24px 24px;
  border-top: 1px solid var(--border);
  background: var(--bg-secondary);
}

.chat-input-wrapper {
  max-width: 800px;
  margin: 0 auto;
  position: relative;
}

.chat-input {
  width: 100%;
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 16px 56px 16px 20px;
  color: var(--text-primary);
  font-size: 14px;
  font-family: inherit;
  resize: none;
  outline: none;
  transition: border-color 0.2s, box-shadow 0.2s;
  min-height: 52px;
  max-height: 200px;
}

.chat-input:focus {
  border-color: var(--purple-500);
  box-shadow: 0 0 0 3px rgba(168, 85, 247, 0.15);
}

.chat-input::placeholder {
  color: var(--text-muted);
}

.send-btn {
  position: absolute;
  right: 8px;
  bottom: 8px;
  width: 36px;
  height: 36px;
  background: linear-gradient(135deg, var(--purple-600), var(--neon));
  border: none;
  border-radius: 10px;
  color: white;
  font-size: 16px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
  box-shadow: var(--glow);
}

.send-btn:hover {
  transform: scale(1.05);
  box-shadow: 0 0 30px rgba(168, 85, 247, 0.5);
}

/* ── Pages ───────────────────────────────────────────────────── */

.page { display: none; height: calc(100vh - 56px); overflow-y: auto; padding: 24px; }
.page.active { display: block; }

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
}

.page-title {
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary);
}

.page-subtitle {
  font-size: 14px;
  color: var(--text-secondary);
  margin-top: 4px;
}

/* ── Cards Grid ──────────────────────────────────────────────── */

.cards-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
}

.card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 20px;
  transition: all 0.2s;
  cursor: pointer;
}

.card:hover {
  border-color: var(--purple-600);
  box-shadow: var(--shadow);
  transform: translateY(-2px);
}

.card-icon {
  width: 44px;
  height: 44px;
  background: linear-gradient(135deg, rgba(168, 85, 247, 0.2), rgba(217, 70, 239, 0.1));
  border: 1px solid rgba(168, 85, 247, 0.3);
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  margin-bottom: 14px;
}

.card-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 6px;
}

.card-desc {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
}

.card-status {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  padding: 3px 10px;
  border-radius: 20px;
  margin-top: 12px;
  font-weight: 600;
}

.card-status.online { background: rgba(74, 222, 128, 0.15); color: var(--green); }
.card-status.offline { background: rgba(107, 90, 128, 0.15); color: var(--text-muted); }
.card-status.configured { background: rgba(168, 85, 247, 0.15); color: var(--purple-300); }

/* ── Stats Grid ──────────────────────────────────────────────── */

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}

.stat-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 20px;
  text-align: center;
}

.stat-value {
  font-size: 32px;
  font-weight: 800;
  background: linear-gradient(135deg, var(--purple-400), var(--neon));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.stat-label {
  font-size: 13px;
  color: var(--text-secondary);
  margin-top: 4px;
  font-weight: 500;
}

/* ── Table ───────────────────────────────────────────────────── */

.data-table {
  width: 100%;
  border-collapse: collapse;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.data-table th {
  background: var(--bg-tertiary);
  padding: 12px 16px;
  text-align: left;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  border-bottom: 1px solid var(--border);
}

.data-table td {
  padding: 12px 16px;
  font-size: 14px;
  color: var(--text-primary);
  border-bottom: 1px solid rgba(42, 31, 66, 0.5);
}

.data-table tr:hover td {
  background: var(--bg-hover);
}

/* ── File Browser ────────────────────────────────────────────── */

.file-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.file-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  border-radius: var(--radius);
  cursor: pointer;
  transition: background 0.15s;
}

.file-item:hover { background: var(--bg-hover); }

.file-icon { font-size: 20px; width: 28px; text-align: center; }
.file-name { flex: 1; font-size: 14px; color: var(--text-primary); }
.file-size { font-size: 12px; color: var(--text-muted); }
.file-date { font-size: 12px; color: var(--text-muted); }

.file-download {
  background: rgba(168, 85, 247, 0.15);
  border: 1px solid rgba(168, 85, 247, 0.3);
  color: var(--purple-300);
  padding: 4px 12px;
  border-radius: 8px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
  text-decoration: none;
}

.file-download:hover {
  background: rgba(168, 85, 247, 0.3);
}

/* ── Empty State ─────────────────────────────────────────────── */

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  text-align: center;
}

.empty-icon { font-size: 48px; margin-bottom: 16px; }
.empty-title { font-size: 18px; font-weight: 600; color: var(--text-primary); margin-bottom: 8px; }
.empty-desc { font-size: 14px; color: var(--text-secondary); max-width: 400px; }

/* ── Buttons ─────────────────────────────────────────────────── */

.btn {
  padding: 8px 20px;
  border-radius: var(--radius);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  border: none;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.btn-primary {
  background: linear-gradient(135deg, var(--purple-600), var(--neon));
  color: white;
  box-shadow: var(--glow);
}

.btn-primary:hover { transform: translateY(-1px); box-shadow: var(--shadow-lg); }

.btn-secondary {
  background: var(--bg-tertiary);
  border: 1px solid var(--border);
  color: var(--text-primary);
}

.btn-secondary:hover { border-color: var(--purple-600); }

/* ── Scrollbar ───────────────────────────────────────────────── */

::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--purple-900); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--purple-700); }

/* ── Responsive ──────────────────────────────────────────────── */

@media (max-width: 768px) {
  .sidebar { display: none; }
  .chat-messages { padding: 16px; }
  .stats-grid { grid-template-columns: repeat(2, 1fr); }
  .cards-grid { grid-template-columns: 1fr; }
}
</style>
</head>
<body>

<div class="app">
  <!-- ═══ Sidebar ═══ -->
  <div class="sidebar">
    <div class="sidebar-header">
      <div class="logo">
        <div class="logo-icon">⚡</div>
        Rally Agent
      </div>
    </div>

    <nav class="nav">
      <div class="nav-section">
        <div class="nav-label">Main</div>
        <div class="nav-item active" data-page="chat">
          <span class="icon">💬</span> Chat
        </div>
        <div class="nav-item" data-page="dashboard">
          <span class="icon">📊</span> Dashboard
        </div>
        <div class="nav-item" data-page="agents">
          <span class="icon">🤖</span> Agents
          <span class="badge" id="agent-count">10</span>
        </div>
      </div>

      <div class="nav-section">
        <div class="nav-label">System</div>
        <div class="nav-item" data-page="tools">
          <span class="icon">🔧</span> Tools
          <span class="badge" id="tool-count">15</span>
        </div>
        <div class="nav-item" data-page="memory">
          <span class="icon">🧠</span> Memory
        </div>
        <div class="nav-item" data-page="providers">
          <span class="icon">🌐</span> Providers
        </div>
        <div class="nav-item" data-page="channels">
          <span class="icon">📡</span> Channels
          <span class="badge" id="channel-count">55</span>
        </div>
      </div>

      <div class="nav-section">
        <div class="nav-label">Files</div>
        <div class="nav-item" data-page="files">
          <span class="icon">📁</span> File Manager
        </div>
        <div class="nav-item" data-page="downloads">
          <span class="icon">⬇️</span> Downloads
        </div>
      </div>

      <div class="nav-section">
        <div class="nav-label">Settings</div>
        <div class="nav-item" data-page="config">
          <span class="icon">⚙️</span> Configuration
        </div>
      </div>
    </nav>
  </div>

  <!-- ═══ Main Content ═══ -->
  <div class="main">
    <!-- Top Bar -->
    <div class="topbar">
      <div class="topbar-title" id="page-title">Chat</div>
      <div class="topbar-status">
        <span class="dot"></span>
        <span>Running</span>
      </div>
      <div class="topbar-right">
        <span class="model-badge" id="model-badge">auto</span>
      </div>
    </div>

    <!-- ═══ Chat Page ═══ -->
    <div class="chat-container" id="page-chat">
      <div class="chat-messages" id="chat-messages">
        <div class="message assistant">
          <div class="message-avatar">⚡</div>
          <div>
            <div class="message-content">
              Hey! I'm <strong>Rally</strong>, your AI agent. 🟣⚡<br><br>
              I can help you with coding, research, analysis, creative work, and much more.<br><br>
              Just type below to get started, or explore the sidebar to see what I can do!
            </div>
            <div class="message-time">Just now</div>
          </div>
        </div>
      </div>

      <div class="chat-input-area">
        <div class="chat-input-wrapper">
          <textarea class="chat-input" id="chat-input" placeholder="Message Rally..." rows="1"></textarea>
          <button class="send-btn" id="send-btn">➤</button>
        </div>
      </div>
    </div>

    <!-- ═══ Dashboard Page ═══ -->
    <div class="page" id="page-dashboard">
      <div class="page-header">
        <div>
          <div class="page-title">Dashboard</div>
          <div class="page-subtitle">System overview and statistics</div>
        </div>
      </div>

      <div class="stats-grid" id="stats-grid">
        <div class="stat-card"><div class="stat-value" id="stat-messages">0</div><div class="stat-label">Messages</div></div>
        <div class="stat-card"><div class="stat-value" id="stat-memory">0</div><div class="stat-label">Memory Entries</div></div>
        <div class="stat-card"><div class="stat-value" id="stat-tools">15</div><div class="stat-label">Tools</div></div>
        <div class="stat-card"><div class="stat-value" id="stat-agents">10</div><div class="stat-label">Agents</div></div>
        <div class="stat-card"><div class="stat-value" id="stat-providers">0</div><div class="stat-label">Providers</div></div>
        <div class="stat-card"><div class="stat-value" id="stat-channels">55</div><div class="stat-label">Channels</div></div>
      </div>
    </div>

    <!-- ═══ Agents Page ═══ -->
    <div class="page" id="page-agents">
      <div class="page-header">
        <div>
          <div class="page-title">🤖 Agents</div>
          <div class="page-subtitle">Specialized AI agents that work together</div>
        </div>
      </div>
      <div class="cards-grid" id="agents-grid"></div>
    </div>

    <!-- ═══ Tools Page ═══ -->
    <div class="page" id="page-tools">
      <div class="page-header">
        <div>
          <div class="page-title">🔧 Tools</div>
          <div class="page-subtitle">Built-in tools for every task</div>
        </div>
      </div>
      <div class="cards-grid" id="tools-grid"></div>
    </div>

    <!-- ═══ Memory Page ═══ -->
    <div class="page" id="page-memory">
      <div class="page-header">
        <div>
          <div class="page-title">🧠 Memory</div>
          <div class="page-subtitle">Persistent memory system</div>
        </div>
      </div>
      <div class="stats-grid">
        <div class="stat-card"><div class="stat-value" id="mem-total">0</div><div class="stat-label">Total Entries</div></div>
        <div class="stat-card"><div class="stat-value" id="mem-user">0</div><div class="stat-label">User Messages</div></div>
        <div class="stat-card"><div class="stat-value" id="mem-assistant">0</div><div class="stat-label">Assistant Messages</div></div>
      </div>
      <div id="memory-entries" class="file-list"></div>
    </div>

    <!-- ═══ Providers Page ═══ -->
    <div class="page" id="page-providers">
      <div class="page-header">
        <div>
          <div class="page-title">🌐 Providers</div>
          <div class="page-subtitle">35+ AI model providers — every provider on the planet</div>
        </div>
      </div>
      <div class="cards-grid" id="providers-grid"></div>
    </div>

    <!-- ═══ Channels Page ═══ -->
    <div class="page" id="page-channels">
      <div class="page-header">
        <div>
          <div class="page-title">📡 Channels</div>
          <div class="page-subtitle">55+ messaging channels — universal connectivity</div>
        </div>
      </div>
      <div class="cards-grid" id="channels-grid"></div>
    </div>

    <!-- ═══ Files Page ═══ -->
    <div class="page" id="page-files">
      <div class="page-header">
        <div>
          <div class="page-title">📁 File Manager</div>
          <div class="page-subtitle">Browse and download files created by the agent</div>
        </div>
        <button class="btn btn-secondary" id="files-up">⬆️ Up</button>
      </div>
      <div class="file-list" id="files-list"></div>
    </div>

    <!-- ═══ Downloads Page ═══ -->
    <div class="page" id="page-downloads">
      <div class="page-header">
        <div>
          <div class="page-title">⬇️ Downloads</div>
          <div class="page-subtitle">Files created or modified by Rally Agent</div>
        </div>
      </div>
      <div class="file-list" id="downloads-list"></div>
    </div>

    <!-- ═══ Config Page ═══ -->
    <div class="page" id="page-config">
      <div class="page-header">
        <div>
          <div class="page-title">⚙️ Configuration</div>
          <div class="page-subtitle">Rally Agent settings</div>
        </div>
      </div>
      <div id="config-display"></div>
    </div>
  </div>
</div>

<script>
// ═══════════════════════════════════════════════════════════════
// 🟣 Rally Agent — Web UI JavaScript
// ═══════════════════════════════════════════════════════════════

const API = '';
let ws = null;
let currentPath = '.';

// ── Navigation ──────────────────────────────────────────────
document.querySelectorAll('.nav-item').forEach(item => {
  item.addEventListener('click', () => {
    document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
    item.classList.add('active');
    const page = item.dataset.page;
    document.querySelectorAll('.page, .chat-container').forEach(p => p.style.display = 'none');
    const el = document.getElementById('page-' + page);
    if (el) {
      el.style.display = page === 'chat' ? 'flex' : 'block';
      document.getElementById('page-title').textContent = item.textContent.trim().split('\\n')[0].trim();
    }
    loadPage(page);
  });
});

// ── WebSocket ───────────────────────────────────────────────
function connectWS() {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  ws = new WebSocket(`${proto}//${location.host}/ws`);
  ws.onmessage = (e) => {
    const data = JSON.parse(e.data);
    if (data.type === 'response') {
      addMessage('assistant', data.content);
    } else if (data.type === 'tool_result') {
      addMessage('assistant', data.content);
    }
  };
  ws.onclose = () => setTimeout(connectWS, 3000);
}
connectWS();

// ── Chat ────────────────────────────────────────────────────
const chatInput = document.getElementById('chat-input');
const sendBtn = document.getElementById('send-btn');
const chatMessages = document.getElementById('chat-messages');

function addMessage(role, content) {
  const div = document.createElement('div');
  div.className = `message ${role}`;
  const avatar = role === 'user' ? '👤' : '⚡';
  const time = new Date().toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'});
  div.innerHTML = `
    <div class="message-avatar">${avatar}</div>
    <div>
      <div class="message-content">${escapeHtml(content).replace(/\\n/g, '<br>')}</div>
      <div class="message-time">${time}</div>
    </div>
  `;
  chatMessages.appendChild(div);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

async function sendMessage() {
  const msg = chatInput.value.trim();
  if (!msg) return;
  addMessage('user', msg);
  chatInput.value = '';

  try {
    const resp = await fetch(API + '/api/chat', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({message: msg})
    });
    const data = await resp.json();
    if (data.response) addMessage('assistant', data.response);
  } catch (e) {
    addMessage('assistant', '⚠️ Connection error. Is Rally Agent running?');
  }
}

sendBtn.addEventListener('click', sendMessage);
chatInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

chatInput.addEventListener('input', () => {
  chatInput.style.height = 'auto';
  chatInput.style.height = Math.min(chatInput.scrollHeight, 200) + 'px';
});

// ── Page Loader ─────────────────────────────────────────────
async function loadPage(page) {
  try {
    if (page === 'dashboard') loadDashboard();
    else if (page === 'agents') loadAgents();
    else if (page === 'tools') loadTools();
    else if (page === 'memory') loadMemory();
    else if (page === 'providers') loadProviders();
    else if (page === 'channels') loadChannels();
    else if (page === 'files') loadFiles('.');
    else if (page === 'downloads') loadDownloads();
    else if (page === 'config') loadConfig();
  } catch (e) { console.error(e); }
}

async function loadDashboard() {
  try {
    const resp = await fetch(API + '/api/stats');
    const data = await resp.json();
    document.getElementById('stat-messages').textContent = data.total_messages || 0;
    document.getElementById('stat-memory').textContent = data.memory_entries || 0;
    document.getElementById('stat-tools').textContent = data.tools_available || 0;
    document.getElementById('stat-agents').textContent = data.agents_available || 0;
    document.getElementById('stat-providers').textContent = data.providers_available || 0;
  } catch (e) {}
}

async function loadAgents() {
  try {
    const resp = await fetch(API + '/api/agents');
    const data = await resp.json();
    const grid = document.getElementById('agents-grid');
    grid.innerHTML = data.agents.map(a => `
      <div class="card">
        <div class="card-icon">🤖</div>
        <div class="card-title">${a.name}</div>
        <div class="card-desc">${a.description}</div>
        <div class="card-status online">● Ready</div>
      </div>
    `).join('');
  } catch (e) {}
}

async function loadTools() {
  try {
    const resp = await fetch(API + '/api/tools');
    const data = await resp.json();
    const grid = document.getElementById('tools-grid');
    grid.innerHTML = data.tools.map(t => `
      <div class="card">
        <div class="card-icon">🔧</div>
        <div class="card-title">${t.name}</div>
        <div class="card-desc">${t.description}</div>
        <div class="card-status configured">${t.category}</div>
      </div>
    `).join('');
  } catch (e) {}
}

async function loadMemory() {
  try {
    const resp = await fetch(API + '/api/memory');
    const data = await resp.json();
    document.getElementById('mem-total').textContent = data.count || 0;
    const userCount = data.entries.filter(e => e.role === 'user').length;
    const asstCount = data.entries.filter(e => e.role === 'assistant').length;
    document.getElementById('mem-user').textContent = userCount;
    document.getElementById('mem-assistant').textContent = asstCount;

    const list = document.getElementById('memory-entries');
    list.innerHTML = data.entries.slice(-20).reverse().map(e => `
      <div class="file-item">
        <span class="file-icon">${e.role === 'user' ? '👤' : '⚡'}</span>
        <span class="file-name">${escapeHtml(e.content).substring(0, 120)}...</span>
        <span class="file-date">${e.timestamp?.substring(11, 19) || ''}</span>
      </div>
    `).join('') || '<div class="empty-state"><div class="empty-icon">🧠</div><div class="empty-title">No memories yet</div><div class="empty-desc">Start chatting to build memory</div></div>';
  } catch (e) {}
}

async function loadProviders() {
  try {
    const resp = await fetch(API + '/api/providers');
    const data = await resp.json();
    const grid = document.getElementById('providers-grid');
    grid.innerHTML = data.providers.map(p => `
      <div class="card">
        <div class="card-icon">${p.available ? '🟢' : '⚪'}</div>
        <div class="card-title">${p.name}</div>
        <div class="card-desc">${p.description}</div>
        <div class="card-status ${p.available ? 'online' : 'offline'}">${p.available ? '● Available' : '○ Not configured'}</div>
      </div>
    `).join('');
  } catch (e) {}
}

async function loadChannels() {
  try {
    const resp = await fetch(API + '/api/channels');
    const data = await resp.json();
    const grid = document.getElementById('channels-grid');
    grid.innerHTML = data.channels.map(c => `
      <div class="card">
        <div class="card-icon">${c.emoji}</div>
        <div class="card-title">${c.name}</div>
        <div class="card-desc">${c.description}</div>
        <div class="card-status ${c.configured ? 'configured' : 'offline'}">${c.configured ? '● Configured' : '○ Not configured'}</div>
      </div>
    `).join('');
  } catch (e) {}
}

async function loadFiles(path) {
  try {
    currentPath = path || '.';
    const resp = await fetch(API + '/api/files?path=' + encodeURIComponent(currentPath));
    const data = await resp.json();
    const list = document.getElementById('files-list');
    list.innerHTML = data.files.map(f => `
      <div class="file-item" ${f.is_dir ? `onclick="loadFiles('${f.path}')"` : ''}>
        <span class="file-icon">${f.is_dir ? '📁' : '📄'}</span>
        <span class="file-name">${f.name}</span>
        <span class="file-size">${f.is_dir ? '' : formatSize(f.size)}</span>
        ${!f.is_dir ? `<a class="file-download" href="${API}/api/files/download?path=${encodeURIComponent(f.path)}" download>⬇️ Download</a>` : ''}
      </div>
    `).join('') || '<div class="empty-state"><div class="empty-icon">📁</div><div class="empty-title">Empty directory</div></div>';
  } catch (e) {}
}

async function loadDownloads() {
  // Load files from the workspace/downloads directory
  try {
    const resp = await fetch(API + '/api/files?path=' + encodeURIComponent(process.cwd() || '.'));
    const data = await resp.json();
    const list = document.getElementById('downloads-list');
    const downloadable = data.files.filter(f => !f.is_dir);
    list.innerHTML = downloadable.map(f => `
      <div class="file-item">
        <span class="file-icon">📄</span>
        <span class="file-name">${f.name}</span>
        <span class="file-size">${formatSize(f.size)}</span>
        <span class="file-date">${f.modified?.substring(0, 10) || ''}</span>
        <a class="file-download" href="${API}/api/files/download?path=${encodeURIComponent(f.path)}" download>⬇️ Download</a>
      </div>
    `).join('') || '<div class="empty-state"><div class="empty-icon">⬇️</div><div class="empty-title">No files yet</div><div class="empty-desc">Files created by Rally will appear here</div></div>';
  } catch (e) {}
}

async function loadConfig() {
  try {
    const resp = await fetch(API + '/api/config');
    const data = await resp.json();
    const display = document.getElementById('config-display');
    display.innerHTML = `<pre style="background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius-lg);padding:20px;font-family:'JetBrains Mono',monospace;font-size:13px;color:var(--cyan);overflow:auto;max-height:600px;">${JSON.stringify(data.config, null, 2)}</pre>`;
  } catch (e) {}
}

// ── File Up Button ──────────────────────────────────────────
document.getElementById('files-up')?.addEventListener('click', () => {
  const parts = currentPath.split('/');
  parts.pop();
  loadFiles(parts.join('/') || '.');
});

// ── Utilities ───────────────────────────────────────────────
function formatSize(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024*1024) return (bytes/1024).toFixed(1) + ' KB';
  if (bytes < 1024*1024*1024) return (bytes/1024/1024).toFixed(1) + ' MB';
  return (bytes/1024/1024/1024).toFixed(1) + ' GB';
}

// ── Init ────────────────────────────────────────────────────
loadDashboard();
</script>
</body>
</html>"""
