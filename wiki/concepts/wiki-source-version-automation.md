---
type: concept
title: "Wiki source version automation — docs/ değişikliği otomatik bump"
slug: "wiki-source-version-automation"
category: "tooling"
status: "live"
created: "2026-05-11"
updated: "2026-05-11"
sources:
  - ".github/workflows/wiki-source-sync.yml"
  - "GitHub Issue #696 (D17 versiyon takibi otomasyonu)"
  - "CLAUDE.md §3.1 INGEST + §1.3 paralel worktree write disiplini"
tags: ["wiki", "automation", "github-actions", "tooling", "version-tracking"]
---

# Wiki Source Version Automation

> **TL;DR:** GitHub Actions workflow `docs/**/*.md` değiştiğinde `wiki/sources/<slug>-md.md` frontmatter'ında `source_version` + `source_updated` alanlarını otomatik bump eder. PR'da yorum bırakır, main merge sonrası bot commit'iyle uygular.

## Sorun

CLAUDE.md §3.1 INGEST kuralı: kaynak doküman güncelse `wiki/sources/<slug>.md` versiyon takibi yapılmalı. Manuel yapılırsa unutulur → wiki out-of-sync olur.

Önceki sprint #696 D16: 35 source sayfası ingest edildi; versiyon takibi manuel.

## Çözüm

`.github/workflows/wiki-source-sync.yml` workflow:

1. **Tetik:** `push to main` veya `pull_request` `docs/**/*.md` patikası
2. **Diff:** önceki commit veya base branch ile karşılaştır
3. **Bump:** her değişen `docs/<X>.md` için karşılığı `wiki/sources/<X>-md.md` frontmatter:
   - `source_version: "v0.X"` ← doc başlığından yeni okunur
   - `source_updated: "YYYY-MM-DD"` ← doc başlığından
4. **Aksiyon:**
   - PR ise: PR'a yorum (bump önerisi listesi)
   - main push: `nodrat-wiki-bot` user ile otomatik commit + push

## Workflow Mantığı (Python adımı)

```python
# Her değişen docs/<X>.md için:
slug = doc_path.stem + "-md"
source_md = Path(f"wiki/sources/{slug}.md")
new_version = parse_doc_header(doc_path)  # "**Sürüm:** v0.X" satırı
new_updated = parse_doc_header(doc_path)  # "**Son güncelleme:** YYYY-MM-DD"

# wiki/sources/<slug>-md.md frontmatter REGEX replace
re.sub(r'^source_version: "[^"]*"', f'source_version: "{new_version}"', ...)
re.sub(r'^source_updated: "[^"]*"', f'source_updated: "{new_updated}"', ...)
```

## Güvenlik

- **Bot user:** `nodrat-wiki-bot` (workflow-only, real user değil)
- **Sadece wiki/sources/ frontmatter** değiştirir; body değil
- **Paralel worktree disiplini (CLAUDE.md §1.3):** bot main'e direkt commit; feature worktree etkilenmez
- **PR yorumlarında:** "Merge sonrası otomatik bump uygulanacak" mesajı kullanıcıya görünür

## Eksikler / Açık Takip

1. **Yeni docs/ dosyası** — workflow sadece mevcut wiki/sources için bump yapar; yeni doc ingest gerek (manuel `/wiki-ingest`)
2. **Doc'tan version okuma** — basit regex; markdown frontmatter farklı stil kullanırsa fail
3. **PR yorum text/emoji** — Türkçe + emoji destek

## CLAUDE.md Uyumu

- §3.1 INGEST 8. madde "log notu" — bot commit message'da değişiklik listesi
- §1.3 paralel write disiplini — bot main'e PR-free commit ama bu OK (workflow zaten kontrollü)
- §3.4 wiki ingest disipline — bu otomasyon manuel ingest'in yerine geçmez; sadece versiyon takibi

## İlişkiler

- [[data-model-md]] — örnek sürüm bump hedefi
- [[api-contracts-md]]
- [[architecture-md]]
- [[prompt-contracts-md]]
- [[risk-register-md]]

## Kaynaklar

- [.github/workflows/wiki-source-sync.yml](../../.github/workflows/wiki-source-sync.yml)
- [Issue #696 D17](https://github.com/selmanays/nodrat/issues/696)
