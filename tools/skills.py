"""
🟣 Rally Agent — Skills Registry
30+ production skills with proper function calling schemas, input validation, error handling.
Each skill is a BaseTool subclass registered through the ToolRegistry.
"""

from __future__ import annotations

import asyncio
import base64
import csv
import hashlib
import io
import json
import math
import os
import random
import re
import shutil
import string
import subprocess
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Optional

from tools.registry import (
    BaseTool,
    ToolCategory,
    ToolDefinition,
    ToolParameter,
    PermissionLevel,
    ToolRegistry,
)


# ═══════════════════════════════════════════════════════════════
# Helper
# ═══════════════════════════════════════════════════════════════

def _run_cmd(cmd: str, timeout: int = 30) -> dict[str, Any]:
    """Run a shell command synchronously and return structured output."""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return {"exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
    except subprocess.TimeoutExpired:
        return {"exit_code": -1, "stdout": "", "stderr": f"Command timed out ({timeout}s)"}
    except Exception as e:
        return {"exit_code": -1, "stdout": "", "stderr": str(e)}


async def _run_cmd_async(cmd: str, timeout: int = 30) -> dict[str, Any]:
    """Run a shell command asynchronously."""
    try:
        proc = await asyncio.create_subprocess_shell(
            cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return {
            "exit_code": proc.returncode,
            "stdout": stdout.decode("utf-8", errors="replace"),
            "stderr": stderr.decode("utf-8", errors="replace"),
        }
    except asyncio.TimeoutError:
        return {"exit_code": -1, "stdout": "", "stderr": f"Timed out ({timeout}s)"}
    except Exception as e:
        return {"exit_code": -1, "stdout": "", "stderr": str(e)}


# ═══════════════════════════════════════════════════════════════
# SYSTEM SKILLS
# ═══════════════════════════════════════════════════════════════

class SystemInfoSkill(BaseTool):
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="system_info",
            description="Get system information: OS, CPU, memory, disk, network, processes.",
            category=ToolCategory.SYSTEM,
            parameters=[
                ToolParameter("query", "string", "What to query",
                    enum=["os", "cpu", "memory", "disk", "network", "processes", "uptime", "hostname", "all"], required=True),
            ],
            tags=["system", "info", "monitor"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        query = arguments["query"]
        cmds = {
            "os": "uname -a",
            "cpu": "top -bn1 | head -5",
            "memory": "free -h",
            "disk": "df -h",
            "network": "ip addr show 2>/dev/null || ifconfig",
            "processes": "ps aux --sort=-%mem | head -20",
            "uptime": "uptime",
            "hostname": "hostname",
        }

        if query == "all":
            results = {}
            for key, cmd in cmds.items():
                results[key] = _run_cmd(cmd, timeout=5)
            return json.dumps(results, indent=2)

        cmd = cmds.get(query)
        if cmd:
            return json.dumps(_run_cmd(cmd, timeout=10))
        return json.dumps({"error": f"Unknown query: {query}"})


class GitSkill(BaseTool):
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="git",
            description="Execute Git operations: status, log, diff, branch, commit, push, pull, clone, stash.",
            category=ToolCategory.DEVOPS,
            parameters=[
                ToolParameter("command", "string", "Git subcommand", required=True,
                    enum=["status", "log", "diff", "branch", "commit", "push", "pull", "clone", "stash", "checkout", "merge", "remote"]),
                ToolParameter("args", "string", "Additional arguments for the git command"),
                ToolParameter("repo_path", "string", "Path to the repository"),
            ],
            tags=["git", "version-control", "dev"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        command = arguments["command"]
        args = arguments.get("args", "")
        repo = arguments.get("repo_path", ".")

        # Sanitize: prevent command injection via git args
        if any(c in args for c in [";", "|", "&", "$", "`", "\n"]):
            return json.dumps({"error": "Invalid characters in arguments"})

        cmd = f"git -C {repo} {command} {args}".strip()
        result = _run_cmd(cmd, timeout=30)
        # Truncate output
        result["stdout"] = result["stdout"][:10000]
        return json.dumps(result)


class DockerSkill(BaseTool):
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="docker",
            description="Manage Docker containers and images: ps, images, build, run, logs, stop, rm, exec, compose.",
            category=ToolCategory.DEVOPS,
            parameters=[
                ToolParameter("command", "string", "Docker subcommand", required=True,
                    enum=["ps", "images", "build", "run", "logs", "stop", "rm", "exec", "pull", "push",
                          "inspect", "stats", "compose_up", "compose_down", "compose_ps"]),
                ToolParameter("args", "string", "Additional arguments"),
                ToolParameter("compose_file", "string", "Path to docker-compose file"),
            ],
            permission=PermissionLevel.AUTHENTICATED,
            rate_limit_per_minute=30,
            tags=["docker", "container", "devops"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        command = arguments["command"]
        args = arguments.get("args", "")
        compose_file = arguments.get("compose_file", "docker-compose.yml")

        compose_cmds = {"compose_up", "compose_down", "compose_ps"}
        if command in compose_cmds:
            sub = command.replace("compose_", "")
            cmd = f"docker compose -f {compose_file} {sub} {args}"
        else:
            cmd = f"docker {command} {args}"

        result = await _run_cmd_async(cmd, timeout=120)
        result["stdout"] = result["stdout"][:10000]
        return json.dumps(result)


class KubernetesSkill(BaseTool):
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="kubernetes",
            description="Manage Kubernetes resources: get, describe, logs, apply, delete, scale, port-forward.",
            category=ToolCategory.DEVOPS,
            parameters=[
                ToolParameter("command", "string", "kubectl subcommand", required=True,
                    enum=["get", "describe", "logs", "apply", "delete", "scale", "port-forward",
                          "exec", "top", "config", "context"]),
                ToolParameter("args", "string", "Additional arguments (e.g. 'pods -n default')"),
                ToolParameter("namespace", "string", "Kubernetes namespace"),
                ToolParameter("kubeconfig", "string", "Path to kubeconfig file"),
            ],
            permission=PermissionLevel.AUTHENTICATED,
            rate_limit_per_minute=30,
            tags=["kubernetes", "k8s", "devops", "orchestration"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        command = arguments["command"]
        args = arguments.get("args", "")
        namespace = arguments.get("namespace")
        kubeconfig = arguments.get("kubeconfig")

        cmd_parts = ["kubectl"]
        if kubeconfig:
            cmd_parts.extend(["--kubeconfig", kubeconfig])
        if namespace and command not in ("config", "context"):
            cmd_parts.extend(["-n", namespace])
        cmd_parts.append(command)
        if args:
            cmd_parts.append(args)

        cmd = " ".join(cmd_parts)
        result = await _run_cmd_async(cmd, timeout=60)
        result["stdout"] = result["stdout"][:15000]
        return json.dumps(result)


class PackageManagerSkill(BaseTool):
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="package_manager",
            description="Manage system/language packages: pip, npm, apt, brew, cargo, go.",
            category=ToolCategory.SYSTEM,
            parameters=[
                ToolParameter("manager", "string", "Package manager", required=True,
                    enum=["pip", "npm", "apt", "brew", "cargo", "go"]),
                ToolParameter("command", "string", "Command (install, uninstall, list, update, etc.)", required=True),
                ToolParameter("packages", "string", "Space-separated package names"),
                ToolParameter("sudo", "boolean", "Use sudo (for apt)"),
            ],
            permission=PermissionLevel.AUTHENTICATED,
            rate_limit_per_minute=10,
            tags=["packages", "install", "system"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        manager = arguments["manager"]
        command = arguments["command"]
        packages = arguments.get("packages", "")
        use_sudo = arguments.get("sudo", False)

        prefix = "sudo " if use_sudo and manager == "apt" else ""
        cmd = f"{prefix}{manager} {command} {packages}".strip()
        result = await _run_cmd_async(cmd, timeout=120)
        result["stdout"] = result["stdout"][:10000]
        return json.dumps(result)


# ═══════════════════════════════════════════════════════════════
# DATABASE SKILLS
# ═══════════════════════════════════════════════════════════════

class SQLiteSkill(BaseTool):
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="sqlite",
            description="Query and manage SQLite databases: execute SQL, list tables, show schema, dump data.",
            category=ToolCategory.DATABASE,
            parameters=[
                ToolParameter("db_path", "string", "Path to SQLite database file", required=True),
                ToolParameter("action", "string", "Action to perform",
                    enum=["query", "tables", "schema", "dump", "execute"], required=True),
                ToolParameter("sql", "string", "SQL query or statement"),
                ToolParameter("table", "string", "Table name (for schema/dump)"),
            ],
            permission=PermissionLevel.AUTHENTICATED,
            tags=["sqlite", "database", "sql", "query"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        import sqlite3

        db_path = arguments["db_path"]
        action = arguments["action"]
        sql = arguments.get("sql", "")
        table = arguments.get("table", "")

        if not os.path.exists(db_path):
            return json.dumps({"error": f"Database not found: {db_path}"})

        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row

            if action == "tables":
                rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
                return json.dumps({"tables": [r["name"] for r in rows]})

            elif action == "schema":
                target = table or "ALL"
                if target == "ALL":
                    rows = conn.execute("SELECT sql FROM sqlite_master WHERE sql IS NOT NULL").fetchall()
                    return json.dumps({"schema": [r["sql"] for r in rows]})
                else:
                    row = conn.execute("SELECT sql FROM sqlite_master WHERE name=?", (table,)).fetchone()
                    return json.dumps({"table": table, "schema": row["sql"] if row else None})

            elif action == "query":
                if not sql:
                    return json.dumps({"error": "SQL query required"})
                rows = conn.execute(sql).fetchall()
                result = [dict(r) for r in rows[:500]]
                return json.dumps({"rows": result, "count": len(result)})

            elif action == "execute":
                if not sql:
                    return json.dumps({"error": "SQL statement required"})
                conn.execute(sql)
                conn.commit()
                return json.dumps({"success": True, "message": "Statement executed"})

            elif action == "dump":
                target = table or "ALL"
                if target == "ALL":
                    dump = "\n".join(conn.iterdump())
                else:
                    dump = "\n".join(
                        line for line in conn.iterdump()
                        if line.startswith(f"CREATE TABLE {table}") or
                           line.startswith(f"INSERT INTO {table}")
                    )
                return json.dumps({"dump": dump[:50000]})

            conn.close()
        except Exception as e:
            return json.dumps({"error": str(e)})
        return json.dumps({"error": f"Unknown action: {action}"})


class PostgresSkill(BaseTool):
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="postgres",
            description="Query PostgreSQL via psql CLI. Requires connection string or env vars.",
            category=ToolCategory.DATABASE,
            parameters=[
                ToolParameter("sql", "string", "SQL query to execute", required=True),
                ToolParameter("connection_string", "string", "PostgreSQL connection string (postgresql://user:pass@host/db)"),
                ToolParameter("database", "string", "Database name"),
                ToolParameter("format", "string", "Output format", enum=["table", "csv", "json"]),
            ],
            permission=PermissionLevel.AUTHENTICATED,
            tags=["postgres", "postgresql", "database", "sql"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        sql = arguments["sql"]
        conn_str = arguments.get("connection_string", "")
        database = arguments.get("database", "")
        fmt = arguments.get("format", "table")

        # Build psql command
        fmt_flag = {"table": "", "csv": "--csv", "json": "--json"}.get(fmt, "")
        conn_flag = f"'{conn_str}'" if conn_str else database

        cmd = f"psql {conn_flag} {fmt_flag} -c \"{sql}\" 2>&1"
        result = await _run_cmd_async(cmd, timeout=30)
        result["stdout"] = result["stdout"][:10000]
        return json.dumps(result)


class RedisSkill(BaseTool):
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="redis",
            description="Execute Redis commands via redis-cli.",
            category=ToolCategory.DATABASE,
            parameters=[
                ToolParameter("command", "string", "Redis command (GET, SET, DEL, KEYS, HGET, etc.)", required=True),
                ToolParameter("args", "string", "Command arguments"),
                ToolParameter("host", "string", "Redis host (default: localhost)"),
                ToolParameter("port", "integer", "Redis port (default: 6379)"),
                ToolParameter("password", "string", "Redis password"),
            ],
            permission=PermissionLevel.AUTHENTICATED,
            tags=["redis", "cache", "database"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        command = arguments["command"].upper()
        args = arguments.get("args", "")
        host = arguments.get("host", "localhost")
        port = arguments.get("port", 6379)
        password = arguments.get("password", "")

        auth = f"-a {password}" if password else ""
        cmd = f"redis-cli -h {host} -p {port} {auth} {command} {args}".strip()
        result = await _run_cmd_async(cmd, timeout=15)
        return json.dumps({"command": command, "result": result["stdout"].strip(), "error": result["stderr"]})


# ═══════════════════════════════════════════════════════════════
# FILE COMPRESSION SKILLS
# ═══════════════════════════════════════════════════════════════

class FileCompressionSkill(BaseTool):
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="compress",
            description="Compress and decompress files: zip, tar.gz, gzip, bzip2, xz.",
            category=ToolCategory.FILES,
            parameters=[
                ToolParameter("action", "string", "Action: compress or decompress", enum=["compress", "decompress"], required=True),
                ToolParameter("format", "string", "Archive format", enum=["zip", "tar.gz", "gzip", "bzip2", "xz"], required=True),
                ToolParameter("source", "string", "Source file or directory path", required=True),
                ToolParameter("destination", "string", "Destination path"),
                ToolParameter("password", "string", "Password (zip only)"),
            ],
            tags=["compress", "archive", "zip", "tar", "gzip"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        action = arguments["action"]
        fmt = arguments["format"]
        source = arguments["source"]
        dest = arguments.get("destination", "")
        password = arguments.get("password", "")

        if not os.path.exists(source):
            return json.dumps({"error": f"Source not found: {source}"})

        try:
            if action == "compress":
                if fmt == "zip":
                    import zipfile
                    if not dest:
                        dest = source.rstrip("/") + ".zip"
                    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
                        if os.path.isfile(source):
                            zf.write(source, os.path.basename(source))
                        else:
                            for root, dirs, files in os.walk(source):
                                for f in files:
                                    fpath = os.path.join(root, f)
                                    arcname = os.path.relpath(fpath, os.path.dirname(source))
                                    zf.write(fpath, arcname)
                    return json.dumps({"success": True, "destination": dest, "format": "zip"})

                elif fmt == "tar.gz":
                    if not dest:
                        dest = source.rstrip("/") + ".tar.gz"
                    cmd = f"tar czf {dest} -C {os.path.dirname(source)} {os.path.basename(source)}"
                    return json.dumps(_run_cmd(cmd))

                elif fmt == "gzip":
                    if not dest:
                        dest = source + ".gz"
                    cmd = f"gzip -c {source} > {dest}"
                    return json.dumps(_run_cmd(cmd))

                elif fmt == "bzip2":
                    if not dest:
                        dest = source + ".bz2"
                    cmd = f"bzip2 -c {source} > {dest}"
                    return json.dumps(_run_cmd(cmd))

                elif fmt == "xz":
                    if not dest:
                        dest = source + ".xz"
                    cmd = f"xz -c {source} > {dest}"
                    return json.dumps(_run_cmd(cmd))

            elif action == "decompress":
                if fmt == "zip":
                    import zipfile
                    if not dest:
                        dest = os.path.dirname(source) or "."
                    with zipfile.ZipFile(source, "r") as zf:
                        zf.extractall(dest)
                    return json.dumps({"success": True, "destination": dest})

                elif fmt == "tar.gz":
                    if not dest:
                        dest = os.path.dirname(source) or "."
                    cmd = f"tar xzf {source} -C {dest}"
                    return json.dumps(_run_cmd(cmd))

                elif fmt == "gzip":
                    cmd = f"gunzip -c {source}"
                    if dest:
                        cmd += f" > {dest}"
                    return json.dumps(_run_cmd(cmd))

                elif fmt in ("bzip2", "xz"):
                    tool = "bunzip2" if fmt == "bzip2" else "unxz"
                    cmd = f"{tool} -c {source}"
                    if dest:
                        cmd += f" > {dest}"
                    return json.dumps(_run_cmd(cmd))

        except Exception as e:
            return json.dumps({"error": str(e)})

        return json.dumps({"error": f"Unsupported action/format: {action}/{fmt}"})


# ═══════════════════════════════════════════════════════════════
# IMAGE PROCESSING SKILLS
# ═══════════════════════════════════════════════════════════════

class ImageProcessingSkill(BaseTool):
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="image",
            description="Process images: resize, crop, rotate, convert format, get info, apply filters, add watermark.",
            category=ToolCategory.MEDIA,
            parameters=[
                ToolParameter("action", "string", "Image operation", required=True,
                    enum=["info", "resize", "crop", "rotate", "convert", "thumbnail", "grayscale",
                          "blur", "sharpen", "brightness", "contrast", "watermark", "compress"]),
                ToolParameter("source", "string", "Source image path or URL", required=True),
                ToolParameter("destination", "string", "Output path"),
                ToolParameter("width", "integer", "Target width"),
                ToolParameter("height", "integer", "Target height"),
                ToolParameter("format", "string", "Output format (png, jpeg, webp, gif)"),
                ToolParameter("quality", "integer", "Output quality (1-100)"),
                ToolParameter("angle", "number", "Rotation angle in degrees"),
                ToolParameter("text", "string", "Text for watermark"),
            ],
            tags=["image", "resize", "convert", "media", "photo"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        action = arguments["action"]
        source = arguments["source"]
        dest = arguments.get("destination", "")

        try:
            from PIL import Image, ImageFilter, ImageEnhance, ImageDraw, ImageFont
        except ImportError:
            # Fallback to ImageMagick CLI
            return await self._execute_imagemagick(arguments)

        try:
            if action == "info":
                if source.startswith("http"):
                    import httpx
                    async with httpx.AsyncClient() as client:
                        resp = await client.get(source)
                        img = Image.open(io.BytesIO(resp.content))
                else:
                    img = Image.open(source)
                return json.dumps({
                    "format": img.format, "mode": img.mode,
                    "width": img.width, "height": img.height,
                    "size_bytes": os.path.getsize(source) if not source.startswith("http") else None,
                })

            img = Image.open(source)

            if action == "resize":
                w = arguments.get("width", img.width)
                h = arguments.get("height", img.height)
                img = img.resize((w, h), Image.LANCZOS)

            elif action == "crop":
                w = arguments.get("width", img.width // 2)
                h = arguments.get("height", img.height // 2)
                left = (img.width - w) // 2
                top = (img.height - h) // 2
                img = img.crop((left, top, left + w, top + h))

            elif action == "rotate":
                angle = arguments.get("angle", 90)
                img = img.rotate(angle, expand=True)

            elif action == "thumbnail":
                size = (arguments.get("width", 256), arguments.get("height", 256))
                img.thumbnail(size, Image.LANCZOS)

            elif action == "grayscale":
                img = img.convert("L")

            elif action == "blur":
                img = img.filter(ImageFilter.GaussianBlur(radius=5))

            elif action == "sharpen":
                img = img.filter(ImageFilter.SHARPEN)

            elif action == "brightness":
                factor = arguments.get("quality", 150) / 100
                enhancer = ImageEnhance.Brightness(img)
                img = enhancer.enhance(factor)

            elif action == "contrast":
                factor = arguments.get("quality", 150) / 100
                enhancer = ImageEnhance.Contrast(img)
                img = enhancer.enhance(factor)

            elif action == "watermark":
                text = arguments.get("text", "Rally Agent")
                if img.mode != "RGBA":
                    img = img.convert("RGBA")
                overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
                draw = ImageDraw.Draw(overlay)
                try:
                    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 36)
                except Exception:
                    font = ImageFont.load_default()
                bbox = draw.textbbox((0, 0), text, font=font)
                tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
                x = img.width - tw - 20
                y = img.height - th - 20
                draw.text((x, y), text, fill=(255, 255, 255, 128), font=font)
                img = Image.alpha_composite(img, overlay)

            elif action == "compress":
                quality = arguments.get("quality", 85)
                if not dest:
                    dest = source.rsplit(".", 1)[0] + "_compressed.jpg"
                img = img.convert("RGB")
                img.save(dest, "JPEG", quality=quality, optimize=True)
                return json.dumps({
                    "success": True, "destination": dest,
                    "original_size": os.path.getsize(source),
                    "compressed_size": os.path.getsize(dest),
                })

            # Save output
            if not dest:
                base, ext = os.path.splitext(source)
                fmt = arguments.get("format", ext.lstrip(".") or "png")
                dest = f"{base}_processed.{fmt}"

            save_fmt = arguments.get("format", os.path.splitext(dest)[1].lstrip(".") or "png").upper()
            if save_fmt == "JPG":
                save_fmt = "JPEG"
            if save_fmt == "JPEG" and img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            quality = arguments.get("quality", 90)
            img.save(dest, save_fmt, quality=quality)
            return json.dumps({"success": True, "destination": dest, "width": img.width, "height": img.height})

        except Exception as e:
            return json.dumps({"error": str(e)})

    async def _execute_imagemagick(self, arguments: dict[str, Any]) -> str:
        """Fallback using ImageMagick CLI."""
        action = arguments["action"]
        source = arguments["source"]
        dest = arguments.get("destination", "")

        if action == "info":
            result = _run_cmd(f"identify -verbose {source} | head -20")
            return json.dumps({"info": result["stdout"][:2000]})

        if not dest:
            dest = f"output_{action}.png"

        cmds = {
            "resize": f"convert {source} -resize {arguments.get('width', 800)}x{arguments.get('height', 600)} {dest}",
            "crop": f"convert {source} -gravity center -crop {arguments.get('width', 400)}x{arguments.get('height', 400)}+0+0 {dest}",
            "rotate": f"convert {source} -rotate {arguments.get('angle', 90)} {dest}",
            "grayscale": f"convert {source} -colorspace Gray {dest}",
            "blur": f"convert {source} -blur 0x5 {dest}",
            "sharpen": f"convert {source} -sharpen 0x5 {dest}",
            "thumbnail": f"convert {source} -thumbnail {arguments.get('width', 256)}x{arguments.get('height', 256)} {dest}",
            "convert": f"convert {source} {dest}",
            "compress": f"convert {source} -quality {arguments.get('quality', 85)} {dest}",
        }

        cmd = cmds.get(action)
        if cmd:
            return json.dumps(_run_cmd(cmd))
        return json.dumps({"error": f"Unsupported action: {action}"})


# ═══════════════════════════════════════════════════════════════
# PDF GENERATION SKILL
# ═══════════════════════════════════════════════════════════════

class PDFSkill(BaseTool):
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="pdf",
            description="Generate PDFs from text/HTML, merge PDFs, extract text, split pages.",
            category=ToolCategory.MEDIA,
            parameters=[
                ToolParameter("action", "string", "PDF operation", required=True,
                    enum=["generate", "merge", "extract_text", "split", "info"]),
                ToolParameter("content", "string", "Text or HTML content for generation"),
                ToolParameter("sources", "array", "List of PDF file paths (for merge/split)"),
                ToolParameter("destination", "string", "Output PDF path"),
                ToolParameter("page_size", "string", "Page size", enum=["A4", "Letter", "Legal"]),
                ToolParameter("margins", "integer", "Page margins in points"),
            ],
            tags=["pdf", "generate", "document"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        action = arguments["action"]
        dest = arguments.get("destination", "output.pdf")

        try:
            if action == "generate":
                content = arguments.get("content", "")
                if not content:
                    return json.dumps({"error": "Content required for PDF generation"})

                # Try reportlab first
                try:
                    from reportlab.lib.pagesizes import A4, letter, legal
                    from reportlab.pdfgen import canvas
                    from reportlab.lib.units import inch

                    sizes = {"A4": A4, "Letter": letter, "Legal": legal}
                    page_size = sizes.get(arguments.get("page_size", "A4"), A4)
                    margins = arguments.get("margins", 72)

                    c = canvas.Canvas(dest, pagesize=page_size)
                    width, height = page_size
                    text_obj = c.beginText(margins, height - margins)
                    text_obj.setFont("Helvetica", 11)

                    for line in content.split("\n"):
                        # Wrap long lines
                        while len(line) > 90:
                            text_obj.textLine(line[:90])
                            line = line[90:]
                        text_obj.textLine(line)
                        if text_obj.getY() < margins:
                            c.drawText(text_obj)
                            c.showPage()
                            text_obj = c.beginText(margins, height - margins)
                            text_obj.setFont("Helvetica", 11)

                    c.drawText(text_obj)
                    c.save()
                    return json.dumps({"success": True, "destination": dest, "pages": "generated"})

                except ImportError:
                    # Fallback: use HTML -> PDF via wkhtmltopdf or pandoc
                    html_content = f"<html><body><pre style='font-family: monospace; font-size: 11px;'>{content}</pre></body></html>"
                    html_file = dest + ".html"
                    with open(html_file, "w") as f:
                        f.write(html_content)
                    result = _run_cmd(f"wkhtmltopdf {html_file} {dest} 2>/dev/null || pandoc {html_file} -o {dest} 2>/dev/null")
                    os.unlink(html_file)
                    if os.path.exists(dest):
                        return json.dumps({"success": True, "destination": dest})
                    return json.dumps({"error": "No PDF generation library available. Install reportlab or wkhtmltopdf."})

            elif action == "merge":
                sources = arguments.get("sources", [])
                if len(sources) < 2:
                    return json.dumps({"error": "At least 2 PDF files required for merge"})
                try:
                    from PyPDF2 import PdfMerger
                    merger = PdfMerger()
                    for src in sources:
                        merger.append(src)
                    merger.write(dest)
                    merger.close()
                    return json.dumps({"success": True, "destination": dest, "merged": len(sources)})
                except ImportError:
                    # Fallback to ghostscript
                    cmd = f"gs -dBATCH -dNOPAUSE -q -sDEVICE=pdfwrite -sOutputFile={dest} {' '.join(sources)}"
                    return json.dumps(_run_cmd(cmd))

            elif action == "extract_text":
                source = arguments.get("sources", [None])[0] if arguments.get("sources") else arguments.get("content", "")
                if not source or not os.path.exists(source):
                    return json.dumps({"error": "Source PDF path required"})
                try:
                    from PyPDF2 import PdfReader
                    reader = PdfReader(source)
                    text = ""
                    for page in reader.pages:
                        text += page.extract_text() or ""
                    return json.dumps({"text": text[:50000], "pages": len(reader.pages)})
                except ImportError:
                    result = _run_cmd(f"pdftotext {source} -")
                    return json.dumps({"text": result["stdout"][:50000]})

            elif action == "info":
                source = arguments.get("sources", [None])[0] if arguments.get("sources") else ""
                if not source or not os.path.exists(source):
                    return json.dumps({"error": "Source PDF path required"})
                try:
                    from PyPDF2 import PdfReader
                    reader = PdfReader(source)
                    return json.dumps({
                        "pages": len(reader.pages),
                        "metadata": reader.metadata,
                        "size_bytes": os.path.getsize(source),
                    })
                except ImportError:
                    result = _run_cmd(f"pdfinfo {source}")
                    return json.dumps({"info": result["stdout"]})

        except Exception as e:
            return json.dumps({"error": str(e)})

        return json.dumps({"error": f"Unsupported action: {action}"})


# ═══════════════════════════════════════════════════════════════
# DATA & ANALYSIS SKILLS
# ═══════════════════════════════════════════════════════════════

class DataAnalysisSkill(BaseTool):
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="data_analysis",
            description="Analyze data: CSV parsing, statistics, correlation, summary, filtering.",
            category=ToolCategory.DATA,
            parameters=[
                ToolParameter("action", "string", "Analysis action", required=True,
                    enum=["parse_csv", "statistics", "correlation", "filter", "summary", "groupby"]),
                ToolParameter("data", "string", "CSV data or file path", required=True),
                ToolParameter("columns", "array", "Columns to analyze"),
                ToolParameter("filter_expr", "string", "Filter expression (e.g. 'age > 30')"),
                ToolParameter("group_by", "string", "Column to group by"),
                ToolParameter("agg", "string", "Aggregation function", enum=["sum", "mean", "count", "min", "max"]),
            ],
            tags=["data", "csv", "analysis", "statistics"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        action = arguments["action"]
        data_src = arguments["data"]
        columns = arguments.get("columns", [])

        try:
            # Load data
            if os.path.exists(data_src):
                with open(data_src, "r") as f:
                    reader = csv.DictReader(f)
                    rows = list(reader)
            else:
                reader = csv.DictReader(io.StringIO(data_src))
                rows = list(reader)

            if not rows:
                return json.dumps({"error": "No data found"})

            if action == "parse_csv":
                return json.dumps({
                    "columns": list(rows[0].keys()),
                    "row_count": len(rows),
                    "preview": rows[:5],
                })

            elif action == "statistics":
                target_cols = columns or list(rows[0].keys())
                stats = {}
                for col in target_cols:
                    try:
                        values = [float(row[col]) for row in rows if row.get(col)]
                        if not values:
                            continue
                        n = len(values)
                        mean = sum(values) / n
                        sorted_v = sorted(values)
                        median = sorted_v[n // 2]
                        variance = sum((x - mean) ** 2 for x in values) / n
                        stats[col] = {
                            "count": n, "mean": round(mean, 4), "median": round(median, 4),
                            "std": round(math.sqrt(variance), 4),
                            "min": min(values), "max": max(values),
                            "sum": round(sum(values), 4),
                        }
                    except (ValueError, KeyError):
                        continue
                return json.dumps({"statistics": stats})

            elif action == "filter":
                expr = arguments.get("filter_expr", "")
                if not expr:
                    return json.dumps({"error": "filter_expr required"})
                # Simple filter: "column op value"
                match = re.match(r"(\w+)\s*(>|<|>=|<=|==|!=)\s*(.+)", expr)
                if not match:
                    return json.dumps({"error": "Invalid filter expression"})
                col, op, val = match.groups()
                val = val.strip().strip('"').strip("'")
                ops = {">": lambda a, b: a > b, "<": lambda a, b: a < b,
                       ">=": lambda a, b: a >= b, "<=": lambda a, b: a <= b,
                       "==": lambda a, b: str(a) == str(b), "!=": lambda a, b: str(a) != str(b)}
                filtered = []
                for row in rows:
                    try:
                        rv = float(row.get(col, 0))
                        fv = float(val)
                        if ops[op](rv, fv):
                            filtered.append(row)
                    except ValueError:
                        if ops[op](row.get(col, ""), val):
                            filtered.append(row)
                return json.dumps({"filtered_count": len(filtered), "rows": filtered[:100]})

            elif action == "summary":
                return json.dumps({
                    "columns": list(rows[0].keys()),
                    "row_count": len(rows),
                    "column_types": {
                        col: "numeric" if all(self._is_numeric(r.get(col)) for r in rows if r.get(col)) else "text"
                        for col in rows[0].keys()
                    },
                })

        except Exception as e:
            return json.dumps({"error": str(e)})
        return json.dumps({"error": f"Unknown action: {action}"})

    @staticmethod
    def _is_numeric(val: Any) -> bool:
        try:
            float(str(val))
            return True
        except (ValueError, TypeError):
            return False


class JSONPathSkill(BaseTool):
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="jsonpath",
            description="Query JSON data using JSONPath expressions or jq-style queries.",
            category=ToolCategory.DATA,
            parameters=[
                ToolParameter("data", "string", "JSON data string", required=True),
                ToolParameter("query", "string", "JSONPath or dot-notation query (e.g. 'store.books[0].title')", required=True),
            ],
            tags=["json", "jsonpath", "query", "data"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        data_str = arguments["data"]
        query = arguments["query"]

        try:
            data = json.loads(data_str)
        except json.JSONDecodeError as e:
            return json.dumps({"error": f"Invalid JSON: {e}"})

        # Simple JSONPath: dot notation + array indices
        try:
            result = data
            for part in re.split(r"\.(?![^\[]*\])", query):
                if not part:
                    continue
                # Handle array index: key[0]
                match = re.match(r"(\w+)\[(\d+)\]", part)
                if match:
                    key, idx = match.groups()
                    if key:
                        result = result[key]
                    result = result[int(idx)]
                elif part.endswith("]") and "[" in part:
                    key, idx = part[:-1].split("[")
                    result = result[key][int(idx)]
                else:
                    result = result[part]
            return json.dumps({"query": query, "result": result})
        except (KeyError, IndexError, TypeError) as e:
            return json.dumps({"error": f"Query failed: {e}"})


# ═══════════════════════════════════════════════════════════════
# UTILITY SKILLS
# ═══════════════════════════════════════════════════════════════

class UnitConverterSkill(BaseTool):
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="unit_convert",
            description="Convert between units: length, weight, temperature, speed, data size, currency.",
            category=ToolCategory.UTILITY,
            parameters=[
                ToolParameter("value", "number", "Value to convert", required=True),
                ToolParameter("from_unit", "string", "Source unit", required=True),
                ToolParameter("to_unit", "string", "Target unit", required=True),
            ],
            tags=["convert", "units", "measurement"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        value = float(arguments["value"])
        from_u = arguments["from_unit"].lower().strip()
        to_u = arguments["to_unit"].lower().strip()

        # Conversion tables (everything to base unit)
        conversions = {
            # Length -> meters
            "mm": 0.001, "cm": 0.01, "m": 1, "km": 1000,
            "in": 0.0254, "ft": 0.3048, "yd": 0.9144, "mi": 1609.344,
            # Weight -> grams
            "mg": 0.001, "g": 1, "kg": 1000, "ton": 1_000_000,
            "oz": 28.3495, "lb": 453.592,
            # Data -> bytes
            "b": 1, "kb": 1024, "mb": 1048576, "gb": 1073741824, "tb": 1099511627776,
            # Speed -> m/s
            "m/s": 1, "km/h": 0.277778, "mph": 0.44704, "knot": 0.514444,
        }

        # Temperature (special handling)
        temp_units = {"c", "f", "k", "celsius", "fahrenheit", "kelvin"}
        if from_u in temp_units or to_u in temp_units:
            result = self._convert_temperature(value, from_u, to_u)
            if result is not None:
                return json.dumps({"value": value, "from": from_u, "to": to_u, "result": round(result, 4)})
            return json.dumps({"error": f"Unknown temperature unit: {from_u} or {to_u}"})

        from_factor = conversions.get(from_u)
        to_factor = conversions.get(to_u)

        if from_factor is None:
            return json.dumps({"error": f"Unknown unit: {from_u}"})
        if to_factor is None:
            return json.dumps({"error": f"Unknown unit: {to_u}"})

        base_value = value * from_factor
        result = base_value / to_factor

        return json.dumps({"value": value, "from": from_u, "to": to_u, "result": round(result, 6)})

    @staticmethod
    def _convert_temperature(value: float, from_u: str, to_u: str) -> Optional[float]:
        # Normalize
        aliases = {"celsius": "c", "fahrenheit": "f", "kelvin": "k"}
        from_u = aliases.get(from_u, from_u)
        to_u = aliases.get(to_u, to_u)

        # Convert to Celsius first
        if from_u == "c":
            c = value
        elif from_u == "f":
            c = (value - 32) * 5 / 9
        elif from_u == "k":
            c = value - 273.15
        else:
            return None

        # Convert from Celsius to target
        if to_u == "c":
            return c
        elif to_u == "f":
            return c * 9 / 5 + 32
        elif to_u == "k":
            return c + 273.15
        return None


class PasswordGeneratorSkill(BaseTool):
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="password",
            description="Generate secure passwords and check password strength.",
            category=ToolCategory.SECURITY,
            parameters=[
                ToolParameter("action", "string", "Action: generate or check", enum=["generate", "check"], required=True),
                ToolParameter("length", "integer", "Password length (default 20)"),
                ToolParameter("password", "string", "Password to check (for 'check' action)"),
                ToolParameter("include_symbols", "boolean", "Include special characters"),
                ToolParameter("exclude_ambiguous", "boolean", "Exclude ambiguous chars (0, O, l, 1)"),
            ],
            tags=["password", "security", "generate"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        action = arguments["action"]

        if action == "generate":
            length = arguments.get("length", 20)
            include_symbols = arguments.get("include_symbols", True)
            exclude_ambiguous = arguments.get("exclude_ambiguous", False)

            chars = string.ascii_letters + string.digits
            if include_symbols:
                chars += "!@#$%^&*()-_=+[]{}|;:,.<>?"
            if exclude_ambiguous:
                chars = chars.translate(str.maketrans("", "", "0OoIl1"))

            import secrets
            password = "".join(secrets.choice(chars) for _ in range(length))
            return json.dumps({"password": password, "length": length, "strength": self._check_strength(password)})

        elif action == "check":
            password = arguments.get("password", "")
            return json.dumps({"password": "***", "strength": self._check_strength(password)})

        return json.dumps({"error": f"Unknown action: {action}"})

    @staticmethod
    def _check_strength(password: str) -> dict[str, Any]:
        score = 0
        checks = {
            "length_8+": len(password) >= 8,
            "length_12+": len(password) >= 12,
            "uppercase": bool(re.search(r"[A-Z]", password)),
            "lowercase": bool(re.search(r"[a-z]", password)),
            "digits": bool(re.search(r"\d", password)),
            "symbols": bool(re.search(r"[!@#$%^&*()\-_=+\[\]{}|;:,.<>?]", password)),
            "no_repeats": not bool(re.search(r"(.)\1{2,}", password)),
        }
        score = sum(checks.values())
        levels = {0: "Very Weak", 1: "Weak", 2: "Fair", 3: "Good", 4: "Strong", 5: "Strong", 6: "Very Strong", 7: "Excellent"}
        return {"score": score, "max_score": 7, "level": levels.get(score, "Unknown"), "checks": checks}


class IPInfoSkill(BaseTool):
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="ip_info",
            description="Get IP address information: your public IP, IP geolocation, DNS lookup.",
            category=ToolCategory.NETWORK if hasattr(ToolCategory, 'NETWORK') else ToolCategory.UTILITY,
            parameters=[
                ToolParameter("action", "string", "Action: myip, lookup, dns", enum=["myip", "lookup", "dns"], required=True),
                ToolParameter("target", "string", "IP address or domain to look up"),
            ],
            tags=["ip", "network", "geolocation", "dns"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        action = arguments["action"]
        target = arguments.get("target", "")

        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                if action == "myip":
                    resp = await client.get("https://api.ipify.org?format=json")
                    return json.dumps(resp.json())

                elif action == "lookup":
                    if not target:
                        return json.dumps({"error": "target IP required"})
                    resp = await client.get(f"http://ip-api.com/json/{target}")
                    return json.dumps(resp.json())

                elif action == "dns":
                    if not target:
                        return json.dumps({"error": "target domain required"})
                    result = _run_cmd(f"dig +short {target} A && dig +short {target} AAAA")
                    return json.dumps({"domain": target, "records": result["stdout"].strip().split("\n")})

        except Exception as e:
            return json.dumps({"error": str(e)})
        return json.dumps({"error": f"Unknown action: {action}"})


class URLSkill(BaseTool):
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="url_op",
            description="URL operations: encode, decode, parse, build query string.",
            category=ToolCategory.UTILITY,
            parameters=[
                ToolParameter("action", "string", "Action: encode, decode, parse, build_query",
                    enum=["encode", "decode", "parse", "build_query"], required=True),
                ToolParameter("url", "string", "URL or string to process", required=True),
                ToolParameter("params", "object", "Query parameters (for build_query)"),
            ],
            tags=["url", "encode", "decode", "parse"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        from urllib.parse import quote, unquote, urlparse, urlencode

        action = arguments["action"]
        url = arguments["url"]

        if action == "encode":
            return json.dumps({"encoded": quote(url)})
        elif action == "decode":
            return json.dumps({"decoded": unquote(url)})
        elif action == "parse":
            parsed = urlparse(url)
            return json.dumps({
                "scheme": parsed.scheme, "host": parsed.netloc,
                "path": parsed.path, "query": parsed.query,
                "fragment": parsed.fragment, "port": parsed.port,
            })
        elif action == "build_query":
            params = arguments.get("params", {})
            base = url.split("?")[0]
            return json.dumps({"url": f"{base}?{urlencode(params)}"})

        return json.dumps({"error": f"Unknown action: {action}"})


class LoremGeneratorSkill(BaseTool):
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="lorem",
            description="Generate Lorem Ipsum placeholder text.",
            category=ToolCategory.UTILITY,
            parameters=[
                ToolParameter("count", "integer", "Number of items to generate"),
                ToolParameter("type", "string", "Type: words, sentences, paragraphs", enum=["words", "sentences", "paragraphs"]),
            ],
            tags=["lorem", "text", "placeholder", "generate"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        count = arguments.get("count", 1)
        text_type = arguments.get("type", "paragraphs")

        words = "lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod tempor incididunt ut labore et dolore magna aliqua enim ad minim veniam quis nostrud exercitation ullamco laboris nisi aliquip ex ea commodo consequat duis aute irure in reprehenderit voluptate velit esse cillum fugiat nulla pariatur excepteur sint occaecat cupidatat non proident sunt culpa qui officia deserunt mollit anim id est laborum".split()

        if text_type == "words":
            result = " ".join(random.choices(words, k=min(count, 500)))
        elif text_type == "sentences":
            sentences = []
            for _ in range(min(count, 50)):
                sentence = " ".join(random.choices(words, k=random.randint(8, 20)))
                sentences.append(sentence.capitalize() + ".")
            result = " ".join(sentences)
        else:  # paragraphs
            paragraphs = []
            for _ in range(min(count, 20)):
                sentences = []
                for _ in range(random.randint(3, 7)):
                    sentence = " ".join(random.choices(words, k=random.randint(8, 20)))
                    sentences.append(sentence.capitalize() + ".")
                paragraphs.append(" ".join(sentences))
            result = "\n\n".join(paragraphs)

        return json.dumps({"type": text_type, "count": count, "text": result})


class RandomSkill(BaseTool):
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="random",
            description="Generate random data: numbers, strings, choices, shuffle, sample.",
            category=ToolCategory.UTILITY,
            parameters=[
                ToolParameter("type", "string", "Type: number, string, choice, shuffle, sample, boolean, uuid",
                    enum=["number", "string", "choice", "shuffle", "sample", "boolean", "uuid"], required=True),
                ToolParameter("min", "integer", "Min value (for number)"),
                ToolParameter("max", "integer", "Max value (for number)"),
                ToolParameter("length", "integer", "Length (for string)"),
                ToolParameter("items", "array", "List of items (for choice/shuffle/sample)"),
                ToolParameter("count", "integer", "Count (for sample/uuid)"),
            ],
            tags=["random", "generate", "utility"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        rtype = arguments["type"]

        if rtype == "number":
            lo = arguments.get("min", 0)
            hi = arguments.get("max", 100)
            return json.dumps({"result": random.randint(lo, hi)})

        elif rtype == "string":
            length = arguments.get("length", 16)
            chars = string.ascii_letters + string.digits
            return json.dumps({"result": "".join(random.choices(chars, k=length))})

        elif rtype == "choice":
            items = arguments.get("items", [])
            return json.dumps({"result": random.choice(items) if items else None})

        elif rtype == "shuffle":
            items = arguments.get("items", [])
            shuffled = list(items)
            random.shuffle(shuffled)
            return json.dumps({"result": shuffled})

        elif rtype == "sample":
            items = arguments.get("items", [])
            count = min(arguments.get("count", 1), len(items))
            return json.dumps({"result": random.sample(items, count)})

        elif rtype == "boolean":
            return json.dumps({"result": random.choice([True, False])})

        elif rtype == "uuid":
            count = arguments.get("count", 1)
            return json.dumps({"result": [str(uuid.uuid4()) for _ in range(min(count, 100))]})

        return json.dumps({"error": f"Unknown type: {rtype}"})


class EncodingSkill(BaseTool):
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="encoding",
            description="Encode/decode data: base64, URL, HTML entities, hex, binary.",
            category=ToolCategory.UTILITY,
            parameters=[
                ToolParameter("action", "string", "Action: encode or decode", enum=["encode", "decode"], required=True),
                ToolParameter("format", "string", "Encoding format", enum=["base64", "url", "html", "hex", "binary"], required=True),
                ToolParameter("data", "string", "Data to encode/decode", required=True),
            ],
            tags=["encode", "decode", "base64", "url", "hex"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        action = arguments["action"]
        fmt = arguments["format"]
        data = arguments["data"]

        try:
            if fmt == "base64":
                if action == "encode":
                    return json.dumps({"result": base64.b64encode(data.encode()).decode()})
                else:
                    return json.dumps({"result": base64.b64decode(data.encode()).decode()})

            elif fmt == "url":
                from urllib.parse import quote, unquote
                if action == "encode":
                    return json.dumps({"result": quote(data)})
                else:
                    return json.dumps({"result": unquote(data)})

            elif fmt == "html":
                import html
                if action == "encode":
                    return json.dumps({"result": html.escape(data)})
                else:
                    return json.dumps({"result": html.unescape(data)})

            elif fmt == "hex":
                if action == "encode":
                    return json.dumps({"result": data.encode().hex()})
                else:
                    return json.dumps({"result": bytes.fromhex(data).decode()})

            elif fmt == "binary":
                if action == "encode":
                    return json.dumps({"result": " ".join(format(b, "08b") for b in data.encode())})
                else:
                    bytes_data = bytes(int(b, 2) for b in data.split())
                    return json.dumps({"result": bytes_data.decode()})

        except Exception as e:
            return json.dumps({"error": str(e)})
        return json.dumps({"error": f"Unknown format: {fmt}"})


class CronSkill(BaseTool):
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="cron",
            description="Manage scheduled tasks: list, add, remove cron jobs.",
            category=ToolCategory.AUTOMATION,
            parameters=[
                ToolParameter("action", "string", "Action: list, add, remove", enum=["list", "add", "remove"], required=True),
                ToolParameter("schedule", "string", "Cron schedule expression (for add)"),
                ToolParameter("command", "string", "Command to run (for add)"),
                ToolParameter("job_id", "string", "Job identifier (for remove)"),
            ],
            permission=PermissionLevel.AUTHENTICATED,
            tags=["cron", "schedule", "automation"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        action = arguments["action"]

        if action == "list":
            result = _run_cmd("crontab -l 2>/dev/null")
            return json.dumps({"jobs": result["stdout"].strip() or "No cron jobs"})

        elif action == "add":
            schedule = arguments.get("schedule", "")
            command = arguments.get("command", "")
            if not schedule or not command:
                return json.dumps({"error": "schedule and command required"})
            # Validate cron expression (5 fields)
            fields = schedule.split()
            if len(fields) != 5:
                return json.dumps({"error": "Schedule must have 5 fields: minute hour day month weekday"})
            entry = f"{schedule} {command}"
            result = _run_cmd(f'(crontab -l 2>/dev/null; echo "{entry}") | crontab -')
            return json.dumps({"success": True, "entry": entry})

        elif action == "remove":
            job_id = arguments.get("job_id", "")
            if not job_id:
                return json.dumps({"error": "job_id required"})
            result = _run_cmd(f"crontab -l 2>/dev/null | grep -v '{job_id}' | crontab -")
            return json.dumps({"success": True, "removed": job_id})

        return json.dumps({"error": f"Unknown action: {action}"})


class MarkdownSkill(BaseTool):
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="markdown",
            description="Markdown operations: generate TOC, validate, convert to HTML, extract headings.",
            category=ToolCategory.UTILITY,
            parameters=[
                ToolParameter("action", "string", "Action: toc, validate, to_html, headings",
                    enum=["toc", "validate", "to_html", "headings"], required=True),
                ToolParameter("content", "string", "Markdown content", required=True),
            ],
            tags=["markdown", "text", "format"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        action = arguments["action"]
        content = arguments["content"]

        if action == "toc":
            toc = []
            for line in content.split("\n"):
                if line.startswith("#"):
                    level = len(line) - len(line.lstrip("#"))
                    title = line.lstrip("#").strip()
                    indent = "  " * (level - 1)
                    anchor = re.sub(r"[^\w\s-]", "", title.lower()).replace(" ", "-")
                    toc.append(f"{indent}- [{title}](#{anchor})")
            return json.dumps({"toc": "\n".join(toc) or "No headings found"})

        elif action == "validate":
            issues = []
            if content.count("**") % 2 != 0:
                issues.append("Unclosed bold markers (**)")
            if content.count("*") % 2 != 0:
                issues.append("Possible unclosed italic markers (*)")
            code_blocks = content.count("```")
            if code_blocks % 2 != 0:
                issues.append("Unclosed code block (```)")
            return json.dumps({"valid": len(issues) == 0, "issues": issues})

        elif action == "to_html":
            try:
                import markdown
                html_content = markdown.markdown(content, extensions=["tables", "fenced_code"])
                return json.dumps({"html": html_content})
            except ImportError:
                return json.dumps({"error": "markdown library not installed"})

        elif action == "headings":
            headings = []
            for line in content.split("\n"):
                if line.startswith("#"):
                    level = len(line) - len(line.lstrip("#"))
                    headings.append({"level": level, "text": line.lstrip("#").strip()})
            return json.dumps({"headings": headings})

        return json.dumps({"error": f"Unknown action: {action}"})


class YAMLSkill(BaseTool):
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="yaml_op",
            description="YAML operations: parse, validate, convert to JSON.",
            category=ToolCategory.DATA,
            parameters=[
                ToolParameter("action", "string", "Action: parse, validate, to_json", enum=["parse", "validate", "to_json"], required=True),
                ToolParameter("data", "string", "YAML data", required=True),
            ],
            tags=["yaml", "parse", "data"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        action = arguments["action"]
        data = arguments["data"]

        try:
            import yaml
            if action in ("parse", "to_json"):
                parsed = yaml.safe_load(data)
                return json.dumps({"result": parsed}, default=str)
            elif action == "validate":
                yaml.safe_load(data)
                return json.dumps({"valid": True})
        except Exception as e:
            return json.dumps({"valid": False, "error": str(e)})
        return json.dumps({"error": f"Unknown action: {action}"})


class TOMLSkill(BaseTool):
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="toml_op",
            description="TOML operations: parse, validate, convert to JSON.",
            category=ToolCategory.DATA,
            parameters=[
                ToolParameter("action", "string", "Action: parse, validate, to_json", enum=["parse", "validate", "to_json"], required=True),
                ToolParameter("data", "string", "TOML data", required=True),
            ],
            tags=["toml", "parse", "data"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        action = arguments["action"]
        data = arguments["data"]

        try:
            try:
                import tomllib
            except ImportError:
                import tomli as tomllib

            if action in ("parse", "to_json"):
                parsed = tomllib.loads(data)
                return json.dumps({"result": parsed}, default=str)
            elif action == "validate":
                tomllib.loads(data)
                return json.dumps({"valid": True})
        except Exception as e:
            return json.dumps({"valid": False, "error": str(e)})
        return json.dumps({"error": f"Unknown action: {action}"})


# ═══════════════════════════════════════════════════════════════
# SKILL REGISTRATION
# ═══════════════════════════════════════════════════════════════

def register_all_skills(registry: ToolRegistry) -> int:
    """Register all built-in skills into the tool registry. Returns count of skills registered."""
    skills = [
        # System
        SystemInfoSkill(),
        GitSkill(),
        DockerSkill(),
        KubernetesSkill(),
        PackageManagerSkill(),
        # Database
        SQLiteSkill(),
        PostgresSkill(),
        RedisSkill(),
        # Files
        FileCompressionSkill(),
        # Media
        ImageProcessingSkill(),
        PDFSkill(),
        # Data
        DataAnalysisSkill(),
        JSONPathSkill(),
        # Utility
        UnitConverterSkill(),
        PasswordGeneratorSkill(),
        IPInfoSkill(),
        URLSkill(),
        LoremGeneratorSkill(),
        RandomSkill(),
        EncodingSkill(),
        CronSkill(),
        MarkdownSkill(),
        YAMLSkill(),
        TOMLSkill(),
    ]

    for skill in skills:
        registry.register(skill)

    return len(skills)
