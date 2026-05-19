---
type: decision
title: "Cited-only HARD invariant — 0 gerçek kaynak + substantive cevap servis edilmez"
slug: "research-cited-only-hard-invariant"
status: "locked"
decided_on: "2026-05-19"
decided_by: "tech"
created: "2026-05-19"
updated: "2026-05-19"
sources:
  - "PR #1058 (cited-only hard guard + force-retrieval + condense leak)"
  - "apps/api/app/api/app_research_stream.py (_is_substantive, C1 backstop, hard-refuse, Fix B′)"
  - "apps/api/app/core/conversation_context.py (format_context_block include_sources)"
  - "Prod-audit conv 865e36e3 (uydurma '[Forbes Türkiye]')"
tags: ["locked-decision", "pivot", "answer-integrity", "hallucination", "C1", "architecture"]
aliases: ["cited-only-hard", "forbes-turkiye-bug", "fix-b-prime", "0-kaynak-red"]
---

# Cited-only HARD invariant — 0 gerçek kaynak + substantive cevap servis edilmez

> **Karar:** Substantive (olgusal, ≥120 char) bir cevap **0 GERÇEK retrieved kaynak** ile üretildiyse ASLA servis edilmez → dürüst reddedilir. Sayısal-olmayan uydurma atıf (`[Forbes Türkiye]`) da C1 düzeltici turu tetikler. Condense ile bağlamlı takip → ilk tur GERÇEK retrieval'a zorlanır (`tool_choice="required"`). Önceki cevabın kaynak ADLARI condense bağlamına SIZMAZ. Hepsi flag-gated, default-AÇIK, gözlem-only şeffaflık [[research-retrieval-transparency]] ile görünür.
> **Durum:** locked
> **Tarih:** 2026-05-19

## Bağlam (prod-audit incident, conv 865e36e3)

Pivot sonrası bağlamlı takip ("nerede yaptı bu açıklamayı") prod'da **halüsinasyon** üretti: "Tamamlandı (2 adım, **0 kaynak**)" + elle yazılmış **`[Forbes Türkiye]`** (sayısal-olmayan sahte atıf) + devrik ilk cümle + "bu bilgi kaynakta yok" (oysa Forbes haberinde vardı). Üç bağımsız kök:

1. **C1 deliği:** [[agentic-generate-orchestration]] #851 C1 backstop'u `_CITE_TOKEN_RE = [W?\d{1,3}]` (yalnız sayısal) ile arıyordu → `[Forbes Türkiye]` sayısal değil → backstop atlandı → 0-kaynak halüsinasyon serbestçe servis edildi.
2. **Bellekten cevap:** LLM, condense ile bağlamlandırılmış takibi hiç tool çağırmadan kendi belleğinden cevapladı (0 retrieval).
3. **Condense kaynak-adı sızıntısı:** `format_context_block` önceki cevabın kaynak ADLARINI ("Forbes Türkiye") condense bağlamına koyuyordu → uydurma atıfın tohumu ([[l1-recency-anchored-context]] L1 condense besleyici).

## Alternatifler ve neden reddedildi

| Alternatif | Neden reddedildi |
|---|---|
| Yalnız `_CITE_TOKEN_RE`'yi genişlet (regex'e metin-atıf ekle) | Serbest-metin ifade eşleştirme = #819 anti-pattern; uydurma atıf biçimi sonsuz |
| Derin chunk-scoped cascade (ilk chunk→devamı→yeni search) | Retrieval kalite makinesine dokunur; eval-gate'li AYRI iş — ertelendi ([[research-retrieval-transparency]] kapsam notu) |
| 0-kaynak cevabı düşük güvenle yine de servis et | Kaynaksız "haber" = marka hasarı; editöryal motor dürüstlük çekirdeği (S6/C1) |
| Prompt'u sıkılaştır (yalnız) | Prompt-bağımlı; yapısal invariant gerek (deterministik, test-edilebilir) |

## Sonuç (3 düzeltme — locked)

- **Fix A — cited-only HARD guard (`_is_substantive`):** saf eşik (`len(strip()) ≥ 120`; selamlama/kimlik/meta kısa → dışlanır). (a) C1 backstop genişletildi: 0 kaynak + substantive → sayısal `[n]` OLMASA da düzeltici tur (`tool_choice="required"`, 1 kez). (b) Servis öncesi sert invariant: `_cited_only_strict and not all_sources and _is_substantive(final_text)` → cevap dürüst redle değiştirilir ("doğrulanabilir kaynak bulunamadı … kaynaksız cevap vermiyorum"). Kısa selamlama/kimlik etkilenmez.
- **Fix B′ — contextualized-takip force-retrieval:** condense `effective_query`'yi bağlamlı yeniden yazdıysa (`_contextualized`) ilk tur `tool_choice="required"` → bellekten cevap yapısal imkânsız; kanıtlı retrieval entity-zengin sorguyla doğru makaleyi getirir. Kullanıcının "önceki kaynakları önceliklendir/cache" önerisinin **risk-sınırlı** hali (derin chunk-cascade DEĞİL — o eval-gate'li ertelendi).
- **Fix C — condense kaynak-adı sızıntısı kapatıldı:** `format_context_block(..., include_sources: bool = False)`; varsayılan kaynak-adı satırını ÜRETMEZ (condense yalnız önceki Q&A KONUSUNA muhtaç, kaynak adına değil). Legacy birebir format yalnız opt-in `include_sources=True` (mevcut çağrı yok). [[l1-recency-anchored-context]] condense sözleşmesi korunur.
- 2 flag (`research.cited_only_strict`, `research.followup_force_retrieval`) admin SETTING_REGISTRY "research" grubu, default **True**, escape-hatch.
- **Prod-kanıt (Playwright, deploy sonrası):** aynı takip → "Tamamlandı (3 adım, **1 kaynak** + 7 taranan)", gerçek sayısal `⁸` + gerçek Anadolu Ajansı Kaynaklar linki; uydurma `[Forbes Türkiye]` YOK, devrik cümle YOK, yeni ayrı conversation (no-thread korunur).

## İlişkiler

- [[agentic-generate-orchestration]] — #851 C1 backstop'u bu karar genişletti (sayısal → substantive); aynı agentic loop
- [[l1-recency-anchored-context]] — Fix C condense besleyici sözleşmesi; kaynak-adı sızıntısı L1 condense tohumuydu
- [[research-single-turn-invariant]] — Fix B′ bağlamlı takip = yeni conversation; oturumlar-arası bağlam yalnız L1 condense
- [[pivot-editorial-research-engine]] — cevap-bütünlüğü pivotun dürüstlük çekirdeği (S6/C1 invariant)
- [[research-retrieval-transparency]] — bu invariantların kullanıcıya görünür kılınması (gözlem-only)
- [[self-identity-canonical-prompt]] — kardeş anti-halü backstop (kimlik/meta path)
- [[global-research-cluster-model]] — C ops-doğrulamada: kümeleme/L2/hiyerarşi flag'leri açıkken bu invariantlar (kaynaklı cevap) bozulmadan tuttu (kanıt)

## Geri alma maliyeti

> `research.cited_only_strict=false` → eski davranış (0-kaynak substantive servis edilebilir — halüsinasyon riski geri gelir). `research.followup_force_retrieval=false` → LLM bağlamlı takipte tool çağırmayabilir. Fix C geri-uyumlu (opt-in param; çağıran yok). Additive; cevap-üretim şeması/citation namespace değişmedi. Düşük maliyet ama dürüstlük çekirdeği — geri-alma önerilmez.

## Kaynaklar

- [app_research_stream.py](apps/api/app/api/app_research_stream.py) — `_is_substantive`, C1 backstop (genişletilmiş), hard-refuse, Fix B′ `next_tool_choice`
- [conversation_context.py](apps/api/app/core/conversation_context.py) — `format_context_block(include_sources=False)`
- [admin_settings.py](apps/api/app/api/admin_settings.py) — `research.cited_only_strict` / `research.followup_force_retrieval`
- PR #1058 · prod-audit conv 865e36e3
