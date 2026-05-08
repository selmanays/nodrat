---
title: Wiki Log — Kronolojik Kayıt
type: hub
updated: 2026-05-08
---
<!-- En son giriş yukarıda (#440 close-out + 2 yeni locked decision) -->


# Wiki Log

Sadece-ekleme (append-only) kronolojik kayıt. LLM her `ingest`, `query` (arşivlenen) ve `lint` operasyonu sonrası buraya bir kayıt ekler.

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
