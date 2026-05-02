# Nodrat — Manuel Deployment Adımları (Operasyon Rehberi)

**Sürüm:** v1.0 (2026-05-02)
**Hedef kitle:** Selman (kullanıcı) · DevOps · operasyon ekibi

Bu rehber, MVP-1 launch öncesi kullanıcı tarafından **manuel olarak yapılması gereken** tek seferlik adımları içerir. Otomatize edilmiş işler ayrıca [`infra/deploy.sh`](../../infra/deploy.sh) ve [`.github/workflows/`](../../.github/workflows/) dosyalarındadır.

---

## 0. Hızlı checklist (kullanıcının uyandığında yapacakları)

```text
[ ] 1) DEEPSEEK_API_KEY veya NIM_API_KEY env doğrula (mevcut: NIM)
[ ] 2) Resend API key al ve .env'e ekle (#68 unblock)
[ ] 3) Backblaze B2 hesabı + bucket aç (#41 unblock)
[ ] 4) Sentry projesi oluştur + DSN al (.env: SENTRY_DSN)
[ ] 5) Better Uptime hesabı + 4 monitor ekle
[ ] 6) age key oluştur + sops kurulumu
[ ] 7) GitHub Actions secrets ekle (CI/CD için)
[ ] 8) Admin user'ı sıfırla / şifre değiştir (Geliştirme placeholder)
[ ] 9) Production .env'i sops ile şifrele
[ ] 10) Cloudflare DNS ayarları kontrol (zaten yapıldı)
```

---

## 1. API Anahtarları (Production .env)

### 1.1 NIM (NVIDIA — chat + embedding)
✅ **Hâlihazırda yapılı.** `NIM_API_KEY` env'de set edilmiş.

NIM ücretsiz tier şunları sağlıyor:
- DeepSeek V3 chat (deepseek-ai/deepseek-v3.1-terminus — varsayılan)
- Embedding: nvidia/nv-embedqa-e5-v5 (1024-dim)

### 1.2 Resend (transactional email — #68)
**Yapılacak:**
1. https://resend.com adresinden hesap aç (developer plan free tier)
2. Domain doğrula: `nodrat.com` SPF/DKIM kayıtları
3. API key oluştur: dashboard → API keys → Create
4. VPS'te `.env` dosyasına ekle:
   ```bash
   ssh -p 443 root@173.212.238.104
   cd /opt/nodrat
   echo "RESEND_API_KEY=re_xxxxxxxxxxxxx" >> .env
   chmod 600 .env
   ```
5. API restart: `docker compose restart api`

**Not:** Issue #68 backend implementasyonu API key sağlandığında açılacak. Şu anda template dosyalar yok; kayıt onayı, parola sıfırlama ve admin uyarıları için kullanılacak.

### 1.3 Sentry (error tracking — #42)
**Yapılacak:**
1. https://sentry.io adresinden hesap aç (free tier 5K event/month)
2. Yeni proje oluştur: Platform = Python (FastAPI) → "nodrat-api"
3. İkinci proje: Platform = Next.js → "nodrat-web"
4. DSN'i kopyala
5. VPS .env'e ekle:
   ```bash
   echo "SENTRY_DSN=https://xxxx@oxxxx.ingest.sentry.io/xxxx" >> .env
   echo "NEXT_PUBLIC_SENTRY_DSN=https://yyyy@oxxxx.ingest.sentry.io/yyyy" >> .env
   ```
6. `docker compose restart api web`
7. Sentry'de ilk error'i tetiklemek için: `curl https://nodrat.com/api/__not_a_real_path` (404 — Sentry'de görünmeli)

### 1.4 Better Uptime (uptime monitoring — #42)
**Yapılacak:**
1. https://betteruptime.com hesap aç (free tier 10 monitor)
2. `infra/uptime-monitors.md` dosyasındaki 4 monitor'i ekle:
   - https://nodrat.com (5 dk, 200 OK)
   - https://nodrat.com/health (1 dk, JSON contains "status:ok")
   - https://nodrat.com/api/admin/sources (5 dk, 401 expected — auth wall)
   - https://nodrat.com/legal/abuse (5 dk, 200)
3. Notification policy: 3 ardışık fail → email + (opsiyonel) Slack/Discord
4. (Opsiyonel) Status page oluştur: status.nodrat.com (Cloudflare DNS'te CNAME)

---

## 2. Backblaze B2 Backup (#41)

### 2.1 Hesap + bucket
1. https://www.backblaze.com/b2 adresinden hesap aç
2. Bucket oluştur: `nodrat-backups-prod` (private, encryption enabled)
3. Application key oluştur:
   - Capabilities: `listBuckets`, `readFiles`, `writeFiles`, `deleteFiles`
   - Bucket: sadece `nodrat-backups-prod`
4. Endpoint, Key ID, Application Key kaydet

### 2.2 VPS setup (PR #136 ile otomatize edildi)

> **Not:** Backup pipeline artık `infra/backup.sh` + `infra/restore.sh` ile çalışır. Aşağıdaki adımlar **bir kerelik kurulum**, sonrasında cron otomatik.

```bash
ssh -p 443 root@173.212.238.104
cd /opt/nodrat

# 1) restic install (Debian/Ubuntu) — VPS'te zaten v0.12.1 var
apt update && apt install -y restic

# 2) .env'e B2 credentials + RESTIC_PASSWORD ekle:
#    B2_KEY_ID, B2_APP_KEY, B2_BUCKET=nodrat-prod-backups,
#    B2_BUCKET_ID, B2_ENDPOINT, RESTIC_PASSWORD
#    (zaten production'da kurulu)

# 3) Repository init (sadece bir kez — zaten yapıldı)
set -a && . ./.env && set +a
export B2_ACCOUNT_ID=$B2_KEY_ID
export B2_ACCOUNT_KEY=$B2_APP_KEY
export RESTIC_REPOSITORY="b2:$B2_BUCKET:nodrat"
restic init   # → "created restic repository"

# 4) İlk manuel backup test
/opt/nodrat/infra/backup.sh

# 5) Snapshot listesi
restic snapshots
```

### 2.3 Daily cron (production'da kurulu)

```bash
# /etc/crontab (root) — 04:00 UTC = 07:00 Türkiye
0 4 * * * /opt/nodrat/infra/backup.sh >> /var/log/nodrat/backup.log 2>&1
```

Backup pipeline:
1. PostgreSQL `pg_dump -Fc` (compressed custom format)
2. MinIO buckets `mc mirror` (articles/thumbnails)
3. `.env` + `docker-compose.yml` + `Caddyfile`
4. `restic backup` → B2 (encrypted client-side)
5. Retention prune: 7 daily + 4 weekly + 6 monthly

Logs: `/var/log/nodrat/backup-YYYY-MM-DD-HHMMSS.log`

### 2.4 Disaster recovery — restore drill

**Aylık 1 kez** restore drill yapılması zorunlu (KS-1 acceptance criterion):

```bash
# Snapshot listesi
ssh -p 443 root@173.212.238.104
cd /opt/nodrat
set -a && . ./.env && set +a
export B2_ACCOUNT_ID=$B2_KEY_ID
export B2_ACCOUNT_KEY=$B2_APP_KEY
export RESTIC_REPOSITORY="b2:$B2_BUCKET:nodrat"
restic snapshots --compact

# Dry-run restore (önce gör)
/opt/nodrat/infra/restore.sh latest --dry-run

# Gerçek restore (PRODUCTION'DA YAPMA — sandbox VPS'te)
/opt/nodrat/infra/restore.sh <snapshot-id>
# "RESTORE" yazarak onay → pg_restore + mc mirror

# Servisleri yeniden başlat
docker compose restart api scheduler worker_*
curl https://nodrat.com/api/health
```

### 2.4 Restore drill (ayda 1)
```bash
# Latest snapshot listele
restic snapshots --tag postgres

# Restore
restic restore latest --target /tmp/restore

# Test load (geçici DB'ye)
gunzip < /tmp/restore/tmp/nodrat-pg-XXX.sql.gz | psql -h localhost -p 5434 -U nodrat nodrat_restore_test
```

---

## 3. sops + age secrets management (#38)

`infra/sops-setup.md` rehberi tam adımları içeriyor. Özet:

### 3.1 Lokalde
```bash
brew install age sops      # macOS
age-keygen -o ~/.config/sops/age/keys.txt

# public key'i al ve infra/.sops.yaml'e ekle:
# creation_rules:
#   - path_regex: \.env$
#     age: age1xxxxxxxxxxxxxxxxxxx
```

### 3.2 .env şifreleme
```bash
cd /opt/nodrat
sops -e .env > .env.encrypted
git add .env.encrypted infra/.sops.yaml
# .env hâlâ .gitignore'da, sadece .encrypted commit
```

### 3.3 VPS'te decrypt
```bash
# VPS'e age public/private key kopyala (manuel, scp ile)
mkdir -p /etc/sops/age
scp ~/.config/sops/age/keys.txt root@173.212.238.104:/etc/sops/age/keys.txt

# VPS'te decrypt
sops -d .env.encrypted > .env
chmod 600 .env
```

---

## 4. GitHub Actions secrets

CI/deploy workflow'ları için repo secrets.

> **Not:** Aşağıdakilerden 5'i (HOST/PORT/USER/PATH/KNOWN_HOSTS) ajan tarafından otomatik set edildi — sadece **`VPS_SSH_KEY`** seni bekliyor (güvenlik nedeniyle özel anahtarın repo secret'a yüklenmesi onay gerektiriyor).

```bash
# Tek eksik adım — sen çalıştır:
gh secret set VPS_SSH_KEY < ~/.ssh/id_ed25519

# Aşağıdakiler ZATEN set (verify için):
gh secret list
# Beklenen: VPS_HOST, VPS_PORT, VPS_USER, VPS_PATH, VPS_KNOWN_HOSTS, VPS_SSH_KEY

# Opsiyonel
gh secret set SLACK_WEBHOOK_URL -b "https://hooks.slack.com/..."
```

`VPS_SSH_KEY` set edildikten sonra, sonraki main push'unda otomatik deploy çalışır (şu an her push fail ediyor: "ssh-private-key argument is empty").

GitHub Settings → Environments → "production" oluştur → Required reviewers: kendin

---

## 5. Admin user yönetimi

### 5.1 Geliştirme döneminde oluşturulan admin
**E-posta:** selmanaycom@gmail.com
**Şifre:** NodratAdmin2026! (DEVELOPMENT GRADE — hemen değiştir)

### 5.2 Şifre değiştirme
Şu an UI'dan password reset yok (#68 Resend bekliyor). VPS'ten manuel:

```bash
ssh -p 443 root@173.212.238.104
docker compose exec -T api python -c "
import asyncio
from sqlalchemy import select
from app.core.security import hash_password
from app.models.user import User
from app.workers.tasks.sources import _get_session_factory

async def reset(email, new_pass):
    factory = _get_session_factory()
    async with factory() as db:
        u = (await db.execute(select(User).where(User.email == email))).scalar_one()
        u.password_hash = hash_password(new_pass)
        await db.commit()
        print(f'Reset: {email}')

asyncio.run(reset('selmanaycom@gmail.com', 'YENI_GUCLU_SIFRE'))
"
```

### 5.3 Yeni admin oluşturma
`/admin/users` UI'dan yeni admin oluşturulamaz (security). Yeni admin için:
1. Normal kayıt: `/register` → user role
2. SSH ile role'ünü `super_admin` yap (yukarıdaki pattern'in PATCH versiyonu)

---

## 6. Cloudflare DNS (zaten yapıldı)

**Mevcut konfigürasyon:**
- `nodrat.com` A → 173.212.238.104 (Proxy ON)
- `www.nodrat.com` CNAME → nodrat.com
- SSL/TLS mode: **Full (strict)**
- Origin certificate: `/etc/nginx/ssl/nodrat.{crt,key}`

**Doğrulama:**
```bash
dig nodrat.com +short    # 173.212.238.104 dönmeli
curl -I https://nodrat.com    # HTTP/2 200, server: cloudflare
```

---

## 7. Production smoke test (her deploy sonrası)

```bash
# 1. Public sayfalar
for u in nodrat.com nodrat.com/register nodrat.com/login \
         nodrat.com/legal/tos nodrat.com/legal/abuse \
         nodrat.com/bot nodrat.com/health; do
  printf "%-35s → %s\n" "$u" "$(curl -sIL -o /dev/null -w '%{http_code}' https://$u)"
done

# 2. API auth wall (401 beklenir)
for path in /api/app/me /api/admin/users /api/admin/legal/requests; do
  echo "$path → $(curl -s -o /dev/null -w '%{http_code}' https://nodrat.com$path)"
done

# 3. Komşu siteler — dokunulmamış olmalı
for u in milletneder.com sosyologar.com desen.com.tr; do
  printf "%-25s → %s\n" "$u" "$(curl -sIL -o /dev/null -w '%{http_code}' https://$u)"
done

# 4. Pipeline durumu (admin login + DB query)
ssh -p 443 root@173.212.238.104 "
  docker compose exec -T postgres psql -U nodrat -d nodrat -c '
    SELECT
      (SELECT count(*) FROM users WHERE deleted_at IS NULL) AS users,
      (SELECT count(*) FROM sources WHERE is_active) AS active_sources,
      (SELECT count(*) FROM articles WHERE status = '\''cleaned'\'') AS cleaned_articles,
      (SELECT count(*) FROM event_clusters) AS clusters,
      (SELECT count(*) FROM agenda_cards) AS agenda_cards,
      (SELECT count(*) FROM generations WHERE status = '\''completed'\'') AS generations,
      (SELECT count(*) FROM provider_call_logs WHERE created_at > NOW() - INTERVAL '\''1 day'\'') AS provider_calls_24h;
  '
"
```

---

## 8. Closed alpha launch (ayrı doc)

`docs/research/alpha-invite-checklist.md` tam launch checklist.

Özet:
1. Whitelist email backend hazır (#69 admin user mgmt UI ile)
2. 5-10 kişi davet (alpha-target-criteria.md kriterleriyle)
3. 30 gün gözlem
4. KS-1 metrikleri ölç (alpha-success-metrics.md)
5. Go/no-go: 5/5 KPI → MVP-2 hazır

---

## 9. Acil durum (incident response)

`docs/legal/incident-response.md` SEV-1 prosedürü.

Hızlı erişim:
- Production crash → `docker compose restart api web`
- DB connection hatası → `docker compose restart postgres api`
- LLM provider down → `docker compose exec api python -c 'from app.providers.registry import registry; print(list(registry._providers))'`
- KVKK ihlali → DPO çağrısı + 72h timer

İletişim:
- legal@nodrat.com
- dpo@nodrat.com

---

## Değişiklik notları

- **2026-05-02 v1.0** — İlk yayın (4 paralel agent batch sonrası MVP-1 %96)
