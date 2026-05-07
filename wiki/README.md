---
title: Nodrat Wiki — İkinci Beyin
type: hub
updated: 2026-05-07
---

# Nodrat Wiki

LLM tarafından sürdürülen, Nodrat dokümanlarının üzerine inşa edilmiş kalıcı bilgi tabanı.

## Üç katman

```
docs/    ← KAYNAK katmanı (kanonik, immutable). LLM yalnızca okur.
wiki/    ← İKİNCİ BEYİN (LLM yazar/günceller). Özetler, varlıklar, kavramlar, sentezler.
INDEX.md ← İnsan tarafından sürdürülen kanonik doküman indeksi (root'ta).
```

`wiki/` içeriğinin tamamı LLM tarafından üretilir ve sürdürülür. İnsan sadece kaynakları seçer ve sorular sorar.

## Klasör yapısı

| Klasör | İçerik | Örnek |
|---|---|---|
| `entities/` | Somut "şey"ler | DeepSeek V3, persona-p1a, NodratBot, Contabo VPS |
| `concepts/` | Soyut kavramlar | WSGAU, citation coverage, RAPTOR, PII redaction |
| `topics/` | Sentez / karşılaştırma | LLM provider karşılaştırması, MVP-2 teslimat özeti |
| `decisions/` | Locked kararlar | DeepSeek default, 18+ gate, 25-kelime quote cap |
| `sources/` | Kaynak doküman özetleri (`docs/` köprüsü) | PRD özet, architecture.md özet |
| `_templates/` | Sayfa şablonları | entity, concept, topic, decision, source |
| `assets/` | İndirilen görseller, ekler | — |

## Hub dosyalar

- **`index.md`** — tüm wiki sayfalarının kataloğu (her sayfa: link + 1 satır özet). LLM her ingest'te günceller.
- **`log.md`** — kronolojik bakım kaydı (`## [YYYY-MM-DD] ingest|query|lint | başlık`).
- **`SETUP.md`** — Obsidian + Local REST API + MCP server kurulum kılavuzu.

## İş akışları

LLM agent için kurallar ve protokoller kök [`CLAUDE.md`](../CLAUDE.md) dosyasında. Üç ana iş akışı:

1. **Ingest** — yeni kaynak (`docs/...`) → varlık/kavram/karar sayfaları + index/log update.
2. **Query** — kullanıcı sorusu → wiki içinde arama + sentez + (değerli yanıt ise) yeni `topics/` sayfası.
3. **Lint** — periyodik sağlık taraması: yetim sayfa, çelişki, eksik backlink, geçersiz iddia.

## Erişim

- **Doğrudan dosya:** Claude Code Read/Edit/Grep ile her zaman erişir.
- **Obsidian:** `nodrat/` klasörünü vault olarak aç → graph view, backlink panel, full-text search.
- **MCP:** Obsidian Local REST API + `@bitbonsai/mcpvault` MCP server. Kurulum: [SETUP.md](SETUP.md).

## Versiyonlama

`wiki/` klasörü git altındadır. Her ingest, query archive ve lint pass'i ayrı bir commit olarak izlenebilir. Çatışma riskini azaltmak için PR akışı önerilir (büyük ingestler için `wiki/` branch).

---

**Sürdürme:** Bu README'yi güncellerken sadece klasör yapısı, hub dosyalar ve giriş noktası bilgileri değişmeli. Detaylı kurallar `CLAUDE.md`'de.
