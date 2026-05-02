# =============================================================================
# Nodrat API + Worker Dockerfile
# Python 3.12 slim base, multi-stage build
# =============================================================================

# ---- Builder stage ----------------------------------------------------------
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# System deps: lxml needs libxml2, asyncpg needs libpq-dev for compile
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libxml2-dev \
        libxslt-dev \
        libpq-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Copy pyproject.toml first for cache efficiency
COPY pyproject.toml ./

# Install deps to a venv.
# Note: sentence-transformers + torch (#163) VPS disk yetersizliği nedeniyle
# devre dışı. USE_LOCAL_EMBEDDING=false → NIM bge-m3 (geçici) kullanılır.
# VPS upgrade sonrası pyproject.toml'a torch eklenir + bu RUN'a aşağıdaki
# satır geri eklenir:
#   && /opt/venv/bin/pip install --index-url https://download.pytorch.org/whl/cpu \
#       torch>=2.5.0 \
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install -e .

# ---- Runtime stage ----------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# Runtime deps (lxml runtime + tesseract for Faz 4 OCR — şimdi opt'l)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libxml2 \
        libxslt1.1 \
        libpq5 \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Non-root user
RUN groupadd -r nodrat --gid 1000 \
    && useradd -r -u 1000 -g nodrat -s /sbin/nologin nodrat

# Copy venv from builder
COPY --from=builder --chown=nodrat:nodrat /opt/venv /opt/venv

# Copy app code
WORKDIR /app
COPY --chown=nodrat:nodrat . .

# bge-m3 model cache path — runtime download to volume (#163)
# docker-compose.yml: 'hf_cache:/opt/hf-cache' shared volume
ENV HF_HOME=/opt/hf-cache
RUN mkdir -p /opt/hf-cache && chown -R nodrat:nodrat /opt/hf-cache

USER nodrat

# Expose internal port (compose maps externally)
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# Default: API server. Worker'lar override eder (compose command).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
