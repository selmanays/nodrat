#!/usr/bin/env bash
# Nodrat restore script (#41 + #135)
#
# Disaster recovery: restic snapshot → unpack → restore PostgreSQL + MinIO
#
# Usage:
#   ./infra/restore.sh                          # interactive (lists snapshots)
#   ./infra/restore.sh <snapshot-id>            # restore specific snapshot
#   ./infra/restore.sh latest                   # restore most recent
#   ./infra/restore.sh <snapshot> --dry-run     # show what would happen
#
# WARNING: This OVERWRITES the current PostgreSQL database. Take a manual
# pg_dump first if you want to preserve current state.
#
# References:
#   - docs/legal/incident-response.md §10.1 (RTO 4h)
#   - infra/backup.sh

set -euo pipefail

NODRAT_DIR="${NODRAT_DIR:-/opt/nodrat}"
RESTORE_DIR="${RESTORE_DIR:-/tmp/nodrat-restore}"

SNAPSHOT="${1:-}"
DRY_RUN=0

if [[ "${2:-}" == "--dry-run" ]]; then
  DRY_RUN=1
fi

# ---- Setup ------------------------------------------------------------------

cd "${NODRAT_DIR}"

if [[ ! -f .env ]]; then
  echo "ERROR: ${NODRAT_DIR}/.env not found" >&2
  exit 1
fi
set -a
# shellcheck disable=SC1091
. ./.env
set +a

export B2_ACCOUNT_ID="${B2_KEY_ID}"
export B2_ACCOUNT_KEY="${B2_APP_KEY}"
export RESTIC_REPOSITORY="b2:${B2_BUCKET}:nodrat"
export RESTIC_PASSWORD

# ---- 1. Pick snapshot -------------------------------------------------------

if [[ -z "${SNAPSHOT}" ]]; then
  echo ""
  echo "Recent snapshots:"
  restic snapshots --compact 2>/dev/null | tail -20
  echo ""
  echo "Usage: $0 <snapshot-id>  (or 'latest')"
  exit 0
fi

if [[ "${SNAPSHOT}" == "latest" ]]; then
  SNAPSHOT=$(restic snapshots --json --latest 1 2>/dev/null \
    | python3 -c "import json,sys; print(json.load(sys.stdin)[-1]['short_id'])")
fi

echo "Selected snapshot: ${SNAPSHOT}"
echo ""

# ---- 2. Confirm (unless dry-run) -------------------------------------------

if [[ ${DRY_RUN} -eq 0 ]]; then
  echo "⚠️  WARNING: This will OVERWRITE current data:"
  echo "   - PostgreSQL database '${POSTGRES_DB}' will be dropped + recreated"
  echo "   - MinIO buckets will be replaced"
  echo ""
  read -rp "Type 'RESTORE' to proceed: " CONFIRM
  if [[ "${CONFIRM}" != "RESTORE" ]]; then
    echo "Aborted."
    exit 1
  fi
fi

# ---- 3. Unpack snapshot -----------------------------------------------------

rm -rf "${RESTORE_DIR}"
mkdir -p "${RESTORE_DIR}"

echo ""
echo "[1/4] Restoring snapshot ${SNAPSHOT} to ${RESTORE_DIR} ..."
restic restore "${SNAPSHOT}" --target "${RESTORE_DIR}"

# Find the actual content path (restic mirrors source path)
TMP_BACKUP=$(find "${RESTORE_DIR}" -name "postgres-${POSTGRES_DB}.dump" -type f | head -1)
TMP_BACKUP_DIR=$(dirname "${TMP_BACKUP}")

if [[ ! -f "${TMP_BACKUP}" ]]; then
  echo "ERROR: pg_dump file not found in snapshot" >&2
  exit 4
fi

echo "  unpacked to: ${TMP_BACKUP_DIR}"

# ---- 4. PostgreSQL restore --------------------------------------------------

echo ""
echo "[2/4] Restoring PostgreSQL ..."

if [[ ${DRY_RUN} -eq 1 ]]; then
  echo "  (dry-run) would: pg_restore -c --if-exists -d ${POSTGRES_DB} ${TMP_BACKUP}"
else
  # Drop + recreate database (clean slate)
  docker compose exec -T \
    -e PGPASSWORD="${POSTGRES_PASSWORD}" \
    postgres psql -U "${POSTGRES_USER}" -h 127.0.0.1 -d postgres \
    -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${POSTGRES_DB}' AND pid <> pg_backend_pid();" \
    > /dev/null 2>&1 || true

  # Copy dump into postgres container, then restore
  docker compose cp "${TMP_BACKUP}" postgres:/tmp/restore.dump
  docker compose exec -T \
    -e PGPASSWORD="${POSTGRES_PASSWORD}" \
    postgres pg_restore \
      -U "${POSTGRES_USER}" -h 127.0.0.1 -d "${POSTGRES_DB}" \
      --clean --if-exists --no-owner \
      /tmp/restore.dump
  docker compose exec -T postgres rm -f /tmp/restore.dump
  echo "  ✓ PostgreSQL restored"
fi

# ---- 5. MinIO restore -------------------------------------------------------

echo ""
echo "[3/4] Restoring MinIO ..."

MINIO_BACKUP_DIR="${TMP_BACKUP_DIR}/minio"

if [[ ! -d "${MINIO_BACKUP_DIR}" ]]; then
  echo "  WARN: MinIO snapshot not in this backup — skipping"
else
  if [[ ${DRY_RUN} -eq 1 ]]; then
    echo "  (dry-run) would: mc mirror ${MINIO_BACKUP_DIR}/* nodrat-minio/"
  else
    if ! command -v mc &> /dev/null; then
      curl -sSL https://dl.min.io/client/mc/release/linux-amd64/mc \
        -o /usr/local/bin/mc
      chmod +x /usr/local/bin/mc
    fi
    mc alias set nodrat-minio "http://127.0.0.1:9000" \
        "${MINIO_ROOT_USER:-minioadmin}" "${MINIO_ROOT_PASSWORD:-minioadmin}" \
        --api S3v4 > /dev/null

    for dir in "${MINIO_BACKUP_DIR}"/*; do
      [[ -d "${dir}" ]] || continue
      bucket=$(basename "${dir}")
      mc mb "nodrat-minio/${bucket}" 2>/dev/null || true
      mc mirror --overwrite "${dir}" "nodrat-minio/${bucket}/"
    done
    echo "  ✓ MinIO restored"
  fi
fi

# ---- 6. Cleanup -------------------------------------------------------------

echo ""
echo "[4/4] Cleanup ..."
rm -rf "${RESTORE_DIR}"

echo ""
echo "==== Restore complete ===="
echo ""
echo "Next steps:"
echo "  1. docker compose restart api scheduler worker_*"
echo "  2. Smoke test: curl https://nodrat.com/api/health"
echo "  3. Verify users/articles count via /admin"
echo ""

exit 0
