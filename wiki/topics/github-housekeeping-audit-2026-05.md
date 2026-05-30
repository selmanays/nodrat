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

## 10. Housekeeping roadmap (HK-0..6)

| Sıra | İş | Risk |
|---|---|---|
| HK-0 | Bu audit'i wiki'ye kaydet (bu sayfa) | Safe |
| HK-1 | repo description + topics güncelle | Safe→Moderate |
| HK-2 | README stale fix + wiki/modular-monolith link (lisans NÖTR) | Moderate |
| HK-3 | 7 stale PR triage (kanıtlı close / keep-open) | Moderate |
| HK-4 | Milestone #1 + #11 close | Moderate |
| HK-5 | 12 milestone'suz issue triage (güvenli sınıflandırma) | Moderate |
| HK-6 | Label taxonomy **dry-run** (uygulama YOK) | Safe (rapor) |

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
