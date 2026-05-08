---
type: decision
title: "shadcn bileşen özelleştirme politikası — varsayılan dosya korunur, çağrı yerinde özelleştir"
slug: "shadcn-customization-policy"
status: "locked"
decided_on: "2026-05-09"
decided_by: "founder"
created: "2026-05-09"
updated: "2026-05-09"
sources:
  - "Kullanıcı talimatı (2026-05-09)"
  - "docs/design/design-system.md§D1"
tags: ["locked-decision", "frontend", "ui", "convention", "engineering", "shadcn"]
aliases: ["shadcn-defaults", "ui-customization-policy", "components-ui-immutable"]
---

# shadcn bileşen özelleştirme politikası

> **Karar:** Tüm UI çalışmalarında **shadcn varsayılan bileşenleri** kullanılır. **Bileşenin varsayılan dosyası (`apps/web/src/components/ui/<component>.tsx`) bozulmaz.** Bileşen-bazlı değişiklik talepleri geldiğinde özelleştirme **bileşenin çağrıldığı yerde** (block, page veya feature komponenti) **prop / className / variant** ile yapılır. Bileşen kütüphanesini ekleme ve inceleme için `mcp__Shadcn_UI__*` connector tercih edilir.
> **Durum:** locked.
> **Tarih:** 2026-05-09 (kullanıcı talimatı).

## Bağlam

Nodrat web (`apps/web`) tüm bileşenleri [[shadcn-ui-stack|shadcn/ui preset b1VlIttI]] üzerinden kullanır. shadcn'in en güçlü yönü, bileşeni **kaynak kodu** olarak projeye eklemesidir — yani teorik olarak istediğimiz gibi değiştirebiliriz. Ama bu özgürlük disiplinsizce kullanılırsa:

1. **Upstream güncellemelerini kaybederiz.** shadcn periyodik olarak bileşenlerini günceller (Radix sürüm bumpı, a11y düzeltmesi, prop API). Yerelde kaynağı oynatmışsak `npx shadcn add --overwrite` her seferinde merge conflict'idir.
2. **Tutarsız davranış.** Aynı `Button`'ın iki farklı yerde farklı davranması debug cehennemine sokar.
3. **Ekibe açık değil.** Yeni katılan biri `Button.tsx`'in shadcn varsayılanı sandığı şeyi okur, ama biz zaten "öyle değil aslında" diye düzeltmek zorunda kalırız.
4. **Test/eval yüzeyi şişer.** Her custom bileşen yeni test gerektirir.

Buna karşılık özelleştirme **çağrı yerinde** yapılırsa:
- shadcn dosyaları upstream ile %100 hizalı kalır (`npx shadcn add` her zaman güvenli)
- Özelleştirme **lokal kapsamda** kalır → ekipteki diğer geliştiriciler okurken `<Button className="...">` görür ve özelleştirmenin sınırını anında anlar
- Tek bir bileşen özelleştirmesi tüm uygulamaya değil, sadece kullanıldığı yere yansır

## Karar detayı

```text
✅ KABUL: components/ui/* dosyaları shadcn varsayılanı, dokunulmaz
   - npx shadcn add <component> ile eklenir
   - Üretirken/güncellerken --overwrite ile sync
   - Sadece preset / token / theme değişikliği globals.css'te

✅ KABUL: Özelleştirme çağrı noktasında
   - className= ile Tailwind utility (en sık)
   - variant / size / asChild prop'ları (Button, Card vb.)
   - cn() helper ile koşullu class composition
   - Compound component pattern (Card + CardHeader + CardContent ...)

✅ KABUL: Yeni composed component yaratma
   - apps/web/src/components/blocks/<feature>.tsx (örn. PostCard, GenerationList)
   - apps/web/src/components/<feature>/<sub>.tsx (örn. consent/consent-gate.tsx)
   - Bu yeni dosyalar shadcn primitives'i çağırır, içine sarmalar

🛑 RED: components/ui/<component>.tsx dosyalarını edit etmek
   - Yeni prop ekleme, default davranış değiştirme, JSX strukturu modifiye
   - Color/spacing tweak'leri için bile içeri girme

🛑 RED: Yeni bileşen oluştururken shadcn'i bypass etmek
   - Bir Modal lazımsa Dialog kullan, sıfırdan div yazma
   - Bir Dropdown lazımsa DropdownMenu kullan
```

### Kapsam

- **Production frontend kodu** (`apps/web/src/`) için bağlayıcı.
- **İstisnalar:** preset / theme / global token değişiklikleri **`globals.css`** üzerinden yapılır (CSS variable bazında); bu `components/ui/*` editi sayılmaz.
- **Yeni shadcn bileşeni eklerken**: önce `mcp__Shadcn_UI__list_components` + `get_component_demo` ile kontrol et, varsa eklemeden önce blok da incele (`list_blocks`).

### MCP connector kullanımı

```text
✅ KABUL: shadcn MCP tool'larını agent kullanım sırası
   - get_component / get_component_demo  → ekleme öncesi inceleme
   - list_blocks / get_block             → composed sayfa kurarken
   - get_theme b1VlIttI                  → token referansı
   - get_directory_structure             → mevcut komponent envanteri
   - list_components                     → katalog tarama

🛑 RED: shadcn MCP yokmuş gibi davranıp manuel npx ile devam etmek
   - MCP varsa onu kullan; deterministik tool > shell wrap
```

## Alternatifler ve neden reddedildi

| Alternatif | Artı | Eksi | Karar |
|---|---|---|---|
| Bileşeni doğrudan modify et (`components/ui/button.tsx` içine yeni prop) | Hızlı, "tek satır fix" | Upstream sync kırılır, tutarsızlık, bilgi gizlemesi | Reddedildi |
| Wrapper component yaratma (örn. `<NodratButton>` her yerde) | Tek noktadan kontrol | Boilerplate, kullanım yerinde dolaylı, prop drilling | Reddedildi (gerçekten cross-cutting değişimde duruma göre kabul) |
| Tailwind preset + global theme override | Visual tutarlılık | Sadece cosmetic; davranış değişikliklerine yetmez | Bu kuralın bir parçası (✅ kabul) |
| **Çağrı yerinde özelleştirme + global theme** | Lokal, açık, upstream-safe | Bazen tekrar (DRY ihlali küçük) — ama çok büyürse `blocks/` katmanına çekilebilir | **Seçildi** |

## Sonuçlar

- **Etkilenen kod yapısı:**
  - `apps/web/src/components/ui/` — **immutable** (shadcn defaults)
  - `apps/web/src/components/<feature>/` — uygulama-spesifik composed komponentler
  - `apps/web/src/components/blocks/` — page-level composed bloklar
  - `apps/web/src/app/<route>/page.tsx` — kullanım noktası
- **Etkilenen agent davranışı:** Claude Code kullanıcı talimatı olmadıkça `components/ui/*.tsx` editlemez. Her UI değişiklik talebinde önce kullanım noktasına bakar.
- **Etkilenen MCP discipline:** shadcn ekleme/inceleme `mcp__Shadcn_UI__*` connector'ı üzerinden tercih edilir. Manuel `npx shadcn add ...` ikinci tercih.

## Geri alma maliyeti

Düşük-orta. Bu bir code-review + agent-behavior kuralıdır, kod değil. Mevcut `components/ui/*` dosyaları zaten shadcn defaults — bu kuraldan sapmış lokal düzenleme yok (audit sonucu). Yeni bir özelleştirme talebi geldiğinde "buraya nasıl yansıyacak" sorusunun cevabı bu sayfadır.

## Uygulama

1. **Agent (Claude Code) davranışı:** Bu sayfa wiki'ye eklendi → bir UI iş akışında shadcn bileşen değişikliği talebi geldiğinde:
   - `apps/web/src/components/ui/*.tsx` dosyalarını **edit etmez**
   - Çağrı yerini bulur (page veya block) ve `className` / `variant` / `prop` ile özelleştirir
   - Yeni bileşen gerekirse önce `mcp__Shadcn_UI__list_components` ile var olanı taramak
2. **PR review:** UI PR'larında `components/ui/<component>.tsx` diff'i varsa kırmızı bayrak — gerekçesi açıklanmalı (örn. shadcn upstream sync veya yeni bileşen ekleme).
3. **Onboarding:** Yeni geliştirici/agent için bu sayfa zorunlu okuma.

## İlişkiler

- **Bağlı varlıklar:** [[shadcn-ui-stack]]
- **Bağlı kavramlar:** —
- **Bağlı kararlar:** [[endpoint-naming-policy]] (aynı engineering convention sınıfı — kalıcı kural, refactor maliyeti azaltır)
- **Bağlı topics:** —

## Kaynaklar

- Kullanıcı talimatı (2026-05-09 oturumu)
- [docs/design/design-system.md §D1](../../docs/design/design-system.md) — komponent kütüphanesi shadcn/ui (Radix + Tailwind)
- [GitHub PR #275](https://github.com/selmanays/nodrat/pull/275) — admin panel shadcn migration (MVP-1.3)
- [INDEX.md §4 (Çekirdek kararlar — locked)](../../INDEX.md)
