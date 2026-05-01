-- =============================================================================
-- Postgres init script (Docker entrypoint)
-- Bu dosya postgres container ilk kez ayağa kalktığında çalışır.
-- Extension'lar Alembic migration üzerinden yükleneceği için minimal:
-- timezone setup + audit user (gelecekte).
-- =============================================================================

-- Timezone
ALTER DATABASE nodrat SET timezone TO 'UTC';

-- Performans tuning (production-ready defaults)
-- Bu değerler container restart sonrası persistent olur (postgresql.conf'ta).
-- Tek satırlık ALTER SYSTEM yerine docker-compose'da -c argümanları daha iyi olabilir,
-- ama init script de basit + çalışıyor.
ALTER SYSTEM SET shared_buffers = '4GB';
ALTER SYSTEM SET effective_cache_size = '12GB';
ALTER SYSTEM SET work_mem = '16MB';
ALTER SYSTEM SET maintenance_work_mem = '1GB';
ALTER SYSTEM SET random_page_cost = 1.1;
ALTER SYSTEM SET max_connections = 100;
