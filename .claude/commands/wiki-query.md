---
description: Wiki'ye soru sor — sentezleyip cevapla, değerli ise topics/'e arşivle (CLAUDE.md §3.2)
argument-hint: <soru veya konu>
---

# /wiki-query

CLAUDE.md §3.2 QUERY protokolünü uygula.

**Soru:** $ARGUMENTS

## Adımlar

1. **`wiki/index.md` tara** — ilgili görünen sayfa(lar)ı belirle (kategori + slug + 1-cümle özet üzerinden).
2. **Sayfaları oku** — ilgili 3-7 sayfayı `Read` ile aç.
3. **Eksik bağlam varsa kaynaklara in** — `wiki/sources/<slug>.md` üzerinden ilgili `docs/...` ilgili section'a git.
4. **Sentezle** — her iddiayı `[[slug]]` veya `docs/...` linki ile bağla.
5. **Quote yapma** — kendi kelimenle yaz. Kopyalama ≥15 kelime ⇒ kaynak linki.
6. **Yanıt değerli mi?**
   - **Yeni karşılaştırma/sentez** içeriyor → `wiki/topics/<slug>.md` olarak arşivle (kullanıcıya sor).
   - **Yeni locked decision**'a işaret ediyor → kullanıcıya sor: "Bunu locked decision olarak `wiki/decisions/<slug>.md` kaydedelim mi?"
   - **Sadece bilgi getiriyor** → arşivlemeye gerek yok.
7. **Arşivlenirse `wiki/log.md` ekle:**
   ```markdown
   ## [YYYY-MM-DD] query | <soru özeti>
   - **Soru:** ...
   - **Yanıt sayfası:** [[topic-slug]]
   - **Kullanılan sayfalar:** [[s1]], [[s2]], ...
   ```

## Branch disiplini

Eğer arşivleme yapılacaksa **CLAUDE.md §1.3** uygulanır: write işlemi `main` veya `wiki/*` branch'inde olmalı. Feature worktree'sindeysen önce TODO notu tut, ayrı PR aç.

## Yanıt formatı

- **TL;DR ilk cümlede.** Kullanıcı tüm cevabı okumadan ana noktayı alsın.
- **Her iddia bağlantılı** — `[[slug]]` veya `docs/...§N`.
- **Belirsizlik varsa** "Açık sorular" bölümü.
- **Tahmin yapma.** Veri yoksa "Wiki'de henüz bu kapsama girmiş kaynak yok" de.
