"""
🟣 Rally Agent — System Control
System information, updates, and platform management.
"""

import asyncio
import os
import subprocess
import platform
import logging
import json
import shutil
from datetime import datetime

logger = logging.getLogger("rally.system_control")


class SystemControl:
    """Provides system information, updates, and management."""

    def __init__(self, config=None):
        self.config = config
        self.data_dir = os.path.expanduser("~/.rally-agent/data")
        os.makedirs(self.data_dir, exist_ok=True)

    def get_system_info(self) -> dict:
        """Get comprehensive system information."""
        info = {
            "platform": platform.system(),
            "platform_release": platform.release(),
            "platform_version": platform.version(),
            "architecture": platform.machine(),
            "processor": platform.processor(),
            "python_version": platform.python_version(),
            "hostname": platform.node(),
            "uptime": self._get_uptime(),
            "cpu_count": os.cpu_count(),
            "disk": self._get_disk_info(),
            "memory": self._get_memory_info(),
            "load_average": self._get_load_average(),
            "rally_version": self._get_rally_version(),
            "timestamp": datetime.now().isoformat(),
        }
        return info

    def _get_uptime(self) -> str:
        try:
            with open("/proc/uptime") as f:
                seconds = float(f.read().split()[0])
            days = int(seconds // 86400)
            hours = int((seconds % 86400) // 3600)
            minutes = int((seconds % 3600) // 60)
            return f"{days}d {hours}h {minutes}m"
        except Exception:
            return "unknown"

    def _get_disk_info(self) -> dict:
        try:
            total, used, free = shutil.disk_usage("/")
            return {
                "total_gb": round(total / (1024**3), 1),
                "used_gb": round(used / (1024**3), 1),
                "free_gb": round(free / (1024**3), 1),
                "percent_used": round(used / total * 100, 1),
            }
        except Exception:
            return {}

    def _get_memory_info(self) -> dict:
        try:
            with open("/proc/meminfo") as f:
                lines = f.readlines()
            mem = {}
            for line in lines:
                parts = line.split(":")
                if len(parts) == 2:
                    key = parts[0].strip()
                    val = parts[1].strip().split()[0]
                    mem[key] = int(val)

            total = mem.get("MemTotal", 0)
            available = mem.get("MemAvailable", 0)
            return {
                "total_mb": round(total / 1024, 1),
                "available_mb": round(available / 1024, 1),
                "used_mb": round((total - available) / 1024, 1),
                "percent_used": round((total - available) / total * 100, 1) if total else 0,
            }
        except Exception:
            return {}

    def _get_load_average(self) -> list:
        try:
            load = os.getloadavg()
            return [round(x, 2) for x in load]
        except Exception:
            return []

    def _get_rally_version(self) -> str:
        try:
            from core.version import __version__
            return __version__
        except Exception:
            return "unknown"

    async def check_for_updates(self) -> dict:
        """Check for and optionally apply updates."""
        result = {
            "current_version": self._get_rally_version(),
            "update_available": False,
            "latest_version": None,
            "channel": "stable",
        }

        try:
            # Check git for updates
            proc = await asyncio.create_subprocess_exec(
                "git", "remote", "update",
                cwd=os.path.expanduser("~/.rally-agent"),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.wait()

            proc = await asyncio.create_subprocess_exec(
                "git", "status", "-uno",
                cwd=os.path.expanduser("~/.rally-agent"),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            output = stdout.decode()

            if "Your branch is behind" in output:
                result["update_available"] = True
                result["message"] = "Update available. Run 'git pull' to update."
            elif "Your branch is up to date" in output:
                result["message"] = "Already up to date."
            else:
                result["message"] = output.strip()[:200]

        except Exception as e:
            result["message"] = f"Update check failed: {e}"

        return result

    async def apply_update(self) -> dict:
        """Pull latest changes and restart."""
        try:
            rally_dir = os.path.expanduser("~/.rally-agent")
            if not os.path.isdir(os.path.join(rally_dir, ".git")):
                return {"status": "error", "message": "Not a git repository"}

            proc = await asyncio.create_subprocess_exec(
                "git", "pull", "--ff-only",
                cwd=rally_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode == 0:
                return {
                    "status": "updated",
                    "output": stdout.decode().strip(),
                    "message": "Updated successfully. Restart to apply.",
                }
            else:
                return {
                    "status": "error",
                    "message": stderr.decode().strip(),
                }
        except Exception as e:
            return {"status": "error", "message": str(e)}
