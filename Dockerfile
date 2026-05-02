# ═══════════════════════════════════════════════════════════════════════════════
# 🟣 RALLY AGENT — Dockerfile
#
# Multi-stage build for minimal image size.
#
# Build:   docker build -t rally-agent .
# Run:     docker run -it --rm -p 8778:8778 -v rally-data:/data rally-agent
# Compose: docker-compose up
# ═══════════════════════════════════════════════════════════════════════════════

# ── Stage 1: Builder ─────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install system deps needed for building wheels
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        git \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files first (cache layer)
COPY requirements.txt pyproject.toml setup.py ./

# Install Python deps into a virtual environment
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir --upgrade pip setuptools wheel && \
    /opt/venv/bin/pip install --no-cache-dir -r requirements.txt && \
    /opt/venv/bin/pip install --no-cache-dir -e ".[all]"

# Install Playwright browser (Chromium only)
RUN /opt/venv/bin/playwright install chromium --with-deps || \
    /opt/venv/bin/python -m playwright install chromium

# ── Stage 2: Runtime ─────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

LABEL maintainer="Rally Labs <hello@rally-agent.dev>"
LABEL org.opencontainers.image.title="Rally Agent"
LABEL org.opencontainers.image.description="The OpenClaw Killer — Your AI. Your Rules. Your Data."
LABEL org.opencontainers.image.url="https://github.com/Atum246/rally-agent"
LABEL org.opencontainers.image.source="https://github.com/Atum246/rally-agent"
LABEL org.opencontainers.image.version="1.0.0"
LABEL org.opencontainers.image.licenses="MIT"

# Install minimal runtime dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        git \
        ca-certificates \
        fonts-liberation \
        libasound2 \
        libatk-bridge2.0-0 \
        libatk1.0-0 \
        libcups2 \
        libdbus-1-3 \
        libdrm2 \
        libgbm1 \
        libgtk-3-0 \
        libnspr4 \
        libnss3 \
        libxcomposite1 \
        libxdamage1 \
        libxfixes3 \
        libxkbcommon0 \
        libxrandr2 \
        xdg-utils \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Copy application code
WORKDIR /app
COPY . .

# Make sure the venv is in PATH
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Rally-specific env
ENV RALLY_HOME="/app"
ENV RALLY_DATA="/data"

# Create data directories for volume mount
RUN mkdir -p /data/config /data/memory /data/logs /data/skills /data/plugins

# Create non-root user
RUN groupadd --gid 1000 rally && \
    useradd --uid 1000 --gid rally --shell /bin/bash --create-home rally && \
    chown -R rally:rally /app /data

USER rally

# Expose web UI port
EXPOSE 8778

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8778/health || exit 1

# Default command
ENTRYPOINT ["python", "rally.py"]
CMD ["serve", "8778"]
