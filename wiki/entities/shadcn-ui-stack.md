---
type: entity
title: "shadcn/ui (preset b1VlIttI / radix-luma)"
slug: "shadcn-ui-stack"
category: "tool"
status: "live"
created: "2026-05-09"
updated: "2026-05-09"
sources:
  - "docs/engineering/architecture.md§0"
  - "docs/design/design-system.md§D1"
  - "docs/design/design-system.md§A0"
tags: ["frontend", "ui", "design-system", "shadcn", "radix", "tailwind"]
aliases: ["shadcn", "shadcn-radix-luma", "preset-b1VlIttI"]
---

# shadcn/ui (preset b1VlIttI / radix-luma)

> **TL;DR:** Nodrat web (`apps/web`) için tek UI bileşen kütüphanesi. **Preset `b1VlIttI` (radix-luma OKLCH)** üzerine kurulu, Tailwind v4 + Radix primitives + class-variance-authority. Yeni proje shadcn CLI komutu: `pnpm dlx shadcn@latest init --preset b1VlIttI --template next --monorepo`. MVP-1.3 (#275)'te admin paneline, ardından kullanıcı arayüzüne yayıldı.

## Tanım

shadcn/ui — kopyala-yapıştır pattern'iyle çalışan UI bileşen kütüphanesi. Klasik bir npm paketi değil; CLI ile her bileşeni projeye **kaynak kodu olarak** ekler (`apps/web/src/components/ui/<component>.tsx`). Bu sayede:

- Vendor lock'a immune (paket sürümü beklenmez)
- Bileşeni **değiştirmek istersen** kendi kaynaklarındır — ama Nodrat'ta kural: dokunma (bkz. [[shadcn-customization-policy]])
- Radix UI primitive'leri üzerine inşa edilir (a11y, klavye, focus management Radix sağlar)
- Stil **Tailwind class-name composition** ile: `cva` + `cn` helper

**Preset** (`b1VlIttI`) — shadcn'in resmi preset registry'sinde tanımlı tema. Adı kullanıcı için anlamsız (rastgele ID), ama karşılığı **radix-luma OKLCH renk paleti**:
- Background, foreground, primary, secondary, muted, accent, destructive — hepsi `oklch()` cinsinden
- Light + dark mode CSS variable çiftiyle
- `--radius` token'ı (border-radius scale)

## Nodrat'ta kullanım

| Alan | Durum | Not |
|---|---|---|
| Admin panel (`/admin/*`) | ✅ MVP-1.3 (#275) | Sidebar primitive + radix-luma preset; tüm ekranlar |
| Kullanıcı arayüzü (`/app/*`) | ✅ MVP-1.x → 1.7 polish | Generate, billing, me, generations, saved sayfaları |
| Public pages (`/legal/*`, `/`, `/ara`) | ✅ kısmen | Bileşenler aynı kütüphaneden |
| Auth pages | ✅ | Login, register, forgot-password |

**Kullanılan bileşenler** (kaynak: `apps/web/src/components/ui/`):
- Layout: `Sidebar`, `SidebarProvider`, `SidebarRail`, `SidebarInset`, `Breadcrumb`
- Form: `Button`, `Input`, `Label`, `Textarea`, `Select`, `Checkbox`, `Switch`, `RadioGroup`, `Form`
- Display: `Card`, `Badge`, `Avatar`, `Separator`, `Skeleton`
- Feedback: `Alert`, `Sonner` (toast), `Tooltip`, `Progress`
- Overlay: `Dialog`, `Sheet`, `Popover`, `DropdownMenu`, `Command` (cmdk)
- Data: `Table`, `Tabs`, `Accordion`, `Collapsible`

## Önemli özellikler / parametreler

| Parametre | Değer | Kaynak |
|---|---|---|
| Preset ID | `b1VlIttI` (radix-luma OKLCH) | shadcn registry |
| Init komutu | `pnpm dlx shadcn@latest init --preset b1VlIttI --template next --monorepo` | shadcn docs |
| Template | `next` (App Router) | architecture.md §0 |
| Monorepo flag | aktif | apps/web turbo monorepo |
| Tailwind sürümü | v4 (CSS-only config) | apps/web/src/app/globals.css |
| Token mapping | `@theme inline` ile CSS var → Tailwind token | globals.css §"@theme inline" |
| Dark mode | `.dark` class manuel toggle (`@custom-variant dark`) | globals.css |
| Radix variant shorthand | `data-active`, `data-open`, `data-checked` vb. mapping | globals.css `@custom-variant` blokları |
| MCP server | `mcp__Shadcn_UI__*` (resmi shadcn MCP) | Bileşen ekleme/inceleme/tema yönetimi |

## MCP connector

Claude Code oturumunda **shadcn MCP** mevcut — bu kullanılması beklenen normatif yoldur:

```text
mcp__Shadcn_UI__list_components       # mevcut tüm bileşen kataloğu
mcp__Shadcn_UI__get_component          # bileşen kaynağı (kopyalanacak kod)
mcp__Shadcn_UI__get_component_demo     # demo örnekleri
mcp__Shadcn_UI__get_component_metadata # depencency, prop, slot bilgisi
mcp__Shadcn_UI__get_block              # composed block (örn. dashboard, login)
mcp__Shadcn_UI__list_blocks            # blok kataloğu
mcp__Shadcn_UI__list_themes            # preset kataloğu
mcp__Shadcn_UI__get_theme              # preset detayları (b1VlIttI dahil)
mcp__Shadcn_UI__apply_theme            # preset uygula
mcp__Shadcn_UI__get_directory_structure # şu anki proje yapısı
```

**Ne zaman:** yeni bir bileşen eklemeden önce, mevcut bileşenin demo'larını inceleme, blok-bazlı sayfa kurma. **Manuel `npx shadcn add ...` yerine MCP tercih edilir** — agent tool kullanımı daha deterministik.

## Kararlar (locked)

- [[shadcn-customization-policy]] — varsayılan bileşen dosyalarına dokunulmaz; özelleştirme bileşenin **çağrıldığı yerde** prop/className ile yapılır.

## İlişkiler

- **İlgili kararlar:** [[shadcn-customization-policy]]
- **İlgili kavramlar:** —
- **İlgili topics:** —
- **Bağlı varlıklar:** —

## Açık sorular / TODO

- Yok.

## Kaynaklar

- [docs/engineering/architecture.md §0](../../docs/engineering/architecture.md) — frontend stack
- [docs/design/design-system.md §D1](../../docs/design/design-system.md) — komponent kütüphane seçimi (shadcn/ui Radix + Tailwind)
- [docs/design/design-system.md §A0](../../docs/design/design-system.md) — design system token kaynağı
- [shadcn/ui registry](https://ui.shadcn.com/docs/registry) — preset/component katalog
- [GitHub PR #275](https://github.com/selmanays/nodrat/pull/275) — admin panel shadcn migration (MVP-1.3)
- [GitHub PR #508](https://github.com/selmanays/nodrat/pull/508) — Tailwind v4 container fix (preset bağımlı detay)
