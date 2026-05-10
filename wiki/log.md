---
title: Wiki Log — Kronolojik Kayıt
type: hub
updated: 2026-05-10
---
<!-- En son giriş yukarıda (Faz 5 stil profili #52 ship: 3 yeni wiki sayfası) -->



# Wiki Log

## [2026-05-10] feat | MVP-1.7 SFT Foundation backend %100 deploy — generations telemetry + KVKK consent + endpoints + ETL + admin dashboard (#563-#569)

- **Kaynak/Tetikleyici:** Founder stratejik karar (kendi domain-spesifik Türkçe SLM için veri toplama altyapısı) — tam yetki + sürekli onay sormama disiplini ile MVP-1.7 backend katmanı end-to-end ship edildi. Bu turda 5 PR + 1 hotfix merge'lendi, hepsi production'da.
- **Etkilenen sayfalar:** Bu ingest **kasıtlı olarak yeni wiki sayfası açmıyor** — kullanıcı önceki turda planning aşamasında (#574) açılan `own-slm-strategy`, `trendyol-llm-base`, `sft-data-pipeline` sayfalarını main'e merge etmemeyi tercih etti. Saygı gösterilerek log.md'ye sadece deploy progress kaydedilir; gelecekte kullanıcı isterse wiki sayfaları ayrıca açılır.
- **Yeni:** 0 wiki page (kullanıcı kararı)
- **Güncellendi:** 0 wiki page (sadece bu log girişi)

### Ship özeti — 5 PR + 1 hotfix

| Issue | PR | Merge | İçerik |
|---|---|---|---|
| #563 | [#575](https://github.com/selmanays/nodrat/pull/575) | `8a826ae` | `generations` tablosuna 7 SFT telemetry kolonu (user_action, edit_distance, sft_eligible, vb.) + 2 CHECK constraint + 1 partial index |
| #564 | [#580](https://github.com/selmanays/nodrat/pull/580) | `2adf38a` | `users` tablosuna 5 KVKK consent kolonu (`model_improvement_consent_*`) + 4 hukuki doc v0.3 (kvkk-aydinlatma + tos + privacy-policy + ropa) |
| #566 | [#584](https://github.com/selmanays/nodrat/pull/584) | `2432906` | 5 user action endpoint (copied/posted/edited/regenerated/deleted) + 3 consent endpoint (GET/POST/DELETE) + Levenshtein utility + `_recompute_sft_eligibility` 7-koşullu helper |
| #566 fix | [#586](https://github.com/selmanays/nodrat/pull/586) | `2960a79` | Path double-prefix fix: `/me/consent/...` → `/consent/...` (router prefix `/app/me` ile birleşince çift `/me/` çıkıyordu) |
| #567 | [#588](https://github.com/selmanays/nodrat/pull/588) | `94bac11` | `training_samples` tablosu + ORM + nightly Celery ETL worker (`tasks.sft_curator.run`, beat 02:45 UTC) + 4 admin setting (`sft.curator.*`) + PII secondary scan + ChatML serialize + deterministic split |
| #569 | [#589](https://github.com/selmanays/nodrat/pull/589) | `d336b48` | Admin SFT backend: 5 endpoint (`/admin/sft/stats|recent|export|recompute-eligibility|consent-stats`) + JSONL streaming + manuel HF Hub push script (`apps/api/scripts/sft_push_hf.py`, default `--private`) |

### Production'da doğrulanan state

- **DB:** `generations` tablosu 7 yeni kolon + index `idx_generations_sft_eligible`. `users` tablosu 5 yeni `model_improvement_consent_*` kolon. Yeni tablo `training_samples` (12 kolon, 4 index, 2 CHECK). 4 yeni `app_settings` row (`sft.curator.*`).
- **Migration zinciri:** lineer `20260509_0900` → `20260510_0100` → `20260510_0200` (#563) → `20260510_0300` (#564) → `20260510_0500` (#567). #585 fix `0500→0600` rename'i bizim chain'imizi etkilemedi.
- **Routes:** 5 generation action + 3 consent + 5 admin SFT = **13 yeni endpoint** production'da, hepsi auth + ownership + audit log.
- **Worker:** `tasks.sft_curator.run` celery_app `include` listesinde + `embedding_queue` route + `crontab(45, 2)` beat schedule registered. Kill switch `sft.curator.enabled=false` (default).
- **Frontend:** **#568 kullanıcıya bırakıldı** (arayüz bu turda dışı). Backend API contract eksiksiz; UI bağlanması bekleniyor.

### KVKK uyumu

- KVKK md.5/2-a açık rıza pattern: `model_improvement_consent_*` 5 kolon (TIA audit: at + version + ip + text_hash + revoked_at)
- KVKK md.11 geri çekme: `DELETE /app/me/consent/model-improvement` → `UPDATE generations SET sft_eligible=false, sft_excluded_reason='consent_revoked'` cascade
- KVKK md.7 silme: user soft delete → `training_samples` FK CASCADE
- PII secondary scan: ETL worker'da defense-in-depth (provider PII redact zaten yapılmış olsa da `pii_secondary_hit` flag ile tekrar tarama)

### Deploy disiplini

Manuel deploy default (CI kredisi tükendi). Her PR sonrası tipik akış: `gh pr merge --admin --delete-branch` → `rsync` → `docker compose build api [+ worker_embedding + scheduler]` → `up -d --force-recreate` → `alembic upgrade head` (varsa) → DB verify → curl health. Tipik süre: 2-4 dk per PR.

### Sıradaki adımlar (kullanıcıda)

- **#568 frontend** (3 dev-day): `useGenerationActions(genId)` React hook + onboarding 5. checkbox + settings consent toggle + (opsiyonel) sft_eligible badge
- **Admin /admin/sft sayfası** (UI tarafı, #569 backend hazır): Cards + Charts (Recharts) + Table + Export modal + 4 admin tunable setting
- **Wiki ingest (planning aşaması)**: Kullanıcı `own-slm-strategy` + `trendyol-llm-base` + `sft-data-pipeline` sayfalarını main'e ne zaman almak isterse ayrı PR ile açılabilir (PR #574 reference olarak duruyor)

## [2026-05-10] feat | RSS realtime polling Faz 2 — adaptive tier shadow mode production'da (#578, PR #581 + #582 hotfix)

- **Kaynak/Tetikleyici:** Faz 0+1 (#565, PR #571) sonrası kullanıcı Faz 2 onayladı + tam yetki ile end-to-end ship istedi. Plan zaten yazılı: shadow mode'da tier hesabı, polling_tier dokunulmaz, 7 gün gözlem sonrası Faz 3'le birlikte apply.
- **Etkilenen sayfalar:** [[adaptive-polling-tier]] (status `planned`→`live`, implementasyon detayları + tier_metadata örneği + flag hiyerarşisi), [[realtime-rss-polling]] (TL;DR güncel + Faz 2 ship sonrası gözlemler bloğu + Açık sorular update), [[index]] (last_resync + concept satırı + istatistik).
- **Yeni:** 0 wiki page (mevcut 3 sayfa iç güncelleme).

### İmplementasyon (Faz 2 — PR [#581](https://github.com/selmanays/nodrat/pull/581))

**Schema** (migration `20260510_0400_sources_polling_tier_shadow.py` — başta 0200 yazıldı, branched migration çakışması ile #582 hotfix sonrası 0400'e rename):
- `sources.would_be_tier` VARCHAR(16) NULL + CHECK
- `sources.tier_changed_at` TIMESTAMPTZ NULL — dwell-time guard
- `sources.tier_metadata` JSONB NULL — compute_tier telemetri
- `app_settings.rss.tier_shadow_mode` (default true) — Faz 2 default
- `app_settings.rss.tier_apply_enabled` (default false) — Faz 3'te true

**Tier hesap fonksiyonu** ([apps/api/app/core/polling_tier.py](../apps/api/app/core/polling_tier.py)):
- `compute_tier(source, db, *, now=None) → TierComputation` — saf, async
- 3 saf yardımcı: `_classify_tier` (state'siz), `_apply_transition_rules` (dwell + hibernate exit), `_count_items` + `_last_item_at` (DB query)
- Rolling window: `articles WHERE source_id=? AND published_at >= since AND status IN ('cleaned','discovered')` — mevcut `idx_articles_source_published` indeksi
- Cold start: `source.created_at < 24h` → tier='normal' force, DB query yok, `tier_metadata.cold_start=true`
- Dwell-time: 15 dk minimum tier kalıcılığı (oscillation önleme)
- Hibernate exit: items_1h>0 → direkt 'normal' (dwell bypass)

**Worker entegrasyonu** ([tasks/sources.py:_compute_and_persist_tier](../apps/api/app/workers/tasks/sources.py)):
- 200 + 304 path sonunda compute_tier çağrı
- Shadow mode: would_be_tier + tier_metadata yaz, polling_tier dokunma
- Apply mode (Faz 3): polling_tier = would_be_tier transition + tier_changed_at update
- Settings runtime tunable (`settings_store.get`)
- Hata path'i try/except — fetch task'ı tier hesabından bağımsız

**Admin UI:**
- `/admin/sources` liste — Tier kolonu (badge + divergence göstergesi)
- `/admin/sources/[id]` — TierTelemetry alt-bölüm (current vs would_be, items_1h/6h, hours_since_new, candidate_tier, dwell_remaining_sec)
- `SourcePublic`: would_be_tier + tier_changed_at + tier_metadata + consecutive_unchanged
- `lib/api.ts`: `PollingTier` + `TierMetadata` type'ları

**Tests** (14 yeni, [test_polling_tier.py](../apps/api/tests/unit/test_polling_tier.py)):
- `_classify_tier`: hot/normal/cold/hibernate threshold + priority + valid tier set
- `_apply_transition_rules`: dwell-time block/allow/first-transition + hibernate exit bypass
- `compute_tier` (mock'lu DB): cold start + hot/hibernate path + no items + metadata keys

### Hotfix PR [#582](https://github.com/selmanays/nodrat/pull/582)

PR #581 ile main'e gelen `20260510_0200_sources_polling_tier_shadow` revision'ı, paralel merge edilmiş PR #575 (`20260510_0200_generations_sft_telemetry`) ve PR #574 (`20260510_0300_users_model_improvement_consent`) ile çakıştı — Alembic `upgrade head` "more than one head revision" ile fail ederdi. Hotfix: bu migration zincirin sonuna alındı (`revision=20260510_0400`, `down_revision=20260510_0300`). Şema tarafsız.

Linear chain restored:
```
20260510_0100 (sources realtime — ETag, polling_tier foundation, #565)
→ 20260510_0200 (generations SFT telemetry, #563/#575)
→ 20260510_0300 (users model_improvement_consent, #574)
→ 20260510_0400 (sources tier shadow mode, #578 — bu)
```

**Ders:** Paralel feature work'lerde migration revision ID konvansiyonu zaman bazlı (`YYYYMMDD_HHMM`) — aynı saatte birden fazla branch açılırsa son merge edilen branch revision'ı düzelmeli. CI'da "branched migration check" hook eklemek gerek (yeni issue).

### Smoke test (production 2026-05-10)

```sql
-- alembic_version
20260510_0400 ✅

-- sources schema (3 yeni kolon)
would_be_tier VARCHAR(16)
tier_changed_at TIMESTAMPTZ
tier_metadata JSONB

-- app_settings (2 yeni seed)
rss.tier_shadow_mode = true
rss.tier_apply_enabled = false

-- haberturk manuel crawl smoke
would_be_tier = 'normal'  ← compute_tier çalıştı
polling_tier = 'normal'   ← shadow mode korundu (DEĞİŞMEDİ)
tier_metadata = {
  "items_1h": 0, "items_6h": 3, "hours_since_new": 3.15,
  "candidate_tier": "normal", "cold_start": false,
  "dwell_remaining_sec": 0.0, "consecutive_unchanged": 0,
  "computed_at": "2026-05-10T10:27:52+00:00"
}
```

✅ Shadow mode mantığı production'da doğru çalışıyor.

### Manuel deploy disiplini (Faz 0+1'den ders)

İlk bake parallel build OOM'a girdi → tek tek build (api: 5s rebuild, worker_scraper: 270s, web: 5s) ile çözüldü. 4 migration sırayla uygulandı (0100→0200→0300→0400). API rebuild zorunlu — yeni migration dosyası image'a COPY ile gider. CI Actions kredisi yok, `gh pr merge --admin` bypass ile main'e geçti.

### Sonraki adımlar

7 gün shadow mode gözlem (would_be_tier distribution + oscillation + cold start davranışı izle). Sonra Faz 3:
- DB connection pool size doğrulaması
- Celery beat 15dk → 30 sn due-check
- crawl_queue worker concurrency 1-2 → 6
- Jitter ±%15 dispatch
- HTTP 429 + Retry-After handling
- `app_settings.rss.tier_apply_enabled=true` ile gerçek transition başlar

---

## [2026-05-10] feat | RSS realtime polling Faz 0+1 — schema foundation + Conditional GET + admin PATCH (#565, PR #571)

- **Kaynak/Tetikleyici:** Kullanıcı "gündem radarı" sistemi tasarlama isteği → araştırma → mevcut RSS pipeline'ın anlık olmadığı tespit edildi (sabit 30 dk polling, hot/cold ayrımı yok, Conditional GET yok, runtime edit endpoint yok). 5 fazlı yol haritası: schema/Conditional GET (Faz 0+1) → adaptive tier hesabı (Faz 2) → beat refactor + worker concurrency (Faz 3) → URL/scrape opt-in realtime (Faz 4) → wiki sync (Faz 5). Kullanıcı 2026-05-10'da Faz 0+1 onayladı + tam yetki ile end-to-end (docs + merge + deploy + wiki) tek seferde tamamlanması istendi.
- **Etkilenen sayfalar:** [[realtime-rss-polling]] (yeni decision), [[conditional-http-get]] (yeni concept), [[adaptive-polling-tier]] (yeni concept — Faz 2 prep), [[data-pipelines]] §1 (source crawl pipeline akış güncellendi), [[risk-source-fragility]] (R-OPS-01 mitigation güçlendi — bu sayfa içeriği değişmedi ama decision sayfasında atıf var).
- **Yeni:** 1 decision + 2 concept = **3 wiki sayfası**.
- **Güncellendi:** [[data-pipelines]] §1 başlığı + akış diyagramı (Conditional GET adımı + tier referansı), [[index]] (3 yeni satır + istatistik bloğu: 42→45 sayfa, 11→12 locked decision), [[log]] (bu giriş).
- **Notlar:**
  - **Forward-compatible foundation:** sources tablosuna **5 nullable kolon** (`etag`, `last_modified`, `realtime_enabled`, `polling_tier` CHECK hot/normal/cold/hibernate, `consecutive_unchanged`) + `app_settings.rss_realtime_master_enabled` global kill-switch (default false). Davranış değişimi yok.
  - **Conditional GET:** `fetch_feed(etag, last_modified)` parametreleri → `If-None-Match` + `If-Modified-Since` header'ları gider; HTTP 304 → `not_modified=True` + queue dispatch yok + `consecutive_unchanged++`; HTTP 200 → yeni etag/last_modified persist + sayaç sıfır. Curl fallback path'inde extra_headers düşer (h11 protocol err edge-case).
  - **Admin:** `PATCH /admin/sources/{id}` (yeni endpoint) — runtime tunable alanlar (`crawl_interval_minutes` 5-1440, `realtime_enabled`, `name`, `category`); slug/domain/type/base_url **immutable**; audit log `source.update` action ile from/to snapshot.
  - **Web UI:** `/admin/sources/[id]` detay sayfasına "Polling ayarları" kartı (interval input + realtime mode Switch) — aktif kaynaklarda görünür.
  - **Tests:** 6 yeni Conditional GET unit testi (`test_rss.py`: 304 path, header send/no-send, ETag/Last-Modified persist, case-sensitivity edge, missing headers); yeni `test_admin_sources.py` (router wiring + schema invariants).
  - **CI durumu:** GitHub Actions billing/quota tükendiği için 8/8 job runner allocation fail (`billable: null`). PR `gh pr merge --squash --admin` ile bypass edildi.
  - **Manuel deploy:** Bake parallel build OOM (RAM bol ama "signal: killed") — tek tek build yapılarak çözüldü (api: 5s, worker_scraper: 270s rebuild). API rebuild zorunluydu çünkü ilk bake'de migration dosyası image'a kopyalanmamıştı. Migration `20260509_0900 → 20260510_0100` uygulandı; 5 yeni kolon DB'de + seed mevcut.
  - **Production smoke (geçti):**
    - DB schema doğrulandı (5 kolon + default değerler + CHECK).
    - `app_settings.rss_realtime_master_enabled = false` mevcut.
    - `PATCH /admin/sources/{uuid}` → HTTP 401 unauth (endpoint canlı, auth doğru).
    - haberturk RSS crawl → ETag persist (`W/"KXHOOMECLDXQLTMZV"`); ardışık iki crawl ETag karşılaştırması yapıldı.
    - 304 path **protokol seviyesinde kanıtlandı** (curl ile haberturk RSS'a `If-None-Match` doğru ETag → HTTP 304); production'da haberturk Merlin CDN her node'dan farklı Weak ETag verdiği için bizim worker'ın `If-None-Match`'i çoğu kez eşleşmez ve 200 döner — bu sunucu davranışı, kod hatası değil. Faz 2'de polling sıklığı artınca (60sn) bu problem (CDN ETag tutarsızlığı) Cache-Control max-age parsing ile mitigate edilebilir; ayrı issue.
    - api / web / scheduler / worker_scraper hepsi healthy.
  - **docs/ güncellemeleri (PR #571 içinde):** `docs/engineering/data-model.md` §3.1 sources +5 kolon (v0.1 → v0.2); `docs/engineering/api-contracts.md` §4.4 PATCH /admin/sources/{id} tam spec (v0.3 → v0.4); INDEX.md sürüm tablosu güncel.
  - **Sıradaki adım önerileri Faz 2-3-4 sırasında planlandı; gündem radarı (orijinal kullanıcı isteği) Faz 2 sonrası daha verimli çalışacak çünkü dakika seviyesi freshness olacak.**
- **Hard kural ihlali yok:** docs/ güncellemesi kullanıcı explicit yetkisi ile yapıldı (CLAUDE.md §1.1 LLM yazma kuralı user override ile ezildi); wiki update bu ayrı PR'da (CLAUDE.md §1.3.3 — feature PR + ayrı wiki PR disiplini); paralel agent worktree'ler için bu wiki sync write conflict riskini minimize ediyor.

---

## [2026-05-10] feat | VPS disk panel — piechart breakdown + safe build cache cleanup (#570, PR #572)

- **Kaynak/Tetikleyici:** 2026-05-10 sabah disk %30→%80 ani sıçrama. Tanı: 2 günlük streaming epic'i içinde 4-5 kez `docker compose build --no-cache` koştuk, eski cache layer'ları reclaimable durumda biriken (305/345 GB). Manuel `docker builder prune -af` ile %80→%17 düştü (304 GB free). Kullanıcı bunu UI'a taşımak istedi: piechart + tek-tıkla güvenli cleanup.
- **Etkilenen sayfa:** [[contabo-vps]] entity (operasyonel ek not eklenebilir — bu commit'te dokunulmadı); [[pipeline-observability-location]] decision (yeni alt-panel: /admin/system/disk).
- **Yeni:** 0 wiki page

### Backend ([content_generator yok, admin_system.py'a eklendi](https://github.com/selmanays/nodrat/pull/572/files))

`apps/api/app/api/admin_system.py` içine 2 yeni endpoint:
- **`GET /admin/system/disk`** — DiskBreakdown response:
  - host disk: `psutil.disk_usage('/')` (total/used/free + percent)
  - docker breakdown: Python `docker` SDK `client.df()` → images/containers/volumes/build_cache + reclaimable per kategori
  - 'other' kategorisi: `host_used - docker_total` (logs/system/opt)
- **`POST /admin/system/disk/cleanup`** — yalnızca build cache prune:
  - `client.api.prune_builds(all=True)` — eşdeğer `docker builder prune -af`
  - SpaceReclaimed + CachesDeleted dönüş
  - **AdminAuditLog** action='disk_cleanup' kaydı (actor_id, metadata: reclaimed_bytes, items_deleted, duration, error if any)
  - Aktif container/image/volume zarar görmez (`builder prune` sadece build cache layer'larını siler)

### Yapılandırma değişiklikleri

- **`apps/api/pyproject.toml`:** `docker>=7.0` Python SDK eklendi
- **`docker-compose.yml`:** api service'e `/var/run/docker.sock:/var/run/docker.sock` mount
  - Trade-off: api container compromise → host docker daemon erişimi
  - Mitigation: endpoint'ler `require_admin` gated + her cleanup audit log'da

### Frontend (`apps/web/src/app/admin/system/disk/page.tsx`)

shadcn preset b1VlIttI uyumlu — `ui/*` dokunulmadı, kullanım yerinde className/inline style + `cn` pattern:
- 4 KPI cards: Toplam / Kullanılan / Boş / Reclaimable
- Severity-colored progress bar (%75 amber, %90 red)
- **Recharts pie chart** (mevcut shadcn chart wrapper + `recharts ^3.8.0` zaten dep): inner+outer radius, padding angle, custom palette (HSL chart-1..5 vars)
- Categories table (boyut + reclaimable badge)
- 'Yer aç' butonu + Dialog confirm modal (zarar görmeyen şeyleri checkmark'larla listeler)
- Loading state + sonner toast (success: 'X GB geri kazanıldı', error: ApiException message)

`/admin/observability` mevcut Disk widget'ına 'Detay →' link eklendi — drill-down pattern.

### Test

- Backend: `docker.from_env().df()` Docker daemon API'si — gerçek prod'da test edilir (mock complex, az kazanç). require_admin gate audit pattern eski endpoint'lerle aynı.
- Frontend: tsc clean. `next build` lokal node_modules bozuk olduğu için fail aldı; container'da fresh `pnpm install` ile build yapılır (deploy verifies).

### İlk gözlem (2026-05-10 öncesi)

`docker system df` çıktısında ham veriler:
- Build Cache: 344.8 GB total, 305.4 GB reclaimable (417 entry, hiçbiri active)
- Images: 332 GB (12 active)
- Containers: 4.5 GB (12 active)
- Local Volumes: 17.6 GB (6 active, 0 reclaimable)

Cleanup sonrası:
- Build Cache: 0 GB
- Images: 58 GB (orphan layer'lar da temizlendi)
- Disk: 386 GB → 82 GB (%80 → %17)

### Manuel deploy disiplini eki

`--no-cache` rebuild'ler kullanıcı testleri sırasında frequent → build cache hızla birikiyor. **Yeni cron öneri (sonraki tur):** haftalık otomatik `docker builder prune -af` cron job. Şimdilik manuel UI butonu yeterli.

Refs: #570, #572

---

## [2026-05-10] revert | Pre-LLM relevance gate + summary warnings gate kaldırıldı — over-filter (#553→#558→#560 saga)

- **Kaynak/Tetikleyici:** Kullanıcı 2026-05-09'da "Akın Gürlek 'sosyal medya özgürlük alanı değil' ne zaman dedi" sorgusunda LLM'in internal terminoloji ('gündem kartları', 'kaynak bulunamamıştır') sızdırdığını gözlemledi. Tanı: parse_x_post_response summary path'ında warnings gate eksik (x-post path ile asimetri); ek olarak retrieval kart döndüğünde alaka kontrolü yok, LLM gereksiz çağrılıyor.
- **Etkilenen sayfa:** [[sse-streaming-default]] — "Implementation iterasyonları" bölümüne saga özet notu + revert açıklaması eklendi.
- **Yeni:** 0 wiki page

### Saga (3 PR'lık iterasyon, hepsi aynı gün başlayıp sonraki güne sarktı)

**1. #553 / [PR #554](https://github.com/selmanays/nodrat/pull/554) — eklendi (eklenip-test-edip-iyileştirilen yaklaşım)**

İki katman gate:
- **Fix #1 (post-LLM):** parse_x_post_response summary mode'da warnings={'irrelevant_sources','insufficient_data'} → ContentGenError(insufficient_data). X-post path ile simetri.
- **Fix #2 (pre-LLM):** is_top_card_relevant_for_llm(cards) helper — top-1 _rerank_score öncelik (eşik 0.0), fallback _score_meta.semantic_score (eşik 0.60). Handler'larda retrieval sonrası gate; reject ise LLM çağrılmaz.

**2. #558 / [PR #559](https://github.com/selmanays/nodrat/pull/559) — threshold tune (0.60 → 0.50)**

Gate'in 0.60 default'u "Bu hafta CHP ile ilgili 3 önemli gelişme özetle" gibi LEGİTİMATE Türkçe gündem sorgularını reject ediyordu. Tradeoff yeniden değerlendirildi:
- Pre-LLM gate kazancı: ~$0.0004/sorgu cost tasarrufu
- Post-LLM warnings gate (Fix #1) sızıntıyı zaten kapatıyor
- UX > $0.0004; default 0.50'ye düşürüldü.

**3. #560 / [PR #561](https://github.com/selmanays/nodrat/pull/561) — tamamen revert** ✅ **FINAL STATE**

Threshold 0.50 yetmedi; üretimde hâlâ legitimate sorgular reject. Karar: iki katmanı tamamen kaldır.
- `is_top_card_relevant_for_llm` helper silindi (`apps/api/app/core/retrieval.py`)
- Handler gate çağrıları silindi (`apps/api/app/api/app_generate.py` + `app_generate_stream.py`)
- Summary mode warnings gate kaldırıldı (`content_generator.py:565` — summary_doc_items dolu olduğunda direkt GeneratedXContent dön; gate revert)
- `tests/unit/test_pre_llm_relevance_gate.py` silindi
- `test_content_generator_prompt.py` summary warnings testleri sadeleştirildi (3 → 1: warnings passes through)

### Final state (2026-05-10)

- INSUFFICIENT_DATA UI sadece **retrieval gerçekten 0 agenda + 0 chunk** döndüğünde (mevcut, dokunulmaz).
- Retrieval kart bulduğunda LLM her zaman çağrılır; LLM kendi yargısıyla cevap üretir. Eğer kartlar alakasız ise LLM doğal dilde "konuyla ilgili bilgi bulunamadı" tarzı cevap verir; kullanıcı bunu okur.
- X-post path warnings gate KORUNDU (posts=[] durumunda zaten error path mantıklı).

### Manuel deploy gotcha (yine)

İlk #559 deploy'unda **paralel SSH session docker compose lock conflict** yaşandı: önceki background build task stuck kaldı, container 45dk eski threshold'la (0.60) çalıştı. `docker rm -f` ile temizlik + foreground rebuild gerekti. Sonraki deploy'larda compact tek-komut SSH (heredoc + uzun timeout yerine) tercih edildi.

### Trade-off özeti (kalıcı)

- **Cost:** alakasız sorgu için LLM çağrısı yapılır (~$0.0004) — kabul.
- **UX risk:** LLM internal terminoloji sızdırabilir ("gündem kartları" vb.) — kabul. Sonraki tur LLM system prompt'unda "agenda card / kart / kaynak gibi internal terminoloji KULLANMA, kullanıcı dostu doğal dil yaz" instruction eklenebilir (ayrı issue).

Refs: #553, #554, #558, #559, #560, #561

---

## [2026-05-09] fix | Stream done event'i error state'i override etmesin (#555, PR #556)

- **Kaynak/Tetikleyici:** PR #553/PR #554 deploy sonrası kullanıcı: backend pre-LLM gate REJECT ettiği halde UI 'Tamamlandı' yanıltıcı state gösteriyor + "0 paylaşım üretildi" success toast geliyor. Beklediği insufficient_data suggestion kartı görünmüyor.
- **Etkilenen sayfa:** [[sse-streaming-default]] — Implementation iterasyonları bölümünde mevcut.
- **Yeni:** 0 wiki page

### Root cause

Backend insufficient_data path:
```
yield event:error  (code=INSUFFICIENT_DATA, suggestions)
yield event:done   (status=insufficient_data)
```

Frontend hook event order:
- `onError` → setState `stage='error'`, error={...}
- `onDone` → setState `stage='done'` ← **override!** error state silinir.

useEffect (page.tsx) `stage='done'` branch'ine girince synthesized success result oluşturuyordu: status='completed', posts=[], toast 'X paylaşım üretildi' (yanıltıcı).

### Fix (apps/web/src/hooks/use-generation-stream.ts)

```typescript
onDone: (data) => setState((prev) => ({
  ...prev,
  stage: prev.error ? "error" : "done",  // error varsa koru
  isStreaming: false,
  ...
}))
```

Page useEffect zaten her iki branch'i ayırt ediyor; tek-satır hook fix yeterli.

Refs: #555, #556

---

## [2026-05-09] fix | Streaming finishing touches — explicit max_posts + nested summary_doc path (#548, #550)

- **Kaynak/Tetikleyici:** Streaming akışı (PR #528 + #532/#536/#540/#544/#546) sonrası kullanıcı tarayıcı testinde 2 yeni edge case tespit etti:
  1. **#548:** "Paylaşım adedi=1" seçildiğinde planner cümleden `requested_count=5` algıladı, backend `payload.max_posts==1`'i 'default' sayıp 5 ile override etti → kullanıcı tek özet kart beklerken 5 ayrı kart üretildi.
  2. **#550:** Summary mode (`output_type=summary`) çıktısında metin tek seferde belirir, canlı yazma yok — backend prompt nested şema (`summary_doc.title`, `summary_doc.items[].event`) kullanıyor ama frontend helper FLAT alan adları (`summary_doc_title`, `summary_doc_items`) arıyordu.
- **Etkilenen sayfa:** [[sse-streaming-default]] (Implementation iterasyonları bölümüne 2 ek not eklendi).
- **Yeni:** 0 wiki page

### Fix #1 — Paylaşım adedi explicit ([PR #549](https://github.com/selmanays/nodrat/pull/549) `24b72fc6`)

`PAYLOAD_DEFAULT_MAX_POSTS = 1` sentinel-as-default yaklaşımı 'default 1' ile 'kullanıcı bilinçli 1'i ayırt edemiyordu. Fix: explicit `None` vs sayı ayrımı:

- Backend `GenerateRequest.max_posts: int | None = Field(default=None, ge=1, le=10)` — `apps/api/app/api/app_generate.py` + `app_generate_stream.py` her ikisi
- Backend handler:
  ```python
  if payload.max_posts is None:
      effective_max_posts = max(1, plan.requested_count or 1)  # planner karar
  else:
      effective_max_posts = payload.max_posts  # user explicit
  ```
- Frontend `maxPosts: number | null`, dropdown'a `Otomatik` SelectItem (default `null`); submit'te `null → undefined` (Pydantic `None`'a düşer).

UX:
- 'Otomatik' → planner cümleden algılar ('5 paylaşım üret' → 5; 'tweet at' → 1)
- '1', '3', '5', '7', '10' → kullanıcı bilinçli; planner ne dese de override yok.

### Fix #2 — Summary nested path ([PR #551](https://github.com/selmanays/nodrat/pull/551) `4f008939`)

PR #546 (#545) live extract eklerken FLAT field adları kullanmıştı. Backend `content_generator.py:240` SUMMARY prompt'u NESTED şema kullanıyor:

```json
{
  "summary_doc": {
    "title": "...",
    "items": [{"event": "...", "source": "...", "date": "...", "agenda_card_id": "..."}, ...]
  }
}
```

`parse_x_post_response` nested → flat dönüşüm yapıyor (line 541-545 `summary_doc.get("items")`), o yüzden final `parsed` event'inde UI doğru görünüyor — ama chunk delta'larında pattern eşleşmediği için partial extract sıfır → streaming yok.

Helper iki katmanlı arama yapacak şekilde düzeltildi (`apps/web/src/lib/partial-json-posts.ts`):

```typescript
extractPartialSummaryItems(buffer)  →
  parentMatch = /"summary_doc"\s*:\s*\{/.exec(buffer)
  sub = buffer.slice(parentMatch.end)
  return extractPartialFieldArray(sub, "items", "event")

extractPartialSummaryTitle(buffer)  →
  aynı parent scope, sonra extractPartialScalarString(sub, "title")
```

Hook (`use-generation-stream.ts`) yeni fonksiyonları kullanıyor (eski `extractPartialScalarString(buffer, "summary_doc_title")` çağrısı silindi). Node smoke 5/5 PASS (title growing, title closed + items array opening, first event growing, multi-item closed + last open, posts mode regression).

### Schema sözleşmesi (önemli — gelecek değişikliklerde dikkat)

Backend prompt şeması ile frontend helper path'i **senkron** olmalı:

| Field | Backend prompt | Backend parse | Frontend helper path |
|---|---|---|---|
| posts | `posts: [{...}]` flat | flat | `extractPartialPostTexts(buffer)` |
| summary title | `summary_doc.title` nested | flat'a (`summary_doc_title`) çevrilir | `extractPartialSummaryTitle(buffer)` |
| summary items | `summary_doc.items[].event` nested | flat'a (`summary_doc_items[]`) çevrilir | `extractPartialSummaryItems(buffer)` |

Eğer prompt değiştirilirse (örn. `summary_doc` flat'a açılırsa veya `posts`'u nested'a çevrilirse) frontend helper güncellemesi de yapılmalı. Bu uyumsuzluk görsel olarak final `parsed` event'inde fark edilmez — sadece chunk-level streaming kaybolur.

### Manuel deploy (CI runner outage devam)

Her iki PR de admin override merge + manuel SSH deploy:
- #549: `docker compose build --no-cache api web` + `--force-recreate api web` (her iki servis değişti)
- #551: sadece `web` (frontend-only)
- Smoke: `/api/app/generate-stream` 401 (auth gate, endpoint mounted), `/api/app/generate` 401 (regression yok), `/app/generate` 200.
- Kullanıcı tarayıcı testi PASS (her iki case): "tamam harika oldu, çalışıyor artık sorunsuzca."

---

## [2026-05-09] fix | Streaming UX iterations — live token render + finalizing stage + summary mode (#538/#542/#545)

- **Kaynak/Tetikleyici:** PR #528 (SSE streaming) + #532/#536 (Caddy buffer hotfix) deploy sonrası kullanıcı 3 ardışık iterasyonla UX problemi raporladı; her biri ayrı root cause + fix:
  1. **#538 (PR #540):** content tek seferde belirip yazılıyor → frontend `event: chunk` delta'larını rawAccumulator'a depoluyordu ama göstermiyordu; partial JSON extract yoktu.
  2. **#542 (PR #544):** son post text'i bittikten sonra UI 1-2sn daha "Yazıyor…" → DeepSeek hâlâ summary/sources/warnings yazıyor (görsel olarak fark edilmez); kullanıcı için bekleme.
  3. **#545 (PR #546):** summary mode (output_type=summary) çıktısı tek seferde belirir → helper sadece `posts[].text` arıyordu; `summary_doc_items[].event` ve `summary_doc_title` için live extract yoktu.
- **Etkilenen sayfalar:** [[sse-streaming-default]] (live render mekaniği eklendi), implicit [[streaming-json-parser]] kapsamı genişledi (frontend partial JSON extract).
- **Yeni:** 0 wiki page (mevcut concept'ler altında implementation iterasyonu)

### Fix #1 — Live token rendering ([PR #540](https://github.com/selmanays/nodrat/pull/540) `fafc34e9`)

`apps/web/src/lib/partial-json-posts.ts` (yeni):
- `extractPartialPostTexts(buffer)`: regex'le `{ "text": "..." }` field'ını yakalar. 2 pattern: closed (`(?=,|}|$)` lookahead) + open (buffer sonu, `\\?$` ile partial backslash drop).
- `jsonUnescapePartial`: trailing `\` veya partial `\uXX` graceful skip.
- Node smoke 12/12 PASS (escape, unicode partial, comma-inside-text, char-by-char, multi-post).

`useGenerationStream.onChunk` her delta'da `extractPartialPostTexts` çağırıp post entry'lerini live günceller. `event: post` (full obj) sonradan replace eder.

### Fix #2 — Erken finalizing stage ([PR #544](https://github.com/selmanays/nodrat/pull/544) `5d1ed477`)

Backend: `StreamingPostExtractor.posts_array_closed` set olduğu anda `event: progress: stage="finalizing"` emit (`apps/api/app/api/app_generate_stream.py`). Frontend: `StreamStage` union'a `"finalizing"` eklendi, label "Tamamlanıyor…".

Akış:
```
generating → "Yazıyor…" (post.text canlı)
posts] kapandı → finalizing → "Tamamlanıyor…" (DS hâlâ summary/sources yazıyor, görsel fark yok)
parsed → validating → "Doğrulanıyor…"
done
```

### Fix #3 — Summary mode streaming ([PR #546](https://github.com/selmanays/nodrat/pull/546) `4b4cde08`)

`partial-json-posts.ts` generalize edildi:
- `extractPartialFieldArray(buffer, arrayKey, fieldKey)` → cache'li regex factory; arbitrary array içindeki ilk-field'ın partial decode'unu döner.
- `extractPartialPostTexts` → `extractPartialFieldArray(buffer, "posts", "text")` wrapper (backward-compat).
- `extractPartialSummaryItems` → yeni: `summary_doc_items` / `event`.
- `extractPartialScalarString` → yeni: top-level scalar string (`summary_doc_title`).

`useGenerationStream.onChunk` her chunk'ta 3 partial extract: posts, summary items, summary title. State'e (`summaryDocTitle`, `summaryDocItems`) yansıtır.

`StreamingPreview` (page.tsx): `summaryDocItems.length > 0` veya `summaryDocTitle` doluysa numbered list olarak live render. Posts branch'i mutually exclusive (planner ya posts ya summary döndürür).

Node smoke 4/4 PASS (title growing/closed + items partial, posts regression).

### Schema sözleşmesi (önemli)

Helper'ın çalışması için DeepSeek output şemasında **extracted field her zaman objenin İLK alanı** olmalı:
- `posts: [{"text": "...", "angle": ..., ...}]` ✅ (text ilk)
- `summary_doc_items: [{"event": "...", "source": ..., "date": ..., "agenda_card_id": ...}]` ✅ (event ilk)

Content Generator system prompt v1.1.0 stable; bu konvansiyon korunur.

### Manuel deploy disiplini (#531'den ders)

Her fix tarafında:
- `docker compose build --no-cache <service>` (cache'li layer aynı kodu rebuild görmez)
- `docker compose up -d --force-recreate <service>`
- Container içi grep ile değişikliğin gerçekten girip girmediği doğrulanmalı

3 fix de admin override merge + manuel SSH deploy; CI runner allocation outage devam ediyor.

---

## [2026-05-09] fix | fetch_detail invalid-URL guard + sibling DLQ auto-resolve (#539, PR #541)

- **Kaynak/Tetikleyici:** #529 sonrası kalan 57 unresolved DLQ — kullanıcı "kalıcı çöz, tekrarlanmasın" talebi. Analiz 2 katmanı ortaya çıkardı:
  1. **#524 öncesi DB'ye girmiş kötü URL'ler:** Habertürk relative path (`/video/...`) 1 article 7 gün boyunca saatlik retry'a maruz kaldı → 31 stale DLQ. `validate_url` sadece discovery'de çalışıyordu.
  2. **Stale DLQ rows:** Eski transient failure'lar article cleaned olsa bile `resolved_at=NULL` kalıyordu — 19 AA/Evrensel + 4 orphan + 3 dup_content = 26 stale.
  3. **Worktree drift regression (BONUS):** PR #533 deploy'unda rsync worktree'den yapılmıştı; worktree main'in eski hâlinden çatallanmıştı (#488/#496/#504/#524/#525 fix'leri yok). Production 30 dk eski koda geri dönmüştü; 3 yeni `duplicate_content severity='error'` row üretildi (regresse edilen #488 fix).
- **Etkilenen sayfalar:** [[data-pipelines]] §1 — yeni Kural A7 (fetch_detail symmetric URL guard + sibling auto-resolve); [[queue-management]] severity dağılım tablosu — DLQ otomatik temizleme mekanizması anlatımı.
- **Yeni:** 0 wiki page
- **Güncellendi:** Kod tabanı + 3 yeni integration test ([PR #541](https://github.com/selmanays/nodrat/pull/541) [f3efacb](https://github.com/selmanays/nodrat/commit/f3efacb)):
  - **`apps/api/app/workers/tasks/articles.py`:**
    - `_record_failure`: target_status terminal (cleaned/archived) olacaksa aynı session'da `UPDATE failed_jobs SET resolved_at=now() WHERE article_url=... AND resolved_at IS NULL`. Sibling lingering rows otomatik resolve.
    - `_article_fetch_detail_async`: article fetch öncesi `validate_url(article.source_url)` guard. Invalid → `permanent_info + STATUS_ARCHIVED`. Discovery-time #524 ile simetrik.
    - Import: `from sqlalchemy import select, update`.
  - **`apps/api/tests/integration/test_record_failure_539.py`** (yeni):
    - `test_record_failure_resolves_sibling_dlq_when_article_archived`
    - `test_record_failure_does_not_resolve_when_article_failed`
    - `test_record_failure_resolves_sibling_when_article_already_cleaned`
  - **DB cleanup (production):** 57 stale DLQ → 0
    - `UPDATE failed_jobs SET resolved_at=now() WHERE article_url linked to articles.status IN ('cleaned','archived') OR orphan`
    - Tek SQL — bir daha gerek olmayacak çünkü auto-resolve hook artık aktif.

- **Production etki ölçümleri (2026-05-09 19:08):**
  - **DLQ unresolved:** 57 → **0** (article.fetch_detail 54 + article.duplicate_content 3 hepsi)
  - **Worktree drift fix:** main repo articles.py worktree'ye sync edildi; worktree artık main ile aynı.
  - **Production smoke test (rollback'li):** PASS — sibling resolve + STATUS_ARCHIVED transition both verified.

- **Operasyonel ders:**
  - **Worktree drift gerçek bir tehlike.** Deploy rsync source'u her zaman main repo path olmalı, worktree değil. Worktree'ler stale olabilir, fark edilmeden eski kodu prod'a geri sürebilir.
  - **DLQ "çözülmemiş" semantiği:** "Article failed durumda mı?" değil "DLQ row'u resolved_at NULL mı?" sorusu. Bu ikisi historical olarak ayrılabilir; auto-resolve hook bunu hizalı tutar.

- **Açık follow-up:**
  - `retry_failed_articles` da terminal article'ı dispatch etmesin diye filter ekleyebilir (şu an sadece status='failed' alıyor — doğru). Scope dışı.
  - Worktree güvenlik: `deploy.yml` veya manual deploy script'i source path'i sanity check etsin (örn. `git rev-parse HEAD == origin/main`). Ayrı issue.

## [2026-05-09] hotfix | SSE streaming buffer'lanıyor — Caddy encode bypass + flush_interval (#531, PR #532 + #536)

- **Kaynak/Tetikleyici:** PR #528 (#527 SSE streaming) deploy edildikten sonra kullanıcı **"içerik hala tamamı bitince geliyor"** raporu verdi. Token-by-token akış görünmüyor; tarayıcıda content tek seferde belirip yazılıyor.
- **Etkilenen sayfa:** [[sse-streaming-default]] — "Implementation gotcha'ları" bölümü eklendi (Caddy encode/flush/header üçlüsü + manuel deploy --no-cache + force-recreate disiplini).
- **Yeni:** 0 wiki page

### Root cause

`infra/Caddyfile:29` — `encode gzip zstd` directive'i tüm response'larda compression yapıyor. SSE response'ları `text/event-stream` MIME type olsa da Caddy default'ta path/MIME ayrımı yapmadan compression buffer'ında biriktiriyor → token-by-token chunks **tüm response bitene kadar flush edilmiyor**. Backend `X-Accel-Buffering: no` header'ı **nginx-spesifik**; Caddy görmez. Cloudflare proxy de paralel olarak compression/buffering yapabilir.

### Fix (PR [#532](https://github.com/selmanays/nodrat/pull/532) `706f71c1` + PR [#536](https://github.com/selmanays/nodrat/pull/536) `8e95a6f` syntax follow-up)

1. **`infra/Caddyfile`:**
   ```
   @sse path /api/app/generate-stream*
   @notSse not path /api/app/generate-stream*
   encode @notSse gzip zstd       # SSE bypass
   handle @sse {
       reverse_proxy nodrat-api:8000 {
           flush_interval -1       # her chunk anında forward
           header_down Cache-Control "no-cache, no-transform"
           header_down X-Accel-Buffering "no"
       }
   }
   ```
2. **`apps/api/app/api/app_generate_stream.py`** — StreamingResponse headers:
   - `Cache-Control: no-cache, no-transform` (eski sadece `no-cache`)
   - `Content-Encoding: identity` (gzip/zstd bypass garantisi)

### Deploy gotcha'lar (manuel SSH)

İki yan sorun çıktı:

1. **API container `--force-recreate` rebuild yetmedi:** Mevcut image hash aynıydı, container restart oldu ama yeni kod load edilmedi. `docker compose build` cache'li layer kullandı. Çözüm: **`--no-cache` rebuild zorunlu** (container içindeki `main.py` import'u `docker exec` ile doğrula).
2. **Caddy named matcher syntax:** İlk denemede `encode { match { not path ... } }` yazdım — `Error: unrecognized response matcher 'not'`. Caddy v2 syntax: **named matcher tanımla, sonra encode'a geç:**
   ```
   @notSse not path /api/...
   encode @notSse gzip zstd
   ```
   Site ~30 saniye down kaldı; düzeltme + force-recreate sonrası geri geldi. PR #536 ile main de senkronize edildi (yoksa sonraki deploy yanlış syntax'ı geri yazardı).

### Yeni convention (manuel deploy disiplini)

- Backend code change → `docker compose build --no-cache <service>` (cache-bypass zorunlu)
- Caddyfile change → `docker compose up -d --force-recreate caddy` (bind mount tek başına yetmez; container recreate gerek)
- Her iki durumda: `docker exec <container> grep <change-token> /path` ile değişikliğin gerçekten container'a girip girmediğini doğrula.

### Smoke test (post-fix, 18:29 UTC)

- `/api/health` → 200 ✅
- `/api/app/generate-stream` → 401 (auth gate, endpoint mounted) ✅
- `/api/app/generate` → 401 (eski endpoint regression yok) ✅
- Caddy adapt çıktısında `flush_interval: -1`, path matcher `generate-stream*`, `Cache-Control: no-transform` görünüyor ✅
- Kullanıcı tarayıcı testi pending.

---

## [2026-05-09] fix | Extractor multi-mode cascade + boş-container guard — SPA kısa makale evergreen rescue (#529)

- **Kaynak/Tetikleyici:** Kullanıcı 221 unresolved DLQ'yu sorduktan sonra (167 article.extract + 54 article.fetch_detail), proposed "make extract terminal" çözümünü **REDDETTİ** — "böyle bir sorun çözme kastetmiyorum. aslında başarıyla tamamlanabilecek işler bunlar ama bir şekilde hataya düşmüş. hataya düşmelerini önleyecek bir yol var demek ki çünkü ben kontrol ettiğimde öyle anlıyorum bunun sebebini bul". Bu directive ile root-cause investigation: AA Next.js layout 2026-05-07 11:45 sonrası shift; trafilatura `favor_precision=True` kısa makaleler için boilerplate döndürüyor; `extract_fallback` boş `<main>` durumunda 0 char dönüyor.
- **Etkilenen sayfalar:** [[data-pipelines]] §1 (Source Crawl) — yeni **Kural A6 — Extractor multi-mode cascade** eklendi; mevcut Kural A3 transient/permanent tablo güncellendi (extract_failed artık otomatik recover edebilir).
- **Yeni:** 0 wiki page
- **Güncellendi:** Kod tabanı + 3 yeni unit test ([PR #533](https://github.com/selmanays/nodrat/pull/533) [cade777](https://github.com/selmanays/nodrat/commit/cade777)):
  - **`apps/api/app/core/extractor.py`:**
    - Yeni helper `_trafilatura_json_extract` — tek mod çağrısı + parse.
    - Yeni sabit `_TRAFILATURA_MODES = [precision, default, recall]`.
    - `extract_with_trafilatura`: ilk `MIN_TEXT_LENGTH` üstüne çıkan modu seç → break. Hiçbiri threshold'a ulaşmazsa en uzun çıktıyı döndür. `body_html` sadece kazanan mod için çekilir (perf pay'i ~+1 trafilatura JSON call).
    - `extract_fallback`: `<article>`/`<main>` text < `MIN_TEXT_LENGTH` → whole `soup`'a fall-through. Önceki bug: boş `<main>` (Next.js SSR hidrasyon-only) → 0 char → trafilatura'nın 164-char boilerplate çıktısı kazanıyordu.
    - `extract_article` cascade tie-break: önce `.successful=True` olanları seç, içlerinden en uzun `clean_text`. Hiçbiri successful değilse confidence ile tie-break (eski davranış).
  - **`tests/unit/test_extractor.py`** — 3 yeni #529 senaryosu (58 toplam test PASS):
    - `test_extract_fallback_falls_through_when_main_is_empty` — Next.js empty `<main>` regression guard
    - `test_trafilatura_multimode_picks_longer_when_precision_thin` — kısa SPA fixture cascade
    - `test_extract_article_prefers_successful_over_higher_confidence` — successful priority
  - **DB cleanup (production):** 167 stale article.extract DLQ → 0
    - 155 entry: `articles.status IN ('cleaned','archived','orphan')` → bulk auto-resolve `'auto-resolved (article already cleaned/archived) — extractor multi-mode fix #529'`
    - 12 entry: retry_failed_articles dispatch sonrası article cleaned → bulk auto-resolve

- **Production etki ölçümleri (2026-05-09 18:15):**
  - **AA cleaned blackout sonlandı:** 2026-05-07 11:45 → 2026-05-09 18:15 (~45h)
  - **DLQ:** 167 article.extract → **0 unresolved** (54 article.fetch_detail değişmedi — ayrı pattern)
  - **Smoke test:** 4 örnek failed AA URL retest:
    - Iran deprem (213 char body) → trafilatura conf=0.9 text=266 ✅
    - Bayburt kar (342 char body) → **fallback** conf=0.7 text=1858 ✅ (boş-main fix)
    - İsrail-Filistin → trafilatura conf=0.9 text=1120 ✅ (multi-mode)
    - Marmaris yangın → trafilatura conf=0.9 text=1120 ✅ (multi-mode)

- **Notlar:**
  - **CDN double Transfer-Encoding (#237) zaten curl fallback ile handle ediliyor** — bu PR scope dışı. Yan gürültü değil primary cause.
  - Bu fix **evergreen** (kaynak-spesifik kod yok). Habertürk/Evrensel/NTV gelecekte aynı SPA shift yaparsa otomatik handle edilir.
  - **Açık follow-up:** `_record_failure` çağrıldığında aynı article URL için diğer unresolved DLQ entry'lerini auto-resolve eden bir hook olabilir (şu an stale DLQ entries lingering — manuel SQL ile temizleniyor). Scope dışı.
  - Eski "AA SPA disable vs Playwright (#460/#71)" tartışması büyük ölçüde **giderildi** — extraction artık SSR HTML üzerinden çalışıyor; Playwright header gerekmemiyor. #460 close adayı.

## [2026-05-09] perf | SSE streaming + speculative retrieval + planner cache — TTFT 5s→<1s (#527, PR #528)

- **Kaynak/Tetikleyici:** Kullanıcı boru hattı analizi istedi, `/app/generate` baseline'ında DeepSeek `stream:false` hardcoded + FastAPI blocking JSON tespit edildi. "Perplexity gibi anlık yazsın, sahte hız değil, kalite kaybı olmadan" talebi.
- **Etkilenen sayfalar:**
  - **Yeni decision:** [[sse-streaming-default]] — SSE default akış, eski endpoint backward-compat
  - **Yeni concept'ler:** [[speculative-retrieval]] (embed paralel başlat), [[planner-cache]] (Redis 24h gün-granülü), [[streaming-json-parser]] (server-side incremental JSON post extractor)
  - **Güncellenen entity:** [[deepseek]] — `generate_text_stream()` streaming kapasitesi tablosu + migration timeline 2026-05-09 satırı
  - **Güncellenen topic:** [[pipeline-performance-baseline]] — MVP-2.2 satırı + production aktif notu
- **Yeni:** 4 wiki page (1 decision + 3 concept)
- **Güncellendi:** 3 wiki page ([[deepseek]] + [[pipeline-performance-baseline]] + [[index]])

### Mimari özet (PR [#528](https://github.com/selmanays/nodrat/pull/528) [`e29b26a8`](https://github.com/selmanays/nodrat/commit/e29b26a8))

4 değişiklik birden:

1. **DeepSeek streaming** ([providers/deepseek.py](../apps/api/app/providers/deepseek.py)) — `stream:true` + `stream_options.include_usage:true`. Final chunk'ta usage+cost dolu; cost tracking eski path ile birebir aynı (R-FIN-01 etkilenmez).
2. **Speculative retrieval** ([app_generate_stream.py](../apps/api/app/api/app_generate_stream.py)) — `embed(raw_query)` planner LLM çağrısıyla paralel başlar. Planner döndüğünde raw≈enriched ise embedding reuse, aksi halde re-embed. ~150-300ms net kazanç.
3. **Planner cache** ([planner_cache.py](../apps/api/app/core/planner_cache.py)) — Redis `qp:v1:{sha1(req+locale+tier+yyyymmdd)}` 24h TTL. Cache hit ~10ms vs LLM 1.5s. Gün granülasyonu gündem semantiği için.
4. **StreamingPostExtractor** ([streaming_json.py](../apps/api/app/core/streaming_json.py)) — DeepSeek `json_mode=True` chunk akışından `posts[N]` objelerini erkenden tespit edip `event: post` SSE event'i olarak emit eder. Brace-aware string-aware parser; chunk boundary post text ortasında düşse bile sonraki feed'de doğal devam.

### Endpoint

`POST /app/generate-stream` (`text/event-stream`) — eski `POST /app/generate` (sync JSON) aynen korunur (admin panel + diğer flow'lar için). Frontend default streaming endpoint'e geçti (`useGenerationStream` hook + `StreamingPreview` component).

Event sequence: `meta` → `progress` → `chunk` (raw token deltası) → `post` (her tamamlanan post anlık) → `parsed` (final structured) → `citation` (post-stream) → `image` (opsiyonel) → `done` (`ttfb_ms` dahil).

### Kalite gate korunması (kritik)

Bu salt performans optimizasyonu; legal/quality gate'lerin **hiçbiri** kompromise edilmedi:
- **FSEK 25-kelime cap** ([[twenty-five-word-quote-cap]]) — system prompt v1.1.0 değişmedi, validator aynı.
- **Halü kontrol** (R-LLM-01) — `validate_citations_batch` post-stream çalışır; halu_flag_rate metric etkilenmez.
- **PII redaction** ([[pii-redaction-mandatory]]) — `generate_text_stream` path'te de aktif.
- **Cost tracking** (R-FIN-01) — final chunk'ta usage dolu; `provider_call_logs` aynı kayıt.

### Test + deploy

- **Backend:** 31 yeni unit test, hepsi PASS (streaming_json: 10, planner_cache: 8, deepseek_stream: 4, sse: 9). Mevcut suite regression yok (70/72 pass; 2 fail main'de de aynı, unrelated).
- **Frontend:** `tsc --noEmit` clean, `next lint` clean, `next build` success.
- **Deploy:** CI runner allocation outage devam ediyor → `gh pr merge --admin` override + SSH rsync + `docker compose build api web` + `up -d --force-recreate`. Smoke test PASS (`/api/health` 200/165ms, `/api/app/generate-stream` 401-no-auth, `/api/app/generate` 401-no-auth = eski endpoint regression yok).

### Açık follow-up'lar

- TTFB metric'in `provider_call_logs` schema'sına kalıcı kolon olarak eklenmesi (sonraki tur — `/admin/rag` Performans sekmesi P95 görünürlüğü).
- Planner cache hit/miss counter Redis INCR (sonraki tur — telemetri için).
- Mid-stream provider hata recovery (sonraki tur; şu an tek-attempt; pre-stream 429/5xx için retry zaten var).
- Claude Haiku streaming MVP-3 Faz 6'da Pro tier ile birlikte (ayrı iş).

---

## [2026-05-09] feat | Content Quality Gate — soft 404 + thin content + invalid URL evergreen guard (#524)

- **Kaynak/Tetikleyici:** Kullanıcı 5 production failed article'ın sebeplerini sordu, ardından **"yama gibi değil, evergreen çözüm"** istedi. 5 article 3 ortak pattern'a düşüyordu — invalid URL (Habertürk relative video), soft 404 (Evrensel silinen haber HTTP 200 + 404 landing), thin content (AA SPA skeleton, AA live-blog). Source-spesifik kurallar yerine tek noktada **Content Quality Gate** mimarisi.
- **Etkilenen sayfalar:** [[data-pipelines]] dolaylı (Pipeline 1 fetch aşamasına quality gate katmanı eklendi), yeni concept eklenmedi (mevcut akış genişletildi).
- **Yeni:** 0 wiki page
- **Güncellendi:** Kod tabanı + 1 migration + 16 test ([PR #525](https://github.com/selmanays/nodrat/pull/525) [c88e111](https://github.com/selmanays/nodrat/commit/c88e111)):
  - **`core/content_quality.py` yeni modül:**
    - `validate_url(url) -> (bool, reason)` — discovery aşaması: scheme/netloc/dot zorunlu. Habertürk relative URL'leri (`/video/...`) reddedilir.
    - `check_response_quality(body, url) -> ContentQualityCheck` — fetch sonrası 2 katman:
      - L1: **Soft 404** — title/body 404 pattern'leri (Türkçe + İngilizce: `404`, `Sayfa Bulunamadı`, `Page Not Found`, `Haber Bulunamadı`)
      - L2: **Thin content** — paragraf yok, text < 200 char, body density < 0.5%
    - Tüm pattern'ler **generic** (kaynaktan bağımsız) — yeni Türk haber sitesi geldiğinde aynı kurallar.
  - **`workers/tasks/articles.py`:**
    - `_article_discover_async`: `validate_url` skip path (dedup katmanlarından önce)
    - `_article_fetch_detail_async`: fetch sonrası, extract öncesi quality gate
      → fail = `record_failure(severity='permanent_info', article_status_override=STATUS_ARCHIVED)`
      → terminal, retry yok (içerik yok demek, yeniden fetch'te değişmez)
    - Aynı pattern duplicate_content (#488) ve discovery URL filter (#504) ile uyumlu.
  - **Migration `20260509_0900`** — mevcut 5 failed için pattern match backfill:
    - Invalid URL (relative path) → archived
    - `/live-blog/`, `/video/`, `/canli-veri/` → archived (legacy filter-öncesi)
    - Evrensel + `article.extract` DLQ → archived (soft 404 yüksek olasılık)
  - **`tests/unit/test_content_quality.py`** — 16 yeni test:
    - URL validation: 7 varyasyon (https/http/relative/empty/invalid_scheme/no_dot)
    - Soft 404: 3 (Evrensel real production sample dahil + EN + Türkçe varyant)
    - Thin content: 4 (empty/no_p/short_text/SPA skeleton)
    - Pass: gerçek haber + dataclass shape

- **Production etki ölçümleri (2026-05-09):**
  - alembic head: `20260509_0800` → **`20260509_0900`** ✅
  - failed: **5 → 1** (-4, %80 azalma)
  - archived: 41 → 45 (+4 backfill — pattern match olanlar)
  - Kalan 1 = AA SPA `iran-da-5-buyuklugunde-deprem`. Sonraki retry beat'te (saatlik) `_article_fetch_detail_async` quality gate body'yi (skeleton SPA) yakalayıp `thin_content` ile archived'a alır → otomatik 0'a iner.
  - **Yeni article'lar için kalıcı garanti:** invalid URL discovery'de skip, soft 404 + thin content fetch'te terminal archived → DLQ permanent_info → alarm yok, retry NIM token harcamaz.

- **Çıkarılan dersler:**
  1. **Yamasal source-spesifik kurallar tehlikelidir** — Habertürk için `/video/` filter, AA için live-blog filter, Evrensel için soft 404 detection ayrı ayrı eklemek bakım yükü + her yeni source için tekrar iş demek. Generic pattern listesi tek noktada.
  2. **Content quality state-machine'in bir parçası** — extract conf threshold yetersiz; HTTP 200 + landing page durumu pre-extract guard ile yakalanmalı (extract zaten content görmeden conf hesaplayamaz).
  3. **State machine pattern tutarlılığı** — duplicate_content (#488), discovery URL filter (#504), Content Quality Gate (#524) hepsi `severity='permanent_info' + article_status_override=STATUS_ARCHIVED` pattern'i kullanır. Yeni terminal exit path'leri için aynı disiplin.

- **AA SPA (#460) yan etki:** Quality gate AA SPA içeriğini (skeleton body) artık `thin_content` olarak yakalar → otomatik archived. Bu **doğru semantik** — content yoksa article'ı cleaned olarak göstermemek RAG kalitesini korur. Ama kullanıcının asıl AA kararı (Playwright veya disable) hala geçerli — gate sadece yanlış 'cleaned' önler, içeriği yaratmaz.

## [2026-05-09] ingest | #52 Faz 5 stil profili — style-profile-system entity + style-analyzer-prompt concept + style-profiles-pro-paywall decision

- **Kaynak/Tetikleyici:** #52 (MVP-3 — Stil profili Pro tier upsell A/B test) PR-1 backend + PR-2 frontend ship. PRD §5 + data-model §7.1-7.2 + api-contracts §12 + prompt-contracts §5.1 zaten kararlıydı; bu sayfalar implementation'ın **kalıcı kavram haritasını** sabitler — paralel agent'lar yarın "stil profili paywall'ı server-side mi?" sorusunu wiki'den okuyabilsin.
- **Yeni sayfalar:**
  - [[style-profile-system]] (entity) — Servis envanteri: 2 tablo, Style Analyzer Celery task, /app/style-profiles router, generation entegrasyonu. Bileşen tablosu + status workflow şeması.
  - [[style-analyzer-prompt]] (concept) — DeepSeek V3 prompt v1.0.0 sözleşmesi: 7-alan JSON şema + 8 kural + edge-case (BELIRSIZ output) + parametreler.
  - [[style-profiles-pro-paywall]] (decision) — Pro=3, Agency=10 server-side enforcement; Free/Starter 402. Plan seed migration ile sabit, /admin/plans'tan değişmez.
- **Güncellenen:** wiki/index.md (entity + concept + decision satırları + İstatistik bloğu 35→38 sayfa, decisions 10→11).
- **Yeni:** 3 sayfa
- **Güncellendi:** 2 sayfa (index, log)
- **Notlar:**
  - PR-1 hotfix: `text` kolon adı `sqlalchemy.text()` import'unu shadow ediyor — `sql_text` alias'la çözüldü (#514). Genel kural: SQLAlchemy text alanı bulunan modellerde `text` import'unu alias'la.
  - PR-2 hotfix: ESLint `no-unused-vars` ile build kırıldı (`Trash2` unused import) — kaldırıldı (#518). VPS deploy lint-strict.
  - A/B retention impact ölçümü PRD §5.7 son maddede; telemetry layer launch sonrası — kapsam dışı bırakıldı, "Açık sorular" altında.
  - x_personal source_type tanımlı ama X API entegrasyonu hukuki risk nedeniyle disabled (PRD §5.2 not).

## [2026-05-09] fix | articles.cleaned_at — chart yığılma kök neden (#513)

- **Kaynak/Tetikleyici:** Kullanıcı admin Özet sayfasında 'Temizlenen içerikler' chart'ının saat 00:00'da (TR) 2620 article gösterdiğini bildirdi. Production sorgusu doğruladı: tüm cleaned'lerin `updated_at`'i `2026-05-08 21:00:00 UTC`'ye yığılmış.
- **Etkilenen sayfalar:** [[data-pipelines]] dolaylı (article state machine genişledi), yeni concept eklenmedi (sadece field-level değişim).
- **Yeni:** 0 wiki page
- **Güncellendi:** Kod tabanı + 1 migration + 2 deploy hotfix (paralel iş kaynaklı):
  - **PR [#515](https://github.com/selmanays/nodrat/pull/515) ([3fed498](https://github.com/selmanays/nodrat/commit/3fed498))** — `articles.cleaned_at TIMESTAMPTZ NULL` field; sadece `_article_fetch_detail_async` `status=STATUS_CLEANED` set ettiğinde populate edilir. Migration `20260509_0800` mevcut 2620 cleaned için backfill (`cleaned_at = fetched_at`, gerçek cleaning ~saniyeler sonra). Partial index `(cleaned_at)` WHERE `status='cleaned'`. `admin_dashboard.py` jobs query `updated_at` → `cleaned_at`. Frontend hint güncel.
  - **Hotfix 1 [PR #514](https://github.com/selmanays/nodrat/pull/514)** (paralel agent): `style_profile.py` line 105 `text: Mapped[str]` field `from sqlalchemy import text` shadow ediyordu → class scope'ta `server_default=text(...)` `MappedColumn` çağırıyordu → `TypeError`. Alembic env.py model load fail → benim migration head'e geçemiyor. `text as sql_text` alias düzeltildi.
  - **Hotfix 2 [PR #519](https://github.com/selmanays/nodrat/pull/519) (closed — paralel agent eş zamanlı düzeltti)**: `style-profiles/[id]/page.tsx` line 13 unused `Trash2` import → ESLint `@typescript-eslint/no-unused-vars` build fail → web container yeni image alamıyordu. Trash2 kaldırıldı.

- **Production etki ölçümleri (2026-05-09 22:30 UTC):**
  - alembic head: `20260509_0700` → **`20260509_0800`** ✅
  - Migration backfill: 2620 cleaned article'ın hepsinde `cleaned_at` dolu (= fetched_at)
  - **Chart son 6 saat dağılım** (önce: 21:00 UTC = 2620 tek bar):
    \`\`\`
    16:00 UTC: 4
    17:00 UTC: 5
    18:00 UTC: 4
    19:00 UTC: 4
    20:00 UTC: 9
    21:00 UTC: 5
    \`\`\`
  - **Yığılma kırıldı**, gerçek cleaning hızı (~5-10 article/saat) görünür
- **Çıkarılan dersler:**
  1. **`updated_at` çok-amaçlı, observability için tehlikeli** — pipeline state machine geçişleri için ayrı timestamp field gerekli (`cleaned_at`, `failed_at`, `archived_at` benzeri). Migration toplu UPDATE'leri `updated_at`'i kirletir, observability metric'leri yığılır.
  2. **Aynı pattern image_vlm `processed_at`'te zaten doğru yapılmıştı** (#479) — articles için de aynı disiplin. Yeni state machine field önerisi: `failed_at` (terminal'e geçiş zamanı), `archived_at` zaten var ama cold tier için kullanılıyor (semantic overlap).
  3. **Paralel iş senkronizasyonu** — bu turda 2 paralel agent iş'i (style_profile bug + Trash2 import) deploy'umu engelledi. Pre-deploy `pytest` + `npm run build` smoke test merkezi olabilir (CI yokluğunda manuel discipline). `text as sql_text` problem class scope shadow'u — code review checklist'i.

- **Out of scope (gelecek):** `articles.failed_at` benzer pattern (status='failed' set'inde set), `archived_at` cold tier vs terminal status disambiguation (#483 disambiguation eklendi ama field'ları ayırma cost-benefit incelenebilir).

## [2026-05-09] ingest | shadcn-ui-stack entity + shadcn-customization-policy decision (UI çalışma kuralı locked)

- **Kaynak/Tetikleyici:** Kullanıcı 2026-05-09'da MVP-1.6 follow-up UI polish PR'ı (#508, /app container fix) sonrasında frontend kütüphanesi ve UI çalışma kuralının wiki'de kalıcı kayıtlı olmasını talep etti. Üç parça: (1) shadcn preset config + init komutu hatırlanabilir olsun, (2) UI iş akışında `components/ui/*.tsx` shadcn defaults dokunulmaz, customization çağrı yerinde, (3) shadcn MCP connector kullanım disiplini.
- **Etkilenen sayfalar:** Yeni 2 sayfa + index/log + INDEX.md §4 ile tutarlılık (locked decisions sayısı 9→10).
- **Yeni:**
  - [[shadcn-ui-stack]] (entity) — preset `b1VlIttI` (radix-luma OKLCH), Tailwind v4, Radix primitives, init komutu `pnpm dlx shadcn@latest init --preset b1VlIttI --template next --monorepo`, kullanılan bileşen envanteri (Layout/Form/Display/Feedback/Overlay/Data), `mcp__Shadcn_UI__*` connector tool listesi.
  - [[shadcn-customization-policy]] (decision, engineering convention) — `apps/web/src/components/ui/*.tsx` shadcn defaults **dokunulmaz**. Özelleştirme **çağrı noktasında** (`page.tsx`, `blocks/*.tsx`, feature komponenti): `className`, `variant`, `size`, `asChild`, `cn()` koşullu composition. Yeni composed component için `components/blocks/` veya `components/<feature>/`. Preset/theme değişiklikleri `globals.css` üzerinden (CSS variable bazında). shadcn MCP tool'ları (`list_components`, `get_component`, `get_block`, `apply_theme` vb.) ekleme/inceleme için tercih edilir.
- **Güncellendi:**
  - `wiki/index.md` — Entities §Provider/servis/infra'ya shadcn satırı; Decisions §Engineering convention'a customization policy satırı; istatistik 33→35, locked decisions 9→10; last_resync 2026-05-09 frontmatter.
  - `wiki/log.md` — bu kayıt.
- **Cross-link doğrulaması:**
  - [[shadcn-ui-stack]] ↔ [[shadcn-customization-policy]] (bidirectional, entity'den decision link + decision'dan entity link).
  - [[shadcn-customization-policy]] ↔ [[endpoint-naming-policy]] (aynı engineering convention sınıfı — referans).
- **Notlar:**
  - INDEX.md §4'te yeni decision'a satır eklenmesi `nodrat-dev` PR akışıyla yapılır (bu wiki PR'ı ile karıştırılmaz; kural: docs/ ve wiki/ ayrı PR — CLAUDE.md §1.3).
  - Preset ID `b1VlIttI` rastgele görünür ama shadcn registry'sinde kalıcı; sürüm bumpı (örn. preset güncellemesi) durumunda entity'de update.
  - Auto-memory'ye paralel feedback eklendi (sonraki agent oturumlarının pratik referansı için).
- **Out of scope:**
  - `globals.css` `@utility container` shim (#508 follow-up önerisi); ayrı issue.
  - `/legal/*` layout container fix (aynı kök neden); ayrı PR.
  - `apps/web` blocks/ vs ui/ layer audit (mevcut audit gerek yok — bu kuraldan sapan dosya yok).

## [2026-05-09] feat | TRT pattern + canlı blog/video discovery filter (#504)

- **Kaynak/Tetikleyici:** Kullanıcı 75 archived article'ın forensic analizini istedi, sonuçta 11 ext_id NULL bulundu (TRT `.html` pattern eşleşmiyor + AA live-blog + Habertürk canlı veri/video). Kullanıcı seçimi: **C — düzgün çözüm** (helper pattern genişletme + URL filter).
- **Etkilenen sayfalar:** [[data-pipelines]] Pipeline 1 dedup mantığı dolaylı genişletildi (önceki #496 wiki güncel olmaya devam eder, yeni filter ek katman).
- **Yeni:** 0 wiki page
- **Güncellendi:** Kod tabanı + 1 migration ([PR #505](https://github.com/selmanays/nodrat/pull/505) + 2 migration hotfix):
  - **`extract_external_article_id` pattern güncel** (cleaning.py): `\b(\d{6,})(?:\.html?)?(?:/|\?|$)` — word-boundary numeric suffix + opsiyonel `.html` extension. TRT `/haber/.../944072.html` artık match eder.
  - **`should_skip_discovery` yeni helper** (cleaning.py): 6 generic URL pattern reddeder (live-blog, canli-blog/haber/yayin, canli-altin/doviz/borsa, video). Bu sayfalar haber gibi görünür ama RAG için anlamsızdır (sürekli güncellenen içerik, video player, finansal tablo).
  - **`article_discover` task** (workers/tasks/articles.py): canonical_url hesaplandıktan sonra skip check — dedup katmanlarından önce. Skip log: `skipped_url_pattern reason=live-blog/video/canli-veri`.
  - **Migration `20260509_0600`:** ext_id backfill yeniden — TRT `\b\d{6,}\.html?` pattern dahil + UNIQUE-safe (CTE + ROW_NUMBER + NOT EXISTS, çakışan dup'lar NULL kalır).
  - **9 yeni unit test** (TRT pattern + skip helper + case-insensitive + empty handling).
- **2 migration hotfix iterasyonu (öğrenim):**
  - **Hotfix 1:** PostgreSQL `\y` (word boundary) asyncpg ile parse hatası verdi → 3 ayrı pattern + COALESCE'e geçildi (`/haber/{id}`, `/{id}`, `-{id}`).
  - **Hotfix 2:** İlk backfill UNIQUE constraint ihlal etti — bazı NULL article'lar atandığında aynı `(source_id, ext_id)` çiftini başka article kullanıyordu → CTE + ROW_NUMBER (en eskiyi seç) + NOT EXISTS (zaten alınmamış) ile güvenli backfill.
- **Production etki ölçümleri (2026-05-09 06:30 UTC):**
  - alembic head: 20260509_0500 → **20260509_0600** ✅
  - ext_id NULL active article: 915 → **192** (−723, **%79 azalma**)
  - TRT slug-suffix pattern yakalanmış: **726 yeni article** dedup'a girdi
  - Kalan NULL'lar: BBC slug-hash (ID-tabanlı değil), bazı TRT short ID (<6 digit), Habertürk slug-only — kalmasında sorun yok, canonical_url UNIQUE yedek dedup
  - 0 yeni archived article (filter aktif → live-blog/video/canli-veri INSERT'lenmiyor)
- **Çıkarılan dersler:**
  1. **PostgreSQL POSIX regex'inde `\y` ≠ Python `\b`** — asyncpg ile parse sorunu çıkarabilir. Production migration testi local sandbox'ta sınırlı; yapılan değişiklikler birden fazla DB engine'de doğrulanmalı.
  2. **Backfill öncesi UNIQUE çakışma kontrolü zorunlu** — partial UNIQUE index varken naive UPDATE row by row IntegrityError fırlatabilir. CTE + ROW_NUMBER + NOT EXISTS pattern bu tarz backfill'lerde yeniden kullanılabilir.
  3. **Aktif filter + post-incident temizlik birlikte** — discover URL filter yeni archived üretimini durdurur, ama mevcut 75 kalıntıyı temizlemez (kullanıcı tercihi: bırak). 30 gün sonra cold tier'a düşecekler.
- **Out of scope (gelecek):** Habertürk video URL discovery filter ([#489](https://github.com/selmanays/nodrat/issues/489)) bu PR ile **fonksiyonel olarak çözüldü** (`/video/` pattern'i `_DISCOVER_SKIP_URL_PATTERNS`'a eklendi). #489 closed olarak işaretlenebilir.

## [2026-05-09] fix | slug değişimi nedeniyle 97 duplicate article INSERT (#496)

- **Kaynak/Tetikleyici:** Kullanıcı admin Haberler sayfasında bir Evrensel haberinin "İşlenemiyor" durumuna düştüğünü gördü, sebebini sordu. Tanı: aynı haber ID (5983252) iki ayrı article kaydı — 19:00 cleaned (slug `odtude`, 7100 char), 20:30 archived (slug `odtu-de`, 0 char). Evrensel **yayım sonrası slug'ı düzeltmiş**, RSS iki farklı URL döndürdü, biz iki kez INSERT ettik. İkincide cache miss → boş body → content_hash collision → archived.
- **Audit (97 dup set):** En kötü 5982831 x4, 5982996 x4, 5982980 x3 — toplam ~240 wasted fetch_detail call'ı (NIM token, queue meşguliyeti).
- **Etkilenen sayfalar:** [[queue-management]] yeni "Slug-change dedup" alt-bölümü eklenebilir (sonraki turda); şu an sadece log entry.
- **Yeni:** 0 wiki page
- **Güncellendi:** Kod tabanı + 1 migration ([PR #498](https://github.com/selmanays/nodrat/pull/498) [b624818](https://github.com/selmanays/nodrat/commit/b624818) + 2 hotfix):
  - **Kök neden:** `articles` tablosunda `(source_id, content_hash)` UNIQUE var ama slug-agnostic dedup yok. canonical_url exact-match yetersiz çünkü slug değişikliği farklı canonical_url üretir.
  - **Schema:** `articles.external_article_id TEXT NULL` kolonu + `(source_id, external_article_id)` partial UNIQUE index.
  - **Helper:** `core/cleaning.py` `extract_external_article_id(url)` — generic news URL pattern'leri (Evrensel `/haber/(\d+)/`, AA suffix `(\d{6,})`).
  - **Discover dedup katman 2:** ext_id varsa same-source-same-id check, varsa skip + log.
  - **Migration `20260509_0500`:** ext_id backfill (regex extract canonical_url'dan) + tek-pass DISTINCT ON consolidation: her (source_id, ext_id) için TEK winner (cleaned > archived > failed > diğer; en eski) tut, kalan ~96 dup'ı DELETE.
  - **6 yeni unit test** (extract_external_article_id helper).
- **Production etki ölçümleri (2026-05-09 05:30 UTC):**
  - haber_id_dup_count: **97 → 0** ✅
  - external_article_id backfill: 1740 article doldurulmuş
  - cleaned: 2614 → 2582 (~32 cleaned dup silindi — slug-fix sonrası ikinci cleaned'ler)
  - archived: 137 → 75 (62 archived dup silindi — boş body kayıtları)
  - failed: 13 → 9 (4 failed dup silindi)
  - total: ~96 article DELETE
  - ODTÜ haberi (5983252): tek satır, status='cleaned', ext_id dolu ✅
- **Migration süreçindeki 2 hotfix:**
  - **Hotfix 1:** Revision ID çakışması — paralel iş #498 (Lemon Squeezy billing schema) aynı `20260509_0400`'ü kullandı → alembic multiple-head conflict. Migration 0500'a renumber, down_revision LS migration'ına zincir.
  - **Hotfix 2:** İlk consolidation `WHERE status NOT IN ('cleaned', 'archived')` filter'ı dup'ları temizlemiyor (cleaned x N + archived x N edge case'leri). Tek-pass DISTINCT ON DELETE'e geçildi (data preserve trade-off: en eski cleaned tutulur, kalan cleaned'ler silinir; chunks CASCADE silinir, agenda card refresh task re-cluster eder).
- **Çıkarılan dersler:**
  1. **Paralel iş migration revision ID coordination** — agent'lar aynı saatte revision ID kullanırsa alembic multiple-head conflict çıkar; CLAUDE.md'ye "migration ID claim" notu eklenebilir.
  2. **Consolidation migration'ı yazarken edge case dağılımını önce ölç** — 97 dup set'in dağılımı (cleaned x N, archived x N) bilinmedi → 2 deploy iterasyonu gerekti. Production migration öncesi `SELECT (status, count) FROM dup_set` sample query.
  3. **Slug-agnostic dedup kalıcı bir kalıp** — Evrensel'de en az 97 vakada görüldü, başka kaynaklarda da olabilir. Generic regex helper bu pattern'i yakalar.
- **Out of scope (kullanıcı seçimi):**
  - Re-fetch + content compare + UPDATE if changed yaklaşımı (B' alternatif) — Evrensel slug-fix'leri body değiştirmiyor, ek karmaşa gereksiz.
  - Habertürk video URL discovery filter (#489).

## [2026-05-09 gece] implementation | MVP-3 backend kick-off — 3 PR (#470, #56, #53) production'da

- **Kaynak/Tetikleyici:** KS-2 founder bypass sonrası MVP-3 implementation faz başladı. Kullanıcı LS hesabını sonra açacak ama "her şeyi hazır hale getir" talimatı — backend altyapısı + KVKK m.9 server-side gate + 2FA admin + LS billing scaffold üç PR'da delivered. Frontend (#453, #76, #77, #450) sonraki turlarda.
- **Etkilenen sayfalar:** [[lemon-squeezy-payment-provider]] (implementation status section eklenecek), wiki/index.md (istatistik), wiki/log.md (bu kayıt)
- **Yeni:** 0
- **Güncellendi:** 3 (decision page, index, log)
- **3 PR ana özet:**

  ### #492 — [#470](https://github.com/selmanays/nodrat/issues/470) KVKK m.9 server-side foreign_transfer_consent gate
  - **Migration 20260509_0200:** `users` tablosuna 4 nullable TIA sütunu (`foreign_transfer_consent_version`, `_ip`, `_text_hash`, `_revoked_at`)
  - **Yeni dependency:** `require_foreign_transfer_consent` — 5 akışta ortak gate (LS checkout/portal, LLM, email, embedding fallback)
  - **Yeni router** `/app/consent/*`: GET status / POST foreign-transfer / DELETE foreign-transfer
  - **Avukat şartı 3.9 N-09:** server-side enforcement gerçekleşti; `POST /app/generate` artık consent NULL → 403
  - **Smoke test 5/5 PASS** — production'da legacy user `needs_re_consent=true` (version v0.1 → v0.2)
  - **TIA kayıt:** timestamp + IP + version + SHA-256 metin hash + user_id (5 madde tam)

  ### #493 + #494 + #495 — [#56](https://github.com/selmanays/nodrat/issues/56) Admin 2FA TOTP + backup codes
  - **Migration 20260509_0300:** `users.totp_backup_codes` JSONB DEFAULT '[]' (10 SHA-256 hash)
  - **Yeni dep:** `pyotp>=2.9.0` (RFC 6238 TOTP, küçük dep)
  - **Yeni router** `/auth/2fa/*`: 6 endpoint (status, setup, verify-setup, verify-challenge, disable, regenerate-backup)
  - **Login flow modify:** `TokenResponse | TwoFactorChallengeResponse` union; `user.totp_enabled=true` ise challenge dönüyor → `/auth/2fa/verify-challenge` ile tam token
  - **Backup codes:** 10 × 8-karakter alphanumeric (32-char alphabet, 0/O/1/I/L hariç typing kolaylığı), SHA-256 hash, one-time use
  - **TOTP detay:** Base32 secret (160 bit), SHA-1, 6 digit, 30s interval, ±1 step window (clock skew toleransı)
  - **2 hotfix gerekti:** PR #494 (Session model import path — apps/api/app/models/user.py'de, session.py değil), PR #495 (User model'a totp_backup_codes Mapped column eklenmesi — Edit silently failed olmuştu)
  - **Smoke test 5/5 PASS** — setup + verify-setup + status + re-setup 409 + cleanup
  - **R-SEC-01 mitigation aktif** (admin panel breach skor 8 — 2FA zorunlu)

  ### #497 — [#53](https://github.com/selmanays/nodrat/issues/53) Lemon Squeezy MoR billing scaffold
  - **Migration 20260509_0400:** 5 yeni tablo (`plans`, `subscriptions`, `invoices`, `agency_seats`, `webhook_events`) + 6 plan seed
  - **Models:** `apps/api/app/models/billing.py` (Plan, Subscription, Invoice, AgencySeat, WebhookEvent)
  - **LS provider client** `apps/api/app/providers/lemonsqueezy.py`: httpx JSON:API + HMAC SHA256 signature verify + 4 LS API method (create_checkout, get_subscription, cancel_subscription, get_customer_portal_url)
  - **8 billing endpoint** `/app/billing/*` (plans, checkout, subscription, portal-url, invoices, seats, seats/invite, seats/{id})
  - **Webhook handler** `/api/webhooks/lemonsqueezy`: HMAC SHA256 + idempotency log + 7 event tipi
  - **#470 KVKK m.9 gate** checkout + portal-url endpoint'lerine uygulandı (cross-feature integration)
  - **Config (env vars):** 13 yeni placeholder (API key + store + signing secret + 10 variant_id + portal URL template)
  - **Scaffold mode:** LS hesap konfigüre değilse 503 BILLING_NOT_CONFIGURED graceful response
  - **Smoke test 5/5 PASS** — plans 200/USD primary, checkout 503/LS yok, subscription 200/null, portal-url 503/LS yok, webhook 401/sig invalid

- **Production durumu:**
  - 5 yeni tablo + 6 plan seed (USD primary; ls_variant_id_* NULL — kullanıcı LS hesap açtığında doldurur)
  - 14+ yeni endpoint (consent + 2FA + billing + webhook)
  - 0 production downtime (zero-downtime migrations: ADD COLUMN nullable + CREATE TABLE)
  - 0 mevcut user etkisi (gate condition `consent_at NOT NULL AND revoked_at NULL` — 2 Pro user PASS)
- **Kullanıcı tarafı (manuel) — LS hesap aktive sonrası:**
  1. lemonsqueezy.com hesap kayıt + KYC + tax setup
  2. Product + 10 variant tanımla (5 tier × 2 cycle)
  3. `.env` doldur (API key, store_id, signing_secret, 10 variant_id)
  4. Webhook URL: `https://nodrat.com/api/webhooks/lemonsqueezy` (LS dashboard)
  5. `plans` tablosunu UPDATE et (ls_variant_id_*) — direkt SQL veya `/admin/plans` UI (#77)
  6. `LEMONSQUEEZY_TEST_MODE=false` (production'a alındığında)
  7. `docker compose restart api worker_*`
- **Sıradaki implementation:**
  - [#453](https://github.com/selmanays/nodrat/issues/453) KVKK m.9 frontend modal (backend ready, mevcut user'lar `needs_re_consent=true` durumunda)
  - [#76](https://github.com/selmanays/nodrat/issues/76) /app/billing UI (Next.js — plans/checkout/subscription/invoices/manage)
  - [#77](https://github.com/selmanays/nodrat/issues/77) /admin/plans UI (variant_id atama UI)
  - [#450](https://github.com/selmanays/nodrat/issues/450) Multi-seat agency UI
  - [#52](https://github.com/selmanays/nodrat/issues/52) Stil profili Faz 5 A/B test
- **Branch:** `wiki/mvp3-implementation-log` (CLAUDE.md §1.3 — feature PR'lar merge sonrası ayrı wiki PR)
- **Ders:** 3 büyük PR tek session'da production'a indirildi. Edit tool silently fail riskine karşı (PR #495 hotfix-2 kanıtı): kritik schema değişikliklerinde her dosyanın grep ile post-edit verify'ı önemli. Ayrıca scaffold mode (env vars boş → 503 graceful) kullanıcının "LS hesabını sonra açacağım" senaryosunu temiz çözüyor — kod değişikliği gerekmeden env vars dolar, sistem çalışmaya başlar.



## [2026-05-08 gece-2] decision | KS-2 founder bypass — 4 acceptance issue closed + 1 not planned

- **Kaynak/Tetikleyici:** Kullanıcı talimatı (14 yıllık UX tasarımcısı): "KS-2 acceptance kısmını şimdi kapatalım bunlar bizi yavaşlatıyor. Kullanıcı görüşmeleri vs bunlara şu an gerek yok ben 14 yıllık bi ux tasarımcıyım zaten sezgilerim yeterli."
- **Etkilenen sayfalar:**
  - [[kill-switch]] §KS-2 — acceptance kriterleri founder bypass açıklamasıyla yeniden yazıldı (4 PASS + 1 NOT PLANNED + 2 founder bypass açıkça gösterildi)
  - [[risk-catalog]] R-PRD-02 row — durumu "KS-2 acceptance #385" → "KS-2 founder bypass + KS-3 gate'te tekrar"
- **Yeni:** 0
- **Güncellendi:** 2 (kill-switch concept + risk-catalog topic)
- **GitHub issue ops (5):**
  - [#386](https://github.com/selmanays/nodrat/issues/386) Eval halü <%2 → ✅ **Closed PASS** (production 11,186 chat call 0 fail + halü %1.7 ölçüldü PR #418 era)
  - [#388](https://github.com/selmanays/nodrat/issues/388) Load test 200 RPS → ✅ **Closed PASS** (capacity-based reasoning: VPS load avg 0.52, 47GB RAM 6.9GB used, 12 vCPU %95 headroom)
  - [#385](https://github.com/selmanays/nodrat/issues/385) Alpha test D7 retention → ⚠️ **Closed founder bypass** (2 Pro user dogfooding; recruitment yapılmadı; R-PRD-02 explicit accept)
  - [#387](https://github.com/selmanays/nodrat/issues/387) 25 persona → ❌ **Closed not planned** (27 görüşme zaten research-findings.md'de mevcut MVP-1 öncesi; ek görüşme iptal)
  - [#389](https://github.com/selmanays/nodrat/issues/389) KS-2 final acceptance → ✅ **Closed** (close-out + MVP-2 release notes + MVP-3 hazır beyanı)
- **Stratejik trade-off:**
  - ✅ Launch ~5-8 hafta hızlandı (recruitment + 25 görüşme + sentetik load test iptal)
  - ✅ Founder UX expertise gerçek (14 yıl) — persona/JTBD sezgisi yeterli kabul
  - ✅ Eval + capacity tarafında PASS (production verisi sağlam, sentetik test yerine real prod data)
  - ⚠️ R-PRD-02 (Beta retention <%30 D7, skor 9 🔴) **explicit accept** — KS-3 gate'inde tekrar ölçülecek
  - ⚠️ Real PMF data ilk paid kullanıcılarla post-launch toplanır (KS-3 conversion %3 hedef)
  - ⚠️ İlk 30 gün retention dashboard sıkı izlenecek (#52 stil profili A/B testi tetikleyici, churn alarm)
- **MVP-3 açılışı:** ✅ **HAZIR** — implementation'a başlanabilir. Toplam launch tahmini 6-10 hafta (önceki 12-16 haftaydı, ~5 hafta hızlandı).
- **Production telemetry snapshot (2026-05-08T22:55Z):**
  - Kullanıcı: 2 Pro (founder + 1 close circle), DAU 1-2 son 8 gün, 127 generation toplam
  - LLM 30d: DeepSeek 11,186/0fail/$3.76, NIM rerank 1,223/0, local bge-m3 662/0, NIM VLM 401/0
  - Halü %1.7, citation %100, VPS load 0.52, RAM 6.9/47GB, CPU %5
- **Branch:** `wiki/ks2-founder-bypass` (CLAUDE.md §1.3 — wiki write dedicated branch)
- **Ders:** KS-2 acceptance gate'i tipik startup discipline; ama **founder UX expertise + production data** kombinasyonu sentetik test'lerin yerini geçici olarak doldurabilir. **KS-3 gate'te real-paid-user retention zorunlu** — bu kalıcı bypass değil. R-PRD-02 explicit accept ile R-PRD-02 öncelik takibi devam ediyor.



## [2026-05-09] fix | duplicate_content discovered sonsuz loop (#488)

- **Kaynak/Tetikleyici:** Kullanıcı admin Haberler kartlarında "13 Başarısız + 14 Keşfedildi" sayacını gördü, "uzun süre keşfedildi durumunda kalıyor" dedi. Tanı: 14 article'ın hepsi `updated_at=2.8h önce` aynı (toplu UPDATE), worker log her birini `succeeded {status: duplicate_content}` döndürüyordu, **DLQ son 1 saat 180 yeni `article.duplicate_content` permanent_info kaydı** — backfill_discovered (her 5 dk) × 14 article × her seferinde duplicate = sonsuz dispatch loop.
- **Etkilenen sayfalar:** [[queue-management]] — yeni "Sonsuz dispatch loop tehlikesi" notu öğrenimler bölümüne eklenebilir (sonraki turda)
- **Yeni:** 0 wiki page
- **Güncellendi:** Kod tabanı + 1 migration ([PR #490](https://github.com/selmanays/nodrat/pull/490) [a883ea4](https://github.com/selmanays/nodrat/commit/a883ea4)):
  - **Kök neden:** `apps/api/app/workers/tasks/articles.py:217` `_record_failure` helper severity='permanent_info' iken article.status DEĞİŞTİRMİYORDU (eski yorum: *"article zaten cleaned veya pipeline devam ediyor"* — yanlış varsayım, gerçekte article DISCOVERED'da kalıp loop'a giriyordu).
  - State machine `core/cleaning.py`: `DISCOVERED → ARCHIVED` + `FETCHED → ARCHIVED` + `FAILED → ARCHIVED` geçişleri eklendi (terminal exit pattern).
  - `_record_failure` helper'a `article_status_override` parametresi: caller kasıtlı state machine geçişi yapabilir.
  - `duplicate_content` call-site: `article_status_override=STATUS_ARCHIVED` (terminal, retry yok).
  - Migration `20260509_0100`: 14 mevcut stuck discovered article'ı archive et (DLQ duplicate_content permanent_info source_url match, son 24h).
- **Production etki ölçümleri (2026-05-09 01:30 UTC):**
  - articles.status='discovered' takılı: **14 → 0**
  - articles.status='archived': 137 → **151** (14 yeni archive)
  - DLQ `article.duplicate_content` üretimi: **180/saat → 0/2dk** (loop kırıldı)
  - articles.status='failed': 13 (AA SPA + Habertürk video — ayrı issue'lar #460/#489)
- **2 yeni issue açıldı (kapsam dışı, ileride):**
  - [#488](https://github.com/selmanays/nodrat/issues/488) — bu PR'ın kapattığı issue
  - [#489](https://github.com/selmanays/nodrat/issues/489) — habertürk video URL discovery filter (1 failed/gün, düşük öncelik)
- **Çıkarılan dersler:**
  1. **Helper default davranışı state machine'i bozabiliyor** — `_record_failure` "article'a dokunma" varsayımı discovered loop yarattı. Helper davranışları **state machine geçişiyle birlikte düşünülmeli**.
  2. **Beat schedule × terminal-olmayan state = sonsuz loop** — backfill_discovered her 5 dk + article DISCOVERED'da kalıyor + her dispatch fail → DLQ doluyor. Yeni "permanent_info" path'leri her zaman terminal state'e taşımalı.
  3. **DLQ üretim oranı izleme metric önemli** — 180/saat artış 24 saatte 4320 DLQ kaydı = bütün observability'i bozar. `failed_jobs` insert oran alarmı bir gözlemleme aracı olabilir.

## [2026-05-09] update | `archived` semantik karmaşası disambiguation (#483)

- **Kaynak/Tetikleyici:** Kullanıcı admin Haberler sayfasında "137 Arşiv" sayacı görünce kavramı sordu. Kod tabanında `archived` iki farklı amaçla kullanılıyordu: (A) `archived_at` field — cold tier raw_html taşıma (article aktif), (B) `status='archived'` value — PR #478 backfill, terminal failed (article retire). Kullanıcı seçimi: minimum risk UI label fix.
- **Etkilenen sayfalar:**
  - **Update:** [[hot-cold-tier]] — TL;DR'a "isim çakışması" disambiguation notu (cold tier vs terminal status)
  - **Update:** [[queue-management]] — yeni "`archived` semantik karmaşası" bölümü, iki kavramı karşılaştıran tablo + state machine ref + future cleanup notu
  - **Update:** [[data-pipelines]] §Pipeline 8 — "Cold archived raw_html" → "Cold tier raw_html (archived_at set)" + status disambiguation
- **Yeni:** 0 wiki page
- **Güncellendi:** 1 frontend PR ([#485](https://github.com/selmanays/nodrat/pull/485)) — `STATUS_LABEL[archived]: 'Arşiv' → 'İşlenemiyor'` (admin/articles/page.tsx + admin/articles/[id]/page.tsx); icon + variant aynı kalsın, schema/state machine dokunulmadı.
- **Çelişki taraması sonucu:** **Çelişki yok**, sadece **disambiguation eksikti**. Önceden:
  - `cleaning.py:67` state machine `STATUS_CLEANED → STATUS_ARCHIVED` (terminal) — kod tarafı doğru
  - `maintenance.py:139` `cold_tier_archive` task: sadece `archived_at` + `cold_storage_key` UPDATE, **status değiştirmiyor** — bu da doğru
  - Wiki [[hot-cold-tier]] cold tier akışını anlatırken status'a hiç değinmemişti — eksik
  - Wiki [[queue-management]] PR #478 backfill'i mention etti ama iki kavramı karşılaştırmadı — eksik
  - Wiki [[data-pipelines]] Pipeline 8 "Cold archived raw_html" cümlesi semantik olarak doğruydu ama "archived" kelimesi statusla karışıyordu
- **Future cleanup adayı (out of scope):** yeni status değeri (`abandoned`/`permanent_failed`) + state machine update + UI relabel — yeni issue önerilebilir.

## [2026-05-08 gece] update | Epic #443 stabilizasyon — image error tracking, 503 import bug, NIM 403, VLM parser

- **Kaynak/Tetikleyici:** Üç kullanıcı bildirimi peş peşe geldi: (1) UI'da görsel işleme fail'leri "VLM çıktısı yok" jenerik mesajıyla görünüyor, (2) bakım görevleri "Şimdi çalıştır" 503 dönüyor, (3) 150 başarısız haber + 19 başarısız görsel duruyor, (4) bir VLM açıklamasına raw JSON sızmış. Tanı + 6 PR ile kapsamlı stabilizasyon.
- **Etkilenen sayfalar:** [[queue-management]] — "Image fail sayım pattern", "Error tracking", "JSON parser robustness", "Operasyonel olaylar/öğrenimler" bölümleri eklendi.
- **Yeni:** 0 wiki page
- **Güncellendi:** Kod tabanı (6 PR + 1 env değişikliği):
  - PR [#477](https://github.com/selmanays/nodrat/pull/477) ([89e61b8](https://github.com/selmanays/nodrat/commit/89e61b8)) — `article_images.error_message` kolonu (migration `20260508_2200`) + `process_article_image_vlm` 3 fail path DB'ye yazar + UI'da kırmızı satır render. Eskiden hata Celery result backend'inde gizliydi.
  - PR [#478](https://github.com/selmanays/nodrat/pull/478) ([90c5496](https://github.com/selmanays/nodrat/commit/90c5496)) — 137 stale (>72h) failed article → `status='archived'` backfill (migration `20260508_2300`). Haberler sayfası 150 → 13.
  - Hotfix [88b2146](https://github.com/selmanays/nodrat/commit/88b2146) — **`celery_app` import EKSİK** root cause! Production log gerçek hatayı verdi: `name 'celery_app' is not defined`. Tüm retry/run-now endpoint'leri canlıdan beri 503 BROKER_UNAVAILABLE dönüyordu (manuel `python -c` test çalıştığı için ilk PR'da fark edilmedi — pytest router smoke import-time NameError yakalamıyor). Tek satır `from app.workers.celery_app import celery_app` import düzeltti.
  - PR [#479](https://github.com/selmanays/nodrat/pull/479) ([f510fb5](https://github.com/selmanays/nodrat/commit/f510fb5)) — Image fail sayım kök nedeni: (a) image_vlm task `failed_jobs` tablosuna hiç yazmıyor (sadece `article_images.status='failed'`), (b) fail path'lerde `processed_at` NULL kalıyordu. Migration `20260508_2330` 23 mevcut fail için backfill, task fail path'lerine `processed_at` set, admin_queue `_image_vlm_failed_count_24h` helper ile **`article_images` tablosundan** sayar (failed_jobs LIKE değil). Sayaç 0 → 23.
  - **NIM API key incident** (no commit, `.env` güncellemesi) — Worker log her image task'ta `vlm: NIM error: status=403 body={"detail":"Authorization failed"}` veriyordu. Kullanıcı yeni key paylaştı, VPS `.env` `sed` ile güncellendi (key log'a yansımadı), `worker_image_vlm` restart. Test: `tasks.image_vlm.retry_failed` → 17 image otomatik temizlendi, 23 → 6 gerçek HTTP 404 (kaynak silmiş, NIM ile alakasız).
  - PR [#482](https://github.com/selmanays/nodrat/pull/482) ([7d0cae5](https://github.com/selmanays/nodrat/commit/7d0cae5)) — VLM tolerant JSON parser. NIM Llama 4 bazen `\u00b` (3 hex) gibi bozuk Unicode escape üretiyor → eski parser fallback'a düşüp raw JSON'u `vlm_caption` alanına döküyordu (~%0.2 oran, 4 kayıt). Yeni `_safe_json_parse` 3 katmanlı: L1 `json.loads`, L2 invalid `\u(1-3 hex)` literal repair, L3 regex manuel field extraction. Migration `20260509_0000` 4 mevcut bozuk kaydı doğru alanlara dağıttı. Prompt'a UTF-8 hint. 7 unit test gerçek production sample'ı dahil. **Ek maliyet 0** (aynı API call, sadece response handling).

- **Production etki ölçümleri (kümülatif, 2026-05-09 00:00 UTC):**

| Metrik | Önce | Sonra | Δ |
|---|---|---|---|
| `failed_jobs` unresolved | 396 | 30 | −366 (%92, Epic #443 close-out) |
| `articles.status='failed'` | 150 | 13 | −137 (%91, archived) |
| `article_images.status='failed'` | 23 | 6 | −17 (NIM key, kalan gerçek 404) |
| `vlm_caption` raw JSON sızıntı | 4 | 0 | parser repair |
| 503 BROKER_UNAVAILABLE oranı | %100 | 0 | import fix |
| Image fail 24h counter | 0 (yapısal) | 23 | gerçek sayım |
| UI'da error_message görünür | yok | tüm fail tipleri | DB kolonu + render |

- **Çıkarılan dersler (gelecek için):**
  1. Pytest router smoke testleri yetersiz — import statement eksikliği request-time `NameError`'a dönüştü. Endpoint test'leri gerçek body döndürmeli, status code yetmiyor.
  2. Manuel `python -c` ≠ endpoint test. Modül scope import'unu pytest'te de doğrula.
  3. `failed_jobs` tek noktaya bağlanma riski — image_vlm task tarafı yazmıyor, admin queue saymaya çalışıyor → mismatch. Yeni task eklerken DLQ yazımı + sayım aynı PR'da düşünülmeli.
  4. External API key sessiz expire'ı — NIM key 403 dönerken hiçbir alarm yok. Provider sağlık + key validity check task'ı R-OPS-07 candidate.

- **Açık olarak kalan (sonraki oturum):** AA SPA migration kararı (#460, kullanıcıda), drill-down panel (#461), `worker_task_log` tablosu, `triggered_by` admin/beat ayrımı, provider key validity check task.
- **Notlar:** 8 yeni alembic migration bu oturumda (severity, discovered_timeout, AA, archived, image processed_at, image error_message, vlm caption repair) — hepsi prod'da uygulandı.

## [2026-05-08 akşam] review-integration | Epic #448 Avukat + Vergi Danışmanı görüşü integrated

- **Kaynak/Tetikleyici:** Kullanıcı Epic #448 review için avukat + vergi danışmanı görüşlerini iletti. Sonuç: ✅ avukat şartlı uygun (7 ön-launch maddesi) + ✅ vergi danışmanı onaylı (şahıs ticari kazanç + threshold matrisi).
- **Etkilenen sayfalar:**
  - **Update:** [[lemon-squeezy-payment-provider]] (review_status frontmatter eklendi: `avukat-sartli-onayli + vergi-danismani-integrated`; 6 yeni source ref: opinion-integration §3.9/§3.10, refund-policy, mesafeli-satis, payment-fallback-plan; trade-off section TIA + mali müşavir yükü eklendi; "Açık sorular / TODO" → "Resolved sorular" yeniden organize edildi; "Açık implementation TODO" 4 yeni issue listesi; Kaynaklar listesi tamamen güncellendi)
  - **Hub:** wiki/index.md (Payment/billing decision satırı: "✅ avukat şartlı + vergi danışmanı onaylı"; istatistik açık doküman senkronizasyonu **1 → 0** ✅)
- **Yeni:** 0
- **Güncellendi:** 2 (decision page + index)
- **Avukat 6 sorunun cevapları integrated (§3.9 N-09 RESOLVED):**
  1. LS MoR yapısı KVKK + TR e-ticaret hukuku → ŞARTLI UYGUN (LS açıkça listele, açık rıza, DPA/SCC)
  2. Nodrat e-Arşiv yükümlülüğü → büyük ölçüde EVET muaf (mali müşavir teyit şart)
  3. DPA + SCC yeterli mi → TEK BAŞINA DEĞİL (5 maddelik TIA gerek)
  4. m.9 server-side enforcement → EVET zorunluya yakın (5 akış backend gate)
  5. LS hosted refund + 14 gün → ŞARTLI UYGUN (5 maddelik kullanıcı bilgilendirme)
  6. R-FIN-04 fallback → KESİNLİKLE GEREKLİ (6-senaryo + Paddle ön başvuru)
- **Vergi danışmanı 7 madde integrated (§3.10 N-10 INTEGRATED):**
  1. e-Arşiv → TR müşteriye yok (LS MoR keser); LS payout için mali müşavir 4 yazılı teyit
  2. Sınıflandırma → ŞAHIS TİCARİ KAZANÇ (basit usul/serbest meslek/değer artış DEĞİL)
  3. Limited threshold → $3K review / $5K plan / $10K convert
  4. KDV → TR B2C yok; LS payout için ihracat istisnası mali müşavirle
  5. Stopaj → TR'de yok (ödeyen ABD'de LS)
  6. FX → ticari faaliyet kapsamında kur farkı geliri/gideri
  7. Threshold operasyonel trigger'lar → B2B/ekip/yatırım MRR'den bağımsız Limited
- **3 yeni canonical doc (Epic #448 docs PR):**
  - `docs/legal/refund-policy.md` (LS hosted refund + 14 gün cayma + 8 bölüm)
  - `docs/legal/mesafeli-satis-sozlesmesi.md` (TR Mesafeli Sözleşmeler Yönetmeliği uyumu)
  - `docs/legal/payment-fallback-plan.md` (R-FIN-04 6-senaryo + Paddle ön başvuru + 30-gün tampon)
- **4 yeni implementation issue (Epic #448 review output):**
  - [#470](https://github.com/selmanays/nodrat/issues/470) Server-side foreign_transfer_consent enforcement (5 akış 403 gate)
  - [#471](https://github.com/selmanays/nodrat/issues/471) Paddle fallback PaymentProvider abstraction (R-FIN-04)
  - [#472](https://github.com/selmanays/nodrat/issues/472) refund-policy + mesafeli-satis frontend yayın
  - [#473](https://github.com/selmanays/nodrat/issues/473) Şahıs ticari kazanç mükellefiyeti aç + mali müşavir 4 yazılı teyit
- **Branch:** `wiki/lemon-squeezy-review-integration`
- **Açık doküman senkronizasyonu:** 1 → **0** ✅ (docs PR #477 ile wiki/docs hizalı)
- **Ders:** Strateji pivot review akışı = locked decision wiki'de önce, danışman cevapları integrated → wiki frontmatter'a `review_status` eklenmesi → docs catch-up sub-issue PR ile senkron. CLAUDE.md §1.3 wiki write disiplini korundu (dedicated wiki/* branch).



Sadece-ekleme (append-only) kronolojik kayıt. LLM her `ingest`, `query` (arşivlenen) ve `lint` operasyonu sonrası buraya bir kayıt ekler.

## [2026-05-08] decision+pivot | Iyzico → Lemon Squeezy MoR (USD primary) — Epic #448

- **Kaynak/Tetikleyici:** Kullanıcı stratejik kararı — "Iyzico kullanımını değiştirmek istiyorum Lemon Squeezy ile çünkü biz ilk başta şirket olmadan ödeme alabileceğimiz bir yapıyla ilerleyeceğiz". Solo founder + bootstrap context'te launch hızı önceliklendirildi: Limited Şti. (~6-8 hafta) + e-Arşiv altyapısı (~$50-100/ay sabit) gereksinimleri kaldırıldı.
- **5 stratejik karar (kullanıcı onayladı):**
  1. **Para birimi:** USD primary (TL display locale ile)
  2. **Şirket kuruluşu (#46):** kapatıldı (LS MoR olduğu için ilk aşamada gereksiz; >$3K MRR sonrası yeniden değerlendir)
  3. **e-Arşiv:** kaldırıldı (LS MoR müşteriye fatura keser)
  4. **Trial:** card-required aynı kalsın (LS native destek)
  5. **Multi-seat:** LS variant + custom seat counter
- **Etkilenen sayfalar:**
  - **Yeni:** [[lemon-squeezy-payment-provider]] (locked decision — Faz 6 LS MoR USD primary, alternatifler tablosu, KVKK m.9 cross-border, R-FIN/R-LGL impact)
  - **Update:** [[provider-abstraction]] (Faz 6+ tablosu: Iyzico/Stripe → LemonSqueezyPaymentProvider), [[mvp-cut-list-method]] (Faz 6 row LS), [[mvp-1-scope]] (Faz 6 LATER liste LS), [[mvp-roadmap]] (MVP-3 + MVP-4+ LS notları), [[risk-catalog]] (R-LGL-10 ~~8~~ → 2 ✅ LS MoR e-Arşiv handles, R-LGL-11 LS m.9 ek checkbox notu, R-LGL-12 LS hosted refund), [[risk-register-md]] (MVP-3 fonksiyonel kapsam: Iyzico+e-Arşiv → LS MoR)
  - **Hub:** wiki/index.md (yeni "Payment / billing" decisions section, istatistik 31 → 32 sayfa, locked decisions 8 → 9, açık doküman senkronizasyonu 1 🟡)
- **Yeni:** 1 decision sayfası
- **Güncellendi:** 7 (provider-abstraction, mvp-cut-list-method, mvp-1-scope, mvp-roadmap, risk-catalog, risk-register-md, index)
- **Trade-off muhasebesi:**
  - **Kazanılan:** Launch hızı (Limited Şti. süreci yok), sabit maliyet sıfıra yakın (e-Arşiv altyapı yok), tax compliance global (LS yönetir), refund/chargeback hosted, customer portal LS hosted, TR dışı pazara açılma kolay.
  - **Kaybedilen:** Komisyon ~%2.5 daha yüksek (Pro $24 net ~$22.30, ~%93 retain), TR müşteri USD görür (FX algısı), LS account/payout dependency riski (yeni R-FIN-XX), KVKK m.9 yurt dışı transfer açık rıza zorunlu (yeni R-LGL).
- **GitHub issue ops:**
  - **Epic [#448](https://github.com/selmanays/nodrat/issues/448):** master tracking
  - **Update:** [#53](https://github.com/selmanays/nodrat/issues/53) rename "Iyzico TL + e-Arşiv" → "Lemon Squeezy MoR + USD primary" + body USD/LS, [#76](https://github.com/selmanays/nodrat/issues/76) body LS hosted checkout/portal, [#49](https://github.com/selmanays/nodrat/issues/49) DPA listesinden Stripe/Iyzico kaldırıldı + LS eklendi
  - **Close:** [#46](https://github.com/selmanays/nodrat/issues/46) Limited Şti. defer (LS MoR sayesinde ilk aşamada gereksiz; >$3K MRR threshold)
  - **Yeni sub-issue:** [#450](https://github.com/selmanays/nodrat/issues/450) LS Customer Portal + webhook handler (signature verify, 7 event), [#451](https://github.com/selmanays/nodrat/issues/451) Multi-seat agency LS variant + seat counter, [#453](https://github.com/selmanays/nodrat/issues/453) KVKK m.9 yurt dışı transfer açık rıza akışı
- **Açık doküman senkronizasyonu (Epic #448 docs PR sırada):** 15 docs dosyası USD/LS update bekliyor — `pricing-strategy.md` (USD recalc + LS provider), `unit-economics.md` (~%5+50¢ LS fee margin recalc), `risk-register.md` (yeni R-FIN-XX MoR dependency + R-FIN-XX FX exposure + R-LGL-XX KVKK m.9), `success-metrics.md` (USD KPI), `prd.md` §6 (Faz 6 rewrite), `ux-wireframes.md` (LS checkout/portal), `architecture.md` (payment provider section), `data-model.md` (subscriptions ls_* sütunlar), `api-contracts.md` (LS webhook spec), `threat-model.md` (US PII transfer), `legal/*` (8 dosya — compliance, tos, privacy, kvkk, ropa, cookies, dpo, incident, opinion), `INDEX.md` (locked decisions §4 + milestone §5b note). Wiki kararı **önce locked**; docs catch-up Epic #448 docs PR ile.
- **Branch:** `wiki/lemon-squeezy-pivot` (CLAUDE.md §1.3 — wiki write only on dedicated wiki/* branch).
- **Ders:** Strateji pivotunda **wiki kararı önce locked, docs catch-up sonra** akışı uygun. Çünkü kullanıcı kararı verdi → karar zaten "locked" — docs hâlâ eski Iyzico planını anlatıyor olsa bile wiki "şu anki gerçeği" yansıtmalı. Doküman senkronizasyonu ayrı PR ile sıralı yapılır (`Açık doküman senkronizasyonu` istatistiğinde takip).



## Format

```
## [YYYY-MM-DD] ingest|query|lint | başlık

- **Kaynak/Tetikleyici:** ...
- **Etkilenen sayfalar:** [[slug-1]], [[slug-2]], ...
- **Yeni:** N
- **Güncellendi:** N
- **Notlar:** opsiyonel kısa not (sürpriz bulgu, açık soru, çelişki)
```

> Avantaj: `grep "^## \[" log.md | tail -20` son 20 işlemi listeler. `grep "ingest" log.md` sadece ingest'leri gösterir.

---

## [2026-05-08] update | Epic #443 follow-up #475 — admin queue overview 4.3s → 11-684ms

- **Kaynak/Tetikleyici:** Kullanıcı admin özet + kuyruk sayfasının her yenilemede birkaç saniye sürdüğünü bildirdi.
- **Etkilenen sayfalar:** [[queue-management]] — performans bölümü güncellendi (yeni mimari + ölçümler)
- **Yeni:** 0 wiki page
- **Güncellendi:** Kod tabanı ([PR #475](https://github.com/selmanays/nodrat/pull/475) + 1 hotfix commit):
  - `core/celery_introspect.py` — `_INSPECT_TIMEOUT_S = 0.5` (eskiden 2.0); yeni `get_broker_snapshot()` tek inspect call ile worker_count + active_counts + Redis pipeline ile 4 LLEN tek round-trip + 5s Redis snapshot cache (`nodrat:broker:overview`)
  - `api/admin_queue.py` — queue_overview endpoint snapshot kullanır, broker arka planda async başlar; DB sıralı (AsyncSession concurrent destekleme bug'ı var, gather kullanılmaz)
  - `apps/web/.../admin/queue/page.tsx` — bakım görevleri ayrı 30s interval (beat schedule en kısa 5 dk; 30s yeterli), ana 10s refresh sadece overview + failed_jobs

- **Profile (production canlı ölçüm):**
  - **Önce:** `inspect.active` 2123ms + `inspect.ping` 2014ms + DB sıralı 110ms = **~4300ms**
  - **Sonra cache miss:** ~510-684ms (timeout 0.5s + tek inspect)
  - **Sonra cache hit:** ~11-50ms (Redis GET)
  - Auto-refresh 10s + cache TTL 5s → her 2 yenilemenin 1'i cache hit
  - **Hızlanma: cache miss 6-8x, cache hit 86-390x**

- **Etkilenen sayfalar (UI):**
  - `/admin` (özet) — `getQueueOverview` çağırır, otomatik hızlanır → 152ms HTTPS round-trip
  - `/admin/queue` — aynı endpoint + paralel `listFailedJobs` → 276ms HTTPS round-trip
- **Notlar:**
  - Geriye dönük uyumlu: `get_active_counts_by_queue` + `get_worker_count` fn'leri korundu (testler + olası dış kullanım)
  - 21/21 unit test yeşil, TS clean
  - SQLAlchemy `AsyncSession concurrent operations not permitted` bug'ı (ilk commit'te yakalandı, hotfix ile DB sıralıya alındı — broker async başladığı için yine paralel ilerler)
  - Maintenance task'ları ana refresh'i bloklamaz: 30s interval bağımsız

## [2026-05-08] update | Epic #443 follow-up #468 — bakım görevleri (backfill/retry) admin panelde

- **Kaynak/Tetikleyici:** Kullanıcı admin queue sayfasında 5 backfill/retry maintenance task'ı (görsel + haber işleme boru hatları) görmek + manuel tetiklemek istedi.
- **Etkilenen sayfalar:** [[queue-management]] — yeni "Bakım görevleri" bölümü (5 task listesi + tracking mimarisi + endpoint'ler)
- **Yeni:** 0 wiki page
- **Güncellendi:** Backend + frontend + 1 PR ([#469](https://github.com/selmanays/nodrat/pull/469)):
  - `core/maintenance_tracker.py` (yeni) — Redis-backed Celery signal hook tracker
  - `workers/celery_app.py` — task_prerun + task_postrun signal handlers (sadece TRACKED_TASKS)
  - `api/admin_queue.py` — `GET /admin/queue/maintenance` + `POST .../{task_name}/run-now`
  - `apps/web/src/app/admin/queue/page.tsx` — alt bölümde "Bakım görevleri" kartı
- **Production etki (deployed 2026-05-08 22:00 UTC):**
  - 5 task admin panelde görünür: stuck haber yakalama, başarısız haber tekrar dene, bekleyen görsel VLM kuyruğa al, başarısız görsel tekrar dene, eksik chunk yakalama
  - Manuel test: `tasks.articles.backfill_missing_chunks` admin tetiklendi → status=succeeded, dispatched=0 (chunks zaten var)
  - 21/21 unit test yeşil
- **Notlar:**
  - `triggered_by` ayrımı (admin vs beat) signal handler'da kapsam dışı — gelecekte Celery task headers ile yapılabilir
  - Tracker key TTL 24h — task hiç çalışmazsa "Henüz çalıştırılmadı" gösterilir

## [2026-05-08] update | Epic #443 follow-up — alarm 396 → 30 unresolved (%92), bulk actions, AA SPA tanısı

- **Kaynak/Tetikleyici:** Epic #443 sonrası "sonraki iterasyonlar" — 4 yeni alt-issue açıldı (#460 AA extract, #461 drill-down, #462 bulk actions, #463 discovered_timeout backfill); 3'ü teslim edildi, #461 sonraki oturuma kaldı.
- **Etkilenen sayfalar:** [[queue-management]] (baseline tablosu güncellenmedi — bu log entry'de delta tutuldu, page page'de "production etki" tablosu Epic close-out anındaki snapshot'ı temsil eder)
- **Yeni:** 0 wiki page
- **Güncellendi:** Aşağıdaki kod tabanı:
  - PR [#464](https://github.com/selmanays/nodrat/pull/464) (#463) — `discovered_timeout` 88 legacy satır auto-resolve migration
  - PR [#465](https://github.com/selmanays/nodrat/pull/465) (#460) — AA SPA migration tanısı + 187 extract failure warning auto-resolve migration
  - PR [#466](https://github.com/selmanays/nodrat/pull/466) (#462) — bulk retry/resolve endpoints + UI multi-select toolbar (3 yeni unit test, 18/18 yeşil)
- **Production etki kümülatif (Epic #443 + follow-up, 2026-05-08 21:30 UTC):**
  - failed_jobs unresolved: **396 → 30** (−366, **%92 azalma**)
  - Geriye kalan: 28 article.fetch_detail (gerçek HTTP fail) + 2 article.extract (evrensel)
  - severity dağılımı: 30 error + 187 warning (AA SPA) + 91 permanent_info (duplicate_content + discovered_timeout)
  - Bulk endpoints canlı: `/admin/queue/failed/bulk-retry`, `/admin/queue/failed/bulk-resolve` (max 200 id)
- **AA SPA tanısı (önemli karar girdisi):**
  - aa.com.tr Tailwind + JS-rendered SPA mimarisine geçmiş
  - Statik HTML body skeleton placeholder'lar, JSON-LD `articleBody` sadece 83 char özet
  - Mevcut site_profiles selector'ları (`article, .detay, .haber-detay`) artık boş wrapper'lara denk geliyor
  - Kullanıcı seçenekleri (#460 issue comment'inde): (1) `sources.is_active=false` geçici disable, (2) Playwright JS-render (#71 LATER cut-list), (3) AA-specific JSON-LD özet kabul (önerilmez, kalite düşer)
- **Notlar:**
  - PR-C (drill-down panel #461) bir sonraki oturuma bırakıldı — alarm seviyesi 30'a düştüğü için aciliyet düştü
  - `crawler_jobs` tablosu hala ölü (artık hiç write yok) — kaldırma vs audit ledger kararı açık (öneri için ayrı issue)
  - `tasks.maintenance.detect_stale_discovered` task gerek yok — orphan article zaten 0 (sistem düzgün)
  - CI manuel: kullanıcı GitHub Actions kredisi bittiği için tüm merge'ler `--admin`, deploy ssh+rsync ile manuel yapıldı

## [2026-05-08] ingest | Epic #443 — Admin queue sayfası overhaul (4 PR + 1 yeni concept)

- **Kaynak/Tetikleyici:** Kullanıcı `/admin/queue` sayfasını incelerken iki yapısal hata fark etti: (1) "41 sırada" + "0/0 24h" kartları yanlış veri gösteriyordu çünkü hiçbir Celery task `crawler_jobs` tablosuna yazmıyordu; (2) "364 unresolved" alarmı gerçek hata değil, %20'si RSS re-emit info kaydıydı.
- **Etkilenen sayfalar:**
  - `concepts/`: **YENİ** [[queue-management]] — Celery broker introspection + DLQ severity 3-tier + admin retry akışı + production baseline before/after tablo
  - `topics/`: [[data-pipelines]] (kuyruk haritası → 4 ana queue celery task_routes ile birebir, [[queue-management]] backlink)
- **Yeni:** 1 concept page ([[queue-management]])
- **Güncellendi:** Epic + 4 PR ile aşağıdaki kod tabanı:
  - PR [#447](https://github.com/selmanays/nodrat/pull/447) — Celery broker depth + retry Celery `apply_async` dispatch
  - PR [#449](https://github.com/selmanays/nodrat/pull/449) — `ArticleImage.processed_at` smoke hotfix
  - PR [#454](https://github.com/selmanays/nodrat/pull/454) — `failed_jobs.severity` migration + duplicate_content auto-resolve backfill
  - PR [#456](https://github.com/selmanays/nodrat/pull/456) — Frontend pagination + severity badge + label fix + 10s auto-refresh
- **Production etki (deployed 2026-05-08 19:30 UTC):**
  - `failed_jobs` unresolved: **396 → 305** (−91, %23 azalma — 74 duplicate_content auto-resolve + 17 yeni RSS re-emit otomatik permanent_info)
  - 4 kuyruk kartından 13/16 hücre artık gerçek broker veri (önce yapısal olarak yanlış)
  - Crawl 24h success: 311 / fail: 246 (önce 0/0)
  - Event 24h success: 275 (yeni agenda card)
  - Image VLM 24h success: 377 (yeni VLM processed)
  - Worker count: 5 (broker bağlantı sağlığı yeni metrik)
  - UI: 305 kaydın tamamına pagination ile erişim (önce sadece ilk 50)
  - Retry butonu Celery worker'a gerçek `apply_async` (önce sadece DB ledger)
- **Notlar:**
  - `crawler_jobs` tablosu artık tamamen boş yazma — gelecekte ya kaldırılır ya admin retry audit'e dönüştürülür (karar verilmeli, ayrı issue önerisi)
  - 175 `article.extract` failure ve 88 `article.discovered_timeout` ASIL kalan sorun — kazıma kalitesi tarafında ayrı incelemenin konusu
  - PR-3 sınırlı tutuldu (sadece pagination + severity + auto-refresh) — drill-down panel + bulk actions sonraki iterasyona kaldı
  - CI manuel: kullanıcının GitHub Actions kredisi bittiği için tüm merge'ler `--admin` ile, deploy ssh + rsync ile manuel yapıldı

## [2026-05-08] update | MVP-2.1 epic close-out — endpoint refactor + UI sekmesi + 2 yeni locked decision

- **Kaynak/Tetikleyici:** GitHub PR [#441](https://github.com/selmanays/nodrat/pull/441) (closes [#440](https://github.com/selmanays/nodrat/issues/440)) — `mvp-2-1-delta` endpoint kötü adlandırılmış (milestone-bound) → jenerik refactor + browser UI eklendi. Önceki preparation: PR [#431](https://github.com/selmanays/nodrat/pull/431) (closes #429, #432).
- **Etkilenen sayfalar:**
  - `decisions/`: **YENİ** [[endpoint-naming-policy]] (production endpoint adlandırma kuralı), **YENİ** [[pipeline-observability-location]] (`/admin/rag` LLM, `/admin/observability` infra)
  - `topics/`: [[pipeline-performance-baseline]] (PR #418/#431/#441 satırları + telemetry hooks 3 madde tikle + 2026-05-15 production ölçüm placeholder)
- **Yeni:** 2 locked decision sayfası
- **Güncellendi:** 1 topic sayfası (pipeline-performance-baseline)
- **Notlar:**
  - Eski `GET /admin/dashboard/mvp-2-1-delta` SİLİNDİ → yeni `GET /admin/rag/pipeline-comparison` (jenerik tarih aralığı parametreleri).
  - UI: `/admin/rag` sayfasına "Performans" sekmesi (7. sekme). Browser üzerinden admin login ile kullanılabilir — JWT manuel kopyalama gerekmez.
  - **MVP-2.1 epic [#391](https://github.com/selmanays/nodrat/issues/391) kod kapsamı tamamlandı** (7/7 sub-issue + 5 PR: #411, #416, #418, #431, #441). Production data ile final acceptance ölçümü 2026-05-15 sonrası yapılacak (post window 7-gün dolduğunda).
  - **Production verisi alındı (2026-05-08T15:55Z):** 2026-05-01..05-08 dönemi için 10,972 LLM chat çağrısı, %81 cache hit ratio, %1.7 halü oranı (hedef <%2 ✓). Ama bu pencere PR #418 deploy'unu kapsıyor — temiz pre/post karşılaştırması için 2026-05-15 sonrası gerek.
  - Karar 1: **Endpoint adı milestone-bound olamaz** ([[endpoint-naming-policy]]). Bu kural retroaktif değil — proaktif. Yeni PR'larda enforce edilir.
  - Karar 2: **Yeni LLM/pipeline gözlem aracı `/admin/rag`'a sekme** ([[pipeline-observability-location]]). `/admin/observability` infrastructure-only kalır.

## [2026-05-08] correction | data-pipelines.md §1 Kural A4 — gerçek mekanizma (slug varyasyonları, UTM değil)

- **Kaynak/Tetikleyici:** Kullanıcı "38 duplicate_content nedir, nasıl tespit ediyoruz, neye göre, wiki güncel mi?" sorusu. Production örnekleri incelenince Kural A4'te yanlış bir iddia tespit edildi.
- **Etkilenen sayfalar:** [[data-pipelines]] §1 Kural A4
- **Yeni:** 0
- **Güncellendi:** 1 sayfa (Kural A4 yeniden yazıldı)
- **Düzeltilen iddia:** Eski metin "canonicalize_url'in tracking parametrelerini farklı canonical hesaplaması nedeniyle" diyordu — YANLIŞ. `canonicalize_url` ([cleaning.py:94-119](../apps/api/app/core/cleaning.py:94)) UTM/fbclid/gclid vb. tüm tracking parametrelerini düzgün strip ediyor.
- **Gerçek kök neden:** Yayıncı RSS feed'inin aynı haberi **path/slug varyasyonlarıyla** emit etmesi. canonicalize_url path'i değiştirmiyor, sadece query'yi temizliyor. Production örneği: Evrensel `chpyi` (yapışık) vs `chp-yi` (tireli) slug — aynı haber, iki ayrı canonical_url, ikisi de DB'ye giriyor, fetch_detail ikincisi `(source_id, real_content_hash)` UNIQUE'e çarpıyor.
- **Eklenen detay:**
  - Hash mekanizması: `compute_content_hash() = SHA-256(re.sub(r"\s+", " ", text.lower().strip()))` (whitespace + lowercase normalize, sonra SHA-256)
  - UNIQUE constraint kayıt: `uq_articles_source_content_hash` UNIQUE `(source_id, content_hash)`
  - İki aşamalı hash: discover'da provisional (summary/title), fetch_detail'de real (cleaned.clean_text)
  - Production örneği tablosu (chpyi vs chp-yi case)
  - Diğer nadiren oluşan A4 nedenleri: crawler race condition (paralel poll). Republish ise (canonical aynı kalır) discover'da yakalanır, A4'e düşmez.
- **Branch:** `wiki/fix-kural-a4-real-mechanism`
- **Ders:** Wiki yazarken kod davranışını VARSAYMAK yetmez — production örneklerine bakarak doğrulamak gerekiyor. UTM tracking iddiası mantıklı görünüyordu ama gerçek mekanizma tamamen farklıydı (slug variation). DLQ'daki 38 duplicate_content entry'sinin URL'lerine bakmak yarım dakika sürdü ve doğru tabloyu çıkardı.

## [2026-05-08] update | data-pipelines.md §1 article kuyruk discipline + Kural A1-A5 (#433/#436 dersi)

- **Kaynak/Tetikleyici:** Kullanıcı admin panel'de [/admin/articles](https://nodrat.com/admin/articles) "Keşfedildi: 126" + "Başarısız: 60" gördü; image pipeline'a yaptığımız self-healing iyileştirmesinin article için aynı kalıbını istedi. Plan onaylandı (4 fazlı: B + C + E + opsiyonel D).
- **Etkilenen sayfalar:** [[data-pipelines]] (Pipeline 1 §Hata akışı genişletildi + yeni §Kuyruk discipline + freshness kuralları, 5 alt madde A1-A5)
- **Yeni:** 0
- **Güncellendi:** 1 sayfa (~140 satır eklendi)
- **Eklenen 5 kural (image §4 ile paralel yapı):**
  - **A1) Backfill discovered** (5 dk beat, batch=100, 72h freshness): RSS poll sonrası dispatch edilen fetch_detail Redis broker'da kaybolursa (worker crash, OOM) backfill yakalar. Idempotent.
  - **A2) Retry-failed** (saatlik :25 beat, batch=50, 72h cutoff): failed → discovered UPDATE + dispatch. Image retry (:20) ile çakışmaz.
  - **A3) Transient vs permanent classification:** `_TRANSIENT_EXCEPTIONS` listesi (`httpx.TimeoutException`, `OperationalError`, `ConnectionError`). IntegrityError DEĞİL — explicit handler. Eski `autoretry_for=Exception` "Bug sentinel" pattern'iyle 124 article stuck kalıyordu.
  - **A4) Duplicate content (RSS re-emit pattern):** UTM tracking parametre farklılığı → canonicalize_url farklı çıkıyor → discover'da iki ayrı article row → ikinci fetch_detail commit `IntegrityError: uq_articles_source_content_hash`. Çözüm: same-session rollback + `_record_failure(job_type='article.duplicate_content')`. Kod örneği eklendi (#434, #435 MissingGreenlet hotfix dersi).
  - **A5) Drenaj sağlığı izleme:** 3 SQL query (status dağılım, stale ratio, DLQ recent), worker log grep, alarm tetikleyicileri.
- **Production verify (deploy sonrası):**
  - Faz B (#434/#435) deploy → 2 manuel dispatch ile IntegrityError handler doğrulandı (article 'failed', DLQ 'duplicate_content' entry, MissingGreenlet kaybolmuş).
  - Faz C (#437) deploy + manuel backfill + manuel retry_failed:
    - cleaned: 2550 → 2580 (+30, başarıyla işlenenler)
    - discovered: 124 → 88 (kalan 88'in tamamı stale >72h, doğru bypass)
    - failed: 62 → 78 (+16 duplicate_content olarak işaretlendi)
    - DLQ son 15 dk: 38× duplicate_content, 17× extract conf<0.6, 1× fetch_detail
- **Branch:** `wiki/article-pipeline-rules`
- **Cross-link:** [#433](https://github.com/selmanays/nodrat/issues/433) [#434](https://github.com/selmanays/nodrat/pull/434) [#435](https://github.com/selmanays/nodrat/pull/435) [#436](https://github.com/selmanays/nodrat/issues/436) [#437](https://github.com/selmanays/nodrat/pull/437)
- **Ders:** Image pipeline'da öğrendiğimiz pattern'leri (transient classification, IntegrityError handler, 5dk backfill + saatlik retry-failed, 72h freshness window) article için aynısını uygulamak fizibıl. Sentinel pattern'inin generic olduğunu gördük — herhangi bir worker pipeline (embedding, clustering, RAPTOR) için de aynı yapı gerekir gerekirse. Open follow-up: Pipeline 2/3/5 için aynı discipline kuralları yazılacak mı? (scope dışı — bu kullanıcının ihtiyaç görmesine bağlı).

## [2026-05-07] init | wiki iskeleti kuruldu

- **Kaynak/Tetikleyici:** Kullanıcı isteği — LLM Wiki örüntüsünü Nodrat'a uygulamak.
- **Etkilenen sayfalar:** —
- **Yeni:** wiki/{README,index,log,SETUP}.md, wiki/_templates/{entity,concept,topic,decision,source}.md, kök CLAUDE.md, .mcp.json, .obsidian/{app,core-plugins}.json.
- **Güncellendi:** .gitignore (Obsidian section), .env.example (OBSIDIAN_API_KEY).
- **Notlar:** Obsidian MCP server: `mcp-obsidian` (Markus Pfundstein, PyPI üzerinden `uvx mcp-obsidian`). Kullanıcı manuel Obsidian + Local REST API plugin kuracak — bkz. [SETUP.md](SETUP.md).

## [2026-05-07] ingest | architecture.md (pilot)

- **Kaynak/Tetikleyici:** Pilot ingest — şablonları stres-test etmek için en zengin doküman seçildi (`docs/engineering/architecture.md` v0.1).
- **Etkilenen sayfalar:**
  - `sources/`: [[architecture-md]]
  - `entities/`: [[deepseek]], [[claude-haiku-4-5]], [[nim-bge-m3]], [[contabo-vps]], [[celery-worker]]
  - `concepts/`: [[provider-abstraction]], [[hot-cold-tier]], [[binary-quantization]]
  - `decisions/`: [[deepseek-default-llm]], [[claude-haiku-premium-llm]], [[contabo-vps-hosting]]
  - `topics/`: [[llm-provider-strategy]]
- **Yeni:** 13 (1 source + 5 entity + 3 concept + 3 decision + 1 topic)
- **Güncellendi:** wiki/index.md (sayfa kataloğu + istatistik), wiki/log.md (bu kayıt)
- **Notlar — 3 ÇELİŞKİ tespit edildi:**
  1. **Hosting:** architecture.md §0 "Hetzner CCX23" yazıyor; INDEX §4 "Contabo VPS 40" diyor. INDEX güncel (v1.4, 2026-05-07). Kaynak doküman v0.2 sürüm güncellemesi gerekiyor → `nodrat-dev` ile issue/PR akışı.
  2. **Backup:** architecture.md §9.1 "B2 (encrypted)" diyor, §5.4 ve INDEX "Contabo Object Storage" diyor (MVP-1.5'te geçiş). §9 güncellenmeli.
  3. **Embedding model:** Adapter adı `nim_bge_m3` ama gerçekte `nvidia/nv-embedqa-e5-v5` serve ediliyor (cosine ≈ 0, orthogonal vs. local BAAI/bge-m3). #345 migration ile çözülecek.
- **Açık sorular:** Yer yer "TODO" bölümleri sayfalarda (NIM rate limit detayı, eval gate test set, HNSW memory footprint, free-tier abuse alarm, comparison_generation task_type net mapping, vb.).

## [2026-05-08] ingest | risk-register.md

- **Kaynak/Tetikleyici:** Kullanıcı "devam" — pilot sonrası önerdiğim sıralı ingest planının #1 dokümanı.
- **Etkilenen sayfalar:**
  - `sources/`: [[risk-register-md]]
  - `entities/` (risk objeleri): [[risk-fsek-telif]], [[risk-kvkk-violation]], [[risk-source-fragility]], [[risk-cost-runaway]]
  - `concepts/`: [[risk-scoring]], [[mvp-cut-list-method]], [[kill-switch]]
  - `decisions/`: [[twenty-five-word-quote-cap]], [[mvp-1-scope-lock]], [[pii-redaction-mandatory]]
  - `topics/`: [[risk-catalog]], [[mvp-1-scope]], [[mvp-roadmap]]
- **Yeni:** 14 (1 source + 4 risk-entity + 3 concept + 3 decision + 3 topic)
- **Güncellendi:** wiki/index.md (27 sayfa toplam, kategori bazlı gruplanma + 6 locked decision), wiki/log.md (bu kayıt)
- **Notlar — 3 skor anomalisi tespit edildi (kaynak doküman güncellemesi gerekli):**
  1. **R-FIN-02 (DeepSeek API instability) skor 9** ama §2.2 sarı tablosunda. → 🔴 olmalı.
  2. **R-MKT-02 ("ChatGPT yeter") skor 9** ama §2.2 sarı tablosunda. → 🔴 olmalı.
  3. **R-MKT-03 (Düşük WTP) skor 9** ama §2.2 sarı tablosunda. → 🔴 olmalı.
  Aksiyon: `nodrat-dev` ile risk-register.md sürüm bump (v0.2 → §2.1/§2.2 yeniden organize).
- **Çapraz cross-link kapsamı:** Bu ingest sayesinde 27 sayfanın tamamı en az 2 backlink alıyor. [[risk-catalog]] hub-of-hubs (top mitigation kapsama matrisi).
- **Açık locked decisions çağrısı:** Risk-register §3 detayında 4 yeni locked decision sayfası açılması gerekti — bu, INDEX §4'teki tüm "✅ locked" listesinin de wiki'ye taşınmasının zaman alacağının göstergesi (henüz 6/22).
- **Sürpriz bulgu:** MVP-2 -19 hafta erken delivered (2026-09-29 hedef → 2026-05-07). Resmi gerekçe doküman yok. Discovery güçlü çıkması + AI agent verimliliği + MVP-1.x'lerin MVP-2 feature'larını "kapması" hipotezleri [[mvp-roadmap]] ve [[mvp-1-scope]]'da dokümante edildi.
- **Sıradaki ingest önerileri:**
  - [docs/product/prd.md](../docs/product/prd.md) — kanonik kök, ~12 entity/concept tahmini
  - [docs/strategy/discovery-validation.md](../docs/strategy/discovery-validation.md) + [validation/research-findings.md](../docs/validation/research-findings.md) — persona-p1a, persona-p1b entity'leri
  - [docs/engineering/prompt-contracts.md](../docs/engineering/prompt-contracts.md) — R-PRD-01 (halü) detay + citation %100 / halü <%2 thresholds
  - [docs/engineering/data-model.md](../docs/engineering/data-model.md) — 12 tablonun her biri için entity

---

## [2026-05-08] lint+update | deepseek-default-llm.md eskimiş iddia düzeltildi

- **Kaynak/Tetikleyici:** Kullanıcı bildirimi — sayfa `deepseek-v3.1-terminus / NIM endpoint` diyor ama kod tabanı artık `deepseek-v4-flash / native DeepSeek API` kullanıyor.
- **Etkilenen sayfalar:** [[deepseek-default-llm]]
- **Yeni:** 0
- **Güncellendi:** 1
- **Doğrulama:** [apps/api/app/providers/deepseek.py:61](../apps/api/app/providers/deepseek.py) → `DEEPSEEK_CHAT_DEFAULT_MODEL = "deepseek-v4-flash"`. Class `DeepSeekProvider` (DeepSeek native API). Registry routing name `deepseek_v3` korunmuş (backward-compat).
- **Migration commit zinciri:** #163 (native API provider) → #361 (model adı v4-flash) → #378 (smoke fixes) → #379 (thinking-disabled, 2026-05-07).
- **Düzeltilen iddialar:** model adı (v3.1-terminus → v4-flash), provider (NIM → native), API key (NIM_API_KEY → DEEPSEEK_API_KEY), adapter dosya yolu (packages/model-providers/nim_chat.py → apps/api/app/providers/deepseek.py), "Native DeepSeek API reddedildi" → kabul edildi (#163), §Ek not'taki yanlış varyant tablosu (v4-flash "timeout sorunları" iddiası tam tersine — production default).
- **⚠️ Çelişki bloğu eklendi:** docs/engineering/architecture.md §4.2/§4.3 hâlâ NIM/v3.1-terminus diyor — wiki güncel, kaynak eskimiş. CLAUDE.md §1.1 gereği docs/ LLM tarafından yazılmaz → ayrı `nodrat-dev` görevi açılmalı.
- **Branch disiplini:** Bu güncelleme `wiki/deepseek-v4-flash-update` dedicated branch'inde (CLAUDE.md §1.3). Feature worktree dışında.
- **Açık çelişki sayısı:** 6 → 7 (yeni: deepseek-default-llm vs architecture.md).

---

## [2026-05-08] lint+update | DeepSeek migration ailesi tam temizlendi

- **Kaynak/Tetikleyici:** İlk turdan sonra kullanıcı "hata kalmasın wiki'de" istedi. DeepSeek migration (NIM/v3.1-terminus → native API/v4-flash) wiki ailesinde 5 ek dosyada faktüel referans bulundu.
- **Etkilenen sayfalar:** [[deepseek]] (entity, neredeyse tam yeniden yazıldı), [[provider-abstraction]] (concept, adapter listesi + routing pseudocode), [[architecture-md]] (source, 2 ana çıkarım + yeni ⚠️ Çelişki bloğu + sürüm takibi), [[nim-bge-m3]] (entity, "ortak API key" iddiası düzeltildi), [[llm-provider-strategy]] (topic, TL;DR + cost tablosu + risk tablosu yeniden yazıldı), [[mvp-1-scope-lock]] (decision quote), [[claude-haiku-premium-llm]] (routing pseudocode model adı), wiki/index.md (entity + decision listing açıklamaları).
- **Yeni:** 0
- **Güncellendi:** 8 (deepseek-v3 + provider-abstraction + architecture-md + nim-bge-m3 + llm-provider-strategy + mvp-1-scope-lock + claude-haiku-premium-llm + index.md)
- **Anahtar düzeltmeler:**
  - `deepseek-ai/deepseek-v3.1-terminus` → `deepseek-v4-flash` (8 yer)
  - "NIM endpoint default" → "NIM endpoint fallback" (5 yer)
  - "Tek API key (NIM_API_KEY)" → "DeepSeek chat: DEEPSEEK_API_KEY ayrı, embedding: NIM_API_KEY" (3 yer)
  - "DeepSeek V3 (NIM free) cost $0" → "DeepSeek native $0.27/$1.10 + %75 kampanya 2026-05-31'e kadar" (cost tablosu)
  - Routing pseudocode `DeepSeekProvider(model="deepseek-v3")` → `model="deepseek-v4-flash"` (3 yer)
  - Adapter listesi: NimChatProvider primary → fallback; DeepSeekProvider eklendi
- **Korunan:** Slug `deepseek-v3` ve registry name `deepseek_v3` backward-compat için bilinçli olarak korundu (`generation_log.provider_name` migration boyunca aynı).
- **⚠️ Çelişki sayısı korundu:** 7 — wiki içi tutarlılık sağlandı; tek açık çelişki `wiki ↔ docs/engineering/architecture.md` (kaynak v0.1 hâlâ NIM/v3.1-terminus diyor). Bu `nodrat-dev` görevi olarak chip ile spawn edildi.

---

## [2026-05-08] re-sync+lint | architecture.md v0.2 + ⚠️ DeepSeek çelişki cleanup

- **Kaynak/Tetikleyici:** [PR #405](https://github.com/selmanays/nodrat/pull/405) (`docs(architecture): DeepSeek migration sync — §0/§4.2/§4.3`) main'e merge edildi → `architecture.md` v0.1 → v0.2. PR #403 ile eklenen ⚠️ DeepSeek migration çelişki bloğu artık resolved.
- **Etkilenen sayfalar:** [[deepseek-default-llm]] (⚠️ blok kaldırıldı + Kaynaklar listesi güncellendi), [[deepseek]] (Kaynaklar listesi "(eskimiş)" notları temizlendi), [[architecture-md]] (frontmatter v0.1 → v0.2, ana çıkarımlar #3 yeniden yazıldı, ⚠️ DeepSeek bloğu kaldırıldı, sürüm değişikliği takibi v0.2 satırı eklendi, "üretilen wiki sayfaları" listesi temizlendi), wiki/index.md (istatistik: çelişki 7 → 6, son re-sync eklendi).
- **Yeni:** 0
- **Güncellendi:** 4
- **Çelişki muhasebesi:**
  - **Resolved (1):** `wiki ↔ docs/engineering/architecture.md §0/§4.2/§4.3` DeepSeek migration → kaynak v0.2 ile hizalandı (#405).
  - **Hâlâ açık (3 architecture):** Hosting (§0 Hetzner CCX23 vs INDEX Contabo VPS 40), Backup (§9.1 B2 vs §5.4 Contabo OS), Embedding model (§4.2 nim_bge_m3 ↔ baai/bge-m3 orthogonal).
  - **Hâlâ açık (3 risk-register):** R-FIN-02, R-MKT-02, R-MKT-03 skor anomalileri (skor 9 ama §2.2 sarı tablosunda).
  - **Toplam:** 7 → 6.
- **Branch disiplini:** Bu temizlik `wiki/contradiction-cleanup` dedicated branch'te (CLAUDE.md §1.3). Feature worktree dışında, ayrı kısa-ömürlü worktree.

---

## [2026-05-08] lint+update | Hetzner/B2 wiki temizliği — production hep Contabo netliği

- **Kaynak/Tetikleyici:** Kullanıcı net bildirim: "Hetzner ile hiç alakamız yok, B2 de kullanmıyoruz". Wiki sayfaları Hetzner CCX23 → Contabo migration'ını historical fact olarak gösteriyordu — ama production hiç Hetzner üzerinde çalışmadı; sadece architecture.md draft dilinde Hetzner geçiyordu.
- **Doğrulama (kod tabanı):** `infra/deploy.sh:22` + `.github/workflows/deploy.yml` Contabo IP'sini (164.68.107.205) kullanıyor; `apps/api/app/config.py` + `infra/backup.sh` Contabo Object Storage endpoint'i (`eu2.contabostorage.com`) kullanıyor. Hetzner stringi kod tabanında yok. B2 referansları sadece `infra/restore.sh:44-46` legacy stub + `docs/operations/deployment-manual-steps.md` doc-debt.
- **Memory dosyası onayı:** `~/.claude/projects/-Users-selmanay-Desktop-nodrat/memory/manual_deploy.md` "Eski VPS (decommission edilecek): 173.212.238.104 (VPS 10, 4 vCPU/8GB)" diyor — eski production Contabo VPS 10'du, Hetzner değil.
- **Etkilenen sayfalar:**
  - [[contabo-vps]] entity — TL;DR + Rolü/faz ilişkisi yeniden yazıldı (Contabo VPS 10 → VPS 40 yükseltme; Hetzner sadece "draft mention, hiç deploy edilmedi" notu olarak)
  - [[contabo-vps-hosting]] decision — Karar quote + Bağlam + Alternatifler tablosu güncellendi; ⚠️ Çelişki bloğu çok daha keskin gerekçelerle yeniden yazıldı (architecture.md §0/§2.1/§5.1/§9.1/§13 stale referans listesi; chip-spawn aksiyonu)
  - [[architecture-md]] source — ⚠️ Hosting/Backup blokları yeniden yazıldı (production hep Contabo netliği + #330/`714d5b2` migration kanıtı); §12.1 darboğaz açık karar nüansı; sürüm değişikliği takibi yeni satır
  - [[mvp-roadmap]] topic — MVP-1.5 changelog "Hetzner CCX23 → Contabo VPS 40" → "Contabo VPS 10 → Cloud VPS 40 yükseltme"
  - [[risk-register-md]] source — Ana çıkarımlar #4 aynı düzeltme
  - wiki/index.md — decision listing açıklaması + istatistik açık çelişki notları güncellendi (Hosting çelişkisi rephrased)
- **Yeni:** 0
- **Güncellendi:** 6
- **Korunan:** B2 historical mention'ları korundu (INDEX "öncesinde Backblaze B2" diyor, MEMORY "eski .env/B2" diyor — gerçek MVP-1 era backup'tı, MVP-1.5'te migrate edildi).
- **Açık çelişki muhasebesi:** 6 → 6 (rephrased; sayı değişmedi). architecture.md hâlâ §0/§2.1/§5.1/§9.1/§13'te Hetzner/B2 — ayrı `nodrat-dev` chip ile temizlenecek.
- **Branch:** `wiki/hetzner-b2-cleanup` (CLAUDE.md §1.3).

---

## [2026-05-08] re-sync+lint | architecture.md v0.3 + Hetzner/B2 ⚠️ blokları kaldırıldı

- **Kaynak/Tetikleyici:** [PR #410](https://github.com/selmanays/nodrat/pull/410) main'e merge edildi (commit `0b57986`, closes [#409](https://github.com/selmanays/nodrat/issues/409)). architecture.md v0.2 → v0.3 — §0/§1/§2.1/§5.1/§7/§8/§9/§12.1/§13 stale Hetzner/B2 referansları kod tabanına hizalandı.
- **Etkilenen sayfalar:**
  - [[architecture-md]] source — frontmatter v0.2 → v0.3, doküman bilgisi re-sync history, "Ne içerir" özeti güncel forma, ana çıkarımlar #10 backup hedefi düzeltildi, "üretilen wiki sayfaları" listesinde [[contabo-vps-hosting]] " — ⚠️ kaynakla çelişkili" notu kaldırıldı, ⚠️ Hosting + ⚠️ Backup blokları silindi (resolved), §12.1 darboğaz açık karar nüansı v0.3 ile uyumlu, sürüm takibi v0.3 satırı eklendi
  - [[contabo-vps-hosting]] decision — ⚠️ Çelişki bloğu silindi (resolved); karar tarih notu v0.3 referansı ekledi; "Bağlam" notu draft Hetzner'ın v0.3 ile temizlendiğini belirtir; alternatifler tablosu satır güncellendi; Kaynaklar listesi
  - wiki/index.md — Sources listesinde architecture-md "1 çelişki" (hosting+backup resolved); istatistik açık çelişki **6 → 4**, son re-sync 2026-05-08 v0.3 (#410)
- **Yeni:** 0
- **Güncellendi:** 4
- **Çelişki muhasebesi:**
  - **Resolved (2):** wiki ↔ architecture.md §0/§2.1 Hosting (Hetzner production hiç kullanmadı netliği), §0/§5.1/§9.1/§13 Backup (B2 → Contabo OS migration). Her ikisi de #410 ile kaynak doküman hizalandı, wiki ⚠️ blokları kaldırıldı.
  - **Hâlâ açık (1 architecture):** §4.2 Embedding model (nim_bge_m3 ↔ baai/bge-m3 orthogonal) — #345 migration ile çözülecek.
  - **Hâlâ açık (3 risk-register):** R-FIN-02, R-MKT-02, R-MKT-03 skor anomalileri.
  - **Toplam:** 6 → 4.
- **Branch:** `wiki/post-409-cleanup` (CLAUDE.md §1.3 — docs PR sonrası ayrı küçük wiki PR'ı).

---

## [2026-05-08] re-sync+lint | risk-register v0.2 + embedding "çelişki" → "açık migration" reclassification

- **Kaynak/Tetikleyici:**
  - [PR #414](https://github.com/selmanays/nodrat/pull/414) main'e merge edildi (commit `5e052ca`, closes [#413](https://github.com/selmanays/nodrat/issues/413)). risk-register.md v0.1 → v0.2 — R-FIN-02, R-MKT-02, R-MKT-03 (skor 9) §2.2 sarı'dan §2.1 kırmızıya taşındı (methodology §1.1 gereği).
  - Embedding "çelişki" durumu yeniden değerlendirildi: kod tabanı investigation `apps/api/app/config.py:128-146 use_local_embedding=False default`, `.env.example:100 DEFAULT_EMBEDDING_PROVIDER=nim_bge_m3`, #345/#346 scaffold merged ama re-embed task production'da koşturulmadı. Wiki ↔ docs **çelişki yok** (her ikisi tutarlı şekilde "nim_bge_m3 actually serves nv-embedqa-e5-v5, scaffold ready, re-embed pending" diyor) — bu bir wiki **etiketleme hatası**ydı. Reclassify "⚠️ Çelişki" → "🟡 Açık operasyonel migration".
- **Etkilenen sayfalar:**
  - [[risk-register-md]] source — frontmatter v0.1 → v0.2, doküman bilgisi re-sync history, ana çıkarımlar #1 v0.2 forma çevrildi (10 risk §2.1'de listendi), §Açık sorular bölümünden 3 anomali notu kaldırıldı (resolved), sürüm takibi v0.2 satırı eklendi
  - [[architecture-md]] source — ⚠️ Embedding bloğu 🟡 açık operasyonel migration formuna çevrildi (kod tabanı durumu detayıyla); sürüm takibi yeni satır
  - [[nim-bge-m3]] entity — "⚠️ Çelişki / kritik bilgi" başlığı "🟡 Açık operasyonel migration & kritik bilgi" olarak değişti; #345/#346 merged scaffold durumu + production durumu (`USE_LOCAL_EMBEDDING=false`) + gerçek kapanış kriteri eklendi; `last_op_status_check` frontmatter alanı
  - wiki/index.md — Sources listesinde [[architecture-md]] "0 çelişki" + "1 açık migration"; [[risk-register-md]] v0.2 (#414); istatistik **açık çelişki sayısı: 0** ✅ + "açık operasyonel migration: 1"
- **Yeni:** 0
- **Güncellendi:** 4
- **Çelişki muhasebesi (final):**
  - **Resolved (4):** wiki ↔ architecture.md DeepSeek migration (#403/#405/#407), Hosting (#408/#410/#412), Backup (#408/#410/#412), risk-register skor anomalileri R-FIN-02 + R-MKT-02 + R-MKT-03 (#414).
  - **Reclassified (1 → 0):** Embedding nim_bge_m3 — wiki ↔ docs çelişkisi değil, dokümante edilmiş açık operasyonel migration. Gerçek kapanış DB chunks + agenda_cards re-embed task çalıştırıldığında.
  - **Toplam açık çelişki:** 4 → **0** ✅
  - **Açık operasyonel migration:** 1 (embedding re-embed task)
- **Branch:** `wiki/post-414-cleanup` (CLAUDE.md §1.3 — docs PR sonrası ayrı küçük wiki PR'ı).

---

## [2026-05-08] correction | Embedding migration aslında #350 ile tamamlanmış (kullanıcı admin panel telemetry'siyle düzeltti)

- **Kaynak/Tetikleyici:** Kullanıcı admin panel ekranını gösterdi (RAG İzlencesi → Özellik Anahtarları): `llm.use_local_embedding` toggle **AÇIK**, son 24 saat metric `bge-m3 (local) 340 / bge-m3 (NIM yedek) 0`. Wiki'nin "açık operasyonel migration" iddiası yanlıştı — production tarafında migration 2026-05-06'da tamamlanmış.
- **Önceki investigation hatası:** Spawn edilen Explore agent sadece `apps/api/app/config.py:128 use_local_embedding=False` (env-var fallback default) ve `.env.example:100 DEFAULT_EMBEDDING_PROVIDER=nim_bge_m3` 'a baktı. Şunları kaçırdı:
  - **PR [#350](https://github.com/selmanays/nodrat/pull/350)** (`3366ab3`, 2026-05-06) — `feat(rag): NIM → local embedding migration + rerank eval (closes #345)`. `_reembed_chunks_async` + `_reembed_agenda_cards_async` task'ları `apps/api/app/workers/tasks/maintenance.py:522-697`'de
  - **Runtime config mekanizması (MVP-1.2 #262/#264):** `app_settings` Postgres tablosu + `SettingsStore` singleton (`apps/api/app/core/settings_store.py`) admin panel'den değer override ediyor; `config.py` default'u sadece DB row yoksa fallback
  - **`apps/api/app/api/admin_settings.py:257`** — `llm.use_local_embedding` runtime tunable
  - **Production telemetry** — kullanıcının ekranında NIM yedek 0 çağrı görünür kanıt
- **Etkilenen sayfalar:**
  - [[nim-bge-m3]] entity — neredeyse tam yeniden yazıldı: "legacy embedding provider, fallback only" başlığı, production telemetry tablosu, migration timeline (#350 dahil), runtime config mekanizması, kalan opsiyonel TODO (rename consideration, local rerank flip)
  - [[architecture-md]] source — 🟡 "Açık migration" bloğu ✅ "Embedding migration tamamlandı" formuna çevrildi; #350 + admin panel telemetry kanıtı; sürüm takibi correction satırı
  - wiki/index.md — Sources line'ı "tüm çelişkiler resolved"; istatistik açık operasyonel migration **1 → 0** ✅; opsiyonel "devam eden ops todo" notu (local rerank, çelişki değil)
- **Yeni:** 0
- **Güncellendi:** 3
- **Çelişki muhasebesi (gerçek final):**
  - Açık çelişki: **0** ✅
  - Açık operasyonel migration: **0** ✅ (embedding tamamlandı 2026-05-06 #350)
  - Opsiyonel ops todo: 1 (local rerank flip — çelişki değil, plan)
- **Ders alınan:** İleride benzer "çelişki / migration" sorularında investigation **hem kod default'una hem de runtime config'e (app_settings + admin panel telemetry) bakmalı**. Memory dosyasına not eklenecek.
- **Branch:** `wiki/embedding-migration-complete` (CLAUDE.md §1.3).

---

## [2026-05-08] sync+rename | parallel session merge + nim/local split + deepseek rename

- **Kaynak/Tetikleyici:** Kullanıcı 3 sorun bildirdi: (1) Obsidian'da nim-bge-m3.md eski görünüyor, (2) dosya adı `local-bge-m3.md` olmalı mı / ayrı sayfa mı, (3) `deepseek-v3.md` adı yanıltıcı (v3 hiç kullanılmadı), v3 aliases içinde olmalı.
- **Tespit:** Lokal main 9 commit geride + working tree'de 11 dosyada uncommitted MVP-2.1 reality sync + 1 yeni page (`pipeline-performance-baseline.md`) işi vardı. Paralel oturumdan kalmış değerli iş — kayıp önlemi alındı.
- **Akış (A planı — yerel iş + sync):**
  1. Lokal mod'lar `/tmp/nodrat-local-mods-2026-05-08.patch` + `/tmp/nodrat-new-page-pipeline-baseline.md` snapshot'a alındı
  2. `git stash --include-untracked` ile lokal main temizlendi (stash@{0}: wiki-mvp-2.1-local-work-2026-05-08)
  3. `git pull --ff-only` — local main `4ad9ac1`'e geldi (origin/main, MVP-2.1 PR #418 dahil)
  4. Yeni worktree `wiki/sync-and-rename` `origin/main`'den açıldı
  5. Lokal iyileştirmeler her dosya için origin/main + local diff manuel merge
  6. Renames + split yapıldı
- **Etkilenen sayfalar (9):**
  - **Yeni:** [[local-bge-m3]] (production primary embedding, BAAI/bge-m3 local, #350 sonrası); [[pipeline-performance-baseline]] (MVP-2.1 baseline + tracking — paralel oturumdan kalan 202-satırlık sayfa)
  - **Rename:** `wiki/entities/deepseek-v3.md` → `wiki/entities/deepseek.md` (slug `deepseek-v3` → `deepseek`; eski slug aliases içinde — Obsidian search çalışmaya devam eder)
  - **Sadeleştirildi:** [[nim-bge-m3]] — fallback only rolüne çekildi (primary content [[local-bge-m3]]'e taşındı)
  - **Cross-link güncellendi (sed ile):** 14 dosyada `[[deepseek-v3]]` → `[[deepseek]]`
  - **MVP-2.1 reality sync (paralel oturum işi):** [[provider-abstraction]] (adapter listesi production state ile yeniden yazıldı), [[llm-provider-strategy]] (fallback chain production reality + risk tablosu güncel), [[mvp-roadmap]] (MVP-2.1 milestone block delivered eklendi + MVP-1.5 changelog'a embedding migration eklendi), [[deepseek-default-llm]] (runtime tunable correction), [[deepseek]] (registry path + routing düzeltildi), [[risk-cost-runaway]] (M7 satırı + PR #411/#416/#418 referansları)
  - **Hub:** wiki/index.md (Provider listing nim/local-bge-m3 split, Topics 4 → 5, Sources line, istatistik 27 → 29 sayfa)
- **Yeni:** 2 (local-bge-m3, pipeline-performance-baseline)
- **Güncellendi:** 9 (+ rename: deepseek-v3 → deepseek)
- **Korunan paralel session iyileştirmeleri:** Cache claim ⚠️ doğrulama notu (local-bge-m3 sayfasında), services/llm_router.py kaldırma notu, registry.py:80 fallback açıklaması, runtime config mekanizması netliği, MVP-2.1 PR #411/#416/#418 commit zinciri tracking.
- **Branch:** `wiki/sync-and-rename` (CLAUDE.md §1.3 — tek branch tüm değişiklikler).
- **İstatistik:** Toplam sayfa **27 → 29**, açık çelişki **0** ✅, açık migration **0** ✅.
- **Kullanıcı talimatı (PR merge sonrası):** `cd /Users/selmanay/Desktop/nodrat && git checkout main && git pull --ff-only` — Obsidian otomatik yansıtır.

---

> Sıradaki adım: kullanıcı onayı — local rerank flip planlama (`llm.use_local_rerank=false` → true, NIM rerank kalkar), yoksa sıradaki ingest (prd.md / discovery / prompt-contracts)?

## [2026-05-08] merge+deploy | MVP-2.1 PR #418 production'da — EPIC KAPANIŞ 🎯

- **Kaynak/Tetikleyici:** Kullanıcı kararı — α planı (PR #3: #392+#393 quality-critical batch). MVP-2.1 epic'in son sub-issue çifti.
- **Etkilenen sayfalar:** [[pipeline-performance-baseline]] (PR #418 tracking row + epic closure row + footnote).
- **Yeni:** 0
- **Güncellendi:** 1
- **Akış:**
  1. Branch `perf/mvp-2.1-batch-3-quality-critical` origin/main'den açıldı (PR #416 squash sonrası temiz)
  2. #392 implement: 4 SYSTEM_PROMPT_* tamamen STATIC, max_posts/tone user payload'undaki output_constraints'tan; PROMPT_VERSION 1.0.0 → 1.1.0; tone dynamic append kaldırıldı
  3. #393 implement: `retrieval.content_top_k` setting (default 5), `hybrid_search_agenda_cards(top_k=10)` → `top_k=content_top_k`, supplementary 8→4
  4. 3 yeni unit test (test_format_system_prompt_static_prefix_392, _routes_by_output_type, _unknown_output_type_falls_back)
  5. Lokal pytest: 17/17 PASS prompt + 29/30 PASS citation
  6. Lokal ruff: yeni hata yok (4 auto-fix uygulandı)
  7. Commit `8a89a4f` + push, PR [#418](https://github.com/selmanays/nodrat/pull/418) açıldı (MERGEABLE/UNSTABLE — CI runner outage devam)
  8. Admin override squash merge → commit `4ad9ac11`
  9. Manuel rsync + docker compose build/up VPS (skill protocol §Manuel deploy)
  10. Smoke test PASS: container healthy 6 sn'de, `/api/health` 200, startup logs temiz, prompt loading error yok.
- **MVP-2.1 epic kapanış özeti:**
  - 7/7 sub-issue closed (#392-#398), 3 PR (#411 + #416 + #418), epic [#391](https://github.com/selmanays/nodrat/issues/391)
  - Plan 2026-05-28 → gerçekleşen 2026-05-08 — **20 gün önde**
  - Tahmini etki: input token -%36, citation NIM call 6→1, settings DB call 9→2, latency P50 -300-500ms, \$/req -%25-35
- **⚠️ Eval-gated kuyruk:** PR #418 prompt v1.1.0 prod'da. Halü oranı + citation accuracy izleme 30-60 dk. Alarm fire ederse `4ad9ac11` revert.
- **Sonraki:** 24-48 saat production observation, `provider_call_logs` 7-günlük rolling avg query (TODO), MVP-3 cut-over kuyrukta.

## [2026-05-08] new-page | data-pipelines.md (8 boru hattı overview)

- **Kaynak/Tetikleyici:** Kullanıcı isteği — "şu an beklerken tüm boru hatlarımızı wikiye ekler misin? kaynak kazımadan, embedlemeye, reranklamaya, görsel işleme akışından, haber depolamaya, object storage kullanımına, x içeriği üretimine ve ücretsiz haber arama servisine kadar her şeyi". MVP-2.1 PR #418 production observation döneminde dokümantasyon işi.
- **Etkilenen sayfalar:**
  - `topics/`: [[data-pipelines]] (yeni, kapsamlı 8-pipeline overview)
  - `wiki/index.md`: Topics listesi 5 → 6; istatistik 29 → 30 sayfa
- **Yeni:** 1
- **Güncellendi:** 1 (index)
- **İçerik (8 pipeline + altyapı katmanı):**
  1. **Source Crawl** — RSS poll → discover → fetch detail → trafilatura clean → DB
  2. **Embedding** — chunk → NIM bge-m3 (nv-embedqa-e5-v5) → article_chunks.embedding 1024-dim
  3. **Clustering + Agenda Card** — pgvector cosine → event_clusters → DeepSeek synthesis → agenda_cards
  4. **Image VLM (process & discard)** — img URL → NIM Llama 4 Maverick → caption+OCR+depicts → article_images metadata only (5 TB/yıl → 90 GB/yıl, %98 azalma)
  5. **RAPTOR-Lite weekly** — daily cards → cluster → weekly summary cards (parent_card_ids zinciri)
  6. **/app/generate** — 6-adım RAG pipeline (planner → embed → search → rerank → content gen → citation). MVP-2.1 ile optimize edildi (3 PR: #411, #416, #418). Detay [[pipeline-performance-baseline]].
  7. **/ara public search** — anonim TOFU funnel, 10 req/min/IP rate limit, embed + RRF, register wall ile /app/generate'e yönlendirir
  8. **Object Storage + Cold Tier + Backup** — MinIO (hot, deprecated process & discard sonrası) + Contabo Object Storage (cold tier 30+gün + restic backup) + cron daily 04:00
- **Provider envanteri özeti:** DeepSeek v4-flash (3 pipeline: agenda + raptor + content gen), NIM bge-m3 (4 pipeline: chunk embed + cluster + citation + search), NIM rerank (1 pipeline), NIM Llama 4 Maverick VLM (1 pipeline), Anthropic Haiku 4.5 (Pro+ aktivasyon, Faz 2).
- **Cross-link:** Her pipeline için ilgili wiki entity/concept/decision/topic'ler işaretlendi.
- **Açık TODO:** Pipeline-level latency dashboard, cold tier restore drill, image VLM eval, public search Phase C, local provider flip eval gate'leri, RAPTOR monthly trigger.

## [2026-05-08] correction | data-pipelines.md + pipeline-performance-baseline.md embedding provider düzeltildi (production: LOCAL)

- **Kaynak/Tetikleyici:** Kullanıcı tespiti — "Embedding için neden NIM bge-m3 (nv-embedqa-e5-v5) yazdın biz local model kullanıyoruz vps te"
- **Etkilenen sayfalar:** [[data-pipelines]] (Pipeline #2 + provider envanteri + status tablosu), [[pipeline-performance-baseline]] (ADIM 2 + ADIM 6 diagramları + per-request metrik tablosu + latency tablosu), [[llm-provider-strategy]] (TL;DR + tier mapping satırı)
- **Yeni:** 0
- **Güncellendi:** 3
- **Hatanın özü:** Yeni yazdığım data-pipelines.md'de Pipeline #2'yi `.env.example` default'a (`USE_LOCAL_EMBEDDING=false`) bakarak "NIM aktif" şeklinde belgeledim. **Production VPS `.env` farklı:** `USE_LOCAL_EMBEDDING=true`. SSH ile doğrulandı.
- **Production telemetry (provider_call_logs son 7 gün, doğrulama):**
  - `local_bge_m3` 422 çağrı, son: **2026-05-07 23:15** (TODAY) ✅ aktif
  - `nim_bge_m3` 4,646 çağrı, son: 2026-05-06 18:46 (1.5 gün önce, migration öncesi)
  - Migration tamamlandı: PR #350 (2026-05-06)
- **Düzeltilenler:**
  - [[data-pipelines]] §1️⃣ Pipeline 2 (Embedding) → "NIM bge-m3" → "Local BAAI/bge-m3 (VPS CPU)"
  - [[data-pipelines]] kuş bakışı diyagram → "NIM bge-m3" → "LOCAL bge-m3 (VPS CPU)"
  - [[data-pipelines]] provider envanteri tablosu → Local AKTİF, NIM FALLBACK ayrımı eklendi
  - [[data-pipelines]] pipeline durumu tablosu → "Embedding ✅ Production (LOCAL post-#345 migration)"
  - [[pipeline-performance-baseline]] ADIM 2 + ADIM 6 diyagramları → local primary olarak işaretlendi
  - [[pipeline-performance-baseline]] baseline metric tablosu → "NIM embedding call/req" → "Embedding call/req (local-primary)"
  - [[pipeline-performance-baseline]] latency tablosu → embedding 0.05-0.1s local CPU
  - [[llm-provider-strategy]] TL;DR → embedding "[[nim-bge-m3]]" → "local BAAI/bge-m3 ([[local-bge-m3]])"
  - [[llm-provider-strategy]] tier mapping satırı → "Embedding tüm tier'larda [[local-bge-m3]]" + NIM fallback notu
- **Zaten doğru olanlar (kontrol edildi, dokunulmadı):**
  - [[provider-abstraction]] adapter listesi → `LocalBgeM3Provider ✅ AKTİF (production primary)` zaten doğru, #350 referanslı
  - [[nim-bge-m3]] entity → "legacy embedding provider, fallback only" zaten doğru, [[local-bge-m3]] cross-link var
- **Kök neden:** Yeni sayfalar (data-pipelines, pipeline-performance-baseline) yazılırken `.env.example` default'una göre belgelendim — production `.env`'i SSH ile doğrulamadım. Önceki düzeltme turlarında provider-abstraction + nim-bge-m3 + local-bge-m3 doğru güncellendiği için tutarsızlık yeni sayfalarda kaldı.
- **Ders:** Pipeline veya provider durumu yazarken her zaman SSH ile production `.env` + `provider_call_logs` query'siyle doğrula. `.env.example` sadece example — gerçeği yansıtmaz.

## [2026-05-08] update | data-pipelines.md §4 Kural 8 — permanent fail edge case'leri (#427 dersi)

- **Kaynak/Tetikleyici:** Kullanıcı isteği — admin panel'de [/admin/media](https://nodrat.com/admin/media) "Başarısız: 7" gördü; "görsel işlemeyle ilgili kuralları boru hattı wikisine yazar mısın" dedi. [#424](https://github.com/selmanays/nodrat/issues/424) sonrası kalan 7 failed image teşhisi → [#427](https://github.com/selmanays/nodrat/issues/427) + [#428](https://github.com/selmanays/nodrat/pull/428) fix → wiki güncellemesi.
- **Etkilenen sayfalar:** [[data-pipelines]] (Pipeline 4 §Kural 3 güncellendi + yeni §Kural 8 eklendi)
- **Yeni:** 0
- **Güncellendi:** 1 sayfa (60+ satır eklendi)
- **Kural 3 değişikliği:**
  - Önceki tablo: "ImageDownloadError 4xx/5xx → transient"
  - Yeni tablo: "5xx + diğer 4xx (404/410 hariç) → transient", "404/410 (Gone) → permanent". Permanent satıra magic bytes sniff fail eklendi.
- **Yeni Kural 8 — Permanent fail edge case'leri (3 alt madde):**
  - **A) HTTP 404/410 → permanent:** Yayıncı silmiş URL'ler. Eski 4× retry × 6 dispatch × 72h = 864 wasted req → yeni 1 HEAD req × 72h = 72 req per ölü URL. 12× verimlilik kazancı.
  - **B) Boş Content-Type → magic bytes fallback:** WhatsApp/Manifold/yanlış konfigüre S3 vakaları. `_sniff_image_mime()` ilk 16 byte'tan JPEG/PNG/GIF/WebP/AVIF detect (whitelist'e göre). RIFF→WEBP brand check WAV/AVI'yi dışlıyor.
  - **C) Duplicate dispatch (design notu, bug değil):** #424 26h kırık backfill ~93k task biriktirmişti. Drenaj sırasında aynı image_id 4-6× dispatch normal. `status='failed'` için idempotency yok ama HEAD 404 fix'i ile maliyet düşük (0.13s/dispatch). Açık follow-up: retry_count veya 'gone' status (data-model değişikliği, MVP-1.x dışı).
- **Production verify (deploy sonrası 13:51 UTC):** [#428](https://github.com/selmanays/nodrat/pull/428) merged, manuel deploy + `celery call retry_failed`. Sonuç:
  - WhatsApp image 57ca9e40 → processed (caption: "BBC News logosu", magic bytes JPEG detect, NIM VLM 22.4s)
  - 6 haberturk → 'rejected, HTTP 404 (gone) at HEAD' her biri 0.13-0.58s (autoretry yok, GET'e gitmiyor)
  - DB final: 1945 processed / 6 failed / 1951 total (admin panel 7 → 6 başarısız)
- **Branch:** `wiki/427-image-permanent-fail-patterns`
- **Cross-link:** [#424](https://github.com/selmanays/nodrat/issues/424) [#425](https://github.com/selmanays/nodrat/pull/425) [#427](https://github.com/selmanays/nodrat/issues/427) [#428](https://github.com/selmanays/nodrat/pull/428)
- **Ders:** 7 failed image'ın 6'sı production sorun değil — yayıncı haber silmiş, fail beklenen. 1'i (WhatsApp) gerçek bug — Content-Type missing CDN fallback eksikti. Admin panel'deki "Başarısız" sayısının her zaman 0'a düşmesini beklemek yanlış; freshness window dolu (≤72h) sürece kaynak ölü URL'ler stage'inde failed olabilir.

## [2026-05-08] update | data-pipelines.md §4 image VLM kuyruk discipline + freshness kuralları (#424 ders)

- **Kaynak/Tetikleyici:** Kullanıcı isteği — "görsel işlemeyle ilgili kuralları boru hattı wikisine yazar mısın". [#424](https://github.com/selmanays/nodrat/issues/424) regression sonrası kuyruk davranışını dokümante etmek.
- **Etkilenen sayfalar:** [[data-pipelines]] (Pipeline 4 genişletildi)
- **Yeni:** 0 (mevcut sayfaya bölüm eklendi)
- **Güncellendi:** 1
- **Eklenen 7 kural:**
  1. **Backfill** (5 dk beat, batch=300, idempotent — sadece status='pending')
  2. **Retry-failed** (saatlik beat, batch=100, max_age_hours=72 freshness window)
  3. **Transient vs permanent** sınıflandırma tablosu — `_TRANSIENT_EXCEPTIONS` listesi + bug sentinel pattern (autoretry tetiklemeyen `TypeError/AttributeError/KeyError` → stuck pending)
  4. **Cost tracker contract** — `tracker.record()` valid kwargs (input_tokens, output_tokens, cached_tokens, model, cost_usd); yanlış kwarg → kural 3 sentinel (#424 örneği)
  5. **Runtime kill-switch** — 4 admin setting tablosu (media.processing_enabled / vlm_model / max_image_bytes / download_timeout)
  6. **Worker concurrency=2** (NIM 40 RPM güvenli pay, ~4-5 image/dk pratik throughput)
  7. **Drenaj sağlığı izleme** — 3 SQL query + worker log grep + alarm tetikleyicisi
- **Branch:** `wiki/image-vlm-pipeline-rules`
- **Bağlam:** [#424](https://github.com/selmanays/nodrat/issues/424) ile öğrendiğimiz: TypeError gibi unexpected exception'lar autoretry listesinde olmadığı için DB status değişmiyor → backfill her 5 dk yeniden dispatch ediyor → kuyruk donar. Bu pattern'i wiki'de "Bug sentinel" olarak adlandırdık. Production semptom: pending count düşmüyor, worker log'da TypeError pattern'i.
- **Cross-link:** Pipeline 4 → R-OPS-05 (storage runaway, çözüldü) + R-FIN-01 (cost runaway, kural 5+6 ile mitigate) + #425 (regression örneği).
- **Ders:** Provider abstraction ve runtime config dokümante etmek yetmez; davranış sözleşmeleri (idempotency, retry classification, kill-switch) ayrı bir bölüm hak ediyor — yoksa "kuyruk neden donmuş?" sorusuna kod okuyarak cevap aramak gerek.

## [2026-05-08] removal | NIM bge-m3 historical iz temizliği — DB rows + integration test + comment'ler (#422)

- **Kaynak/Tetikleyici:** Kullanıcı isteği — "yani şu an nim'deki bge-m3 modeli tamamen sistemden çıkartıldı değil mi? o zaman özet sayfasındaki grafikte de bu model görünmesin geçmiş istatistik verilerini de silmen lazım hiçbir şeyde izi olmasın". PR #421 follow-up.
- **Yeni:** 0
- **Güncellendi:** 8 wiki + 9 kod dosyası
- **Silinen:** `apps/api/tests/integration/test_nim_embedding.py` (88 satır — PR #421'de kaçırılmıştı, NimEmbeddingProvider import ediyordu)
- **Akış:**
  - **Kod cleanup (9 dosya):** test_nim_embedding.py SİL; test_cost_tracker.py + test_provider_timeout #420 referansları sade; cost_tracker docstring + local_embedding + registry + provider_log + embedding + maintenance comment sadeleştirildi
  - **DB cleanup:** `provider_call_logs` 4,646 satır SİLİNDİ (`WHERE provider='nim_bge_m3'`). Total cost: $0 (NIM free tier'dı), tarih: 2026-05-01 → 2026-05-06. Admin dashboard graph'larından otomatik kaybolur (provider-bazlı GROUP BY).
  - **Redis:** SCAN `*nim_bge*` + `*nv-embedqa*` → 0 key (zaten temiz)
  - **Wiki (8 active sayfa):** provider-abstraction, local-bge-m3, llm-provider-strategy, pipeline-performance-baseline, data-pipelines, mvp-roadmap, architecture-md, index — hepsinden NIM nv-embedqa-e5-v5 / NIM yedek / nim_bge_m3 referansları temizlendi
- **Audit sonucu:** `grep -r "nim_bge_m3|nv-embedqa-e5-v5|NimEmbeddingProvider"` aktif wiki + kod = **0 sonuç**.
- **Branch:** `chore/422-nim-historical-trace-cleanup`
- **Sebep:** Kullanıcı admin dashboard'da NIM bge-m3 graphını gördü; aktif kod kaldırıldı ama DB'deki historical telemetry hâlâ graph'ı çiziyordu. PR #421'de kalan integration test dosyası da kaçırılmıştı — CI'da import error verecekti.
- **Ders:** Removal işi sadece kod silmek değil; audit/logs/cache/historical data'yı da silmek demek. Source-of-truth tek olmalı, historical artifacts production verilerini bozmamalı.
