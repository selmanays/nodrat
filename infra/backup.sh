#!/bin/bash
# Nodrat production backup → Contabo Object Storage (S3)
#
# Cron: günlük 04:00 Europe/Istanbul (cron sistem TZ)
# Repo: s3:https://eu2.contabostorage.com/nodrat-prod/restic
#
# Yapılan iş:
#   1. PostgreSQL pg_dump → /tmp/nodrat-backup/postgres.dump
#   2. MinIO data snapshot (mc mirror veya cp -R) → /tmp/nodrat-backup/minio/
#   3. .env + docker-compose.yml + infra/Caddyfile → /tmp/nodrat-backup/config/
#   4. restic backup --tag auto --tag YYYY-MM-DD
#   5. restic forget --keep-daily 7 --keep-weekly 4 --keep-monthly 6 --prune
#
# References:
#   - docs/engineering/architecture.md §9 (backup strategy)
#   - docs/legal/incident-response.md §10.1 (recovery procedure)
#   - docs/operations/deployment-manual-steps.md §2

set -euo pipefail

NODRAT_DIR="${NODRAT_DIR:-/opt/nodrat}"
LOG_DIR="${LOG_DIR:-/var/log/nodrat}"
TMP_DIR="${TMP_DIR:-/tmp/nodrat-backup}"

SKIP_MINIO=0
SKIP_PRUNE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-minio) SKIP_MINIO=1; shift ;;
    --skip-prune) SKIP_PRUNE=1; shift ;;
    -h|--help)
      head -25 "$0" | grep -E '^#' | sed 's/^# \?//'
      exit 0
      ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done

# ---- Setup ------------------------------------------------------------------

mkdir -p "${LOG_DIR}" "${TMP_DIR}"
TS=$(date +%Y-%m-%d-%H%M%S)
LOG_FILE="${LOG_DIR}/backup-${TS}.log"
START_TS=$(date +%s)

log() {
  local msg="[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] $*"
  echo "${msg}" | tee -a "${LOG_FILE}" >&2
}

cleanup() {
  rm -rf "${TMP_DIR}"
}
trap cleanup EXIT

cd "${NODRAT_DIR}"

# Load env (S3 creds, postgres creds, restic password)
if [[ ! -f .env ]]; then
  log "ERROR: ${NODRAT_DIR}/.env not found"
  exit 1
fi
set -a
# shellcheck disable=SC1091
. ./.env
set +a

# Restic backend: Contabo S3 (MVP-1.5 PR-2)
export RESTIC_REPOSITORY="s3:${S3_ENDPOINT_URL}/${S3_BUCKET}/restic"
export AWS_ACCESS_KEY_ID="${S3_ACCESS_KEY_ID}"
export AWS_SECRET_ACCESS_KEY="${S3_SECRET_ACCESS_KEY}"
export RESTIC_PASSWORD

if [[ -z "${RESTIC_PASSWORD:-}" ]]; then
  log "ERROR: RESTIC_PASSWORD not set in .env"
  exit 1
fi

log "==== Nodrat backup START (${TS}) ===="
log "Target: ${RESTIC_REPOSITORY}"
log "Log:    ${LOG_FILE}"
log ""

# ---- 1. PostgreSQL dump -----------------------------------------------------

log "[1/3] PostgreSQL dump ..."

PG_DUMP_FILE="${TMP_DIR}/postgres.dump"

# Container içinden pg_dump (Docker compose)
if docker compose ps postgres 2>/dev/null | grep -q "Up"; then
  docker compose exec -T postgres pg_dump \
    -U "${POSTGRES_USER:-nodrat}" \
    -d "${POSTGRES_DB:-nodrat}" \
    --format=custom \
    --no-owner \
    --no-acl \
    > "${PG_DUMP_FILE}" 2>>"${LOG_FILE}"
  PG_SIZE=$(du -h "${PG_DUMP_FILE}" | cut -f1)
  log "  pg_dump OK (${PG_SIZE})"
else
  log "ERROR: postgres container not running"
  exit 1
fi

# ---- 2. MinIO snapshot ------------------------------------------------------

log ""
log "[2/3] MinIO snapshot ..."

if [[ ${SKIP_MINIO} -eq 1 ]]; then
  log "  MinIO SKIPPED (--skip-minio)"
else
  MINIO_DIR="${TMP_DIR}/minio"
  mkdir -p "${MINIO_DIR}"

  if [[ -d "${NODRAT_DIR}/data/minio" ]]; then
    rsync -a "${NODRAT_DIR}/data/minio/" "${MINIO_DIR}/"
    MINIO_SIZE=$(du -sh "${MINIO_DIR}" | cut -f1)
    log "  MinIO snapshot OK (${MINIO_SIZE})"
  else
    log "  MinIO data dir not found — skipping"
    SKIP_MINIO=1
  fi
fi

# ---- 3. Config backup -------------------------------------------------------

log ""
log "[3/3] Config + .env backup ..."

CONFIG_DIR="${TMP_DIR}/config"
mkdir -p "${CONFIG_DIR}"

# .env (kritik — secrets dahil)
cp .env "${CONFIG_DIR}/.env"

# Compose + infra
[[ -f docker-compose.yml ]] && cp docker-compose.yml "${CONFIG_DIR}/"
[[ -f docker-compose.dev.yml ]] && cp docker-compose.dev.yml "${CONFIG_DIR}/"
[[ -d infra ]] && rsync -a --exclude="*.log" infra/ "${CONFIG_DIR}/infra/"

log "  config OK"

# ---- 4. Restic backup -------------------------------------------------------

log ""
log "[4/4] restic backup ..."

DATE_TAG=$(date +%Y-%m-%d)

restic backup "${TMP_DIR}" \
  --tag auto \
  --tag "${DATE_TAG}" \
  --host "$(hostname)" \
  --exclude-caches \
  >> "${LOG_FILE}" 2>&1

SNAPSHOT_ID=$(restic snapshots --json --tag auto 2>/dev/null \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(d[-1]['short_id'] if d else '?')" \
  || echo "?")

log "  snapshot saved: ${SNAPSHOT_ID}"

# ---- 5. Retention prune -----------------------------------------------------

if [[ ${SKIP_PRUNE} -eq 0 ]]; then
  log ""
  log "[5/5] Retention prune ..."
  restic forget \
    --keep-daily 7 \
    --keep-weekly 4 \
    --keep-monthly 6 \
    --prune \
    >> "${LOG_FILE}" 2>&1
  log "  prune OK"
else
  log "[5/5] Prune SKIPPED (--skip-prune)"
fi

# ---- Summary ----------------------------------------------------------------

END_TS=$(date +%s)
DURATION=$((END_TS - START_TS))

log ""
log "==== Nodrat backup DONE ===="
log "  Snapshot:    ${SNAPSHOT_ID}"
log "  Duration:    ${DURATION}s"
log "  Repository:  ${RESTIC_REPOSITORY}"

# Latest snapshots
log ""
log "Recent snapshots:"
restic snapshots --compact --json 2>/dev/null \
  | python3 -c "
import json, sys
data = json.load(sys.stdin)
for s in data[-5:]:
    print(f\"  {s['short_id']}  {s['time'][:19]}  {','.join(s.get('tags',[]))}\")
" >> "${LOG_FILE}" 2>&1

exit 0
