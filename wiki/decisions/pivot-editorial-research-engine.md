---
type: decision
title: "Pivot — sohbet/asistan → editöryal haber/araştırma motoru"
slug: "pivot-editorial-research-engine"
status: "locked"
decided_on: "2026-05-18"
decided_by: "founder"
created: "2026-05-18"
updated: "2026-05-18"
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
| F7 | (Koşullu) fiziksel rename — **ERTELENDİ** (en yüksek blast-radius; pivot değeri rename'siz tam; UI seansıyla eşli) | #1021 |

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
- İlişki: [[global-research-cluster-model]] · [[pivot-3-layer-memory]] · [[agentic-generate-orchestration]] (cevap çekirdeği — DOKUNULMADI)

## Geri alma maliyeti

> Her faz bağımsız flag/revert: settings flag kapat → ilgili katman no-op (retrieval/condense eski davranış). F0 wipe Object Storage yedeğinden geri (pre-launch tek-DB). Çekirdek dokunulmadığı için pivot-geri-alma = flag'leri kapat; veri additive (mevcut tablo/şema bozulmadı).
