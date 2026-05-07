---
description: Bir docs/ dokümanını wiki/'ye ingest et (CLAUDE.md §3.1 protokolü)
argument-hint: <docs/.../*.md> veya boş (sıradaki öneri için)
---

# /wiki-ingest

CLAUDE.md §3.1 INGEST protokolünü uygula.

**Kaynak:** `$ARGUMENTS`

## Adımlar

1. **Branch güvenlik kontrolü.** `git rev-parse --abbrev-ref HEAD` çıktısı `main` veya `wiki/*` değilse, **DUR** ve sor: "Şu anda `<branch>` branch'indeyim. CLAUDE.md §1.3'e göre wiki yazma sadece `main` veya dedicated `wiki/*` branch'inde yapılır. Yeni `wiki/<slug>` branch'i açayım mı (origin/main'den), yoksa mevcut PR'ını merge edip sonra mı?"
2. **Argüman boşsa:** `wiki/log.md` son giriş notlarından sıradaki öneriyi al, kullanıcıya 3 seçenek sun.
3. **Kaynağı oku** baştan sona — section haritası çıkar.
4. **Mevcut wiki tarama:** `wiki/index.md`'i + `Grep -r "<slug aday>" wiki/` ile çakışma kontrolü. Var ise: `wiki/sources/<slug>.md`'in `source_version`'unu karşılaştır → sürüm değişikliği takibi tablosunu güncelle.
5. **Çıkarım kategorileri:**
   - **Entities** — provider, persona, servis, platform, tool, doküman, risk objesi.
   - **Concepts** — metric, technique, rule, framework, architecture-pattern.
   - **Decisions** — locked kararlar (✅ / "lock" işaretli + INDEX §4 ile uyumlu).
   - **Topics** — sentez / karşılaştırma / timeline / retrospective / playbook.
6. **Çakışma & çelişki tespiti:**
   - Slug çakışması → kategori prefix ekle.
   - Kaynak ↔ INDEX ↔ diğer wiki sayfaları farkı → `> ⚠️ Çelişki:` bloğu (her iki sayfada da).
7. **Sayfa oluştur/güncelle** — `wiki/_templates/<type>.md`'den şablonu kopyala, frontmatter doldur, bölümleri kaynaktan besle.
8. **Bidirectional backlink şart.** A→B varsa B'de A linki olmalı. Yeni sayfanın bağlandığı diğer sayfaları da güncelle.
9. **`wiki/index.md` güncelle** — yeni/değiştirilen sayfalar için satır ekle/güncelle. İstatistik bloğunu güncelle (toplam sayfa, kaynak sayısı, son ingest tarihi, açık çelişki sayısı).
10. **`wiki/log.md` ekle:**
    ```markdown
    ## [YYYY-MM-DD] ingest | <kaynak başlık>
    - **Kaynak/Tetikleyici:** docs/.../...md (vX.Y)
    - **Etkilenen sayfalar:** [[slug-1]], [[slug-2]], ...
    - **Yeni:** N
    - **Güncellendi:** M
    - **Notlar:** sürpriz bulgu, çelişki, eksiklik
    ```
11. **3-5 satır rapor:** kaç sayfa yaratıldı, hangi entity/concept'ler eklendi, açık sorular, çelişki sayısı.

## Pilot kuralı (CLAUDE.md §3.1)

Bir dokümandan beklenen sayfa sayısı: **8-15**. Daha azı = kaynağı yeterince ezmedin; daha fazlası = granülasyon çok ince, birleştir.

## Yazma disiplini

- `docs/`'a asla yazma — sadece oku.
- Her sayfa: frontmatter + TL;DR + Kaynaklar zorunlu.
- Her iddia kaynağa bağlı; yoksa "(LLM çıkarımı)" işareti.
- Quote yok; kendi kelimenle yaz.
