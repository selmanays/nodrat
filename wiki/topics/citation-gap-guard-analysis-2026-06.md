---
type: topic
title: "Citation-Gap Guard — simetrik citation-enforcement reality-analysis (2026-06)"
slug: citation-gap-guard-analysis-2026-06
status: live
created: 2026-06-12
updated: 2026-06-12
sources:
  - apps/api/app/api/app_research_stream.py§838-1137
  - apps/api/app/modules/generations/citation.py§48-131
  - apps/api/app/prompts/research_answer.py§40-336
  - apps/api/app/modules/settings_admin/routes.py§1099-1142
  - wiki/topics/query-failure-analysis-2026-06.md§8
tags:
  - analysis
  - rag
  - citation
  - guard
  - reality-analysis
  - read-only
aliases:
  - "citation gap guard"
  - "simetrik citation guard analizi"
---

# Citation-Gap Guard — simetrik citation-enforcement reality-analysis (2026-06)

## TL;DR / Executive summary

[[query-failure-analysis-2026-06]] §8'in işaret ettiği **citation enforcement asimetrisi** için read-only tasarım analizi (2026-06-12). Sonuç: **guard yapılmalı — ama kör "cite et" retry'ı olarak DEĞİL, iki-çıkışlı dürüst-netleştirme retry'ı olarak**: *kaynaklar cevabı destekliyorsa her olguya [n] ekle; desteklemiyorsa cevabın başında bunu açıkça söyle ve kaynaksız iddiaları çıkar*. Feature flag (`research.citation_gap_guard_enabled`) **default OFF**; tek bounded corrective turn (`tool_choice="auto"`, sarkaç yok); hard-refuse YOK. Sıra: **önce S-1 search-arg observability, sonra S-2 guard** — iki ayrı issue. Implementation ayrı açık onay gerektirir.

> ✅ **DURUM (2026-06-12): Implemented — [#1489](https://github.com/selmanays/nodrat/pull/1489) merged + FULL deploy success.** Flag `research.citation_gap_guard_enabled` **default OFF / unset** → prod davranış **no-op / byte-identical**. Implementation = bu sayfadaki Opt-B tasarımının birebiri: saf 5-AND gate + iki-çıkışlı sabit nudge; **hard-refuse YOK**; **one-shot retry invariant test-kilitli** (`citation_gap_forced_once`, gate `forced_once=True → False`); `tool_choice="auto"`; post-retry hâlâ atıfsız → `coverage_gap("citation_gap")`. Schema/migration YOK. **C1/cited-only/faithfulness regresyonları korundu** (targeted 80 + full 1358 passed; lint-imports 16/16). Bağımlılık: **S-1 (#1483) implemented + canary-validated ama flag OFF.** **S-2 canary YAPILMADI** — activation/canary ayrı prod-config onayı gerektirir (S-1 telemetri flag'iyle birlikte kısa süreli ON = teşhis için ideal kombinasyon, o da ayrı karar).

> 🟢 **S-2 MICRO-CANARY SONUCU (2026-06-12): güvenlik temiz, etkinlik kanıtı yok, rollback tamam.** İki flag (`citation_gap_guard_enabled` + `search_arg_telemetry_enabled`) kullanıcı onayıyla kısa süreli ON; **7 mesaj / planlanan 6 konuşma** test edildi (gerçekte 8 ayrı conversation oluştu — aşağıda Q7 düzeltmesi); rollback `settings_store.reset ×2 + commit` → **final prod state: iki flag unset/OFF baseline**. **Güvenlik:** yanlış-pozitif **0** · zarar **0** · error/exception/traceback **0** · C1/cited-only/faithfulness çakışması yok · normal sorgularda davranış değişimi yok. **`citation_gap_retry` 0/7 tetiklendi** — 6/7 cevap citation'lıydı, gate doğru sustu. **Etkinlik kanıtı yok → kalıcı ON önerilmiyor.**
>
> ⚠️ **Q5 DÜZELTMESİ (root-cause verification sonrası geri çekilen yorum):** Q5 ("borsa ne olur", 23 considered / 0 used / citation'sız substantive cevap, forced-final yolu) önce "forced-final guard faz-2 kanıtı" gibi göründü — **bu yorum GERİ ÇEKİLDİ**. Read-only doğrulama: `research.l1_windowed_context_enabled` prod'da **2026-05-18'den beri ON**; L1 **user-scope cross-conversation** condense zenginleştirmesi Q5'in effective_query'sine **bir önceki konuşmanın "uzay madenciliği yasası" konusunu sızdırdı** ("Türkiye 2026 uzay madenciliği yasası borsa etkisi") → yanlış `retrieval_forced`/contextualized yolu → 3 tur alakasız arama → forced-final → sources_used=0. **Q5 bir citation-gap-guard kapsam bulgusu değil, context-isolation / retrieval_forced sınıflandırması bulgusudur.** Forced-final kapsam boşluğu yapısal olarak doğru kalır ama Q5 onun kanıtı değildir.
>
> ⚠️ **Q7 DÜZELTMESİ:** Q6→Q7 gerçek same-conversation follow-up olarak **test edilemedi** — Q7 backend'de **ayrı conversation'a** düşmüş görünüyor (client yeni-sorgu state'i); retrieval_forced etkisi büyük olasılıkla L1 cross-conv üzerindendi.
>
> **Sonuç:** S-2 guard güvenli görünüyor ama canlı etkinlik kanıtı yok; **kalıcı activation YOK**; **forced-final faz-2 implementation'a GEÇİLMEMELİ**; sıradaki doğru iş **"new-search context isolation / L1 retrieval_forced classification" reality-analysis** (ayrı onay). **→ Analiz tamamlandı: [[l1-new-search-context-isolation-analysis-2026-06]]** (Q5 kök-neden zinciri + Gate-4 drift fix önerisi; "Q5 forced-final faz-2 kanıtı değildir" hükmü korunur).

## 1. Bağlam + metod

Citation-loss follow-up'ın ([[query-failure-analysis-2026-06]] §8) düzeltilmiş bulgusu: aktif organik silent-uncited ≈%6.3 (4/63); aktif iki problem = retrieval gündem-dump + citation enforcement asimetrisi. Bu analiz "kaynak var ama cevapta citation yok" durumu için simetrik guard tasarlanmalı mı, tasarlanacaksa nasıl sorusunu yanıtlar. Metod: read-only kod/prompt/settings/test/issue keşfi (5 paralel okuyucu) + 4 organik vakanın davranış eşlemesi. Kod/PR/issue/prod-config/mutation yok.

## 2. Current pipeline map (citation enforcement, satır-doğrulanmış)

```
Prompt katmanı (app/prompts/research_answer.py):
  L40,52-55        her cümlede [n] zorunlu
  L306-310,386-387 kaynak içermiyorsa citation YAZMA (sahte kaynak = marka zararı)
  L104-106,138-143 alakasız kaynaktan sentez YAPMA; entity-eşleşme karar kuralı
  L332-336         bulamadıysan scope-aware "kaynaklarda bulamadım" + sourced kısım

Yapısal guard'lar (app/api/app_research_stream.py):
  L838        retrieval_forced — contextualized follow-up → ilk tur tool_choice=required
              (flag research.followup_force_retrieval, default ON)
  L886-913    C1 grounding_retry — `not all_sources` + (cite-token VEYA substantive)
              → 1× düzeltici tur (c1_forced_once; tool_choice=required)
  L1069-1081  cited-only refuse — `not all_sources` + substantive → canned refuse
              + coverage_gap(zero_source)  (flag research.cited_only_strict, default ON)
  L1098-1107  faithfulness reframe — `all_sources` + substantive + reconstruction-marker
              → canned reframe + coverage_gap(reconstruction_marker)
              (flag research.faithfulness_guard_enabled, default ON)
  L1125-1137  citation_filter — yalnız DISPLAY (sources_used türetimi); enforcement DEĞİL
```

## 3. Gap / asymmetry

| | cevapta cite-token VAR | cevapta cite-token YOK |
|---|---|---|
| **all_sources = 0** | C1 retry → olmadıysa refuse | C1 retry (substantive ise) → refuse |
| **all_sources > 0** | normal yol (filter sayar) | **🕳️ BOŞLUK** — yalnız reconstruction-marker varsa reframe; aksi halde substantive cevap **sessizce kaynaksız servis** |

`sources_considered>0 ∧ sources_used=0` (organik ≈%6.3) tam bu boşlukta oluşuyor. Kanıt vakası: retrieval_forced çalıştı, 4 kaynak geldi, substantive cevap refuse-wording'i bile olmadan citation'sız gitti. #1058/#1076 arkının tekrarlanan dersi geçerli: kritik answer-integrity kuralı prompt-only olamaz, yapısal backstop ister (RC3-A prompt'a rağmen marker sızmıştı).

## 4. Design options

| Opt | Tasarım | Karar |
|---|---|---|
| 0 | No-op (prompt'a güven) | ❌ ~%6.3 sessiz bütünlük açığı; dayanaksız-substantive-cevap riski |
| A | Kör "cite et" retry'ı | ❌ Organik vakaların yarısında kaynaklar alakasızdı → modeli tam #1058'in savaştığı sahte/gevşek atfa iter |
| **B ★** | **İki-çıkışlı dürüst-netleştirme retry'ı** — tek bounded corrective turn; nudge: "destekliyorsa her olguya [n]; desteklemiyorsa açıkça belirt + kaynaksız iddiaları çıkar"; `tool_choice="auto"` | ✅ **Önerilen** |
| C | Canned reframe (faithfulness deseni) | ❌ Meşru dürüst "bulamadım" cevaplarını siler; v1-reframe UX dersi (kullanıcı aynı soruyu 4× yeniden sordu) |
| D | LLM-judge relevance kontrolü | ❌ #1076 dersi: LLM-judgment calibration-fragile (v1 prod 4/8 yanlış-pozitif) + ekstra çağrı |

## 5. Risk analysis (Opt-B)

| Risk | Önlem |
|---|---|
| Alakasız kaynağı cite etmeye zorlama | Nudge'ın 2. kolu + prompt L306-310 kuralı hatırlatılır; sıfır değil → **canary spot-check zorunlu** |
| Sahte/gevşek citation'a itme | `tool_choice` **required yapılmaz** (C1'den fark: kaynak zaten var, zorlama yok); tek retry |
| Doğru "bulamadım" cevabını bozma | Nudge koruyucu dil içerir; canary'de bu sınıf özellikle izlenir |
| Kısa konuşmasal/meta yanlış tetikleme | `_is_substantive` (≥120 char) eşiği aynen kullanılır |
| Latency / maliyet | +1 chat çağrısı, yalnız tetiklenen ~%6 dilimde; `tool_round_timeout` bounded; cache-prefix korunur (aynı tools + `auto`, append-only — #983/#1006 dersi: `none` KULLANMA) |
| Faithfulness etkileşimi | Retry tool-loop içinde, reframe post-loop'ta → retry çıktısında marker varsa reframe yine çalışır (doğru sıra); C1 ile koşullar karşılıklı dışlayan |
| Retry loop riski | `cite_gap_forced_once` bayrağı (C1'in `c1_forced_once` deseni) — invariant test-kilitli olmadan merge YOK |

## 6. Recommended design

- **Tetik (deterministik saf predicate, `citation.py`'ye):** `guard_flag ∧ all_sources ∧ not cite_gap_forced_once ∧ _is_substantive(candidate) ∧ not _CITE_TOKEN_RE.search(candidate)` — mevcut yapıtaşlarından, LLM-judge yok.
- **Yer:** tool-loop **natural-final branch** (C1'in yanı, `app_research_stream.py` L886-917 deseni): nudge user-mesajı append + `continue`; `tool_choice="auto"` (model isterse yeni arama yapabilir — alakasız kaynak durumunda meşru çıkış).
- **Retry sonrası:** ne gelirse servis edilir — **hard-refuse YOK** (kaynak var; refuse yanlış sınıf; dürüst "bulamadım" meşru cevap).
- **Telemetri (PII-suz):** `thinking_step` phase=`citation_gap_retry` + retry-sonucu `citation_filter` adımında zaten görünür; post-retry hâlâ 0 cite → `_log_coverage_gap("citation_gap", …)`.
- **Flag:** `research.citation_gap_guard_enabled`, **default False** (diğer guard'lar ON ama kanıtlanmış; bu yeni → OFF doğar; ON'a terfi canary sonrası ayrı karar).
- **4 organik vakaya etki:** kanıt-vakası (substantive+citation'sız+refuse-wording'siz) en net kazanım; gündem-dump vakalarında 2. kol veya yeni arama; dürüst-bulamadım vakasında düşük zarar riski + latency.

## 7. Minimal implementation plan (yalnız plan)

| Adım | Kapsam |
|---|---|
| **S-1 (ÖNCE, ayrı issue)** | Search-arg observability micro-PR — tool-call arama metnini `thinking_steps` meta'sına PII-bilinçli persist; önce kendi reality-analysis'i. Guard canary'sinin teşhis altyapısını kurar + sınıf-A/sınıf-3 teşhisine bağımsız değer. **→ Analiz + implementation + micro-canary TAMAMLANDI: [[search-arg-observability-analysis-2026-06]]** (#1483, [#1486](https://github.com/selmanays/nodrat/pull/1486)) — canary başarılı (5/5 searches[], 11/11 key-set, PII/log sızıntısı 0, behavior-neutral), **flag reset/OFF (baseline)**. S-2 guard çalışması artık teknik olarak hazır (canary'de gereken telemetri kanıtlandı) ama **ayrı onay** gerektirir. **S-2 hâlâ başlamadı.** |
| **S-2 (SONRA, ayrı issue)** | Citation-gap guard tek PR: `citation.py` saf helper + nudge sabit metni · `app_research_stream.py` flag-gated ~15 satır (natural-final branch) · `settings_admin/routes.py` registry +1 bool (default False) · `coverage_gap("citation_gap")` |
| S-2 canary | Ayrı onay: admin-only micro-canary (flag kısa süreli ON + 5-10 spot-check; decomposition micro-canary protokolü); allowlist-setting ilk aşamada gereksiz (PR-E kalıbı hazır) |

## 8. Tests

- **Saf helper unit:** gate kombinasyon matrisi (~8 test; `test_research_stream_helpers.py` faithfulness 4-AND gate kalıbı emsal).
- **Flag-OFF byte-identical:** default False → mevcut SSE-replay + orchestrator + decomposition-baseline kanıt kalıbı (#619 PR-3 emsali) + 1 explicit guard-OFF testi.
- **Flag-ON davranış:** AsyncMock kalıbıyla (test_query_decomposition_baseline.py `_search_news_patches` emsal) nudge-append + phase-emit.
- **One-shot retry / no loop:** `forced_once` ikinci kez tetiklemez — invariant testi.
- **PII-free telemetry:** nudge sabit-metin + telemetri key-set exact-match (PR-F `test_telemetry_payload_is_pii_free` kalıbı).
- **Regression:** C1/cited-only/faithfulness mevcut testleri dokunulmadan geçer; schema yok.

## 9. Hard-stops

- `app/` davranış-kritik değişiklik → **implementation ayrı açık onay**; flag default-OFF + byte-identical kanıtı olmadan merge YOK; characterization diff≠0 → DUR.
- Schema/migration/data/embedding mutation YOK.
- Telemetri/nudge'a query/user_id/email girerse DUR (sabit metin + enum-only).
- Prod flag ON (canary dahil) = prod-config hard-stop → ayrı onay + reset planı.
- Retry loop invariant'ı (`forced_once`) test-kilitli olmadan merge YOK. lint-imports 16/16; CI otoriter.

## 10. Final recommendation

1. **Guard yapılmalı** — Opt-B, flag-OFF, tek küçük PR; boşluk yapısal ve vaka-kanıtlı.
2. **S-1 ve S-2 iki AYRI issue** — farklı dosya/risk profili.
3. **Sıra: önce S-1 search-arg observability** (sıfır davranış riski; guard canary'sini besler), sonra S-2.
4. Organik N=4 küçük → guard'ın değer kanıtı canary'den gelir; default-ON'a terfi ayrı karar. **Her adım implementation öncesi ayrı onay.**

## İlişkiler

- [[query-failure-analysis-2026-06]] — tetikleyici analiz; §8 citation-loss follow-up bu sayfanın problem tanımıdır.
- [[query-decomposition-postmortem]] — ark bağlamı (#619 rafta; bu analiz post-mortem'in "sonraki değerli iş" zincirinin devamı).

## Kaynaklar

- `apps/api/app/api/app_research_stream.py` §838 (retrieval_forced) · §886-913 (C1 gate + `c1_forced_once`) · §1069-1081 (cited-only refuse) · §1098-1107 (faithfulness reframe) · §1125-1137 (citation_filter display-only).
- `apps/api/app/modules/generations/citation.py` §48-54 (`_is_substantive`) · §65-91 (marker regex) · §96-131 (reframe metni + 4-AND gate).
- `apps/api/app/prompts/research_answer.py` §40, 52-55, 104-106, 138-143, 306-336, 386-387 — prompt-katmanı citation kuralları.
- `apps/api/app/modules/settings_admin/routes.py` §1099-1142 — guard flag registry kalıbı (default/requires_restart konvansiyonu).
- [#1058](https://github.com/selmanays/nodrat/pull/1058) — cited-only hard invariant + C1 genişletmesi; [#1076](https://github.com/selmanays/nodrat/pull/1076) — RC3-B v2 (LLM-judgment kırılganlığı dersi); [#619](https://github.com/selmanays/nodrat/issues/619) — ark bağlamı.
- Keşif: 5 paralel read-only okuyucu (kod/prompt/settings/test/issue kayıtları), 2026-06-12.
