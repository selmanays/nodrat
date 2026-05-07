---
title: Wiki Setup — Obsidian + MCP Kurulum
type: hub
updated: 2026-05-07
---

# Wiki Kurulum Kılavuzu

Bu rehber **bir defalık** kurulum içindir. Tamamlandıktan sonra Claude Code wiki'yi hem doğrudan dosya tool'larıyla hem de Obsidian MCP üzerinden yönetebilir.

## Genel akış

```
1. Obsidian indir + nodrat/ vault olarak aç          (5 dk)
2. "Local REST API" plugin install + API key al      (5 dk)
3. .env'ye OBSIDIAN_API_KEY yaz                       (1 dk)
4. uv yüklü değilse yükle                             (2 dk)
5. Claude Code restart → .mcp.json otomatik yüklenir (1 dk)
6. Doğrulama testi                                   (2 dk)
```

Toplam: ~15 dk.

---

## 1. Obsidian kurulumu

### 1.1 Indir

[obsidian.md](https://obsidian.md/) → macOS / Windows / Linux. Free, kapalı kaynak masaüstü uygulaması.

### 1.2 Vault aç

Obsidian'ı ilk açtığında "Open folder as vault" seçeneğine tıkla → `/Users/selmanay/Desktop/nodrat/` klasörünü seç.

> **Vault olarak `nodrat/` (kök), `wiki/` değil.** Çünkü wiki sayfaları `docs/...md` dosyalarına relative link veriyor — Obsidian vault'unun bu linkleri çözmesi için kök seviyesinden başlaması gerekir.
>
> Repo kökünde Obsidian'ın ilgilenmediği büyük klasörler (`apps/`, `infra/`, `node_modules/`) `.obsidian/app.json`'daki `userIgnoreFilters` ile gizlenmiştir.

### 1.3 Sandbox uyarısı (ilk açılış)

Obsidian "trust this vault?" diyebilir → "Trust author and enable plugins" seç. (Bu vault'taki plugin ve özel CSS'lerin çalışmasına izin verir.)

---

## 2. Local REST API plugin

### 2.1 Install

1. Obsidian → Settings (`⌘ ,`) → **Community plugins**
2. "Turn on community plugins" → Browse
3. Ara: **"Local REST API"** (yazar: coddingtonbear)
4. Install → Enable

GitHub: [coddingtonbear/obsidian-local-rest-api](https://github.com/coddingtonbear/obsidian-local-rest-api)

### 2.2 API key al

Settings → **Community plugins → Local REST API** ekranı:

- "API Key" alanı altında otomatik üretilmiş bir UUID görürsün. **Kopyala.**
- Default port: `27124` (HTTPS). Değiştirme.
- "Enable Non-encrypted (HTTP) Server" — **kapalı kalsın** (HTTPS yeterli).

### 2.3 HTTPS sertifika güveni (macOS)

Plugin self-signed sertifika kullanır. macOS'ta:

1. Aynı plugin ekranında **"Crypto" sekmesi** veya alt bölüm
2. "Download Certificate" → indir
3. Keychain Access aç → indirilen `.crt` dosyasını çift tıkla → System keychain'e ekle
4. Sertifikaya çift tıkla → "Trust" → "Always Trust"

> **Alternatif (daha basit):** Plugin'in HTTP (non-encrypted) server'ını localhost'a açabilirsin (`Enable Non-encrypted (HTTP) Server` ON, port `27123`). Bu durumda `.env`'de `OBSIDIAN_PORT=27123` yap. Lokal makinede çalıştığı için risk düşük.

---

## 3. `.mcp.json` oluştur (Claude Code MCP config)

> **Önemli:** Claude Code şu an `.env` dosyasını veya `settings.local.json` `env` field'ını MCP server'a otomatik aktarmıyor (bilinen bug — [anthropic/claude-code#1254](https://github.com/anthropics/claude-code/issues/1254)). Tek garantili yol: `.mcp.json`'a key'i **doğrudan plain text** yazmak. Repo'ya gitmemesi için `.mcp.json` `.gitignore`'da, repo'da template versiyonu `.mcp.json.example` paylaşılır.

```bash
# Repo kökünde
cp .mcp.json.example .mcp.json

# .mcp.json'u editörle aç, "PASTE_YOUR_KEY_HERE" yerine
# §2.2'de kopyaladığın UUID'i yapıştır
```

`.mcp.json` son hali:
```json
{
  "mcpServers": {
    "obsidian": {
      "command": "uvx",
      "args": ["mcp-obsidian"],
      "env": {
        "OBSIDIAN_API_KEY": "ccfbb40882b53493162367ff5416f039df8266a6607eaedf5fb065c512f25389",
        "OBSIDIAN_HOST": "127.0.0.1",
        "OBSIDIAN_PORT": "27124"
      }
    }
  }
}
```

> **Güvenlik:** `.mcp.json` `.gitignore`'da, commit'lenmez. Sadece kullanıcının lokal makinesinde plain text. Bu Local REST API plugin key'i — sadece localhost'tan erişilebilir, internet'e expose değil.

> **Alternatif (`.env` da kalsın):** `.env`'de de aynı key'i `OBSIDIAN_API_KEY=...` olarak tutabilirsin (production deployment veya başka tool'lar için). MCP server `.mcp.json`'daki plain key'i alır, `.env`'i okumaz — ama her iki yerde tutmak zarar vermez.

---

## 4. uv (Python package manager) yükleme

MCP server `uvx mcp-obsidian` ile çalışır. `uv` yüklü değilse:

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Doğrulama:
```bash
uv --version
uvx --help
```

İlk kullanımda `uvx mcp-obsidian` paketi otomatik indirir (~10 sn).

---

## 5. Claude Code MCP yüklemesi

Repo kökünde `.mcp.json` zaten hazır. Claude Code yeni bir konuşma açtığında otomatik yükler.

### 5.1 Restart

```bash
# Mevcut Claude Code oturumunu kapat (terminal: Ctrl+C)
# Tekrar başlat:
claude
```

> **Uyarı:** İlk açılışta Claude Code "do you trust the MCP server in `.mcp.json`?" diye sorar → onayla.

### 5.2 Env değişkenleri

`.mcp.json`'daki plain key MCP server'a doğrudan aktarılır. **Ek shell export gerekmez** (§3 not'unda detay). Bu kasten — Claude Code env var expansion bug'ını atlayan en güvenilir çözüm.

---

## 6. Doğrulama

Yeni bir Claude Code konuşması aç ve şunu yaz:

```
Obsidian MCP üzerinden wiki/index.md dosyasını okur musun?
```

Beklenen: Claude `mcp__obsidian__*` tool'larından birini çağırır (örn. `get_file_contents`) ve dosya içeriğini döner.

Hata alırsan kontrol listesi:

| Hata | Olası neden | Çözüm |
|---|---|---|
| `connection refused` | Obsidian açık değil veya plugin enable değil | Obsidian aç, plugin'i tekrar enable et |
| `401 Unauthorized` | `.mcp.json`'daki key yanlış / placeholder kalmış | `.mcp.json` aç, `PASTE_YOUR_KEY_HERE` veya yanlış key yerine §2.2 UUID'i yapıştır, Claude Code restart |
| `SSL: CERTIFICATE_VERIFY_FAILED` | HTTPS sertifika güvenli değil | §2.3 yap veya HTTP'ye geç (port 27123) |
| `command not found: uvx` | uv yüklü değil | §4 |
| MCP server listede yok | .mcp.json yüklenmedi | Claude Code restart, "MCP servers"a bak |

---

## 7. Önerilen ek pluginler (opsiyonel)

Bunlar wiki deneyimini güçlendirir. Settings → Community plugins → Browse:

| Plugin | Faydası |
|---|---|
| **Dataview** | Frontmatter sorgulama, dinamik tablolar (örn. "tüm `type: decision` sayfaları listele") |
| **Templater** | `wiki/_templates/` şablonlarını hızlı insert |
| **Excalidraw** | Mimari diyagramları vault içinde çiz |
| **Tag Wrangler** | Tag ağacını yönet, rename |

> **MCP ile ilgili yok:** MCP server doğrudan REST API'yle konuşur, bu pluginlere bağımlı değildir. Sadece insan (Obsidian UI) deneyimini iyileştirirler.

---

## 8. Veri kaybı uyarısı (önemli)

Obsidian Local REST API plugin'in bilinen bir bug'ı: POST endpoint metadata cache miss durumunda **append'i overwrite yapabilir** (bkz. [GitHub issue tracker](https://github.com/coddingtonbear/obsidian-local-rest-api/issues)).

**Önlemler:**

1. **Wiki'yi git altında tut.** Ne olursa olsun `git restore` ile geri al.
2. **Toplu write öncesi `git status` clean olmalı.** Hata olursa zarar belirgin.
3. **Claude Code'un MCP write işlemleri sırasında patch_note tercih edilir** (Markus Pfundstein versiyonunda mevcut). Default config'de `mcp-obsidian` Markus versiyonu — `patch_content` tool'u kullanılır.
4. **Büyük ingestler doğrudan dosya tool'larıyla** (`Edit`, `Write`) yapılır — MCP yerine. Kök CLAUDE.md §4.1 default kuralı.

---

## 9. Alternatif MCP server'ları

`mcp-obsidian` (Markus Pfundstein) yerine deneyebileceklerin:

| Server | Paket | Komut | Özellik |
|---|---|---|---|
| **mcpvault** (`@bitbonsai/mcpvault`) | npm | `npx -y @bitbonsai/mcpvault` | 14 tool, BM25 search + reranking, batch read |
| **obsidian-mcp-server** (cyanheads) | npm | `npx -y obsidian-mcp-server` | Surgical edit, frontmatter management |

`.mcp.json` içindeki `command`/`args` değiştirilerek geçiş yapılır. Tüm bu server'lar **aynı Local REST API plugin'ini** kullandığı için Obsidian tarafında değişiklik gerekmez.

---

**Sorun çıkarsa:** [`wiki/log.md`](log.md)'ye not düş ve [coddingtonbear/obsidian-local-rest-api/issues](https://github.com/coddingtonbear/obsidian-local-rest-api/issues) sayfasına bak.
