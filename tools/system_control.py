"""
🟣 Rally Agent — System Control Engine
Process management, service control, file monitoring, network control, hardware info,
package manager abstraction, environment management, scheduled tasks, power management, auto-updater.
"""

from __future__ import annotations

import asyncio
import json
import os
import platform
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

from tools.registry import (
    BaseTool,
    ToolCategory,
    ToolDefinition,
    ToolParameter,
    PermissionLevel,
    ToolRegistry,
)


# ═══════════════════════════════════════════════════════════════
# Platform Detection
# ═══════════════════════════════════════════════════════════════

PLATFORM = platform.system().lower()  # "linux", "darwin", "windows"


def _run(cmd: list[str] | str, timeout: int = 30, shell: bool = False) -> subprocess.CompletedProcess:
    """Run a command with timeout and return result."""
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout, shell=isinstance(cmd, str) or shell,
    )


def _run_safe(cmd: list[str] | str, timeout: int = 30, shell: bool = False) -> dict[str, Any]:
    """Run a command and return a standardized result dict."""
    try:
        r = _run(cmd, timeout=timeout, shell=shell)
        return {
            "success": r.returncode == 0,
            "exit_code": r.returncode,
            "stdout": r.stdout[:50000],
            "stderr": r.stderr[:10000],
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"Command timed out ({timeout}s)"}
    except FileNotFoundError:
        return {"success": False, "error": f"Command not found: {cmd if isinstance(cmd, str) else cmd[0]}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════
# Process Manager
# ═══════════════════════════════════════════════════════════════

@dataclass
class ProcessInfo:
    pid: int
    name: str
    user: str = ""
    cpu_percent: float = 0.0
    memory_mb: float = 0.0
    memory_percent: float = 0.0
    status: str = ""
    started: str = ""
    command: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "pid": self.pid,
            "name": self.name,
            "user": self.user,
            "cpu_percent": self.cpu_percent,
            "memory_mb": round(self.memory_mb, 1),
            "memory_percent": round(self.memory_percent, 1),
            "status": self.status,
            "started": self.started,
            "command": self.command[:200],
        }


class ProcessManager:
    """Cross-platform process management."""

    @staticmethod
    def list_processes(sort_by: str = "cpu", limit: int = 50) -> list[ProcessInfo]:
        """List running processes sorted by CPU or memory."""
        try:
            import psutil
            processes = []
            for proc in psutil.process_iter(["pid", "name", "username", "cpu_percent", "memory_info", "memory_percent", "status", "create_time", "cmdline"]):
                try:
                    info = proc.info
                    mem_mb = info["memory_info"].rss / (1024 * 1024) if info["memory_info"] else 0
                    started = ""
                    if info.get("create_time"):
                        started = datetime.fromtimestamp(info["create_time"]).strftime("%Y-%m-%d %H:%M")
                    processes.append(ProcessInfo(
                        pid=info["pid"],
                        name=info["name"] or "",
                        user=info.get("username", "") or "",
                        cpu_percent=info.get("cpu_percent", 0) or 0,
                        memory_mb=mem_mb,
                        memory_percent=info.get("memory_percent", 0) or 0,
                        status=info.get("status", ""),
                        started=started,
                        command=" ".join(info.get("cmdline", []) or []),
                    ))
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            key = "cpu_percent" if sort_by == "cpu" else "memory_percent"
            processes.sort(key=lambda p: getattr(p, key), reverse=True)
            return processes[:limit]
        except ImportError:
            # Fallback: ps command
            return ProcessManager._list_ps(limit)

    @staticmethod
    def _list_ps(limit: int) -> list[ProcessInfo]:
        """Fallback process listing using ps command."""
        processes = []
        try:
            if PLATFORM == "windows":
                r = _run(["tasklist", "/fo", "csv", "/nh"], timeout=10)
                for line in r.stdout.strip().split("\n")[:limit]:
                    parts = line.replace('"', '').split(",")
                    if len(parts) >= 5:
                        processes.append(ProcessInfo(
                            pid=int(parts[1]),
                            name=parts[0],
                            memory_mb=float(parts[4].replace(" K", "").replace(",", "")) / 1024,
                        ))
            else:
                r = _run(["ps", "aux", "--sort=-pcpu"], timeout=10)
                for line in r.stdout.strip().split("\n")[1:limit + 1]:
                    parts = line.split(None, 10)
                    if len(parts) >= 11:
                        processes.append(ProcessInfo(
                            pid=int(parts[1]),
                            user=parts[0],
                            cpu_percent=float(parts[2]),
                            memory_percent=float(parts[3]),
                            name=parts[10].split()[0] if parts[10] else "",
                            command=parts[10],
                        ))
        except Exception:
            pass
        return processes

    @staticmethod
    def get_process(pid: int) -> Optional[ProcessInfo]:
        """Get detailed info about a specific process."""
        try:
            import psutil
            proc = psutil.Process(pid)
            info = proc.as_dict(["pid", "name", "username", "cpu_percent", "memory_info", "memory_percent", "status", "create_time", "cmdline"])
            mem_mb = info["memory_info"].rss / (1024 * 1024) if info["memory_info"] else 0
            started = datetime.fromtimestamp(info["create_time"]).strftime("%Y-%m-%d %H:%M") if info.get("create_time") else ""
            return ProcessInfo(
                pid=info["pid"],
                name=info["name"] or "",
                user=info.get("username", "") or "",
                cpu_percent=info.get("cpu_percent", 0) or 0,
                memory_mb=mem_mb,
                memory_percent=info.get("memory_percent", 0) or 0,
                status=info.get("status", ""),
                started=started,
                command=" ".join(info.get("cmdline", []) or []),
            )
        except ImportError:
            pass
        # Fallback
        if PLATFORM == "windows":
            r = _run(["tasklist", "/fi", f"PID eq {pid}", "/fo", "csv", "/nh"], timeout=5)
            return ProcessInfo(pid=pid, name=r.stdout.strip().split(",")[0].replace('"', '')) if r.stdout.strip() else None
        else:
            r = _run(["ps", "-p", str(pid), "-o", "pid,comm,%cpu,%mem,etime,args"], timeout=5)
            lines = r.stdout.strip().split("\n")
            if len(lines) >= 2:
                parts = lines[1].split(None, 5)
                return ProcessInfo(
                    pid=int(parts[0]),
                    name=parts[1],
                    cpu_percent=float(parts[2]),
                    memory_percent=float(parts[3]),
                    started=parts[4] if len(parts) > 4 else "",
                    command=parts[5] if len(parts) > 5 else "",
                )
        return None

    @staticmethod
    def kill_process(pid: int, force: bool = False) -> dict[str, Any]:
        """Kill a process by PID."""
        try:
            import psutil
            proc = psutil.Process(pid)
            name = proc.name()
            if force:
                proc.kill()
            else:
                proc.terminate()
            return {"success": True, "pid": pid, "name": name, "signal": "KILL" if force else "TERM"}
        except ImportError:
            pass
        # Fallback
        sig = "9" if force else "15"
        if PLATFORM == "windows":
            result = _run_safe(["taskkill", "/PID", str(pid), "/F" if force else ""])
        else:
            result = _run_safe(["kill", f"-{sig}", str(pid)])
        result["pid"] = pid
        return result

    @staticmethod
    def find_processes(name: str) -> list[ProcessInfo]:
        """Find processes by name pattern."""
        try:
            import psutil
            results = []
            for proc in psutil.process_iter(["pid", "name", "username", "cpu_percent", "memory_info", "memory_percent", "cmdline"]):
                try:
                    info = proc.info
                    if name.lower() in (info["name"] or "").lower():
                        mem_mb = info["memory_info"].rss / (1024 * 1024) if info["memory_info"] else 0
                        results.append(ProcessInfo(
                            pid=info["pid"],
                            name=info["name"] or "",
                            user=info.get("username", "") or "",
                            cpu_percent=info.get("cpu_percent", 0) or 0,
                            memory_mb=mem_mb,
                            memory_percent=info.get("memory_percent", 0) or 0,
                            command=" ".join(info.get("cmdline", []) or []),
                        ))
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            return results
        except ImportError:
            pass
        # Fallback
        if PLATFORM == "windows":
            r = _run(["tasklist", "/fi", f"IMAGENAME eq {name}*", "/fo", "csv", "/nh"], timeout=10)
        else:
            r = _run(["pgrep", "-a", name], timeout=10)
        return [ProcessInfo(pid=0, name=name, command=r.stdout[:200])]


# ═══════════════════════════════════════════════════════════════
# Service Manager
# ═══════════════════════════════════════════════════════════════

class ServiceManager:
    """Cross-platform service management."""

    @staticmethod
    def _get_init_system() -> str:
        """Detect init system on Linux."""
        if PLATFORM == "darwin":
            return "launchd"
        if PLATFORM == "windows":
            return "sc"
        # Linux detection
        if os.path.exists("/run/systemd/system"):
            return "systemd"
        if shutil.which("rc-service"):
            return "openrc"
        return "sysvinit"

    @staticmethod
    def list_services() -> list[dict[str, Any]]:
        """List system services."""
        init = ServiceManager._get_init_system()

        if init == "systemd":
            r = _run(["systemctl", "list-units", "--type=service", "--all", "--no-pager", "--plain"], timeout=15)
            services = []
            for line in r.stdout.strip().split("\n"):
                parts = line.split(None, 4)
                if len(parts) >= 4 and parts[0].endswith(".service"):
                    services.append({
                        "name": parts[0].replace(".service", ""),
                        "load": parts[1],
                        "active": parts[2],
                        "sub": parts[3],
                        "description": parts[4] if len(parts) > 4 else "",
                    })
            return services

        elif init == "launchd":
            r = _run(["launchctl", "list"], timeout=10)
            services = []
            for line in r.stdout.strip().split("\n")[1:]:  # Skip header
                parts = line.split("\t")
                if len(parts) >= 3:
                    services.append({
                        "pid": parts[0],
                        "status": parts[1],
                        "name": parts[2],
                    })
            return services

        elif init == "sc":
            r = _run(["sc", "query", "type=", "service", "state=", "all", " bufsize=", "8192"], timeout=15, shell=True)
            return [{"raw": r.stdout[:2000]}]

        return [{"error": f"Unsupported init system: {init}"}]

    @staticmethod
    def service_action(name: str, action: str) -> dict[str, Any]:
        """Perform an action on a service (start, stop, restart, status, enable, disable)."""
        init = ServiceManager._get_init_system()

        if init == "systemd":
            valid_actions = {"start", "stop", "restart", "status", "enable", "disable", "reload"}
            if action not in valid_actions:
                return {"error": f"Invalid action. Use: {', '.join(valid_actions)}"}
            return _run_safe(["systemctl", action, f"{name}.service"])

        elif init == "launchd":
            action_map = {
                "start": ["launchctl", "start"],
                "stop": ["launchctl", "stop"],
                "restart": ["launchctl", "stop"],  # macOS doesn't have restart; stop + start
                "status": ["launchctl", "list"],
                "enable": ["launchctl", "load", "-w"],
                "disable": ["launchctl", "unload", "-w"],
            }
            cmd = action_map.get(action)
            if not cmd:
                return {"error": f"Invalid action: {action}"}
            if action == "status":
                cmd.append(name)
            else:
                cmd.append(name)
            result = _run_safe(cmd)
            if action == "restart" and result.get("success"):
                time.sleep(0.5)
                result = _run_safe(["launchctl", "start", name])
            return result

        elif init == "sc":
            sc_action = {"start": "start", "stop": "stop", "restart": "stop"}.get(action)
            if not sc_action:
                return {"error": f"Action not supported on Windows: {action}"}
            result = _run_safe(["sc", sc_action, name])
            if action == "restart" and result.get("success"):
                time.sleep(1)
                result = _run_safe(["sc", "start", name])
            return result

        return {"error": "Unsupported init system"}


# ═══════════════════════════════════════════════════════════════
# File System Watcher
# ═══════════════════════════════════════════════════════════════

class FileSystemWatcher:
    """Watch files/directories for changes."""

    @staticmethod
    def watch_directory(path: str, duration: int = 10, recursive: bool = False) -> dict[str, Any]:
        """Watch a directory for changes for a specified duration."""
        if not os.path.isdir(path):
            return {"error": f"Not a directory: {path}"}

        # Take initial snapshot
        initial = FileSystemWatcher._snapshot(path, recursive)

        time.sleep(duration)

        # Take final snapshot
        final = FileSystemWatcher._snapshot(path, recursive)

        added = final.keys() - initial.keys()
        removed = initial.keys() - final.keys()
        modified = {k for k in (final.keys() & initial.keys()) if final[k] != initial[k]}

        return {
            "path": path,
            "duration": duration,
            "added": sorted(added),
            "removed": sorted(removed),
            "modified": sorted(modified),
            "total_changes": len(added) + len(removed) + len(modified),
        }

    @staticmethod
    def _snapshot(path: str, recursive: bool) -> dict[str, float]:
        """Get a snapshot of file modification times."""
        snapshot = {}
        if recursive:
            for root, dirs, files in os.walk(path):
                for name in files:
                    fp = os.path.join(root, name)
                    try:
                        snapshot[os.path.relpath(fp, path)] = os.path.getmtime(fp)
                    except OSError:
                        continue
        else:
            try:
                for name in os.listdir(path):
                    fp = os.path.join(path, name)
                    try:
                        snapshot[name] = os.path.getmtime(fp)
                    except OSError:
                        continue
            except OSError:
                pass
        return snapshot

    @staticmethod
    def get_file_info(path: str) -> dict[str, Any]:
        """Get detailed file information."""
        if not os.path.exists(path):
            return {"error": f"Path not found: {path}"}
        try:
            stat = os.stat(path)
            return {
                "path": path,
                "type": "directory" if os.path.isdir(path) else "file",
                "size": stat.st_size,
                "size_human": FileSystemWatcher._human_size(stat.st_size),
                "permissions": oct(stat.st_mode)[-3:],
                "owner_uid": stat.st_uid,
                "group_gid": stat.st_gid,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "accessed": datetime.fromtimestamp(stat.st_atime).isoformat(),
                "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
            }
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def _human_size(size: int) -> str:
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"


# ═══════════════════════════════════════════════════════════════
# Network Control
# ═══════════════════════════════════════════════════════════════

class NetworkControl:
    """Network operations: firewall, ports, interfaces."""

    @staticmethod
    def list_interfaces() -> list[dict[str, Any]]:
        """List network interfaces with addresses."""
        try:
            import psutil
            interfaces = []
            addrs = psutil.net_if_addrs()
            stats = psutil.net_if_stats()
            for name, addr_list in addrs.items():
                iface = {"name": name, "addresses": []}
                if name in stats:
                    s = stats[name]
                    iface["up"] = s.isup
                    iface["speed_mbps"] = s.speed
                    iface["mtu"] = s.mtu
                for addr in addr_list:
                    iface["addresses"].append({
                        "family": str(addr.family),
                        "address": addr.address,
                        "netmask": addr.netmask,
                        "broadcast": addr.broadcast,
                    })
                interfaces.append(iface)
            return interfaces
        except ImportError:
            pass
        # Fallback
        if PLATFORM == "windows":
            r = _run(["ipconfig"], timeout=10)
        else:
            r = _run(["ip", "addr", "show"], timeout=10)
            if r.returncode != 0:
                r = _run(["ifconfig"], timeout=10)
        return [{"raw": r.stdout[:3000]}]

    @staticmethod
    def list_connections(limit: int = 50) -> list[dict[str, Any]]:
        """List active network connections."""
        try:
            import psutil
            connections = []
            for conn in psutil.net_connections(kind="inet")[:limit]:
                connections.append({
                    "fd": conn.fd,
                    "family": str(conn.family),
                    "type": str(conn.type),
                    "local": f"{conn.laddr.ip}:{conn.laddr.port}" if conn.laddr else "",
                    "remote": f"{conn.raddr.ip}:{conn.raddr.port}" if conn.raddr else "",
                    "status": conn.status,
                    "pid": conn.pid,
                })
            return connections
        except ImportError:
            pass
        # Fallback
        if PLATFORM == "windows":
            r = _run(["netstat", "-ano"], timeout=10)
        else:
            r = _run(["ss", "-tuln"], timeout=10)
            if r.returncode != 0:
                r = _run(["netstat", "-tuln"], timeout=10)
        return [{"raw": r.stdout[:3000]}]

    @staticmethod
    def check_port(port: int, host: str = "localhost") -> dict[str, Any]:
        """Check if a port is open."""
        import socket
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            result = sock.connect_ex((host, port))
            sock.close()
            return {"host": host, "port": port, "open": result == 0}
        except Exception as e:
            return {"host": host, "port": port, "open": False, "error": str(e)}

    @staticmethod
    def firewall_status() -> dict[str, Any]:
        """Check firewall status."""
        if PLATFORM == "linux":
            # Try ufw first, then iptables
            if shutil.which("ufw"):
                r = _run(["ufw", "status", "verbose"], timeout=10)
                return {"backend": "ufw", "status": r.stdout[:2000]}
            elif shutil.which("iptables"):
                r = _run(["iptables", "-L", "-n", "--line-numbers"], timeout=10)
                return {"backend": "iptables", "rules": r.stdout[:5000]}
            return {"backend": "unknown", "error": "No supported firewall found"}

        elif PLATFORM == "darwin":
            r = _run(["/usr/libexec/ApplicationFirewall/socketfilterfw", "--getglobalstate"], timeout=10)
            return {"backend": "macos_firewall", "status": r.stdout.strip()}

        elif PLATFORM == "windows":
            r = _run(["netsh", "advfirewall", "show", "allprofiles"], timeout=10)
            return {"backend": "windows_firewall", "status": r.stdout[:3000]}

        return {"error": "Unsupported platform"}


# ═══════════════════════════════════════════════════════════════
# Hardware Info
# ═══════════════════════════════════════════════════════════════

class HardwareInfo:
    """System hardware information."""

    @staticmethod
    def get_cpu_info() -> dict[str, Any]:
        info: dict[str, Any] = {
            "platform": platform.machine(),
            "processor": platform.processor(),
            "cores_physical": os.cpu_count(),
        }
        try:
            import psutil
            info["cores_logical"] = psutil.cpu_count(logical=True)
            freq = psutil.cpu_freq()
            if freq:
                info["freq_current_mhz"] = freq.current
                info["freq_max_mhz"] = freq.max
            info["cpu_percent"] = psutil.cpu_percent(interval=1, percpu=True)
            info["cpu_percent_avg"] = sum(info["cpu_percent"]) / len(info["cpu_percent"])
        except ImportError:
            pass
        # Linux /proc/cpuinfo
        if PLATFORM == "linux":
            try:
                with open("/proc/cpuinfo") as f:
                    cpuinfo = f.read()
                for line in cpuinfo.split("\n"):
                    if "model name" in line:
                        info["model_name"] = line.split(":")[1].strip()
                        break
            except Exception:
                pass
        return info

    @staticmethod
    def get_memory_info() -> dict[str, Any]:
        try:
            import psutil
            mem = psutil.virtual_memory()
            swap = psutil.swap_memory()
            return {
                "total_mb": round(mem.total / (1024 * 1024)),
                "available_mb": round(mem.available / (1024 * 1024)),
                "used_mb": round(mem.used / (1024 * 1024)),
                "percent": mem.percent,
                "swap_total_mb": round(swap.total / (1024 * 1024)),
                "swap_used_mb": round(swap.used / (1024 * 1024)),
                "swap_percent": swap.percent,
            }
        except ImportError:
            pass
        # Fallback
        if PLATFORM == "linux":
            try:
                with open("/proc/meminfo") as f:
                    meminfo = f.read()
                info = {}
                for line in meminfo.split("\n"):
                    if ":" in line:
                        key, val = line.split(":", 1)
                        info[key.strip()] = val.strip()
                return {"raw": info}
            except Exception:
                pass
        return {"error": "psutil not available"}

    @staticmethod
    def get_disk_info() -> list[dict[str, Any]]:
        try:
            import psutil
            disks = []
            for part in psutil.disk_partitions(all=False):
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                    disks.append({
                        "device": part.device,
                        "mountpoint": part.mountpoint,
                        "fstype": part.fstype,
                        "total_gb": round(usage.total / (1024 ** 3), 1),
                        "used_gb": round(usage.used / (1024 ** 3), 1),
                        "free_gb": round(usage.free / (1024 ** 3), 1),
                        "percent": usage.percent,
                    })
                except PermissionError:
                    continue
            return disks
        except ImportError:
            pass
        # Fallback
        if PLATFORM == "windows":
            r = _run(["wmic", "logicaldisk", "get", "size,freespace,caption"], timeout=10)
        else:
            r = _run(["df", "-h"], timeout=10)
        return [{"raw": r.stdout[:3000]}]

    @staticmethod
    def get_gpu_info() -> list[dict[str, Any]]:
        """Get GPU information."""
        gpus = []
        # Try nvidia-smi
        if shutil.which("nvidia-smi"):
            r = _run([
                "nvidia-smi", "--query-gpu=name,memory.total,memory.used,memory.free,temperature.gpu,utilization.gpu",
                "--format=csv,noheader,nounits",
            ], timeout=10)
            if r.returncode == 0:
                for line in r.stdout.strip().split("\n"):
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) >= 6:
                        gpus.append({
                            "name": parts[0],
                            "memory_total_mb": int(parts[1]),
                            "memory_used_mb": int(parts[2]),
                            "memory_free_mb": int(parts[3]),
                            "temperature_c": int(parts[4]),
                            "utilization_percent": int(parts[5]),
                        })
        # Try lspci on Linux
        if not gpus and PLATFORM == "linux" and shutil.which("lspci"):
            r = _run(["lspci", "-v"], timeout=10)
            for line in r.stdout.split("\n"):
                if "VGA" in line or "3D" in line or "Display" in line:
                    gpus.append({"name": line.split(": ", 1)[-1].strip() if ": " in line else line})
        if not gpus:
            # Try dxdiag on Windows
            if PLATFORM == "windows":
                gpus.append({"info": "Run dxdiag for GPU details"})
            else:
                gpus.append({"info": "No GPU detected or nvidia-smi/lspci not available"})
        return gpus

    @staticmethod
    def get_system_info() -> dict[str, Any]:
        """Get comprehensive system info."""
        return {
            "platform": platform.system(),
            "platform_release": platform.release(),
            "platform_version": platform.version(),
            "architecture": platform.machine(),
            "hostname": platform.node(),
            "python_version": platform.python_version(),
            "cpu": HardwareInfo.get_cpu_info(),
            "memory": HardwareInfo.get_memory_info(),
            "disk": HardwareInfo.get_disk_info(),
            "gpu": HardwareInfo.get_gpu_info(),
            "network": NetworkControl.list_interfaces()[:5],
        }


# ═══════════════════════════════════════════════════════════════
# Package Manager Abstraction
# ═══════════════════════════════════════════════════════════════

class PackageManager:
    """Cross-platform package manager abstraction."""

    @staticmethod
    def detect() -> str:
        """Detect the system package manager."""
        managers = [
            ("apt", ["apt", "--version"]),
            ("dnf", ["dnf", "--version"]),
            ("yum", ["yum", "--version"]),
            ("pacman", ["pacman", "--version"]),
            ("zypper", ["zypper", "--version"]),
            ("brew", ["brew", "--version"]),
            ("winget", ["winget", "--version"]),
            ("choco", ["choco", "--version"]),
        ]
        for name, cmd in managers:
            if shutil.which(cmd[0]):
                return name
        return "unknown"

    @staticmethod
    def update_index() -> dict[str, Any]:
        """Update package index."""
        pm = PackageManager.detect()
        commands = {
            "apt": ["apt", "update"],
            "dnf": ["dnf", "check-update"],
            "yum": ["yum", "check-update"],
            "pacman": ["pacman", "-Sy"],
            "zypper": ["zypper", "refresh"],
            "brew": ["brew", "update"],
            "winget": ["winget", "upgrade"],
            "choco": ["choco", "upgrade", "all", "--noop"],
        }
        cmd = commands.get(pm)
        if not cmd:
            return {"error": f"Unsupported package manager: {pm}"}
        return _run_safe(cmd, timeout=120)

    @staticmethod
    def install(package: str) -> dict[str, Any]:
        """Install a package."""
        pm = PackageManager.detect()
        commands = {
            "apt": ["apt", "install", "-y", package],
            "dnf": ["dnf", "install", "-y", package],
            "yum": ["yum", "install", "-y", package],
            "pacman": ["pacman", "-S", "--noconfirm", package],
            "zypper": ["zypper", "--non-interactive", "install", package],
            "brew": ["brew", "install", package],
            "winget": ["winget", "install", "--accept-package-agreements", package],
            "choco": ["choco", "install", "-y", package],
        }
        cmd = commands.get(pm)
        if not cmd:
            return {"error": f"Unsupported package manager: {pm}"}
        return _run_safe(cmd, timeout=300)

    @staticmethod
    def remove(package: str) -> dict[str, Any]:
        """Remove a package."""
        pm = PackageManager.detect()
        commands = {
            "apt": ["apt", "remove", "-y", package],
            "dnf": ["dnf", "remove", "-y", package],
            "yum": ["yum", "remove", "-y", package],
            "pacman": ["pacman", "-R", "--noconfirm", package],
            "zypper": ["zypper", "--non-interactive", "remove", package],
            "brew": ["brew", "uninstall", package],
            "winget": ["winget", "uninstall", package],
            "choco": ["choco", "uninstall", "-y", package],
        }
        cmd = commands.get(pm)
        if not cmd:
            return {"error": f"Unsupported package manager: {pm}"}
        return _run_safe(cmd, timeout=120)

    @staticmethod
    def search(query: str) -> dict[str, Any]:
        """Search for packages."""
        pm = PackageManager.detect()
        commands = {
            "apt": ["apt", "search", query],
            "dnf": ["dnf", "search", query],
            "yum": ["yum", "search", query],
            "pacman": ["pacman", "-Ss", query],
            "zypper": ["zypper", "search", query],
            "brew": ["brew", "search", query],
            "winget": ["winget", "search", query],
            "choco": ["choco", "search", query],
        }
        cmd = commands.get(pm)
        if not cmd:
            return {"error": f"Unsupported package manager: {pm}"}
        return _run_safe(cmd, timeout=60)

    @staticmethod
    def list_installed(query: Optional[str] = None) -> dict[str, Any]:
        """List installed packages."""
        pm = PackageManager.detect()
        if pm == "apt":
            cmd = ["dpkg", "-l"]
            if query:
                cmd.append(query)
        elif pm in ("dnf", "yum"):
            cmd = [pm, "list", "installed"]
            if query:
                cmd.append(query)
        elif pm == "pacman":
            cmd = ["pacman", "-Q"]
            if query:
                cmd.extend(["-s", query])
        elif pm == "brew":
            cmd = ["brew", "list"]
        elif pm == "winget":
            cmd = ["winget", "list"]
        elif pm == "choco":
            cmd = ["choco", "list", "--local-only"]
        else:
            return {"error": f"Unsupported package manager: {pm}"}
        return _run_safe(cmd, timeout=60)

    @staticmethod
    def upgrade_all() -> dict[str, Any]:
        """Upgrade all packages."""
        pm = PackageManager.detect()
        commands = {
            "apt": ["apt", "upgrade", "-y"],
            "dnf": ["dnf", "upgrade", "-y"],
            "yum": ["yum", "update", "-y"],
            "pacman": ["pacman", "-Syu", "--noconfirm"],
            "zypper": ["zypper", "--non-interactive", "update"],
            "brew": ["brew", "upgrade"],
            "winget": ["winget", "upgrade", "--all"],
            "choco": ["choco", "upgrade", "all", "-y"],
        }
        cmd = commands.get(pm)
        if not cmd:
            return {"error": f"Unsupported package manager: {pm}"}
        return _run_safe(cmd, timeout=600)


# ═══════════════════════════════════════════════════════════════
# Environment Manager
# ═══════════════════════════════════════════════════════════════

class EnvironmentManager:
    """Manage environment variables."""

    @staticmethod
    def get(name: Optional[str] = None) -> dict[str, Any]:
        """Get an env var or list all."""
        if name:
            value = os.environ.get(name)
            if value is not None:
                return {"name": name, "value": value, "exists": True}
            return {"name": name, "exists": False}
        # List all (excluding sensitive)
        sensitive = {"password", "secret", "token", "key", "credential", "auth"}
        env_vars = {}
        for k, v in sorted(os.environ.items()):
            if any(s in k.lower() for s in sensitive):
                env_vars[k] = "[REDACTED]"
            else:
                env_vars[k] = v
        return {"variables": env_vars, "count": len(env_vars)}

    @staticmethod
    def set(name: str, value: str, persistent: bool = False) -> dict[str, Any]:
        """Set an environment variable. If persistent, writes to shell profile."""
        os.environ[name] = value
        result = {"success": True, "name": name, "value": value, "persistent": persistent}

        if persistent:
            export_line = f'export {name}="{value}"'
            if PLATFORM == "windows":
                # Windows: setx
                r = _run_safe(["setx", name, value])
                result["persist_result"] = r
            else:
                # Unix: append to ~/.bashrc
                profile = os.path.expanduser("~/.bashrc")
                try:
                    with open(profile, "a") as f:
                        f.write(f"\n{export_line}\n")
                    result["persist_file"] = profile
                except Exception as e:
                    result["persist_error"] = str(e)

        return result

    @staticmethod
    def unset(name: str, persistent: bool = False) -> dict[str, Any]:
        """Remove an environment variable."""
        existed = name in os.environ
        os.environ.pop(name, None)

        result = {"success": True, "name": name, "existed": existed}

        if persistent and PLATFORM != "windows":
            profile = os.path.expanduser("~/.bashrc")
            try:
                if os.path.exists(profile):
                    with open(profile) as f:
                        lines = f.readlines()
                    new_lines = [l for l in lines if not l.strip().startswith(f"export {name}=")]
                    with open(profile, "w") as f:
                        f.writelines(new_lines)
                    result["cleaned_profile"] = True
            except Exception as e:
                result["clean_error"] = str(e)

        return result


# ═══════════════════════════════════════════════════════════════
# Scheduled Tasks
# ═══════════════════════════════════════════════════════════════

class ScheduledTasks:
    """Manage scheduled tasks (crontab / Task Scheduler)."""

    @staticmethod
    def list_tasks() -> dict[str, Any]:
        """List scheduled tasks."""
        if PLATFORM == "windows":
            r = _run_safe(["schtasks", "/query", "/fo", "csv", "/nh"])
            return {"backend": "schtasks", "tasks": r.get("stdout", "")[:5000]}
        else:
            r = _run_safe(["crontab", "-l"])
            if r.get("success"):
                tasks = []
                for line in r["stdout"].strip().split("\n"):
                    line = line.strip()
                    if line and not line.startswith("#"):
                        tasks.append(line)
                return {"backend": "cron", "tasks": tasks, "count": len(tasks)}
            return {"backend": "cron", "tasks": [], "count": 0, "note": "No crontab found"}

    @staticmethod
    def add_task(schedule: str, command: str) -> dict[str, Any]:
        """Add a cron task. Schedule format: 'min hour day month weekday'."""
        if PLATFORM == "windows":
            # Windows schtasks
            r = _run_safe(["schtasks", "/create", "/tn", f"rally_{int(time.time())}", "/tr", command, "/sc", "daily"])
            return r

        # Unix cron
        try:
            r = _run(["crontab", "-l"], timeout=5)
            existing = r.stdout if r.returncode == 0 else ""
        except Exception:
            existing = ""

        new_entry = f"{schedule} {command}  # rally-agent"
        new_crontab = existing.rstrip() + "\n" + new_entry + "\n"

        try:
            proc = subprocess.run(["crontab", "-"], input=new_crontab, text=True, timeout=10)
            if proc.returncode == 0:
                return {"success": True, "entry": new_entry, "schedule": schedule, "command": command}
            return {"success": False, "error": proc.stderr}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    def remove_task(pattern: str) -> dict[str, Any]:
        """Remove cron tasks matching a pattern."""
        if PLATFORM == "windows":
            return _run_safe(["schtasks", "/delete", "/tn", pattern, "/f"])

        try:
            r = _run(["crontab", "-l"], timeout=5)
            if r.returncode != 0:
                return {"success": False, "error": "No crontab found"}
            lines = r.stdout.split("\n")
            removed = []
            kept = []
            for line in lines:
                if pattern in line and "rally-agent" in line:
                    removed.append(line.strip())
                else:
                    kept.append(line)
            if not removed:
                return {"success": False, "error": f"No matching tasks found for: {pattern}"}
            new_crontab = "\n".join(kept) + "\n"
            proc = subprocess.run(["crontab", "-"], input=new_crontab, text=True, timeout=10)
            return {"success": proc.returncode == 0, "removed": removed}
        except Exception as e:
            return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════
# Power Management
# ═══════════════════════════════════════════════════════════════

class PowerManagement:
    """System power operations (shutdown, restart, sleep)."""

    @staticmethod
    def shutdown(delay: int = 0, message: str = "System shutdown requested") -> dict[str, Any]:
        """Shutdown the system."""
        if PLATFORM == "windows":
            cmd = ["shutdown", "/s", "/t", str(delay)]
            if message:
                cmd.extend(["/c", message])
        elif PLATFORM == "darwin":
            cmd = ["osascript", "-e", f'tell app "System Events" to shut down']
        else:
            cmd = ["shutdown", "-h", f"+{delay}" if delay > 0 else "now"]
        return _run_safe(cmd)

    @staticmethod
    def restart(delay: int = 0, message: str = "System restart requested") -> dict[str, Any]:
        """Restart the system."""
        if PLATFORM == "windows":
            cmd = ["shutdown", "/r", "/t", str(delay)]
            if message:
                cmd.extend(["/c", message])
        elif PLATFORM == "darwin":
            cmd = ["osascript", "-e", 'tell app "System Events" to restart']
        else:
            cmd = ["shutdown", "-r", f"+{delay}" if delay > 0 else "now"]
        return _run_safe(cmd)

    @staticmethod
    def sleep() -> dict[str, Any]:
        """Put the system to sleep."""
        if PLATFORM == "windows":
            return _run_safe(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
        elif PLATFORM == "darwin":
            return _run_safe(["osascript", "-e", 'tell app "System Events" to sleep'])
        else:
            return _run_safe(["systemctl", "suspend"])


# ═══════════════════════════════════════════════════════════════
# Auto-Updater
# ═══════════════════════════════════════════════════════════════

class AutoUpdater:
    """Check for and apply Rally Agent updates."""

    RALLY_AGENT_DIR = os.path.expanduser("~/.rally-agent")
    VERSION_FILE = os.path.join(RALLY_AGENT_DIR, "version.json")

    @staticmethod
    def get_current_version() -> dict[str, Any]:
        """Get the current Rally Agent version."""
        if os.path.exists(AutoUpdater.VERSION_FILE):
            try:
                with open(AutoUpdater.VERSION_FILE) as f:
                    return json.load(f)
            except Exception:
                pass
        # Try git
        rally_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        try:
            r = _run(["git", "describe", "--tags", "--always"], timeout=5, cwd=rally_dir)
            if r.returncode == 0:
                return {"version": r.stdout.strip(), "source": "git"}
        except Exception:
            pass
        return {"version": "unknown", "source": "none"}

    @staticmethod
    def check_for_updates(repo: str = "rally-agent") -> dict[str, Any]:
        """Check if updates are available."""
        current = AutoUpdater.get_current_version()
        # Try to check via git remote
        rally_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        try:
            r = _run(["git", "fetch", "--dry-run"], timeout=15, cwd=rally_dir)
            # If there's output, there are updates
            has_updates = bool(r.stdout.strip()) or bool(r.stderr.strip())
            return {
                "current_version": current.get("version", "unknown"),
                "updates_available": has_updates,
                "repo": repo,
            }
        except Exception as e:
            return {
                "current_version": current.get("version", "unknown"),
                "updates_available": False,
                "error": str(e),
            }

    @staticmethod
    def apply_update() -> dict[str, Any]:
        """Pull latest updates and restart."""
        rally_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        try:
            r = _run(["git", "pull", "--rebase"], timeout=60, cwd=rally_dir)
            if r.returncode == 0:
                # Save version info
                version = AutoUpdater.get_current_version()
                os.makedirs(AutoUpdater.RALLY_AGENT_DIR, exist_ok=True)
                with open(AutoUpdater.VERSION_FILE, "w") as f:
                    json.dump({"version": version.get("version", "updated"), "updated_at": time.time()}, f, indent=2)
                return {"success": True, "output": r.stdout[:2000]}
            return {"success": False, "error": r.stderr[:2000]}
        except Exception as e:
            return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════
# Tool Definitions for Registry
# ═══════════════════════════════════════════════════════════════

class ProcessTool(BaseTool):
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="process",
            description="Manage system processes: list, find, get info, or kill processes.",
            category=ToolCategory.SYSTEM,
            parameters=[
                ToolParameter("action", "string", "Process action", required=True,
                    enum=["list", "find", "get", "kill"]),
                ToolParameter("pid", "integer", "Process ID (for get/kill)"),
                ToolParameter("name", "string", "Process name pattern (for find)"),
                ToolParameter("sort_by", "string", "Sort by 'cpu' or 'memory' (for list)", enum=["cpu", "memory"]),
                ToolParameter("limit", "integer", "Max results (for list, default 50)"),
                ToolParameter("force", "boolean", "Force kill (SIGKILL) instead of SIGTERM"),
            ],
            permission=PermissionLevel.AUTHENTICATED,
            dangerous=True,
            tags=["process", "ps", "kill", "system"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        action = arguments["action"]

        if action == "list":
            procs = ProcessManager.list_processes(
                sort_by=arguments.get("sort_by", "cpu"),
                limit=arguments.get("limit", 50),
            )
            return json.dumps({"processes": [p.to_dict() for p in procs], "count": len(procs)})

        elif action == "find":
            procs = ProcessManager.find_processes(arguments["name"])
            return json.dumps({"processes": [p.to_dict() for p in procs], "count": len(procs)})

        elif action == "get":
            proc = ProcessManager.get_process(arguments["pid"])
            if proc:
                return json.dumps(proc.to_dict())
            return json.dumps({"error": f"Process not found: {arguments['pid']}"})

        elif action == "kill":
            return json.dumps(ProcessManager.kill_process(arguments["pid"], arguments.get("force", False)))

        return json.dumps({"error": f"Unknown action: {action}"})


class ServiceTool(BaseTool):
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="service",
            description="Manage system services: list, start, stop, restart, enable, disable.",
            category=ToolCategory.SYSTEM,
            parameters=[
                ToolParameter("action", "string", "Service action", required=True,
                    enum=["list", "start", "stop", "restart", "status", "enable", "disable"]),
                ToolParameter("name", "string", "Service name"),
            ],
            permission=PermissionLevel.AUTHENTICATED,
            dangerous=True,
            tags=["service", "systemd", "launchd", "system"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        action = arguments["action"]

        if action == "list":
            return json.dumps({"services": ServiceManager.list_services()})
        else:
            name = arguments.get("name")
            if not name:
                return json.dumps({"error": "Service name required"})
            return json.dumps(ServiceManager.service_action(name, action))


class FileSystemTool(BaseTool):
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="filesystem",
            description="File system operations: watch for changes, get file info.",
            category=ToolCategory.SYSTEM,
            parameters=[
                ToolParameter("action", "string", "Action", required=True, enum=["watch", "info"]),
                ToolParameter("path", "string", "Path to watch or inspect", required=True),
                ToolParameter("duration", "integer", "Watch duration in seconds (default 10)"),
                ToolParameter("recursive", "boolean", "Watch recursively"),
            ],
            tags=["filesystem", "watch", "monitor", "system"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        action = arguments["action"]

        if action == "watch":
            return json.dumps(FileSystemWatcher.watch_directory(
                arguments["path"],
                arguments.get("duration", 10),
                arguments.get("recursive", False),
            ))
        elif action == "info":
            return json.dumps(FileSystemWatcher.get_file_info(arguments["path"]))
        return json.dumps({"error": f"Unknown action: {action}"})


class NetworkTool(BaseTool):
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="network",
            description="Network operations: list interfaces, connections, check ports, firewall status.",
            category=ToolCategory.SYSTEM,
            parameters=[
                ToolParameter("action", "string", "Network action", required=True,
                    enum=["interfaces", "connections", "check_port", "firewall"]),
                ToolParameter("port", "integer", "Port number (for check_port)"),
                ToolParameter("host", "string", "Host to check (default localhost)"),
                ToolParameter("limit", "integer", "Max results (for connections)"),
            ],
            tags=["network", "firewall", "port", "system"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        action = arguments["action"]

        if action == "interfaces":
            return json.dumps({"interfaces": NetworkControl.list_interfaces()})
        elif action == "connections":
            return json.dumps({"connections": NetworkControl.list_connections(arguments.get("limit", 50))})
        elif action == "check_port":
            return json.dumps(NetworkControl.check_port(arguments["port"], arguments.get("host", "localhost")))
        elif action == "firewall":
            return json.dumps(NetworkControl.firewall_status())
        return json.dumps({"error": f"Unknown action: {action}"})


class HardwareTool(BaseTool):
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="hardware",
            description="Get hardware information: CPU, memory, disk, GPU, full system info.",
            category=ToolCategory.SYSTEM,
            parameters=[
                ToolParameter("component", "string", "Hardware component", required=True,
                    enum=["cpu", "memory", "disk", "gpu", "system"]),
            ],
            tags=["hardware", "cpu", "memory", "disk", "gpu", "system"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        component = arguments["component"]

        if component == "cpu":
            return json.dumps(HardwareInfo.get_cpu_info())
        elif component == "memory":
            return json.dumps(HardwareInfo.get_memory_info())
        elif component == "disk":
            return json.dumps({"disks": HardwareInfo.get_disk_info()})
        elif component == "gpu":
            return json.dumps({"gpus": HardwareInfo.get_gpu_info()})
        elif component == "system":
            return json.dumps(HardwareInfo.get_system_info())
        return json.dumps({"error": f"Unknown component: {component}"})


class PackageTool(BaseTool):
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="package",
            description="Package management: install, remove, search, list, update, upgrade.",
            category=ToolCategory.SYSTEM,
            parameters=[
                ToolParameter("action", "string", "Package action", required=True,
                    enum=["install", "remove", "search", "list", "update_index", "upgrade_all", "detect"]),
                ToolParameter("package", "string", "Package name (for install/remove/search)"),
                ToolParameter("query", "string", "Search query (for search/list filter)"),
            ],
            permission=PermissionLevel.AUTHENTICATED,
            dangerous=True,
            tags=["package", "apt", "brew", "winget", "system"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        action = arguments["action"]

        if action == "detect":
            return json.dumps({"package_manager": PackageManager.detect()})
        elif action == "update_index":
            return json.dumps(PackageManager.update_index())
        elif action == "upgrade_all":
            return json.dumps(PackageManager.upgrade_all())
        elif action == "install":
            if not arguments.get("package"):
                return json.dumps({"error": "Package name required"})
            return json.dumps(PackageManager.install(arguments["package"]))
        elif action == "remove":
            if not arguments.get("package"):
                return json.dumps({"error": "Package name required"})
            return json.dumps(PackageManager.remove(arguments["package"]))
        elif action == "search":
            if not arguments.get("query"):
                return json.dumps({"error": "Search query required"})
            return json.dumps(PackageManager.search(arguments["query"]))
        elif action == "list":
            return json.dumps(PackageManager.list_installed(arguments.get("query")))
        return json.dumps({"error": f"Unknown action: {action}"})


class EnvironmentTool(BaseTool):
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="environment",
            description="Manage environment variables: get, set, unset, list.",
            category=ToolCategory.SYSTEM,
            parameters=[
                ToolParameter("action", "string", "Environment action", required=True,
                    enum=["get", "set", "unset", "list"]),
                ToolParameter("name", "string", "Variable name"),
                ToolParameter("value", "string", "Variable value (for set)"),
                ToolParameter("persistent", "boolean", "Persist to shell profile"),
            ],
            tags=["env", "environment", "variable", "system"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        action = arguments["action"]

        if action == "get":
            return json.dumps(EnvironmentManager.get(arguments.get("name")))
        elif action == "set":
            return json.dumps(EnvironmentManager.set(arguments["name"], arguments["value"], arguments.get("persistent", False)))
        elif action == "unset":
            return json.dumps(EnvironmentManager.unset(arguments["name"], arguments.get("persistent", False)))
        elif action == "list":
            return json.dumps(EnvironmentManager.get())
        return json.dumps({"error": f"Unknown action: {action}"})


class ScheduledTaskTool(BaseTool):
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="scheduled_task",
            description="Manage scheduled tasks (crontab on Unix, Task Scheduler on Windows).",
            category=ToolCategory.SYSTEM,
            parameters=[
                ToolParameter("action", "string", "Task action", required=True,
                    enum=["list", "add", "remove"]),
                ToolParameter("schedule", "string", "Cron schedule (e.g. '0 */6 * * *' for every 6 hours)"),
                ToolParameter("command", "string", "Command to schedule"),
                ToolParameter("pattern", "string", "Pattern to match for removal"),
            ],
            permission=PermissionLevel.AUTHENTICATED,
            dangerous=True,
            tags=["cron", "schedule", "task", "system"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        action = arguments["action"]

        if action == "list":
            return json.dumps(ScheduledTasks.list_tasks())
        elif action == "add":
            return json.dumps(ScheduledTasks.add_task(arguments["schedule"], arguments["command"]))
        elif action == "remove":
            return json.dumps(ScheduledTasks.remove_task(arguments["pattern"]))
        return json.dumps({"error": f"Unknown action: {action}"})


class PowerTool(BaseTool):
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="power",
            description="System power management: shutdown, restart, sleep. ⚠️ Destructive operations!",
            category=ToolCategory.SYSTEM,
            parameters=[
                ToolParameter("action", "string", "Power action", required=True,
                    enum=["shutdown", "restart", "sleep"]),
                ToolParameter("delay", "integer", "Delay in seconds (default 0)"),
                ToolParameter("message", "string", "Shutdown message"),
                ToolParameter("confirm", "boolean", "Confirm the destructive action (required for shutdown/restart)"),
            ],
            permission=PermissionLevel.ADMIN,
            dangerous=True,
            requires_confirmation=True,
            tags=["power", "shutdown", "restart", "sleep", "system"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        action = arguments["action"]

        if action == "sleep":
            return json.dumps(PowerManagement.sleep())

        if not arguments.get("confirm"):
            return json.dumps({
                "error": "Destructive action requires confirmation. Set 'confirm': true.",
                "action": action,
            })

        if action == "shutdown":
            return json.dumps(PowerManagement.shutdown(arguments.get("delay", 0), arguments.get("message", "")))
        elif action == "restart":
            return json.dumps(PowerManagement.restart(arguments.get("delay", 0), arguments.get("message", "")))
        return json.dumps({"error": f"Unknown action: {action}"})


class UpdateTool(BaseTool):
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="updater",
            description="Check for and apply Rally Agent updates.",
            category=ToolCategory.SYSTEM,
            parameters=[
                ToolParameter("action", "string", "Update action", required=True,
                    enum=["check", "apply", "version"]),
            ],
            permission=PermissionLevel.AUTHENTICATED,
            tags=["update", "upgrade", "version", "system"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        action = arguments["action"]

        if action == "version":
            return json.dumps(AutoUpdater.get_current_version())
        elif action == "check":
            return json.dumps(AutoUpdater.check_for_updates())
        elif action == "apply":
            return json.dumps(AutoUpdater.apply_update())
        return json.dumps({"error": f"Unknown action: {action}"})


# ═══════════════════════════════════════════════════════════════
# Registration Helper
# ═══════════════════════════════════════════════════════════════

def register_system_control_tools(registry: ToolRegistry) -> None:
    """Register all system control tools."""
    tools = [
        ProcessTool(),
        ServiceTool(),
        FileSystemTool(),
        NetworkTool(),
        HardwareTool(),
        PackageTool(),
        EnvironmentTool(),
        ScheduledTaskTool(),
        PowerTool(),
        UpdateTool(),
    ]

    for tool in tools:
        registry.register(tool)
