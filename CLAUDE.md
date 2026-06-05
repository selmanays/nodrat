# Nodrat — Claude Code Şeması

Bu dosya Claude Code (ve genel olarak LLM agent'lar) için **proje düzeyinde sözleşmedir**. Üç şeyi tanımlar:

1. **Repo nasıl organize** (üç katman: kaynak / wiki / indeks).
2. **Wiki katmanı (`wiki/`) nasıl sürdürülür** — ingest, query, lint protokolleri.
3. **Mevcut skill'lerle ilişki** — geliştirme/test workflow'larıyla nasıl bir arada çalışır.

> **Önce bunu oku:** Yeni bir konuşma açıldığında bu dosyayı, kök [`INDEX.md`](INDEX.md)'yi ve [`wiki/index.md`](wiki/index.md)'yi tara. **Feature/kod işine başlayacaksan önce §0 (Mimari Bootstrap).**

---

## 0. Mimari / Feature Development Bootstrap

> **Kod/feature işine başlamadan ÖNCE oku** — modular monolith v1/v2/v3 (#18/#19/#20) + housekeeping sonrası güncel düzen. (Yalnız wiki bakımı yapıyorsan §1-8'e geç.)

**Minimum okuma seti (feature öncesi):**
1. [`wiki/topics/architecture-final-state-2026-05.md`](wiki/topics/architecture-final-state-2026-05.md) — repo yapısı + 16 import-linter contract + **§5 feature-dev kuralları** + invariants.
2. [`wiki/decisions/modular-monolith-boundary.md`](wiki/decisions/modular-monolith-boundary.md) + [`wiki/decisions/import-direction-rules.md`](wiki/decisions/import-direction-rules.md) — domain katmanları + izinli import yönleri.
3. [`wiki/log.md`](wiki/log.md) son 5-10 giriş + [`wiki/index.md`](wiki/index.md) — son aktivite + katalog.

**Kod yerleşim karar ağacı:**
- Tek domain'e ait logic → `app/modules/<domain>/` (kernel / middle / business seviyesine uy).
- Pure primitive / domain-bağımsız kernel (I/O-suz) → `app/shared/` (Seviye 0 leaf).
- Cross-domain BFF / orchestration (birden çok domain import eden route) → `app/api/` aggregator — **zorla modüle taşıma.**
- `app/core/` **model-free** kalır (T7); retrieval saf facade + `core/_retrieval_*` submodülleri.
- **Model ownership** → `app/modules/<x>/models.py`. Documented flat exception: `FailedJob` + `AdminAuditLog` (`app/models/job.py`, cross-cutting observability; domain→ops contract).

**🛑 HARD-STOP (DUR + onay):**
- **Boundary ihlali** — `core→modules` · `shared→{modules,core,api,models}` · `domain→ops` · `accounts→business` · `rag→{crawler,generations}` · `sources→other-domain`. import-linter **16 contract CI hard-gate** (CI otoriter; local lint-imports cache yanıltabilir).
- **Schema / migration / DB-data mutation** (backward-incompatible = zero-downtime ihlali; alembic check strict gate aktif).
- **Embedding / RAG-index / chunk / vector mutation** (rechunk / reembed / toplu-backfill / truncate) — geri-dönülmez veri.
- **Production data touch / manuel task trigger.**
- **High-caution repo ayarı** (LICENSE / visibility / branch-protection / SECURITY / releases) → yalnız decision-backlog, kullanıcı kararı.
- **Belirsiz ownership / mimari karar** — tahmin etme, sor.

**Deploy:** code-PR → FULL deploy; docs/wiki-only (`**/*.md` · `wiki/**` · `docs/**`) → SKIP (#1114 two-job gating). Deploy "cancelled/failure" → çoğu kez `/health` smoke false-fail → SSH ile doğrula, **körlemesine re-deploy yok**.

> Tam detay: [[architecture-final-state-2026-05]] §5 + bu dosyanın §6 hard kuralları (aşağıda).

---

## 1. Üç katman

```
nodrat/
├── INDEX.md          ← İnsan tarafından sürdürülen kanonik DOKÜMAN indeksi.
├── CLAUDE.md         ← Bu dosya. LLM iş akışları + sözleşme.
├── docs/             ← KAYNAK katmanı. 32 markdown, 8 kategori. Immutable kanonik.
│   ├── product/      (PRD, IA)
│   ├── strategy/     (discovery, competitive, pricing, metrics, risk, economics)
│   ├── engineering/  (architecture, data-model, api, prompt, threat)
│   ├── design/       (UX wireframes, design system)
│   ├── legal/        (compliance, ToS, privacy, KVKK, ROPA, DPO, incident)
│   ├── validation/   (research findings)
│   ├── research/     (alpha invite, success metrics)
│   └── operations/   (deployment manual)
└── wiki/             ← İKİNCİ BEYİN. LLM yazar/günceller.
    ├── index.md      Wiki sayfa kataloğu
    ├── log.md        Kronolojik bakım kaydı
    ├── README.md     Vault girişi
    ├── SETUP.md      Obsidian + MCP kurulum
    ├── entities/     Somut "şey"ler (provider, persona, servis, tool)
    ├── concepts/     Soyut kavramlar (metric, technique, rule)
    ├── topics/       Sentez / karşılaştırma / timeline
    ├── decisions/    Locked kararlar
    ├── plans/        Kalıcı mimari/refactor master planlar (geçici not değil)
    ├── sources/      Her docs/* için 1 özet sayfası
    └── _templates/   Sayfa şablonları (entity, concept, topic, decision, source)
```

### 1.1 Hangi katmana yazılır?

| Katman | LLM yetkisi | İnsan yetkisi | Doğruluk önceliği |
|---|---|---|---|
| `docs/` | **Sadece okuma.** Asla yazma. | Tam yazma. PR + INDEX güncelleme. | Doğruluk kaynağı (kanonik). |
| `wiki/` | **Tam yazma.** Yapı + içerik LLM kontrolünde. | Okuma + yönlendirme. | Türetilmiş; çelişkide `docs/` kazanır. |
| `INDEX.md` | Sadece okuma (öneriler `wiki/` log'una). | Tam yazma. | Kanonik doküman indeksi. |

> **Hard kural:** `docs/` altındaki bir dosyayı LLM olarak değiştirmeyeceksin. Eğer kaynak güncellenmeli ise (örn. eskimiş bilgi), `wiki/log.md`'ye not düş ve kullanıcıya bildir. `nodrat-dev` skill'i bu güncellemeyi GitHub akışıyla yapar.

### 1.2 Slug ve isimlendirme

- Dosya adı: `kebab-case` (Türkçe karakterler ASCII'ye: `ş→s`, `ı→i`, `ç→c`, `ö→o`, `ü→u`, `ğ→g`).
- İçerik dili: Türkçe (Nodrat dokümanlarıyla tutarlı).
- Wiki-link: `[[slug]]` veya `[[slug|Türkçe görünen ad]]`.
- Asla iki sayfa aynı slug'a sahip olmaz. Çakışırsa: kategori prefix ekle (`provider-deepseek-v3` vs `concept-deepseek-cost`).

### 1.3 Paralel worktree write disiplini (KRİTİK)

`wiki/` klasörünün **birincil amacı:** birden fazla Claude Code agent'ın (farklı worktree'lerde paralel çalışan) projeyi anlamada **tek doğruluk kaynağı** olmasıdır. Bu disiplin olmadan worktree-A'da öğrenilen bir karar worktree-B'deki agent'a görünmez → kafa karışıklığı geri döner.

**Hard kurallar:**

1. **Wiki yazma yetkisi sadece `main` branch'inde** (veya geçici olarak dedicated `wiki/*` branch'inde). Feature worktree'lerinde wiki **read-only** kullanılır.
2. **Yeni ingest, lint, query-archive operasyonları** ayrı bir kısa-ömürlü branch'te yapılır, hızla PR'lanıp main'e merge edilir.
3. **Feature worktree'sinde wiki güncellemesi gerekirse** (örn. yeni locked decision çıktı, çelişki tespit edildi):
   - Sadece o sayfa için "TODO" notunu kendi turn'ünde tut,
   - Feature PR merge edildikten sonra ayrı bir wiki PR ile main'e ekle.
   - Bu, feature PR'ı şişirmemek + paralel write conflict'i önlemek için.
4. **Yeni Claude Code session başladığında** agent şu sırayı uygular:
   - Kök [`CLAUDE.md`](./CLAUDE.md) auto-loaded (her zaman) → bu dosyayı okur.
   - Kök [`INDEX.md`](./INDEX.md) — kanonik doküman indeksi.
   - [`wiki/index.md`](./wiki/index.md) — wiki sayfa kataloğu (mevcut ne var?).
   - [`wiki/log.md`](./wiki/log.md) son 5-10 girişi — ne yapıldı son zamanlarda?
   - Sonra ilgili sayfaları takip eder.
5. **Wiki dosyalarına git merge conflict** mümkün olduğunca azaltılmalı: `wiki/index.md` ve `wiki/log.md` en sık çatışan dosyalar — bu yüzden ingest PR'ları **küçük tutulur ve hızla merge edilir**.

---

## 2. Sayfa anatomisi

Her wiki sayfası bir Obsidian-uyumlu **YAML frontmatter** ile başlar. Şablonlar [`wiki/_templates/`](wiki/_templates/) altında. Frontmatter zorunlu alanları:

```yaml
---
type: entity | concept | topic | decision | source
title: "İnsan-okunur başlık"
slug: "kebab-case-slug"
status: live | draft | deprecated | planned
created: YYYY-MM-DD
updated: YYYY-MM-DD
sources:
  - "docs/.../...md§X"   # her zaman section ile (§1.2 vb.)
tags: []
aliases: []
---
```

### 2.1 Bölüm sırası (zorunlu)

1. **TL;DR** — 1-3 cümle. Sayfanın özünü taşır.
2. **Tanım / Bağlam** — ne olduğu, neden Nodrat'ta var.
3. **Detay bölümleri** — sayfa tipine göre değişir (entity için "kullanım", concept için "formül/kural", decision için "alternatifler", topic için "ana içerik").
4. **İlişkiler** — `[[wiki-link]]` ile diğer sayfalara backlink.
5. **Kaynaklar** — `docs/...` dosyalarına markdown linkleri, **her zaman section numarasıyla** (`§3.1`).

### 2.2 Sentez kalitesi

- TL;DR olmadan sayfa tamamlanmış sayılmaz.
- Her iddia bir kaynağa bağlı olmalı (kaynak yoksa "(LLM çıkarımı)" notuyla işaretle).
- Çelişki tespit ettiğinde sayfaya bir **`> ⚠️ Çelişki:`** bloğu ekle ve hangi kaynakların neyi söylediğini yaz.
- Tahmin yapma. Belirsizlik varsa "Açık sorular / TODO" bölümüne ekle.

---

## 3. İş akışları

### 3.1 INGEST — yeni kaynak içe alma

**Tetikleyici:**
- Kullanıcı: "wiki ingest [`docs/.../...md`]" der.
- VEYA: `docs/` altında yeni/güncellenmiş bir doküman fark edilir (git diff sonrası).

**Adımlar:**

1. **Oku.** Kaynak dokümanı baştan sona oku. Section haritasını çıkar.
2. **Mevcut wiki taraması.** Bu kaynak daha önce mi ingest edildi?
   - Var: ilgili `wiki/sources/<slug>.md` aç, `source_version` karşılaştır → sürüm değişikliği takibi tablosunu güncelle.
   - Yok: yeni source sayfası yarat.
3. **Varlık/kavram/karar çıkarımı.** Aşağıdakiler için liste yap:
   - **Entities:** isim verilen somut "şey"ler (provider, persona, servis, dosya, platform).
   - **Concepts:** soyut kavramlar (metric, technique, rule, framework).
   - **Decisions:** "✅ locked" işaretli veya yapılan tercihler.
4. **Çakışma kontrolü.** Her aday için `wiki/index.md` ve dosya sistemi (Grep) ile kontrol et. Var ise: yeni sayfa yaratma, mevcut sayfayı güncelle.
5. **Sayfa oluşturma/güncelleme.** Şablondan yarat. Frontmatter doldur. Bölümleri kaynaktan beslenerek yaz. **Her sayfa minimum 2 backlink içerir** (kaynak + en az 1 ilişkili wiki sayfası).
6. **Cross-update.** Yeni sayfanın bağlandığı diğer sayfalarda backlink eksikse onları da güncelle (bidirectional link).
7. **`wiki/index.md` güncelle.** Yeni/değiştirilen her sayfa için satır ekle/güncelle. İstatistik bloğunu güncelle.
8. **`wiki/log.md` ekle.**
   ```markdown
   ## [YYYY-MM-DD] ingest | <kaynak başlık>
   - **Kaynak/Tetikleyici:** docs/.../...md (v0.X)
   - **Etkilenen sayfalar:** [[slug-1]], [[slug-2]], ...
   - **Yeni:** N
   - **Güncellendi:** N
   - **Notlar:** sürpriz bulgu, çelişki, eksiklik
   ```
9. **Rapor.** Kullanıcıya 3-5 satır özet: kaç sayfa yaratıldı, hangi entity/concept'ler eklendi, açık sorular.

> **Pilot kuralı:** İlk ingest'te bir dokümandan 8-15 sayfa beklenir. 5'ten azsa kaynağı yeterince ezmedin. 25'ten fazlaysa granülasyon çok ince — birleştir.

### 3.2 QUERY — wiki'ye soru sorma

**Tetikleyici:**
- Kullanıcı doğrudan soru sorar (kaynaklar değil, anlama/sentez).

**Adımlar:**

1. **`wiki/index.md` tara.** İlgili görünen sayfaları belirle (kategori + slug + 1-cümle özet üzerinden).
2. **Sayfaları oku.** İlgili 3-7 sayfayı `Read` ile aç.
3. **Eksik bağlam varsa kaynaklara in.** `wiki/sources/<slug>.md` üzerinden ilgili `docs/...` dosyasının ilgili section'ına git.
4. **Sentezle.** Her iddiayı `[[slug]]` veya `docs/...` linki ile bağla. Quote yapma — kendi kelimelerinle yaz.
5. **Yanıt değerli mi?** Eğer cevap:
   - Yeni bir karşılaştırma içeriyorsa → `wiki/topics/<slug>.md` olarak arşivle.
   - Yeni bir locked karara işaret ediyorsa → kullanıcıya sor: "Bunu locked decision olarak kaydedelim mi?"
   - Sadece bilgi getiriyorsa → arşivlemeye gerek yok.
6. **`wiki/log.md` ekle (sadece arşivlenirse):**
   ```markdown
   ## [YYYY-MM-DD] query | <soru özeti>
   - **Soru:** ...
   - **Yanıt sayfası:** [[topic-slug]]
   - **Kullanılan sayfalar:** [[s1]], [[s2]], ...
   ```

### 3.3 LINT — periyodik sağlık taraması

**Tetikleyici:**
- Kullanıcı: "wiki lint" der.
- VEYA: 10+ ingest sonrası otomatik öneri.

**Kontrol listesi:**

1. **Yetim sayfa.** Hiçbir sayfaya backlink'i olmayan sayfa. → kullanıcıya bildir, silme önerisi yapma.
2. **Kırık wiki-link.** `[[slug]]` referansı ama hedef yok. → düzelt veya kullanıcıya işaret et.
3. **Eksik backlink.** Sayfa A, B'yi ilgilendiriyor ama B'de A'ya link yok. → ekle.
4. **Çelişki.** İki sayfa aynı şey için farklı değer söylüyor → her iki sayfaya da `> ⚠️ Çelişki:` bloğu ekle, log'a not düş.
5. **Eskimiş iddia.** Kaynağın güncel sürümüyle wiki'deki bilgi uyuşmuyor (`source_updated` ile `wiki updated` karşılaştır) → güncelle.
6. **Adı geçen ama sayfası olmayan kavram.** Sayfalarda 3+ kez geçen ama kendi sayfası olmayan kavram → entity/concept oluşturma adayı.
7. **Boş frontmatter alanı.** Zorunlu alanlar boş kalmamalı.
8. **Veri boşluğu.** Section'da "TODO" veya "?" varsa → kullanıcıya sor (web araması yapılabilir).

**Çıktı:** `wiki/log.md`'ye lint kaydı + 5-10 satır özet rapor (kullanıcıya).

---

## 4. Obsidian + MCP

### 4.1 Erişim katmanları

LLM wiki'ye iki şekilde erişebilir:

1. **Doğrudan dosya** (her zaman): `Read`, `Edit`, `Write`, `Grep`, `Bash`. Hızlı, güvenli, ek setup gerektirmez.
2. **Obsidian MCP server** (opsiyonel ama önerilir): `@bitbonsai/mcpvault` üzerinden. Avantajlar:
   - BM25 tabanlı semantik arama + LLM reranking
   - Frontmatter sorgulama, tag operasyonları
   - Surgical patch (başlık altı patch — full overwrite riskini azaltır)
   - Vault istatistikleri, batch okuma

> **Default kural:** Hızlı işlemler için doğrudan dosya tool'larını kullan. Search-heavy işler (lint, complex query) için MCP'yi tercih et.

### 4.1.1 Path konvansiyonu (kritik)

Obsidian MCP tool'ları (`mcp__obsidian__*`) path'leri **vault kökünden relative** ister (vault = `nodrat/` repo kökü):

```
✅ wiki/decisions/deepseek-default-llm.md
✅ wiki/index.md
✅ INDEX.md
✅ docs/engineering/architecture.md

❌ /Users/selmanay/Desktop/nodrat/wiki/...   (mutlak path)
❌ /wiki/decisions/...                        (leading slash)
❌ ./wiki/decisions/...                       (./ prefix)
```

Mutlak path veya leading slash → 404 / "vault kökü farklı görünüyor" hatası → gereksiz retry. İlk denemede doğru relative path'i kullan.

### 4.2 Veri kaybı uyarısı

Obsidian Local REST API plugin'in bilinen bir bug'ı: POST endpoint metadata cache miss durumunda **append'i overwrite yapabilir**. Önlemler:

- MCP `write_note` yerine **`patch_note`** kullan (mümkünse).
- Toplu write öncesi git working tree temiz olsun (`git status` → clean). Hata olursa `git restore` ile geri al.
- Büyük ingestler doğrudan dosya tool'ları (`Edit`, `Write`) ile yapılır — MCP yerine. MCP daha çok read/search için.

### 4.3 Setup

Kullanıcı tarafından manuel yapılması gereken adımlar [`wiki/SETUP.md`](wiki/SETUP.md)'de.

---

## 5. Mevcut skill'lerle ilişki

Bu CLAUDE.md `nodrat-dev` ve `nodrat-test` skill'leriyle **çakışmaz**, tamamlar:

| Skill / dosya | Amacı | Tetiklenme |
|---|---|---|
| `nodrat-dev` ([SKILL.md](.claude/skills/nodrat-dev/SKILL.md)) | Kod/doküman değişikliği — issue/branch/PR akışı | Kullanıcı "nodrat-dev ..." der |
| `nodrat-test` ([SKILL.md](.claude/skills/nodrat-test/SKILL.md)) | Test/eval koşumu | Kullanıcı "nodrat-test ..." der |
| `CLAUDE.md` (bu dosya) | Wiki bakım + genel proje sözleşmesi | Her konuşma başında otomatik |

**Etkileşimler:**

- `nodrat-dev` ile `docs/` değişti → `wiki/` ingest gerekir (LLM bu güncellemeyi sonraki turda yapar veya kullanıcı "wiki ingest" der).
- `nodrat-test` LLM eval'lerinden çıkan içgörüler → `wiki/topics/eval-findings-YYYY-MM.md` olarak arşivlenebilir.
- Yeni `decision` (örn. provider değişikliği) `nodrat-dev` üzerinden `INDEX.md §4`'e eklenmeli; `wiki/decisions/` ile **eşzamanlı** güncelle.

---

## 6. Hard kurallar (özet)

```text
✅ docs/ asla LLM tarafından yazılmaz.
✅ Her wiki sayfası: frontmatter + TL;DR + Kaynaklar zorunlu.
✅ Her iddia kaynağa bağlı (yoksa "(LLM çıkarımı)" işareti).
✅ Çelişki = "⚠️ Çelişki:" bloğu + log'a not.
✅ Slug = kebab-case, ASCII; içerik = Türkçe.
✅ Her ingest sonrası: index.md + log.md güncellenir.
✅ Bidirectional backlink: A→B varsa B'de A linki olmalı.
✅ MCP write için patch_note tercih, full POST riskli.
✅ docs/ değişiminde wiki ingest geç değil → mümkünse aynı turda.
✅ Wiki write SADECE main veya dedicated wiki/* branch'inde (§1.3).
✅ Yeni session başlangıcı: CLAUDE.md → INDEX.md → wiki/index.md → wiki/log.md (§1.3).
🛑 Feature worktree'sinde wiki dosyasına yazma — TODO notu tut, ayrı PR aç.
🛑 Tahmin/uydurma yok. Belirsizlik → "Açık sorular".
🛑 Quote yok. Kendi kelimenle yaz (kopyalama ≥15 kelime ⇒ kaynak linki).
🛑 wiki/ commit'inde docs/ değişikliği karıştırma (ayrı PR).
```

---

## 7. Hızlı komut sözlüğü

Slash command (`.claude/commands/wiki-*.md`) ile veya doğal dille tetiklenebilir:

| Slash command | Doğal dil eşdeğeri | LLM yapar |
|---|---|---|
| `/wiki-ingest <path>` | "wiki ingest \<path>" | §3.1 protokolü |
| `/wiki-ingest` (boş) | "sıradaki ingest" | log son notlarından öneri sun |
| `/wiki-query <soru>` | "wiki query: \<soru>" | §3.2 protokolü |
| `/wiki-lint` | "wiki lint" | §3.3 protokolü (8 kontrol) |
| `/wiki-status` | "wiki ne durumda" | sayfa sayısı + son aktivite + açık çelişki + öneri |

Diğer doğal dil ifadeleri:

| Kullanıcı der | LLM yapar |
|---|---|
| "wiki ingest all" | `docs/**/*.md` üzerinde sıralı §3.1 (uzun iş — `/loop` ile periyodik tetikleyici) |
| "wiki ne içeriyor" | `index.md` özeti |
| "wiki son aktivite" | `log.md` son 10 satır |
| "wiki [[slug]]" | İlgili sayfayı oku + özetle |
| "wiki ne eksik" | Lint'in "veri boşluğu" + "yetim" + "eksik kavram" çıktısı |

### Otomatik wiki status injection

`.claude/settings.json` SessionStart hook'u her yeni Claude Code session açıldığında `wiki/index.md` istatistik bloğu + `wiki/log.md` son 3 işlem başlığını **otomatik** context'e enjekte eder. Agent talimat takibine gerek kalmadan deterministik olarak wiki durumunu görür.

Hook'u devre dışı bırakmak için: `.claude/settings.local.json`'da `"hooks": {"SessionStart": []}` override yaz.

---

## 8. Konvansiyonlar (genel proje)

`docs/`'tan miras alınan konvansiyonlar (INDEX §7):

```text
- Tüm dokümanlar Markdown (.md)
- Türkçe primary, gerekirse İngilizce kavramlar
- Tarih: ISO 8601 (2026-05-07)
- Para: TL primary, USD secondary
- Section: §1.2.3 formatında
- Cross-reference: "Discovery §3.6" → docs/strategy/discovery-validation.md §3.6
```

`wiki/`'ye özel ek konvansiyonlar:

```text
- Slug: kebab-case ASCII (kategori prefix opsiyonel)
- Wiki-link: [[slug]] veya [[slug|Türkçe başlık]]
- Frontmatter: YAML, zorunlu alanlar §2'de
- Backlink: bidirectional zorunlu
- Dosya kaynak referansı: relative path + section (§X)
- Görseller: wiki/assets/ altında, relatif link
```

---

**Sürüm:** v1.0 (2026-05-07) — ilk yayın, LLM Wiki örüntüsünün Nodrat'a uygulanması.
