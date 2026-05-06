# Secrets Yönetimi — sops + age Kurulumu

> **Issue:** #38 — docker-compose production refinement + sops .env
> **Karar:** docs/engineering/architecture.md §13 D7 (sops + age)
> **Kapsam:** `.env` ve `.env.production` dosyaları repo'da düz metin
> tutulamaz; sops + age ile şifrelenmiş varyant repo'da, plaintext sadece
> deployment anında VPS üzerinde elde edilir.

Bu rehber ekibe sops + age workflow'unu uçtan uca tarif eder. Gerçek
şifreleme anahtarı **kullanıcı tarafından** lokal makinede üretilir; bu repo
hiçbir koşulda gerçek private key barındırmaz.

---

## 1. Bir defalık kurulum

### 1.1 macOS / Linux paketleri

```bash
# macOS (Homebrew)
brew install sops age

# Linux (Debian/Ubuntu)
apt-get install -y age
# sops için release binary indir: https://github.com/getsops/sops/releases
```

Doğrula:

```bash
sops --version          # ≥ 3.9
age --version           # ≥ 1.1
age-keygen --version    # age binary ile birlikte gelir
```

### 1.2 age key üretimi (kullanıcı bilgisayarı)

> **Bu adımı sadece kullanıcı kendisi koşturur.** Üretilen private key
> (`~/.config/sops/age/keys.txt`) **asla repo'ya commit edilmez**.

```bash
mkdir -p ~/.config/sops/age
age-keygen -o ~/.config/sops/age/keys.txt
chmod 600 ~/.config/sops/age/keys.txt
```

Çıktıdaki public key (`age1...` ile başlayan satır) ekibe ve `.sops.yaml`
dosyasına `creation_rules.age` listesine eklenir. Private key dosyası
aşağıdaki yol ile sops tarafından otomatik bulunur:

```bash
export SOPS_AGE_KEY_FILE="$HOME/.config/sops/age/keys.txt"
```

Bu satırı `~/.zshrc` veya `~/.bashrc` içine ekleyin.

### 1.3 VPS deploy key

VPS'in de `.env.encrypted` dosyasını çözebilmesi için kendi age key
çiftine ihtiyacı var:

```bash
ssh root@164.68.107.205 -p 22 \
  "mkdir -p /etc/sops/age && age-keygen -o /etc/sops/age/keys.txt && chmod 600 /etc/sops/age/keys.txt"
```

VPS'teki public key'i `infra/.sops.yaml` `creation_rules.age` listesine
ekleyin (recipient sayısı 2 olur: maintainer + deploy). Sonra dosyayı
yeniden şifreleyin (bkz. §3.3).

---

## 2. Repo tarafı yapı

```
infra/
├── .sops.yaml                  # creation rules (committed)
├── .env.encrypted              # production secrets (committed, encrypted)
├── .env.encrypted.example      # placeholder structure (committed)
└── sops-setup.md               # bu doküman
```

`.gitignore` ile düz metin `.env` ve `.env.production` her zaman dışarıda
tutulur. `*.encrypted` uzantılı dosyalar repo'ya **girer**.

---

## 3. Günlük workflow

### 3.1 Yeni secret yazma / değiştirme

```bash
# Şifrelenmiş dosyayı doğrudan editör ile aç (decrypt → edit → re-encrypt)
sops infra/.env.encrypted
```

### 3.2 Plaintext'ten şifreli dosya üretme

```bash
# Lokal .env hazırsa:
sops --encrypt --config infra/.sops.yaml .env > infra/.env.encrypted
```

### 3.3 Recipient eklendiğinde re-encrypt

```bash
sops updatekeys --config infra/.sops.yaml infra/.env.encrypted
```

### 3.4 Decrypt (deploy adımı)

```bash
sops --decrypt infra/.env.encrypted > .env
chmod 600 .env
```

---

## 4. CI / CD entegrasyonu (issue #40)

GitHub Actions deploy workflow'u VPS'e SSH ile bağlandıktan sonra
şu adımı çalıştırır:

```bash
ssh root@$VPS "cd /opt/nodrat && \
  SOPS_AGE_KEY_FILE=/etc/sops/age/keys.txt \
  sops --decrypt infra/.env.encrypted > .env && chmod 600 .env"
```

`infra/deploy.sh` mevcut manuel script'i bu workflow'a paralel kalır
(workflow ve script aynı operasyonu yapar). Manuel deploy yapan kullanıcı
yerel `.env` dosyasını `scp` ile gönderirken sops çalışmamış olabilir;
bu durumda script `infra/.env.encrypted` mevcutsa tercihen sops decrypt
adımını koşturur, yoksa düz `.env`'i atar.

---

## 5. Güvenlik notları

- Private key dosyası (`keys.txt`) **disk şifrelemesi** olan bir cihazda
  saklanır (FileVault, LUKS).
- Yedek: 1Password / Bitwarden gibi secret manager içinde **yalnız
  hash/parmak izi** değil, dosya içeriği zaten encrypted; düz metin
  yedekleme yapılmaz.
- Key rotasyon: yılda bir kez veya bir maintainer ayrıldığında
  `age-keygen` ile yeni çift üretilir, eski recipient `.sops.yaml`'dan
  kaldırılır, tüm `*.encrypted` dosyalar `sops updatekeys` ile yeniden
  şifrelenir.
- `git log` üzerinde plaintext kontrolü — eski commit'lerde sızma varsa
  o secret production'da rotated kabul edilir.

---

## 6. Sorun giderme

| Hata | Olası neden |
| --- | --- |
| `Failed to get the data key required to decrypt the SOPS file` | Mevcut age private key bu recipient'a karşılık gelmiyor — `keys.txt` doğru mu? |
| `no encryption configuration found` | `.sops.yaml` repo kökünde değil; sops `--config infra/.sops.yaml` parametresi ile çağrılmalı |
| `unsupported encryption mode` | sops sürümü < 3.7 — Homebrew/release güncellemesi |

---

## 7. Çapraz Referans

- docs/engineering/architecture.md §7 — Secrets Yönetimi (mimari kararı)
- docs/engineering/architecture.md §7.4 — sops + age operational workflow
- docs/engineering/threat-model.md §3 — secret leakage tehdidi
- infra/.sops.yaml — encryption rules
- infra/.env.encrypted.example — boş yapısal örnek
- infra/deploy.sh — VPS deploy script (sops decrypt aşaması)

---

## 8. MVP-1.5 — Contabo Object Storage credentials (Epic #215)

> **Not**: MVP-1.5 migration ile Backblaze B2 → Contabo Object Storage.
> Eski `B2_*` envaranrı yerine `S3_*` generic envaranlar kullanılacak.
> Tam migration adımları: docs/operations/deployment-manual-steps.md §11.

Yeni `.env` alanları (sops-encrypted):

```bash
# Contabo Object Storage (S3-compatible)
S3_ACCESS_KEY=<contabo-os-access-key>
S3_SECRET_KEY=<contabo-os-secret-key>
S3_ENDPOINT=https://eu2.contabostorage.com
S3_REGION=eu2
S3_BUCKET=nodrat-prod-backups

# Restic
RESTIC_PASSWORD=<32-char-random>
RESTIC_REPOSITORY=s3:eu2.contabostorage.com/nodrat-prod-backups/nodrat
```

**Eski B2 alanları (PR-2 sonrası KALDIR):**
- `B2_KEY_ID`, `B2_APP_KEY`, `B2_BUCKET`, `B2_BUCKET_ID`, `B2_ENDPOINT`

**Migration prosedürü:**
1. Yeni Contabo OS credentials .env.encrypted'e ekle (sops)
2. PR-2'de restic backend swap test (init + first backup)
3. Eski B2 alanları kaldır + sops re-encrypt
4. Eski B2 bucket 30 gün retention sonrası sil
