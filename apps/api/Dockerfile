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
# torch CPU-only wheel'i resmi PyTorch index'inden çekilir (~250 MB GPU
# wheel'lerinden kaçınmak için). sentence-transformers transitive olarak
# torch'a bağımlı; pip --extra-index-url ile çakışma çözülür (PyPI primary,
# PyTorch index fallback).
# PR-8 #223 (MVP-1.5): Local bge-m3 primary, NIM embedding fallback.
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install \
        --extra-index-url https://download.pytorch.org/whl/cpu \
        -e .

# bge-m3 (~2.3 GB) + bge-reranker-v2-m3 (~568 MB) build-time HF cache.
# Runtime'da SentenceTransformer / CrossEncoder otomatik /opt/hf-cache'i okur.
# İlk container start = anında ready (lazy load saniye cinsinden).
ENV HF_HOME=/opt/hf-cache
RUN mkdir -p /opt/hf-cache \
    && /opt/venv/bin/python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-m3', cache_folder='/opt/hf-cache')" \
    && /opt/venv/bin/python -c "from sentence_transformers import CrossEncoder; CrossEncoder('BAAI/bge-reranker-v2-m3', cache_dir='/opt/hf-cache')"

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

# Copy preloaded HF cache (bge-m3 ~2.3 GB) — image'da hazır, runtime download yok.
# docker-compose.yml shared volume override edebilir (yeniden indirim olmaz çünkü
# volume cache aynı path'i bind eder, model dosyaları zaten orada).
COPY --from=builder --chown=nodrat:nodrat /opt/hf-cache /opt/hf-cache

# Copy app code
WORKDIR /app
COPY --chown=nodrat:nodrat . .

ENV HF_HOME=/opt/hf-cache

USER nodrat

# Expose internal port (compose maps externally)
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# Default: API server. Worker'lar override eder (compose command).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
