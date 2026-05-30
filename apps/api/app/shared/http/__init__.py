"""Shared infrastructure: http

HTTP fetch primitive (NodratBot UA + robots-aware client + fetch_text).
P4.5a (v2): app.core.http_client → app.shared.http.client (kernel + crawler
primitives kullanıyor → Layer 0 shared).

Public module:
    client — get_async_client, fetch_text, get_nodrat_headers, NODRAT_BOT_* sabitleri
"""
