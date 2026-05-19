---
type: decision
title: "Pivot — sohbet/asistan → editöryal haber/araştırma motoru"
slug: "pivot-editorial-research-engine"
status: "locked"
decided_on: "2026-05-18"
decided_by: "founder"
created: "2026-05-18"
updated: "2026-05-19"
sources:
  - "Plan rev.12 (nodrat-ta-r-n-y-n-n-nemli-deep-forest)"
  - "Milestone 'Pivot: Editöryal Haber/Araştırma Motoru' (#1011..#1022)"
tags: ["locked-decision", "pivot", "product", "architecture"]
aliases: ["pivot", "editöryal-motor", "araştırma-motoru-pivotu"]
---

# Pivot — sohbet/asistan → editöryal haber/araştırma motoru

> **Karar:** Nodrat klasik "sohbet/asistan" UX'inden **editöryal haber/araştırma motoru**na çevrildi: her sorgu bağımsız araştırma çıktısı; asistan-nezaketi yasak; görünmez zaman-pencereli bağlam; kapsam-dışı istek yumuşak yönlendirilir; geçmiş **listelenir, sentezlenmez**.
> **Durum:** locked
> **Tarih:** 2026-05-18

## Bağlam

Ürün kimliği "araştırmacı asistan" → "araştırma motoru" olarak konumlandırıldı (rakip ChatGPT-asistan değil, Perplexity-tarzı kaynaklı editöryal). Bu, davranış + dil + arka-uç hafıza substratını etkiledi ama **cevap-üretim çekirdeği (citation [n]/cited-only, halü/freshness #928/#906/#888)** kasıtla DOKUNULMADAN bırakıldı — pivot additive/flag-gated katmanlar olarak inşa edildi.

## Faz haritası (F0–F6 teslim; F7 koşullu-ertelendi)

| Faz | İçerik | PR |
|---|---|---|
| F0 | Dev wipe (yalnız test-user chat kayıtları + chat_cache_telemetry; users/sub/billing KORUNDU) | #1011 |
| F1 | Editöryal prompt (asistan-nezaket YASAK + kapsam-dışı deflection + opsiyonel başlık); legacy "asistan"→"araştırma motoru" | #1023 |
| F2a | `messages.effective_query` persist (eğitim INPUT bütünlüğü — L1 ÖNCESİ; #854) | #1024 |
| F2b | L1 zaman-pencereli bağlam — YALNIZ condense'i besler, asıl cevaba GİRMEZ; 5-katman kirlilik koruması; flag-off byte-eş | #1026 |
| F3/3b/3c | GLOBAL `research_clusters`/`message_clusters` + gece atama + ilgi/küme admin gözlem endpoint | #1025/#1027/#1028 |
| F4 | L3 geçmiş-araştırma **listeleme** servisi (sentez YOK) + Faz4 prompt kuralı | #1029 |
| F5 | L2 retrieval-affinity — additive, down-rank YOK (S6), flag-off byte-eş | #1037 |
| F6 | GLOBAL hiyerarşi rafine — aggregate df-asimetri, false-positive YOK | #1038 |
| F7 | Fiziksel rename chat→research — **TESLİM** (atomik BE/FE; migration 20260519_0100; A/B sınırı) | #1052/#1053 |

## Güncelleme — 2026-05-19 (F7 teslim + davranışsal düzeltmeler)

Önceki sync'te (2026-05-18) F0–F6 teslim, F7 ertelenmişti. Bu seansta:

- **Davranışsal pivot düzeltmesi:** "UI değişmez" = layout/bileşen sabit, **davranış değişir**. Her sorgu bağımsız araştırma; backend invariantı 409 ile thread'i yapısal imkânsız kılar → [[research-single-turn-invariant]] (#1045/#1046/#1048).
- **L1 yeniden tasarım:** cosine relatedness KANITLI hatalı (belirsiz takip ↔ eski belirsiz takip 0.985 > içerikli antecedent 0.605) → S5 Gate-1 standalone + recency-anchored çapa → [[l1-recency-anchored-context]] (#1049 hatalı → #1051).
- **F7 rename TESLİM:** "chat" ürün katmanından kaldırıldı; B (LLM-primitifi) + dış-standart korundu → [[faz7-chat-research-rename]] (#1052/#1053).
- **Deploy güvenilirliği:** schema-drift incident kalıcı çözüldü (assert + force-recreate kör-nokta) → [[deploy-schema-drift-hardening]] (#1047/#1054).
- **CI-health:** flaky JWT testi (base64url son-karakter artık-bit) deterministik yapıldı (#1050).

### F7-sonrası cevap-bütünlüğü sertleştirme (#1058/#1059)

F7 rename sonrası prod-audit (conv 865e36e3) bağlamlı takipte halüsinasyon yakaladı (0 kaynak + elle `[Forbes Türkiye]` + devrik cümle):

- **Cevap-bütünlüğü HARD invariant** (#1058): 0 GERÇEK kaynak + substantive → servis edilmez (dürüst red); sayısal-olmayan uydurma atıf da C1 düzeltici turu tetikler; bağlamlı takip → zorunlu retrieval (Fix B′); condense kaynak-adı sızıntısı kapatıldı (Fix C) → [[research-cited-only-hard-invariant]]. Çekirdek invariant DOKUNULMADI; flag-gated default-ON.
- **Retrieval aşama şeffaflığı** (#1059, gözlem-only): cevap üretilirken aşamalar `ThinkingPanel`'de okunur → [[research-retrieval-transparency]]. Kullanıcının istediği 3-kademeli chunk-cascade DEĞİL (eval-gate'li ayrı iş; ileriye uyumlu).
- **Ops gözlem:** GitHub Actions kredisi geri gelmiş — bu seansta hem CI hem Deploy-to-VPS otomatik koştu (#1058/#1059 auto-deploy + v2-hardened doğrulandı); `actions_credits_exhausted` varsayımı artık geçersiz → [[deploy-schema-drift-hardening]].

## Alternatifler ve neden reddedildi

| Alternatif | Neden reddedildi |
|---|---|
| Cevap çekirdeğini de yeniden yaz | Citation/halü/freshness invariantı riske girer; kanıtlı kalite makinesi korunmalı (S6/S11) |
| Kullanıcı-metrik ağırlıklı (davranışsal A/B) | Kullanıcı: product-led, metrik-azalt; pre-launch dev tek-DB |
| Tek seansta UI davranış+yerleşim dahil | Davranışsal UX **ayrı seans**a ertelendi; bu plan metin+arka-uç+admin |
| F7 rename'i şimdi | Çekirdek tablo rename = en yüksek blast-radius; opsiyonel; ertelendi |

## Sonuçlar

- **İnvaryant (DOKUNULMADI):** cevap prompt, citation [n]/cited-only, halü/freshness/#928/#906/#888, LLM routing, agentic loop, search_news/wikipedia, quota/billing, auth.
- Tüm yeni katmanlar **flag-gated + additive + flag-off byte-identical (#854)** → prod davranışı varsayılan değişmez; aktivasyon admin-tunable.
- İlişki: [[global-research-cluster-model]] · [[pivot-3-layer-memory]] · [[agentic-generate-orchestration]] (cevap çekirdeği — DOKUNULMADI) · [[research-cited-only-hard-invariant]] (F7-sonrası halü sertleştirme) · [[research-retrieval-transparency]] (aşama şeffaflığı)

## Geri alma maliyeti

> Her faz bağımsız flag/revert: settings flag kapat → ilgili katman no-op (retrieval/condense eski davranış). F0 wipe Object Storage yedeğinden geri (pre-launch tek-DB). Çekirdek dokunulmadığı için pivot-geri-alma = flag'leri kapat; veri additive (mevcut tablo/şema bozulmadı).
