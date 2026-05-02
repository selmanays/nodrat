#!/usr/bin/env bash
# Nodrat backup script (#41 + #135)
#
# Usage:
#   ./infra/backup.sh                       # full backup (PostgreSQL + MinIO + .env)
#   ./infra/backup.sh --skip-minio          # only DB + config
#   ./infra/backup.sh --skip-prune          # don't run retention prune
#
# Output:
#   /var/log/nodrat/backup-YYYY-MM-DD.log
#
# Cron usage:
#   0 4 * * * /opt/nodrat/infra/backup.sh >> /var/log/nodrat/backup.log 2>&1
#
# Retention (restic forget):
#   - Last 7 daily snapshots
#   - Last 4 weekly snapshots
#   - Last 6 monthly snapshots
#
# References:
#   - docs/engineering/architecture.md §9
#   - docs/legal/incident-response.md §10.1
#   - docs/operations/deployment-manual-steps.md §2

set -euo pipefail

# ---- Config -----------------------------------------------------------------

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

# Load env (B2 creds, postgres creds, restic password)
if [[ ! -f .env ]]; then
  log "ERROR: ${NODRAT_DIR}/.env not found"
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

log "==== Nodrat backup START (${TS}) ===="
log "Target: ${RESTIC_REPOSITORY}"
log "Log:    ${LOG_FILE}"

# ---- 1. PostgreSQL dump -----------------------------------------------------

log ""
log "[1/3] PostgreSQL dump ..."
PG_DUMP_FILE="${TMP_DIR}/postgres-${POSTGRES_DB}.dump"

if ! docker compose exec -T \
    -e PGPASSWORD="${POSTGRES_PASSWORD}" \
    postgres pg_dump \
      -U "${POSTGRES_USER}" \
      -h 127.0.0.1 \
      -d "${POSTGRES_DB}" \
      -Fc \
    > "${PG_DUMP_FILE}"; then
  log "ERROR: pg_dump failed"
  exit 3
fi

PG_SIZE=$(du -h "${PG_DUMP_FILE}" | cut -f1)
log "  pg_dump OK (${PG_SIZE})"

# ---- 2. MinIO snapshot ------------------------------------------------------

if [[ ${SKIP_MINIO} -eq 0 ]]; then
  log ""
  log "[2/3] MinIO snapshot ..."

  MINIO_DIR="${TMP_DIR}/minio"
  mkdir -p "${MINIO_DIR}"

  # mc client check (install if missing)
  if ! command -v mc &> /dev/null; then
    log "  installing mc client (mcli) ..."
    curl -sSL https://dl.min.io/client/mc/release/linux-amd64/mc \
      -o /usr/local/bin/mc
    chmod +x /usr/local/bin/mc
  fi

  # Configure local MinIO alias (uses container exposed port)
  mc alias set nodrat-minio "http://127.0.0.1:9000" \
      "${MINIO_ROOT_USER:-minioadmin}" "${MINIO_ROOT_PASSWORD:-minioadmin}" \
      --api S3v4 > /dev/null 2>&1

  # Mirror buckets to local tmp dir
  for bucket in articles thumbnails; do
    if mc ls "nodrat-minio/${bucket}" > /dev/null 2>&1; then
      log "  mirroring ${bucket} ..."
      mc mirror --quiet --overwrite \
        "nodrat-minio/${bucket}" "${MINIO_DIR}/${bucket}/" \
        >> "${LOG_FILE}" 2>&1 || log "  WARN: ${bucket} mirror partial"
    fi
  done

  MINIO_SIZE=$(du -sh "${MINIO_DIR}" 2>/dev/null | cut -f1 || echo "0")
  log "  MinIO snapshot OK (${MINIO_SIZE})"
else
  log "[2/3] MinIO SKIPPED (--skip-minio)"
fi

# ---- 3. Config backup -------------------------------------------------------

log ""
log "[3/3] Config + .env backup ..."
CONFIG_DIR="${TMP_DIR}/config"
mkdir -p "${CONFIG_DIR}"

# .env (already encrypted via sops in repo, but include just in case)
cp .env "${CONFIG_DIR}/.env"
chmod 600 "${CONFIG_DIR}/.env"

# docker-compose files
cp docker-compose.yml "${CONFIG_DIR}/"
[[ -f docker-compose.dev.yml ]] && cp docker-compose.dev.yml "${CONFIG_DIR}/"

# Caddyfile
[[ -f infra/Caddyfile ]] && cp infra/Caddyfile "${CONFIG_DIR}/"

log "  config OK"

# ---- 4. restic backup -------------------------------------------------------

log ""
log "[4/4] restic backup ..."
restic backup \
  --tag "auto" \
  --tag "$(date +%Y-%m-%d)" \
  --host "$(hostname)" \
  "${TMP_DIR}" \
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

# Always exit 0 if we got here
exit 0
