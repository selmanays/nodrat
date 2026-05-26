"""T8-PRE-1 v2 regression guard: paket `__init__.py` lazy import.

## Bağlam — v68 + v69 dersleri

**v68 dersi (PR #1298 reverted):** Production module-level eager
`from .routes import router` pattern, `app.models.__init__.py`'dan paketi import
etmek collect-time'da `app.core.deps` partially init iken zincire dönerek
ImportError veriyor.

**v69 dersi (PR #1301 reverted):** v1'de eklenen
`test_app_models_init_does_not_pull_module_routes` testinin içinde
`_purge_cached_modules(("app.models", ...))` `app.models`'i sys.modules'tan
silip yeniden import → SQLAlchemy MetaData duplicate registration → 20 test
FAIL (1 doğrudan + 19 collateral).

## v2'de uygulanan strateji

1. **8 parametric test** korunur — her A grubu modül için paket import sonrası
   `app.core.deps not in sys.modules` doğrulanır. Bu test'ler SQLAlchemy
   metadata zincirine ulaşmaz (paket-init lazy → core.deps yüklenmez), bu
   yüzden global state çakışması yaratmaz. v1'de 8/8 PASS olduğu kanıtlandı.

2. **`app.models` lazy testi subprocess pattern'i ile çalıştırılır** —
   fresh Python process'te `import app.models` yapılır; sonra `sys.modules`
   içinde modül `routes.py` zincirlerinin leak edip etmediği kontrol edilir.
   Fresh process → SQLAlchemy MetaData state izole → ana process'in global
   registry'si bozulmaz.

Bkz.:
- wiki/topics/t8-model-relocation-mini-plan.md §3 hard-stop kuralı 11
- wiki/topics/t8-model-relocation-mini-plan.md §5 T8-PRE-1 v2 scope
- wiki/log.md v68 + v69 entries
"""

from __future__ import annotations

import importlib
import subprocess
import sys
import textwrap

import pytest

# T8 hedef + risk-altı modüller. Tüm A grubu modüllerin paket-init'i lazy olmalı.
_MODULES_REQUIRING_LAZY_INIT = (
    "app.modules.settings_admin",
    "app.modules.prompts_admin",
    "app.modules.legal",
    "app.modules.sft",
    "app.modules.sources",
    "app.modules.articles",
    "app.modules.style_profiles",
    "app.modules.media",
)


def _purge_cached_modules(prefixes: tuple[str, ...]) -> None:
    """Test isolation: yalnız modül paketlerini temizle.

    ÖNEMLİ: `app.models`'i ASLA bu fonksiyon ile temizlemeyin — module-level
    SQLAlchemy Table objesi MetaData'ya kaydedilmiş, ikinci import duplicate
    registration tetikler (v69 dersi, PR #1301 → #1302 revert).

    Modül paketlerini temizlemek güvenli çünkü bunların `__init__.py`'leri
    T8-PRE-1'de lazy yapıldı — module attribute (router, settings vb.) yok,
    sadece docstring + `__all__: list[str] = []`.
    """
    for name in list(sys.modules):
        for prefix in prefixes:
            if name == prefix or name.startswith(prefix + "."):
                del sys.modules[name]
                break


@pytest.mark.parametrize("module_name", _MODULES_REQUIRING_LAZY_INIT)
def test_module_init_does_not_pull_core_deps(module_name: str) -> None:
    """Paket import sırasında `app.core.deps` import edilmemeli.

    Hata mesajı: `__init__.py`'de `from .routes import router` (veya benzeri
    eager re-export) bulunuyor; `routes.py`'nin `app.core.deps` import zinciri
    paket yükleme zamanında tetikleniyor. Çözüm: re-export'u kaldır,
    `main.py` doğrudan `from app.modules.X.routes import router as X_router`
    kullansın.
    """
    # Hedef modül paketini ve app.core.deps'i temizle. NOT: app.models'a
    # DOKUNULMUYOR (v69 dersi — SQLAlchemy MetaData duplicate registration).
    _purge_cached_modules((module_name, "app.core.deps"))

    importlib.import_module(module_name)

    leaked = "app.core.deps" in sys.modules
    assert not leaked, (
        f"{module_name} paket import sırasında `app.core.deps`'i sys.modules'a "
        f"sokuyor — paket `__init__.py`'sinde eager `from .routes import ...` "
        f"vardır. T8-PRE-1 (v68/v69) bu pattern'i yasaklıyor; bkz. "
        f"wiki/topics/t8-model-relocation-mini-plan.md §3 hard-stop 11."
    )


def test_app_models_lazy_via_subprocess() -> None:
    """`app.models` import edildiğinde modül route zincirleri leak etmemeli.

    **v69 dersi — subprocess-based fresh process kullanımı:** Bu test
    `_purge_cached_modules(("app.models", ...))` YAPMAZ. Bunun yerine,
    fresh Python process spawn ederek `import app.models` zincirini izole
    olarak doğrular. Bu sayede SQLAlchemy MetaData global state'i ana test
    process'inin registry'sini bozmaz.

    Fail durumunda: `app.models.__init__.py`'de bir model dosyası
    `from app.modules.X.models import Y` yaparsa **AND** o paketin
    `__init__.py`'si eager `from .routes import router` yapıyorsa,
    `app.modules.X.routes` zinciri yüklenir. T8 model relocation sırasında
    bu pattern collect-time circular import yarattığı için `__init__.py`'lerin
    LAZY kalması zorunludur.
    """
    snippet = textwrap.dedent(
        """
        import sys
        import app.models  # noqa: F401  — Alembic env.py:40 pattern

        # 8 A grubu modülün route'larından herhangi biri leak etti mi?
        targets = (
            "app.modules.settings_admin.routes",
            "app.modules.prompts_admin.routes",
            "app.modules.legal.routes",
            "app.modules.sft.admin.routes",
            "app.modules.sources.admin.routes",
            "app.modules.articles.admin.routes",
            "app.modules.style_profiles.routes",
            "app.modules.media.admin.routes",
        )
        leaked = [t for t in targets if t in sys.modules]
        if leaked:
            print("LEAKED:", leaked, file=sys.stderr)
            sys.exit(1)
        print("OK")
        """
    ).strip()

    result = subprocess.run(  # noqa: S603 — sys.executable mutlak path
        [sys.executable, "-c", snippet],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, (
        f"`app.models` import sırasında modül route'ları yüklendi:\n"
        f"stdout: {result.stdout}\n"
        f"stderr: {result.stderr}\n\n"
        f"Bu, T8 model relocation sırasında collect-time circular import "
        f"riski yaratır (PR #1298 dersi). Çözüm: ilgili modülün "
        f"`__init__.py`'sini lazy yap (T8-PRE-1 v68 dersi)."
    )
