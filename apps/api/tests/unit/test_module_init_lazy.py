"""T8-PRE-1 regression guard: paket `__init__.py` lazy import.

PR #1298 (T8-1 app_setting → modules/settings_admin/models.py) main CI'da
collect-time circular import nedeniyle FAIL etti:

    test_admin_rag → app.api.admin_rag → app.core.deps (PARTIALLY INIT)
      → app.core.deps:20 from app.models.user
      → app.models.__init__.py:30 from app.modules.settings_admin.models import AppSetting
      → app.modules.settings_admin.__init__.py:15 from .routes import router
      → routes.py:30 from app.core.deps import get_client_ip
      → ❌ ImportError

Bu test, T8-PRE-1'in (v68) 8 A grubu modülün `__init__.py`'lerinden
`from .routes import router` satırlarını kaldırma kararının (collect-time
circular import koruması) regression guard'ıdır.

Test: 8 modül `__init__.py` import edildiğinde `app.core.deps` `sys.modules`'da
**olmamalı**. Eğer ileride bir katkıcı `__init__.py`'ye eager `from .routes`
eklerse, bu test FAIL eder ve dersi hatırlatır.

Bkz.:
- wiki/topics/t8-model-relocation-mini-plan.md §3 hard-stop kuralı 11
- wiki/log.md v68 entry (PR #1298 reverted, T8-PRE-1 önerisi)
"""

from __future__ import annotations

import importlib
import sys

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
    """Test isolation: ilgili paketleri sys.modules'tan temizle."""
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
    # Bu paketleri ve `app.core.deps`'i temizle ki taze import durumu test edilsin.
    _purge_cached_modules((module_name, "app.core.deps", "app.models"))

    importlib.import_module(module_name)

    leaked = "app.core.deps" in sys.modules
    assert not leaked, (
        f"{module_name} paket import sırasında `app.core.deps`'i sys.modules'a "
        f"sokuyor — paket `__init__.py`'sinde eager `from .routes import ...` "
        f"vardır. T8-PRE-1 (v68) bu pattern'i yasaklıyor; bkz. "
        f"wiki/topics/t8-model-relocation-mini-plan.md §3 hard-stop 11."
    )


def test_app_models_init_does_not_pull_module_routes() -> None:
    """`app.models.__init__.py` yüklendiğinde modül route zincirleri tetiklenmemeli.

    Daha sıkı kontrol: `from app.models import *` (Alembic env.py:40 pattern'i)
    çalıştığında 8 modülün `routes.py`'sini import etmemeli — çünkü T8 ileride
    `app.models.__init__.py`'dan `from app.modules.X.models import Y` ekleyecek.
    """
    _purge_cached_modules(("app.models", "app.modules", "app.core.deps"))

    importlib.import_module("app.models")

    leaked_routes = [
        name
        for name in sys.modules
        if name.startswith("app.modules.")
        and name.endswith(".routes")
        and any(name.startswith(m) for m in _MODULES_REQUIRING_LAZY_INIT)
    ]
    assert not leaked_routes, (
        f"`app.models` import sırasında modül route'ları yüklendi: {leaked_routes}. "
        f"Bu, T8 model relocation sırasında collect-time circular import "
        f"riski yaratır (PR #1298 dersi)."
    )
