#!/usr/bin/env bash
# =============================================================================
# Nodrat — VPS deploy script
#
# Kullanım (yerel makineden):
#   ./infra/deploy.sh                       # Mevcut .env kullanarak deploy
#
# VPS bilgisi:
#   Host  : 173.212.238.104
#   Port  : 443 (sslh)
#   User  : root
#   Path  : /opt/nodrat
#
# ⚠️ VPS'te başka uygulamalar çalışıyor:
#   - nginx (80, 4443)
#   - PostgreSQL (5432) [başka projelerin]
#   - PM2/Node servisleri (3000, 4000, 9000) [milletneder, desen]
#
# Bu script izole olarak Nodrat stack'i ayağa kaldırır:
#   - Docker containers prefix "nodrat-"
#   - Web 3010 (3000 dolu)
#   - API 8000
#   - Postgres 5433 (5432 dolu)
#   - Redis 6380
#   - MinIO 9100/9101
#   - nginx mevcut konfigine vhost ekler (nodrat.com → 8000/3010 proxy)
# =============================================================================

set -euo pipefail

VPS_HOST="173.212.238.104"
VPS_PORT="443"
VPS_USER="root"
VPS_PATH="/opt/nodrat"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/id_ed25519}"
SSH_OPTS="-p ${VPS_PORT} -i ${SSH_KEY} -o StrictHostKeyChecking=accept-new"

echo "════════════════════════════════════════════════════"
echo "  Nodrat VPS Deploy"
echo "  Target: ${VPS_USER}@${VPS_HOST}:${VPS_PORT}"
echo "  Path:   ${VPS_PATH}"
echo "════════════════════════════════════════════════════"
echo ""

# -----------------------------------------------------------------------------
# 1. SSH bağlantı kontrolü
# -----------------------------------------------------------------------------
echo "[1/8] SSH bağlantı testi..."
ssh ${SSH_OPTS} ${VPS_USER}@${VPS_HOST} "echo '✓ SSH OK' && whoami"

# -----------------------------------------------------------------------------
# 2. Docker varlığı kontrol — yoksa kur
# -----------------------------------------------------------------------------
echo ""
echo "[2/8] Docker kurulumu kontrolü..."
ssh ${SSH_OPTS} ${VPS_USER}@${VPS_HOST} "bash -s" << 'REMOTE_DOCKER'
if ! command -v docker &> /dev/null; then
    echo "Docker yok, kuruluyor..."
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
    echo "✓ Docker kuruldu"
else
    echo "✓ Docker zaten mevcut: $(docker --version)"
fi
docker compose version || echo "⚠️ Docker Compose v2 plugin yok"
REMOTE_DOCKER

# -----------------------------------------------------------------------------
# 3. Repo clone / pull
# -----------------------------------------------------------------------------
echo ""
echo "[3/8] Repo sync..."
ssh ${SSH_OPTS} ${VPS_USER}@${VPS_HOST} "bash -s" << REMOTE_GIT
if [ ! -d "${VPS_PATH}/.git" ]; then
    mkdir -p "${VPS_PATH}"
    cd "${VPS_PATH}"
    git clone https://github.com/selmanays/nodrat.git . || \
        echo "⚠️ Public clone failed; SSH/PAT auth gerekebilir"
else
    cd "${VPS_PATH}"
    git fetch origin
    # Hangi branch çalışıyorsak onu pull et
    CURRENT_BRANCH=\$(git rev-parse --abbrev-ref HEAD)
    git pull origin \${CURRENT_BRANCH}
fi
git rev-parse HEAD | head -c 8
echo " (current commit)"
REMOTE_GIT

# -----------------------------------------------------------------------------
# 4. .env dosyası — sops decrypt branch | local .env scp branch (#38)
# -----------------------------------------------------------------------------
echo ""
echo "[4/8] .env hazırlık..."
if [ -f infra/.env.encrypted ]; then
    # sops branch — encrypted dosya repo'da, VPS kendi age key'i ile decrypt eder
    echo "→ infra/.env.encrypted bulundu, VPS üzerinde sops decrypt edilecek"
    ssh ${SSH_OPTS} ${VPS_USER}@${VPS_HOST} "bash -s" << REMOTE_SOPS
cd ${VPS_PATH}
if ! command -v sops &> /dev/null; then
    echo "⚠️ sops VPS'te yüklü değil — kurulum: https://github.com/getsops/sops/releases"
    echo "   skip — fallback için local .env scp gerekli"
    exit 0
fi
if [ ! -f /etc/sops/age/keys.txt ]; then
    echo "⚠️ /etc/sops/age/keys.txt yok — VPS deploy key kurulu değil"
    echo "   bkz. infra/sops-setup.md §1.3"
    exit 0
fi
SOPS_AGE_KEY_FILE=/etc/sops/age/keys.txt sops --decrypt infra/.env.encrypted > .env
chmod 600 .env
echo "✓ .env sops ile decrypt edildi (mod 600)"
REMOTE_SOPS
elif [ -f .env ]; then
    # Legacy branch — local plaintext .env'i scp ile transfer
    scp ${SSH_OPTS} .env ${VPS_USER}@${VPS_HOST}:${VPS_PATH}/.env
    ssh ${SSH_OPTS} ${VPS_USER}@${VPS_HOST} "chmod 600 ${VPS_PATH}/.env"
    echo "✓ .env transfer edildi (mod 600, plaintext)"
else
    echo "⚠️ Ne infra/.env.encrypted ne de local .env mevcut — VPS'te manuel oluşturulacak"
fi

# -----------------------------------------------------------------------------
# 5. Docker Compose up
# -----------------------------------------------------------------------------
echo ""
echo "[5/8] Docker Compose up..."
ssh ${SSH_OPTS} ${VPS_USER}@${VPS_HOST} "bash -s" << REMOTE_COMPOSE
cd ${VPS_PATH}
# Caddy'yi disable et (VPS'te zaten nginx var)
docker compose --env-file .env up -d \\
    postgres redis minio api web \\
    worker_scraper worker_cleaner worker_embedding worker_rag scheduler
echo ""
echo "Container durumu:"
docker compose ps
REMOTE_COMPOSE

# -----------------------------------------------------------------------------
# 6. Migration çalıştır
# -----------------------------------------------------------------------------
echo ""
echo "[6/8] Database migration..."
ssh ${SSH_OPTS} ${VPS_USER}@${VPS_HOST} "bash -s" << REMOTE_MIGRATE
cd ${VPS_PATH}
# DB hazır olana kadar bekle
sleep 5
docker compose exec -T api alembic upgrade head
echo "✓ Migration tamamlandı"
REMOTE_MIGRATE

# -----------------------------------------------------------------------------
# 7. nginx vhost ekle
# -----------------------------------------------------------------------------
echo ""
echo "[7/8] nginx vhost setup..."
ssh ${SSH_OPTS} ${VPS_USER}@${VPS_HOST} "bash -s" << REMOTE_NGINX
cd ${VPS_PATH}
if [ ! -f /etc/nginx/sites-available/nodrat ]; then
    cp infra/nginx-nodrat.conf /etc/nginx/sites-available/nodrat
    ln -sf /etc/nginx/sites-available/nodrat /etc/nginx/sites-enabled/nodrat
fi

# Test config + reload
if nginx -t 2>&1 | grep -q "successful"; then
    systemctl reload nginx
    echo "✓ nginx reload OK"
else
    echo "⚠️ nginx config test başarısız:"
    nginx -t
    rm -f /etc/nginx/sites-enabled/nodrat
    systemctl reload nginx
    echo "Önceki config geri yüklendi"
    exit 1
fi
REMOTE_NGINX

# -----------------------------------------------------------------------------
# 8. Smoke test
# -----------------------------------------------------------------------------
echo ""
echo "[8/8] Smoke test..."
ssh ${SSH_OPTS} ${VPS_USER}@${VPS_HOST} "bash -s" << 'REMOTE_SMOKE'
echo "API healthcheck (host'tan):"
curl -fsS http://localhost:8000/health | head -1 || echo "API erişilemedi"
echo ""
echo "Web (host'tan):"
curl -fsSI http://localhost:3010 | head -1 || echo "Web erişilemedi"
echo ""
echo "Public URL test (Cloudflare → nginx → docker):"
curl -fsSI -H "Host: nodrat.com" http://localhost/health | head -3 || echo "nginx vhost erişilemedi"
REMOTE_SMOKE

echo ""
echo "════════════════════════════════════════════════════"
echo "  ✓ Deploy tamamlandı"
echo "  Test URL: https://nodrat.com (Cloudflare üzerinden)"
echo "════════════════════════════════════════════════════"
