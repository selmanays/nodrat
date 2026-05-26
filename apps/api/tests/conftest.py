"""Pytest fixtures — unit + integration test infrastructure.

Tier'lar:
    unit         : fast, no external deps. Default — tüm testler bu fixture'lara erişebilir.
    integration  : testcontainers (postgres + redis + minio).
                   pytest -m integration ile çalışır; CI'da setup yavaştır.
    eval         : LLM provider çağrısı içerir, $$ maliyetli. Manuel tetik (pytest -m eval).

Fixture'lar:
    pg_container       — function-scope, postgres+pgvector image
    redis_container    — function-scope, Redis 7
    minio_container    — function-scope, MinIO testcontainer
    test_db_engine     — pg_container'a bağlı async engine, alembic upgrade head çalıştırılır
    test_db_session    — Per-test rollback semantiği

Not: docker daemon yoksa integration testleri otomatik skip edilir.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import socket
from collections.abc import AsyncIterator, Iterator

import pytest


def _docker_available() -> bool:
    """Docker daemon erişilebilir mi? (testcontainers gerektirir)"""
    if not shutil.which("docker"):
        return False
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(0.5)
        try:
            sock.connect("/var/run/docker.sock")
            sock.close()
            return True
        except (FileNotFoundError, OSError):
            sock.close()
            return False
    except OSError:
        return False


# Marker: integration test'ler docker yoksa skip
DOCKER_AVAILABLE = _docker_available()
SKIP_NO_DOCKER = pytest.mark.skipif(
    not DOCKER_AVAILABLE,
    reason="Docker daemon erişilemiyor — testcontainer fixture'ları atlanıyor",
)


# ============================================================================
# Event loop policy (pytest-asyncio uyumu)
# ============================================================================


@pytest.fixture(scope="session")
def event_loop_policy():  # type: ignore[no-untyped-def]
    """Session-scoped event loop policy — testcontainers + asyncio uyumu."""
    return asyncio.DefaultEventLoopPolicy()


# ============================================================================
# Postgres + pgvector container
# ============================================================================


@pytest.fixture(scope="session")
def pg_container() -> Iterator[object]:
    """Postgres + pgvector container (testcontainers).

    Image: pgvector/pgvector:pg16 (production'la birebir).
    """
    if not DOCKER_AVAILABLE:
        pytest.skip("docker yok")

    from testcontainers.postgres import PostgresContainer

    container = (
        PostgresContainer("pgvector/pgvector:pg16")
        .with_env("POSTGRES_DB", "nodrat_test")
        .with_env("POSTGRES_USER", "nodrat")
        .with_env("POSTGRES_PASSWORD", "test_pass")
    )
    container.start()
    try:
        yield container
    finally:
        container.stop()


@pytest.fixture(scope="session")
def pg_url(pg_container) -> str:  # type: ignore[no-untyped-def]
    """Async Postgres DSN — testcontainer up'a göre oluşur."""
    raw = pg_container.get_connection_url()
    # testcontainers bazen psycopg+postgres döner — asyncpg'e çevir
    return raw.replace("postgresql+psycopg2://", "postgresql+asyncpg://").replace(
        "postgresql://", "postgresql+asyncpg://"
    )


# ============================================================================
# Redis container
# ============================================================================


@pytest.fixture(scope="session")
def redis_container() -> Iterator[object]:
    if not DOCKER_AVAILABLE:
        pytest.skip("docker yok")

    from testcontainers.redis import RedisContainer

    container = RedisContainer("redis:7-alpine")
    container.start()
    try:
        yield container
    finally:
        container.stop()


@pytest.fixture(scope="session")
def redis_url(redis_container) -> str:  # type: ignore[no-untyped-def]
    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(6379)
    return f"redis://{host}:{port}/0"


# ============================================================================
# MinIO container
# ============================================================================


@pytest.fixture(scope="session")
def minio_container() -> Iterator[object]:
    if not DOCKER_AVAILABLE:
        pytest.skip("docker yok")

    from testcontainers.minio import MinioContainer

    container = MinioContainer(
        access_key="minio_test",
        secret_key="minio_test_pass",
    )
    container.start()
    try:
        yield container
    finally:
        container.stop()


@pytest.fixture()
def minio_endpoint(minio_container) -> str:  # type: ignore[no-untyped-def]
    host = minio_container.get_container_host_ip()
    port = minio_container.get_exposed_port(9000)
    return f"{host}:{port}"


# ============================================================================
# DB session helpers — async engine + per-test rollback
# ============================================================================


@pytest.fixture(scope="session")
async def test_db_engine(pg_url: str) -> AsyncIterator[object]:
    """Async engine + alembic upgrade head (subprocess-based).

    Schema migration tüm testler için bir kez çalışır (session scope).

    **#1292 fix — subprocess yaklaşımı:**
    Önceki implementasyon `command.upgrade(alembic_cfg, "head")` sync API'sini
    pytest-asyncio'nun çalışan event loop'u içinden çağırıyordu. `command.upgrade`
    → `alembic/env.py:run_migrations_online()` → `asyncio.run(run_async_migrations())`
    nested-loop hatası fırlatıyordu:
    `RuntimeError: asyncio.run() cannot be called from a running event loop`.

    Bu fixture'ı kullanan tüm integration testleri (PR-8b-2 #1254 ile eklendi:
    test_fresh_upgrade + test_testcontainers_smoke + test_seed_bakinazik_sources)
    `api-unit-tests` job'da `-m "unit or not integration"` exclude edildiği için
    hiç çalışmamış; PR-8b-2.5 (#1290) ilk wire denemesinde bug yüzeye çıktı,
    PR-8b-2.5 REVERTED (#1291). Bu fix #1292 issue'sunu kapatır + tüm o silent
    dead test'ler işlevsel hale gelir.

    Çözüm: alembic CLI'sını `subprocess.run` ile ayrı process'te çalıştır.
    Subprocess kendi event loop'unu yaratır → parent pytest-asyncio loop'la
    çakışmaz. `alembic/env.py` (production migration path) **DEĞİŞTİRİLMEDİ**.
    env.py `DATABASE_URL` env var'ından URL okur (bkz: get_database_url).
    asyncpg URL formatı `async_engine_from_config` ile uyumludur.
    """
    import subprocess
    import sys

    from sqlalchemy.ext.asyncio import create_async_engine

    repo_root = os.environ.get("PYTEST_REPO_ROOT", ".")
    # Subprocess ortamı: parent env + DATABASE_URL override (asyncpg URL)
    subprocess_env = {**os.environ, "DATABASE_URL": pg_url}
    # `sys.executable -m alembic` mutlak Python yolu kullanır (S607 partial-path
    # uyarısından kaçınır + virtualenv'le tutarlı interpreter garantisi).
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=repo_root,
        env=subprocess_env,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"alembic upgrade head failed (exit={result.returncode}):\n"
            f"--- stdout ---\n{result.stdout}\n"
            f"--- stderr ---\n{result.stderr}"
        )

    # NullPool: pool reuse YOK — her `engine.connect()` fresh asyncpg connection.
    # Sebep: session-scoped engine + function-scoped pytest-asyncio test'leri =
    # farklı event loop'lar. Default QueuePool/AsyncAdaptedQueuePool ping/reuse
    # mantığı, ilk test'in loop'una bağlı connection'ları sonraki test'lerin
    # loop'unda kullanmaya çalışır → `Future attached to a different loop` hatası.
    # NullPool bu reuse'u tamamen elimine eder; integration test setup için
    # ideal trade-off (tek-process disposable DB, performans kritik değil).
    from sqlalchemy.pool import NullPool

    engine = create_async_engine(pg_url, poolclass=NullPool)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture()
async def test_db_session(test_db_engine) -> AsyncIterator[object]:  # type: ignore[no-untyped-def]
    """Per-test transactional rollback — testler birbirini etkilemez."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    async with test_db_engine.connect() as conn:
        trans = await conn.begin()
        session_factory = async_sessionmaker(bind=conn, expire_on_commit=False, class_=AsyncSession)
        async with session_factory() as session:
            try:
                yield session
            finally:
                await trans.rollback()


# ============================================================================
# Marker setup
# ============================================================================


def pytest_configure(config):  # type: ignore[no-untyped-def]
    """Custom markers ve auto-skip logic."""
    config.addinivalue_line(
        "markers",
        "needs_docker: integration test gerektirir docker daemon",
    )


def pytest_collection_modifyitems(config, items):  # type: ignore[no-untyped-def]
    """integration ve eval marker'lı testlere otomatik skip ekle."""
    if not DOCKER_AVAILABLE:
        skip_marker = pytest.mark.skip(reason="docker daemon yok")
        for item in items:
            if "integration" in item.keywords or "needs_docker" in item.keywords:
                item.add_marker(skip_marker)
