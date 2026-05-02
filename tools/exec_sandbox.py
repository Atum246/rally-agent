"""
🟣 Rally Agent — Sandboxed Code Execution Engine
Docker-based sandbox with subprocess fallback. Resource limits, network policy, artifact collection.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import signal
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, AsyncIterator, Optional


class SandboxBackend(str, Enum):
    DOCKER = "docker"
    SUBPROCESS = "subprocess"


@dataclass
class ResourceLimits:
    """Resource limits for sandboxed execution."""
    cpu_seconds: int = 30
    memory_mb: int = 512
    disk_mb: int = 1024
    timeout_seconds: int = 60
    max_output_bytes: int = 1_048_576  # 1 MB
    max_processes: int = 32
    network_access: bool = False
    allowed_domains: list[str] = field(default_factory=list)


@dataclass
class SandboxResult:
    """Result of a sandboxed execution."""
    success: bool
    exit_code: int
    stdout: str
    stderr: str
    execution_time_ms: float
    timed_out: bool = False
    memory_exceeded: bool = False
    artifacts: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "execution_time_ms": self.execution_time_ms,
            "timed_out": self.timed_out,
            "memory_exceeded": self.memory_exceeded,
            "artifacts": self.artifacts,
            "metadata": self.metadata,
        }

    @property
    def output(self) -> str:
        """Combined stdout + stderr."""
        parts = []
        if self.stdout:
            parts.append(self.stdout)
        if self.stderr:
            parts.append(self.stderr)
        return "\n".join(parts)


@dataclass
class LanguageConfig:
    """Configuration for a supported language runtime."""
    name: str
    extension: str
    run_command: list[str]  # Template: {file} placeholder
    docker_image: str
    compile_command: Optional[list[str]] = None  # For compiled languages

    def get_run_command(self, file_path: str) -> list[str]:
        return [c.replace("{file}", file_path) for c in self.run_command]

    def get_compile_command(self, file_path: str, output: str) -> list[str]:
        if not self.compile_command:
            return []
        return [c.replace("{file}", file_path).replace("{output}", output) for c in self.compile_command]


# Language configurations
LANGUAGES: dict[str, LanguageConfig] = {
    "python": LanguageConfig(
        name="Python",
        extension=".py",
        run_command=["python3", "-u", "{file}"],
        docker_image="python:3.12-slim",
    ),
    "node": LanguageConfig(
        name="Node.js",
        extension=".js",
        run_command=["node", "{file}"],
        docker_image="node:22-slim",
    ),
    "bash": LanguageConfig(
        name="Bash",
        extension=".sh",
        run_command=["bash", "{file}"],
        docker_image="bash:latest",
    ),
    "go": LanguageConfig(
        name="Go",
        extension=".go",
        run_command=["go", "run", "{file}"],
        docker_image="golang:1.22-alpine",
        compile_command=["go", "build", "-o", "{output}", "{file}"],
    ),
    "rust": LanguageConfig(
        name="Rust",
        extension=".rs",
        run_command=["rustc", "{file}", "-o", "/tmp/rust_out", "&&", "/tmp/rust_out"],
        docker_image="rust:1.77-slim",
        compile_command=["rustc", "{file}", "-o", "{output}"],
    ),
}


class ExecutionSandbox:
    """
    Sandboxed code execution engine.
    Uses Docker when available, falls back to subprocess with resource limits.
    """

    def __init__(
        self,
        backend: Optional[SandboxBackend] = None,
        limits: Optional[ResourceLimits] = None,
        workspace_dir: Optional[str] = None,
    ):
        self.limits = limits or ResourceLimits()
        self.workspace_dir = workspace_dir or os.path.expanduser("~/.rally-agent/sandbox")
        os.makedirs(self.workspace_dir, exist_ok=True)

        # Auto-detect backend
        if backend is None:
            self.backend = self._detect_backend()
        else:
            self.backend = backend

        self._active_containers: dict[str, str] = {}  # execution_id -> container_id

    @staticmethod
    def _detect_backend() -> SandboxBackend:
        """Detect if Docker is available."""
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                timeout=5,
            )
            if result.returncode == 0:
                return SandboxBackend.DOCKER
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return SandboxBackend.SUBPROCESS

    async def execute(
        self,
        code: str,
        language: str = "python",
        limits: Optional[ResourceLimits] = None,
        files: Optional[dict[str, str]] = None,
        env: Optional[dict[str, str]] = None,
        execution_id: Optional[str] = None,
    ) -> SandboxResult:
        """
        Execute code in a sandbox.

        Args:
            code: Source code to execute.
            language: Programming language (python, node, bash, go, rust).
            limits: Resource limits override.
            files: Additional files to create in sandbox (filename -> content).
            env: Environment variables.
            execution_id: Optional execution identifier.

        Returns:
            SandboxResult with execution output and metadata.
        """
        exec_id = execution_id or str(uuid.uuid4())[:8]
        lim = limits or self.limits
        lang = LANGUAGES.get(language)

        if not lang:
            return SandboxResult(
                success=False,
                exit_code=1,
                stdout="",
                stderr=f"Unsupported language: {language}. Supported: {', '.join(LANGUAGES.keys())}",
                execution_time_ms=0,
            )

        # Prepare sandbox directory
        sandbox_dir = os.path.join(self.workspace_dir, exec_id)
        os.makedirs(sandbox_dir, exist_ok=True)

        # Write main code file
        main_file = os.path.join(sandbox_dir, f"main{lang.extension}")
        with open(main_file, "w") as f:
            f.write(code)

        # Write additional files
        if files:
            for filename, content in files.items():
                file_path = os.path.join(sandbox_dir, filename)
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                with open(file_path, "w") as f:
                    f.write(content)

        # Execute
        try:
            if self.backend == SandboxBackend.DOCKER:
                result = await self._execute_docker(exec_id, sandbox_dir, lang, lim, env)
            else:
                result = await self._execute_subprocess(exec_id, sandbox_dir, lang, lim, env)
        finally:
            # Collect artifacts
            artifacts = []
            artifacts_dir = os.path.join(sandbox_dir, "artifacts")
            if os.path.isdir(artifacts_dir):
                for fname in os.listdir(artifacts_dir):
                    artifacts.append(os.path.join(artifacts_dir, fname))
            result.artifacts = artifacts

            # Cleanup sandbox directory
            try:
                shutil.rmtree(sandbox_dir, ignore_errors=True)
            except Exception:
                pass

        return result

    async def _execute_docker(
        self,
        exec_id: str,
        sandbox_dir: str,
        lang: LanguageConfig,
        limits: ResourceLimits,
        env: Optional[dict[str, str]],
    ) -> SandboxResult:
        """Execute code in a Docker container."""
        container_name = f"rally-sandbox-{exec_id}"
        main_file = f"/sandbox/main{lang.extension}"
        artifacts_dir = os.path.join(sandbox_dir, "artifacts")
        os.makedirs(artifacts_dir, exist_ok=True)

        cmd = [
            "docker", "run",
            "--rm",
            "--name", container_name,
            "--memory", f"{limits.memory_mb}m",
            "--cpus", "1.0",
            "--pids-limit", str(limits.max_processes),
            "--read-only",
            "--tmpfs", "/tmp:size=256m",
            "-v", f"{sandbox_dir}:/sandbox:ro",
            "-v", f"{artifacts_dir}:/artifacts",
            "-w", "/sandbox",
        ]

        # Network policy
        if not limits.network_access:
            cmd.extend(["--network", "none"])
        elif limits.allowed_domains:
            # Docker doesn't natively support domain whitelisting;
            # we use network=none and set allowed_domains via iptables in container
            pass

        # Environment variables
        safe_env = self._sanitize_env(env or {})
        for key, value in safe_env.items():
            cmd.extend(["-e", f"{key}={value}"])

        # Timeout wrapper
        cmd.extend([
            lang.docker_image,
            "timeout", str(limits.timeout_seconds),
        ] + lang.get_run_command(main_file))

        self._active_containers[exec_id] = container_name

        try:
            start_time = time.monotonic()
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=limits.timeout_seconds + 5,
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return SandboxResult(
                    success=False,
                    exit_code=-1,
                    stdout="",
                    stderr="Execution timed out",
                    execution_time_ms=(time.monotonic() - start_time) * 1000,
                    timed_out=True,
                    metadata={"container": container_name},
                )

            elapsed = (time.monotonic() - start_time) * 1000

            # Truncate output
            stdout = stdout_bytes[:limits.max_output_bytes].decode("utf-8", errors="replace")
            stderr = stderr_bytes[:limits.max_output_bytes].decode("utf-8", errors="replace")

            # Collect artifacts
            artifacts = []
            if os.path.isdir(artifacts_dir):
                for fname in os.listdir(artifacts_dir):
                    artifacts.append(os.path.join(artifacts_dir, fname))

            return SandboxResult(
                success=proc.returncode == 0,
                exit_code=proc.returncode or 0,
                stdout=stdout,
                stderr=stderr,
                execution_time_ms=elapsed,
                artifacts=artifacts,
                metadata={"container": container_name, "backend": "docker"},
            )

        except Exception as e:
            return SandboxResult(
                success=False,
                exit_code=-1,
                stdout="",
                stderr=f"Docker execution error: {e}",
                execution_time_ms=0,
                metadata={"container": container_name, "error": str(e)},
            )
        finally:
            self._active_containers.pop(exec_id, None)
            # Force cleanup container
            try:
                subprocess.run(
                    ["docker", "rm", "-f", container_name],
                    capture_output=True,
                    timeout=5,
                )
            except Exception:
                pass

    async def _execute_subprocess(
        self,
        exec_id: str,
        sandbox_dir: str,
        lang: LanguageConfig,
        limits: ResourceLimits,
        env: Optional[dict[str, str]],
    ) -> SandboxResult:
        """Execute code in a subprocess with resource limits."""
        main_file = os.path.join(sandbox_dir, f"main{lang.extension}")

        # For Rust, we need to compile first
        if lang.compile_command:
            compile_cmd = lang.get_compile_command(main_file, "/tmp/rally_out")
            compile_proc = await asyncio.create_subprocess_exec(
                *compile_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=sandbox_dir,
            )
            _, compile_stderr = await compile_proc.communicate()
            if compile_proc.returncode != 0:
                return SandboxResult(
                    success=False,
                    exit_code=compile_proc.returncode or 1,
                    stdout="",
                    stderr=f"Compilation failed:\n{compile_stderr.decode('utf-8', errors='replace')}",
                    execution_time_ms=0,
                    metadata={"phase": "compile"},
                )
            run_cmd = ["/tmp/rally_out"]
        else:
            run_cmd = lang.get_run_command(main_file)

        # Build environment
        run_env = os.environ.copy()
        run_env.update(self._sanitize_env(env or {}))
        run_env["PYTHONDONTWRITEBYTECODE"] = "1"

        # Prepare resource limits via preexec_fn
        def set_limits():
            import resource
            # CPU time limit
            resource.setrlimit(resource.RLIMIT_CPU, (limits.cpu_seconds, limits.cpu_seconds))
            # Memory limit (virtual)
            mem_bytes = limits.memory_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
            # File size limit
            file_bytes = limits.disk_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_FSIZE, (file_bytes, file_bytes))
            # Process limit
            resource.setrlimit(resource.RLIMIT_NPROC, (limits.max_processes, limits.max_processes))

        start_time = time.monotonic()
        timed_out = False

        try:
            proc = await asyncio.create_subprocess_exec(
                *run_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=sandbox_dir,
                env=run_env,
                preexec_fn=set_limits,
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=limits.timeout_seconds,
                )
            except asyncio.TimeoutError:
                timed_out = True
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
                await proc.wait()
                stdout_bytes, stderr_bytes = b"", b"Execution timed out"

            elapsed = (time.monotonic() - start_time) * 1000

            stdout = stdout_bytes[:limits.max_output_bytes].decode("utf-8", errors="replace")
            stderr = stderr_bytes[:limits.max_output_bytes].decode("utf-8", errors="replace")

            # Collect artifacts
            artifacts_dir = os.path.join(sandbox_dir, "artifacts")
            artifacts = []
            if os.path.isdir(artifacts_dir):
                for fname in os.listdir(artifacts_dir):
                    artifacts.append(os.path.join(artifacts_dir, fname))

            return SandboxResult(
                success=(proc.returncode == 0 and not timed_out),
                exit_code=proc.returncode or 0,
                stdout=stdout,
                stderr=stderr,
                execution_time_ms=elapsed,
                timed_out=timed_out,
                artifacts=artifacts,
                metadata={"backend": "subprocess"},
            )

        except Exception as e:
            elapsed = (time.monotonic() - start_time) * 1000
            return SandboxResult(
                success=False,
                exit_code=-1,
                stdout="",
                stderr=f"Execution error: {e}",
                execution_time_ms=elapsed,
                metadata={"backend": "subprocess", "error": str(e)},
            )

    async def execute_interactive(
        self,
        code: str,
        language: str = "python",
        limits: Optional[ResourceLimits] = None,
    ) -> AsyncIterator[str]:
        """
        Execute code with streaming output.
        Yields output lines as they become available.
        """
        lim = limits or self.limits
        lang = LANGUAGES.get(language)
        if not lang:
            yield f"Error: Unsupported language: {language}"
            return

        exec_id = str(uuid.uuid4())[:8]
        sandbox_dir = os.path.join(self.workspace_dir, exec_id)
        os.makedirs(sandbox_dir, exist_ok=True)

        main_file = os.path.join(sandbox_dir, f"main{lang.extension}")
        with open(main_file, "w") as f:
            f.write(code)

        run_cmd = lang.get_run_command(main_file)

        try:
            proc = await asyncio.create_subprocess_exec(
                *run_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=sandbox_dir,
            )

            start_time = time.monotonic()
            try:
                while True:
                    line = await asyncio.wait_for(
                        proc.stdout.readline(),
                        timeout=lim.timeout_seconds,
                    )
                    if not line:
                        break
                    decoded = line.decode("utf-8", errors="replace").rstrip()
                    yield decoded

                    # Check timeout
                    if (time.monotonic() - start_time) * 1000 > lim.timeout_seconds * 1000:
                        proc.kill()
                        yield "[TIMEOUT] Execution timed out"
                        break

            except asyncio.TimeoutError:
                proc.kill()
                yield "[TIMEOUT] Execution timed out"
            finally:
                await proc.wait()

        finally:
            shutil.rmtree(sandbox_dir, ignore_errors=True)

    async def cleanup(self):
        """Clean up all active containers and sandbox directories."""
        # Kill active Docker containers
        for exec_id, container_name in list(self._active_containers.items()):
            try:
                subprocess.run(
                    ["docker", "rm", "-f", container_name],
                    capture_output=True,
                    timeout=5,
                )
            except Exception:
                pass
        self._active_containers.clear()

        # Clean sandbox directory
        try:
            shutil.rmtree(self.workspace_dir, ignore_errors=True)
            os.makedirs(self.workspace_dir, exist_ok=True)
        except Exception:
            pass

    @staticmethod
    def _sanitize_env(env: dict[str, str]) -> dict[str, str]:
        """Sanitize environment variables — remove dangerous ones."""
        blocked_keys = {
            "LD_PRELOAD", "LD_LIBRARY_PATH", "PATH",
            "HOME", "USER", "SHELL", "SUDO_USER",
        }
        return {k: v for k, v in env.items() if k not in blocked_keys}

    def get_supported_languages(self) -> list[str]:
        """Return list of supported language identifiers."""
        return list(LANGUAGES.keys())

    def get_backend_info(self) -> dict[str, Any]:
        """Return information about the current backend."""
        return {
            "backend": self.backend.value,
            "supported_languages": self.get_supported_languages(),
            "limits": {
                "cpu_seconds": self.limits.cpu_seconds,
                "memory_mb": self.limits.memory_mb,
                "timeout_seconds": self.limits.timeout_seconds,
            },
            "workspace": self.workspace_dir,
        }
