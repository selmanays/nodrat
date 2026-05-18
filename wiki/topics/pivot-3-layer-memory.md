---
type: topic
title: "Pivot 3-katman hafıza — L1 condense-only / L2 affinity-additive / L3 listeleme"
slug: "pivot-3-layer-memory"
category: "retrospective"
status: "live"
created: "2026-05-18"
updated: "2026-05-18"
sources:
  - "Plan rev.12 §7 + S5/S6/S11"
  - "PR #1026 (L1) / #1037 (L2) / #1029 (L3) / #1025 #1038 (küme)"
tags: ["retrospective", "pivot", "memory", "retrieval"]
aliases: ["3-katman-hafıza", "l1-l2-l3", "pivot-memory"]
---

# Pivot 3-katman hafıza — L1 / L2 / L3

> **TL;DR:** Pivot 3 ayrı hafıza katmanı + global küme substratı ekledi; **hiçbiri cevap-üretim çekirdeğine dokunmaz**, hepsi flag-gated + additive + flag-off byte-identical (#854). Katmanlar amaç-ayrık: L1 yalnız condense, L2 yalnız retrieval-recall, L3 yalnız listeleme.

## Bağlam

"Geniş hafıza" tek monolit değil; asistan-tonuna geri kaymayı (sentez/uydurma) önlemek için **amaç-ayrık 3 katman**. Her biri ayrı PR, ayrı flag, ayrı invariant.

## Ana içerik

| Katman | Ne yapar | NE YAPMAZ | Koruma |
|---|---|---|---|
| **L1** (#1026) | Zaman-pencereli bağlam — YALNIZ condense'i besler | Asıl cevap prompt'una GİRMEZ | 5-katman kirlilik koruması (S5): standalone-yeterlilik no-op + relatedness kapısı + en-dar-pencere cascade + rewrite-drift reddi + kanıt; flag-off byte-eş |
| **L2** (#1037) | retrieval-affinity: yüksek-affinity kümeye ait sonuca **ADDITIVE** boost | Cevap prompt/citation/halü/freshness DOKUNMAZ; **ASLA down-rank (S6)** | retrieval CACHE SONRASI (cross-user yok S11); flag+user gate; flag-off aynı obje |
| **L3** (#1029) | Geçmiş-araştırma **LİSTELEME** servisi | LLM sentez YAZMAZ (asistan-tonu geri-dönüş riski) | yapısal liste; ayrı servis/endpoint; cross-user yok |
| **Global küme** (#1025/#1038) | Trend/affinity substratı; gece atama + df-asimetri hiyerarşi | Cevaba girmez; içerik user-scoped | S11 çapa=korpus-entity; S12 boş→deprecate; [[global-research-cluster-model]] |

## Ne öğrenildi / neden bu tasarım

- **Bağlamı getirmek ≠ nasıl kullanılacağını söylemek** (#888 dersi) — L1 yalnız condense'e bağlı, asıl cevap heuristik-gate'e takılmaz.
- **Akıllı cache uyumu (S3):** asıl cevap cacheable prefix = STATİK system+tools; L1/geçmiş asıl prompt'a HİÇ girmez → #981 implicit-cache hit korunur. L2 retrieval cache'i user-agnostik (boost cache SONRASI).
- **Eğitim bütünlüğü:** `effective_query` persist L1'DEN ÖNCE (F2a #1024) → SFT/DPO INPUT'u L1 ile bozulmaz.
- **Asistan-tonu geri-dönüşü** en büyük risk → L3 sentez YASAK (yalnız listele); editöryal prompt (F1) asistan-nezaketi yasak.

## İlişkiler

[[pivot-editorial-research-engine]] · [[global-research-cluster-model]] · [[agentic-generate-orchestration]] (cevap çekirdeği — bu katmanlardan ETKİLENMEZ) · [[conversational-query-rewriting]] (L1 condense'i besler)

## Kaynaklar

Plan rev.12 §7 + S5/S6/S11; PR #1024/#1026/#1025/#1027/#1028/#1029/#1037/#1038 — bu oturum (otonom F-SYNC, conv quirky-gates 2026-05-18).
