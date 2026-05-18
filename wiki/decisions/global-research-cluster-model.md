---
type: decision
title: "Global araştırma kümesi modeli — tek sağlayıcı, çok dinleyici"
slug: "global-research-cluster-model"
status: "locked"
decided_on: "2026-05-18"
decided_by: "tech"
created: "2026-05-18"
updated: "2026-05-18"
sources:
  - "Plan rev.12 §3/§7 + S11/S12"
  - "apps/api/app/models/research_cluster.py"
  - "PR #1025 (#1015 Faz 3) / #1038 (#1020 Faz 6)"
tags: ["locked-decision", "pivot", "clustering", "privacy"]
aliases: ["tek-sağlayıcı-çok-dinleyici", "research-cluster-model", "global-küme"]
---

# Global araştırma kümesi modeli — tek sağlayıcı, çok dinleyici

> **Karar:** Araştırma kümeleri **GLOBAL kanonik düğüm** (`research_clusters`, user_id TAŞIMAZ); kullanıcı görünürlüğü `message_clusters ⋈ WHERE user_id=?` ile **türetilir** (cross-user sızma yok). Atama GECE batch. Hiyerarşi **kullanım deseninden** (df-asimetri), ansiklopediden DEĞİL.
> **Durum:** locked
> **Tarih:** 2026-05-18

## Bağlam

3-katman hafızanın ([[pivot-3-layer-memory]]) küme substratı. "Tek sağlayıcı, çok dinleyici": tek kanonik "CHP" düğümü; içerik user-scoped görünür. Global → depolama/işlem azalır, hiyerarşi aggregate sağlam, trend-sinyal substratı tutarlı.

## Kritik gizlilik kısıtı (S11) — UNUTMA

Küme **çapası YALNIZ haber-korpusu (`entities`) entity'si**. Entity'siz sorgu → embedding-centroid fallback **yalnız MEVCUT aktif küme'ye** bağlanır; **yeni global küme MİNTLEMEZ** → özel-sorgu metni/adı global düğüm yaratmaz, başka kullanıcıya sızmaz. S12: boş aktif küme → async soft-deprecate (`deprecated_at`).

## Hiyerarşi (Faz 6) — kullanım deseni, ansiklopedi DEĞİL

`parent_cluster_id` aggregate co-occurrence + **df-asimetri** ile (#1020): B child-of-A ANCAK asimetrik kapsama (P(A|B)≥hi ∧ P(B|A)≤lo) + A daha genel (df/occ). **Salt birlikte-geçme YETMEZ** → Erdoğan↔Özel simetrik = yanlış-ebeveyn OLMAZ (eşik-korumalı, false-positive yok). Aggregate yalnız COUNT (içerik ifşa olmaz). Idempotent + reversible (düz-küme-önce; flag-off no-op).

## Alternatifler ve neden reddedildi

| Alternatif | Neden reddedildi |
|---|---|
| Per-user küme | Depolama/işlem ↑, hiyerarşi zayıf, trend-sinyal tutarsız |
| Per-answer atama | Çekişme (S7); gece batch → izole, NER ETL deseniyle hizalı |
| Entity'siz sorgudan yeni küme | S11 ihlali — özel-sorgu adı global'e sızar → fallback yalnız mevcut |
| Ansiklopedik hiyerarşi | Yanlış; kullanım-aggregate + df-asimetri (çıkarım, kesin değil) |

## Sonuçlar

- Şema additive: `research_clusters`/`message_clusters` (mevcut tablo/trigger değişmez). FK: message_id CASCADE, cluster_id RESTRICT, user_id CASCADE (KVKK).
- Cevap-üretim akışı **DOKUNULMAZ** — küme paylaşımlı, içerik user-scoped (sızma yok).
- İlişki: [[pivot-editorial-research-engine]] · [[pivot-3-layer-memory]]

## Geri alma maliyeti

> flag (`research.clustering.enabled` / `research.hierarchy_refine_enabled`) kapat → gece job no-op; tablolar additive (mevcut şema bozulmaz). Hiyerarşi reversible (düz-küme recompute). Pre-launch dev → düşük maliyet.
