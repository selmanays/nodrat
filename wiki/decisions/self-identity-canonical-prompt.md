---
type: decision
title: "Sistem self-knowledge: kanonik prompt bloğu + meta C1 (tool DEĞİL)"
slug: "self-identity-canonical-prompt"
category: "rag"
status: "locked"
decided_on: "2026-05-18"
decided_by: "tech"
created: "2026-05-18"
updated: "2026-05-18"
sources:
  - "apps/api/app/prompts/chat_answer.py§SYSTEM_PROMPT_NODRAT_AGENT-Adının-anlamı"
  - "apps/api/app/prompts/chat_answer.py§Karar-md1-C1-backstop"
  - "GitHub Issue #958 / PR #959 / conv b107069a"
tags: ["locked-decision", "chat", "prompt", "hallucination", "identity", "888-family"]
aliases: ["nodrat-no-drat", "self-knowledge-architecture", "meta-c1-backstop"]
---

# Sistem self-knowledge: kanonik prompt bloğu + meta C1 (tool DEĞİL)

> **Karar:** Sistemin kendisi hakkındaki bilgi (isim kökeni, ne olduğu, yetenekler) **kısa kanonik blok olarak system prompt'ta** tutulur + meta/kimlik path'inde **C1 anti-halüsinasyon backstop**. Ayrı "self-docs tool"a bağlanmaz — prefix-caching ile statik prompt maliyeti ≈0; tool küçük/statik kimlik için over-engineering.
> **Durum:** locked · **Tarih:** 2026-05-18 · #888/#955 ailesi (chat-kalite)

## Bağlam — sorun

conv b107069a: "neden adın Nodrat? ne demek bu" → **"Nodrat = 'Taylor' (Taylor Swift) tersten yazılışı"** — tamamen uydurma (harfler bile uyuşmuyor). Ağır C1 halüsinasyonu.

**Kök neden:** Bir LLM, kendisini saran ürünün (Nodrat) adını/kökenini **eğitim verisinden bilmez** (ürün eğitim cut-off sonrası / niş). `SYSTEM_PROMPT_NODRAT_AGENT` "Sen Nodrat'sın — araştırma motoru" diyordu ama **isim kökeni/anlamı tanımsızdı**. §Karar md1 (kimlik/meta → tool çağırma, doğrudan yanıt) spesifik faktüel alt-soru (etimoloji) için ne veri ne "bilmiyorsan uydurma" kuralı içeriyordu → tool-path'lerdeki C1 (kaynak yoksa uydurma yasak) bu **tool'suz path'te yoktu** → bilgi boşluğu serbest halüsinasyonla doldu.

## Karar

1. **Kanonik kimlik bloğu (system prompt):** `SYSTEM_PROMPT_NODRAT_AGENT` kimlik tanımına kısa "Adının anlamı" bloğu — **"Nodrat" = İngilizce "no drat"** ('drat' = hafif sıkıntı/can sıkkınlığı ünlemi; "no drat" = sıkıntı/gecikme yok, güncel habere "drat" demeden ulaşma teması; kullanıcı onaylı kanonik köken). "Bu dışında etimoloji/kısaltma İCAT ETME" kaydı.
2. **Meta-path C1 backstop (§Karar md1):** isim kökeni / nasıl çalıştığın / kim yaptığı / hangi model gibi sistem-içi sorulara YALNIZ kanonik bilgiyle yanıt; tool çağrılmadığı için doğrulanacak kaynak yok → kanonik dışı İCAT ETME; emin değilsen "bu konuda kesin bilgim yok" de.

`chat_answer` prompt'u **cache'siz** (answer LLM her çağrıda) → `PROMPT_VERSION` bump yok; davranış prompt'la değişir.

## Neden tool DEĞİL (mimari gerekçe)

| Boyut | Kanonik prompt bloğu | Ayrı "self-docs" tool |
|---|---|---|
| Girdi maliyeti | DeepSeek **prefix-caching** → statik system prompt cache-hit'te ~10× ucuz; birkaç cümlenin marjinal maliyeti ≈0 | Tool schema HER istekte token (tasarruf yok, yer değiştirir) |
| Latency | 0 ek | Tool çağrılırsa **+1 LLM round-trip** |
| Hata yüzeyi | Yok | Tool seçilmez/yanlış çağrılır → yine halü |
| Karmaşıklık | 1 prompt bloğu | Schema + dispatch + sonuç-serileştirme |

> Tool'un haklı çıktığı eşik: self-knowledge **büyük + dinamik + sık değişen** olursa (detaylı SSS, sürüm notları, fiyat tablosu — kilobaytlarca). O noktada ayrı **self-docs knowledge-source** (mevcut `search_wikipedia` gibi retrieval) eklenir. Küçük/statik kimlik için DEĞİL.

> **Perplexity referansı:** Model seçimi yalnız cevap-üreten modeli değiştirir; Perplexity bir **orkestrasyon katmanı** — her isteğe kendi kurumsal kimlik context'ini **model-agnostik enjekte eder** (model eğitim verisinden değil). Kısa kimlik = enjekte system prompt; detaylı ürün/abonelik = kendi yardım-dokümantasyonuna retrieval. Yani Perplexity de **hibrit**: küçük kimlik prompt-enjekte, büyük/dinamik docs-retrieval — bu sayfanın kararıyla aynı omurga.

## Alternatifler

| Alternatif | Karar |
|---|---|
| Self-docs tool (küçük kimlik için) | reddedildi — schema-token + round-trip + hata yüzeyi; prefix-caching zaten maliyeti sıfırlıyor |
| İsim kökeni hiç koyma, sadece C1 "bilmiyorum" | reddedildi — kullanıcı gerçek köken ("no drat") sağladı; kanonik doğru bilgi > "bilmiyorum" |
| LLM'in bilmesini bekle (prompt'a koyma) | reddedildi — kök neden tam buydu (eğitim verisinde yok → halü) |
| **Kanonik prompt bloğu + meta-C1 (hibrit; tool-eşiği saklı)** | **seçildi** |

## Sonuçlar

- 58 chat/app_chat/nodrat_agent unit regresyon yeşil. **Prod mechanism smoke:** `prompts_store.get("chat_nodrat_agent",…)` resolved == kod default (8804=8804) → **DB-override YOK, A+B prod'da etkili** (#854/#270 prompt-override tuzağına düşülmedi — kritik kontrol).
- 2-mesaj NL davranışı (kimlik sorusu → "no drat" doğru, uydurma yok) prompt-düzeyi → kullanıcı UI re-test (#845/#888/#955 deseni).
- Statik prompt büyümesi prefix-caching ile maliyet-nötr; gelecekte detaylı self-docs gerekirse tool-eşiği bu sayfada tanımlı.

## Geri alma

> `SYSTEM_PROMPT_NODRAT_AGENT`'tan "Adının anlamı" bloğu + md1 C1 backstop'u çıkar → halü geri döner. Şema/migration/PROMPT_VERSION etkisi yok (cache'siz prompt); tek commit.

## İlişkiler

- [[chat-knowledge-evolution]] — #958 satırı + anti-pattern ders #32
- [[agentic-generate-orchestration]] — §Karar md1 (kimlik/meta path) bu C1 backstop'un yeri; #888/#955/#958 zinciri
- [[planner-cache-key-v2]] — prefix-caching mantığının kuzeni (sürüm-bağlı cache; burada statik-prompt caching ekonomisi)
- [[news-first-strict-contamination-guard]] — C1 (kaynaksız iddia yasağı) ailesi; bu, C1'i tool'suz meta-path'e taşır

## Kaynaklar

- [Issue #958](https://github.com/selmanays/nodrat/issues/958) · [PR #959](https://github.com/selmanays/nodrat/pull/959) · conv b107069a
- [`apps/api/app/prompts/chat_answer.py`](apps/api/app/prompts/chat_answer.py) — SYSTEM_PROMPT_NODRAT_AGENT "Adının anlamı" + §Karar md1 C1 backstop
- Mimari tartışma: tool-vs-prompt+caching + Perplexity hibrit analizi (oturum, 2026-05-18)
