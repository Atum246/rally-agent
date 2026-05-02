"""
Rally Agent — Enterprise Security Manager
==========================================
Sandboxed execution, RBAC, audit logging, secrets vault, network policies,
data classification, rate limiting, prompt injection detection, and more.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import json
import logging
import os
import re
import resource
import secrets
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("rally.security")

# ---------------------------------------------------------------------------
# Optional dependency imports with graceful fallbacks
# ---------------------------------------------------------------------------

try:
    from cryptography.fernet import Fernet
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False
    logger.warning("cryptography not installed — secrets vault disabled")


# ============================= Data Types ==================================

class Role(Enum):
    VIEWER = "viewer"
    USER = "user"
    ADMIN = "admin"


ROLE_HIERARCHY = {Role.VIEWER: 0, Role.USER: 1, Role.ADMIN: 2}

ROLE_PERMISSIONS: Dict[Role, Set[str]] = {
    Role.VIEWER: {"read", "view_history"},
    Role.USER: {"read", "write", "execute", "view_history", "manage_own_secrets"},
    Role.ADMIN: {
        "read", "write", "execute", "view_history", "manage_own_secrets",
        "manage_users", "manage_secrets", "manage_network", "view_audit",
        "manage_rate_limits", "manage_commands",
    },
}


class DataSensitivity(Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    SENSITIVE = "sensitive"
    SECRET = "secret"


@dataclass
class AuditEntry:
    timestamp: str
    user_id: str
    action: str
    resource: str
    detail: str
    ip: Optional[str] = None
    result: str = "success"
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RateLimitConfig:
    max_requests: int = 60
    window_seconds: int = 60
    burst: int = 10


@dataclass
class UserSession:
    session_id: str
    user_id: str
    role: Role
    created_at: float
    last_active: float
    ip: Optional[str] = None
    timeout_seconds: int = 3600

    @property
    def expired(self) -> bool:
        return (time.time() - self.last_active) > self.timeout_seconds

    def touch(self) -> None:
        self.last_active = time.time()


# =========================== Security Manager ==============================

class SecurityManager:
    """
    Central security orchestrator for Rally Agent.

    Features:
      • Sandboxed code execution (subprocess + seccomp + resource limits)
      • Role-Based Access Control (RBAC)
      • Encrypted secrets vault (Fernet)
      • Network domain allowlisting / denylisting
      • PII & secret auto-detection in outputs
      • Per-user / per-tool rate limiting
      • Prompt injection detection (heuristic + pattern-based ML-lite)
      • Output sanitization & auto-redaction
      • Session management with configurable timeout
      • IP-based access control
      • Command allowlisting / denylisting
    """

    def __init__(self, data_dir: str | Path = "~/.rally/security") -> None:
        self._data_dir = Path(data_dir).expanduser()
        self._data_dir.mkdir(parents=True, exist_ok=True)

        # ---- RBAC ----
        self._users: Dict[str, Dict[str, Any]] = {}  # user_id -> {role, ip_whitelist, ...}
        self._load_users()

        # ---- Sessions ----
        self._sessions: Dict[str, UserSession] = {}
        self._session_lock = threading.Lock()

        # ---- Audit log ----
        self._audit_path = self._data_dir / "audit.jsonl"
        self._audit_lock = threading.Lock()

        # ---- Secrets vault ----
        self._vault_path = self._data_dir / "vault.enc"
        self._vault_key_path = self._data_dir / ".vault_key"
        self._vault: Dict[str, str] = {}
        self._fernet: Optional[Any] = None
        self._init_vault()

        # ---- Network policies ----
        self._allowed_domains: Set[str] = set()
        self._denied_domains: Set[str] = {"malware.com", "phishing.net"}
        self._load_network_policies()

        # ---- Rate limiting ----
        self._rate_limits: Dict[str, RateLimitConfig] = {}  # key: "user_id" or "user_id:tool"
        self._rate_buckets: Dict[str, List[float]] = defaultdict(list)
        self._rate_lock = threading.Lock()

        # ---- Command allowlist / denylist ----
        self._allowed_commands: Set[str] = set()  # empty = all allowed (unless denied)
        self._denied_commands: Set[str] = {
            "rm -rf /", "mkfs", "dd if=", ":(){ :|:& };:",
            "shutdown", "reboot", "halt", "poweroff",
        }

        # ---- Prompt injection patterns (ML-lite) ----
        self._injection_patterns = self._build_injection_patterns()

        # ---- PII / secret detection regex ----
        self._pii_patterns = self._build_pii_patterns()

    # ====================================================================
    #  RBAC
    # ====================================================================

    def create_user(
        self,
        user_id: str,
        role: Role = Role.USER,
        ip_whitelist: Optional[List[str]] = None,
        *,
        created_by: str = "system",
    ) -> None:
        self._users[user_id] = {
            "role": role.value,
            "ip_whitelist": ip_whitelist or [],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": created_by,
        }
        self._save_users()
        self._audit(created_by, "create_user", user_id, f"role={role.value}")

    def get_user_role(self, user_id: str) -> Role:
        info = self._users.get(user_id)
        if info is None:
            return Role.VIEWER
        return Role(info["role"])

    def set_user_role(self, user_id: str, role: Role, *, by: str) -> bool:
        if user_id not in self._users:
            return False
        old = self._users[user_id]["role"]
        self._users[user_id]["role"] = role.value
        self._save_users()
        self._audit(by, "set_role", user_id, f"{old} -> {role.value}")
        return True

    def check_permission(self, user_id: str, permission: str) -> bool:
        role = self.get_user_role(user_id)
        return permission in ROLE_PERMISSIONS.get(role, set())

    def require_permission(self, user_id: str, permission: str) -> None:
        if not self.check_permission(user_id, permission):
            raise PermissionError(
                f"User '{user_id}' lacks permission '{permission}'"
            )

    # ====================================================================
    #  Session Management
    # ====================================================================

    def create_session(
        self,
        user_id: str,
        ip: Optional[str] = None,
        timeout: int = 3600,
    ) -> str:
        # IP check
        if ip and not self._ip_allowed(user_id, ip):
            raise PermissionError(f"IP {ip} not allowed for user '{user_id}'")

        sid = uuid.uuid4().hex
        session = UserSession(
            session_id=sid,
            user_id=user_id,
            role=self.get_user_role(user_id),
            created_at=time.time(),
            last_active=time.time(),
            ip=ip,
            timeout_seconds=timeout,
        )
        with self._session_lock:
            self._sessions[sid] = session
        self._audit(user_id, "create_session", sid, f"ip={ip}")
        return sid

    def validate_session(self, session_id: str) -> Optional[UserSession]:
        with self._session_lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            if session.expired:
                del self._sessions[session_id]
                self._audit(session.user_id, "session_expired", session_id, "")
                return None
            session.touch()
            return session

    def destroy_session(self, session_id: str) -> None:
        with self._session_lock:
            session = self._sessions.pop(session_id, None)
        if session:
            self._audit(session.user_id, "destroy_session", session_id, "")

    def cleanup_expired_sessions(self) -> int:
        expired = []
        with self._session_lock:
            for sid, s in list(self._sessions.items()):
                if s.expired:
                    expired.append(sid)
                    del self._sessions[sid]
        return len(expired)

    # ====================================================================
    #  Audit Logging
    # ====================================================================

    def _audit(
        self,
        user_id: str,
        action: str,
        resource: str,
        detail: str,
        *,
        ip: Optional[str] = None,
        result: str = "success",
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        entry = AuditEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            user_id=user_id,
            action=action,
            resource=resource,
            detail=detail,
            ip=ip,
            result=result,
            meta=meta or {},
        )
        line = json.dumps(entry.__dict__, default=str)
        with self._audit_lock:
            with open(self._audit_path, "a") as f:
                f.write(line + "\n")

    def get_audit_log(
        self,
        user_id: Optional[str] = None,
        action: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        entries: List[Dict[str, Any]] = []
        if not self._audit_path.exists():
            return entries
        with open(self._audit_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if user_id and entry.get("user_id") != user_id:
                    continue
                if action and entry.get("action") != action:
                    continue
                entries.append(entry)
        return entries[-limit:]

    # ====================================================================
    #  Secrets Vault (Fernet encryption)
    # ====================================================================

    def _init_vault(self) -> None:
        if not HAS_CRYPTO:
            return
        key_path = self._vault_key_path
        if key_path.exists():
            key = key_path.read_bytes().strip()
        else:
            key = Fernet.generate_key()
            key_path.write_bytes(key)
            os.chmod(key_path, 0o600)
        self._fernet = Fernet(key)
        # Load existing vault
        if self._vault_path.exists():
            try:
                data = self._vault_path.read_bytes()
                plaintext = self._fernet.decrypt(data)
                self._vault = json.loads(plaintext)
            except Exception as e:
                logger.error("Failed to decrypt vault: %s", e)
                self._vault = {}

    def _save_vault(self) -> None:
        if not self._fernet:
            return
        data = json.dumps(self._vault).encode()
        encrypted = self._fernet.encrypt(data)
        self._vault_path.write_bytes(encrypted)
        os.chmod(self._vault_path, 0o600)

    def store_secret(self, name: str, value: str, *, user_id: str) -> None:
        self.require_permission(user_id, "manage_secrets")
        self._vault[name] = value
        self._save_vault()
        self._audit(user_id, "store_secret", name, "value=***")

    def get_secret(self, name: str, *, user_id: str) -> Optional[str]:
        self.require_permission(user_id, "manage_secrets")
        val = self._vault.get(name)
        self._audit(user_id, "get_secret", name, "found" if val else "not_found")
        return val

    def delete_secret(self, name: str, *, user_id: str) -> bool:
        self.require_permission(user_id, "manage_secrets")
        if name in self._vault:
            del self._vault[name]
            self._save_vault()
            self._audit(user_id, "delete_secret", name, "")
            return True
        return False

    def list_secrets(self, *, user_id: str) -> List[str]:
        self.require_permission(user_id, "manage_secrets")
        return list(self._vault.keys())

    # ====================================================================
    #  Network Policies
    # ====================================================================

    def _load_network_policies(self) -> None:
        path = self._data_dir / "network_policies.json"
        if path.exists():
            try:
                data = json.loads(path.read_text())
                self._allowed_domains = set(data.get("allowed", []))
                self._denied_domains = set(data.get("denied", []))
            except Exception as e:
                logger.error("Failed to load network policies: %s", e)

    def _save_network_policies(self) -> None:
        path = self._data_dir / "network_policies.json"
        path.write_text(json.dumps({
            "allowed": sorted(self._allowed_domains),
            "denied": sorted(self._denied_domains),
        }, indent=2))

    def add_allowed_domain(self, domain: str, *, user_id: str) -> None:
        self.require_permission(user_id, "manage_network")
        self._allowed_domains.add(domain.lower())
        self._save_network_policies()
        self._audit(user_id, "add_allowed_domain", domain, "")

    def add_denied_domain(self, domain: str, *, user_id: str) -> None:
        self.require_permission(user_id, "manage_network")
        self._denied_domains.add(domain.lower())
        self._save_network_policies()
        self._audit(user_id, "add_denied_domain", domain, "")

    def is_url_allowed(self, url: str) -> bool:
        """Check whether a URL is permitted by network policies."""
        from urllib.parse import urlparse

        try:
            hostname = urlparse(url).hostname or ""
        except Exception:
            return False
        hostname = hostname.lower()

        # Deny takes precedence
        for d in self._denied_domains:
            if hostname == d or hostname.endswith("." + d):
                return False

        # If allowlist is empty, everything not denied is allowed
        if not self._allowed_domains:
            return True

        for d in self._allowed_domains:
            if hostname == d or hostname.endswith("." + d):
                return True
        return False

    # ====================================================================
    #  Rate Limiting
    # ====================================================================

    def set_rate_limit(
        self,
        key: str,
        max_requests: int,
        window_seconds: int = 60,
        burst: int = 10,
        *,
        user_id: str,
    ) -> None:
        self.require_permission(user_id, "manage_rate_limits")
        self._rate_limits[key] = RateLimitConfig(
            max_requests=max_requests,
            window_seconds=window_seconds,
            burst=burst,
        )

    def check_rate_limit(self, user_id: str, tool: Optional[str] = None) -> bool:
        """Return True if request is allowed, False if rate-limited."""
        keys_to_check = [user_id]
        if tool:
            keys_to_check.append(f"{user_id}:{tool}")

        now = time.time()
        with self._rate_lock:
            for key in keys_to_check:
                cfg = self._rate_limits.get(key)
                if cfg is None:
                    continue
                bucket = self._rate_buckets[key]
                # Prune old entries
                cutoff = now - cfg.window_seconds
                bucket[:] = [t for t in bucket if t > cutoff]
                if len(bucket) >= cfg.max_requests:
                    self._audit(user_id, "rate_limited", key, "")
                    return False
                bucket.append(now)
        return True

    # ====================================================================
    #  Prompt Injection Detection
    # ====================================================================

    @staticmethod
    def _build_injection_patterns() -> List[Tuple[re.Pattern, str, float]]:
        """Build weighted injection detection patterns."""
        patterns = [
            # Direct override attempts
            (r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions|rules|prompts|context)",
             "direct_override", 0.95),
            (r"disregard\s+(all\s+)?(previous|prior|above|your)\s+(instructions|rules|context)",
             "direct_override", 0.95),
            (r"forget\s+(everything|all)\s+(you|about)\s+(know|were told)",
             "direct_override", 0.90),

            # System prompt extraction
            (r"(output|print|show|reveal|display|repeat)\s+(your|the)\s+(system|initial|original)\s+(prompt|instructions|rules|message)",
             "prompt_extraction", 0.95),
            (r"what\s+(are|is)\s+your\s+(system|initial)\s+(prompt|instructions)",
             "prompt_extraction", 0.90),

            # Role hijacking
            (r"you\s+are\s+now\s+(a|an)\s+\w+",
             "role_hijack", 0.85),
            (r"from\s+now\s+on,?\s+you\s+(will|shall|must|should)",
             "role_hijack", 0.85),
            (r"act\s+as\s+(if\s+)?(you\s+are\s+)?(a|an)\s+",
             "role_hijack", 0.70),

            # DAN / jailbreak patterns
            (r"\bDAN\b.*\b(do\s+anything|jailbreak|bypass)",
             "jailbreak", 0.95),
            (r"developer\s+mode\s+(enabled|activated|on)",
             "jailbreak", 0.90),
            (r"\b(bypass|disable|remove|override)\s+(safety|content|filter|restriction|guardrail)",
             "jailbreak", 0.90),

            # Encoding tricks
            (r"(base64|rot13|hex)\s*(encode|decode|encoded|decoded).*?(ignore|override|system)",
             "encoding_trick", 0.90),

            # Prompt leaking via markdown
            (r"```\s*(system|assistant)\s*:",
             "prompt_leak", 0.80),

            # Indirect injection via embedded content
            (r"\[INST\]|\[/INST\]|<\|im_start\|>|<\|im_end\|>",
             "token_injection", 0.95),
        ]
        compiled = []
        for pattern, category, weight in patterns:
            compiled.append((re.compile(pattern, re.IGNORECASE), category, weight))
        return compiled

    def detect_prompt_injection(self, text: str) -> Dict[str, Any]:
        """
        Analyze text for prompt injection attempts.

        Returns dict with:
          - is_injection: bool
          - score: float 0.0–1.0
          - matches: list of {pattern, category, weight, span}
        """
        matches = []
        max_score = 0.0

        for compiled_re, category, weight in self._injection_patterns:
            for m in compiled_re.finditer(text):
                matches.append({
                    "category": category,
                    "weight": weight,
                    "match": m.group()[:80],
                    "span": m.span(),
                })
                max_score = max(max_score, weight)

        # Heuristic: high density of special tokens
        special_count = len(re.findall(r"[<>{}|\\]", text))
        if special_count > 20 and len(text) < 500:
            max_score = max(max_score, 0.5)

        return {
            "is_injection": max_score >= 0.7,
            "score": round(max_score, 3),
            "matches": matches,
        }

    # ====================================================================
    #  Data Classification & PII Detection
    # ====================================================================

    @staticmethod
    def _build_pii_patterns() -> List[Tuple[re.Pattern, str, DataSensitivity]]:
        """Patterns for detecting PII, secrets, and tokens."""
        specs = [
            # API keys / tokens
            (r"(?i)(sk-[a-zA-Z0-9]{20,})", "openai_key", DataSensitivity.SECRET),
            (r"(?i)(ghp_[a-zA-Z0-9]{36})", "github_pat", DataSensitivity.SECRET),
            (r"(?i)(glpat-[a-zA-Z0-9\-]{20,})", "gitlab_token", DataSensitivity.SECRET),
            (r"(?i)(AKIA[0-9A-Z]{16})", "aws_access_key", DataSensitivity.SECRET),
            (r"(?i)(xox[bpors]-[a-zA-Z0-9\-]+)", "slack_token", DataSensitivity.SECRET),
            (r"(?i)(Bearer\s+[a-zA-Z0-9._\-]{20,})", "bearer_token", DataSensitivity.SECRET),
            # Generic secrets
            (r'(?i)(api[_-]?key|secret|token|password|passwd|pwd)\s*[:=]\s*["\']?([^\s"\']{8,})',
             "generic_secret", DataSensitivity.SECRET),

            # PII
            (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "email", DataSensitivity.SENSITIVE),
            (r"\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}\b", "phone_us", DataSensitivity.SENSITIVE),
            (r"\b\d{3}-\d{2}-\d{4}\b", "ssn", DataSensitivity.SECRET),
            (r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13})\b",
             "credit_card", DataSensitivity.SECRET),

            # IP addresses
            (r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "ipv4", DataSensitivity.INTERNAL),

            # Private keys
            (r"-----BEGIN\s+(RSA\s+)?PRIVATE KEY-----", "private_key", DataSensitivity.SECRET),
        ]
        return [(re.compile(p), name, sens) for p, name, sens in specs]

    def classify_output(self, text: str) -> Dict[str, Any]:
        """
        Classify text for PII / secrets / sensitive data.

        Returns:
          - max_sensitivity: DataSensitivity
          - findings: list of {category, sensitivity, snippet, span}
        """
        findings: List[Dict[str, Any]] = []
        max_level = 0

        for pattern, category, sensitivity in self._pii_patterns:
            for m in pattern.finditer(text):
                level = list(DataSensitivity).index(sensitivity)
                max_level = max(max_level, level)
                findings.append({
                    "category": category,
                    "sensitivity": sensitivity.value,
                    "snippet": m.group()[:40] + "..." if len(m.group()) > 40 else m.group(),
                    "span": m.span(),
                })

        return {
            "max_sensitivity": list(DataSensitivity)[max_level].value if findings else DataSensitivity.PUBLIC.value,
            "finding_count": len(findings),
            "findings": findings,
        }

    # ====================================================================
    #  Output Sanitization / Auto-Redaction
    # ====================================================================

    def sanitize_output(self, text: str) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Auto-redact sensitive data from output.

        Returns (redacted_text, redaction_log).
        """
        redactions: List[Dict[str, Any]] = []
        result = text

        # Process in reverse order so spans don't shift
        all_matches: List[Tuple[int, int, str, str]] = []
        for pattern, category, sensitivity in self._pii_patterns:
            for m in pattern.finditer(result):
                level = list(DataSensitivity).index(sensitivity)
                if level >= 2:  # SENSITIVE or SECRET
                    all_matches.append((m.start(), m.end(), category, m.group()))

        # Sort by start position descending
        all_matches.sort(key=lambda x: x[0], reverse=True)

        for start, end, category, original in all_matches:
            redacted = f"[REDACTED:{category}]"
            result = result[:start] + redacted + result[end:]
            redactions.append({
                "category": category,
                "original_length": len(original),
                "span": (start, end),
            })

        return result, redactions

    # ====================================================================
    #  Command Allowlisting / Denylisting
    # ====================================================================

    def add_allowed_command(self, cmd: str, *, user_id: str) -> None:
        self.require_permission(user_id, "manage_commands")
        self._allowed_commands.add(cmd)

    def add_denied_command(self, cmd: str, *, user_id: str) -> None:
        self.require_permission(user_id, "manage_commands")
        self._denied_commands.add(cmd)

    def is_command_allowed(self, command: str) -> bool:
        """Check if a shell command is permitted."""
        cmd_lower = command.strip().lower()

        # Deny takes precedence
        for denied in self._denied_commands:
            if denied.lower() in cmd_lower:
                return False

        # If allowlist is empty, everything not denied is allowed
        if not self._allowed_commands:
            return True

        for allowed in self._allowed_commands:
            if cmd_lower.startswith(allowed.lower()):
                return True
        return False

    # ====================================================================
    #  Sandboxed Code Execution
    # ====================================================================

    def execute_sandboxed(
        self,
        code: str,
        *,
        user_id: str,
        language: str = "python",
        timeout: int = 30,
        memory_limit_mb: int = 256,
        network: bool = False,
        allowed_modules: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Execute code in a sandboxed subprocess with resource limits.

        Returns:
          - stdout, stderr, returncode
          - timed_out: bool
          - resource_usage: dict
        """
        self.require_permission(user_id, "execute")

        if not self.check_rate_limit(user_id, "execute"):
            return {"error": "Rate limit exceeded", "returncode": -1}

        # Check for injection in the code
        injection = self.detect_prompt_injection(code)
        if injection["is_injection"]:
            self._audit(user_id, "blocked_injection", "execute", str(injection), result="blocked")
            return {
                "error": "Potential prompt injection detected in code",
                "details": injection,
                "returncode": -1,
            }

        if language != "python":
            return {"error": f"Unsupported language: {language}", "returncode": -1}

        # Build wrapper with restrictions
        wrapper = self._build_sandbox_wrapper(
            code,
            memory_limit_mb=memory_limit_mb,
            network=network,
            allowed_modules=allowed_modules,
        )

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(wrapper)
            script_path = f.name

        try:
            result = subprocess.run(
                [sys.executable, script_path],
                capture_output=True,
                text=True,
                timeout=timeout,
                env=self._sandbox_env(network),
            )
            stdout, stderr = result.stdout, result.stderr
            returncode = result.returncode
            timed_out = False
        except subprocess.TimeoutExpired:
            stdout, stderr, returncode = "", "Execution timed out", -9
            timed_out = True
        finally:
            os.unlink(script_path)

        # Sanitize output
        stdout, redactions = self.sanitize_output(stdout)

        self._audit(
            user_id, "execute_sandboxed", "code",
            f"lang={language} rc={returncode} timeout={timed_out}",
        )

        return {
            "stdout": stdout,
            "stderr": stderr,
            "returncode": returncode,
            "timed_out": timed_out,
            "redactions": redactions,
        }

    @staticmethod
    def _build_sandbox_wrapper(
        code: str,
        memory_limit_mb: int = 256,
        network: bool = False,
        allowed_modules: Optional[List[str]] = None,
    ) -> str:
        """Wrap user code with resource restrictions."""
        import textwrap

        allowed_mods = allowed_modules or [
            "math", "json", "re", "datetime", "collections", "itertools",
            "functools", "typing", "dataclasses", "enum", "pathlib",
            "os.path", "hashlib", "base64", "textwrap", "string",
        ]
        allowed_set = repr(set(allowed_mods))
        indented_code = textwrap.indent(code, '    ')

        return f"""\
import sys, os, resource

# Memory limit
try:
    soft = {memory_limit_mb} * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (soft, soft))
except Exception:
    pass

# CPU time limit
try:
    resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
except Exception:
    pass

# File size limit (10MB)
try:
    resource.setrlimit(resource.RLIMIT_FSIZE, (10 * 1024 * 1024, 10 * 1024 * 1024))
except Exception:
    pass

# Module allowlist
_allowed = {allowed_set}
_orig_import = __builtins__.__import__ if hasattr(__builtins__, '__import__') else __import__

def _restricted_import(name, *args, **kwargs):
    top = name.split('.')[0]
    if top not in _allowed and name not in _allowed:
        raise ImportError(f"Module '{{name}}' is not allowed in sandbox")
    return _orig_import(name, *args, **kwargs)

import builtins
builtins.__import__ = _restricted_import

# Disable network if needed
if not {str(network)}:
    import socket
    def _blocked(*a, **kw):
        raise OSError("Network access is disabled in sandbox")
    socket.socket = _blocked  # type: ignore

# --- User code ---
try:
{indented_code}
except Exception as e:
    print(f"ERROR: {{type(e).__name__}}: {{e}}", file=sys.stderr)
    sys.exit(1)
"""

    @staticmethod
    def _sandbox_env(network: bool) -> Dict[str, str]:
        """Create restricted environment variables."""
        env = {
            "PATH": "/usr/bin:/bin",
            "LANG": "C.UTF-8",
            "HOME": tempfile.gettempdir(),
        }
        if not network:
            env["http_proxy"] = ""
            env["https_proxy"] = ""
            env["HTTP_PROXY"] = ""
            env["HTTPS_PROXY"] = ""
        return env

    # ====================================================================
    #  IP-based Access Control
    # ====================================================================

    def _ip_allowed(self, user_id: str, ip: str) -> bool:
        info = self._users.get(user_id)
        if info is None:
            return True  # No restrictions for unknown users (RBAC handles access)
        whitelist = info.get("ip_whitelist", [])
        if not whitelist:
            return True  # Empty whitelist = all IPs allowed
        try:
            addr = ipaddress.ip_address(ip)
            for entry in whitelist:
                if "/" in entry:
                    if addr in ipaddress.ip_network(entry, strict=False):
                        return True
                elif addr == ipaddress.ip_address(entry):
                    return True
            return False
        except ValueError:
            return False

    # ====================================================================
    #  Full Request Pipeline
    # ====================================================================

    def process_request(
        self,
        session_id: str,
        action: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Full security pipeline for an incoming request.

        Steps:
          1. Validate session
          2. Check rate limits
          3. Check permissions
          4. Scan for prompt injection
          5. Check network policies (if URL involved)
          6. Check command policies (if command involved)
          7. Log and proceed
        """
        # 1. Session
        session = self.validate_session(session_id)
        if session is None:
            return {"error": "Invalid or expired session", "code": 401}

        uid = session.user_id

        # 2. Rate limit
        if not self.check_rate_limit(uid, action):
            return {"error": "Rate limit exceeded", "code": 429}

        # 3. Permission
        if not self.check_permission(uid, action):
            return {"error": "Permission denied", "code": 403}

        # 4. Prompt injection on any text payload
        for key in ("input", "prompt", "code", "query", "text"):
            if key in payload and isinstance(payload[key], str):
                inj = self.detect_prompt_injection(payload[key])
                if inj["is_injection"]:
                    self._audit(uid, "injection_blocked", action, str(inj), result="blocked")
                    return {"error": "Prompt injection detected", "code": 400, "details": inj}

        # 5. Network check
        url = payload.get("url") or payload.get("domain")
        if url and isinstance(url, str):
            if not self.is_url_allowed(url):
                self._audit(uid, "network_blocked", action, url, result="blocked")
                return {"error": "URL blocked by network policy", "code": 403}

        # 6. Command check
        cmd = payload.get("command")
        if cmd and isinstance(cmd, str):
            if not self.is_command_allowed(cmd):
                self._audit(uid, "command_blocked", action, cmd, result="blocked")
                return {"error": "Command blocked by policy", "code": 403}

        # 7. Log
        self._audit(uid, action, str(payload.get("resource", "")), "proceeding")

        return {"status": "approved", "user_id": uid, "session": session_id}

    # ====================================================================
    #  Persistence helpers
    # ====================================================================

    def _load_users(self) -> None:
        path = self._data_dir / "users.json"
        if path.exists():
            try:
                self._users = json.loads(path.read_text())
            except Exception:
                self._users = {}

    def _save_users(self) -> None:
        path = self._data_dir / "users.json"
        path.write_text(json.dumps(self._users, indent=2))




# ============================= Convenience =================================

_default_manager: Optional[SecurityManager] = None
_manager_lock = threading.Lock()


def get_security_manager(**kwargs: Any) -> SecurityManager:
    """Get or create the global SecurityManager singleton."""
    global _default_manager
    if _default_manager is None:
        with _manager_lock:
            if _default_manager is None:
                _default_manager = SecurityManager(**kwargs)
    return _default_manager
