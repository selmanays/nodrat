---
type: decision
title: No Internal Backward-Compat Aliases (Old Paths Get Deleted)
slug: no-internal-backcompat-aliases
status: locked
decided_on: 2026-05-20
decided_by: founder
created: 2026-05-20
updated: 2026-05-20
sources:
  - /Users/selmanay/.claude/projects/-Users-selmanay-Desktop-nodrat/memory/feedback_backward_compat_argument.md
  - wiki/decisions/modular-monolith-boundary.md
tags:
  - architecture
  - modular-monolith
  - refactor
  - locked-decision
aliases:
  - no-alias-debt
  - delete-old-paths
---

# No Internal Backward-Compat Aliases (Old Paths Get Deleted)

> **Karar:** Modül taşıma sırasında eski path'lere "backward-compat" re-export köprüsü bırakılmaz. Eski `app.core.X` veya `app.api.X` import edilen tüm yerler taşıma PR'ında güncellenir; eski dosya **aynı PR'da silinir**. Backward-compat argümanı yalnız **external sözleşmeler** için geçerlidir (URL, API contract, KVKK metni, kullanıcı veri formatı).
>
> **Durum:** locked
> **Tarih:** 2026-05-20

## Bağlam

Refactor'larda sık başvurulan kalıp: "Eski path'i alias olarak bırak, deprecate et, 1 release sonra sil." Bu yaklaşım **bu repo için yanlış** çünkü:
- Tek geliştirici + LLM workflow — paralel ekip yok; backward-compat alıcısı yok.
- Internal package paths external API değil — kullanıcı görmez.
- Alias-debt birikir: "Hangisi gerçek?" karmaşası; yeni modül `from app.core.X` mi yoksa `from modules.<mod>.X` mi import edecek belirsizleşir.

**Tarihsel kanıt:**
- 2026-05-12 (memory `feedback_backward_compat_argument`): kullanıcı uyardı — DeepSeek v3 routing key'i V3 model kullanılmadığı halde "backward-compat amaçlı koru" dedim; ~21K row UPDATE 1 sn'lik iş. Internal değişimi external sözleşmeye karıştırdım.

## Alternatifler ve neden reddedildi

| Alternatif | Artı | Eksi | Karar |
|---|---|---|---|
| Her taşımada 1 release deprecation alias | "Güvenli" hissi | Alias-debt birikir; agent'lar yanlış path import eder; refactor yarı kalır | **Reddedildi** |
| Geçici alias (1 PR ömründe) | Atomic değil; gerçek geçişe zorlar | İki PR — taşı + temizle. Yine de "geçici" diye unutulur | **Reddedildi** |
| **Aynı PR'da tüm çağrı yerleri güncellenir + eski path silinir** | Atomic; alias-debt sıfır; CI yeşil = gerçek geçiş | Refactor PR'ı biraz büyür (çağrı yerlerini içerir) | **Seçildi** |

## Uygulama

Refactor PR template'inde (`PULL_REQUEST_TEMPLATE/refactor.md`):
- [ ] Yeni `modules/<mod>` veya `shared/<sub>` eklendi
- [ ] Legacy `app.core.*` veya `app.api.*` taşındı (eski dosya silindi)
- [ ] Tüm çağrı yerleri güncel (`grep "from app.core.<oldname>"` boş)
- [ ] CI yeşil

## Backward-compat'ın geçerli olduğu yerler (istisna)

| Tür | Örnek | Backward-compat zorunlu? |
|---|---|---|
| URL prefix | `/admin/sources/...` (kullanıcı bookmark'lar) | **EVET** — değiştirme |
| API contract | `POST /research/conversations` response schema | **EVET** — değiştirme |
| Celery task name | `tasks.sources.crawl_active_sources` (Beat string-bound) | **EVET** — değiştirme |
| Database schema | tablo/sütun adları | **EVET** — Alembic migration ayrı PR |
| LLM prompt content | RC3-B v2 marker-detect regex | **EVET** — characterization |
| KVKK / Legal metin | Privacy policy madde 5 | **EVET** — hukuki süreç |
| **Internal Python import path** | `from app.core.X import Y` | **HAYIR** — taşıma PR'ında temizle |
| **Internal config key (DB enum string)** | "deepseek_v3" routing key | **HAYIR** — bulk UPDATE |
| **Internal class/function isimleri** | `class HybridSearcher` | **HAYIR** — yeniden adlandır |

## Sonuçlar

- Modül taşıma PR'ları **atomic** (taşı + temizle); deprecation period yok.
- CI'da `grep "from app.core.<oldmodule>"` boş çıkar; aksi halde merge edilmez.
- Refactor "yarı kalmış" duruma düşmez; alias-debt sıfır.

## Geri alma maliyeti

Bu kural gevşetilip aliaslar kalırsa: codebase'de 2 doğru-yol gerçeği oluşur; yeni geliştirme hangi path'i kullanacak belirsizleşir; agent'lar yanlış import yapar; refactor PR'ları birikmiş alias temizliğiyle uğraşır. **Orta maliyet** (mental load + agent karmaşası).

## İlişkiler

- **Bağlı kararlar:** [[modular-monolith-boundary]], [[import-direction-rules]], [[god-file-facade-first]]
- **Tarihsel kanıt:** memory `feedback_backward_compat_argument.md` (2026-05-12)

## Kaynaklar

- [docs/engineering/refactor-playbook.md](../../docs/engineering/refactor-playbook.md)
- [wiki/plans/modular-monolith-transition-master-plan.md §11](../plans/modular-monolith-transition-master-plan.md)
