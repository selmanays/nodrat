---
type: topic
title: "Refactor Anti-Patterns — Do Not Do List"
slug: "refactor-anti-patterns-do-not-do"
category: playbook
status: live
created: 2026-05-20
updated: 2026-05-20
sources:
  - "wiki/plans/modular-monolith-transition-master-plan.md§11"
  - "wiki/topics/ci-blind-8-months-incident.md"
  - "/Users/selmanay/.claude/projects/-Users-selmanay-Desktop-nodrat/memory/MEMORY.md"
tags: ["refactor", "anti-pattern", "modular-monolith", "playbook"]
aliases: ["do-not-do", "refactor-traps"]
---

# Refactor Anti-Patterns — Do Not Do List

> **TL;DR:** Modüler monolit dönüşümünde **kesinlikle kaçınılacak 20 anti-pattern**. Her birinin tarihsel kanıtı + neden yasak olduğu + uygulama hatırlatması. Her refactor PR review'ında kontrol edilir.

## Bağlam

Bu liste **gerçek tarihsel olaylardan** doğdu (RC3-B v1 prod yanlış-pozitif, CI 8 ay kör, Türkçe collation 6 ay kör, embedding migration "pending" yanılgısı, vb.). "Bilinmesi gereken refactor tuzakları" değil — **bu repoda yapılmış veya yapılmaması için işaret edilmiş** spesifik hatalar.

## Tablo

| # | Anti-pattern | Tarihsel kanıt | Neden yasak | Uygulama hatırlatması |
|---|---|---|---|---|
| 1 | **Big-bang refactor** (5+ modülü tek PR'da) | (proaktif önlem) | Geri alınamaz; blame imkansız; CI körlüğü (L1) tipi sessiz regresyona açık | Tek PR ≤ 1 modül; tek faz ≤ 5 gün |
| 2 | **Model taşıma Faz N+1 ön-şartları sağlanmadan** | %93 class-ref relationship — agent raporu | Circular import garantili; alembic autogenerate kırılır; production schema sessizce kayar | [[models-flat-until-conditions]] 5 ön-şart sağlandığında |
| 3 | **God-file facade öncesi parçalama** | RC3-B v1 prod 4/8 yanlış-pozitif (log #1076) | Sessiz davranış kayması eval'de görünmez; recall@5 0.005 puan kayması production'da fark edilmez | [[god-file-facade-first]] disiplini |
| 4 | **Characterization test olmadan retrieval/SSE değişikliği** | Türkçe collation #939 6 ay kör; RC3-B v1 | "Test ettim" ≠ "doğru test ettim"; davranış izi snapshot olmadan kayar | Golden snapshot + eval baseline diff < 0.5% |
| 5 | **Merkezi `admin/` god-modülü** (tüm admin_* tek paket) | (proaktif önlem) | Domain boundary çöker; admin tek PR'da büyür; RAG dashboard değişikliği billing'i etkiler | [[admin-route-domain-ownership]] — domain admin kendi modülünde |
| 6 | **`core/` içine yeni domain logic ekleme** | Mevcut 47 dosya legacy çöplük | `core/` zaten 47 dosya; yeni dosya buraya konursa Faz 8 hiçbir zaman tamamlanmaz | Yeni dosya → ilgili `modules/<mod>/` |
| 7 | **Import boundary ihlali** (yasaklı ok) | §3.2 forbidden tablosu | RAG'in crawler'ı import etmesi mimari intihar; ops'a yukarı bağlantı boundary'yi öldürür | import-linter CI gate |
| 8 | **Docs/wiki güncellemesi atlama** | memory `feedback_wiki_sync_completeness` (2026-05-12) | Karar dağılır; paralel worktree agent'ları yeni state'i görmez | PR template "Docs/wiki updates" checklist'i zorunlu |
| 9 | **Internal alias-debt biriktirme** (eski path "backward-compat") | memory `feedback_backward_compat_argument` (2026-05-12) | İki doğru-yol gerçeği; agent'lar yanlış path import eder; refactor yarı kalır | [[no-internal-backcompat-aliases]] — aynı PR'da temizle |
| 10 | **Cross-encoder rerank açma** | `cross-encoder-rerank-disabled` locked-permanent (#750) | Eval gate negatif kanıtlı; recall NDCG regresyon (0.627→0.509) | Refactor fırsatı bunu açma değildir; pluggable interface kapalı kalır |
| 11 | **Confidence-based routing geri getirme** | `confidence-based-routing` superseded (#823→#828) | "Konu geçiyor?" ≠ "cevap var mı?"; production kırdı defalarca | Agentic RAG-as-tool ile değişti; eski yola dönme |
| 12 | **Sub-chunking / micro-chunking** | failed-experiments #769 | Semantic dilution çözmez; +29K satır schema-clutter; recall delta 0 | Chunking strategy locked |
| 13 | **Rerank-only niş entity çözümü** | failed-experiments #758/783/791 | Top-K dışındaki target'ı içeri sokmaz; recall'a çare değil | MUST_MATCH + K=12 rescue zaten doğru çözüm |
| 14 | **LLM-judgment faithfulness verifier geri getirme** | RC3-B v1 prod 4/8 yanlış-pozitif (log #1076) | Calibration-fragile; NLP literatürü "hard problem"; Goodhart-law prompt-twist spiral | Yapısal regex marker-detect zaten doğru araç |
| 15 | **DeepSeek tool_choice cache-breaking değişiklik** | memory `feedback_deepseek_toolchoice_cache` (2026-05-18) | Cache prefix kırılır → cache hit %25→%0; LLM cost ×4 | tool_loop'ta hep "auto"; kök sebepleri izole-değişken deneyle doğrula |
| 16 | **Spike deploy'u clean-main restore etmeden bırakma** | memory `feedback_spike_deploy_restore_clean_main` (2026-05-18) | Production merge edilmemiş kodda kalır = incident-sınıf | Restore SON benchmark sonrası HEMEN; analiz/PR/docs öncesi |
| 17 | **Queue/task name değişikliği** | (proaktif önlem) | Beat schedule + apply_async() string-bound; isim değişirse silent fail; production worker'lar yanlış task çağırır | Refactor sırasında task name **değişmez**; sadece fiziksel konum |
| 18 | **Paralel SSH ile deploy** | memory `feedback_deploy_lessons` (2026-05-10) | Lock conflict; partial build → orphan container; killed/network-kesildi build → `--no-cache` gerek | Sıralı SSH; düzenli `docker builder prune -af`; orphan container `docker rm -f` |
| 19 | **Eski path re-export köprü** (legacy alias) | (mimari prensip) | Alias-debt birikir; "Hangisi gerçek?" karmaşası; refactor yarı kalır | [[no-internal-backcompat-aliases]] — aynı PR'da eski silinir |
| 20 | **Refactor PR'ında davranış değişikliği** (feature + fix karıştırma) | (mimari prensip) | Behavior-preserving disiplin ihlali; karışık PR review imkansız; rollback selektif olamaz | Davranış değişikliği gerekiyorsa ayrı issue + ayrı PR |

## Çıkarımlar

1. **Sessiz regresyon en büyük tehdit.** Anti-pattern'lerin %60'ı (özellikle #3, #4, #14, #15, #17) sessiz davranış kaymasını besler. Bu yüzden characterization test + import-linter + behavior-preserving disiplini hayati.
2. **Anti-pattern'ler "yapma" değil "yapılma sebepleri" listesi.** Her birinin tarihsel kanıtı var — bu gelecek refactor'da "olabilir" değil "geçmişte oldu, tekrar olmasın" demek.
3. **Tek geliştirici + LLM workflow** alias-debt için en savunmasız ortam (#9, #19). Backward-compat argümanı sadece external sözleşme için geçerli.
4. **God-file disiplini ayrı bir mesele** (#3, #4) — facade + characterization olmadan dokunma kuralı locked.

## İlişkiler

- **Beslediği kararlar:** [[modular-monolith-boundary]], [[god-file-facade-first]], [[no-internal-backcompat-aliases]], [[models-flat-until-conditions]]
- **İlgili playbook:** [[refactor-pr-checklist]], [[new-feature-module-checklist]], [[agent-worktree-playbook]]
- **Tarihsel topic:** [[ci-blind-8-months-incident]]

## Açık sorular / TODO

- Anti-pattern listesi yaşayan dokümandır; her phase retrospective'de yeni öğrenmeler buraya eklenir. Her ekleme: tarihsel kanıt + neden yasak + uygulama hatırlatması.

## Kaynaklar

- [wiki/plans/modular-monolith-transition-master-plan.md §11](../plans/modular-monolith-transition-master-plan.md)
- memory MEMORY.md (feedback_* girdileri)
- log #1030, #1076, #939 vb.
