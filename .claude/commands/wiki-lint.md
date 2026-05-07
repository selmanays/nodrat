---
description: Wiki sağlık taraması — yetim sayfa, çelişki, kırık link, eksik backlink (CLAUDE.md §3.3)
---

# /wiki-lint

CLAUDE.md §3.3 LINT protokolünü uygula. 8 kontrol kategorisi:

## Kontroller

1. **Yetim sayfa** — hiçbir sayfaya backlink'i olmayan sayfa. Kullanıcıya bildir, silme önerisi yapma.
2. **Kırık wiki-link** — `[[slug]]` referansı var ama hedef dosya yok. Düzelt veya kullanıcıya işaret et.
3. **Eksik backlink** — Sayfa A, B'yi ilgilendiriyor ama B'de A'ya link yok (bidirectional ihlal). Otomatik ekle veya öner.
4. **Çelişki** — iki sayfa aynı şey için farklı değer söylüyor. Her iki sayfaya `> ⚠️ Çelişki:` bloğu ekle, log'a not düş.
5. **Eskimiş iddia** — kaynağın güncel sürümüyle wiki'deki bilgi uyuşmuyor (`source_updated` ↔ `wiki updated` farkı). `git log -- docs/...` ile son değişiklik tarihi karşılaştır.
6. **Adı geçen ama sayfası olmayan kavram** — 3+ kez geçen ama kendi sayfası olmayan kavram → entity/concept oluşturma adayı.
7. **Boş frontmatter alanı** — zorunlu alanlar dolu mu (`type`, `slug`, `title`, `sources`, `status`, `created`, `updated`).
8. **Veri boşluğu** — sayfa içinde "TODO" / "?" / "açık soru" kalan yerler. Web aramasıyla doldurulabilecekler için aday liste.

## Bash yardımcıları

```bash
# Yetim sayfa (kabaca):
for f in wiki/{entities,concepts,topics,decisions,sources}/*.md; do
  slug=$(basename "$f" .md)
  count=$(grep -rl "\[\[$slug" wiki/ | grep -v "^$f$" | wc -l)
  [ "$count" -eq 0 ] && echo "yetim: $f"
done

# Kırık link:
grep -rEho "\[\[[a-z0-9-]+" wiki/ | sed 's/\[\[//' | sort -u | while read slug; do
  [ -z "$(find wiki -name "${slug}.md")" ] && echo "kırık: [[$slug]]"
done

# Çelişki blokları:
grep -rln "⚠️ Çelişki" wiki/

# Açık sorular:
grep -rln "Açık sorular" wiki/ | wc -l
```

## Çıktı

```
=== /wiki-lint raporu (YYYY-MM-DD) ===
Toplam sayfa: N

[1] Yetim sayfa: M    → [[slug-1]], [[slug-2]]
[2] Kırık link: K     → [[slug-x]] (4 yerde referans)
[3] Eksik backlink: P → A→B var, B'de A yok
[4] Çelişki: Q        → [[slug-y]] vs [[slug-z]]
[5] Eskimiş iddia: R  → kaynak güncel: docs/x.md (2026-MM-DD)
[6] Aday kavram: S    → "halüsinasyon" 5 yerde geçiyor, sayfası yok
[7] Boş frontmatter: T
[8] Veri boşluğu: U   → TODO/? sayısı
```

`wiki/log.md` lint kaydı:
```markdown
## [YYYY-MM-DD] lint | sağlık taraması
- Yetim: N · Kırık: K · Eksik backlink: P · Çelişki: Q
- Eskimiş: R · Aday kavram: S · Boş frontmatter: T · Veri boşluğu: U
- **Önerilen aksiyon:** ...
```

## Branch disiplini

Lint sırasında düzeltme yapılacaksa **CLAUDE.md §1.3**: write işlemi `main` veya `wiki/*` branch'inde olmalı.
