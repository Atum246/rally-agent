"""
🟣 Rally Agent — Web Server (Complete Rewrite)
FastAPI + WebSocket + Full REST API + Beautiful Purple Hacker Theme
Single-file web app with inline HTML/CSS/JS
"""

import os
import json
import asyncio
import time
import hashlib
import secrets
import uuid
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Any
from collections import defaultdict

try:
    from fastapi import (
        FastAPI, WebSocket, WebSocketDisconnect, Request, Depends,
        HTTPException, status, Query, Body, Header, UploadFile, File,
    )
    from fastapi.responses import (
        HTMLResponse, JSONResponse, FileResponse, StreamingResponse,
    )
    from fastapi.staticfiles import StaticFiles
    from fastapi.middleware.cors import CORSMiddleware
    import uvicorn
except ImportError:
    raise RuntimeError("Web UI requires: pip install fastapi uvicorn python-multipart pyjwt")


# ═══════════════════════════════════════════════════════════════
# 🔐 JWT Auth Helpers
# ═══════════════════════════════════════════════════════════════

JWT_SECRET = os.environ.get("RALLY_JWT_SECRET", secrets.token_hex(32))
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 24

def _jwt_encode(payload: dict) -> str:
    """Minimal JWT encode (no external dependency)"""
    import base64
    header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode()).rstrip(b"=").decode()
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    sig_input = f"{header}.{body}"
    sig = hashlib.sha256(f"{sig_input}.{JWT_SECRET}".encode()).hexdigest()[:43]
    return f"{header}.{body}.{sig}"

def _jwt_decode(token: str) -> Optional[dict]:
    """Minimal JWT decode"""
    import base64
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        sig_input = f"{parts[0]}.{parts[1]}"
        expected = hashlib.sha256(f"{sig_input}.{JWT_SECRET}".encode()).hexdigest()[:43]
        if parts[2] != expected:
            return None
        padding = 4 - len(parts[1]) % 4
        payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * padding))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════
# 🎨 Purple Hacker Theme — Full Inline HTML/CSS/JS
# ═══════════════════════════════════════════════════════════════

MAIN_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Rally Agent</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#ffffff;--bg-surface:#f9fafb;--bg-hover:#f3f4f6;--bg-elevated:#ffffff;
  --text:#111827;--text-secondary:#6b7280;--text-muted:#9ca3af;
  --border:#e5e7eb;--border-focus:#f97316;
  --primary:#f97316;--primary-hover:#ea580c;--primary-light:rgba(249,115,22,0.1);
  --secondary:#6366f1;--secondary-light:rgba(99,102,241,0.1);
  --success:#10b981;--success-light:rgba(16,185,129,0.1);
  --danger:#ef4444;--danger-light:rgba(239,68,68,0.1);
  --warning:#f59e0b;--warning-light:rgba(245,158,11,0.1);
  --shadow-sm:0 1px 2px rgba(0,0,0,0.05);
  --shadow:0 1px 3px rgba(0,0,0,0.1),0 1px 2px rgba(0,0,0,0.06);
  --shadow-md:0 4px 6px rgba(0,0,0,0.07),0 2px 4px rgba(0,0,0,0.06);
  --shadow-lg:0 10px 15px rgba(0,0,0,0.1),0 4px 6px rgba(0,0,0,0.05);
  --radius:8px;--radius-lg:12px;--radius-xl:16px;
  --font:-apple-system,BlinkMacSystemFont,'Segoe UI','Inter','Roboto',sans-serif;
  --sidebar-w:260px;--topbar-h:56px;
  --transition:all 0.15s ease;
}
[data-theme="dark"]{
  --bg:#0f0f0f;--bg-surface:#1a1a1a;--bg-hover:#252525;--bg-elevated:#1e1e1e;
  --text:#f9fafb;--text-secondary:#9ca3af;--text-muted:#6b7280;
  --border:#2a2a2a;--shadow-sm:0 1px 2px rgba(0,0,0,0.2);
  --shadow:0 1px 3px rgba(0,0,0,0.3),0 1px 2px rgba(0,0,0,0.2);
  --shadow-md:0 4px 6px rgba(0,0,0,0.3),0 2px 4px rgba(0,0,0,0.2);
  --shadow-lg:0 10px 15px rgba(0,0,0,0.4),0 4px 6px rgba(0,0,0,0.3);
}
html{font-size:14px}
body{font-family:var(--font);background:var(--bg);color:var(--text);min-height:100vh;overflow:hidden;line-height:1.5}
a{color:var(--primary);text-decoration:none}a:hover{text-decoration:underline}
button{font-family:var(--font);cursor:pointer;border:none;outline:none}
input,textarea,select{font-family:var(--font);outline:none}
::-webkit-scrollbar{width:6px;height:6px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}
::-webkit-scrollbar-thumb:hover{background:var(--text-muted)}

/* ═══════ AUTH PAGES ═══════ */
.auth-page{display:flex;align-items:center;justify-content:center;min-height:100vh;background:var(--bg-surface)}
.auth-card{background:var(--bg-elevated);border:1px solid var(--border);border-radius:var(--radius-xl);padding:40px;width:100%;max-width:400px;box-shadow:var(--shadow-lg)}
.auth-logo{font-size:2rem;font-weight:700;text-align:center;margin-bottom:8px;color:var(--text)}
.auth-logo span{color:var(--primary)}
.auth-subtitle{text-align:center;color:var(--text-secondary);margin-bottom:32px;font-size:0.95rem}
.form-group{margin-bottom:20px}
.form-label{display:block;font-size:0.85rem;font-weight:500;color:var(--text-secondary);margin-bottom:6px}
.form-input{width:100%;padding:10px 14px;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius);color:var(--text);font-size:0.95rem;transition:var(--transition)}
.form-input:focus{border-color:var(--primary);box-shadow:0 0 0 3px var(--primary-light)}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;padding:10px 20px;border-radius:var(--radius);font-size:0.9rem;font-weight:500;transition:var(--transition)}
.btn-primary{background:var(--primary);color:#fff;width:100%}
.btn-primary:hover{background:var(--primary-hover);transform:translateY(-1px);box-shadow:var(--shadow-md)}
.btn-secondary{background:var(--bg-surface);color:var(--text);border:1px solid var(--border)}
.btn-secondary:hover{background:var(--bg-hover)}
.btn-danger{background:var(--danger);color:#fff}
.btn-danger:hover{background:#dc2626}
.btn-sm{padding:6px 12px;font-size:0.8rem}
.btn-icon{width:36px;height:36px;padding:0;border-radius:var(--radius);background:var(--bg-surface);border:1px solid var(--border);color:var(--text-secondary);display:flex;align-items:center;justify-content:center}
.btn-icon:hover{background:var(--bg-hover);color:var(--text)}
.auth-toggle{text-align:center;margin-top:20px;font-size:0.85rem;color:var(--text-secondary)}
.auth-toggle a{font-weight:500}

/* ═══════ SETUP WIZARD ═══════ */
.setup-page{display:none;align-items:center;justify-content:center;min-height:100vh;background:var(--bg-surface)}
.setup-card{background:var(--bg-elevated);border:1px solid var(--border);border-radius:var(--radius-xl);padding:40px;width:100%;max-width:560px;box-shadow:var(--shadow-lg)}
.setup-steps{display:flex;gap:8px;margin-bottom:32px}
.setup-step{flex:1;height:4px;border-radius:2px;background:var(--border);transition:var(--transition)}
.setup-step.active{background:var(--primary)}
.setup-step.done{background:var(--success)}

/* ═══════ MAIN APP LAYOUT ═══════ */
#app{display:none;height:100vh}

/* ═══════ SIDEBAR ═══════ */
#sidebar{width:var(--sidebar-w);min-width:var(--sidebar-w);background:var(--bg-surface);border-right:1px solid var(--border);display:flex;flex-direction:column;z-index:100;transition:var(--transition)}
.sidebar-header{padding:16px 20px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:10px}
.sidebar-logo{font-size:1.1rem;font-weight:700;color:var(--text);display:flex;align-items:center;gap:8px}
.sidebar-logo .logo-icon{font-size:1.3rem}
.sidebar-nav{flex:1;overflow-y:auto;padding:8px 12px}
.nav-section{font-size:0.7rem;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;color:var(--text-muted);padding:16px 8px 6px}
.nav-item{display:flex;align-items:center;gap:10px;padding:9px 12px;border-radius:var(--radius);color:var(--text-secondary);font-size:0.9rem;transition:var(--transition);cursor:pointer;margin-bottom:2px}
.nav-item:hover{background:var(--bg-hover);color:var(--text)}
.nav-item.active{background:var(--primary-light);color:var(--primary);font-weight:500}
.nav-item .icon{font-size:1rem;width:22px;text-align:center}
.sidebar-footer{padding:12px 16px;border-top:1px solid var(--border);display:flex;align-items:center;justify-content:space-between}
.sidebar-footer-text{font-size:0.75rem;color:var(--text-muted)}
.theme-toggle{width:32px;height:32px;border-radius:var(--radius);background:var(--bg);border:1px solid var(--border);color:var(--text-secondary);display:flex;align-items:center;justify-content:center;cursor:pointer;font-size:0.9rem;transition:var(--transition)}
.theme-toggle:hover{background:var(--bg-hover)}

/* ═══════ MAIN AREA ═══════ */
#main{flex:1;display:flex;flex-direction:column;overflow:hidden;min-width:0}
.topbar{height:var(--topbar-h);background:var(--bg-elevated);border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;padding:0 24px;flex-shrink:0}
.topbar-title{font-weight:600;color:var(--text);font-size:1rem;display:flex;align-items:center;gap:8px}
.topbar-status{display:flex;align-items:center;gap:16px;font-size:0.8rem;color:var(--text-secondary)}
.status-dot{width:8px;height:8px;border-radius:50%;background:var(--success);display:inline-block;margin-right:4px}
.status-dot.disconnected{background:var(--danger)}

/* ═══════ PAGES ═══════ */
.page{display:none;flex:1;overflow-y:auto;padding:24px}
.page.active{display:block}

/* ═══════ CARDS ═══════ */
.card{background:var(--bg-elevated);border:1px solid var(--border);border-radius:var(--radius-lg);padding:20px;margin-bottom:16px;box-shadow:var(--shadow-sm);transition:var(--transition)}
.card:hover{box-shadow:var(--shadow)}
.card-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px}
.card-title{font-weight:600;color:var(--text);font-size:1rem;display:flex;align-items:center;gap:8px}

/* ═══════ GRID ═══════ */
.grid-2{display:grid;grid-template-columns:repeat(2,1fr);gap:16px}
.grid-3{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}
.grid-4{display:grid;grid-template-columns:repeat(4,1fr);gap:16px}
@media(max-width:1200px){.grid-4{grid-template-columns:repeat(2,1fr)}}
@media(max-width:900px){.grid-3,.grid-2{grid-template-columns:1fr}}

/* ═══════ STAT CARDS ═══════ */
.stat-card{background:var(--bg-elevated);border:1px solid var(--border);border-radius:var(--radius-lg);padding:20px;box-shadow:var(--shadow-sm);transition:var(--transition)}
.stat-card:hover{box-shadow:var(--shadow);transform:translateY(-1px)}
.stat-icon{width:40px;height:40px;border-radius:var(--radius);display:flex;align-items:center;justify-content:center;font-size:1.2rem;margin-bottom:12px}
.stat-icon.orange{background:var(--primary-light)}
.stat-icon.purple{background:var(--secondary-light)}
.stat-icon.green{background:var(--success-light)}
.stat-icon.blue{background:rgba(59,130,246,0.1)}
.stat-value{font-size:1.8rem;font-weight:700;color:var(--text);line-height:1}
.stat-label{font-size:0.8rem;color:var(--text-secondary);margin-top:4px}

/* ═══════ TABLES ═══════ */
.table-wrap{overflow-x:auto;border:1px solid var(--border);border-radius:var(--radius-lg)}
table{width:100%;border-collapse:collapse}
th{text-align:left;padding:12px 16px;font-size:0.78rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.05em;background:var(--bg-surface);border-bottom:1px solid var(--border);font-weight:600}
td{padding:12px 16px;font-size:0.85rem;border-bottom:1px solid var(--border);color:var(--text)}
tr:last-child td{border-bottom:none}
tr:hover td{background:var(--bg-hover)}

/* ═══════ BADGES ═══════ */
.badge{display:inline-flex;align-items:center;padding:3px 10px;border-radius:20px;font-size:0.72rem;font-weight:600}
.badge-green{background:var(--success-light);color:var(--success)}
.badge-purple{background:var(--secondary-light);color:var(--secondary)}
.badge-red{background:var(--danger-light);color:var(--danger)}
.badge-yellow{background:var(--warning-light);color:var(--warning)}
.badge-blue{background:rgba(59,130,246,0.1);color:#3b82f6}
.badge-orange{background:var(--primary-light);color:var(--primary)}

/* ═══════ INPUTS ═══════ */
.input{width:100%;padding:10px 14px;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius);color:var(--text);font-size:0.9rem;transition:var(--transition)}
.input:focus{border-color:var(--primary);box-shadow:0 0 0 3px var(--primary-light)}
.input-group{margin-bottom:16px}
.input-label{display:block;font-size:0.8rem;color:var(--text-secondary);margin-bottom:6px;font-weight:500}
textarea.input{min-height:100px;resize:vertical}
select.input{appearance:none;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%236b7280' d='M6 8L1 3h10z'/%3E%3C/svg%3E");background-repeat:no-repeat;background-position:right 12px center}

/* ═══════ CHAT PAGE ═══════ */
.chat-container{display:flex;flex-direction:column;height:calc(100vh - var(--topbar-h));padding:0!important}
.chat-messages{flex:1;overflow-y:auto;padding:24px;display:flex;flex-direction:column;gap:20px}
.msg{max-width:720px;width:100%;margin:0 auto;display:flex;gap:12px;animation:fadeIn .2s ease}
@keyframes fadeIn{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:translateY(0)}}
.msg-avatar{width:32px;height:32px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:0.85rem;flex-shrink:0;font-weight:600}
.msg-avatar.user{background:var(--primary-light);color:var(--primary)}
.msg-avatar.ai{background:var(--secondary-light);color:var(--secondary)}
.msg-body{flex:1;min-width:0}
.msg-name{font-size:0.78rem;font-weight:600;color:var(--text);margin-bottom:4px}
.msg-content{font-size:0.9rem;line-height:1.65;color:var(--text);word-wrap:break-word;white-space:pre-wrap}
.msg-content code{background:var(--bg-surface);border:1px solid var(--border);padding:1px 5px;border-radius:4px;font-size:0.85em}
.msg-content pre{background:var(--bg-surface);border:1px solid var(--border);border-radius:var(--radius);padding:14px;margin:10px 0;overflow-x:auto;font-size:0.82rem;line-height:1.5}
.msg-content pre code{background:none;border:none;padding:0}
.msg-system{text-align:center;color:var(--text-muted);font-size:0.8rem;padding:8px 0}
.msg-system span{background:var(--bg-surface);border:1px solid var(--border);border-radius:20px;padding:4px 14px}
.msg-tool{border-left:3px solid var(--warning);padding-left:12px}
.msg-tool .tool-name{color:var(--warning);font-weight:600;font-size:0.8rem;margin-bottom:4px}
.typing-indicator{display:flex;align-items:center;gap:8px;padding:0 24px 8px;max-width:720px;margin:0 auto;width:100%}
.typing-dots{display:flex;gap:4px}
.typing-dot{width:6px;height:6px;border-radius:50%;background:var(--text-muted);animation:typingBounce 1.4s infinite both}
.typing-dot:nth-child(2){animation-delay:.2s}
.typing-dot:nth-child(3){animation-delay:.4s}
@keyframes typingBounce{0%,80%,100%{transform:scale(0.6);opacity:0.4}40%{transform:scale(1);opacity:1}}
.typing-text{font-size:0.8rem;color:var(--text-muted)}
.chat-input-area{padding:16px 24px;border-top:1px solid var(--border);background:var(--bg-elevated)}
.chat-input-wrap{max-width:720px;margin:0 auto;display:flex;gap:10px;align-items:flex-end}
.chat-input{flex:1;padding:12px 16px;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-lg);color:var(--text);font-size:0.95rem;resize:none;min-height:48px;max-height:160px;line-height:1.5;transition:var(--transition)}
.chat-input:focus{border-color:var(--primary);box-shadow:0 0 0 3px var(--primary-light)}
.chat-input::placeholder{color:var(--text-muted)}
.send-btn{width:48px;height:48px;border-radius:var(--radius-lg);background:var(--primary);color:#fff;font-size:1.1rem;display:flex;align-items:center;justify-content:center;transition:var(--transition);flex-shrink:0}
.send-btn:hover{background:var(--primary-hover);transform:translateY(-1px);box-shadow:var(--shadow-md)}
.send-btn:disabled{opacity:0.4;cursor:not-allowed;transform:none}

/* ═══════ EMPTY STATES ═══════ */
.empty-state{text-align:center;padding:60px 20px;color:var(--text-secondary)}
.empty-state .icon{font-size:3rem;margin-bottom:16px;opacity:0.5}
.empty-state h3{font-size:1.1rem;color:var(--text);margin-bottom:8px}
.empty-state p{font-size:0.9rem;max-width:400px;margin:0 auto}

/* ═══════ WELCOME SCREEN ═══════ */
.welcome{text-align:center;padding:80px 20px;max-width:600px;margin:0 auto}
.welcome-icon{font-size:4rem;margin-bottom:20px}
.welcome h2{font-size:1.6rem;font-weight:700;color:var(--text);margin-bottom:8px}
.welcome p{color:var(--text-secondary);font-size:1rem;margin-bottom:32px;line-height:1.6}
.welcome-suggestions{display:flex;flex-direction:column;gap:10px;max-width:480px;margin:0 auto}
.suggestion-btn{display:flex;align-items:center;gap:12px;padding:14px 18px;background:var(--bg-surface);border:1px solid var(--border);border-radius:var(--radius-lg);color:var(--text);font-size:0.9rem;text-align:left;transition:var(--transition);cursor:pointer}
.suggestion-btn:hover{border-color:var(--primary);background:var(--primary-light);transform:translateY(-1px)}
.suggestion-btn .sug-icon{font-size:1.2rem;width:36px;height:36px;border-radius:var(--radius);background:var(--bg);display:flex;align-items:center;justify-content:center;flex-shrink:0}

/* ═══════ SCROLLBAR FOR CHAT ═══════ */
.chat-messages::-webkit-scrollbar{width:8px}
.chat-messages::-webkit-scrollbar-track{background:transparent}
.chat-messages::-webkit-scrollbar-thumb{background:var(--border);border-radius:4px}
.chat-messages::-webkit-scrollbar-thumb:hover{background:var(--text-muted)}

/* ═══════ MISC ═══════ */
.divider{height:1px;background:var(--border);margin:16px 0}
.tag{display:inline-block;padding:2px 8px;border-radius:4px;font-size:0.75rem;font-weight:500;background:var(--bg-surface);color:var(--text-secondary);border:1px solid var(--border)}
.progress-bar{height:6px;background:var(--border);border-radius:3px;overflow:hidden}
.progress-fill{height:100%;background:var(--primary);border-radius:3px;transition:width .3s ease}
.toast{position:fixed;bottom:24px;right:24px;background:var(--bg-elevated);border:1px solid var(--border);border-radius:var(--radius-lg);padding:14px 20px;box-shadow:var(--shadow-lg);z-index:10000;display:none;animation:slideUp .3s ease;font-size:0.9rem}
.toast.show{display:flex;align-items:center;gap:10px}
@keyframes slideUp{from{opacity:0;transform:translateY(20px)}to{opacity:1;transform:translateY(0)}}
</style>
</head>
<body>

<!-- ═══════ LOGIN PAGE ═══════ -->
<div id="loginPage" class="auth-page" style="display:none">
  <div class="auth-card">
    <div class="auth-logo">⚡ <span>Rally</span> Agent</div>
    <div class="auth-subtitle">Your AI. Your Rules. Your Data.</div>
    <div id="loginForm">
      <div class="form-group">
        <label class="form-label">Username</label>
        <input id="loginUser" class="form-input" placeholder="Enter username" autocomplete="username">
      </div>
      <div class="form-group">
        <label class="form-label">Password</label>
        <input id="loginPass" type="password" class="form-input" placeholder="Enter password" autocomplete="current-password">
      </div>
      <button class="btn btn-primary" onclick="doLogin()">Sign In</button>
      <div class="auth-toggle">Don't have an account? <a href="#" onclick="toggleAuth()">Sign Up</a></div>
    </div>
    <div id="registerForm" style="display:none">
      <div class="form-group">
        <label class="form-label">Username</label>
        <input id="regUser" class="form-input" placeholder="Choose a username">
      </div>
      <div class="form-group">
        <label class="form-label">Password</label>
        <input id="regPass" type="password" class="form-input" placeholder="Choose a password">
      </div>
      <button class="btn btn-primary" onclick="doRegister()">Create Account</button>
      <div class="auth-toggle">Already have an account? <a href="#" onclick="toggleAuth()">Sign In</a></div>
    </div>
    <div id="authError" style="display:none;color:var(--danger);font-size:0.85rem;margin-top:12px;text-align:center"></div>
  </div>
</div>

<!-- ═══════ SETUP WIZARD ═══════ -->
<div id="setupPage" class="setup-page">
  <div class="setup-card">
    <div class="setup-steps" id="setupSteps"></div>
    <div id="setupContent"></div>
  </div>
</div>

<!-- ═══════ MAIN APP ═══════ -->
<div id="app" style="display:none">
  <!-- SIDEBAR -->
  <div id="sidebar">
    <div class="sidebar-header">
      <div class="sidebar-logo"><span class="logo-icon">⚡</span> Rally Agent</div>
    </div>
    <nav class="sidebar-nav">
      <div class="nav-section">Main</div>
      <div class="nav-item active" data-page="chat" onclick="showPage('chat')"><span class="icon">💬</span> Chat</div>
      <div class="nav-item" data-page="dashboard" onclick="showPage('dashboard')"><span class="icon">📊</span> Dashboard</div>
      <div class="nav-item" data-page="agents" onclick="showPage('agents')"><span class="icon">🤖</span> Agents</div>
      <div class="nav-section">Tools</div>
      <div class="nav-item" data-page="tools" onclick="showPage('tools')"><span class="icon">🛠️</span> Tools</div>
      <div class="nav-item" data-page="browser" onclick="showPage('browser')"><span class="icon">🌐</span> Browser</div>
      <div class="nav-item" data-page="computer" onclick="showPage('computer')"><span class="icon">🖥️</span> Computer</div>
      <div class="nav-item" data-page="files" onclick="showPage('files')"><span class="icon">📁</span> Files</div>
      <div class="nav-section">Intelligence</div>
      <div class="nav-item" data-page="memory" onclick="showPage('memory')"><span class="icon">🧠</span> Memory</div>
      <div class="nav-item" data-page="knowledge" onclick="showPage('knowledge')"><span class="icon">🕸️</span> Knowledge</div>
      <div class="nav-item" data-page="improvement" onclick="showPage('improvement')"><span class="icon">📈</span> Learning</div>
      <div class="nav-section">Automation</div>
      <div class="nav-item" data-page="automation" onclick="showPage('automation')"><span class="icon">⏰</span> Automation</div>
      <div class="nav-item" data-page="workflows" onclick="showPage('workflows')"><span class="icon">🔄</span> Workflows</div>
      <div class="nav-item" data-page="plugins" onclick="showPage('plugins')"><span class="icon">🔌</span> Plugins</div>
      <div class="nav-section">System</div>
      <div class="nav-item" data-page="system" onclick="showPage('system')"><span class="icon">🔧</span> System</div>
      <div class="nav-item" data-page="metrics" onclick="showPage('metrics')"><span class="icon">📈</span> Metrics</div>
      <div class="nav-item" data-page="security" onclick="showPage('security')"><span class="icon">🔒</span> Security</div>
      <div class="nav-item" data-page="users" onclick="showPage('users')"><span class="icon">👥</span> Users</div>
      <div class="nav-item" data-page="profile" onclick="showPage('profile')"><span class="icon">👤</span> Profile</div>
      <div class="nav-item" data-page="settings" onclick="showPage('settings')"><span class="icon">⚙️</span> Settings</div>
    </nav>
    <div class="sidebar-footer">
      <span class="sidebar-footer-text">v2.0 · Self-Hosted</span>
      <button class="theme-toggle" onclick="toggleTheme()" title="Toggle dark mode">🌙</button>
    </div>
  </div>

  <!-- MAIN -->
  <div id="main">
    <div class="topbar">
      <div class="topbar-title" id="pageTitle">💬 Chat</div>
      <div class="topbar-status">
        <span><span class="status-dot" id="wsDot"></span><span id="wsStatus">Connected</span></span>
        <span id="topbarUser" style="color:var(--text)">admin</span>
      </div>
    </div>

    <!-- ═══════ CHAT PAGE ═══════ -->
    <div id="page-chat" class="page active chat-container">
      <div class="chat-messages" id="chatMessages">
        <div class="welcome" id="chatWelcome">
          <div class="welcome-icon">⚡</div>
          <h2>What can I help with?</h2>
          <p>I can help with coding, research, analysis, automation, and more. Ask me anything.</p>
          <div class="welcome-suggestions">
            <button class="suggestion-btn" onclick="useSuggestion('Write a Python script to analyze CSV data')"><span class="sug-icon">💻</span> Write a Python script to analyze CSV data</button>
            <button class="suggestion-btn" onclick="useSuggestion('Research the latest trends in AI agents')"><span class="sug-icon">🔍</span> Research the latest trends in AI agents</button>
            <button class="suggestion-btn" onclick="useSuggestion('Help me plan a product launch')"><span class="sug-icon">📋</span> Help me plan a product launch</button>
            <button class="suggestion-btn" onclick="useSuggestion('Explain how neural networks work')"><span class="sug-icon">🧠</span> Explain how neural networks work</button>
          </div>
        </div>
      </div>
      <div id="typingIndicator" class="typing-indicator" style="display:none">
        <div class="typing-dots"><span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span></div>
        <span class="typing-text">Thinking...</span>
      </div>
      <div class="chat-input-area">
        <div class="chat-input-wrap">
          <textarea id="chatInput" class="chat-input" placeholder="Ask Rally anything..." rows="1"></textarea>
          <button id="sendBtn" class="send-btn" onclick="sendMessage()">→</button>
        </div>
      </div>
    </div>

    <!-- ═══════ DASHBOARD PAGE ═══════ -->
    <div id="page-dashboard" class="page">
      <div class="grid-4" id="dashStats"></div>
      <div class="grid-2" style="margin-top:16px">
        <div class="card"><div class="card-header"><div class="card-title">🤖 Agents</div></div><div id="dashAgents"></div></div>
        <div class="card"><div class="card-header"><div class="card-title">🛠️ Tools</div></div><div id="dashTools"></div></div>
      </div>
    </div>

    <!-- ═══════ AGENTS PAGE ═══════ -->
    <div id="page-agents" class="page">
      <div class="card"><div class="card-header"><div class="card-title">🤖 Available Agents</div></div>
        <div class="table-wrap"><table><thead><tr><th>Name</th><th>Type</th><th>Description</th><th>Capabilities</th></tr></thead><tbody id="agentsTable"></tbody></table></div>
      </div>
    </div>

    <!-- ═══════ MEMORY PAGE ═══════ -->
    <div id="page-memory" class="page">
      <div class="grid-3" id="memoryStats"></div>
      <div class="card" style="margin-top:16px">
        <div class="card-header"><div class="card-title">🔍 Search Memory</div></div>
        <div style="display:flex;gap:10px"><input id="memorySearchInput" class="input" placeholder="Search memories..."><button class="btn btn-primary" onclick="searchMemory()" style="width:auto">Search</button></div>
        <div id="memoryResults" style="margin-top:16px"></div>
      </div>
    </div>

    <!-- ═══════ BROWSER PAGE ═══════ -->
    <div id="page-browser" class="page">
      <div class="card">
        <div class="card-header"><div class="card-title">🌐 Browser Automation</div></div>
        <div style="display:flex;gap:10px;margin-bottom:16px"><input id="browserUrl" class="input" placeholder="https://example.com"><button class="btn btn-primary" onclick="browserGo()" style="width:auto">Go</button></div>
        <div id="browserContent" style="min-height:200px;background:var(--bg-surface);border:1px solid var(--border);border-radius:var(--radius);padding:16px;color:var(--text-secondary)">Browser not launched yet.</div>
      </div>
    </div>

    <!-- ═══════ PLUGINS PAGE ═══════ -->
    <div id="page-plugins" class="page">
      <div class="card"><div class="card-header"><div class="card-title">🔌 Plugins</div></div>
        <div id="pluginsList" class="empty-state"><div class="icon">🔌</div><h3>No plugins installed</h3><p>Install plugins to extend Rally's capabilities.</p></div>
      </div>
    </div>

    <!-- ═══════ TOOLS PAGE ═══════ -->
    <div id="page-tools" class="page">
      <div class="card"><div class="card-header"><div class="card-title">🛠️ Registered Tools</div></div>
        <div class="table-wrap"><table><thead><tr><th>Name</th><th>Category</th><th>Description</th><th>Permission</th></tr></thead><tbody id="toolsTable"></tbody></table></div>
      </div>
    </div>

    <!-- ═══════ FILES PAGE ═══════ -->
    <div id="page-files" class="page">
      <div class="card"><div class="card-header"><div class="card-title">📁 File Browser</div></div>
        <div id="filesContent" class="empty-state"><div class="icon">📁</div><h3>Browse Files</h3><p>Navigate your workspace files.</p></div>
      </div>
    </div>

    <!-- ═══════ METRICS PAGE ═══════ -->
    <div id="page-metrics" class="page">
      <div class="grid-4" id="metricsStats"></div>
      <div class="card" style="margin-top:16px"><div class="card-header"><div class="card-title">📈 Request Log</div></div>
        <div class="table-wrap"><table><thead><tr><th>Endpoint</th><th>Latency</th><th>Status</th><th>Time</th></tr></thead><tbody id="metricsTable"></tbody></table></div>
      </div>
    </div>

    <!-- ═══════ SECURITY PAGE ═══════ -->
    <div id="page-security" class="page">
      <div class="card"><div class="card-header"><div class="card-title">🔒 Security Status</div></div>
        <div class="table-wrap"><table><thead><tr><th>Check</th><th>Status</th></tr></thead><tbody id="securityTable"></tbody></table></div>
      </div>
      <div class="card"><div class="card-header"><div class="card-title">📋 Audit Log</div></div>
        <div id="auditLog" style="max-height:300px;overflow-y:auto;font-size:0.82rem;font-family:monospace"></div>
      </div>
    </div>

    <!-- ═══════ USERS PAGE ═══════ -->
    <div id="page-users" class="page">
      <div class="card"><div class="card-header"><div class="card-title">👥 Users</div></div>
        <div class="table-wrap"><table><thead><tr><th>Username</th><th>Role</th><th>Created</th></tr></thead><tbody id="usersTable"></tbody></table></div>
      </div>
    </div>

    <!-- ═══════ SETTINGS PAGE ═══════ -->
    <div id="page-settings" class="page">
      <div class="card"><div class="card-header"><div class="card-title">⚙️ Configuration</div></div>
        <div id="configContent"></div>
      </div>
    </div>

    <!-- ═══════ AUTOMATION PAGE ═══════ -->
    <div id="page-automation" class="page">
      <div class="card"><div class="card-header"><div class="card-title">⏰ Scheduled Jobs</div></div>
        <div class="table-wrap"><table><thead><tr><th>Name</th><th>Schedule</th><th>Type</th><th>Status</th></tr></thead><tbody id="automationTable"></tbody></table></div>
      </div>
    </div>

    <!-- ═══════ KNOWLEDGE PAGE ═══════ -->
    <div id="page-knowledge" class="page">
      <div class="grid-3" id="knowledgeStats"></div>
      <div class="card" style="margin-top:16px">
        <div class="card-header"><div class="card-title">🔍 Search Knowledge</div></div>
        <div style="display:flex;gap:10px"><input id="knowledgeSearchInput" class="input" placeholder="Search knowledge graph..."><button class="btn btn-primary" onclick="searchKnowledge()" style="width:auto">Search</button></div>
        <div id="knowledgeResults" style="margin-top:16px"></div>
      </div>
    </div>

    <!-- ═══════ WORKFLOWS PAGE ═══════ -->
    <div id="page-workflows" class="page">
      <div class="card"><div class="card-header"><div class="card-title">🔄 Recorded Workflows</div></div>
        <div id="workflowsList" class="empty-state"><div class="icon">🔄</div><h3>No workflows recorded</h3><p>Record your actions to create reusable workflows.</p></div>
      </div>
    </div>

    <!-- ═══════ IMPROVEMENT PAGE ═══════ -->
    <div id="page-improvement" class="page">
      <div class="grid-3" id="improvementStats"></div>
      <div class="card" style="margin-top:16px"><div class="card-header"><div class="card-title">📊 Self-Improvement Report</div></div>
        <div id="improvementContent"></div>
      </div>
    </div>

    <!-- ═══════ COMPUTER PAGE ═══════ -->
    <div id="page-computer" class="page">
      <div class="card"><div class="card-header"><div class="card-title">🖥️ Computer Use</div></div>
        <div id="computerContent" class="empty-state"><div class="icon">🖥️</div><h3>Computer Control</h3><p>Take screenshots, click, and type on the desktop.</p></div>
      </div>
    </div>

    <!-- ═══════ SYSTEM PAGE ═══════ -->
    <div id="page-system" class="page">
      <div class="grid-3" id="systemStats"></div>
      <div class="card" style="margin-top:16px"><div class="card-header"><div class="card-title">🔧 System Information</div></div>
        <div id="systemContent"></div>
      </div>
    </div>

    <!-- ═══════ PROFILE PAGE ═══════ -->
    <div id="page-profile" class="page">
      <div class="card"><div class="card-header"><div class="card-title">👤 User Profile</div></div>
        <div id="profileContent"></div>
      </div>
    </div>

  </div>
</div>

<!-- TOAST -->
<div id="toast" class="toast"></div>

<script>
// ═══════ STATE ═══════
let authToken = localStorage.getItem('rally_token') || '';
let currentUser = localStorage.getItem('rally_user') || '';
let ws = null;
let wsReconnectTimer = null;
let isWaiting = false;

// ═══════ THEME ═══════
function toggleTheme() {
  const html = document.documentElement;
  const isDark = html.getAttribute('data-theme') === 'dark';
  html.setAttribute('data-theme', isDark ? '' : 'dark');
  localStorage.setItem('rally_theme', isDark ? '' : 'dark');
  document.querySelector('.theme-toggle').textContent = isDark ? '🌙' : '☀️';
}
(function() {
  const t = localStorage.getItem('rally_theme');
  if (t === 'dark') {
    document.documentElement.setAttribute('data-theme', 'dark');
    setTimeout(() => { const btn = document.querySelector('.theme-toggle'); if(btn) btn.textContent = '☀️'; }, 0);
  }
})();

// ═══════ API HELPERS ═══════
function api(path, opts = {}) {
  const headers = { 'Content-Type': 'application/json' };
  if (authToken) headers['Authorization'] = 'Bearer ' + authToken;
  return fetch('/api' + path, { ...opts, headers }).then(async r => {
    if (r.status === 401) { logout(); throw new Error('Unauthorized'); }
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || 'Request failed');
    return data;
  });
}

function showToast(msg, type = 'info') {
  const t = document.getElementById('toast');
  const icons = { info: 'ℹ️', success: '✅', error: '❌', warning: '⚠️' };
  t.innerHTML = `<span>${icons[type] || 'ℹ️'}</span><span>${msg}</span>`;
  t.className = 'toast show';
  t.style.borderColor = type === 'error' ? 'var(--danger)' : type === 'success' ? 'var(--success)' : 'var(--border)';
  setTimeout(() => t.className = 'toast', 3000);
}

// ═══════ AUTH ═══════
function toggleAuth() {
  const login = document.getElementById('loginForm');
  const reg = document.getElementById('registerForm');
  login.style.display = login.style.display === 'none' ? 'block' : 'none';
  reg.style.display = reg.style.display === 'none' ? 'block' : 'none';
  document.getElementById('authError').style.display = 'none';
}

async function doLogin() {
  try {
    const data = await fetch('/api/auth/login', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: document.getElementById('loginUser').value, password: document.getElementById('loginPass').value })
    }).then(r => r.json());
    if (data.token) {
      authToken = data.token; currentUser = data.username;
      localStorage.setItem('rally_token', authToken);
      localStorage.setItem('rally_user', currentUser);
      document.getElementById('loginPage').style.display = 'none';
      startApp();
    } else {
      document.getElementById('authError').textContent = data.detail || 'Login failed';
      document.getElementById('authError').style.display = 'block';
    }
  } catch(e) {
    document.getElementById('authError').textContent = 'Connection error';
    document.getElementById('authError').style.display = 'block';
  }
}

async function doRegister() {
  try {
    const data = await fetch('/api/auth/register', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: document.getElementById('regUser').value, password: document.getElementById('regPass').value })
    }).then(r => r.json());
    if (data.token) {
      authToken = data.token; currentUser = data.username;
      localStorage.setItem('rally_token', authToken);
      localStorage.setItem('rally_user', currentUser);
      document.getElementById('loginPage').style.display = 'none';
      startApp();
    } else {
      document.getElementById('authError').textContent = data.detail || 'Registration failed';
      document.getElementById('authError').style.display = 'block';
    }
  } catch(e) {
    document.getElementById('authError').textContent = 'Connection error';
    document.getElementById('authError').style.display = 'block';
  }
}

function logout() {
  authToken = ''; currentUser = '';
  localStorage.removeItem('rally_token');
  localStorage.removeItem('rally_user');
  if (ws) ws.close();
  document.getElementById('app').style.display = 'none';
  document.getElementById('loginPage').style.display = 'flex';
}

// ═══════ SETUP WIZARD ═══════
let setupData = { steps: [], currentStep: 0 };
async function checkOnboarding() {
  try {
    const status = await fetch('/api/setup/status').then(r => r.json());
    if (status.needs_setup) {
      document.getElementById('loginPage').style.display = 'none';
      document.getElementById('setupPage').style.display = 'flex';
      const guides = await fetch('/api/setup/guides').then(r => r.json());
      setupData.steps = guides.guides || [];
      renderSetupStep();
      return true;
    }
    return false;
  } catch(e) { return false; }
}

function renderSetupStep() {
  const steps = document.getElementById('setupSteps');
  steps.innerHTML = setupData.steps.map((_, i) => `<div class="setup-step ${i < setupData.currentStep ? 'done' : i === setupData.currentStep ? 'active' : ''}"></div>`).join('');
  const guide = setupData.steps[setupData.currentStep];
  if (!guide) { finishSetup(); return; }
  const content = document.getElementById('setupContent');
  content.innerHTML = `
    <h2 style="margin-bottom:8px">${guide.icon || '🔧'} ${guide.name}</h2>
    <p style="color:var(--text-secondary);margin-bottom:24px">${guide.description || ''}</p>
    <div class="form-group"><label class="form-label">API Key</label><input id="setupKey" class="form-input" placeholder="${guide.key_prefix || ''}..." type="password"></div>
    <div style="display:flex;gap:10px;justify-content:flex-end">
      ${setupData.currentStep > 0 ? '<button class="btn btn-secondary" onclick="setupPrev()">Back</button>' : ''}
      <button class="btn btn-secondary" onclick="setupSkip()">Skip</button>
      <button class="btn btn-primary" onclick="setupNext()" style="width:auto">Continue</button>
    </div>`;
}

function setupPrev() { setupData.currentStep--; renderSetupStep(); }
function setupSkip() { setupData.currentStep++; renderSetupStep(); }
async function setupNext() {
  const guide = setupData.steps[setupData.currentStep];
  const key = document.getElementById('setupKey').value;
  if (key) {
    try {
      await fetch('/api/setup/complete', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ provider: guide.id, api_key: key }) });
    } catch(e) {}
  }
  setupData.currentStep++;
  renderSetupStep();
}
async function finishSetup() {
  document.getElementById('setupPage').style.display = 'none';
  document.getElementById('loginPage').style.display = 'flex';
}

// ═══════ NAVIGATION ═══════
const pageTitles = {
  chat:'💬 Chat', dashboard:'📊 Dashboard', agents:'🤖 Agents', memory:'🧠 Memory',
  browser:'🌐 Browser', plugins:'🔌 Plugins', tools:'🛠️ Tools', automation:'⏰ Automation',
  knowledge:'🕸️ Knowledge', workflows:'🔄 Workflows', improvement:'📈 Learning',
  computer:'🖥️ Computer', system:'🔧 System', profile:'👤 Profile', files:'📁 Files',
  metrics:'📈 Metrics', security:'🔒 Security', users:'👥 Users', settings:'⚙️ Settings'
};

function showPage(name) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  const page = document.getElementById('page-' + name);
  if (page) page.classList.add('active');
  const nav = document.querySelector(`.nav-item[data-page="${name}"]`);
  if (nav) nav.classList.add('active');
  document.getElementById('pageTitle').textContent = pageTitles[name] || name;
  loadPageData(name);
}

// ═══════ PAGE DATA LOADING ═══════
async function loadPageData(name) {
  try {
    switch(name) {
      case 'dashboard': await loadDashboard(); break;
      case 'agents': await loadAgents(); break;
      case 'memory': await loadMemory(); break;
      case 'tools': await loadTools(); break;
      case 'metrics': await loadMetrics(); break;
      case 'security': await loadSecurity(); break;
      case 'users': await loadUsers(); break;
      case 'settings': await loadConfig(); break;
      case 'automation': await loadAutomation(); break;
      case 'knowledge': await loadKnowledge(); break;
      case 'workflows': await loadWorkflows(); break;
      case 'improvement': await loadImprovement(); break;
      case 'system': await loadSystem(); break;
      case 'profile': await loadProfile(); break;
    }
  } catch(e) { console.error('Load error:', e); }
}

async function loadDashboard() {
  const s = await api('/status');
  document.getElementById('dashStats').innerHTML = [
    { icon:'🤖', label:'Agents', value: s.agents||0, color:'purple' },
    { icon:'🛠️', label:'Tools', value: s.tools||0, color:'orange' },
    { icon:'🧠', label:'Memory', value: s.memory_entries||0, color:'green' },
    { icon:'⏱️', label:'Uptime', value: s.uptime||'0s', color:'blue' },
  ].map(s => `<div class="stat-card"><div class="stat-icon ${s.color}">${s.icon}</div><div class="stat-value">${s.value}</div><div class="stat-label">${s.label}</div></div>`).join('');
  try {
    const agents = await api('/agents');
    document.getElementById('dashAgents').innerHTML = (agents.agents||[]).map(a => `<div style="padding:8px 0;border-bottom:1px solid var(--border);display:flex;justify-content:space-between"><span><strong>${a.name}</strong> <span class="tag">${a.type}</span></span></div>`).join('');
  } catch(e) {}
  try {
    const tools = await api('/tools');
    document.getElementById('dashTools').innerHTML = (tools.tools||[]).map(t => `<div style="padding:8px 0;border-bottom:1px solid var(--border);display:flex;justify-content:space-between"><span><strong>${t.name}</strong></span><span class="tag">${t.category||''}</span></div>`).join('');
  } catch(e) {}
}

async function loadAgents() {
  const data = await api('/agents');
  document.getElementById('agentsTable').innerHTML = (data.agents||[]).map(a => `<tr><td><strong>${a.name}</strong></td><td><span class="badge badge-purple">${a.type}</span></td><td>${a.description||''}</td><td>${(a.capabilities||[]).map(c=>'<span class="tag">'+c+'</span> ').join('')}</td></tr>`).join('');
}

async function loadMemory() {
  const data = await api('/memory');
  document.getElementById('memoryStats').innerHTML = [
    { label:'Total Entries', value: data.total_entries||0 },
    { label:'Embeddings', value: data.total_embeddings||0 },
    { label:'Avg Search Time', value: (data.avg_search_ms||0).toFixed(1)+'ms' },
  ].map(s => `<div class="stat-card"><div class="stat-value">${s.value}</div><div class="stat-label">${s.label}</div></div>`).join('');
}

async function searchMemory() {
  const q = document.getElementById('memorySearchInput').value;
  if (!q) return;
  const data = await api('/memory/search?q=' + encodeURIComponent(q));
  document.getElementById('memoryResults').innerHTML = (data.results||[]).map(r => `<div style="padding:10px;border:1px solid var(--border);border-radius:var(--radius);margin-bottom:8px"><div style="font-size:0.8rem;color:var(--text-muted)">${r.category||''} · ${r.timestamp||''}</div><div style="margin-top:4px">${r.content||''}</div></div>`).join('') || '<p style="color:var(--text-muted)">No results found.</p>';
}

async function loadTools() {
  const data = await api('/tools');
  document.getElementById('toolsTable').innerHTML = (data.tools||[]).map(t => `<tr><td><strong>${t.name}</strong></td><td><span class="badge badge-orange">${t.category||''}</span></td><td>${t.description||''}</td><td><span class="badge badge-${t.permission==='admin'?'red':t.permission==='auth'?'yellow':'green'}">${t.permission||'public'}</span></td></tr>`).join('');
}

async function loadMetrics() {
  const data = await api('/metrics');
  document.getElementById('metricsStats').innerHTML = [
    { label:'Total Requests', value: data.total_requests||0 },
    { label:'Avg Latency', value: (data.avg_latency_ms||0).toFixed(0)+'ms' },
    { label:'Active Queue', value: data.queue_active||0 },
    { label:'Uptime', value: data.uptime||'0s' },
  ].map(s => `<div class="stat-card"><div class="stat-value">${s.value}</div><div class="stat-label">${s.label}</div></div>`).join('');
  document.getElementById('metricsTable').innerHTML = (data.request_log||[]).slice(-20).reverse().map(r => `<tr><td>${r.endpoint}</td><td>${r.latency_ms}ms</td><td><span class="badge badge-${r.status===200?'green':'red'}">${r.status}</span></td><td>${new Date(r.timestamp*1000).toLocaleTimeString()}</td></tr>`).join('');
}

async function loadSecurity() {
  const data = await api('/security');
  document.getElementById('securityTable').innerHTML = Object.entries(data.checks||{}).map(([k,v]) => `<tr><td>${k}</td><td><span class="badge badge-${v.includes('✅')?'green':'red'}">${v}</span></td></tr>`).join('');
  document.getElementById('auditLog').innerHTML = (data.audit_log||[]).slice(-30).reverse().map(e => `<div style="padding:4px 0;border-bottom:1px solid var(--border)"><span style="color:var(--text-muted)">${e.time}</span> <span class="badge badge-purple">${e.user}</span> ${e.event}</div>`).join('') || '<p style="color:var(--text-muted)">No audit events.</p>';
}

async function loadUsers() {
  const data = await api('/users');
  document.getElementById('usersTable').innerHTML = (data.users||[]).map(u => `<tr><td><strong>${u.username}</strong></td><td><span class="badge badge-${u.role==='admin'?'purple':'green'}">${u.role}</span></td><td>${u.created||''}</td></tr>`).join('');
}

async function loadConfig() {
  const data = await api('/config');
  const config = data.config || {};
  let html = '<div class="table-wrap"><table><thead><tr><th>Key</th><th>Value</th></tr></thead><tbody>';
  for (const [section, values] of Object.entries(config)) {
    if (typeof values === 'object') {
      for (const [k, v] of Object.entries(values)) {
        const vStr = typeof v === 'string' && v.length > 20 ? v.slice(0,8)+'...' : String(v);
        html += `<tr><td style="color:var(--text-secondary)">${section}.${k}</td><td>${vStr}</td></tr>`;
      }
    }
  }
  html += '</tbody></table></div>';
  document.getElementById('configContent').innerHTML = html;
}

async function loadAutomation() {
  const data = await api('/automation/jobs');
  const jobs = data.jobs || [];
  document.getElementById('automationTable').innerHTML = jobs.length ? jobs.map(j => `<tr><td>${j.name}</td><td><code>${j.schedule}</code></td><td><span class="badge badge-purple">${j.type}</span></td><td><span class="badge badge-green">active</span></td></tr>`).join('') : '<tr><td colspan="4" style="text-align:center;color:var(--text-muted)">No scheduled jobs</td></tr>';
}

async function loadKnowledge() {
  const data = await api('/knowledge/stats');
  document.getElementById('knowledgeStats').innerHTML = [
    { label:'Entities', value: data.total_entities||0 },
    { label:'Relationships', value: data.total_relationships||0 },
    { label:'Dates Tracked', value: data.dates_tracked||0 },
  ].map(s => `<div class="stat-card"><div class="stat-value">${s.value}</div><div class="stat-label">${s.label}</div></div>`).join('');
}

async function searchKnowledge() {
  const q = document.getElementById('knowledgeSearchInput').value;
  if (!q) return;
  const data = await api('/knowledge/search?q=' + encodeURIComponent(q));
  document.getElementById('knowledgeResults').innerHTML = (data.results||[]).map(r => `<div style="padding:10px;border:1px solid var(--border);border-radius:var(--radius);margin-bottom:8px"><strong>${r.name}</strong> <span class="tag">${r.type}</span><div style="margin-top:4px;font-size:0.85rem;color:var(--text-secondary)">${r.description||''}</div></div>`).join('') || '<p style="color:var(--text-muted)">No results found.</p>';
}

async function loadWorkflows() {
  const data = await api('/workflows');
  const workflows = data.workflows || [];
  if (workflows.length) {
    document.getElementById('workflowsList').innerHTML = workflows.map(w => `<div style="padding:12px;border:1px solid var(--border);border-radius:var(--radius);margin-bottom:8px;display:flex;justify-content:space-between;align-items:center"><div><strong>${w.name}</strong><div style="font-size:0.8rem;color:var(--text-muted)">${w.step_count||0} steps · ${w.created_at||''}</div></div><button class="btn btn-sm btn-secondary" onclick="replayWorkflow('${w.name}')">Replay</button></div>`).join('');
  }
}

async function replayWorkflow(name) { showToast('Replaying workflow: ' + name, 'info'); }

async function loadImprovement() {
  const data = await api('/improvement/report');
  document.getElementById('improvementStats').innerHTML = [
    { label:'Learnings', value: data.learnings||0 },
    { label:'Preferences', value: data.preferences||0 },
    { label:'Expertise Areas', value: data.expertise_areas||0 },
  ].map(s => `<div class="stat-card"><div class="stat-value">${s.value}</div><div class="stat-label">${s.label}</div></div>`).join('');
  const prefs = data.top_preferences || {};
  let html = '<h4 style="margin-bottom:12px">Preferences</h4>';
  for (const [k, v] of Object.entries(prefs)) {
    html += `<div style="padding:8px 0;border-bottom:1px solid var(--border);display:flex;justify-content:space-between"><span>${k}</span><span class="badge badge-purple">${v.value} (${Math.round((v.confidence||0)*100)}%)</span></div>`;
  }
  document.getElementById('improvementContent').innerHTML = html || '<p style="color:var(--text-muted)">No data yet.</p>';
}

async function loadSystem() {
  const data = await api('/system/info');
  document.getElementById('systemStats').innerHTML = [
    { label:'Platform', value: data.platform||'Unknown' },
    { label:'Python', value: data.python_version||'?' },
    { label:'CPU Cores', value: data.cpu_count||0 },
  ].map(s => `<div class="stat-card"><div class="stat-value" style="font-size:1.2rem">${s.value}</div><div class="stat-label">${s.label}</div></div>`).join('');
  let html = '<div class="table-wrap"><table><tbody>';
  for (const [k, v] of Object.entries(data)) {
    html += `<tr><td style="color:var(--text-secondary);font-weight:500">${k}</td><td>${typeof v === 'object' ? JSON.stringify(v) : v}</td></tr>`;
  }
  html += '</tbody></table></div>';
  document.getElementById('systemContent').innerHTML = html;
}

async function loadProfile() {
  const data = await api('/user/profile');
  document.getElementById('profileContent').innerHTML = `<div style="display:flex;align-items:center;gap:16px;margin-bottom:20px"><div style="width:56px;height:56px;border-radius:50%;background:var(--primary-light);display:flex;align-items:center;justify-content:center;font-size:1.5rem;color:var(--primary);font-weight:700">${(currentUser||'A')[0].toUpperCase()}</div><div><div style="font-size:1.2rem;font-weight:600">${currentUser}</div><div style="color:var(--text-secondary)">Admin</div></div></div><div class="divider"></div><button class="btn btn-danger" onclick="logout()">Sign Out</button>`;
}

// ═══════ WEBSOCKET ═══════
function connectWS() {
  if (ws && ws.readyState <= 1) return;
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(`${proto}://${location.host}/ws?token=${encodeURIComponent(authToken)}`);
  ws.onopen = () => {
    clearTimeout(wsReconnectTimer);
    const dot = document.getElementById('wsDot');
    const txt = document.getElementById('wsStatus');
    if (dot) dot.className = 'status-dot';
    if (txt) txt.textContent = 'Connected';
  };
  ws.onclose = () => {
    const dot = document.getElementById('wsDot');
    const txt = document.getElementById('wsStatus');
    if (dot) dot.className = 'status-dot disconnected';
    if (txt) txt.textContent = 'Disconnected';
    wsReconnectTimer = setTimeout(connectWS, 3000);
  };
  ws.onerror = () => {};
  ws.onmessage = (evt) => {
    try {
      const msg = JSON.parse(evt.data);
      if (msg.type === 'token') {
        appendToken(msg.content);
      } else if (msg.type === 'done') {
        finishResponse();
      } else if (msg.type === 'error') {
        appendMessage('system', 'Error: ' + msg.error);
        finishResponse();
      } else if (msg.type === 'tool_call') {
        appendToolCall(msg.tool, msg.input);
      }
    } catch(e) {}
  };
}

// ═══════ CHAT ═══════
let currentStreamEl = null;

function appendMessage(role, content) {
  const container = document.getElementById('chatMessages');
  const welcome = document.getElementById('chatWelcome');
  if (welcome) welcome.style.display = 'none';

  if (role === 'system') {
    const div = document.createElement('div');
    div.className = 'msg-system';
    div.innerHTML = `<span>${content}</span>`;
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
    return;
  }

  const msg = document.createElement('div');
  msg.className = 'msg';
  const isUser = role === 'user';
  msg.innerHTML = `
    <div class="msg-avatar ${isUser ? 'user' : 'ai'}">${isUser ? (currentUser||'U')[0].toUpperCase() : 'R'}</div>
    <div class="msg-body">
      <div class="msg-name">${isUser ? currentUser : 'Rally'}</div>
      <div class="msg-content">${escapeHtml(content)}</div>
    </div>`;
  container.appendChild(msg);
  container.scrollTop = container.scrollHeight;
  return msg;
}

function appendStreamStart() {
  const container = document.getElementById('chatMessages');
  const welcome = document.getElementById('chatWelcome');
  if (welcome) welcome.style.display = 'none';

  const msg = document.createElement('div');
  msg.className = 'msg';
  msg.innerHTML = `
    <div class="msg-avatar ai">R</div>
    <div class="msg-body">
      <div class="msg-name">Rally</div>
      <div class="msg-content" id="streamContent"></div>
    </div>`;
  container.appendChild(msg);
  currentStreamEl = msg.querySelector('#streamContent');
  container.scrollTop = container.scrollHeight;
}

function appendToken(text) {
  if (!currentStreamEl) appendStreamStart();
  currentStreamEl.textContent += text;
  document.getElementById('chatMessages').scrollTop = document.getElementById('chatMessages').scrollHeight;
}

function finishResponse() {
  currentStreamEl = null;
  isWaiting = false;
  document.getElementById('sendBtn').disabled = false;
  document.getElementById('typingIndicator').style.display = 'none';
}

function appendToolCall(tool, input) {
  const container = document.getElementById('chatMessages');
  const div = document.createElement('div');
  div.className = 'msg msg-tool';
  div.innerHTML = `<div class="msg-avatar" style="background:var(--warning-light);color:var(--warning)">⚙</div><div class="msg-body"><div class="tool-name">Using tool: ${tool}</div><div class="msg-content" style="font-size:0.82rem;color:var(--text-secondary)">${typeof input === 'string' ? input : JSON.stringify(input)}</div></div>`;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
}

function escapeHtml(text) {
  const d = document.createElement('div');
  d.textContent = text;
  return d.innerHTML;
}

function sendMessage() {
  const input = document.getElementById('chatInput');
  const text = input.value.trim();
  if (!text || isWaiting) return;
  isWaiting = true;
  document.getElementById('sendBtn').disabled = true;
  document.getElementById('typingIndicator').style.display = 'flex';
  input.value = '';
  input.style.height = 'auto';
  appendMessage('user', text);
  if (ws && ws.readyState === 1) {
    ws.send(JSON.stringify({ type: 'chat', content: text }));
  } else {
    api('/chat', { method: 'POST', body: JSON.stringify({ message: text }) })
      .then(data => { appendMessage('ai', data.response || ''); finishResponse(); })
      .catch(e => { appendMessage('system', 'Error: ' + e.message); finishResponse(); });
  }
}

function useSuggestion(text) {
  document.getElementById('chatInput').value = text;
  sendMessage();
}

// ═══════ BROWSER ═══════
async function browserGo() {
  const url = document.getElementById('browserUrl').value;
  if (!url) return;
  try {
    const data = await api('/browser/navigate', { method: 'POST', body: JSON.stringify({ url }) });
    document.getElementById('browserContent').textContent = data.content || 'Page loaded.';
  } catch(e) {
    document.getElementById('browserContent').textContent = 'Error: ' + e.message;
  }
}

// ═══════ INIT ═══════
async function startApp() {
  document.getElementById('app').style.display = 'flex';
  document.getElementById('topbarUser').textContent = currentUser;
  connectWS();
  loadPageData('chat');
}

// Auto-resize chat input
document.addEventListener('DOMContentLoaded', () => {
  const input = document.getElementById('chatInput');
  if (input) {
    input.addEventListener('input', function() {
      this.style.height = 'auto';
      this.style.height = Math.min(this.scrollHeight, 160) + 'px';
    });
    input.addEventListener('keydown', function(e) {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
    });
  }

  // Check auth state
  if (authToken) {
    checkOnboarding().then(needsSetup => {
      if (!needsSetup) startApp();
    });
  } else {
    checkOnboarding().then(needsSetup => {
      if (!needsSetup) document.getElementById('loginPage').style.display = 'flex';
    });
  }
});
</script>
</body>
</html>
"""


# ═══════════════════════════════════════════════════════════════
# 🌐 Rally Web Server — FastAPI + WebSocket
# ═══════════════════════════════════════════════════════════════

def create_app(engine):
    """Create the Rally Agent web application with full API and UI.

    Args:
        engine: The main Rally engine instance with:
            - engine.chat(messages) -> response
            - engine.orchestrator: AgentOrchestrator
            - engine.swarm: SwarmQueen (optional)
            - engine.memory: MemorySystem (optional)
            - engine.tools: ToolRegistry (optional)
            - engine.providers: ProviderManager (optional)
            - engine.plugins: PluginManager (optional)
            - engine.config: dict
            - engine.browser: BrowserAutomation (optional)
            - engine.sandbox: SandboxExecutor (optional)
            - engine.data_dir: str
    """

    app = FastAPI(title="Rally Agent", version="2.0.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── State ──────────────────────────────────────────────────
    start_time = time.time()
    active_ws: list[WebSocket] = []
    request_log: list[dict] = []
    audit_log: list[dict] = []
    users_db: dict[str, dict] = {}
    feedback_log: list[dict] = []

    # Initialize default admin user
    admin_pw_hash = hashlib.sha256("admin".encode()).hexdigest()
    users_db["admin"] = {
        "username": "admin",
        "password_hash": admin_pw_hash,
        "role": "admin",
        "created": datetime.now().isoformat(),
    }

    # Load users from disk if available
    users_file = os.path.join(getattr(engine, 'data_dir', '~/.rally-agent/data'), 'users.json')
    users_file = os.path.expanduser(users_file)
    if os.path.exists(users_file):
        try:
            with open(users_file) as f:
                loaded = json.load(f)
                users_db.update(loaded)
        except Exception:
            pass

    def _save_users():
        os.makedirs(os.path.dirname(users_file), exist_ok=True)
        with open(users_file, 'w') as f:
            json.dump(users_db, f, indent=2)

    def _log_audit(event: str, user: str = "system"):
        audit_log.append({
            "time": datetime.now().isoformat(),
            "user": user,
            "event": event,
        })
        if len(audit_log) > 500:
            audit_log[:] = audit_log[-500:]

    def _record_request(endpoint: str, latency_ms: float, status_code: int = 200):
        request_log.append({
            "endpoint": endpoint,
            "latency_ms": round(latency_ms, 2),
            "status": status_code,
            "timestamp": time.time(),
        })
        if len(request_log) > 1000:
            request_log[:] = request_log[-1000:]

    def _uptime() -> str:
        s = int(time.time() - start_time)
        if s < 60: return f"{s}s"
        if s < 3600: return f"{s//60}m {s%60}s"
        return f"{s//3600}h {(s%3600)//60}m"

    # ── Auth dependency ────────────────────────────────────────
    async def get_current_user(request: Request) -> Optional[str]:
        auth = request.headers.get("Authorization", "")
        token = auth.replace("Bearer ", "") if auth.startswith("Bearer ") else ""
        # Also check query param (for file downloads)
        if not token:
            token = request.query_params.get("token", "")
        if not token:
            return None
        payload = _jwt_decode(token)
        if not payload:
            return None
        return payload.get("sub")

    async def require_auth(request: Request) -> str:
        user = await get_current_user(request)
        if not user:
            raise HTTPException(status_code=401, detail="Not authenticated")
        return user

    async def require_admin(request: Request) -> str:
        user = await require_auth(request)
        if users_db.get(user, {}).get("role") != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")
        return user

    def _make_token(username: str) -> str:
        return _jwt_encode({
            "sub": username,
            "role": users_db.get(username, {}).get("role", "user"),
            "exp": time.time() + JWT_EXPIRY_HOURS * 3600,
        })

    # ── WebSocket ──────────────────────────────────────────────
    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket, token: str = Query("")):
        # Auth check
        user = None
        if token:
            payload = _jwt_decode(token)
            if payload:
                user = payload.get("sub")
        if not user:
            await websocket.close(code=4001)
            return

        await websocket.accept()
        active_ws.append(websocket)
        _log_audit(f"WebSocket connected: {user}", user)

        try:
            while True:
                data = await websocket.receive_text()
                msg = json.loads(data)

                if msg.get("type") == "chat":
                    content = msg.get("content", "")
                    _log_audit(f"Chat message: {content[:100]}", user)

                    try:
                        # Stream response via engine
                        if hasattr(engine, 'chat_stream'):
                            async for chunk in engine.chat_stream(content):
                                await websocket.send_json({"type": "token", "content": chunk})
                            await websocket.send_json({"type": "done", "content": ""})
                        elif hasattr(engine, 'chat'):
                            # Try streaming if engine.chat returns async generator
                            result = engine.chat(content)
                            if hasattr(result, '__aiter__'):
                                async for chunk in result:
                                    if isinstance(chunk, dict):
                                        await websocket.send_json(chunk)
                                    else:
                                        await websocket.send_json({"type": "token", "content": str(chunk)})
                                await websocket.send_json({"type": "done", "content": ""})
                            else:
                                response = await result if asyncio.iscoroutine(result) else result
                                # Simulate streaming by sending in chunks
                                response_str = str(response)
                                chunk_size = 20
                                for i in range(0, len(response_str), chunk_size):
                                    await websocket.send_json({"type": "token", "content": response_str[i:i+chunk_size]})
                                    await asyncio.sleep(0.02)
                                await websocket.send_json({"type": "done", "content": ""})
                        else:
                            await websocket.send_json({"type": "error", "content": "No chat engine available"})

                    except Exception as e:
                        await websocket.send_json({"type": "error", "content": str(e)})

                elif msg.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})

        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            if websocket in active_ws:
                active_ws.remove(websocket)

    # ══════════════════════════════════════════════════════════════
    # 🔑 Auth Endpoints
    # ══════════════════════════════════════════════════════════════

    @app.post("/api/auth/login")
    async def auth_login(body: dict):
        t0 = time.time()
        username = body.get("username", "").strip()
        password = body.get("password", "")
        if not username or not password:
            _record_request("auth/login", (time.time()-t0)*1000, 400)
            return JSONResponse({"error": "Username and password required"}, status_code=400)

        pw_hash = hashlib.sha256(password.encode()).hexdigest()
        user = users_db.get(username)
        if not user or user.get("password_hash") != pw_hash:
            _log_audit(f"Failed login: {username}")
            _record_request("auth/login", (time.time()-t0)*1000, 401)
            return JSONResponse({"error": "Invalid credentials"}, status_code=401)

        token = _make_token(username)
        _log_audit(f"Login success: {username}", username)
        _record_request("auth/login", (time.time()-t0)*1000)
        return {"token": token, "user": {"username": username, "role": user.get("role", "user")}}

    @app.post("/api/auth/register")
    async def auth_register(body: dict):
        t0 = time.time()
        username = body.get("username", "").strip()
        password = body.get("password", "")
        role = body.get("role", "user")
        if not username or not password:
            return JSONResponse({"error": "Username and password required"}, status_code=400)
        if len(password) < 4:
            return JSONResponse({"error": "Password must be at least 4 characters"}, status_code=400)
        if username in users_db:
            return JSONResponse({"error": "Username already exists"}, status_code=409)

        pw_hash = hashlib.sha256(password.encode()).hexdigest()
        users_db[username] = {
            "username": username,
            "password_hash": pw_hash,
            "role": role if role in ("user", "admin") else "user",
            "created": datetime.now().isoformat(),
        }
        _save_users()
        token = _make_token(username)
        _log_audit(f"User registered: {username}")
        _record_request("auth/register", (time.time()-t0)*1000)
        return {"token": token, "user": {"username": username, "role": role}}

    # ══════════════════════════════════════════════════════════════
    # 🧙 Setup / Onboarding
    # ══════════════════════════════════════════════════════════════

    @app.get("/api/setup/status")
    async def setup_status():
        """Check if this is a first-run (no providers configured)."""
        from core.onboarding import SetupWizard
        wizard = SetupWizard(getattr(engine, 'config', {}))
        data = await wizard.run_web()
        return data

    @app.post("/api/setup/complete")
    async def setup_complete(body: dict):
        """Save onboarding data from the web UI."""
        from core.onboarding import SetupWizard
        wizard = SetupWizard(getattr(engine, 'config', {}))
        result = await wizard.complete_web_setup(body)
        if result.get("status") == "error":
            return JSONResponse(result, status_code=400)
        _log_audit("Setup wizard completed via web")
        return result

    @app.get("/api/setup/guides")
    async def setup_guides():
        """Get all provider setup guides."""
        from core.onboarding import SetupWizard
        wizard = SetupWizard(getattr(engine, 'config', {}))
        return {"guides": wizard.get_all_provider_guides()}

    @app.get("/api/setup/guide/{provider_name}")
    async def setup_guide(provider_name: str):
        """Get setup guide for a specific provider."""
        from core.onboarding import SetupWizard
        wizard = SetupWizard(getattr(engine, 'config', {}))
        return wizard.get_provider_setup_guide(provider_name)

    # ══════════════════════════════════════════════════════════════
    # 📊 Status & Config
    # ══════════════════════════════════════════════════════════════

    @app.get("/api/status")
    async def get_status(user: str = Depends(require_auth)):
        t0 = time.time()
        orchestrator = getattr(engine, 'orchestrator', None)
        agents_count = len(orchestrator.agents) if orchestrator else 0
        tools_reg = getattr(engine, 'tools', None)
        tools_count = len(tools_reg.tools) if tools_reg and hasattr(tools_reg, 'tools') else 0
        providers_mgr = getattr(engine, 'providers', None)
        providers_list = []
        if providers_mgr:
            if hasattr(providers_mgr, 'providers'):
                providers_list = list(providers_mgr.providers.keys()) if isinstance(providers_mgr.providers, dict) else [str(p) for p in providers_mgr.providers]
            elif hasattr(providers_mgr, 'list'):
                providers_list = [p.get('name', str(p)) for p in providers_mgr.list()]

        memory = getattr(engine, 'memory', None)
        memory_entries = 0
        if memory:
            if hasattr(memory, 'entries'):
                memory_entries = len(memory.entries)
            elif hasattr(memory, 'count'):
                memory_entries = memory.count()

        plugins_mgr = getattr(engine, 'plugins', None)
        plugins_count = 0
        if plugins_mgr:
            if hasattr(plugins_mgr, 'plugins'):
                plugins_count = len(plugins_mgr.plugins)

        # Request history for charts (last 24 data points)
        now = time.time()
        req_history = [0] * 24
        lat_history = [0] * 24
        for r in request_log:
            hours_ago = int((now - r['timestamp']) / 3600)
            idx = 23 - min(hours_ago, 23)
            req_history[idx] += 1
            lat_history[idx] = max(lat_history[idx], r['latency_ms'])

        _record_request("status", (time.time()-t0)*1000)
        return {
            "version": "2.0.0",
            "uptime": _uptime(),
            "agents_count": agents_count,
            "tools_count": tools_count,
            "providers": providers_list,
            "total_requests": len(request_log),
            "memory_entries": memory_entries,
            "plugins_count": plugins_count,
            "active_connections": len(active_ws),
            "request_history": req_history,
            "latency_history": lat_history,
        }

    @app.get("/api/config")
    async def get_config(user: str = Depends(require_auth)):
        config = getattr(engine, 'config', {})
        if callable(config):
            config = config()
        # Sanitize sensitive fields
        safe_config = _sanitize_config(config) if isinstance(config, dict) else {"raw": str(config)}
        return {"config": safe_config}

    @app.post("/api/config")
    async def update_config(body: dict, user: str = Depends(require_admin)):
        config_data = body.get("config", {})
        if hasattr(engine, 'update_config'):
            engine.update_config(config_data)
        elif hasattr(engine, 'config'):
            if isinstance(engine.config, dict):
                engine.config.update(config_data)
        _log_audit(f"Config updated by {user}", user)
        return {"status": "updated"}

    def _sanitize_config(config: dict) -> dict:
        """Remove sensitive fields from config"""
        sensitive_keys = {'api_key', 'apikey', 'secret', 'password', 'token', 'private_key', 'credentials'}
        result = {}
        for k, v in config.items():
            if any(s in k.lower() for s in sensitive_keys):
                result[k] = "***REDACTED***"
            elif isinstance(v, dict):
                result[k] = _sanitize_config(v)
            else:
                result[k] = v
        return result

    # ══════════════════════════════════════════════════════════════
    # 💬 Chat (SSE fallback)
    # ══════════════════════════════════════════════════════════════

    @app.post("/api/chat")
    async def api_chat(body: dict, user: str = Depends(require_auth)):
        t0 = time.time()
        content = body.get("content", "")
        if not content:
            return JSONResponse({"error": "No content provided"}, status_code=400)

        _log_audit(f"Chat: {content[:80]}", user)

        async def event_stream():
            try:
                if hasattr(engine, 'chat_stream'):
                    async for chunk in engine.chat_stream(content):
                        yield f"data: {json.dumps({'type': 'token', 'content': chunk})}\n\n"
                    yield f"data: {json.dumps({'type': 'done', 'content': ''})}\n\n"
                elif hasattr(engine, 'chat'):
                    result = engine.chat(content)
                    if asyncio.iscoroutine(result):
                        result = await result
                    if hasattr(result, '__aiter__'):
                        async for chunk in result:
                            if isinstance(chunk, dict):
                                yield f"data: {json.dumps(chunk)}\n\n"
                            else:
                                yield f"data: {json.dumps({'type': 'token', 'content': str(chunk)})}\n\n"
                        yield f"data: {json.dumps({'type': 'done', 'content': ''})}\n\n"
                    else:
                        response = str(result)
                        chunk_size = 20
                        for i in range(0, len(response), chunk_size):
                            yield f"data: {json.dumps({'type': 'token', 'content': response[i:i+chunk_size]})}\n\n"
                            await asyncio.sleep(0.01)
                        yield f"data: {json.dumps({'type': 'done', 'content': ''})}\n\n"
                else:
                    yield f"data: {json.dumps({'type': 'error', 'content': 'No chat engine available'})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

        _record_request("chat", (time.time()-t0)*1000)
        return StreamingResponse(event_stream(), media_type="text/event-stream")

    # ══════════════════════════════════════════════════════════════
    # 🤖 Agents
    # ══════════════════════════════════════════════════════════════

    @app.get("/api/agents")
    async def list_agents(user: str = Depends(require_auth)):
        orchestrator = getattr(engine, 'orchestrator', None)
        agents = []
        if orchestrator:
            agents = orchestrator.get_all() if hasattr(orchestrator, 'get_all') else []
        return {"agents": agents}

    @app.post("/api/agents/spawn")
    async def spawn_agent(body: dict, user: str = Depends(require_auth)):
        agent_type = body.get("type", "orchestrator")
        task = body.get("task", "")
        orchestrator = getattr(engine, 'orchestrator', None)
        if not orchestrator:
            return JSONResponse({"error": "No orchestrator available"}, status_code=400)
        agent = orchestrator.spawn(agent_type) if hasattr(orchestrator, 'spawn') else None
        if not agent:
            return JSONResponse({"error": f"Unknown agent type: {agent_type}"}, status_code=400)
        _log_audit(f"Agent spawned: {agent_type}", user)
        result = None
        if task and hasattr(agent, 'process'):
            result = await agent.process(task) if asyncio.iscoroutinefunction(agent.process) else agent.process(task)
        return {"agent": agent.to_dict() if hasattr(agent, 'to_dict') else {"name": str(agent)}, "result": result}

    @app.post("/api/swarm")
    async def run_swarm(body: dict, user: str = Depends(require_auth)):
        task = body.get("task", "")
        size = body.get("size", 10)
        swarm = getattr(engine, 'swarm', None)
        if not swarm:
            return JSONResponse({"error": "Swarm not available"}, status_code=400)
        if not task:
            return JSONResponse({"error": "Task required"}, status_code=400)
        _log_audit(f"Swarm task: {task[:80]}", user)
        result = await swarm.execute_swarm_task(task, size)
        return {"result": result, "stats": swarm.get_swarm_stats()}

    # ══════════════════════════════════════════════════════════════
    # 🧠 Memory
    # ══════════════════════════════════════════════════════════════

    @app.get("/api/memory")
    async def memory_stats(user: str = Depends(require_auth)):
        memory = getattr(engine, 'memory', None)
        if not memory:
            # Try swarm knowledge
            swarm = getattr(engine, 'swarm', None)
            if swarm and hasattr(swarm, 'knowledge'):
                return swarm.knowledge.get_stats()
            return {"total_entries": 0, "categories": [], "most_useful": []}
        if hasattr(memory, 'get_stats'):
            return memory.get_stats()
        return {"total_entries": getattr(memory, 'count', lambda: 0)()}

    @app.get("/api/memory/search")
    async def memory_search(q: str = Query(""), user: str = Depends(require_auth)):
        if not q:
            return {"results": []}
        memory = getattr(engine, 'memory', None)
        if memory and hasattr(memory, 'search'):
            results = memory.search(q)
            return {"results": results}
        # Try swarm knowledge
        swarm = getattr(engine, 'swarm', None)
        if swarm and hasattr(swarm, 'knowledge'):
            return {"results": swarm.knowledge.search(q)}
        return {"results": []}

    @app.post("/api/memory/rag/ingest")
    async def rag_ingest(body: dict, user: str = Depends(require_auth)):
        content = body.get("content", "")
        if not content:
            return JSONResponse({"error": "Content required"}, status_code=400)
        memory = getattr(engine, 'memory', None)
        if memory and hasattr(memory, 'add'):
            memory.add(content, source="web-ui", category="rag")
            return {"status": "ingested", "length": len(content)}
        # Try swarm knowledge
        swarm = getattr(engine, 'swarm', None)
        if swarm and hasattr(swarm, 'knowledge'):
            swarm.knowledge.add(content, source="web-ui", category="rag")
            return {"status": "ingested", "length": len(content)}
        return JSONResponse({"error": "No memory system available"}, status_code=400)

    @app.get("/api/memory/rag/search")
    async def rag_search(q: str = Query(""), user: str = Depends(require_auth)):
        if not q:
            return {"results": []}
        memory = getattr(engine, 'memory', None)
        if memory and hasattr(memory, 'search'):
            return {"results": memory.search(q)}
        swarm = getattr(engine, 'swarm', None)
        if swarm and hasattr(swarm, 'knowledge'):
            return {"results": swarm.knowledge.search(q)}
        return {"results": []}

    # ══════════════════════════════════════════════════════════════
    # 🛠️ Tools
    # ══════════════════════════════════════════════════════════════

    @app.get("/api/tools")
    async def list_tools(user: str = Depends(require_auth)):
        tools_reg = getattr(engine, 'tools', None)
        tools_list = []
        if tools_reg:
            if hasattr(tools_reg, 'list'):
                tools_list = tools_reg.list()
            elif hasattr(tools_reg, 'tools'):
                if isinstance(tools_reg.tools, dict):
                    tools_list = [
                        {"name": name, "description": getattr(t, 'description', ''), "parameters": getattr(t, 'parameters', {})}
                        for name, t in tools_reg.tools.items()
                    ]
                else:
                    tools_list = [{"name": str(t), "description": "", "parameters": {}} for t in tools_reg.tools]
        return {"tools": tools_list}

    @app.post("/api/tools/execute")
    async def execute_tool(body: dict, user: str = Depends(require_auth)):
        tool_name = body.get("tool", "")
        args = body.get("args", {})
        tools_reg = getattr(engine, 'tools', None)
        if not tools_reg:
            return JSONResponse({"error": "No tool registry"}, status_code=400)
        _log_audit(f"Tool executed: {tool_name}", user)
        try:
            if hasattr(tools_reg, 'execute'):
                result = await tools_reg.execute(tool_name, args) if asyncio.iscoroutinefunction(tools_reg.execute) else tools_reg.execute(tool_name, args)
            elif hasattr(tools_reg, 'tools') and isinstance(tools_reg.tools, dict):
                tool = tools_reg.tools.get(tool_name)
                if not tool:
                    return JSONResponse({"error": f"Tool not found: {tool_name}"}, status_code=404)
                fn = getattr(tool, 'execute', None) or getattr(tool, 'run', None) or getattr(tool, '__call__', None)
                if not fn:
                    return JSONResponse({"error": "Tool has no execute method"}, status_code=400)
                result = await fn(**args) if asyncio.iscoroutinefunction(fn) else fn(**args)
            else:
                return JSONResponse({"error": "Cannot execute tool"}, status_code=400)
            return {"result": result}
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

    # ══════════════════════════════════════════════════════════════
    # 🔌 Providers & Channels
    # ══════════════════════════════════════════════════════════════

    @app.get("/api/providers")
    async def list_providers(user: str = Depends(require_auth)):
        providers_mgr = getattr(engine, 'providers', None)
        providers_list = []
        if providers_mgr:
            if hasattr(providers_mgr, 'list'):
                providers_list = providers_mgr.list()
            elif hasattr(providers_mgr, 'providers') and isinstance(providers_mgr.providers, dict):
                providers_list = [
                    {"name": k, "status": "active", "model": getattr(v, 'model', '') if hasattr(v, 'model') else ''}
                    for k, v in providers_mgr.providers.items()
                ]
        return {"providers": providers_list}

    @app.get("/api/channels")
    async def list_channels(user: str = Depends(require_auth)):
        channels_mgr = getattr(engine, 'channels', None)
        channels_list = []
        if channels_mgr:
            if hasattr(channels_mgr, 'list'):
                channels_list = channels_mgr.list()
            elif hasattr(channels_mgr, 'channels'):
                if isinstance(channels_mgr.channels, dict):
                    channels_list = [
                        {"name": k, "type": getattr(v, 'channel_type', 'unknown'), "enabled": getattr(v, 'enabled', True)}
                        for k, v in channels_mgr.channels.items()
                    ]
        return {"channels": channels_list}

    # ══════════════════════════════════════════════════════════════
    # 🔌 Plugins
    # ══════════════════════════════════════════════════════════════

    @app.get("/api/plugins")
    async def list_plugins(user: str = Depends(require_auth)):
        plugins_mgr = getattr(engine, 'plugins', None)
        plugins_list = []
        if plugins_mgr:
            if hasattr(plugins_mgr, 'list'):
                plugins_list = plugins_mgr.list()
            elif hasattr(plugins_mgr, 'plugins'):
                if isinstance(plugins_mgr.plugins, dict):
                    plugins_list = [
                        {"name": k, "enabled": getattr(v, 'enabled', True), "description": getattr(v, 'description', ''), "version": getattr(v, 'version', '1.0')}
                        for k, v in plugins_mgr.plugins.items()
                    ]
        return {"plugins": plugins_list}

    @app.post("/api/plugins/install")
    async def install_plugin(body: dict, user: str = Depends(require_admin)):
        name = body.get("name", "")
        if not name:
            return JSONResponse({"error": "Plugin name required"}, status_code=400)
        plugins_mgr = getattr(engine, 'plugins', None)
        if not plugins_mgr:
            return JSONResponse({"error": "No plugin manager"}, status_code=400)
        try:
            if hasattr(plugins_mgr, 'install'):
                result = await plugins_mgr.install(name) if asyncio.iscoroutinefunction(plugins_mgr.install) else plugins_mgr.install(name)
            else:
                return JSONResponse({"error": "Install not supported"}, status_code=400)
            _log_audit(f"Plugin installed: {name}", user)
            return {"status": "installed", "result": result}
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

    # ══════════════════════════════════════════════════════════════
    # 📈 Metrics & Dashboard
    # ══════════════════════════════════════════════════════════════

    @app.get("/api/metrics")
    async def get_metrics(user: str = Depends(require_auth)):
        total = len(request_log)
        latencies = [r['latency_ms'] for r in request_log] if request_log else [0]
        errors = sum(1 for r in request_log if r.get('status', 200) >= 400)
        avg_lat = sum(latencies) / len(latencies) if latencies else 0

        # Throughput (last 24 hours)
        now = time.time()
        throughput = [0] * 24
        error_hist = [0] * 24
        for r in request_log:
            hours_ago = int((now - r['timestamp']) / 3600)
            idx = 23 - min(hours_ago, 23)
            throughput[idx] += 1
            if r.get('status', 200) >= 400:
                error_hist[idx] += 1

        return {
            "total_requests": total,
            "avg_latency_ms": round(avg_lat, 2),
            "error_rate": f"{(errors/max(total,1)*100):.1f}%",
            "active_connections": len(active_ws),
            "throughput_history": throughput,
            "error_history": error_hist,
            "p50_latency": round(sorted(latencies)[len(latencies)//2], 2) if latencies else 0,
            "p99_latency": round(sorted(latencies)[int(len(latencies)*0.99)], 2) if latencies else 0,
        }

    @app.get("/api/metrics/dashboard")
    async def get_dashboard(user: str = Depends(require_auth)):
        metrics = await get_metrics(user)
        status = await get_status(user)
        return {**metrics, **status}

    # ══════════════════════════════════════════════════════════════
    # 🌐 Browser Automation
    # ══════════════════════════════════════════════════════════════

    @app.post("/api/browser/navigate")
    async def browser_navigate(body: dict, user: str = Depends(require_auth)):
        url = body.get("url", "")
        if not url:
            return JSONResponse({"error": "URL required"}, status_code=400)
        browser = getattr(engine, 'browser', None)
        if not browser:
            return JSONResponse({"error": "Browser automation not available"}, status_code=400)
        try:
            if hasattr(browser, 'navigate'):
                result = await browser.navigate(url) if asyncio.iscoroutinefunction(browser.navigate) else browser.navigate(url)
            else:
                return JSONResponse({"error": "Navigate not supported"}, status_code=400)
            _log_audit(f"Browser navigate: {url}", user)
            return {"status": "navigated", "url": url, "result": result}
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

    @app.post("/api/browser/screenshot")
    async def browser_screenshot(body: dict, user: str = Depends(require_auth)):
        browser = getattr(engine, 'browser', None)
        if not browser:
            return JSONResponse({"error": "Browser not available"}, status_code=400)
        try:
            if hasattr(browser, 'screenshot'):
                result = await browser.screenshot() if asyncio.iscoroutinefunction(browser.screenshot) else browser.screenshot()
                # If it returns bytes, base64 encode
                if isinstance(result, bytes):
                    import base64
                    return {"screenshot": base64.b64encode(result).decode()}
                return {"screenshot": result}
            return JSONResponse({"error": "Screenshot not supported"}, status_code=400)
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

    @app.post("/api/browser/click")
    async def browser_click(body: dict, user: str = Depends(require_auth)):
        selector = body.get("selector", "")
        browser = getattr(engine, 'browser', None)
        if not browser:
            return JSONResponse({"error": "Browser not available"}, status_code=400)
        try:
            if hasattr(browser, 'click'):
                result = await browser.click(selector) if asyncio.iscoroutinefunction(browser.click) else browser.click(selector)
                return {"status": "clicked", "selector": selector, "result": result}
            return JSONResponse({"error": "Click not supported"}, status_code=400)
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

    @app.post("/api/browser/type")
    async def browser_type(body: dict, user: str = Depends(require_auth)):
        selector = body.get("selector", "")
        text = body.get("text", "")
        browser = getattr(engine, 'browser', None)
        if not browser:
            return JSONResponse({"error": "Browser not available"}, status_code=400)
        try:
            if hasattr(browser, 'type_text'):
                result = await browser.type_text(selector, text) if asyncio.iscoroutinefunction(browser.type_text) else browser.type_text(selector, text)
            elif hasattr(browser, 'type'):
                result = await browser.type(selector, text) if asyncio.iscoroutinefunction(browser.type) else browser.type(selector, text)
            else:
                return JSONResponse({"error": "Type not supported"}, status_code=400)
            return {"status": "typed", "selector": selector, "result": result}
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

    # ══════════════════════════════════════════════════════════════
    # 📦 Sandbox Execution
    # ══════════════════════════════════════════════════════════════

    @app.post("/api/sandbox/exec")
    async def sandbox_exec(body: dict, user: str = Depends(require_auth)):
        command = body.get("command", "")
        timeout = body.get("timeout", 30)
        if not command:
            return JSONResponse({"error": "Command required"}, status_code=400)
        sandbox = getattr(engine, 'sandbox', None)
        if not sandbox:
            return JSONResponse({"error": "Sandbox not available"}, status_code=400)
        _log_audit(f"Sandbox exec: {command[:100]}", user)
        try:
            if hasattr(sandbox, 'execute'):
                result = await sandbox.execute(command, timeout=timeout) if asyncio.iscoroutinefunction(sandbox.execute) else sandbox.execute(command, timeout=timeout)
            elif hasattr(sandbox, 'run'):
                result = await sandbox.run(command, timeout=timeout) if asyncio.iscoroutinefunction(sandbox.run) else sandbox.run(command, timeout=timeout)
            else:
                return JSONResponse({"error": "Sandbox has no execute method"}, status_code=400)
            return {"result": result}
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

    # ══════════════════════════════════════════════════════════════
    # 👥 Users (Admin)
    # ══════════════════════════════════════════════════════════════

    @app.get("/api/users")
    async def list_users(user: str = Depends(require_admin)):
        return {
            "users": [
                {
                    "username": u["username"],
                    "role": u.get("role", "user"),
                    "created": u.get("created", ""),
                }
                for u in users_db.values()
            ]
        }

    @app.delete("/api/users")
    async def delete_user(username: str = Query(...), user: str = Depends(require_admin)):
        if username == "admin":
            return JSONResponse({"error": "Cannot delete admin"}, status_code=400)
        if username not in users_db:
            return JSONResponse({"error": "User not found"}, status_code=404)
        del users_db[username]
        _save_users()
        _log_audit(f"User deleted: {username}", user)
        return {"status": "deleted"}

    # ══════════════════════════════════════════════════════════════
    # 🔒 Security
    # ══════════════════════════════════════════════════════════════

    @app.get("/api/security")
    async def security_status(user: str = Depends(require_auth)):
        failed_logins = sum(1 for e in audit_log if "Failed login" in e.get("event", ""))
        return {
            "users_count": len(users_db),
            "failed_logins": failed_logins,
            "encryption": "AES-256",
            "jwt_enabled": True,
            "audit_log": audit_log[-50:],  # Last 50 entries
        }

    # ══════════════════════════════════════════════════════════════
    # 📁 Files
    # ══════════════════════════════════════════════════════════════

    @app.get("/api/files")
    async def list_files(path: str = Query(""), user: str = Depends(require_auth)):
        data_dir = os.path.expanduser(getattr(engine, 'data_dir', '~/.rally-agent/data'))
        base = os.path.abspath(data_dir)
        target = os.path.abspath(os.path.join(base, path)) if path else base

        # Security: prevent directory traversal
        if not target.startswith(base):
            return JSONResponse({"error": "Access denied"}, status_code=403)

        if not os.path.exists(target):
            return JSONResponse({"error": "Path not found"}, status_code=404)

        if os.path.isfile(target):
            return {"type": "file", "name": os.path.basename(target), "size": os.path.getsize(target)}

        files = []
        try:
            for name in sorted(os.listdir(target)):
                full = os.path.join(target, name)
                rel = os.path.relpath(full, base)
                files.append({
                    "name": name,
                    "path": rel,
                    "is_dir": os.path.isdir(full),
                    "size": os.path.getsize(full) if os.path.isfile(full) else None,
                })
        except PermissionError:
            return JSONResponse({"error": "Permission denied"}, status_code=403)

        parent = os.path.relpath(os.path.dirname(target), base) if target != base else None
        return {"files": files, "path": path, "parent": parent}

    @app.get("/api/files/download")
    async def download_file(path: str = Query(...), user: str = Depends(require_auth)):
        data_dir = os.path.expanduser(getattr(engine, 'data_dir', '~/.rally-agent/data'))
        base = os.path.abspath(data_dir)
        target = os.path.abspath(os.path.join(base, path))

        if not target.startswith(base):
            return JSONResponse({"error": "Access denied"}, status_code=403)
        if not os.path.isfile(target):
            return JSONResponse({"error": "File not found"}, status_code=404)

        _log_audit(f"File download: {path}", user)
        return FileResponse(target, filename=os.path.basename(target))

    # ══════════════════════════════════════════════════════════════
    # 📝 Feedback
    # ══════════════════════════════════════════════════════════════

    @app.post("/api/feedback")
    async def submit_feedback(body: dict, user: str = Depends(require_auth)):
        feedback = {
            "user": user,
            "rating": body.get("rating"),
            "comment": body.get("comment", ""),
            "message_id": body.get("message_id", ""),
            "timestamp": datetime.now().isoformat(),
        }
        feedback_log.append(feedback)
        # Persist
        data_dir = os.path.expanduser(getattr(engine, 'data_dir', '~/.rally-agent/data'))
        fb_file = os.path.join(data_dir, 'feedback.json')
        try:
            os.makedirs(data_dir, exist_ok=True)
            existing = []
            if os.path.exists(fb_file):
                with open(fb_file) as f:
                    existing = json.load(f)
            existing.append(feedback)
            with open(fb_file, 'w') as f:
                json.dump(existing[-1000:], f, indent=2)
        except Exception:
            pass
        return {"status": "recorded"}

    # ══════════════════════════════════════════════════════════════
    # ⏰ Automation / Cron Jobs
    # ══════════════════════════════════════════════════════════════

    @app.get("/api/automation/jobs")
    async def list_automation_jobs(user: str = Depends(require_auth)):
        jobs = engine.list_cron_jobs() if hasattr(engine, 'list_cron_jobs') else []
        return {"jobs": jobs}

    @app.post("/api/automation/jobs")
    async def create_automation_job(body: dict, user: str = Depends(require_auth)):
        schedule = body.get("schedule", "1h")
        task = body.get("task", body.get("name", ""))
        job_type = body.get("type", "agent")
        if not task:
            return JSONResponse({"error": "Task required"}, status_code=400)
        result = engine.add_cron_job(schedule, task, job_type) if hasattr(engine, 'add_cron_job') else {"error": "Not available"}
        _log_audit(f"Cron job created: {task[:50]}", user)
        return result

    @app.delete("/api/automation/jobs/{job_id}")
    async def delete_automation_job(job_id: str, user: str = Depends(require_auth)):
        success = engine.remove_cron_job(job_id) if hasattr(engine, 'remove_cron_job') else False
        if not success:
            return JSONResponse({"error": "Job not found"}, status_code=404)
        _log_audit(f"Cron job deleted: {job_id}", user)
        return {"status": "deleted"}

    @app.post("/api/automation/jobs/{job_id}/run")
    async def run_automation_job(job_id: str, body: dict = Body({}), user: str = Depends(require_auth)):
        result = await engine.run_cron_job(job_id) if hasattr(engine, 'run_cron_job') else {"error": "Not available"}
        _log_audit(f"Cron job run: {job_id}", user)
        return result

    @app.get("/api/automation/history")
    async def automation_history(user: str = Depends(require_auth)):
        history = engine.get_cron_history() if hasattr(engine, 'get_cron_history') else []
        return {"history": history}

    # ══════════════════════════════════════════════════════════════
    # 👤 User Profile
    # ══════════════════════════════════════════════════════════════

    @app.get("/api/user/profile")
    async def get_user_profile(user: str = Depends(require_auth)):
        profile = engine.get_user_profile() if hasattr(engine, 'get_user_profile') else {"summary": "No profile available"}
        return profile

    @app.post("/api/user/profile")
    async def update_user_profile(body: dict, user: str = Depends(require_auth)):
        result = engine.update_user_profile(body) if hasattr(engine, 'update_user_profile') else {"error": "Not available"}
        _log_audit(f"Profile updated", user)
        return result

    # ══════════════════════════════════════════════════════════════
    # 🕸️ Knowledge Graph
    # ══════════════════════════════════════════════════════════════

    @app.get("/api/knowledge")
    async def knowledge_stats(user: str = Depends(require_auth)):
        return engine.get_knowledge_graph_stats() if hasattr(engine, 'get_knowledge_graph_stats') else {"total_entities": 0}

    @app.get("/api/knowledge/search")
    async def knowledge_search(q: str = Query(""), user: str = Depends(require_auth)):
        if not q:
            return {"results": []}
        results = engine.search_knowledge(q) if hasattr(engine, 'search_knowledge') else []
        return {"results": results}

    # ══════════════════════════════════════════════════════════════
    # 🔄 Workflows
    # ══════════════════════════════════════════════════════════════

    @app.get("/api/workflows")
    async def list_workflows(user: str = Depends(require_auth)):
        workflows = engine.list_workflows() if hasattr(engine, 'list_workflows') else []
        return {"workflows": workflows}

    @app.post("/api/workflows/record")
    async def record_workflow(body: dict, user: str = Depends(require_auth)):
        if body.get("stop"):
            result = engine.stop_recording_workflow() if hasattr(engine, 'stop_recording_workflow') else {"error": "Not available"}
        else:
            name = body.get("name", "unnamed")
            result = engine.record_workflow(name) if hasattr(engine, 'record_workflow') else {"error": "Not available"}
        _log_audit(f"Workflow record: {body.get('name', 'stop')}", user)
        return result

    @app.post("/api/workflows/replay")
    async def replay_workflow(body: dict, user: str = Depends(require_auth)):
        name = body.get("name", "")
        if not name:
            return JSONResponse({"error": "Workflow name required"}, status_code=400)
        result = await engine.replay_workflow(name) if hasattr(engine, 'replay_workflow') else {"error": "Not available"}
        _log_audit(f"Workflow replay: {name}", user)
        return result

    # ══════════════════════════════════════════════════════════════
    # 📈 Self-Improvement
    # ══════════════════════════════════════════════════════════════

    @app.get("/api/improvement")
    async def improvement_report(user: str = Depends(require_auth)):
        return engine.get_improvement_report() if hasattr(engine, 'get_improvement_report') else {"total_entries": 0}

    # ══════════════════════════════════════════════════════════════
    # 🖥️ Computer Use
    # ══════════════════════════════════════════════════════════════

    @app.post("/api/computer/screenshot")
    async def computer_screenshot(body: dict = Body({}), user: str = Depends(require_auth)):
        result = await engine.computer_use_screenshot() if hasattr(engine, 'computer_use_screenshot') else {"error": "Not available"}
        _log_audit("Screenshot taken", user)
        return result

    @app.post("/api/computer/click")
    async def computer_click(body: dict, user: str = Depends(require_auth)):
        x = body.get("x", 0)
        y = body.get("y", 0)
        result = await engine.computer_use_click(x, y) if hasattr(engine, 'computer_use_click') else {"error": "Not available"}
        _log_audit(f"Computer click: ({x}, {y})", user)
        return result

    @app.post("/api/computer/type")
    async def computer_type(body: dict, user: str = Depends(require_auth)):
        text = body.get("text", "")
        result = await engine.computer_use_type(text) if hasattr(engine, 'computer_use_type') else {"error": "Not available"}
        _log_audit(f"Computer type: {text[:50]}", user)
        return result

    # ══════════════════════════════════════════════════════════════
    # 🔧 System Control
    # ══════════════════════════════════════════════════════════════

    @app.get("/api/system/info")
    async def system_info(user: str = Depends(require_auth)):
        return engine.system_info() if hasattr(engine, 'system_info') else {"error": "Not available"}

    @app.post("/api/system/update")
    async def system_update(body: dict = Body({}), user: str = Depends(require_admin)):
        result = await engine.auto_update() if hasattr(engine, 'auto_update') else {"error": "Not available"}
        _log_audit("Update check", user)
        return result

    # ══════════════════════════════════════════════════════════════
    # 🌐 Main UI
    # ══════════════════════════════════════════════════════════════

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return MAIN_HTML

    @app.get("/health")
    async def health():
        return {"status": "ok", "uptime": _uptime()}

    return app


# ═══════════════════════════════════════════════════════════════
# 🚀 Server Runner
# ═══════════════════════════════════════════════════════════════

def run_server(engine, host: str = "0.0.0.0", port: int = 7860, **kwargs):
    """Run the Rally Agent web server.

    Args:
        engine: The main Rally engine instance
        host: Bind address
        port: Bind port
    """
    app = create_app(engine)
    uvicorn.run(app, host=host, port=port, log_level="info", **kwargs)
