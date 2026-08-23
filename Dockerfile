# syntax=docker/dockerfile:1
# Multi-stage production Dockerfile for APKPipe

# =========================================================================
# Stage 1: Build React/TypeScript Frontend
# =========================================================================
FROM node:20-slim AS frontend-builder

WORKDIR /build/frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# =========================================================================
# Stage 2: Build Dependencies
# =========================================================================
FROM python:3.12-slim AS python-builder

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build

# Install build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python requirements and build wheel
COPY pyproject.toml requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
RUN pip install --no-cache-dir --no-deps .

# =========================================================================
# Stage 3: Runtime Container
# =========================================================================
FROM python:3.12-slim AS runner

LABEL org.opencontainers.image.title="APKPipe" \
      org.opencontainers.image.description="Automated APK & RSS media pipeline with Real-Debrid, JDownloader fallback, Nextcloud ingestion, Web UI, and MCP server." \
      org.opencontainers.image.authors="Steve Pelech" \
      org.opencontainers.image.source="https://github.com/spelech/apkpipe" \
      org.opencontainers.image.licenses="MIT"

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH="/app/src" \
    APKPIPE_DOWNLOAD_DIR="/downloads" \
    APKPIPE_STAGING_DIR="/data/staging" \
    APKPIPE_DATABASE_URL="sqlite+aiosqlite:////data/apkpipe.db" \
    APKPIPE_HOST="0.0.0.0" \
    APKPIPE_PORT="8000"

# Install runtime dependencies (archive unpackers, curl for healthchecks, init process)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    p7zip-full \
    unrar-free \
    tini \
    && rm -rf /var/lib/apt/lists/*

# Create unprivileged service user and group
RUN groupadd -g 1000 apkpipe && \
    useradd -u 1000 -g apkpipe -d /data -s /bin/sh apkpipe

# Copy Python virtual environment and installed app from builder
COPY --from=python-builder /opt/venv /opt/venv

# Set up working directory structure
WORKDIR /app
COPY --chown=apkpipe:apkpipe src/ /app/src/
COPY --chown=apkpipe:apkpipe --from=frontend-builder /build/frontend/dist /app/frontend/dist
COPY --chown=apkpipe:apkpipe pyproject.toml README.md /app/

# Create application data, staging, and downloads directories with permissions
RUN mkdir -p /data /data/staging /downloads && \
    chown -R apkpipe:apkpipe /data /downloads /app

# Switch to unprivileged user
USER apkpipe

# Expose web service port
EXPOSE 8000

# Health check probe
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Process init and startup command
ENTRYPOINT ["tini", "--"]
CMD ["uvicorn", "apkpipe.main:app", "--host", "0.0.0.0", "--port", "8000"]
