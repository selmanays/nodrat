"""Accounts modülü auth/role dependency surface.

FastAPI auth/role bağımlılıkları: `get_current_user`, `require_admin`,
`require_foreign_transfer_consent`, `get_client_ip`, `bearer_scheme`,
`CURRENT_CONSENT_VERSION`.

## T7-7 geçiş notu (v99 mini-plan → [[t7-7-deps-split-mini-plan]])

Bu dosya **geçiş döneminde** `app/core/deps.py`'den re-export eden bir
**shim**'dir. T7-7'nin amacı `core/deps.py`'yi accounts modülüne taşıyıp
`core/* → app.models.user` import edge'ini ortadan kaldırmak (T8-21
User+Session relocation prereq).

- **Neden shim:** relocation atomiktir — `core/deps.py` silinince 24 caller
  aynı anda kırılır; `core/deps.py`'de `from app.modules.accounts.deps import *`
  re-export stub'ı ise `core/* must not import modules/*` ihlali (yasak).
  Çözüm: ters-yön shim — `accounts → core` import LEGAL (hiçbir contract
  modules→core yasaklamaz). Caller'lar ≤8 batch'te bu modüle flip edilir
  (T7-7b/c/d); gerçek implementasyon + `core/deps.py` silme T7-7e'de.
- **Bu shim davranış-koruyandır:** aynı dependency objelerini re-export eder
  (FastAPI Depends identity korunur).

docs/engineering/api-contracts.md §0 (routing)
docs/engineering/threat-model.md §2 (authn/z)
"""

from __future__ import annotations

from app.core.deps import (  # T7-7 geçiş re-export; gerçek impl T7-7e'de
    CURRENT_CONSENT_VERSION,
    bearer_scheme,
    get_client_ip,
    get_current_user,
    require_admin,
    require_foreign_transfer_consent,
)

__all__ = [
    "CURRENT_CONSENT_VERSION",
    "bearer_scheme",
    "get_client_ip",
    "get_current_user",
    "require_admin",
    "require_foreign_transfer_consent",
]
