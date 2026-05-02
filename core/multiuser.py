"""
🟣 Rally Agent — Multi-User System
=====================================
User profiles, authentication (JWT + bcrypt), RBAC, shared workspaces,
conversation ownership, config overrides, quotas, activity logging, sessions.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import secrets
import threading
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("rally.multiuser")

# Optional heavy deps
try:
    import bcrypt
    HAS_BCRYPT = True
except ImportError:
    HAS_BCRYPT = False
    logger.debug("bcrypt not installed — using hashlib fallback for password hashing")

try:
    import jwt as pyjwt
    HAS_JWT = True
except ImportError:
    HAS_JWT = False
    logger.debug("PyJWT not installed — using custom token implementation")


# ═══════════════════════════════════════════════════════════════
# 📊 Data Types
# ═══════════════════════════════════════════════════════════════

class Role(Enum):
    """User roles with hierarchical permissions."""
    VIEWER = "viewer"
    USER = "user"
    ADMIN = "admin"


# Role hierarchy: higher number = more permissions
ROLE_HIERARCHY: Dict[Role, int] = {
    Role.VIEWER: 0,
    Role.USER: 1,
    Role.ADMIN: 2,
}

# Permissions per role
ROLE_PERMISSIONS: Dict[Role, Set[str]] = {
    Role.VIEWER: {
        "read", "view_history", "view_workspaces",
    },
    Role.USER: {
        "read", "write", "execute", "view_history", "manage_own_conversations",
        "manage_own_preferences", "create_workspace", "join_workspace",
    },
    Role.ADMIN: {
        "read", "write", "execute", "view_history", "manage_own_conversations",
        "manage_own_preferences", "create_workspace", "join_workspace",
        "manage_users", "manage_all_workspaces", "view_audit_log",
        "manage_quotas", "manage_system", "delete_any",
    },
}


@dataclass
class UserProfile:
    """A user profile with preferences and metadata."""
    user_id: str
    username: str
    display_name: str = ""
    email: str = ""
    role: Role = Role.USER
    created_at: float = field(default_factory=time.time)
    last_login: float = 0.0
    is_active: bool = True
    avatar_url: str = ""

    # Preferences (user-specific config overrides)
    preferences: Dict[str, Any] = field(default_factory=dict)

    # Quotas
    quota_requests_per_day: int = 1000
    quota_tokens_per_day: int = 1_000_000
    quota_conversations: int = 100

    # Usage tracking
    total_requests: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0

    # Workspace memberships
    workspace_ids: List[str] = field(default_factory=list)

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def has_permission(self, permission: str) -> bool:
        """Check if user has a specific permission."""
        return permission in ROLE_PERMISSIONS.get(self.role, set())

    def to_dict(self, include_sensitive: bool = False) -> Dict[str, Any]:
        data = {
            "user_id": self.user_id,
            "username": self.username,
            "display_name": self.display_name,
            "email": self.email,
            "role": self.role.value,
            "created_at": self.created_at,
            "last_login": self.last_login,
            "is_active": self.is_active,
            "avatar_url": self.avatar_url,
            "preferences": self.preferences,
            "total_requests": self.total_requests,
            "total_tokens": self.total_tokens,
            "total_cost_usd": round(self.total_cost_usd, 4),
            "workspace_ids": self.workspace_ids,
            "quota_requests_per_day": self.quota_requests_per_day,
            "quota_tokens_per_day": self.quota_tokens_per_day,
            "quota_conversations": self.quota_conversations,
        }
        if include_sensitive:
            data["metadata"] = self.metadata
        return data


@dataclass
class SessionInfo:
    """An active user session."""
    session_id: str
    user_id: str
    token: str
    created_at: float = field(default_factory=time.time)
    expires_at: float = 0.0
    last_active: float = field(default_factory=time.time)
    ip_address: str = ""
    user_agent: str = ""
    is_valid: bool = True

    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires_at if self.expires_at > 0 else False


@dataclass
class ConversationMeta:
    """Metadata for a conversation (ownership, privacy)."""
    conversation_id: str
    owner_id: str
    title: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    is_shared: bool = False
    shared_with: List[str] = field(default_factory=list)  # user_ids
    workspace_id: Optional[str] = None
    message_count: int = 0
    total_tokens: int = 0
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Workspace:
    """A shared workspace for team collaboration."""
    workspace_id: str
    name: str
    description: str = ""
    owner_id: str = ""
    created_at: float = field(default_factory=time.time)
    member_ids: List[str] = field(default_factory=list)
    is_public: bool = False

    # Shared memory/knowledge base
    shared_memory: Dict[str, Any] = field(default_factory=dict)
    knowledge_base: List[Dict[str, Any]] = field(default_factory=list)

    # Workspace settings
    settings: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ActivityLogEntry:
    """A user activity log entry."""
    log_id: str
    timestamp: float
    user_id: str
    action: str
    resource: str
    details: Dict[str, Any] = field(default_factory=dict)
    ip_address: str = ""


@dataclass
class UsageQuotaSnapshot:
    """Current quota usage for a user."""
    user_id: str
    date: str  # YYYY-MM-DD
    requests_used: int = 0
    tokens_used: int = 0
    cost_usd: float = 0.0
    conversations_created: int = 0


# ═══════════════════════════════════════════════════════════════
# 🔐 Password Hashing
# ═══════════════════════════════════════════════════════════════

class PasswordHasher:
    """Hash and verify passwords. Uses bcrypt if available, SHA-256+salt fallback."""

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password for storage."""
        if HAS_BCRYPT:
            salt = bcrypt.gensalt(rounds=12)
            return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")
        else:
            # Fallback: SHA-256 with random salt
            salt = secrets.token_hex(32)
            h = hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()
            return f"sha256${salt}${h}"

    @staticmethod
    def verify_password(password: str, hashed: str) -> bool:
        """Verify a password against its hash."""
        if HAS_BCRYPT and not hashed.startswith("sha256$"):
            return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
        elif hashed.startswith("sha256$"):
            parts = hashed.split("$")
            if len(parts) != 3:
                return False
            salt = parts[1]
            expected = parts[2]
            h = hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()
            return secrets.compare_digest(h, expected)
        return False


# ═══════════════════════════════════════════════════════════════
# 🎫 Token Manager (JWT)
# ═══════════════════════════════════════════════════════════════

class TokenManager:
    """Create and verify JWT tokens. Falls back to HMAC-SHA256 if PyJWT is absent."""

    def __init__(self, secret_key: Optional[str] = None, token_ttl_hours: int = 24):
        self.secret_key = secret_key or os.environ.get(
            "RALLY_JWT_SECRET",
            secrets.token_hex(32),
        )
        self.token_ttl = timedelta(hours=token_ttl_hours)

    def create_token(self, user_id: str, role: str, extra: Optional[Dict[str, Any]] = None) -> str:
        """Create a signed JWT token."""
        now = datetime.now(timezone.utc)
        payload = {
            "sub": user_id,
            "role": role,
            "iat": now,
            "exp": now + self.token_ttl,
            "jti": str(uuid.uuid4())[:8],
        }
        if extra:
            payload.update(extra)

        if HAS_JWT:
            return pyjwt.encode(payload, self.secret_key, algorithm="HS256")
        else:
            # Manual HMAC-SHA256 token
            import base64
            header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode()).decode().rstrip("=")
            body = base64.urlsafe_b64encode(json.dumps(payload, default=str).encode()).decode().rstrip("=")
            sig_input = f"{header}.{body}"
            sig = hmac.new(self.secret_key.encode(), sig_input.encode(), hashlib.sha256).digest()
            sig_b64 = base64.urlsafe_b64encode(sig).decode().rstrip("=")
            return f"{header}.{body}.{sig_b64}"

    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify and decode a token. Returns payload or None if invalid."""
        try:
            if HAS_JWT:
                return pyjwt.decode(token, self.secret_key, algorithms=["HS256"])
            else:
                import base64, hmac as _hmac
                parts = token.split(".")
                if len(parts) != 3:
                    return None
                header, body, sig_b64 = parts
                sig_input = f"{header}.{body}"
                expected_sig = _hmac.new(
                    self.secret_key.encode(), sig_input.encode(), hashlib.sha256
                ).digest()
                actual_sig = base64.urlsafe_b64decode(sig_b64 + "==")
                if not _hmac.compare_digest(expected_sig, actual_sig):
                    return None
                # Decode payload
                padded = body + "=" * (4 - len(body) % 4)
                payload = json.loads(base64.urlsafe_b64decode(padded))
                # Check expiry
                if "exp" in payload:
                    exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
                    if datetime.now(timezone.utc) > exp:
                        return None
                return payload
        except Exception as e:
            logger.debug(f"Token verification failed: {e}")
            return None


# ═══════════════════════════════════════════════════════════════
# 💾 Data Store (file-based)
# ═══════════════════════════════════════════════════════════════

class UserStore:
    """Persistent storage for user data (JSON files)."""

    def __init__(self, data_dir: Optional[str] = None):
        self.data_dir = data_dir or str(Path.home() / ".rally-agent" / "users")
        self._lock = threading.Lock()

        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(os.path.join(self.data_dir, "profiles"), exist_ok=True)
        os.makedirs(os.path.join(self.data_dir, "sessions"), exist_ok=True)
        os.makedirs(os.path.join(self.data_dir, "workspaces"), exist_ok=True)
        os.makedirs(os.path.join(self.data_dir, "conversations"), exist_ok=True)
        os.makedirs(os.path.join(self.data_dir, "activity"), exist_ok=True)
        os.makedirs(os.path.join(self.data_dir, "quotas"), exist_ok=True)

    # --- Users ---

    def save_user(self, profile: UserProfile) -> None:
        path = os.path.join(self.data_dir, "profiles", f"{profile.user_id}.json")
        with self._lock:
            with open(path, "w") as f:
                json.dump(profile.to_dict(include_sensitive=True), f, indent=2, default=str)

    def load_user(self, user_id: str) -> Optional[UserProfile]:
        path = os.path.join(self.data_dir, "profiles", f"{user_id}.json")
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r") as f:
                data = json.load(f)
            role = Role(data.get("role", "user"))
            profile = UserProfile(
                user_id=data["user_id"],
                username=data["username"],
                display_name=data.get("display_name", ""),
                email=data.get("email", ""),
                role=role,
                created_at=data.get("created_at", 0),
                last_login=data.get("last_login", 0),
                is_active=data.get("is_active", True),
                avatar_url=data.get("avatar_url", ""),
                preferences=data.get("preferences", {}),
                quota_requests_per_day=data.get("quota_requests_per_day", 1000),
                quota_tokens_per_day=data.get("quota_tokens_per_day", 1_000_000),
                quota_conversations=data.get("quota_conversations", 100),
                total_requests=data.get("total_requests", 0),
                total_tokens=data.get("total_tokens", 0),
                total_cost_usd=data.get("total_cost_usd", 0.0),
                workspace_ids=data.get("workspace_ids", []),
                metadata=data.get("metadata", {}),
            )
            return profile
        except Exception as e:
            logger.error(f"Failed to load user '{user_id}': {e}")
            return None

    def list_users(self) -> List[UserProfile]:
        profiles_dir = os.path.join(self.data_dir, "profiles")
        users = []
        for fname in os.listdir(profiles_dir):
            if fname.endswith(".json"):
                uid = fname[:-5]
                user = self.load_user(uid)
                if user:
                    users.append(user)
        return users

    def delete_user(self, user_id: str) -> bool:
        path = os.path.join(self.data_dir, "profiles", f"{user_id}.json")
        with self._lock:
            if os.path.exists(path):
                os.remove(path)
                return True
        return False

    # --- Sessions ---

    def save_session(self, session: SessionInfo) -> None:
        path = os.path.join(self.data_dir, "sessions", f"{session.session_id}.json")
        with self._lock:
            with open(path, "w") as f:
                json.dump({
                    "session_id": session.session_id,
                    "user_id": session.user_id,
                    "token": session.token,
                    "created_at": session.created_at,
                    "expires_at": session.expires_at,
                    "last_active": session.last_active,
                    "ip_address": session.ip_address,
                    "user_agent": session.user_agent,
                    "is_valid": session.is_valid,
                }, f, indent=2)

    def load_session(self, session_id: str) -> Optional[SessionInfo]:
        path = os.path.join(self.data_dir, "sessions", f"{session_id}.json")
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r") as f:
                data = json.load(f)
            return SessionInfo(**data)
        except Exception:
            return None

    def delete_session(self, session_id: str) -> None:
        path = os.path.join(self.data_dir, "sessions", f"{session_id}.json")
        with self._lock:
            if os.path.exists(path):
                os.remove(path)

    def cleanup_expired_sessions(self) -> int:
        """Remove expired sessions. Returns count removed."""
        sessions_dir = os.path.join(self.data_dir, "sessions")
        removed = 0
        with self._lock:
            for fname in os.listdir(sessions_dir):
                if not fname.endswith(".json"):
                    continue
                try:
                    path = os.path.join(sessions_dir, fname)
                    with open(path, "r") as f:
                        data = json.load(f)
                    if data.get("expires_at", 0) > 0 and time.time() > data["expires_at"]:
                        os.remove(path)
                        removed += 1
                except Exception:
                    pass
        return removed

    # --- Workspaces ---

    def save_workspace(self, workspace: Workspace) -> None:
        path = os.path.join(self.data_dir, "workspaces", f"{workspace.workspace_id}.json")
        with self._lock:
            with open(path, "w") as f:
                json.dump({
                    "workspace_id": workspace.workspace_id,
                    "name": workspace.name,
                    "description": workspace.description,
                    "owner_id": workspace.owner_id,
                    "created_at": workspace.created_at,
                    "member_ids": workspace.member_ids,
                    "is_public": workspace.is_public,
                    "shared_memory": workspace.shared_memory,
                    "knowledge_base": workspace.knowledge_base,
                    "settings": workspace.settings,
                    "metadata": workspace.metadata,
                }, f, indent=2, default=str)

    def load_workspace(self, workspace_id: str) -> Optional[Workspace]:
        path = os.path.join(self.data_dir, "workspaces", f"{workspace_id}.json")
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r") as f:
                data = json.load(f)
            return Workspace(**data)
        except Exception as e:
            logger.error(f"Failed to load workspace '{workspace_id}': {e}")
            return None

    def list_workspaces(self) -> List[Workspace]:
        ws_dir = os.path.join(self.data_dir, "workspaces")
        workspaces = []
        for fname in os.listdir(ws_dir):
            if fname.endswith(".json"):
                ws = self.load_workspace(fname[:-5])
                if ws:
                    workspaces.append(ws)
        return workspaces

    def delete_workspace(self, workspace_id: str) -> bool:
        path = os.path.join(self.data_dir, "workspaces", f"{workspace_id}.json")
        with self._lock:
            if os.path.exists(path):
                os.remove(path)
                return True
        return False

    # --- Conversations ---

    def save_conversation_meta(self, meta: ConversationMeta) -> None:
        path = os.path.join(self.data_dir, "conversations", f"{meta.conversation_id}.json")
        with self._lock:
            with open(path, "w") as f:
                json.dump({
                    "conversation_id": meta.conversation_id,
                    "owner_id": meta.owner_id,
                    "title": meta.title,
                    "created_at": meta.created_at,
                    "updated_at": meta.updated_at,
                    "is_shared": meta.is_shared,
                    "shared_with": meta.shared_with,
                    "workspace_id": meta.workspace_id,
                    "message_count": meta.message_count,
                    "total_tokens": meta.total_tokens,
                    "tags": meta.tags,
                    "metadata": meta.metadata,
                }, f, indent=2)

    def load_conversation_meta(self, conversation_id: str) -> Optional[ConversationMeta]:
        path = os.path.join(self.data_dir, "conversations", f"{conversation_id}.json")
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r") as f:
                data = json.load(f)
            return ConversationMeta(**data)
        except Exception:
            return None

    def list_user_conversations(self, user_id: str) -> List[ConversationMeta]:
        """List conversations owned by or shared with a user."""
        conv_dir = os.path.join(self.data_dir, "conversations")
        results = []
        for fname in os.listdir(conv_dir):
            if not fname.endswith(".json"):
                continue
            meta = self.load_conversation_meta(fname[:-5])
            if meta and (meta.owner_id == user_id or user_id in meta.shared_with):
                results.append(meta)
        return results

    # --- Activity Log ---

    def log_activity(self, entry: ActivityLogEntry) -> None:
        date_str = datetime.fromtimestamp(entry.timestamp, tz=timezone.utc).strftime("%Y-%m-%d")
        path = os.path.join(self.data_dir, "activity", f"{date_str}.jsonl")
        with self._lock:
            with open(path, "a") as f:
                f.write(json.dumps({
                    "log_id": entry.log_id,
                    "timestamp": entry.timestamp,
                    "user_id": entry.user_id,
                    "action": entry.action,
                    "resource": entry.resource,
                    "details": entry.details,
                    "ip_address": entry.ip_address,
                }, default=str) + "\n")

    def get_activity_log(
        self,
        user_id: Optional[str] = None,
        date: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        activity_dir = os.path.join(self.data_dir, "activity")
        entries: List[Dict[str, Any]] = []

        files = sorted(os.listdir(activity_dir), reverse=True)
        if date:
            files = [f for f in files if f.startswith(date)]

        for fname in files:
            if not fname.endswith(".jsonl"):
                continue
            path = os.path.join(activity_dir, fname)
            try:
                with open(path, "r") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        entry = json.loads(line)
                        if user_id and entry.get("user_id") != user_id:
                            continue
                        entries.append(entry)
                        if len(entries) >= limit:
                            return entries
            except Exception:
                continue
        return entries

    # --- Quotas ---

    def save_quota(self, snapshot: UsageQuotaSnapshot) -> None:
        path = os.path.join(self.data_dir, "quotas", f"{snapshot.user_id}_{snapshot.date}.json")
        with self._lock:
            with open(path, "w") as f:
                json.dump({
                    "user_id": snapshot.user_id,
                    "date": snapshot.date,
                    "requests_used": snapshot.requests_used,
                    "tokens_used": snapshot.tokens_used,
                    "cost_usd": snapshot.cost_usd,
                    "conversations_created": snapshot.conversations_created,
                }, f, indent=2)

    def load_quota(self, user_id: str, date: str) -> Optional[UsageQuotaSnapshot]:
        path = os.path.join(self.data_dir, "quotas", f"{user_id}_{date}.json")
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r") as f:
                data = json.load(f)
            return UsageQuotaSnapshot(**data)
        except Exception:
            return None


# ═══════════════════════════════════════════════════════════════
# 👥 Multi-User Manager
# ═══════════════════════════════════════════════════════════════

class MultiUserManager:
    """Central manager for users, authentication, workspaces, and quotas.

    Usage:
        manager = MultiUserManager()
        await manager.initialize()

        # Create admin user
        user = await manager.create_user("admin", "securepass", role=Role.ADMIN)

        # Authenticate
        session = await manager.authenticate("admin", "securepass")

        # Verify session
        profile = await manager.verify_session(session.session_id)
    """

    def __init__(
        self,
        data_dir: Optional[str] = None,
        jwt_secret: Optional[str] = None,
        session_ttl_hours: int = 24,
        default_quota_requests: int = 1000,
        default_quota_tokens: int = 1_000_000,
    ):
        self.store = UserStore(data_dir=data_dir)
        self.token_manager = TokenManager(secret_key=jwt_secret, token_ttl_hours=session_ttl_hours)
        self.session_ttl_hours = session_ttl_hours
        self.default_quota_requests = default_quota_requests
        self.default_quota_tokens = default_quota_tokens

        # In-memory caches
        self._sessions: Dict[str, SessionInfo] = {}
        self._users: Dict[str, UserProfile] = {}
        self._username_index: Dict[str, str] = {}  # username -> user_id
        self._lock = threading.Lock()

        self._initialized = False

    async def initialize(self) -> None:
        """Load all user data from disk."""
        users = self.store.list_users()
        for user in users:
            self._users[user.user_id] = user
            self._username_index[user.username] = user.user_id
        logger.info(f"Loaded {len(users)} users")
        self._initialized = True

    # --- User Management ---

    async def create_user(
        self,
        username: str,
        password: str,
        display_name: str = "",
        email: str = "",
        role: Role = Role.USER,
    ) -> UserProfile:
        """Create a new user."""
        if username in self._username_index:
            raise ValueError(f"Username '{username}' already exists")

        user_id = str(uuid.uuid4())[:12]
        hashed = PasswordHasher.hash_password(password)

        profile = UserProfile(
            user_id=user_id,
            username=username,
            display_name=display_name or username,
            email=email,
            role=role,
            quota_requests_per_day=self.default_quota_requests,
            quota_tokens_per_day=self.default_quota_tokens,
            metadata={"password_hash": hashed},
        )

        with self._lock:
            self._users[user_id] = profile
            self._username_index[username] = user_id

        self.store.save_user(profile)
        self._log_activity(user_id, "user_created", "user", {"username": username, "role": role.value})
        logger.info(f"Created user '{username}' (id={user_id}, role={role.value})")
        return profile

    async def update_user(self, user_id: str, **kwargs: Any) -> UserProfile:
        """Update user profile fields."""
        profile = self._users.get(user_id)
        if not profile:
            raise ValueError(f"User '{user_id}' not found")

        for key, value in kwargs.items():
            if key == "role" and isinstance(value, str):
                value = Role(value)
            if hasattr(profile, key):
                setattr(profile, key, value)

        self.store.save_user(profile)
        self._log_activity(user_id, "user_updated", "user", {"fields": list(kwargs.keys())})
        return profile

    async def change_password(self, user_id: str, old_password: str, new_password: str) -> bool:
        """Change a user's password."""
        profile = self._users.get(user_id)
        if not profile:
            raise ValueError(f"User '{user_id}' not found")

        old_hash = profile.metadata.get("password_hash", "")
        if not PasswordHasher.verify_password(old_password, old_hash):
            raise PermissionError("Current password is incorrect")

        profile.metadata["password_hash"] = PasswordHasher.hash_password(new_password)
        self.store.save_user(profile)
        self._log_activity(user_id, "password_changed", "user", {})
        return True

    async def delete_user(self, user_id: str, admin_id: Optional[str] = None) -> bool:
        """Delete a user (admin only)."""
        profile = self._users.get(user_id)
        if not profile:
            return False

        with self._lock:
            self._users.pop(user_id, None)
            self._username_index.pop(profile.username, None)

        self.store.delete_user(user_id)
        self._log_activity(
            admin_id or user_id, "user_deleted", "user",
            {"deleted_user": user_id, "username": profile.username},
        )
        return True

    async def get_user(self, user_id: str) -> Optional[UserProfile]:
        """Get a user profile."""
        return self._users.get(user_id)

    async def get_user_by_username(self, username: str) -> Optional[UserProfile]:
        """Look up user by username."""
        uid = self._username_index.get(username)
        return self._users.get(uid) if uid else None

    async def list_users(self, role: Optional[Role] = None, active_only: bool = True) -> List[Dict[str, Any]]:
        """List all users, optionally filtered."""
        users = list(self._users.values())
        if role:
            users = [u for u in users if u.role == role]
        if active_only:
            users = [u for u in users if u.is_active]
        return [u.to_dict() for u in users]

    # --- Authentication ---

    async def authenticate(
        self,
        username: str,
        password: str,
        ip_address: str = "",
        user_agent: str = "",
    ) -> SessionInfo:
        """Authenticate a user and create a session."""
        profile = await self.get_user_by_username(username)
        if not profile:
            raise PermissionError("Invalid username or password")

        if not profile.is_active:
            raise PermissionError("Account is deactivated")

        stored_hash = profile.metadata.get("password_hash", "")
        if not PasswordHasher.verify_password(password, stored_hash):
            raise PermissionError("Invalid username or password")

        # Create session
        session_id = str(uuid.uuid4())[:12]
        now = time.time()
        token = self.token_manager.create_token(
            user_id=profile.user_id,
            role=profile.role.value,
            extra={"session_id": session_id},
        )

        session = SessionInfo(
            session_id=session_id,
            user_id=profile.user_id,
            token=token,
            created_at=now,
            expires_at=now + (self.session_ttl_hours * 3600),
            last_active=now,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        with self._lock:
            self._sessions[session_id] = session

        # Update last login
        profile.last_login = now
        self.store.save_user(profile)
        self.store.save_session(session)
        self._log_activity(profile.user_id, "login", "session", {
            "session_id": session_id,
            "ip": ip_address,
        })

        logger.info(f"User '{username}' authenticated (session={session_id})")
        return session

    async def verify_session(self, session_id: str) -> Optional[UserProfile]:
        """Verify a session and return the user profile."""
        session = self._sessions.get(session_id)
        if not session:
            session = self.store.load_session(session_id)
            if session:
                self._sessions[session_id] = session

        if not session or not session.is_valid:
            return None

        if session.is_expired:
            session.is_valid = False
            self.store.delete_session(session_id)
            self._sessions.pop(session_id, None)
            return None

        # Verify token
        payload = self.token_manager.verify_token(session.token)
        if not payload:
            session.is_valid = False
            return None

        session.last_active = time.time()
        return self._users.get(session.user_id)

    async def verify_token(self, token: str) -> Optional[UserProfile]:
        """Verify a JWT token directly (without session lookup)."""
        payload = self.token_manager.verify_token(token)
        if not payload:
            return None
        user_id = payload.get("sub")
        return self._users.get(user_id)

    async def logout(self, session_id: str) -> bool:
        """Invalidate a session."""
        session = self._sessions.pop(session_id, None)
        if session:
            session.is_valid = False
            self.store.delete_session(session_id)
            self._log_activity(session.user_id, "logout", "session", {"session_id": session_id})
            return True
        return False

    async def logout_all(self, user_id: str) -> int:
        """Invalidate all sessions for a user."""
        count = 0
        for sid, session in list(self._sessions.items()):
            if session.user_id == user_id:
                session.is_valid = False
                self.store.delete_session(sid)
                self._sessions.pop(sid, None)
                count += 1
        self._log_activity(user_id, "logout_all", "session", {"sessions_cleared": count})
        return count

    async def cleanup_sessions(self) -> int:
        """Remove expired sessions."""
        removed = self.store.cleanup_expired_sessions()
        with self._lock:
            expired = [sid for sid, s in self._sessions.items() if s.is_expired]
            for sid in expired:
                self._sessions.pop(sid, None)
            removed += len(expired)
        return removed

    # --- Permissions ---

    async def check_permission(self, user_id: str, permission: str) -> bool:
        """Check if a user has a specific permission."""
        profile = self._users.get(user_id)
        if not profile or not profile.is_active:
            return False
        return profile.has_permission(permission)

    async def require_permission(self, user_id: str, permission: str) -> None:
        """Raise PermissionError if user lacks a permission."""
        if not await self.check_permission(user_id, permission):
            raise PermissionError(f"User '{user_id}' lacks permission: {permission}")

    # --- Workspaces ---

    async def create_workspace(
        self,
        owner_id: str,
        name: str,
        description: str = "",
        is_public: bool = False,
    ) -> Workspace:
        """Create a shared workspace."""
        await self.require_permission(owner_id, "create_workspace")

        ws_id = str(uuid.uuid4())[:12]
        workspace = Workspace(
            workspace_id=ws_id,
            name=name,
            description=description,
            owner_id=owner_id,
            member_ids=[owner_id],
            is_public=is_public,
        )

        self.store.save_workspace(workspace)

        # Add workspace to owner's profile
        profile = self._users.get(owner_id)
        if profile and ws_id not in profile.workspace_ids:
            profile.workspace_ids.append(ws_id)
            self.store.save_user(profile)

        self._log_activity(owner_id, "workspace_created", "workspace", {
            "workspace_id": ws_id,
            "name": name,
        })
        return workspace

    async def join_workspace(self, user_id: str, workspace_id: str) -> bool:
        """Join a workspace."""
        workspace = self.store.load_workspace(workspace_id)
        if not workspace:
            raise ValueError(f"Workspace '{workspace_id}' not found")

        if user_id in workspace.member_ids:
            return True  # already a member

        workspace.member_ids.append(user_id)
        self.store.save_workspace(workspace)

        profile = self._users.get(user_id)
        if profile and workspace_id not in profile.workspace_ids:
            profile.workspace_ids.append(workspace_id)
            self.store.save_user(profile)

        self._log_activity(user_id, "workspace_joined", "workspace", {"workspace_id": workspace_id})
        return True

    async def leave_workspace(self, user_id: str, workspace_id: str) -> bool:
        """Leave a workspace."""
        workspace = self.store.load_workspace(workspace_id)
        if not workspace:
            return False

        if user_id == workspace.owner_id:
            raise PermissionError("Owner cannot leave their own workspace")

        workspace.member_ids = [m for m in workspace.member_ids if m != user_id]
        self.store.save_workspace(workspace)

        profile = self._users.get(user_id)
        if profile:
            profile.workspace_ids = [w for w in profile.workspace_ids if w != workspace_id]
            self.store.save_user(profile)

        return True

    async def get_workspace(self, workspace_id: str, user_id: Optional[str] = None) -> Optional[Workspace]:
        """Get workspace details."""
        workspace = self.store.load_workspace(workspace_id)
        if not workspace:
            return None
        if user_id and not workspace.is_public and user_id not in workspace.member_ids:
            await self.require_permission(user_id, "manage_all_workspaces")
        return workspace

    async def list_workspaces(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List workspaces (all for admin, own for regular users)."""
        workspaces = self.store.list_workspaces()
        if user_id:
            profile = self._users.get(user_id)
            if profile and profile.role != Role.ADMIN:
                workspaces = [w for w in workspaces if user_id in w.member_ids or w.is_public]
        return [
            {
                "workspace_id": w.workspace_id,
                "name": w.name,
                "description": w.description,
                "owner_id": w.owner_id,
                "member_count": len(w.member_ids),
                "is_public": w.is_public,
                "created_at": w.created_at,
            }
            for w in workspaces
        ]

    async def add_to_shared_memory(self, workspace_id: str, user_id: str, key: str, value: Any) -> None:
        """Add to a workspace's shared memory."""
        workspace = await self.get_workspace(workspace_id, user_id)
        if not workspace:
            raise ValueError(f"Workspace '{workspace_id}' not found")
        if user_id not in workspace.member_ids:
            raise PermissionError("Not a workspace member")

        workspace.shared_memory[key] = value
        self.store.save_workspace(workspace)

    async def add_knowledge(self, workspace_id: str, user_id: str, entry: Dict[str, Any]) -> None:
        """Add to a workspace's knowledge base."""
        workspace = await self.get_workspace(workspace_id, user_id)
        if not workspace:
            raise ValueError(f"Workspace '{workspace_id}' not found")
        if user_id not in workspace.member_ids:
            raise PermissionError("Not a workspace member")

        entry["added_by"] = user_id
        entry["added_at"] = time.time()
        workspace.knowledge_base.append(entry)
        self.store.save_workspace(workspace)

    # --- Conversations ---

    async def create_conversation(
        self,
        owner_id: str,
        title: str = "",
        workspace_id: Optional[str] = None,
    ) -> ConversationMeta:
        """Create a new conversation."""
        conv_id = str(uuid.uuid4())[:12]
        meta = ConversationMeta(
            conversation_id=conv_id,
            owner_id=owner_id,
            title=title or f"Conversation {conv_id}",
            workspace_id=workspace_id,
        )
        self.store.save_conversation_meta(meta)
        self._log_activity(owner_id, "conversation_created", "conversation", {
            "conversation_id": conv_id,
        })
        return meta

    async def get_conversation(self, conversation_id: str, user_id: str) -> Optional[ConversationMeta]:
        """Get conversation if user has access."""
        meta = self.store.load_conversation_meta(conversation_id)
        if not meta:
            return None
        if meta.owner_id == user_id or user_id in meta.shared_with:
            return meta
        # Check workspace access
        if meta.workspace_id:
            workspace = self.store.load_workspace(meta.workspace_id)
            if workspace and user_id in workspace.member_ids:
                return meta
        # Admin can access all
        profile = self._users.get(user_id)
        if profile and profile.role == Role.ADMIN:
            return meta
        return None

    async def share_conversation(self, conversation_id: str, owner_id: str, target_user_id: str) -> bool:
        """Share a conversation with another user."""
        meta = self.store.load_conversation_meta(conversation_id)
        if not meta or meta.owner_id != owner_id:
            raise PermissionError("Only the owner can share a conversation")

        if target_user_id not in meta.shared_with:
            meta.shared_with.append(target_user_id)
            meta.is_shared = True
            self.store.save_conversation_meta(meta)
        return True

    # --- Quotas ---

    async def check_quota(self, user_id: str) -> Dict[str, Any]:
        """Check current quota usage for a user."""
        profile = self._users.get(user_id)
        if not profile:
            raise ValueError(f"User '{user_id}' not found")

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        snapshot = self.store.load_quota(user_id, today)
        if not snapshot:
            snapshot = UsageQuotaSnapshot(user_id=user_id, date=today)

        return {
            "user_id": user_id,
            "date": today,
            "requests": {
                "used": snapshot.requests_used,
                "limit": profile.quota_requests_per_day,
                "remaining": max(0, profile.quota_requests_per_day - snapshot.requests_used),
            },
            "tokens": {
                "used": snapshot.tokens_used,
                "limit": profile.quota_tokens_per_day,
                "remaining": max(0, profile.quota_tokens_per_day - snapshot.tokens_used),
            },
            "cost_usd": round(snapshot.cost_usd, 4),
            "within_quota": (
                snapshot.requests_used < profile.quota_requests_per_day
                and snapshot.tokens_used < profile.quota_tokens_per_day
            ),
        }

    async def consume_quota(
        self,
        user_id: str,
        requests: int = 1,
        tokens: int = 0,
        cost_usd: float = 0.0,
    ) -> bool:
        """Consume quota. Returns True if within limits, False if exceeded."""
        profile = self._users.get(user_id)
        if not profile:
            return False

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        snapshot = self.store.load_quota(user_id, today)
        if not snapshot:
            snapshot = UsageQuotaSnapshot(user_id=user_id, date=today)

        # Check limits
        if snapshot.requests_used + requests > profile.quota_requests_per_day:
            return False
        if snapshot.tokens_used + tokens > profile.quota_tokens_per_day:
            return False

        snapshot.requests_used += requests
        snapshot.tokens_used += tokens
        snapshot.cost_usd += cost_usd
        self.store.save_quota(snapshot)

        # Update user totals
        profile.total_requests += requests
        profile.total_tokens += tokens
        profile.total_cost_usd += cost_usd
        self.store.save_user(profile)

        return True

    async def set_quota(self, admin_id: str, user_id: str, **kwargs: Any) -> None:
        """Set quota limits for a user (admin only)."""
        await self.require_permission(admin_id, "manage_quotas")
        profile = self._users.get(user_id)
        if not profile:
            raise ValueError(f"User '{user_id}' not found")

        for key in ("quota_requests_per_day", "quota_tokens_per_day", "quota_conversations"):
            if key in kwargs:
                setattr(profile, key, kwargs[key])

        self.store.save_user(profile)
        self._log_activity(admin_id, "quota_updated", "user", {
            "target_user": user_id,
            "quotas": kwargs,
        })

    # --- Config Overrides ---

    async def set_preference(self, user_id: str, key: str, value: Any) -> None:
        """Set a user-specific preference."""
        profile = self._users.get(user_id)
        if not profile:
            raise ValueError(f"User '{user_id}' not found")
        profile.preferences[key] = value
        self.store.save_user(profile)

    async def get_preferences(self, user_id: str) -> Dict[str, Any]:
        """Get all user preferences."""
        profile = self._users.get(user_id)
        if not profile:
            return {}
        return dict(profile.preferences)

    async def get_preference(self, user_id: str, key: str, default: Any = None) -> Any:
        """Get a single user preference."""
        profile = self._users.get(user_id)
        if not profile:
            return default
        return profile.preferences.get(key, default)

    # --- Activity Logging ---

    def _log_activity(
        self,
        user_id: str,
        action: str,
        resource: str,
        details: Optional[Dict[str, Any]] = None,
        ip_address: str = "",
    ) -> None:
        """Log a user activity."""
        entry = ActivityLogEntry(
            log_id=str(uuid.uuid4())[:8],
            timestamp=time.time(),
            user_id=user_id,
            action=action,
            resource=resource,
            details=details or {},
            ip_address=ip_address,
        )
        self.store.log_activity(entry)

    async def get_activity(
        self,
        admin_id: str,
        user_id: Optional[str] = None,
        date: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get activity log (admin only, or own activity)."""
        if user_id and user_id != admin_id:
            await self.require_permission(admin_id, "view_audit_log")
        elif not user_id:
            await self.require_permission(admin_id, "view_audit_log")

        return self.store.get_activity_log(user_id=user_id, date=date, limit=limit)

    # --- Admin ---

    async def get_admin_stats(self, admin_id: str) -> Dict[str, Any]:
        """Get admin dashboard stats."""
        await self.require_permission(admin_id, "manage_users")

        users = list(self._users.values())
        active_users = [u for u in users if u.is_active]
        sessions = list(self._sessions.values())
        active_sessions = [s for s in sessions if not s.is_expired and s.is_valid]
        workspaces = self.store.list_workspaces()

        total_tokens = sum(u.total_tokens for u in users)
        total_cost = sum(u.total_cost_usd for u in users)

        return {
            "total_users": len(users),
            "active_users": len(active_users),
            "users_by_role": {
                role.value: len([u for u in users if u.role == role])
                for role in Role
            },
            "active_sessions": len(active_sessions),
            "total_workspaces": len(workspaces),
            "total_tokens_all_time": total_tokens,
            "total_cost_all_time_usd": round(total_cost, 4),
        }

    # --- Lifecycle ---

    async def startup(self) -> None:
        """Initialize and clean up on startup."""
        await self.initialize()
        cleaned = await self.cleanup_sessions()
        if cleaned:
            logger.info(f"Cleaned up {cleaned} expired sessions")

    async def shutdown(self) -> None:
        """Clean up on shutdown."""
        logger.info(f"Multi-user system shutting down ({len(self._sessions)} active sessions)")
