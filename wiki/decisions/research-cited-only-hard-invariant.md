---
type: decision
title: "Cited-only/grounding HARD invariant — kaynaksız VEYA dolaylı-kaynak çıkarsama servis edilmez"
slug: "research-cited-only-hard-invariant"
status: "locked"
decided_on: "2026-05-19"
decided_by: "tech"
created: "2026-05-19"
updated: "2026-05-19"
sources:
  - "PR #1058 (cited-only hard guard + force-retrieval + condense leak)"
  - "PR #1068 (#1067 RC3 — dolaylı/tepki-kaynağı rekonstrüksiyon backstop)"
  - "apps/api/app/api/app_research_stream.py (_is_substantive, C1 backstop, hard-refuse, Fix B′, _verify_primary_grounding, _parse_faithfulness_verdict)"
  - "apps/api/app/prompts/research_answer.py (SYSTEM_PROMPT_NODRAT_AGENT — RC3-A anma≠tanım genişleme)"
  - "apps/api/app/core/conversation_context.py (format_context_block include_sources)"
  - "Prod-audit conv 865e36e3 (uydurma '[Forbes Türkiye]') + quirky-gates Q4 (Özel/Çelik dolaylı-kaynak)"
tags: ["locked-decision", "pivot", "answer-integrity", "hallucination", "C1", "architecture"]
aliases: ["cited-only-hard", "forbes-turkiye-bug", "fix-b-prime", "0-kaynak-red", "faithfulness-guard", "indirect-source-reconstruction", "rc3"]
---

# Cited-only/grounding HARD invariant — kaynaksız VEYA dolaylı-kaynak çıkarsama servis edilmez

> **Karar:** Substantive (olgusal, ≥120 char) bir cevap **(a) 0 GERÇEK retrieved kaynak** ile (#1058) **VEYA (b) kaynak VAR ama ana iddia kaynak metinde DOĞRUDAN desteklenmiyor** (dolaylı/tepki-kaynağından geriye-çıkarsama, #1067 RC3) ile üretildiyse ASLA servis edilmez → dürüst kapsam-sınırı/red. Sayısal-olmayan uydurma atıf (`[Forbes Türkiye]`) da C1 düzeltici turu tetikler. Condense bağlamlı takip → ilk tur GERÇEK retrieval (`tool_choice="required"`). Önceki cevabın kaynak ADLARI condense'e SIZMAZ. Hepsi flag-gated, default-AÇIK, gözlem-only şeffaflık [[research-retrieval-transparency]] ile görünür (`faithfulness_reframed`/`cited_only_refused` step).
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

## RC3 genelleme (#1067) — dolaylı/tepki-kaynağı rekonstrüksiyonu (locked)

Bu invariant **0-kaynak**ı kapsıyordu (#1058). Prod-teşhis (conv quirky-gates Q4): **KAYNAK VAR ama cevabın ana iddiası kaynak metinde DOĞRUDAN yok** — soru "Özel'in Kocaeli iddiası neydi", korpusta yalnız Ömer Çelik'in **reddiyesi** var (Özel'in asıl iddiası YOK); model "tepkisinden **anlaşıldığı kadarıyla** Özel … iddiada bulunmuş" diye **geriye-çıkarsama rekonstrüksiyon** yaptı. #1058 yakalamaz (1 kaynak, 0 değil); cosine-validator yakalamaz (**anma ≠ tanım**: Özel/Kocaeli/AKP topical-benzerlik yüksek); `citation.py` dead-code (#845 sonrası).

**Hibrit C (kullanıcı-onaylı, "gerçek+kalıcı"):**
- **RC3-A (prompt):** `SYSTEM_PROMPT_NODRAT_AGENT` §Halüsinasyon "Anma ≠ tanım" genişletildi → *X'in iddiası/sözü, Y'nin tepkisinden ÇIKARSANMAZ*; "anlaşıldığı kadarıyla / tepkisinden anlaşıl…" KALIPLARI YASAK + dürüst kapsam-beyanı. §Yorum/çıkarım: iç-süreç sızıntısı yasağı ("arama sonuçlarında…", Q3 semptomu).
- **RC3-B (yapısal backstop):** `_verify_primary_grounding` — ayrı hafif async dayanak-denetçisi (`_generate_followups` deseni; cheap tier; saf `_parse_faithfulness_verdict` DIRECT/INDIRECT/UNSUPPORTED, en-katı kazanır, tanınmaz→DIRECT). #1058 noktasında, KAYNAK VAR + substantive + cite → kanıt = **tool-result metni** (kaynak kartında metin TUTULMAZ, #845). INDIRECT/UNSUPPORTED → #1058'i genelleştir: dürüst kapsam-sınırı (rekonstrüksiyon engellenir) + `faithfulness_reframed` step ([[research-retrieval-transparency]]; RC2 telemetri kancası). `asyncio.wait_for`+except → DIRECT (degrade-safe, ASLA daha kötü). #1058 ile **karşılıklı dışlayan** (`not all_sources` vs `all_sources`).
- Flag `research.faithfulness_guard_enabled` default **True** (escape-hatch, #1058/#854 deseni); flag-off byte-eş; cevap-çekirdeği DOKUNULMADI; verifier ham çıktı ana cevaba giremez (ayrı call, #819/#840).
- **Prod-kanıt (Playwright):** Q4 "Özgür özel Kocaeli iddiası nedir" → `faithfulness_reframed` step + "Bu soruya **doğrudan** dayanak … bulunamadı … çıkarımsal/dayanaksız cevap vermiyorum" (rekonstrüksiyon YOK, "anlaşıldığı kadarıyla" YOK). Grounded kontrol (Trump) → DIRECT, reframe YOK, **regresyon YOK**; API eval golden-set PR+main yeşil.

> **RC2 (korpus kapsama boşluğu) — TESLİM (#1071 + hotfix #1073):** Özel'in orijinal iddiasının korpusta olmayışı **kod fix değil** (korpus tamamlanamaz) — RC3 davranış-düzeltmesi gerçek çözüm; **ölçülür**: `_log_coverage_gap` RC3-B (`indirect:VERDICT`) ve #1058 (`zero_source`) tespit noktalarında greppable `coverage_gap reason=… q=…` log (observability-only; cevap/şema/akış DOKUNULMAZ; `contextlib.suppress` → telemetri akışı bozmaz; q 160-char trunc). **#1073 hotfix:** `logger.info` prod effective-level WARNING'de sızıyordu (telemetri görünmez no-op) → `logger.warning` (aksiyon-alınabilir ops sinyali; canlı-doğrulama ile yakalandı). **Prod-kanıt:** `nodrat-api | coverage_gap reason=indirect:INDIRECT q='Özgür Özel Kocaeli iddiası…'` log'da göründü + aynı conv `faithfulness_reframed` + dürüst kapsam-sınırı cevabı.

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
- [admin_settings.py](apps/api/app/api/admin_settings.py) — `research.cited_only_strict` / `research.followup_force_retrieval` / `research.faithfulness_guard_enabled` (#1067)
- [research_answer.py](apps/api/app/prompts/research_answer.py) — RC3-A: SYSTEM_PROMPT_NODRAT_AGENT "anma≠tanım" genişleme + iç-süreç sızıntısı yasağı
- [app_research_stream.py](apps/api/app/api/app_research_stream.py) — RC2: `_log_coverage_gap` (greppable `coverage_gap`, observability-only, logger.warning #1073)
- PR #1058 · #1068 (#1067 RC3) · #1071+#1073 (RC2 telemetri + log-level hotfix) · prod-audit conv 865e36e3 + quirky-gates Q4 (Özel/Çelik)
