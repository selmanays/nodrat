"""Re-export shim — `User` + `Session` artık `app/modules/accounts/models.py`'de (T8-21).

T8-21 (User+Session relocation) geçiş döneminde legacy `from app.models.user import ...`
caller'larını çalışır tutar. Caller'lar T8-21b..e'de DIRECT path'e
(`app.modules.accounts.models`) flip edilir; bu shim T8-21e'de SİLİNİR.
"""

from __future__ import annotations

from app.modules.accounts.models import Session, User

__all__ = ["Session", "User"]
