---
type: topic
title: Agent Worktree Playbook (Parallel-Worktree Discipline)
slug: agent-worktree-playbook
category: playbook
status: live
created: 2026-05-20
updated: 2026-05-20
sources:
  - /Users/selmanay/.claude/projects/-Users-selmanay-Desktop-nodrat/memory/feedback_worktree_git_discipline.md
  - CLAUDE.md§1.3
  - wiki/plans/modular-monolith-transition-master-plan.md
tags:
  - agent
  - worktree
  - git
  - playbook
  - modular-monolith
aliases:
  - worktree-discipline
  - parallel-agent-playbook
---

# Agent Worktree Playbook (Parallel-Worktree Discipline)

> **TL;DR:** Birden fazla Claude Code agent paralel worktree'lerde çalışırken karışıklığı önlemek için disiplin. Modüler monolit dönüşümü boyunca tutarlı git akışı, wiki sync sırası, paralel modül taşıma çakışmalarının önlenmesi.

## Bağlam

Tek-developer + LLM workflow + paralel worktree (örn. `claude/elastic-montalcini-3b78e0` gibi) ortamında:
- Modüler monolit PR'ları arasında çakışma olabilir (örn. iki agent aynı anda `core/retrieval.py` import yerlerini güncellese).
- Wiki yazma yetkisi yalnız `main` veya dedicated `wiki/*` branch (CLAUDE.md §1.3) — feature worktree'de yazılırsa paralel kaybolur.
- Git komutları yanlış cwd'den çağrılırsa commit yanlış branch'e düşer (memory `feedback_worktree_git_discipline`).

Bu playbook **modüler monolit refactor PR'larında** spesifik disiplini koyar.

## Ana içerik

### 1. Cwd disiplini (memory `feedback_worktree_git_discipline`)

- ✅ **DOĞRU:** Worktree path'inden çalış: `/Users/selmanay/Desktop/nodrat/.claude/worktrees/<isim>/`
- 🛑 **YASAK:** `cd /Users/selmanay/Desktop/nodrat` (primary = main) → commit yanlış branch'e düşer
- ✅ **DOĞRU:** `gh pr create --head <branch>` her zaman explicit head ver
- ✅ **DOĞRU:** Dosya edit'leri worktree path'inden absolute path ile

### 2. Branch disiplini

- Her refactor PR'ı **tek branch** (worktree branch'i veya yeni `refactor/modular-monolith-pX-<mod>`).
- Master plan **main branch'inde** yaşar; feature worktree'lerinde **read-only** kullanılır.
- Feature worktree wiki update'i gerekirse: **TODO not** tut, feature PR merge sonrası ayrı wiki PR aç (CLAUDE.md §1.3 #3 ihlal etme).

### 3. Paralel modül taşıma çakışması

Birden fazla agent farklı modülleri eş zamanlı taşıyorsa:

| Senaryo | Risk | Önleme |
|---|---|---|
| İki agent aynı `core/X.py`'yi import eden iki ayrı modüle taşıyor | İki PR'da `from app.core.X import ...` ortak import sırası | Önce hangi modülün eski `core/X.py`'yi taşıyacağını master plan'da netleştir; diğer agent merge sonrası yeni path'e geç |
| İki agent `main.py` router include'unu farklı satırda değiştiriyor | Merge conflict | Tek PR'da main.py değişimi; veya alfabetik sıralama disiplini |
| İki agent `celery_app.py` `include` listesini değiştiriyor | Merge conflict | Aynı disiplin: alfabetik sıralama + bir agent diğerinin merge'ini bekler |
| İki agent `wiki/index.md` istatistik güncelliyor | Merge conflict (en sık) | Wiki sync'i en son atomic adım yap; her PR'ın son commit'i wiki index update |

### 4. Wiki sync sırası

Modüler monolit refactor PR'ında doğru sıra:

1. Kod taşıma (refactor edit'leri)
2. Test çalıştır, characterization snapshot doğrula
3. `wiki/log.md` entry ekle
4. `wiki/plans/modular-monolith-transition-master-plan.md` "Current Status" güncel
5. Yeni decision sayfası varsa oluştur + index güncel
6. `docs/engineering/*` güncel
7. Commit (atomic)
8. PR open

### 5. Master plan dosyası — single source of truth

- `wiki/plans/modular-monolith-transition-master-plan.md` her phase başında + bitiminde güncellenir.
- "Current Status Tracker" tablosu **anlık doğruyu** gösterir.
- Karar değişimi: ESKİ KARAR SİLİNMEZ → `~~strikethrough~~` + `superseded by` + decision changelog tarihli.
- Agent oturum başında **bu dosyayı okur** → bağlamı geri kazanır.

### 6. Session başlangıcı (her yeni Claude Code oturumu)

CLAUDE.md §1.3 #4 sırasına ek olarak modüler monolit context için:

1. CLAUDE.md (auto-load)
2. INDEX.md
3. wiki/index.md
4. wiki/log.md (son 5-10 entry)
5. **wiki/plans/modular-monolith-transition-master-plan.md** — modüler monolit context
6. İlgili `wiki/decisions/*` (refactor'a göre)
7. SessionStart hook çıktısı (otomatik enjekte)

### 7. PR template kullanımı

- **Refactor PR:** `.github/PULL_REQUEST_TEMPLATE/refactor.md` — URL'ye `?template=refactor.md` ekle
- **Feature PR:** Varsayılan `.github/pull_request_template.md` — mevcut feature work için (dokunulmadı)
- **Documentation-only PR:** Refactor template Scope: Documentation seç

### 8. Agent araç disiplini

- `Read` ile dosya görüntülemeden Edit/Write yapma (Edit zaten Read şart).
- Mevcut `wiki/_templates/*.md` şablonlarını kullan (decision/topic/concept/entity/source).
- Tahmin yapma; belirsizlik = "Açık sorular" bölümüne ekle.
- Quote yok; 15+ kelime kopyalama → kaynak linki.

### 9. Git stash güvenliği (memory `feedback_git_stash_safety`)

- 🛑 **YASAK:** Bare `git stash` veya `git stash pop` (kullanıcının çok-oturumlu WIP'leri var)
- ✅ **DOĞRU:** Baseline kıyaslama: `git show <ref>:<path>`
- ✅ **DOĞRU:** Spesifik file restore: `git checkout <ref> -- <file>`

### 10. Manuel deploy disiplini (memory `feedback_deploy_lessons`)

Refactor PR merge sonrası deploy:
- Paralel SSH **YASAK** (lock conflict)
- Killed/network-kesildi build → `docker compose build --no-cache`
- Orphan container → `docker rm -f <name>`
- Uzun heredoc yerine tek-komut SSH
- Düzenli `docker builder prune -af` (admin UI'da buton var)
- `gh run list --branch main` ile merge sonrası main CI'ı doğrula

### 11. Worktree sync hijyeni (Phase 2 PR 7 cycle dersi — primary stale)

#### 11.1 Problem örneği (2026-05-20)

Phase 2 PR 7 cycle'ı sırasında **primary worktree (`/Users/selmanay/Desktop/nodrat`)** uzun süre eski bir fix branch'inde takıldı:
- Branch: `fix/983rev-forced-final-toolchoice` @ `95fb616` (May 18 #1005 merge)
- Remote tracking `[gone]` (branch GitHub'da silinmiş)
- Transition PR'larından (#1099, #1100, ..., #1112) **hiçbir commit yok**
- Wiki/docs yeni dosyalar (`wiki/plans/`, `wiki/topics/refactor-pr-checklist.md`, `docs/engineering/modular-monolith-*`) **MISSING**
- Concurrent `keen-swanson-e09b18` worktree main branch'ini tutuyor → primary'i main'e switch etmek `fatal: 'main' is already used by worktree` ile bloklanır

Kullanıcı veya başka agent stale master plan üzerinden karar veriyor → context drift riski.

#### 11.2 Sync algoritması (read-only audit önce)

Her oturum başında veya transition PR cycle'ı sonrası:

```bash
# 1. Primary worktree durumu (read-only)
cd /Users/selmanay/Desktop/nodrat
echo "Branch: $(git branch --show-current)"
echo "HEAD: $(git rev-parse HEAD)"
echo "origin/main: $(git rev-parse origin/main)"
git status --short --branch

# 2. Eski wiki/docs yolları var mı?
for p in wiki/plans wiki/topics/refactor-pr-checklist.md \
         docs/engineering/modular-monolith-architecture.md; do
  [ -e "$p" ] && echo "OK $p" || echo "MISSING $p"
done

# 3. Concurrent main worktree var mı?
git worktree list | grep "\[main\]"
```

#### 11.3 Çözüm yolları (öncelik sırası)

**A. Concurrent main worktree'yi güncelle (en güvenli, FF-only):**
```bash
git -C /Users/selmanay/Desktop/nodrat/.claude/worktrees/<main-worktree>/ \
    pull --ff-only origin main
```
Kullanıcı bu worktree path'inden wiki/docs yeni state'i görür. Primary stale kalır ama navigasyon noktası güncel.

**B. Primary'yi main'e taşı (concurrent worktree yoksa veya silinebilirse):**
```bash
# Concurrent main worktree var ise önce kaldır (uncommitted yoksa):
git worktree remove /path/to/concurrent/main-worktree
cd /Users/selmanay/Desktop/nodrat
git switch main
git pull --ff-only origin main
```
Eski fix branch'i silinmez — sonradan `git switch <branch>` ile dönülebilir.

**C. Tüm worktree'leri tek seferde güncelle:**
```bash
# Her worktree için (sadece tracked branch güncel'se, FF-only):
git worktree list --porcelain | grep "^worktree" | awk '{print $2}' | while read wt; do
  branch=$(git -C "$wt" branch --show-current)
  echo "$wt → $branch"
  # Sadece main ise FF-only pull:
  [ "$branch" = "main" ] && git -C "$wt" pull --ff-only origin main
done
```

#### 11.4 Hard kurallar

- ✅ **Read-only audit önce** — primary worktree durumu hep raporlanır
- ✅ **FF-only pull** (`--ff-only`) — non-FF varsa rebase/merge yapma, kullanıcıya rapor et
- 🛑 **Uncommitted varsa hiçbir destructive işlem yapma** (memory `feedback_git_stash_safety`)
- 🛑 **`git reset --hard` / `git restore .` ASLA otomatik** — kullanıcı onayı şart
- ✅ **Komut sırasını kullanıcıya ver** — Claude doğrudan executable değilse bile rapor önemli

## Çıkarımlar

1. Paralel worktree workflow modüler monolit refactor'ı hızlandırır **ama disiplin gerektirir**. Çakışmalar genelde wiki/index.md ve main.py'de olur.
2. Master plan dosyası **kalıcı state** — her oturum yeni başlıyor gibi okunur; kaybolan context burada bulunur.
3. Wiki write disiplini (CLAUDE.md §1.3) modüler monolit boyunca daha kritik — paralel modül PR'larında karışıklık çıkar.

## İlişkiler

- **Bağlı CLAUDE.md bölümü:** §1.3 (Paralel worktree write disiplini)
- **Bağlı memory:** `feedback_worktree_git_discipline`, `feedback_git_stash_safety`, `feedback_deploy_lessons`, `feedback_verify_main_post_merge`
- **Bağlı playbook:** [[refactor-pr-checklist]], [[refactor-anti-patterns-do-not-do]]

## Açık sorular / TODO

- (Faz 2+) İki agent eş zamanlı modül taşırsa otomatik conflict-resolution patternı denetlenmeli — şu an manuel disiplin.

## Kaynaklar

- [CLAUDE.md §1.3](../../CLAUDE.md)
- memory MEMORY.md
- [wiki/plans/modular-monolith-transition-master-plan.md](../plans/modular-monolith-transition-master-plan.md)
