---
type: concept
title: "Conditional HTTP GET — ETag + If-Modified-Since"
slug: "conditional-http-get"
status: "live"
created: "2026-05-10"
updated: "2026-05-10"
sources:
  - "apps/api/app/core/rss.py"
  - "apps/api/app/core/http_client.py"
  - "apps/api/app/workers/tasks/sources.py"
  - "RFC 7232 — HTTP Conditional Requests"
tags: ["http", "rss", "performance", "bandwidth"]
aliases: ["304-not-modified", "if-none-match", "etag-polling"]
---

# Conditional HTTP GET — ETag + If-Modified-Since

> **TL;DR:** RSS feed fetch'lerinde sunucudan dönen `ETag` ve `Last-Modified` header'ları kaydedilir; sonraki fetch'te `If-None-Match` ve `If-Modified-Since` header'larıyla gönderilir. Sunucu içerik değişmediyse **HTTP 304 Not Modified** döner — body yok, ~%80 bandwidth tasarrufu, queue dispatch atlanır.

## Tanım / Bağlam

[RFC 7232](https://www.rfc-editor.org/rfc/rfc7232) tarafından tanımlanan standart HTTP cache-validation mekanizması. Nodrat'ta [[realtime-rss-polling]] kararı altında RSS pipeline'a entegre edildi (#565 Faz 0+1, PR [#571](https://github.com/selmanays/nodrat/pull/571)).

Faz 2'de polling interval'ı 30 dk'dan 60 sn'ye düşeceği için, Conditional GET olmasa yayıncı sunucusuna her dakika full feed indirmek hem bizim ağ trafiğimizi hem yayıncının load'ını şişirirdi. Conditional GET her iki taraf için de "şu an yeni içerik yoksa hiç response body göndermeme" sözleşmesidir.

## Mekanik

### 1. İlk fetch (cold)

```http
GET /rss HTTP/1.1
Host: example.com
User-Agent: NodratBot/1.0 (+https://nodrat.com/bot; contact: legal@nodrat.com)

→ HTTP/1.1 200 OK
  ETag: "abc123"
  Last-Modified: Sun, 10 May 2026 09:00:00 GMT
  Content-Type: application/rss+xml

  <?xml ... full body ...>
```

Worker `Source.etag = "abc123"` ve `Source.last_modified = "Sun, 10 May 2026 09:00:00 GMT"` olarak persist eder. `consecutive_unchanged = 0`.

### 2. Sonraki fetch (warm)

```http
GET /rss HTTP/1.1
Host: example.com
If-None-Match: "abc123"
If-Modified-Since: Sun, 10 May 2026 09:00:00 GMT

→ HTTP/1.1 304 Not Modified
  (no body)
```

Worker `FeedReport.not_modified=True` görür; queue dispatch ATLANIR; `consecutive_unchanged++`. Sayaç [[adaptive-polling-tier]] için tier kararında girdi olur.

### 3. İçerik değiştiğinde

```http
→ HTTP/1.1 200 OK
  ETag: "def456"
  Last-Modified: Sun, 10 May 2026 09:30:00 GMT
  ...
  <?xml ... new body ...>
```

Yeni etag/last_modified persist; `consecutive_unchanged = 0`; her item için `article_discover` dispatch.

## Kod referansları

- [apps/api/app/core/rss.py:149](../../apps/api/app/core/rss.py) — `fetch_feed(etag, last_modified)` parametreleri + 304 path + response header capture
- [apps/api/app/core/http_client.py:120](../../apps/api/app/core/http_client.py) — `fetch_text(extra_headers=...)` opsiyonel parametre (geriye uyumlu)
- [apps/api/app/workers/tasks/sources.py:312](../../apps/api/app/workers/tasks/sources.py) — `fetch_source_rss` task; 304 path = sayaç++, dispatch atla; 200 path = etag persist + sayaç sıfır

## Fallback davranışı

`httpx` bazı sunucu konfigürasyonlarında `RemoteProtocolError` fırlatır (#237 — örn. AA çift Transfer-Encoding header). Bu durumda `_curl_fallback()` devreye girer; **curl fallback path'inde `extra_headers` DESTEKLENMEZ** (curl_fallback signature'ında yok). Sonuç:

- Conditional GET header'ları sessizce düşer
- Sunucu 200 OK + full body döner
- Bizim kod 200'ü doğal akışta işler (etag persist + dispatch)

Bu kasıtlı bir tradeoff: edge-case sunucu uyumluluğu > Conditional GET marjinal kazancı.

## Kaynak davranış spektrumu (production gözlemi)

Türk haber siteleri arasında ETag/Last-Modified desteği eşit dağılmıyor:

| Kaynak | ETag | Last-Modified | Notu |
|---|---|---|---|
| haberturk | ✅ Weak ETag (`W/"..."`) | ❌ | Merlin CDN; her node farklı ETag → 304 nadir |
| TRT Haber | ❌ | ❌ | Hiç cache header yok |
| Evrensel | ❌ | ❌ | Hiç cache header yok |
| BBC Türkçe | ❌ (302 redirect zinciri) | ❌ | CDN cache-control max-age=60 var ama biz parse etmiyoruz |

→ Faz 2'de polling sıklığı artınca bandwidth tasarrufu çoğunlukla **haberturk benzeri ETag-aktif** kaynaklarda gerçekleşir. Diğerleri zaten 200 + full body döndüğünden Conditional GET sadece "no harm" değer taşır.

## İlişkiler

- [[realtime-rss-polling]] — Bu concept'in kullanıldığı locked decision
- [[adaptive-polling-tier]] — `consecutive_unchanged` sayacı tier kararında girdi
- [[data-pipelines]] §1 — Source crawl pipeline'ı; bu concept §1 fetch akışına entegre
- [[risk-source-fragility]] — R-OPS-01 mitigation; source-friendly polling

## Kaynaklar

- [RFC 7232 — HTTP Conditional Requests](https://www.rfc-editor.org/rfc/rfc7232)
- [GitHub Issue #565](https://github.com/selmanays/nodrat/issues/565) / [PR #571](https://github.com/selmanays/nodrat/pull/571)
- Production smoke test: `2026-05-10` — haberturk ETag persist + curl manuel 304 doğrulaması
