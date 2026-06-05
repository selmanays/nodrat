---
type: topic
title: "GitHub Repository Housekeeping Audit (2026-05)"
slug: github-housekeeping-audit-2026-05
status: live
created: 2026-05-31
updated: 2026-05-31
sources:
  - "wiki/topics/architecture-final-state-2026-05.md"
  - "wiki/plans/modular-monolith-transition-master-plan.md"
tags:
  - github
  - housekeeping
  - repo-hygiene
  - open-source
aliases:
  - github-housekeeping
  - repo-hygiene-audit
---

# GitHub Repository Housekeeping Audit (2026-05)

> **TL;DR:** Modular monolith transition (#18/#19/#20) kapandıktan sonra repo'nun **GitHub'da görünen yüzü** read-only denetlendi (2026-05-31). **İç mühendislik disiplini A-sınıfı** (16 import-linter contract + alembic strict gate + migration tests + issue/PR templates + 190-sayfa wiki) ama **dış-yüz C-sınıfı** (7 stale açık PR, 2 stale-open milestone, 51 label/iki-nesil, README MVP-1.4'te donmuş, LICENSE/topics yok, **public repo + "private/all-rights-reserved" README çelişkisi**). **Profesyonellik puanı: 5.5/10.** Kontrollü housekeeping (HK-0..6) ile 8+'a çıkarılabilir; high-caution kalemler (LICENSE/visibility/branch-protection/SECURITY) kullanıcı kararına bırakıldı.

## 1. Profesyonellik skoru + executive summary

| Boyut | Not |
|---|---|
| **İç disiplin** | A — CI boundary (16 contract) + alembic diff=0 strict + migration tests + conventional PR + templates + wiki |
| **Dış yüz** | C — stale PR/milestone/README, label kaosu, eksik community-health dosyaları |
| **Genel** | **5.5/10** — "ciddi ve aktif" ama "düzenli ve davetkâr değil" |

## 2. Mevcut GitHub state (kanıt, 2026-05-31)

| Boyut | Durum |
|---|---|
| Issue | 35 açık / 408 kapalı; **12 milestone'suz açık** |
| Milestone | 21 toplam; 7 açık (2 **stale-open**: #1 MVP-1 0/67, #11 MVP-1.6 0/1) |
| PR | **7 açık, hepsi 2026-05-10→18 stale, mergeable=UNKNOWN**; son merge'ler conventional+temiz |
| Label | **51** (GitHub-default 9 + eski `type:`/`priority:`/`area:`/`phase:`/`mvp-*` ~33 + yeni dönem 9) |
| Community | README ✅ CONTRIBUTING ✅ CHANGELOG ✅ / LICENSE ❌ CODE_OF_CONDUCT ❌ SECURITY ❌ |
| Templates | Issue (bug/feature/phase/tracking) ✅ + PR (default+refactor) ✅ |
| Repo meta | desc **stale** ("MVP-1 hazırlık fazı") · topics **YOK** · license **YOK** · visibility **PUBLIC** |
| Releases/tags | **0 / 0** · branch protection (main) **YOK** (404) |

## 3. Major inconsistencies

1. 🔴 **Public repo + README "Private repo, tüm hakları saklıdır" + LICENSE yok** — açık-kaynak iddiasıyla zıt (high-caution; IP/SLM-moat stratejisiyle ilgili olabilir).
2. 🔴 **README MVP-1.4'te donmuş** — badge "MVP-1.4 delivered / next MVP-1.5"; modular monolith + MVP-1.5/1.6/1.7/1.8 yok; footer "Durum: MVP-1.4".
3. 🔴 **7 stale açık PR** (mergeable=UNKNOWN) — bakımsız izlenimi.
4. 🟡 **2 stale-open milestone** (#1, #11 = %100 kapalı ama açık).
5. 🟡 **51 label iki nesil** — `type:bug`↔`bug`, `type:docs`↔`documentation`, `type:feature`↔`enhancement` duplicate; 4 blocking-label.
6. 🟡 repo description stale; CHANGELOG modular-monolith içermiyor (0 eşleşme); README'de architecture-final-state/wiki linki yok.
7. ⚪ topics/LICENSE/releases/branch-protection/CODE_OF_CONDUCT/SECURITY yok; 12 milestone'suz açık issue triage edilmemiş.

## 4. Issue triage özeti (35 açık)

> Modular-monolith dışı (RAG/pivot/payment) issue'ların aktif-mi-stale-mi durumu kod-kanıtıyla doğrulanmadı → çoğu **needs-verification**; mass-close ÖNERİLMEDİ.

- **keep-open:** #1421 (P6.1 backlog), #487/#473/#471/#49/#48/#47 (Legal #6), #448/#384 (MVP-3 #3), #64/#63/#62 (Faz 5 #5)
- **convert-to-tracking:** #1080 (T1 master-plan perpetual)
- **needs-review:** #1109 (repo-sync)
- **needs-verification → muhtemelen close:** #1033 (11 test regresyon; şimdi 1189 pass), #1006 (tool_choice → #1411 superseded?)
- **needs-verification:** #1003/#1001/#983/#982/#981/#980 (chat-cache MVP-1.8), #622/#620/#619/#255 (RAG features), #1022/#1021 (pivot)
- **relabel + milestone/backlog:** #778/#760/#735/#612/#461/#328/#250 (milestone'suz)

## 5. Milestone triage özeti

- **close (stale-open):** #1 MVP-1 (0/67), #11 MVP-1.6 (0/1)
- **keep-open:** #3 MVP-3 (2/33), #5 Faz 5 (3/0), #6 Backlog Legal (6/1)
- **needs-verification:** #16 MVP-1.8 RAG (11/29), #17 Pivot (2/17)
- **örnek profesyonel (closed):** #18/#19/#20 Modular Monolith v1/v2/v3

## 6. PR hygiene

- **Son merge'ler:** conventional commit + zengin açıklama + "FULL/SKIP deploy + CI + SSH verify" kanıtı → örnek ✅
- **7 stale açık PR:** #1009/#1008 (#927 Faz-C docs/wiki), #764 (Jina reranker), #663 (alembic down_revision), #658 (entity boost), #641 (source attr), #557 (Contabo storage). Çoğu modular-monolith öncesi; bir kısmı muhtemelen superseded → **per-PR needs-verification** (rebase/merge veya kanıtlı close).

## 7. Label taxonomy (51 → ~22 canonical önerisi)

- **type:** bug · enhancement · documentation · refactor · test · infra · legal · research (eski `type:*` merge)
- **priority:** critical/high/medium/low (koru)
- **area:** backend/frontend/db/llm/rag (worker/devops merge)
- **status:** blocked · ready · in-progress · backlog · tracking (`blocker`+`blocked-external`→`blocked`)
- **special:** architecture · modular-monolith · god-file · runtime-sensitive · pivot · locked · ci · good-first-issue · help-wanted · duplicate · wontfix
- **sil/arşivle:** `phase:0..6` (milestone+area yeterli), `mvp-1/2/3` (milestone var), `type:bug/docs/feature` (default'a merge), `invalid`

## 8. Repo profile / README / templates

- README (206, 13 bölüm): yapı iyi (Pozisyon/Setup/Test/Doküman-haritası) ama **stale** (MVP-1.4 + "private" lisans + footer + modular-monolith linki yok).
- LICENSE ❌ (public → de facto all-rights-reserved); CODE_OF_CONDUCT/SECURITY ❌; topics ❌; releases/tags 0; branch protection yok.
- CONTRIBUTING ✅; CHANGELOG ✅ (modular-monolith eksik); Templates ✅ (güçlü, korunmalı).

## 9. Wiki ↔ GitHub consistency

- **Güçlü:** wiki master-plan §13 + architecture-final-state, GitHub issue/milestone state ile **uyumlu** (v126 cleanup ile hizalandı).
- **Zayıf:** GitHub→wiki backlink (README wiki'ye link vermiyor); README+CHANGELOG wiki-gerçeğinin gerisinde.

## 10. Housekeeping roadmap (HK-0..6) — execution durumu

| Sıra | İş | Risk | Durum (2026-05-31) |
|---|---|---|---|
| HK-0 | Bu audit'i wiki'ye kaydet (bu sayfa) | Safe | ✅ DONE (PR #1426 v127) |
| HK-1 | repo description + topics güncelle | Safe→Moderate | ✅ DONE (desc + 9 topic) |
| HK-2 | README stale fix + wiki/modular-monolith link (lisans NÖTR) | Moderate | ✅ DONE (PR #1427) |
| HK-3 | 7 stale PR triage (kanıtlı close / keep-open) | Moderate | ✅ DONE (4 closed #1009/#1008/#663/#764 + 3 keep-open #658/#641/#557) |
| HK-4 | Milestone #1 + #11 close | Moderate | ✅ DONE (stale-open closed) |
| HK-5 | 12 milestone'suz issue triage | Moderate | ✅ DONE (2 closed #1033/#1109 + 10 keep-open) |
| HK-6A | Label taxonomy dry-run (impact analysis) | Safe (rapor) | ✅ DONE (51-label kullanım matrisi; **Yol B** seçildi) |
| HK-6B-Lite | Additive label temizliği | Safe | ✅ DONE (tracking+security + #1080/#1421 + 9 açıklama) |
| HK-6C | duplicate merge (güvenli olanlar) | Moderate | ✅ KISMİ DONE (`area:worker`→`area:backend` merged; `blocker`→`blocked` semantik-stop; 3 grup Faz-3 rapor) |
| HK-6D | `phase:*` / `mvp-*` historical cleanup | High | ✅ KARAR: **archive-keep** (dokunulmadı — silme tarihsel-filtre/değer-kaybı; bilinçli korundu) |

### HK-5 issue triage sonucu (2026-05-31)
12 milestone'suz açık issue triage edildi (güvenli, kanıt-temelli):
- **2 closed (kanıtlı):** **#1033** (11 pre-existing test regresyonu çözüldü — 11 test main'de 12 passed + CI artık koşuyor) · **#1109** (repo-sync before refactor; modular monolith phase'leri kapandı + prosedür CLAUDE.md §1.3 + worktree-discipline memory'de yerleşik).
- **2 keep-open (doğru konumda):** #1421 (P6.1 backlog, enhancement) · #1080 (T1 master-plan perpetual/tracking — `tracking` label HK-6'da eklenebilir).
- **8 keep-open-backlog (kapatma kanıtı yok, RAG/scraper):** #760 (Jina feature; #764 PR eval-negatif kapatıldı ama feature-talebi kullanıcı kararı) · #778 (RagFlow) · #735 (RAG test) · #612 (RSS bug) · #461 (admin-queue feature) · #328 (extractor bug) · #250 (scraper bug) · #255 (rag low). Milestone ataması → HK-6 sonrası / kullanıcı (milestone stratejisi). **Kör kapatma yapılmadı.**

### HK-6A label dry-run + HK-6B-Lite sonucu (2026-05-31)
**HK-6A bulgu (kullanım matrisi):** Proje **`type:*` custom sistemini kullanıyor**, GitHub-default'lar neredeyse boş (`type:bug`=127 vs `bug`=0; `type:feature`=194 vs `enhancement`=1) → "default'a merge" 250+ tarihsel relabel demek. **Karar: Yol B** (type:* korunur). `phase:*` (6 açık-issue) + `mvp-*` → **archive-keep** (silme bilgi-kaybı). Açık-PR label etkisi **sıfır** (#658/#641/#557 label'sız).

**HK-6B-Lite uygulandı (additive, destructive YOK):**
- **YENİ label:** `tracking` (D4C5F9, "Long-running tracker issue") + `security` (EE0701, "Security/vulnerability/disclosure").
- **#1080** += `tracking` (perpetual master-plan tracker görünür); mevcut label korundu.
- **#1421** += `type:feature` (default→custom taxonomy uyumu); `enhancement` korundu (bilgi kaybı yok).
- **9 açıklama standardize** (Türkçe-kısa → İngilizce profesyonel; sadece `--description`): `type:feature/bug/docs/legal/infra/research/refactor/test` + `backlog`. 8 zaten-İngilizce label (architecture/modular-monolith/god-file/runtime-sensitive/blocked/in-progress/ci/pivot) **dokunulmadı**.
- **Hiçbir label silinmedi/rename/merge edilmedi.** Label: 51 → 53 (+tracking +security).

### HK-6C duplicate merge sonucu (2026-05-31)
Faz 1 dry-run → güvenli olan tek grup uygulandı; semantik-çakışmalı/eksen-farklı gruplar raporlandı (uygulama yok).
- ✅ **`area:worker` → `area:backend` MERGED (uygulandı):** 0 açık-issue; 26 kapalı-issue + 1 kapalı-PR'a `area:backend` eklendi (hepsi doğrulandı → bilgi-kaybı yok) → `area:worker` **silindi**. worker⊂backend semantik-güvenli. Label 53→52.
- 🛑 **`blocker` → `blocked` UYGULANMADI (semantik-ters):** `blocked` açıklaması zaten "different semantic from blocker" diyor — `blocker`="durdurucu (başkalarını engelliyor)" ≠ `blocked`="bağımlılıkla engellenmiş". **#48 (açık, legal)** blocker → merge anlam-kaybı → **stop-condition**. `blocked-external` (0 açık, 3 kapalı) da external-semantik incelmesi → birlikte deferred.
- 📋 **Faz-3 (rapor-only, uygulama yok):**
  - **`area:devops`(0 açık/26 kapalı) → `type:infra`:** EKSEN FARKI (`area:`=kapsam ≠ `type:`=tür) → merge yanlış. Öneri: `area:devops` koru VEYA gelecekte `area:infra`'ya rename (devops bir alan). Karar kullanıcı.
  - **`type:docs`(2 açık #1022/#1003) ↔ `documentation`(3 açık #1080/#1022/#1003):** ikisi de aktif; #1022/#1003 İKİSİNDE de. Canonical öneri: `type:docs` (proje type:* sistemi) — ama #1080 yalnız `documentation`. Merge HK-6D/kullanıcı (açık-issue etkisi var).
  - **`enhancement`(#1421) ↔ `type:feature`:** #1421 HK-6B'de `type:feature` aldı (artık ikisinde). Canonical `type:feature`; `enhancement` community-default koru veya #1421'den çıkar. Karar kullanıcı.

### HK-6C.2 description canonicalization sonucu (2026-05-31)
Faz-3 raporlanan gruplar için **description-only** netleştirme (silme/merge/rename YOK; açık-issue label DEĞİŞMEDİ). 7 label açıklaması güncellendi:
- **`blocker`** → "Blocks other work; this issue is a blocker, not merely blocked by another dependency." (semantik netleşti; #48 açık korundu, merge YOK).
- **`blocked`** → "Blocked by an external or internal dependency; cannot proceed until resolved."
- **`blocked-external`** (0 açık, 3 kapalı — **archive-keep**) → "Blocked specifically by an external dependency or vendor/platform decision."
- **`area:devops`** (0 açık, 26 kapalı — **archive-keep**) → "DevOps, deployment, infrastructure operations, and environment management." (eksen farkı `area:`≠`type:` → merge YOK; korundu).
- **`documentation`** (default; 3 açık #1080/#1022/#1003) → "Documentation-related work. Prefer `type:docs` for new project-tracked issues." (silme YOK).
- **`type:docs`** → "Project documentation, wiki, README, or process documentation."
- **`enhancement`** (default; #1421) → "GitHub default feature label. Prefer `type:feature` for project-tracked feature work." (silme YOK).
- **`type:feature`** + **`type:infra`** → zaten iyi, **dokunulmadı**.

**Etki:** description-only; hiçbir label silinmedi/rename/merge; açık-issue/PR label değişmedi. Canonical-tercih ("Prefer type:docs/type:feature") açıklamalara gömülerek katkıcılara yön verildi (zorlamadan). Label sayısı sabit (52).

**HK-6D (`phase:*` 6 açık-issue + `mvp-*` historical) → ayrı karar turuna ertelendi.**

## 10b. Housekeeping Final State (2026-05-31)

HK-0..6 kontrollü housekeeping turu **TAMAMLANDI**. **Profesyonellik 5.5 → ~8.5/10.**

**Yapılan (kümülatif, hepsi doğrulandı):** HK-0 audit-wiki-kayıt · HK-1 description + 9 topic · HK-2 README refresh · HK-3 7-PR triage (4 closed #1009/#1008/#663/#764 + 3 keep-open) · HK-4 2 milestone closed (#1/#11) · HK-5 2 issue closed (#1033/#1109) + 10 keep-open · HK-6A dry-run (Yol B) · HK-6B-Lite (+`tracking`/`security`, #1080/#1421, 9 açıklama) · HK-6C `area:worker`→`area:backend` merge + `blocker` semantik-stop · HK-6C.2 7 description canonicalize · HK-6D **archive-keep**.

**Final state (read-only doğrulama 2026-05-31):**
- **Repo:** desc güncel + 9 topic; #18/19/20 + #1/#11 closed; açık milestone #5/#6/#16/#17/#3 (gerçek backlog/aktif).
- **Issue:** açık **33** / kapalı **410** / milestone'suz-açık **10**; #1080 +`tracking`, #1421 +`type:feature` (enhancement korundu).
- **PR:** **3 açık** (#658/#641/#557 = keep-open-needs-review; HK-3'te 4 kanıtlı kapatıldı).
- **Label:** **52** (`tracking`/`security` eklendi, `area:worker` silindi; `phase:`7/`mvp:`3/`type:`8 korundu; blocker/blocked/blocked-external ayrı; canonical-tercih açıklamalara gömülü).
- **README:** stale-temiz (MVP-1.4/repo-private kaldırıldı), architecture/wiki link, lisans nötr.

**Disiplin:** sıfır kod değişikliği · sıfır destructive label-op (1 güvenli merge hariç) · sıfır açık-issue bilgi-kaybı · tüm wiki/repo-meta → deploy SKIP · sahte-kapanış yok. **Feature development'a engel kalmadı.**

## 11. High-caution decision list (UYGULANMAZ — kullanıcı kararı)

| Konu | Neden high-caution | Seçenekler |
|---|---|---|
| **LICENSE** | IP/legal; public→all-rights-reserved | açık-kaynak (MIT/Apache/AGPL) / proprietary (source-available) / yok |
| **Visibility (public/private)** | Konumlandırma + IP-moat | public-showcase / private |
| **README lisans-konumlandırma** | Open-source vs proprietary iddia | nötr ("not yet specified, all rights reserved by default") → karar sonrası netleşir |
| **Branch protection (main)** | CI-zorunlu-check + review | etkin (önerilen) / mevcut (yok) |
| **SECURITY policy** | Güvenlik açığı raporlama | ekle / yok |
| **CODE_OF_CONDUCT** | Community health | ekle / yok |
| **Releases/tags** | Sürümleme (v1.0 = milestone kapanışları) | başlat / yok |

## İlişkiler
- [[architecture-final-state-2026-05]] — repo mimari final state (housekeeping bu yapının üstüne dış-yüz katmanı).
- [[modular-monolith-transition-master-plan]] — #18/#19/#20 kapanışı (housekeeping'in tetikleyicisi).

## Kaynaklar
- GitHub repo: https://github.com/selmanays/nodrat
- Read-only audit (2026-05-31): issue/milestone/PR/label/repo-meta/README/CI kanıtları.
