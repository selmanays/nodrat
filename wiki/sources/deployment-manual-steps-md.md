---
type: source
title: "docs/operations/deployment-manual-steps.md — Deployment Manual Steps"
slug: "deployment-manual-steps-md"
status: "ingested-summary"
source_path: "docs/operations/deployment-manual-steps.md"
source_version: "v1.0 (2026-05-02)"
source_updated: "n/a"
created: "2026-05-11"
updated: "2026-05-11"
ingest_method: "summary-only (bulk auto-generated, #696 D16 continuation)"
tags: ['docs', 'operations', 'operations', 'devops']
---

# Source: docs/operations/deployment-manual-steps.md

> **TL;DR:** VPS deployment manuel adımları (rsync + docker compose build + force-recreate). GitHub Actions runner fail fallback. 473 satır, 13 ana bölüm.

## Section Map

| § | Başlık |
|---|---|
| §1 | 0. Hızlı checklist (kullanıcının uyandığında yapacakları) |
| §2 | 1. API Anahtarları (Production .env) |
| §3 | 2. Backblaze B2 Backup (#41) |
| §4 | 3. sops + age secrets management (#38) |
| §5 | 4. GitHub Actions secrets |
| §6 | 5. Admin user yönetimi |
| §7 | 6. Cloudflare DNS (zaten yapıldı) |
| §8 | 7. Production smoke test (her deploy sonrası) |
| §9 | 8. Closed alpha launch (ayrı doc) |
| §10 | 9. Yaygın gotchas (kaybedilen saatler) |
| §11 | 10. Acil durum (incident response) |
| §12 | 11. MVP-1.5 Migration (Epic #215) — DONE 2026-05-06 |
| §13 | Değişiklik notları |

## İlişkiler

(Detay entity/concept extraction sonraki sprintte — bu sayfa minimum-viable
source özet'i. Direct backlink'ler kategori bazında [[wiki/index|index]]'te kataloglu.)

## Versiyon takibi

| Doküman v | Tarih | Notlar |
|---|---|---|
| v1.0 (2026-05-02) | n/a | İlk ingest (auto-generated) |

## Açık takip

1. **Detay entity/concept extraction** — bu sayfa sadece source özet'i. Her ana bölüm için kendi wiki sayfası gelecek sprintte yapılacak (varlık/kavram/karar çıkarımı).
2. **Backlink integrity** — wiki/decisions ve wiki/concepts'ten bu source'a ters yön backlink eklenmesi
3. **Versiyon takibi** — kaynak dosya güncellendiğinde source_version + source_updated bump

## Kaynak

- [docs/operations/deployment-manual-steps.md](../../docs/operations/deployment-manual-steps.md)
