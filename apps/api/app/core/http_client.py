"""Re-export shim — http_client → shared/http/client (P4.5a, Modular Monolith v2).

P4.5 (#1092 P4): HTTP fetch primitive `app/shared/http/client.py`'ye taşındı
(Layer 0 — kernel modüller [sources/articles/media] + crawler primitives [robots/rss]
import ediyor → shared'da olmalı; modules/crawler kernel→crawler yasağı nedeniyle uygun değil).
Bu shim geriye dönük uyumluluk içindir; caller'lar P4.5a-2'de
`app.shared.http.client`'a flip edilir, sonra bu dosya SİLİNİR.
"""

from app.shared.http.client import (  # noqa: F401
    NODRAT_BOT_ACCEPT_LANGUAGE,
    NODRAT_BOT_FROM,
    NODRAT_BOT_USER_AGENT,
    fetch_text,
    get_async_client,
    get_nodrat_headers,
)
