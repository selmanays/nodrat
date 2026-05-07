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

## [2026-05-08] lint+update | DeepSeek migration ailesi tam temizlendi

- **Kaynak/Tetikleyici:** İlk turdan sonra kullanıcı "hata kalmasın wiki'de" istedi. DeepSeek migration (NIM/v3.1-terminus → native API/v4-flash) wiki ailesinde 5 ek dosyada faktüel referans bulundu.
- **Etkilenen sayfalar:** [[deepseek-v3]] (entity, neredeyse tam yeniden yazıldı), [[provider-abstraction]] (concept, adapter listesi + routing pseudocode), [[architecture-md]] (source, 2 ana çıkarım + yeni ⚠️ Çelişki bloğu + sürüm takibi), [[nim-bge-m3]] (entity, "ortak API key" iddiası düzeltildi), [[llm-provider-strategy]] (topic, TL;DR + cost tablosu + risk tablosu yeniden yazıldı), [[mvp-1-scope-lock]] (decision quote), [[claude-haiku-premium-llm]] (routing pseudocode model adı), wiki/index.md (entity + decision listing açıklamaları).
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
- **Etkilenen sayfalar:** [[deepseek-default-llm]] (⚠️ blok kaldırıldı + Kaynaklar listesi güncellendi), [[deepseek-v3]] (Kaynaklar listesi "(eskimiş)" notları temizlendi), [[architecture-md]] (frontmatter v0.1 → v0.2, ana çıkarımlar #3 yeniden yazıldı, ⚠️ DeepSeek bloğu kaldırıldı, sürüm değişikliği takibi v0.2 satırı eklendi, "üretilen wiki sayfaları" listesi temizlendi), wiki/index.md (istatistik: çelişki 7 → 6, son re-sync eklendi).
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

> Sıradaki adım: kullanıcı onayı — risk-register skor anomalileri (R-FIN-02, R-MKT-02, R-MKT-03) için ayrı `nodrat-dev` görevi, kalan 1 architecture çelişkisi için #345 migration takibi, yoksa sıradaki ingest (prd.md / discovery / prompt-contracts)?
