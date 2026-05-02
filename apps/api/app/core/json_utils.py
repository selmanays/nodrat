"""JSON utility — prompt payload encoding (#153).

LLM payload'larında Decimal/datetime/UUID gibi tipler ham JSON'a serialize
edilmez. Bu helper standart fallback sağlar.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID


def json_default(obj: Any) -> Any:
    """JSON encode için fallback — Decimal/datetime/UUID için string/float dönüş.

    Kullanım:
        json.dumps(payload, default=json_default, ensure_ascii=False)
    """
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, set):
        return list(obj)
    return str(obj)


def dumps(obj: Any, **kwargs: Any) -> str:
    """json.dumps wrapper — default=json_default + ensure_ascii=False."""
    kwargs.setdefault("default", json_default)
    kwargs.setdefault("ensure_ascii", False)
    return json.dumps(obj, **kwargs)
