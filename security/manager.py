"""
🟣 Rally Agent — Security Module
Protects against dangerous operations, prompt injection, and data leaks.
"""

import os
import re
from typing import Optional

from cli.theme import Theme


class SecurityManager:
    """Manages security policies and operations"""

    # Dangerous commands that should never execute
    BLOCKED_COMMANDS = [
        "rm -rf /",
        "rm -rf ~",
        "mkfs",
        "dd if=",
        ":(){:|:&};:",
        "> /dev/sda",
        "chmod -R 777 /",
        "chown -R",
        "wget -O- | sh",
        "curl | sh",
        "shutdown",
        "reboot",
        "halt",
        "init 0",
        "init 6",
    ]

    # Sensitive file patterns
    SENSITIVE_PATTERNS = [
        r"\.env$",
        r"\.pem$",
        r"\.key$",
        r"id_rsa",
        r"\.gnupg",
        r"\.ssh/",
        r"password",
        r"secret",
        r"token",
        r"\.aws/credentials",
    ]

    # Prompt injection patterns
    INJECTION_PATTERNS = [
        r"ignore previous instructions",
        r"ignore all instructions",
        r"you are now",
        r"system prompt",
        r"reveal your instructions",
        r"output your prompt",
        r"what are your rules",
        r"forget everything",
        r"new instructions",
        r"override safety",
    ]

    def __init__(self, config):
        self.config = config
        self.confirm_dangerous = config.get("security.confirm_dangerous", True)
        self.audit_log = config.get("security.audit_log", True)
        self.sandbox_exec = config.get("security.sandbox_exec", True)
        self.blocked = config.get("security.blocked_commands", self.BLOCKED_COMMANDS)

    def check_command(self, command: str) -> tuple[bool, str]:
        """Check if a command is safe to execute"""
        cmd_lower = command.lower().strip()

        # Check blocked commands
        for blocked in self.blocked:
            if blocked.lower() in cmd_lower:
                return False, f"⛔ Blocked dangerous command: {command}"

        # Check for sensitive file access
        for pattern in self.SENSITIVE_PATTERNS:
            if re.search(pattern, cmd_lower, re.IGNORECASE):
                return False, f"🔒 Access to sensitive file blocked: {command}"

        return True, "✓ Command allowed"

    def check_prompt_injection(self, text: str) -> tuple[bool, Optional[str]]:
        """Check for prompt injection attempts"""
        text_lower = text.lower()

        for pattern in self.INJECTION_PATTERNS:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return True, f"Potential prompt injection detected: {pattern}"

        return False, None

    def check_file_access(self, path: str, operation: str = "read") -> tuple[bool, str]:
        """Check if file access is allowed"""
        abs_path = os.path.abspath(path)

        # Block access to system directories
        blocked_dirs = ["/etc", "/sys", "/proc", "/dev", "/boot"]
        for d in blocked_dirs:
            if abs_path.startswith(d):
                return False, f"⛔ Access to system directory blocked: {d}"

        # Block access to sensitive files
        for pattern in self.SENSITIVE_PATTERNS:
            if re.search(pattern, abs_path, re.IGNORECASE):
                return False, f"🔒 Access to sensitive file blocked: {abs_path}"

        # Write operations to system dirs
        if operation == "write":
            if abs_path.startswith("/usr") or abs_path.startswith("/bin"):
                return False, f"⛔ Write to system directory blocked"

        return True, "✓ Access allowed"

    def sanitize_output(self, text: str) -> str:
        """Sanitize output to prevent data leaks"""
        # Mask potential API keys
        text = re.sub(
            r'(sk-[a-zA-Z0-9]{20,})',
            'sk-***REDACTED***',
            text
        )
        text = re.sub(
            r'(sk-ant-[a-zA-Z0-9]{20,})',
            'sk-ant-***REDACTED***',
            text
        )
        # Mask potential tokens
        text = re.sub(
            r'(ghp_[a-zA-Z0-9]{36})',
            'ghp_***REDACTED***',
            text
        )
        text = re.sub(
            r'(xoxb-[a-zA-Z0-9-]+)',
            'xoxb-***REDACTED***',
            text
        )

        return text

    def log_action(self, action: str, details: str = ""):
        """Log security-relevant actions"""
        if not self.audit_log:
            return

        log_dir = os.path.expanduser("~/.rally-agent/logs")
        os.makedirs(log_dir, exist_ok=True)

        log_file = os.path.join(log_dir, "security.log")
        from datetime import datetime
        timestamp = datetime.now().isoformat()

        with open(log_file, "a") as f:
            f.write(f"[{timestamp}] {action}: {details}\n")

    def confirm(self, message: str) -> bool:
        """Ask for user confirmation"""
        if not self.confirm_dangerous:
            return True

        response = input(f"\n  ⚠️  {message} (y/N): ").strip().lower()
        return response in ("y", "yes")
