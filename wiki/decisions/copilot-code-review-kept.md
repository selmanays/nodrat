---
type: decision
title: "Copilot Code Review açık kalır (ücretsiz analiz)"
slug: "copilot-code-review-kept"
status: "locked"
decided_on: "2026-05-18"
decided_by: "founder"
created: "2026-05-18"
updated: "2026-05-18"
sources:
  - "Kullanıcı talebi 2026-05-18 (conv quirky-gates)"
tags: ["locked-decision", "ci", "tooling"]
aliases: ["copilot-review-keep"]
---

# Copilot Code Review açık kalır (ücretsiz analiz)

> **Karar:** GitHub-native Copilot Code Review (otomatik PR incelemesi) repo Settings'te **AÇIK** kalır; Actions sayfasında kırmızı görünse de kapatılmaz.
> **Durum:** locked
> **Tarih:** 2026-05-18

## Bağlam

`dynamic/agents/copilot-pull-request-reviewer` (repoda workflow dosyası YOK — GitHub-native ajan) her PR'da otomatik çalışıyor ve abonelik/entitlement eksikliğinden tamamlanamayıp Actions listesinde kırmızı görünüyor. "[[ci-blind-8-months-incident|CI hep kırmızı]]" analizinde 3. bağımsız kırmızı kaynak buydu. Kapatma yalnızca repo Settings web UI'dan mümkün (kod/CLI ile değil).

## Alternatifler ve neden reddedildi

| Alternatif | Artı | Eksi | Karar |
|---|---|---|---|
| Açık tut, çıktıyı izle | Ücretsiz ek kod-analizi | Actions'ta bilinçli kırmızı satır | **seçildi** |
| Settings'ten kapat | Actions tertemiz | Ücretsiz inceleme değeri kaybolur | reddedildi |

## Sonuçlar

- Actions sayfasında Copilot satırı **bilinçli kırmızı** — CI/lint/unit/eval gibi gerçek kapılarla karıştırılmamalı.
- Agent davranışı: Copilot review tamamlandığında bulguları okunur, geçerli olanlar özetlenir/fix'e katılır (memory: `feedback_copilot_review_keep`).
- İlişki: [[ci-ruff-single-formatter]] · [[ci-blind-8-months-incident]]

## Geri alma maliyeti

> Düşük — repo Settings → Copilot otomatik review toggle'ı kapatılarak geri alınır (yalnız repo sahibi, web UI). Kod/PR etkisi yok.
