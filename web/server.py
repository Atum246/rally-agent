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
<title>⚡ Rally Agent</title>
<style>
/* ═══════ RESET & BASE ═══════ */
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg-900:#0a0a14;--bg-800:#0f0f1e;--bg-700:#151528;--bg-600:#1a1a35;
  --bg-500:#22224a;--bg-400:#2a2a55;--purple-500:#8b5cf6;--purple-400:#a78bfa;
  --purple-300:#c4b5fd;--purple-600:#7c3aed;--purple-700:#6d28d9;--purple-800:#5b21b6;
  --purple-glow:0 0 20px rgba(139,92,246,0.3),0 0 60px rgba(139,92,246,0.1);
  --green-500:#10b981;--green-400:#34d399;--red-500:#ef4444;--red-400:#f87171;
  --yellow-500:#eab308;--blue-500:#3b82f6;--cyan-500:#06b6d4;--text:#e2e8f0;
  --text-dim:#94a3b8;--text-muted:#64748b;--border:#2a2a55;--radius:12px;
  --font:'SF Mono','JetBrains Mono','Fira Code',monospace;
}
html{font-size:14px;scroll-behavior:smooth}
body{font-family:var(--font);background:var(--bg-900);color:var(--text);min-height:100vh;overflow:hidden}
a{color:var(--purple-400);text-decoration:none}
a:hover{color:var(--purple-300)}
button{font-family:var(--font);cursor:pointer;border:none;outline:none}
input,textarea,select{font-family:var(--font);outline:none}
::-webkit-scrollbar{width:6px;height:6px}
::-webkit-scrollbar-track{background:var(--bg-800)}
::-webkit-scrollbar-thumb{background:var(--bg-500);border-radius:3px}
::-webkit-scrollbar-thumb:hover{background:var(--purple-700)}

/* ═══════ LAYOUT ═══════ */
#app{display:flex;height:100vh}
#sidebar{width:240px;min-width:240px;background:var(--bg-800);border-right:1px solid var(--border);display:flex;flex-direction:column;z-index:100}
#main{flex:1;display:flex;flex-direction:column;overflow:hidden}

/* ═══════ SIDEBAR ═══════ */
.sidebar-header{padding:20px 16px 12px;border-bottom:1px solid var(--border)}
.sidebar-logo{display:flex;align-items:center;gap:10px;font-size:1.2rem;font-weight:700;color:var(--purple-400)}
.sidebar-logo .logo-icon{font-size:1.6rem}
.sidebar-nav{flex:1;overflow-y:auto;padding:8px}
.nav-item{display:flex;align-items:center;gap:10px;padding:10px 12px;border-radius:8px;color:var(--text-dim);font-size:0.92rem;transition:all .15s;cursor:pointer;margin-bottom:2px}
.nav-item:hover{background:var(--bg-600);color:var(--text)}
.nav-item.active{background:linear-gradient(135deg,var(--purple-800),var(--purple-700));color:#fff;box-shadow:var(--purple-glow)}
.nav-item .icon{font-size:1.1rem;width:24px;text-align:center}
.sidebar-footer{padding:12px 16px;border-top:1px solid var(--border);font-size:0.75rem;color:var(--text-muted);text-align:center}

/* ═══════ TOP BAR ═══════ */
.topbar{height:48px;background:var(--bg-800);border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;padding:0 20px}
.topbar-title{font-weight:600;color:var(--purple-300);font-size:1rem}
.topbar-status{display:flex;align-items:center;gap:16px;font-size:0.8rem;color:var(--text-dim)}
.status-dot{width:8px;height:8px;border-radius:50%;background:var(--green-500);display:inline-block;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.4}}

/* ═══════ PAGE CONTENT ═══════ */
.page{display:none;flex:1;overflow-y:auto;padding:24px}
.page.active{display:block}

/* ═══════ CARDS ═══════ */
.card{background:var(--bg-700);border:1px solid var(--border);border-radius:var(--radius);padding:20px;margin-bottom:16px;transition:border-color .2s}
.card:hover{border-color:var(--purple-700)}
.card-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px}
.card-title{font-weight:600;color:var(--purple-300);font-size:1rem}

/* ═══════ GRID ═══════ */
.grid-2{display:grid;grid-template-columns:repeat(2,1fr);gap:16px}
.grid-3{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}
.grid-4{display:grid;grid-template-columns:repeat(4,1fr);gap:16px}
@media(max-width:1200px){.grid-4{grid-template-columns:repeat(2,1fr)}}
@media(max-width:900px){.grid-3,.grid-2{grid-template-columns:1fr}}

/* ═══════ STAT CARDS ═══════ */
.stat-card{background:var(--bg-700);border:1px solid var(--border);border-radius:var(--radius);padding:16px;position:relative;overflow:hidden}
.stat-card::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:linear-gradient(90deg,var(--purple-500),var(--cyan-500))}
.stat-value{font-size:2rem;font-weight:700;color:var(--purple-300)}
.stat-label{font-size:0.8rem;color:var(--text-dim);margin-top:4px}

/* ═══════ BUTTONS ═══════ */
.btn{padding:8px 16px;border-radius:8px;font-size:0.85rem;font-weight:500;transition:all .15s;display:inline-flex;align-items:center;gap:6px}
.btn-primary{background:linear-gradient(135deg,var(--purple-600),var(--purple-500));color:#fff;box-shadow:0 2px 10px rgba(139,92,246,0.3)}
.btn-primary:hover{background:linear-gradient(135deg,var(--purple-500),var(--purple-400));transform:translateY(-1px)}
.btn-secondary{background:var(--bg-500);color:var(--text);border:1px solid var(--border)}
.btn-secondary:hover{border-color:var(--purple-600);background:var(--bg-400)}
.btn-danger{background:var(--red-500);color:#fff}
.btn-danger:hover{background:var(--red-400)}
.btn-sm{padding:5px 10px;font-size:0.78rem}
.btn-icon{width:32px;height:32px;border-radius:8px;background:var(--bg-500);border:1px solid var(--border);color:var(--text-dim);display:flex;align-items:center;justify-content:center}

/* ═══════ INPUTS ═══════ */
.input{width:100%;padding:10px 14px;background:var(--bg-800);border:1px solid var(--border);border-radius:8px;color:var(--text);font-size:0.9rem;transition:border-color .15s}
.input:focus{border-color:var(--purple-500);box-shadow:0 0 0 3px rgba(139,92,246,0.15)}
.input-group{margin-bottom:14px}
.input-label{display:block;font-size:0.8rem;color:var(--text-dim);margin-bottom:6px;font-weight:500}
textarea.input{min-height:100px;resize:vertical}

/* ═══════ TABLES ═══════ */
.table-wrap{overflow-x:auto}
table{width:100%;border-collapse:collapse}
th{text-align:left;padding:10px 12px;font-size:0.78rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.05em;border-bottom:1px solid var(--border)}
td{padding:10px 12px;font-size:0.85rem;border-bottom:1px solid rgba(42,42,85,0.5)}
tr:hover td{background:rgba(139,92,246,0.05)}

/* ═══════ BADGES ═══════ */
.badge{display:inline-flex;align-items:center;padding:2px 8px;border-radius:20px;font-size:0.72rem;font-weight:600}
.badge-green{background:rgba(16,185,129,0.15);color:var(--green-400)}
.badge-purple{background:rgba(139,92,246,0.15);color:var(--purple-400)}
.badge-red{background:rgba(239,68,68,0.15);color:var(--red-400)}
.badge-yellow{background:rgba(234,179,8,0.15);color:var(--yellow-500)}
.badge-blue{background:rgba(59,130,246,0.15);color:var(--blue-500)}

/* ═══════ CHAT PAGE ═══════ */
.chat-container{display:flex;flex-direction:column;height:calc(100vh - 48px)}
.chat-messages{flex:1;overflow-y:auto;padding:20px;display:flex;flex-direction:column;gap:16px}
.msg{max-width:80%;padding:12px 16px;border-radius:12px;font-size:0.9rem;line-height:1.6;word-wrap:break-word;white-space:pre-wrap}
.msg-user{align-self:flex-end;background:linear-gradient(135deg,var(--purple-700),var(--purple-600));color:#fff;border-bottom-right-radius:4px}
.msg-ai{align-self:flex-start;background:var(--bg-600);border:1px solid var(--border);border-bottom-left-radius:4px}
.msg-system{align-self:center;background:rgba(139,92,246,0.1);border:1px solid var(--purple-800);color:var(--text-dim);font-size:0.8rem}
.msg-tool{align-self:flex-start;background:var(--bg-700);border:1px solid var(--yellow-500);border-bottom-left-radius:4px;font-size:0.82rem}
.msg-tool .tool-name{color:var(--yellow-500);font-weight:600;margin-bottom:4px}
.chat-input-area{padding:16px 20px;border-top:1px solid var(--border);background:var(--bg-800)}
.chat-input-row{display:flex;gap:10px}
.chat-input{flex:1;padding:12px 16px;background:var(--bg-700);border:1px solid var(--border);border-radius:12px;color:var(--text);font-size:0.95rem;resize:none;min-height:48px;max-height:120px}
.chat-input:focus{border-color:var(--purple-500);box-shadow:var(--purple-glow)}
.send-btn{width:48px;height:48px;border-radius:12px;background:linear-gradient(135deg,var(--purple-600),var(--purple-500));color:#fff;font-size:1.2rem;display:flex;align-items:center;justify-content:center;transition:all .15s;box-shadow:0 2px 10px rgba(139,92,246,0.3)}
.send-btn:hover{transform:scale(1.05)}
.send-btn:disabled{opacity:0.4;cursor:not-allowed;transform:none}
.typing-indicator{display:flex;align-items:center;gap:6px;color:var(--text-dim);font-size:0.82rem;padding:4px 0}
.typing-dot{width:6px;height:6px;border-radius:50%;background:var(--purple-400);animation:typingBounce 1.4s infinite}
.typing-dot:nth-child(2){animation-delay:.2s}
.typing-dot:nth-child(3){animation-delay:.4s}
@keyframes typingBounce{0%,60%,100%{transform:translateY(0)}30%{transform:translateY(-6px)}}

/* ═══════ AGENT CARDS ═══════ */
.agent-card{background:var(--bg-700);border:1px solid var(--border);border-radius:var(--radius);padding:16px;transition:all .2s;cursor:pointer}
.agent-card:hover{border-color:var(--purple-500);transform:translateY(-2px);box-shadow:var(--purple-glow)}
.agent-name{font-weight:600;color:var(--purple-300);margin-bottom:4px}
.agent-type{font-size:0.75rem;color:var(--text-muted);margin-bottom:8px}
.agent-caps{display:flex;flex-wrap:wrap;gap:4px}
.agent-cap{font-size:0.68rem;padding:2px 6px;background:var(--bg-500);border-radius:4px;color:var(--text-dim)}

/* ═══════ PROGRESS BAR ═══════ */
.progress-bar{height:6px;background:var(--bg-500);border-radius:3px;overflow:hidden}
.progress-fill{height:100%;background:linear-gradient(90deg,var(--purple-500),var(--cyan-500));border-radius:3px;transition:width .5s}

/* ═══════ CODE BLOCK ═══════ */
.code-block{background:var(--bg-900);border:1px solid var(--border);border-radius:8px;padding:12px;font-size:0.82rem;overflow-x:auto;line-height:1.5}

/* ═══════ METRIC CHART PLACEHOLDER ═══════ */
.chart-container{height:200px;background:var(--bg-800);border:1px solid var(--border);border-radius:8px;display:flex;align-items:center;justify-content:center;color:var(--text-muted);font-size:0.85rem;position:relative;overflow:hidden}
.chart-container canvas{position:absolute;top:0;left:0;width:100%;height:100%}

/* ═══════ MODAL ═══════ */
.modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,0.7);z-index:1000;display:flex;align-items:center;justify-content:center}
.modal{background:var(--bg-700);border:1px solid var(--border);border-radius:16px;padding:24px;max-width:500px;width:90%;max-height:80vh;overflow-y:auto;box-shadow:0 20px 60px rgba(0,0,0,0.5)}
.modal-title{font-size:1.1rem;font-weight:600;color:var(--purple-300);margin-bottom:16px}
.modal-actions{display:flex;justify-content:flex-end;gap:8px;margin-top:16px}

/* ═══════ LOGIN PAGE ═══════ */
.login-container{min-height:100vh;display:flex;align-items:center;justify-content:center;background:radial-gradient(ellipse at center,var(--bg-700) 0%,var(--bg-900) 70%)}
.login-box{background:var(--bg-700);border:1px solid var(--border);border-radius:20px;padding:40px;width:380px;box-shadow:var(--purple-glow);text-align:center}
.login-box h1{color:var(--purple-400);margin-bottom:8px;font-size:1.8rem}
.login-box p{color:var(--text-dim);margin-bottom:24px;font-size:0.85rem}
.login-box .input{margin-bottom:14px;text-align:left}
.login-box .btn{width:100%;justify-content:center;padding:12px;font-size:1rem;margin-top:8px}
.login-error{color:var(--red-400);font-size:0.82rem;margin-top:8px;min-height:20px}
.login-toggle{margin-top:16px;font-size:0.82rem;color:var(--text-dim)}
.login-toggle a{cursor:pointer}

/* ═══════ SECURITY AUDIT LOG ═══════ */
.log-entry{padding:8px 12px;border-left:3px solid var(--purple-700);margin-bottom:8px;font-size:0.82rem;background:var(--bg-800);border-radius:0 6px 6px 0}
.log-time{color:var(--text-muted);font-size:0.72rem}

/* ═══════ FILE MANAGER ═══════ */
.file-item{display:flex;align-items:center;gap:12px;padding:10px 12px;border-radius:8px;cursor:pointer;transition:background .1s}
.file-item:hover{background:var(--bg-600)}
.file-icon{font-size:1.3rem;width:32px;text-align:center}
.file-name{flex:1;font-size:0.88rem}
.file-size{font-size:0.75rem;color:var(--text-muted)}

/* ═══════ SETTINGS EDITOR ═══════ */
.config-editor{width:100%;min-height:400px;background:var(--bg-900);border:1px solid var(--border);border-radius:8px;padding:16px;color:var(--green-400);font-family:var(--font);font-size:0.85rem;resize:vertical;line-height:1.6}

/* ═══════ ANIMATIONS ═══════ */
@keyframes fadeIn{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}
.fade-in{animation:fadeIn .3s ease}
@keyframes slideIn{from{opacity:0;transform:translateX(-20px)}to{opacity:1;transform:translateX(0)}}

/* ═══════ TOAST ═══════ */
.toast-container{position:fixed;top:16px;right:16px;z-index:2000;display:flex;flex-direction:column;gap:8px}
.toast{padding:12px 20px;border-radius:10px;font-size:0.85rem;color:#fff;animation:fadeIn .3s;box-shadow:0 4px 20px rgba(0,0,0,0.3)}
.toast-success{background:linear-gradient(135deg,#059669,var(--green-500))}
.toast-error{background:linear-gradient(135deg,#dc2626,var(--red-500))}
.toast-info{background:linear-gradient(135deg,var(--purple-600),var(--purple-500))}
</style>
</head>
<body>

<!-- ONBOARDING WIZARD -->
<div id="onboardingPage" style="display:none">
<style>
.onboarding-overlay{position:fixed;inset:0;background:radial-gradient(ellipse at center,var(--bg-700) 0%,var(--bg-900) 70%);z-index:5000;display:flex;align-items:center;justify-content:center;overflow-y:auto}
.onboarding-card{background:var(--bg-700);border:1px solid var(--border);border-radius:24px;padding:0;max-width:640px;width:94%;max-height:90vh;overflow-y:auto;box-shadow:var(--purple-glow)}
.onboarding-header{text-align:center;padding:32px 32px 16px;background:linear-gradient(135deg,rgba(139,92,246,0.15),rgba(6,182,212,0.08));border-radius:24px 24px 0 0}
.onboarding-header h1{font-size:2rem;color:var(--purple-300);margin-bottom:8px}
.onboarding-header p{color:var(--text-dim);font-size:0.92rem}
.onboarding-body{padding:24px 32px 32px}
.onboarding-steps{display:flex;justify-content:center;gap:8px;margin-bottom:24px}
.onboarding-dot{width:10px;height:10px;border-radius:50%;background:var(--bg-500);transition:all .3s}
.onboarding-dot.active{background:var(--purple-500);box-shadow:0 0 8px rgba(139,92,246,0.5);transform:scale(1.2)}
.onboarding-dot.done{background:var(--green-500)}
.ob-section{margin-bottom:20px}
.ob-section h3{color:var(--purple-300);font-size:1.1rem;margin-bottom:12px}
.ob-provider-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}
.ob-provider{background:var(--bg-800);border:2px solid var(--border);border-radius:12px;padding:14px;cursor:pointer;transition:all .2s;display:flex;align-items:center;gap:12px}
.ob-provider:hover{border-color:var(--purple-600);transform:translateY(-2px)}
.ob-provider.selected{border-color:var(--purple-500);background:rgba(139,92,246,0.1);box-shadow:var(--purple-glow)}
.ob-provider .icon{font-size:1.6rem}
.ob-provider .name{font-weight:600;color:var(--text);font-size:0.92rem}
.ob-provider .desc{font-size:0.75rem;color:var(--text-dim);margin-top:2px}
.ob-provider .key-badge{font-size:0.68rem;padding:2px 6px;border-radius:4px;margin-left:auto}
.ob-provider .key-badge.needs-key{background:rgba(234,179,8,0.15);color:var(--yellow-500)}
.ob-provider .key-badge.no-key{background:rgba(16,185,129,0.15);color:var(--green-400)}
.ob-guide-box{background:var(--bg-800);border:1px solid var(--border);border-radius:12px;padding:16px;margin-bottom:16px;font-size:0.85rem;line-height:1.8;white-space:pre-wrap;color:var(--text-dim)}
.ob-guide-box a{color:var(--purple-400)}
.ob-model-list{display:flex;flex-wrap:wrap;gap:8px}
.ob-model{padding:8px 14px;background:var(--bg-800);border:2px solid var(--border);border-radius:10px;cursor:pointer;transition:all .15s;font-size:0.82rem;color:var(--text-dim)}
.ob-model:hover{border-color:var(--purple-600);color:var(--text)}
.ob-model.selected{border-color:var(--purple-500);color:var(--purple-300);background:rgba(139,92,246,0.1)}
.ob-model.default::after{content:' ⭐';font-size:0.7rem}
.ob-actions{display:flex;justify-content:space-between;align-items:center;margin-top:24px}
.ob-success{text-align:center;padding:32px}
.ob-success .checkmark{font-size:4rem;margin-bottom:16px}
.ob-success h2{color:var(--green-400);margin-bottom:8px}
.ob-success p{color:var(--text-dim);font-size:0.92rem}
@media(max-width:600px){.ob-provider-grid{grid-template-columns:1fr}.onboarding-card{width:98%;border-radius:16px}.onboarding-body{padding:16px}}
</style>
<div class="onboarding-overlay">
<div class="onboarding-card">
<div class="onboarding-header">
  <h1>⚡ Rally Agent</h1>
  <p>Set up your AI platform in under 2 minutes</p>
</div>
<div class="onboarding-body">
  <div class="onboarding-steps" id="obSteps"></div>
  <div id="obContent"></div>
  <div class="ob-actions">
    <button class="btn btn-secondary" id="obBack" onclick="obPrev()" style="display:none">← Back</button>
    <div></div>
    <button class="btn btn-primary" id="obNext" onclick="obNext()">Next →</button>
  </div>
</div>
</div>
</div>
</div>

<!-- LOGIN PAGE -->
<div id="loginPage" class="login-container">
  <div class="login-box">
    <h1>⚡ Rally Agent</h1>
    <p>Self-hosted AI platform</p>
    <input type="text" id="loginUser" class="input" placeholder="Username" autocomplete="username">
    <input type="password" id="loginPass" class="input" placeholder="Password" autocomplete="current-password">
    <button class="btn btn-primary" onclick="doLogin()">Sign In</button>
    <div id="loginError" class="login-error"></div>
    <div class="login-toggle">No account? <a onclick="showRegister()">Register</a></div>
  </div>
</div>

<!-- MAIN APP -->
<div id="app" style="display:none">
  <!-- SIDEBAR -->
  <div id="sidebar">
    <div class="sidebar-header">
      <div class="sidebar-logo"><span class="logo-icon">⚡</span> Rally Agent</div>
    </div>
    <nav class="sidebar-nav">
      <div class="nav-item active" data-page="chat" onclick="showPage('chat')"><span class="icon">💬</span> Chat</div>
      <div class="nav-item" data-page="dashboard" onclick="showPage('dashboard')"><span class="icon">📊</span> Dashboard</div>
      <div class="nav-item" data-page="agents" onclick="showPage('agents')"><span class="icon">🤖</span> Agents</div>
      <div class="nav-item" data-page="memory" onclick="showPage('memory')"><span class="icon">🧠</span> Memory</div>
      <div class="nav-item" data-page="browser" onclick="showPage('browser')"><span class="icon">🌐</span> Browser</div>
      <div class="nav-item" data-page="plugins" onclick="showPage('plugins')"><span class="icon">🔌</span> Plugins</div>
      <div class="nav-item" data-page="tools" onclick="showPage('tools')"><span class="icon">🛠️</span> Tools</div>
      <div class="nav-item" data-page="automation" onclick="showPage('automation')"><span class="icon">⏰</span> Automation</div>
      <div class="nav-item" data-page="knowledge" onclick="showPage('knowledge')"><span class="icon">🕸️</span> Knowledge</div>
      <div class="nav-item" data-page="workflows" onclick="showPage('workflows')"><span class="icon">🔄</span> Workflows</div>
      <div class="nav-item" data-page="improvement" onclick="showPage('improvement')"><span class="icon">📈</span> Improvement</div>
      <div class="nav-item" data-page="computer" onclick="showPage('computer')"><span class="icon">🖥️</span> Computer</div>
      <div class="nav-item" data-page="system" onclick="showPage('system')"><span class="icon">🔧</span> System</div>
      <div class="nav-item" data-page="profile" onclick="showPage('profile')"><span class="icon">👤</span> Profile</div>
      <div class="nav-item" data-page="files" onclick="showPage('files')"><span class="icon">📁</span> Files</div>
      <div class="nav-item" data-page="metrics" onclick="showPage('metrics')"><span class="icon">📈</span> Metrics</div>
      <div class="nav-item" data-page="security" onclick="showPage('security')"><span class="icon">🔒</span> Security</div>
      <div class="nav-item" data-page="users" onclick="showPage('users')"><span class="icon">👥</span> Users</div>
      <div class="nav-item" data-page="settings" onclick="showPage('settings')"><span class="icon">⚙️</span> Settings</div>
    </nav>
    <div class="sidebar-footer">Rally Agent v2.0 — 🟣 Self-Hosted AI</div>
  </div>

  <!-- MAIN -->
  <div id="main">
    <div class="topbar">
      <div class="topbar-title" id="pageTitle">💬 Chat</div>
      <div class="topbar-status">
        <span><span class="status-dot"></span> Connected</span>
        <span id="topbarUser">admin</span>
      </div>
    </div>

    <!-- ═══════ CHAT PAGE ═══════ -->
    <div id="page-chat" class="page active chat-container">
      <div class="chat-messages" id="chatMessages"></div>
      <div id="typingIndicator" class="typing-indicator" style="display:none;padding:0 20px">
        <span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span>
        <span>Thinking...</span>
      </div>
      <div class="chat-input-area">
        <div class="chat-input-row">
          <textarea id="chatInput" class="chat-input" placeholder="Type a message... (Shift+Enter for new line)" rows="1"></textarea>
          <button id="sendBtn" class="send-btn" onclick="sendMessage()">➤</button>
        </div>
      </div>
    </div>

    <!-- ═══════ DASHBOARD PAGE ═══════ -->
    <div id="page-dashboard" class="page">
      <div class="grid-4" id="dashStats"></div>
      <div class="grid-2" style="margin-top:16px">
        <div class="card">
          <div class="card-header"><span class="card-title">Request Rate</span></div>
          <div class="chart-container"><canvas id="chartRequests"></canvas></div>
        </div>
        <div class="card">
          <div class="card-header"><span class="card-title">Latency (ms)</span></div>
          <div class="chart-container"><canvas id="chartLatency"></canvas></div>
        </div>
      </div>
      <div class="card" style="margin-top:16px">
        <div class="card-header"><span class="card-title">System Status</span></div>
        <div id="dashSystemInfo" style="font-size:0.85rem;color:var(--text-dim)"></div>
      </div>
    </div>

    <!-- ═══════ AGENTS PAGE ═══════ -->
    <div id="page-agents" class="page">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
        <h2 style="font-size:1.2rem;color:var(--purple-300)">🤖 Agents</h2>
        <button class="btn btn-primary" onclick="spawnAgentModal()">+ Spawn Agent</button>
      </div>
      <div class="grid-3" id="agentGrid"></div>
    </div>

    <!-- ═══════ MEMORY PAGE ═══════ -->
    <div id="page-memory" class="page">
      <div class="grid-2">
        <div class="card">
          <div class="card-header"><span class="card-title">🧠 Memory Stats</span></div>
          <div id="memoryStats"></div>
        </div>
        <div class="card">
          <div class="card-header"><span class="card-title">🔍 Semantic Search</span></div>
          <div class="input-group">
            <input id="memorySearchInput" class="input" placeholder="Search memory..." onkeydown="if(event.key==='Enter')searchMemory()">
            <button class="btn btn-primary btn-sm" style="margin-top:8px" onclick="searchMemory()">Search</button>
          </div>
          <div id="memorySearchResults"></div>
        </div>
      </div>
      <div class="card" style="margin-top:16px">
        <div class="card-header"><span class="card-title">📄 RAG — Ingest Documents</span></div>
        <div class="input-group">
          <textarea id="ragContent" class="input" placeholder="Paste document content to ingest..." rows="4"></textarea>
          <button class="btn btn-primary btn-sm" style="margin-top:8px" onclick="ingestRAG()">Ingest</button>
        </div>
      </div>
      <div class="card" style="margin-top:16px">
        <div class="card-header"><span class="card-title">🔎 RAG Search</span></div>
        <div class="input-group">
          <input id="ragSearchInput" class="input" placeholder="Search ingested documents..." onkeydown="if(event.key==='Enter')searchRAG()">
          <button class="btn btn-primary btn-sm" style="margin-top:8px" onclick="searchRAG()">Search RAG</button>
        </div>
        <div id="ragSearchResults"></div>
      </div>
    </div>

    <!-- ═══════ BROWSER PAGE ═══════ -->
    <div id="page-browser" class="page">
      <div class="card">
        <div class="card-header"><span class="card-title">🌐 Browser Automation</span></div>
        <div style="display:flex;gap:10px;margin-bottom:12px">
          <input id="browserUrl" class="input" placeholder="https://example.com" style="flex:1">
          <button class="btn btn-primary" onclick="browserNavigate()">Navigate</button>
          <button class="btn btn-secondary" onclick="browserScreenshot()">📸 Screenshot</button>
        </div>
        <div id="browserPreview" style="background:var(--bg-900);border:1px solid var(--border);border-radius:8px;min-height:300px;display:flex;align-items:center;justify-content:center;color:var(--text-muted);overflow:auto">
          <span>No page loaded</span>
        </div>
      </div>
      <div class="card" style="margin-top:16px">
        <div class="card-header"><span class="card-title">🎯 Element Actions</span></div>
        <div class="grid-2">
          <div class="input-group">
            <label class="input-label">Selector</label>
            <input id="browserSelector" class="input" placeholder="#element or .class">
          </div>
          <div class="input-group">
            <label class="input-label">Text (for type action)</label>
            <input id="browserText" class="input" placeholder="Text to type">
          </div>
        </div>
        <div style="display:flex;gap:8px">
          <button class="btn btn-secondary" onclick="browserClick()">🖱️ Click</button>
          <button class="btn btn-secondary" onclick="browserType()">⌨️ Type</button>
        </div>
        <div id="browserLog" style="margin-top:12px;font-size:0.82rem;color:var(--text-dim)"></div>
      </div>
    </div>

    <!-- ═══════ PLUGINS PAGE ═══════ -->
    <div id="page-plugins" class="page">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
        <h2 style="font-size:1.2rem;color:var(--purple-300)">🔌 Plugins</h2>
        <div style="display:flex;gap:8px">
          <input id="pluginInstallInput" class="input" placeholder="plugin-name" style="width:200px">
          <button class="btn btn-primary" onclick="installPlugin()">Install</button>
        </div>
      </div>
      <div class="grid-3" id="pluginGrid"></div>
    </div>

    <!-- ═══════ TOOLS PAGE ═══════ -->
    <div id="page-tools" class="page">
      <h2 style="font-size:1.2rem;color:var(--purple-300);margin-bottom:16px">🛠️ Tools Registry</h2>
      <div class="card">
        <div class="table-wrap">
          <table id="toolsTable">
            <thead><tr><th>Name</th><th>Description</th><th>Schema</th><th>Status</th><th>Actions</th></tr></thead>
            <tbody id="toolsBody"></tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- ═══════ FILES PAGE ═══════ -->
    <div id="page-files" class="page">
      <h2 style="font-size:1.2rem;color:var(--purple-300);margin-bottom:16px">📁 File Manager</h2>
      <div class="card">
        <div id="fileList"></div>
      </div>
    </div>

    <!-- ═══════ METRICS PAGE ═══════ -->
    <div id="page-metrics" class="page">
      <h2 style="font-size:1.2rem;color:var(--purple-300);margin-bottom:16px">📈 Metrics Dashboard</h2>
      <div class="grid-4" id="metricsStats"></div>
      <div class="grid-2" style="margin-top:16px">
        <div class="card">
          <div class="card-header"><span class="card-title">Throughput</span></div>
          <div class="chart-container"><canvas id="chartThroughput"></canvas></div>
        </div>
        <div class="card">
          <div class="card-header"><span class="card-title">Error Rate</span></div>
          <div class="chart-container"><canvas id="chartErrors"></canvas></div>
        </div>
      </div>
      <div class="card" style="margin-top:16px">
        <div class="card-header"><span class="card-title">Detailed Metrics</span></div>
        <div id="metricsDetail" style="font-size:0.82rem;color:var(--text-dim)"></div>
      </div>
    </div>

    <!-- ═══════ SECURITY PAGE ═══════ -->
    <div id="page-security" class="page">
      <h2 style="font-size:1.2rem;color:var(--purple-300);margin-bottom:16px">🔒 Security Status</h2>
      <div class="grid-3" id="securityStats"></div>
      <div class="card" style="margin-top:16px">
        <div class="card-header"><span class="card-title">Audit Log</span></div>
        <div id="auditLog"></div>
      </div>
    </div>

    <!-- ═══════ USERS PAGE ═══════ -->
    <div id="page-users" class="page">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
        <h2 style="font-size:1.2rem;color:var(--purple-300)">👥 User Management</h2>
        <button class="btn btn-primary" onclick="showAddUserModal()">+ Add User</button>
      </div>
      <div class="card">
        <div class="table-wrap">
          <table>
            <thead><tr><th>Username</th><th>Role</th><th>Created</th><th>Status</th><th>Actions</th></tr></thead>
            <tbody id="usersBody"></tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- ═══════ SETTINGS PAGE ═══════ -->
    <div id="page-settings" class="page">
      <h2 style="font-size:1.2rem;color:var(--purple-300);margin-bottom:16px">⚙️ Configuration</h2>
      <div class="card">
        <div class="card-header">
          <span class="card-title">Config Editor</span>
          <button class="btn btn-primary btn-sm" onclick="saveConfig()">💾 Save</button>
        </div>
        <textarea id="configEditor" class="config-editor" spellcheck="false"></textarea>
      </div>
      <div class="card" style="margin-top:16px">
        <div class="card-header"><span class="card-title">Provider Status</span></div>
        <div id="providerList"></div>
      </div>
      <div class="card" style="margin-top:16px">
        <div class="card-header"><span class="card-title">Channels</span></div>
        <div id="channelList"></div>
      </div>
    </div>

    <!-- ═══════ AUTOMATION PAGE ═══════ -->
    <div id="page-automation" class="page">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
        <h2 style="font-size:1.2rem;color:var(--purple-300)">⏰ Automation / Cron Jobs</h2>
        <button class="btn btn-primary" onclick="showAddJobModal()">+ Add Job</button>
      </div>
      <div class="card">
        <div class="card-header"><span class="card-title">Scheduled Jobs</span></div>
        <div class="table-wrap">
          <table>
            <thead><tr><th>Name</th><th>Schedule</th><th>Type</th><th>Last Run</th><th>Runs</th><th>Status</th><th>Actions</th></tr></thead>
            <tbody id="automationJobsBody"></tbody>
          </table>
        </div>
      </div>
      <div class="card" style="margin-top:16px">
        <div class="card-header"><span class="card-title">Run History</span></div>
        <div id="automationHistory"></div>
      </div>
    </div>

    <!-- ═══════ KNOWLEDGE PAGE ═══════ -->
    <div id="page-knowledge" class="page">
      <div class="grid-2">
        <div class="card">
          <div class="card-header"><span class="card-title">🕸️ Knowledge Graph Stats</span></div>
          <div id="knowledgeStats"></div>
        </div>
        <div class="card">
          <div class="card-header"><span class="card-title">🔍 Search Knowledge</span></div>
          <div class="input-group">
            <input id="knowledgeSearchInput" class="input" placeholder="Search entities..." onkeydown="if(event.key==='Enter')searchKnowledge()">
            <button class="btn btn-primary btn-sm" style="margin-top:8px" onclick="searchKnowledge()">Search</button>
          </div>
          <div id="knowledgeSearchResults"></div>
        </div>
      </div>
    </div>

    <!-- ═══════ WORKFLOWS PAGE ═══════ -->
    <div id="page-workflows" class="page">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
        <h2 style="font-size:1.2rem;color:var(--purple-300)">🔄 Workflows</h2>
        <div style="display:flex;gap:8px">
          <button class="btn btn-primary" onclick="startRecording()">⏺ Record</button>
          <button class="btn btn-secondary" onclick="stopRecording()">⏹ Stop</button>
        </div>
      </div>
      <div class="card">
        <div class="card-header"><span class="card-title">Saved Workflows</span></div>
        <div class="table-wrap">
          <table>
            <thead><tr><th>Name</th><th>Steps</th><th>Created</th><th>Replays</th><th>Actions</th></tr></thead>
            <tbody id="workflowsBody"></tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- ═══════ IMPROVEMENT PAGE ═══════ -->
    <div id="page-improvement" class="page">
      <h2 style="font-size:1.2rem;color:var(--purple-300);margin-bottom:16px">📈 Self-Improvement</h2>
      <div class="grid-4" id="improvementStats"></div>
      <div class="grid-2" style="margin-top:16px">
        <div class="card">
          <div class="card-header"><span class="card-title">Top Errors</span></div>
          <div id="improvementErrors"></div>
        </div>
        <div class="card">
          <div class="card-header"><span class="card-title">Recent Learnings</span></div>
          <div id="improvementLearnings"></div>
        </div>
      </div>
    </div>

    <!-- ═══════ COMPUTER USE PAGE ═══════ -->
    <div id="page-computer" class="page">
      <h2 style="font-size:1.2rem;color:var(--purple-300);margin-bottom:16px">🖥️ Computer Use</h2>
      <div class="grid-2">
        <div class="card">
          <div class="card-header"><span class="card-title">📸 Screenshot</span></div>
          <button class="btn btn-primary" onclick="takeScreenshot()">Take Screenshot</button>
          <div id="screenshotPreview" style="margin-top:12px;min-height:200px;background:var(--bg-800);border:1px solid var(--border);border-radius:8px;display:flex;align-items:center;justify-content:center;color:var(--text-muted)">
            <span>No screenshot yet</span>
          </div>
        </div>
        <div class="card">
          <div class="card-header"><span class="card-title">🖱️ Mouse & Keyboard</span></div>
          <div class="grid-2">
            <div class="input-group">
              <label class="input-label">X Coordinate</label>
              <input id="clickX" class="input" type="number" placeholder="0">
            </div>
            <div class="input-group">
              <label class="input-label">Y Coordinate</label>
              <input id="clickY" class="input" type="number" placeholder="0">
            </div>
          </div>
          <button class="btn btn-secondary" onclick="computerClick()" style="margin-bottom:12px">🖱️ Click</button>
          <div class="input-group">
            <label class="input-label">Text to Type</label>
            <input id="typeText" class="input" placeholder="Hello world">
          </div>
          <button class="btn btn-secondary" onclick="computerType()">⌨️ Type</button>
          <div id="computerLog" style="margin-top:12px;font-size:0.82rem;color:var(--text-dim)"></div>
        </div>
      </div>
    </div>

    <!-- ═══════ SYSTEM PAGE ═══════ -->
    <div id="page-system" class="page">
      <h2 style="font-size:1.2rem;color:var(--purple-300);margin-bottom:16px">🔧 System Info</h2>
      <div class="grid-4" id="systemStats"></div>
      <div class="card" style="margin-top:16px">
        <div class="card-header">
          <span class="card-title">System Details</span>
          <button class="btn btn-primary btn-sm" onclick="checkUpdates()">🔄 Check Updates</button>
        </div>
        <div id="systemDetails" style="font-size:0.85rem;color:var(--text-dim)"></div>
      </div>
    </div>

    <!-- ═══════ PROFILE PAGE ═══════ -->
    <div id="page-profile" class="page">
      <h2 style="font-size:1.2rem;color:var(--purple-300);margin-bottom:16px">👤 User Profile</h2>
      <div class="grid-2">
        <div class="card">
          <div class="card-header"><span class="card-title">Profile Summary</span></div>
          <div id="profileSummary" style="white-space:pre-wrap;font-size:0.85rem;color:var(--text-dim)"></div>
        </div>
        <div class="card">
          <div class="card-header"><span class="card-title">Edit Profile</span></div>
          <div class="input-group">
            <label class="input-label">Name</label>
            <input id="profileName" class="input" placeholder="Your name">
          </div>
          <div class="input-group">
            <label class="input-label">Timezone</label>
            <input id="profileTimezone" class="input" placeholder="UTC+8">
          </div>
          <button class="btn btn-primary" onclick="saveProfile()">💾 Save Profile</button>
        </div>
      </div>
    </div>
  </div>
</div>

<!-- TOAST CONTAINER -->
<div id="toastContainer" class="toast-container"></div>

<!-- MODAL CONTAINER -->
<div id="modalContainer"></div>

<script>
// ═══════════════════════════════════════════════════════════════
// 🔑 Auth State
// ═══════════════════════════════════════════════════════════════
let authToken = localStorage.getItem('rally_token') || '';
let currentUser = null;

function api(path, opts = {}) {
  const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
  if (authToken) headers['Authorization'] = 'Bearer ' + authToken;
  return fetch('/api' + path, { ...opts, headers }).then(async r => {
    if (r.status === 401) { doLogout(); throw new Error('Unauthorized'); }
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.detail || data.error || r.statusText);
    return data;
  });
}

function doLogout() {
  authToken = ''; localStorage.removeItem('rally_token');
  document.getElementById('app').style.display = 'none';
  document.getElementById('loginPage').style.display = 'flex';
}

async function doLogin() {
  const user = document.getElementById('loginUser').value.trim();
  const pass = document.getElementById('loginPass').value;
  if (!user || !pass) { document.getElementById('loginError').textContent = 'Fill in all fields'; return; }
  try {
    const data = await fetch('/api/auth/login', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: user, password: pass })
    }).then(r => r.json());
    if (data.error) { document.getElementById('loginError').textContent = data.error; return; }
    authToken = data.token; localStorage.setItem('rally_token', authToken);
    currentUser = data.user || user;
    enterApp();
  } catch (e) { document.getElementById('loginError').textContent = 'Login failed: ' + e.message; }
}

function showRegister() {
  const box = document.querySelector('.login-box');
  box.querySelector('h1').textContent = '📝 Register';
  box.querySelector('p').textContent = 'Create a new account';
  box.querySelector('.btn').textContent = 'Create Account';
  box.querySelector('.btn').onclick = doRegister;
  box.querySelector('.login-toggle').innerHTML = 'Already have an account? <a onclick="location.reload()">Sign in</a>';
}

async function doRegister() {
  const user = document.getElementById('loginUser').value.trim();
  const pass = document.getElementById('loginPass').value;
  if (!user || !pass) { document.getElementById('loginError').textContent = 'Fill in all fields'; return; }
  try {
    const data = await fetch('/api/auth/register', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: user, password: pass })
    }).then(r => r.json());
    if (data.error) { document.getElementById('loginError').textContent = data.error; return; }
    authToken = data.token; localStorage.setItem('rally_token', authToken);
    currentUser = user;
    enterApp();
  } catch (e) { document.getElementById('loginError').textContent = 'Registration failed: ' + e.message; }
}

function enterApp() {
  document.getElementById('loginPage').style.display = 'none';
  document.getElementById('app').style.display = 'flex';
  document.getElementById('topbarUser').textContent = currentUser || 'user';
  loadAllPages();
  connectWS();
}

// ═══════════════════════════════════════════════════════════════
// 🔌 WebSocket
// ═══════════════════════════════════════════════════════════════
let ws = null;
let wsReconnectTimer = null;

function connectWS() {
  if (ws && ws.readyState <= 1) return;
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(`${proto}://${location.host}/ws?token=${encodeURIComponent(authToken)}`);
  ws.onopen = () => { clearTimeout(wsReconnectTimer); };
  ws.onclose = () => { wsReconnectTimer = setTimeout(connectWS, 3000); };
  ws.onerror = () => {};
  ws.onmessage = (evt) => {
    try {
      const msg = JSON.parse(evt.data);
      handleWSMessage(msg);
    } catch (e) {}
  };
}

let currentAIMsg = null;
let isStreaming = false;

function handleWSMessage(msg) {
  if (msg.type === 'token') {
    if (!currentAIMsg) {
      currentAIMsg = appendMsg('', 'ai');
      document.getElementById('typingIndicator').style.display = 'none';
    }
    currentAIMsg.querySelector('.msg-content').textContent += msg.content;
    scrollChat();
  } else if (msg.type === 'done') {
    if (currentAIMsg && msg.content) {
      currentAIMsg.querySelector('.msg-content').textContent += msg.content;
    }
    currentAIMsg = null;
    isStreaming = false;
    document.getElementById('sendBtn').disabled = false;
    document.getElementById('typingIndicator').style.display = 'none';
    scrollChat();
  } else if (msg.type === 'tool_call') {
    appendToolMsg(`🔧 Calling: ${msg.tool}`, JSON.stringify(msg.args, null, 2));
  } else if (msg.type === 'tool_result') {
    appendToolMsg(`✅ Result: ${msg.tool}`, typeof msg.result === 'string' ? msg.result : JSON.stringify(msg.result, null, 2));
  } else if (msg.type === 'error') {
    appendMsg('⚠️ ' + msg.content, 'system');
    isStreaming = false;
    document.getElementById('sendBtn').disabled = false;
    document.getElementById('typingIndicator').style.display = 'none';
  }
}

function appendMsg(text, type) {
  const div = document.createElement('div');
  div.className = `msg msg-${type} fade-in`;
  div.innerHTML = `<div class="msg-content">${escHtml(text)}</div>`;
  document.getElementById('chatMessages').appendChild(div);
  scrollChat();
  return div;
}

function appendToolMsg(title, body) {
  const div = document.createElement('div');
  div.className = 'msg msg-tool fade-in';
  div.innerHTML = `<div class="tool-name">${escHtml(title)}</div><div class="code-block">${escHtml(body)}</div>`;
  document.getElementById('chatMessages').appendChild(div);
  scrollChat();
}

function scrollChat() {
  const m = document.getElementById('chatMessages');
  m.scrollTop = m.scrollHeight;
}

function escHtml(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

function sendMessage() {
  const input = document.getElementById('chatInput');
  const text = input.value.trim();
  if (!text || isStreaming) return;
  appendMsg(text, 'user');
  input.value = '';
  input.style.height = 'auto';
  isStreaming = true;
  document.getElementById('sendBtn').disabled = true;
  document.getElementById('typingIndicator').style.display = 'flex';
  if (ws && ws.readyState === 1) {
    ws.send(JSON.stringify({ type: 'chat', content: text }));
  } else {
    // Fallback to SSE
    streamChatSSE(text);
  }
}

async function streamChatSSE(text) {
  try {
    const resp = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + authToken },
      body: JSON.stringify({ content: text })
    });
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let aiDiv = null;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const chunk = decoder.decode(value);
      for (const line of chunk.split('\n')) {
        if (!line.startsWith('data: ')) continue;
        const data = JSON.parse(line.slice(6));
        if (data.type === 'token') {
          if (!aiDiv) { aiDiv = appendMsg('', 'ai'); document.getElementById('typingIndicator').style.display = 'none'; }
          aiDiv.querySelector('.msg-content').textContent += data.content;
        } else if (data.type === 'done') {
          if (aiDiv && data.content) aiDiv.querySelector('.msg-content').textContent += data.content;
        }
      }
      scrollChat();
    }
  } catch (e) {
    appendMsg('⚠️ Error: ' + e.message, 'system');
  } finally {
    isStreaming = false; currentAIMsg = null;
    document.getElementById('sendBtn').disabled = false;
    document.getElementById('typingIndicator').style.display = 'none';
  }
}

// Auto-resize textarea
document.getElementById('chatInput').addEventListener('input', function() {
  this.style.height = 'auto';
  this.style.height = Math.min(this.scrollHeight, 120) + 'px';
});
document.getElementById('chatInput').addEventListener('keydown', function(e) {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
});

// ═══════════════════════════════════════════════════════════════
// 📄 Page Navigation
// ═══════════════════════════════════════════════════════════════
const pageTitles = {
  chat:'💬 Chat', dashboard:'📊 Dashboard', agents:'🤖 Agents', memory:'🧠 Memory',
  browser:'🌐 Browser', plugins:'🔌 Plugins', tools:'🛠️ Tools', files:'📁 Files',
  metrics:'📈 Metrics', security:'🔒 Security', users:'👥 Users', settings:'⚙️ Settings',
  automation:'⏰ Automation', knowledge:'🕸️ Knowledge', workflows:'🔄 Workflows',
  improvement:'📈 Improvement', computer:'🖥️ Computer', system:'🔧 System', profile:'👤 Profile'
};

function showPage(name) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  document.getElementById('page-' + name)?.classList.add('active');
  document.querySelector(`.nav-item[data-page="${name}"]`)?.classList.add('active');
  document.getElementById('pageTitle').textContent = pageTitles[name] || name;
  // Refresh data for certain pages
  if (name === 'dashboard') loadDashboard();
  if (name === 'agents') loadAgents();
  if (name === 'metrics') loadMetrics();
  if (name === 'security') loadSecurity();
  if (name === 'users') loadUsers();
  if (name === 'files') loadFiles();
  if (name === 'tools') loadTools();
  if (name === 'plugins') loadPlugins();
  if (name === 'settings') loadSettings();
  if (name === 'memory') loadMemory();
  if (name === 'automation') loadAutomation();
  if (name === 'knowledge') loadKnowledge();
  if (name === 'workflows') loadWorkflows();
  if (name === 'improvement') loadImprovement();
  if (name === 'system') loadSystem();
  if (name === 'profile') loadProfile();
}

function loadAllPages() { loadDashboard(); loadAgents(); }

// ═══════════════════════════════════════════════════════════════
// 📊 Dashboard
// ═══════════════════════════════════════════════════════════════
async function loadDashboard() {
  try {
    const status = await api('/status');
    const stats = document.getElementById('dashStats');
    stats.innerHTML = `
      <div class="stat-card"><div class="stat-value">${status.agents_count || 0}</div><div class="stat-label">Active Agents</div></div>
      <div class="stat-card"><div class="stat-value">${status.total_requests || 0}</div><div class="stat-label">Total Requests</div></div>
      <div class="stat-card"><div class="stat-value">${status.tools_count || 0}</div><div class="stat-label">Tools Registered</div></div>
      <div class="stat-card"><div class="stat-value">${status.uptime || '0s'}</div><div class="stat-label">Uptime</div></div>
    `;
    document.getElementById('dashSystemInfo').innerHTML = `
      <p>Version: ${status.version || '2.0.0'} | Providers: ${(status.providers || []).join(', ') || 'none'}</p>
      <p>Memory entries: ${status.memory_entries || 0} | Plugins: ${status.plugins_count || 0}</p>
    `;
    drawMiniChart('chartRequests', status.request_history || []);
    drawMiniChart('chartLatency', status.latency_history || []);
  } catch (e) { console.error('Dashboard error:', e); }
}

// ═══════════════════════════════════════════════════════════════
// 🤖 Agents
// ═══════════════════════════════════════════════════════════════
async function loadAgents() {
  try {
    const data = await api('/agents');
    const grid = document.getElementById('agentGrid');
    grid.innerHTML = (data.agents || []).map(a => `
      <div class="agent-card fade-in">
        <div class="agent-name">${escHtml(a.name)}</div>
        <div class="agent-type">${escHtml(a.type)} — <span class="badge badge-green">${a.status || 'ready'}</span></div>
        <p style="font-size:0.8rem;color:var(--text-dim);margin:8px 0">${escHtml(a.description || '')}</p>
        <div class="agent-caps">${(a.capabilities||[]).map(c => `<span class="agent-cap">${escHtml(c)}</span>`).join('')}</div>
      </div>
    `).join('') || '<p style="color:var(--text-dim)">No agents registered.</p>';
  } catch (e) { console.error('Agents error:', e); }
}

function spawnAgentModal() {
  showModal('Spawn Agent', `
    <div class="input-group"><label class="input-label">Agent Type</label>
      <select id="spawnType" class="input">
        <option value="code">Code</option><option value="research">Research</option>
        <option value="creative">Creative</option><option value="data">Data</option>
        <option value="pm">PM</option><option value="security">Security</option>
        <option value="devops">DevOps</option><option value="writer">Writer</option>
        <option value="qa">QA</option><option value="orchestrator">Orchestrator</option>
      </select>
    </div>
    <div class="input-group"><label class="input-label">Task (optional)</label>
      <input id="spawnTask" class="input" placeholder="Initial task for the agent">
    </div>
  `, async () => {
    try {
      await api('/agents/spawn', { method: 'POST', body: JSON.stringify({ type: document.getElementById('spawnType').value, task: document.getElementById('spawnTask').value }) });
      toast('Agent spawned!', 'success');
      closeModal();
      loadAgents();
    } catch (e) { toast('Error: ' + e.message, 'error'); }
  });
}

// ═══════════════════════════════════════════════════════════════
// 🧠 Memory
// ═══════════════════════════════════════════════════════════════
async function loadMemory() {
  try {
    const data = await api('/memory');
    document.getElementById('memoryStats').innerHTML = `
      <p>Total entries: <strong>${data.total_entries || 0}</strong></p>
      <p>Categories: ${(data.categories || []).join(', ') || 'none'}</p>
      <p style="margin-top:8px;font-size:0.78rem;color:var(--text-muted)">Most useful entries:</p>
      ${(data.most_useful || []).map(e => `<div style="font-size:0.8rem;padding:4px 0;border-bottom:1px solid var(--border)">${escHtml((e.content||'').slice(0,100))}...</div>`).join('')}
    `;
  } catch (e) { console.error('Memory error:', e); }
}

async function searchMemory() {
  const q = document.getElementById('memorySearchInput').value.trim();
  if (!q) return;
  try {
    const data = await api('/memory/search?q=' + encodeURIComponent(q));
    document.getElementById('memorySearchResults').innerHTML = (data.results || []).map(r => `
      <div style="padding:8px 0;border-bottom:1px solid var(--border);font-size:0.82rem">
        <div>${escHtml(r.content || '')}</div>
        <div style="color:var(--text-muted);font-size:0.72rem;margin-top:4px">Source: ${escHtml(r.source||'')} | Confidence: ${(r.confidence||0).toFixed(2)}</div>
      </div>
    `).join('') || '<p style="color:var(--text-dim)">No results found.</p>';
  } catch (e) { toast('Search error: ' + e.message, 'error'); }
}

async function ingestRAG() {
  const content = document.getElementById('ragContent').value.trim();
  if (!content) return;
  try {
    await api('/memory/rag/ingest', { method: 'POST', body: JSON.stringify({ content }) });
    toast('Document ingested!', 'success');
    document.getElementById('ragContent').value = '';
  } catch (e) { toast('Ingest error: ' + e.message, 'error'); }
}

async function searchRAG() {
  const q = document.getElementById('ragSearchInput').value.trim();
  if (!q) return;
  try {
    const data = await api('/memory/rag/search?q=' + encodeURIComponent(q));
    document.getElementById('ragSearchResults').innerHTML = (data.results || []).map(r => `
      <div style="padding:8px 0;border-bottom:1px solid var(--border);font-size:0.82rem">
        <div>${escHtml(r.content || '')}</div>
        <div style="color:var(--text-muted);font-size:0.72rem;margin-top:4px">Score: ${(r.score||0).toFixed(3)}</div>
      </div>
    `).join('') || '<p style="color:var(--text-dim)">No results.</p>';
  } catch (e) { toast('RAG search error: ' + e.message, 'error'); }
}

// ═══════════════════════════════════════════════════════════════
// 🌐 Browser
// ═══════════════════════════════════════════════════════════════
async function browserNavigate() {
  const url = document.getElementById('browserUrl').value.trim();
  if (!url) return;
  try {
    await api('/browser/navigate', { method: 'POST', body: JSON.stringify({ url }) });
    toast('Navigated!', 'success');
    browserScreenshot();
  } catch (e) { toast('Error: ' + e.message, 'error'); }
}

async function browserScreenshot() {
  try {
    const data = await api('/browser/screenshot', { method: 'POST', body: '{}' });
    const preview = document.getElementById('browserPreview');
    if (data.screenshot) {
      preview.innerHTML = `<img src="data:image/png;base64,${data.screenshot}" style="max-width:100%;border-radius:8px">`;
    } else {
      preview.innerHTML = `<span style="color:var(--text-dim)">${data.message || 'No screenshot available'}</span>`;
    }
  } catch (e) { toast('Screenshot error: ' + e.message, 'error'); }
}

async function browserClick() {
  const sel = document.getElementById('browserSelector').value.trim();
  if (!sel) return;
  try {
    await api('/browser/click', { method: 'POST', body: JSON.stringify({ selector: sel }) });
    document.getElementById('browserLog').innerHTML = `<div class="log-entry">Clicked: ${escHtml(sel)}</div>`;
  } catch (e) { toast('Click error: ' + e.message, 'error'); }
}

async function browserType() {
  const sel = document.getElementById('browserSelector').value.trim();
  const text = document.getElementById('browserText').value;
  if (!sel) return;
  try {
    await api('/browser/type', { method: 'POST', body: JSON.stringify({ selector: sel, text }) });
    document.getElementById('browserLog').innerHTML = `<div class="log-entry">Typed into ${escHtml(sel)}: "${escHtml(text)}"</div>`;
  } catch (e) { toast('Type error: ' + e.message, 'error'); }
}

// ═══════════════════════════════════════════════════════════════
// 🔌 Plugins
// ═══════════════════════════════════════════════════════════════
async function loadPlugins() {
  try {
    const data = await api('/plugins');
    document.getElementById('pluginGrid').innerHTML = (data.plugins || []).map(p => `
      <div class="card fade-in">
        <div class="card-header">
          <span class="card-title">${escHtml(p.name)}</span>
          <span class="badge ${p.enabled ? 'badge-green' : 'badge-red'}">${p.enabled ? 'Enabled' : 'Disabled'}</span>
        </div>
        <p style="font-size:0.8rem;color:var(--text-dim);margin-bottom:8px">${escHtml(p.description || '')}</p>
        <span style="font-size:0.72rem;color:var(--text-muted)">v${escHtml(p.version || '?')}</span>
      </div>
    `).join('') || '<p style="color:var(--text-dim)">No plugins installed.</p>';
  } catch (e) { console.error('Plugins error:', e); }
}

async function installPlugin() {
  const name = document.getElementById('pluginInstallInput').value.trim();
  if (!name) return;
  try {
    await api('/plugins/install', { method: 'POST', body: JSON.stringify({ name }) });
    toast('Plugin installed!', 'success');
    document.getElementById('pluginInstallInput').value = '';
    loadPlugins();
  } catch (e) { toast('Install error: ' + e.message, 'error'); }
}

// ═══════════════════════════════════════════════════════════════
// 🛠️ Tools
// ═══════════════════════════════════════════════════════════════
async function loadTools() {
  try {
    const data = await api('/tools');
    document.getElementById('toolsBody').innerHTML = (data.tools || []).map(t => `
      <tr>
        <td><strong>${escHtml(t.name)}</strong></td>
        <td style="color:var(--text-dim)">${escHtml(t.description || '')}</td>
        <td><code style="font-size:0.72rem">${escHtml(JSON.stringify(t.parameters || {}).slice(0,80))}</code></td>
        <td><span class="badge badge-green">Active</span></td>
        <td><button class="btn btn-secondary btn-sm" onclick="executeTool('${escHtml(t.name)}')">Run</button></td>
      </tr>
    `).join('') || '<tr><td colspan="5" style="color:var(--text-dim)">No tools registered.</td></tr>';
  } catch (e) { console.error('Tools error:', e); }
}

async function executeTool(name) {
  showModal('Execute Tool: ' + name, `
    <div class="input-group"><label class="input-label">Arguments (JSON)</label>
      <textarea id="toolArgs" class="input" rows="4">{}</textarea>
    </div>
  `, async () => {
    try {
      const args = JSON.parse(document.getElementById('toolArgs').value || '{}');
      const data = await api('/tools/execute', { method: 'POST', body: JSON.stringify({ tool: name, args }) });
      toast('Tool executed!', 'success');
      closeModal();
      appendToolMsg('✅ ' + name, JSON.stringify(data.result, null, 2));
      showPage('chat');
    } catch (e) { toast('Error: ' + e.message, 'error'); }
  });
}

// ═══════════════════════════════════════════════════════════════
// 📁 Files
// ═══════════════════════════════════════════════════════════════
async function loadFiles(path = '') {
  try {
    const data = await api('/files' + (path ? '?path=' + encodeURIComponent(path) : ''));
    const list = document.getElementById('fileList');
    let html = '';
    if (data.parent !== undefined) {
      html += `<div class="file-item" onclick="loadFiles('${escHtml(data.parent || '')}')"><span class="file-icon">⬆️</span><span class="file-name">..</span></div>`;
    }
    html += (data.files || []).map(f => {
      const icon = f.is_dir ? '📁' : '📄';
      const click = f.is_dir ? `loadFiles('${escHtml(f.path)}')` : `downloadFile('${escHtml(f.path)}')`;
      return `<div class="file-item" onclick="${click}">
        <span class="file-icon">${icon}</span>
        <span class="file-name">${escHtml(f.name)}</span>
        <span class="file-size">${f.is_dir ? '' : formatBytes(f.size)}</span>
      </div>`;
    }).join('');
    list.innerHTML = html || '<p style="color:var(--text-dim)">Empty directory</p>';
  } catch (e) { console.error('Files error:', e); }
}

function downloadFile(path) {
  window.open('/api/files/download?path=' + encodeURIComponent(path) + '&token=' + encodeURIComponent(authToken), '_blank');
}

function formatBytes(b) {
  if (!b) return '';
  const u = ['B','KB','MB','GB'];
  let i = 0;
  while (b >= 1024 && i < 3) { b /= 1024; i++; }
  return b.toFixed(1) + ' ' + u[i];
}

// ═══════════════════════════════════════════════════════════════
// 📈 Metrics
// ═══════════════════════════════════════════════════════════════
async function loadMetrics() {
  try {
    const data = await api('/metrics');
    document.getElementById('metricsStats').innerHTML = `
      <div class="stat-card"><div class="stat-value">${data.total_requests || 0}</div><div class="stat-label">Requests</div></div>
      <div class="stat-card"><div class="stat-value">${data.avg_latency_ms || 0}ms</div><div class="stat-label">Avg Latency</div></div>
      <div class="stat-card"><div class="stat-value">${data.error_rate || '0%'}</div><div class="stat-label">Error Rate</div></div>
      <div class="stat-card"><div class="stat-value">${data.active_connections || 0}</div><div class="stat-label">WS Connections</div></div>
    `;
    document.getElementById('metricsDetail').innerHTML = `<pre style="white-space:pre-wrap">${escHtml(JSON.stringify(data, null, 2))}</pre>`;
    drawMiniChart('chartThroughput', data.throughput_history || []);
    drawMiniChart('chartErrors', data.error_history || []);
  } catch (e) { console.error('Metrics error:', e); }
}

// ═══════════════════════════════════════════════════════════════
// 🔒 Security
// ═══════════════════════════════════════════════════════════════
async function loadSecurity() {
  try {
    const data = await api('/security');
    document.getElementById('securityStats').innerHTML = `
      <div class="stat-card"><div class="stat-value">${data.users_count || 0}</div><div class="stat-label">Users</div></div>
      <div class="stat-card"><div class="stat-value">${data.failed_logins || 0}</div><div class="stat-label">Failed Logins</div></div>
      <div class="stat-card"><div class="stat-value"><span class="badge badge-green">${data.encryption || 'AES-256'}</span></div><div class="stat-label">Encryption</div></div>
    `;
    document.getElementById('auditLog').innerHTML = (data.audit_log || []).map(l => `
      <div class="log-entry"><span class="log-time">${escHtml(l.time || '')}</span> — ${escHtml(l.event || '')}</div>
    `).join('') || '<p style="color:var(--text-dim)">No audit entries.</p>';
  } catch (e) { console.error('Security error:', e); }
}

// ═══════════════════════════════════════════════════════════════
// 👥 Users
// ═══════════════════════════════════════════════════════════════
async function loadUsers() {
  try {
    const data = await api('/users');
    document.getElementById('usersBody').innerHTML = (data.users || []).map(u => `
      <tr>
        <td><strong>${escHtml(u.username)}</strong></td>
        <td><span class="badge badge-purple">${escHtml(u.role || 'user')}</span></td>
        <td style="color:var(--text-dim)">${escHtml(u.created || '')}</td>
        <td><span class="badge badge-green">Active</span></td>
        <td><button class="btn btn-danger btn-sm" onclick="deleteUser('${escHtml(u.username)}')">Delete</button></td>
      </tr>
    `).join('') || '<tr><td colspan="5" style="color:var(--text-dim)">No users.</td></tr>';
  } catch (e) { console.error('Users error:', e); }
}

function showAddUserModal() {
  showModal('Add User', `
    <div class="input-group"><label class="input-label">Username</label><input id="newUser" class="input"></div>
    <div class="input-group"><label class="input-label">Password</label><input id="newPass" type="password" class="input"></div>
    <div class="input-group"><label class="input-label">Role</label>
      <select id="newRole" class="input"><option value="user">User</option><option value="admin">Admin</option></select>
    </div>
  `, async () => {
    try {
      await api('/auth/register', { method: 'POST', body: JSON.stringify({ username: document.getElementById('newUser').value, password: document.getElementById('newPass').value, role: document.getElementById('newRole').value }) });
      toast('User created!', 'success');
      closeModal();
      loadUsers();
    } catch (e) { toast('Error: ' + e.message, 'error'); }
  });
}

async function deleteUser(username) {
  if (!confirm('Delete user ' + username + '?')) return;
  try {
    await api('/users?username=' + encodeURIComponent(username), { method: 'DELETE' });
    toast('User deleted', 'success');
    loadUsers();
  } catch (e) { toast('Error: ' + e.message, 'error'); }
}

// ═══════════════════════════════════════════════════════════════
// ⚙️ Settings
// ═══════════════════════════════════════════════════════════════
async function loadSettings() {
  try {
    const data = await api('/config');
    document.getElementById('configEditor').value = JSON.stringify(data.config || data, null, 2);
  } catch (e) { console.error('Settings error:', e); }
  try {
    const prov = await api('/providers');
    document.getElementById('providerList').innerHTML = (prov.providers || []).map(p => `
      <div style="display:flex;align-items:center;gap:12px;padding:8px 0;border-bottom:1px solid var(--border)">
        <span class="badge ${p.status === 'active' ? 'badge-green' : 'badge-red'}">${p.status || 'unknown'}</span>
        <strong>${escHtml(p.name)}</strong>
        <span style="color:var(--text-dim);font-size:0.78rem">${escHtml(p.model || '')}</span>
      </div>
    `).join('') || '<p style="color:var(--text-dim)">No providers.</p>';
  } catch (e) {}
  try {
    const ch = await api('/channels');
    document.getElementById('channelList').innerHTML = (ch.channels || []).map(c => `
      <div style="display:flex;align-items:center;gap:12px;padding:8px 0;border-bottom:1px solid var(--border)">
        <span class="badge badge-blue">${escHtml(c.type || 'unknown')}</span>
        <strong>${escHtml(c.name)}</strong>
        <span class="badge ${c.enabled ? 'badge-green' : 'badge-red'}">${c.enabled ? 'Active' : 'Disabled'}</span>
      </div>
    `).join('') || '<p style="color:var(--text-dim)">No channels.</p>';
  } catch (e) {}
}

async function saveConfig() {
  try {
    const config = JSON.parse(document.getElementById('configEditor').value);
    await api('/config', { method: 'POST', body: JSON.stringify({ config }) });
    toast('Config saved!', 'success');
  } catch (e) { toast('Save error: ' + e.message, 'error'); }
}

// ═══════════════════════════════════════════════════════════════
// ⏰ Automation
// ═══════════════════════════════════════════════════════════════
async function loadAutomation() {
  try {
    const data = await api('/automation/jobs');
    document.getElementById('automationJobsBody').innerHTML = (data.jobs || []).map(j => `
      <tr>
        <td><strong>${escHtml(j.name)}</strong></td>
        <td><code>${escHtml(j.schedule)}</code></td>
        <td><span class="badge badge-purple">${escHtml(j.type)}</span></td>
        <td style="color:var(--text-dim)">${j.last_run ? new Date(j.last_run).toLocaleString() : 'Never'}</td>
        <td>${j.run_count || 0}</td>
        <td><span class="badge ${j.enabled ? 'badge-green' : 'badge-red'}">${j.enabled ? 'Active' : 'Disabled'}</span></td>
        <td>
          <button class="btn btn-secondary btn-sm" onclick="runJobNow('${j.id}')">▶ Run</button>
          <button class="btn btn-danger btn-sm" onclick="deleteJob('${j.id}')">🗑️</button>
        </td>
      </tr>
    `).join('') || '<tr><td colspan="7" style="color:var(--text-dim)">No jobs scheduled.</td></tr>';
  } catch (e) { console.error('Automation error:', e); }
  try {
    const hist = await api('/automation/history');
    document.getElementById('automationHistory').innerHTML = (hist.history || []).slice(-20).reverse().map(r => `
      <div class="log-entry">
        <span class="log-time">${escHtml(r.started_at || '')}</span>
        <strong>${escHtml(r.job_name)}</strong> — ${r.error ? '❌ ' + escHtml(r.error) : '✅ ' + escHtml((r.result||'').slice(0,100))}
        <span style="color:var(--text-muted);font-size:0.72rem"> (${(r.duration_ms||0).toFixed(0)}ms)</span>
      </div>
    `).join('') || '<p style="color:var(--text-dim)">No history yet.</p>';
  } catch (e) {}
}

function showAddJobModal() {
  showModal('Add Cron Job', `
    <div class="input-group"><label class="input-label">Job Name</label><input id="jobName" class="input" placeholder="My job"></div>
    <div class="input-group"><label class="input-label">Schedule (e.g. 5m, 1h, 1d)</label><input id="jobSchedule" class="input" placeholder="1h"></div>
    <div class="input-group"><label class="input-label">Task / Command</label><input id="jobTask" class="input" placeholder="Check emails"></div>
    <div class="input-group"><label class="input-label">Type</label>
      <select id="jobType" class="input"><option value="agent">Agent</option><option value="shell">Shell</option><option value="webhook">Webhook</option></select>
    </div>
  `, async () => {
    try {
      await api('/automation/jobs', { method: 'POST', body: JSON.stringify({
        name: document.getElementById('jobName').value,
        schedule: document.getElementById('jobSchedule').value,
        task: document.getElementById('jobTask').value,
        type: document.getElementById('jobType').value,
      })});
      toast('Job created!', 'success'); closeModal(); loadAutomation();
    } catch (e) { toast('Error: ' + e.message, 'error'); }
  });
}

async function runJobNow(id) {
  try { await api('/automation/jobs/' + id + '/run', { method: 'POST', body: '{}' }); toast('Job executed!', 'success'); loadAutomation(); }
  catch (e) { toast('Error: ' + e.message, 'error'); }
}

async function deleteJob(id) {
  if (!confirm('Delete this job?')) return;
  try { await api('/automation/jobs/' + id, { method: 'DELETE' }); toast('Job deleted', 'success'); loadAutomation(); }
  catch (e) { toast('Error: ' + e.message, 'error'); }
}

// ═══════════════════════════════════════════════════════════════
// 🕸️ Knowledge Graph
// ═══════════════════════════════════════════════════════════════
async function loadKnowledge() {
  try {
    const data = await api('/knowledge');
    document.getElementById('knowledgeStats').innerHTML = `
      <p>Entities: <strong>${data.total_entities || 0}</strong></p>
      <p>Relationships: <strong>${data.total_relationships || 0}</strong></p>
      <p style="margin-top:8px">Entity types:</p>
      ${Object.entries(data.entity_types || {}).map(([k,v]) => `<div style="font-size:0.82rem;padding:2px 0"><span class="badge badge-purple">${escHtml(k)}</span> ${v}</div>`).join('')}
    `;
  } catch (e) { console.error('Knowledge error:', e); }
}

async function searchKnowledge() {
  const q = document.getElementById('knowledgeSearchInput').value.trim();
  if (!q) return;
  try {
    const data = await api('/knowledge/search?q=' + encodeURIComponent(q));
    document.getElementById('knowledgeSearchResults').innerHTML = (data.results || []).map(r => `
      <div style="padding:6px 0;border-bottom:1px solid var(--border);font-size:0.82rem">
        <strong>${escHtml(r.name)}</strong> <span class="badge badge-purple">${escHtml(r.type)}</span>
        <span style="color:var(--text-muted)">score: ${(r.score||0).toFixed(2)}</span>
      </div>
    `).join('') || '<p style="color:var(--text-dim)">No results.</p>';
  } catch (e) { toast('Search error: ' + e.message, 'error'); }
}

// ═══════════════════════════════════════════════════════════════
// 🔄 Workflows
// ═══════════════════════════════════════════════════════════════
async function loadWorkflows() {
  try {
    const data = await api('/workflows');
    document.getElementById('workflowsBody').innerHTML = (data.workflows || []).map(w => `
      <tr>
        <td><strong>${escHtml(w.name)}</strong></td>
        <td>${w.step_count || 0}</td>
        <td style="color:var(--text-dim)">${escHtml(w.created_at || '').slice(0,10)}</td>
        <td>${w.replay_count || 0}</td>
        <td>
          <button class="btn btn-secondary btn-sm" onclick="replayWorkflow('${escHtml(w.name)}')">▶ Replay</button>
        </td>
      </tr>
    `).join('') || '<tr><td colspan="5" style="color:var(--text-dim)">No workflows recorded.</td></tr>';
  } catch (e) { console.error('Workflows error:', e); }
}

async function startRecording() {
  const name = prompt('Workflow name:');
  if (!name) return;
  try { await api('/workflows/record', { method: 'POST', body: JSON.stringify({ name }) }); toast('Recording started!', 'info'); }
  catch (e) { toast('Error: ' + e.message, 'error'); }
}

async function stopRecording() {
  try { await api('/workflows/record', { method: 'POST', body: JSON.stringify({ stop: true }) }); toast('Recording stopped!', 'success'); loadWorkflows(); }
  catch (e) { toast('Error: ' + e.message, 'error'); }
}

async function replayWorkflow(name) {
  try { await api('/workflows/replay', { method: 'POST', body: JSON.stringify({ name }) }); toast('Workflow replayed!', 'success'); loadWorkflows(); }
  catch (e) { toast('Error: ' + e.message, 'error'); }
}

// ═══════════════════════════════════════════════════════════════
// 📈 Improvement
// ═══════════════════════════════════════════════════════════════
async function loadImprovement() {
  try {
    const data = await api('/improvement');
    document.getElementById('improvementStats').innerHTML = `
      <div class="stat-card"><div class="stat-value">${data.total_entries || 0}</div><div class="stat-label">Total Learnings</div></div>
      <div class="stat-card"><div class="stat-value">${data.total_corrections || 0}</div><div class="stat-label">Corrections</div></div>
      <div class="stat-card"><div class="stat-value">${data.total_insights || 0}</div><div class="stat-label">Insights</div></div>
      <div class="stat-card"><div class="stat-value">${data.health_score || 100}%</div><div class="stat-label">Health Score</div></div>
    `;
    document.getElementById('improvementErrors').innerHTML = (data.top_errors || []).map(e => `
      <div style="padding:6px 0;border-bottom:1px solid var(--border);font-size:0.82rem">
        <span class="badge badge-red">${e.count}x</span> ${escHtml(e.error)}
      </div>
    `).join('') || '<p style="color:var(--text-dim)">No errors recorded.</p>';
    document.getElementById('improvementLearnings').innerHTML = (data.recent_learnings || []).reverse().map(l => `
      <div class="log-entry">
        <span class="badge badge-${l.category==='error'?'red':l.category==='correction'?'yellow':'green'}">${escHtml(l.category)}</span>
        ${escHtml(l.description)}
        <span class="log-time">${escHtml(l.timestamp||'').slice(0,10)}</span>
      </div>
    `).join('') || '<p style="color:var(--text-dim)">No learnings yet.</p>';
  } catch (e) { console.error('Improvement error:', e); }
}

// ═══════════════════════════════════════════════════════════════
// 🖥️ Computer Use
// ═══════════════════════════════════════════════════════════════
async function takeScreenshot() {
  try {
    const data = await api('/computer/screenshot', { method: 'POST', body: '{}' });
    if (data.image_base64) {
      document.getElementById('screenshotPreview').innerHTML = `<img src="data:image/png;base64,${data.image_base64}" style="max-width:100%;border-radius:8px">`;
    } else {
      document.getElementById('screenshotPreview').innerHTML = `<span style="color:var(--text-dim)">${data.message || 'Screenshot taken'}</span>`;
    }
  } catch (e) { toast('Error: ' + e.message, 'error'); }
}

async function computerClick() {
  const x = parseInt(document.getElementById('clickX').value) || 0;
  const y = parseInt(document.getElementById('clickY').value) || 0;
  try {
    await api('/computer/click', { method: 'POST', body: JSON.stringify({ x, y }) });
    document.getElementById('computerLog').innerHTML = `<div class="log-entry">Clicked at (${x}, ${y})</div>`;
  } catch (e) { toast('Error: ' + e.message, 'error'); }
}

async function computerType() {
  const text = document.getElementById('typeText').value;
  if (!text) return;
  try {
    await api('/computer/type', { method: 'POST', body: JSON.stringify({ text }) });
    document.getElementById('computerLog').innerHTML = `<div class="log-entry">Typed: "${escHtml(text)}"</div>`;
  } catch (e) { toast('Error: ' + e.message, 'error'); }
}

// ═══════════════════════════════════════════════════════════════
// 🔧 System
// ═══════════════════════════════════════════════════════════════
async function loadSystem() {
  try {
    const data = await api('/system/info');
    document.getElementById('systemStats').innerHTML = `
      <div class="stat-card"><div class="stat-value">${escHtml(data.platform || '?')}</div><div class="stat-label">Platform</div></div>
      <div class="stat-card"><div class="stat-value">${data.cpu_count || '?'}</div><div class="stat-label">CPU Cores</div></div>
      <div class="stat-card"><div class="stat-value">${(data.memory||{}).percent_used || 0}%</div><div class="stat-label">Memory Used</div></div>
      <div class="stat-card"><div class="stat-value">${(data.disk||{}).free_gb || 0}GB</div><div class="stat-label">Disk Free</div></div>
    `;
    document.getElementById('systemDetails').innerHTML = `<pre style="white-space:pre-wrap">${escHtml(JSON.stringify(data, null, 2))}</pre>`;
  } catch (e) { console.error('System error:', e); }
}

async function checkUpdates() {
  try {
    const data = await api('/system/update', { method: 'POST', body: '{}' });
    toast(data.message || 'Update check complete', data.update_available ? 'info' : 'success');
  } catch (e) { toast('Error: ' + e.message, 'error'); }
}

// ═══════════════════════════════════════════════════════════════
// 👤 Profile
// ═══════════════════════════════════════════════════════════════
async function loadProfile() {
  try {
    const data = await api('/user/profile');
    document.getElementById('profileSummary').textContent = data.summary || 'No profile data yet.';
    if (data.name) document.getElementById('profileName').value = data.name;
    if (data.timezone) document.getElementById('profileTimezone').value = data.timezone;
  } catch (e) { console.error('Profile error:', e); }
}

async function saveProfile() {
  try {
    await api('/user/profile', { method: 'POST', body: JSON.stringify({
      name: document.getElementById('profileName').value,
      timezone: document.getElementById('profileTimezone').value,
    })});
    toast('Profile saved!', 'success');
  } catch (e) { toast('Error: ' + e.message, 'error'); }
}

// ═══════════════════════════════════════════════════════════════
// 🎨 Mini Chart (Canvas)
// ═══════════════════════════════════════════════════════════════
function drawMiniChart(canvasId, data) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const rect = canvas.parentElement.getBoundingClientRect();
  canvas.width = rect.width;
  canvas.height = rect.height;
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  if (!data.length) {
    // Generate demo data
    for (let i = 0; i < 24; i++) data.push(Math.random() * 100);
  }

  const w = canvas.width, h = canvas.height;
  const max = Math.max(...data, 1);
  const step = w / (data.length - 1 || 1);

  // Grid
  ctx.strokeStyle = 'rgba(42,42,85,0.5)';
  ctx.lineWidth = 1;
  for (let i = 0; i < 5; i++) {
    const y = (h / 5) * i + 10;
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
  }

  // Line
  ctx.beginPath();
  ctx.moveTo(0, h - (data[0] / max) * (h - 20) - 10);
  for (let i = 1; i < data.length; i++) {
    ctx.lineTo(i * step, h - (data[i] / max) * (h - 20) - 10);
  }
  ctx.strokeStyle = '#8b5cf6';
  ctx.lineWidth = 2;
  ctx.stroke();

  // Fill
  ctx.lineTo((data.length - 1) * step, h);
  ctx.lineTo(0, h);
  ctx.closePath();
  const grad = ctx.createLinearGradient(0, 0, 0, h);
  grad.addColorStop(0, 'rgba(139,92,246,0.3)');
  grad.addColorStop(1, 'rgba(139,92,246,0.02)');
  ctx.fillStyle = grad;
  ctx.fill();
}

// ═══════════════════════════════════════════════════════════════
// 🔔 Toast
// ═══════════════════════════════════════════════════════════════
function toast(msg, type = 'info') {
  const div = document.createElement('div');
  div.className = 'toast toast-' + type;
  div.textContent = msg;
  document.getElementById('toastContainer').appendChild(div);
  setTimeout(() => div.remove(), 4000);
}

// ═══════════════════════════════════════════════════════════════
// 🪟 Modal
// ═══════════════════════════════════════════════════════════════
function showModal(title, bodyHtml, onConfirm) {
  document.getElementById('modalContainer').innerHTML = `
    <div class="modal-overlay" onclick="if(event.target===this)closeModal()">
      <div class="modal">
        <div class="modal-title">${escHtml(title)}</div>
        ${bodyHtml}
        <div class="modal-actions">
          <button class="btn btn-secondary" onclick="closeModal()">Cancel</button>
          <button class="btn btn-primary" id="modalConfirm">Confirm</button>
        </div>
      </div>
    </div>
  `;
  document.getElementById('modalConfirm').onclick = onConfirm;
}

function closeModal() {
  document.getElementById('modalContainer').innerHTML = '';
}

// ═══════════════════════════════════════════════════════════════
// 🧙 Onboarding Wizard
// ═══════════════════════════════════════════════════════════════
let obStep = 0;
let obData = { provider: '', api_key: '', model: '', voice: {}, browser: {}, name: 'User' };
let obGuides = {};
const obStepsMeta = ['welcome','provider','api_key','model','extras','name','complete'];

async function checkOnboarding() {
  try {
    const resp = await fetch('/api/setup/status');
    const data = await resp.json();
    if (data.is_first_run) {
      obGuides = data.providers || {};
      showOnboarding();
      return true;
    }
  } catch(e) {}
  return false;
}

function showOnboarding() {
  document.getElementById('loginPage').style.display = 'none';
  document.getElementById('onboardingPage').style.display = 'block';
  renderObStep();
}

function renderObStep() {
  const dots = obStepsMeta.map((_, i) => {
    let cls = 'onboarding-dot';
    if (i === obStep) cls += ' active';
    else if (i < obStep) cls += ' done';
    return `<div class="${cls}"></div>`;
  }).join('');
  document.getElementById('obSteps').innerHTML = dots;
  document.getElementById('obBack').style.display = obStep > 0 && obStep < obStepsMeta.length - 1 ? 'inline-flex' : 'none';

  const step = obStepsMeta[obStep];
  const content = document.getElementById('obContent');
  const nextBtn = document.getElementById('obNext');

  if (step === 'welcome') {
    nextBtn.textContent = "Let's go →";
    content.innerHTML = `
      <div style="text-align:center;padding:20px 0">
        <div style="font-size:3rem;margin-bottom:16px">🚀</div>
        <h2 style="color:var(--purple-300);margin-bottom:12px">Welcome to Rally Agent</h2>
        <p style="color:var(--text-dim);font-size:0.92rem;max-width:400px;margin:0 auto;line-height:1.7">
          Your self-hosted AI platform with <strong style="color:var(--purple-400)">36+ providers</strong>,
          <strong style="color:var(--purple-400)">voice</strong>,
          <strong style="color:var(--purple-400)">browser automation</strong>, and more.<br><br>
          Let's get you configured in a few quick steps.
        </p>
      </div>
    `;
  } else if (step === 'provider') {
    nextBtn.textContent = 'Continue →';
    const providers = Object.entries(obGuides);
    content.innerHTML = `
      <div class="ob-section">
        <h3>Choose your AI provider</h3>
        <div class="ob-provider-grid">
          ${providers.map(([key, g]) => `
            <div class="ob-provider ${obData.provider === key ? 'selected' : ''}" onclick="obSelectProvider('${key}')">
              <span class="icon">${g.icon}</span>
              <div>
                <div class="name">${escHtml(g.name)}</div>
                <div class="desc">${escHtml(g.description)}</div>
              </div>
              <span class="key-badge ${g.requires_key ? 'needs-key' : 'no-key'}">${g.requires_key ? '🔑' : '🆓'}</span>
            </div>
          `).join('')}
        </div>
      </div>
    `;
  } else if (step === 'api_key') {
    const guide = obGuides[obData.provider] || {};
    if (!guide.requires_key) {
      obStep++; renderObStep(); return;
    }
    nextBtn.textContent = 'Verify & Continue →';
    content.innerHTML = `
      <div class="ob-section">
        <h3>${guide.icon} ${escHtml(guide.name)} — API Key</h3>
        <div class="ob-guide-box">${escHtml(guide.how_to_get_key || '')}</div>
        ${guide.url ? `<p style="font-size:0.82rem;margin-bottom:16px">🔗 <a href="${escHtml(guide.url)}" target="_blank">${escHtml(guide.url)}</a></p>` : ''}
        <div class="input-group">
          <label class="input-label">Paste your API key</label>
          <input id="obApiKey" type="password" class="input" placeholder="${escHtml(guide.key_prefix || '')}..." value="${escHtml(obData.api_key)}">
        </div>
      </div>
    `;
    setTimeout(() => document.getElementById('obApiKey')?.focus(), 100);
  } else if (step === 'model') {
    const guide = obGuides[obData.provider] || {};
    const models = guide.models || [];
    const defaultModel = guide.default_model || (models[0] || '');
    nextBtn.textContent = 'Continue →';
    content.innerHTML = `
      <div class="ob-section">
        <h3>Choose default model</h3>
        <div class="ob-model-list">
          ${models.map(m => `
            <div class="ob-model ${obData.model === m ? 'selected' : ''} ${m === defaultModel && !obData.model ? 'selected default' : ''}"
                 onclick="obSelectModel('${escHtml(m)}')">${escHtml(m)}</div>
          `).join('')}
        </div>
      </div>
    `;
    if (!obData.model && defaultModel) obData.model = defaultModel;
  } else if (step === 'extras') {
    nextBtn.textContent = 'Continue →';
    content.innerHTML = `
      <div class="ob-section">
        <h3>Optional Features</h3>
        <div style="display:flex;flex-direction:column;gap:14px">
          <label style="display:flex;align-items:center;gap:12px;padding:14px;background:var(--bg-800);border:1px solid var(--border);border-radius:10px;cursor:pointer">
            <input type="checkbox" id="obVoice" ${obData.voice?.enabled ? 'checked' : ''} style="width:18px;height:18px;accent-color:var(--purple-500)">
            <div>
              <div style="font-weight:600;color:var(--text)">🎤 Voice Input/Output</div>
              <div style="font-size:0.78rem;color:var(--text-dim)">Speak to Rally and hear responses</div>
            </div>
          </label>
          <label style="display:flex;align-items:center;gap:12px;padding:14px;background:var(--bg-800);border:1px solid var(--border);border-radius:10px;cursor:pointer">
            <input type="checkbox" id="obBrowser" ${obData.browser?.enabled ? 'checked' : ''} style="width:18px;height:18px;accent-color:var(--purple-500)">
            <div>
              <div style="font-weight:600;color:var(--text)">🌐 Browser Automation</div>
              <div style="font-size:0.78rem;color:var(--text-dim)">Let Rally browse the web for you</div>
            </div>
          </label>
        </div>
      </div>
    `;
  } else if (step === 'name') {
    nextBtn.textContent = 'Finish Setup →';
    content.innerHTML = `
      <div class="ob-section">
        <h3>What should we call you?</h3>
        <div class="input-group">
          <input id="obName" class="input" placeholder="Your name" value="${escHtml(obData.name || '')}">
        </div>
      </div>
    `;
    setTimeout(() => document.getElementById('obName')?.focus(), 100);
  } else if (step === 'complete') {
    const guide = obGuides[obData.provider] || {};
    nextBtn.textContent = '🚀 Launch Rally Agent';
    document.getElementById('obBack').style.display = 'none';
    content.innerHTML = `
      <div class="ob-success">
        <div class="checkmark">🎉</div>
        <h2>Setup Complete!</h2>
        <p style="margin:12px 0">
          Provider: <strong style="color:var(--purple-300)">${guide.icon || ''} ${escHtml(guide.name || obData.provider)}</strong><br>
          Model: <strong style="color:var(--purple-300)">${escHtml(obData.model)}</strong><br>
          Welcome, <strong style="color:var(--purple-300)">${escHtml(obData.name)}</strong>!
        </p>
      </div>
    `;
  }
}

function obSelectProvider(key) {
  obData.provider = key;
  const guide = obGuides[key] || {};
  obData.model = guide.default_model || '';
  obData.api_key = '';
  renderObStep();
}

function obSelectModel(model) {
  obData.model = model;
  renderObStep();
}

async function obNext() {
  const step = obStepsMeta[obStep];

  if (step === 'provider' && !obData.provider) {
    toast('Please select a provider', 'error');
    return;
  }
  if (step === 'api_key') {
    const input = document.getElementById('obApiKey');
    obData.api_key = input ? input.value.trim() : '';
    const guide = obGuides[obData.provider] || {};
    if (guide.requires_key && !obData.api_key) {
      toast('API key is required', 'error');
      return;
    }
  }
  if (step === 'extras') {
    obData.voice = { enabled: document.getElementById('obVoice')?.checked || false };
    obData.browser = { enabled: document.getElementById('obBrowser')?.checked || false };
  }
  if (step === 'name') {
    obData.name = document.getElementById('obName')?.value?.trim() || 'User';
  }
  if (step === 'complete') {
    await obSubmit();
    return;
  }

  obStep++;
  renderObStep();
}

function obPrev() {
  if (obStep > 0) {
    // Skip api_key step if provider doesn't require key
    if (obStepsMeta[obStep - 1] === 'api_key') {
      const guide = obGuides[obData.provider] || {};
      if (!guide.requires_key) { obStep -= 2; renderObStep(); return; }
    }
    obStep--;
    renderObStep();
  }
}

async function obSubmit() {
  try {
    const resp = await fetch('/api/setup/complete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(obData),
    });
    const data = await resp.json();
    if (data.status === 'ok') {
      toast('Setup complete! 🎉', 'success');
      document.getElementById('onboardingPage').style.display = 'none';
      // Show login or go straight to app
      if (obData.api_key) {
        // Auto-register admin and enter app
        try {
          const regResp = await fetch('/api/auth/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username: 'admin', password: 'admin' }),
          });
          const regData = await regResp.json();
          if (regData.token) {
            authToken = regData.token;
            localStorage.setItem('rally_token', authToken);
            currentUser = 'admin';
            enterApp();
            return;
          }
        } catch(e) {}
      }
      document.getElementById('loginPage').style.display = 'flex';
    } else {
      toast('Error: ' + (data.error || 'Setup failed'), 'error');
    }
  } catch(e) {
    toast('Setup error: ' + e.message, 'error');
  }
}

// ═══════════════════════════════════════════════════════════════
// 🚀 Init
// ═══════════════════════════════════════════════════════════════
if (authToken) {
  // Validate token
  api('/status').then(() => {
    currentUser = 'user';
    enterApp();
  }).catch(() => {
    authToken = ''; localStorage.removeItem('rally_token');
    // Check onboarding before showing login
    checkOnboarding().then(needsSetup => {
      if (!needsSetup) document.getElementById('loginPage').style.display = 'flex';
    });
  });
} else {
  // Check onboarding before showing login
  checkOnboarding().then(needsSetup => {
    if (!needsSetup) document.getElementById('loginPage').style.display = 'flex';
  });
}
</script>
</body>
</html>"""


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
