---
title: Wiki Log — Kronolojik Kayıt
type: hub
updated: 2026-05-08
---

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
  - `entities/`: [[deepseek-v3]], [[claude-haiku-4-5]], [[nim-bge-m3]], [[contabo-vps]], [[celery-worker]]
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

> Sıradaki adım: kullanıcı onayı — sıradaki ingest mi (prd.md / discovery / prompt-contracts), wiki commit mi, lint mi?
