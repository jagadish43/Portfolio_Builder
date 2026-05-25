from __future__ import annotations

import json
from typing import Any


def parse_json_object(raw: str | None, fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    if not raw:
        return dict(fallback or {})
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return dict(fallback or {})
    return value if isinstance(value, dict) else dict(fallback or {})


def parse_json_list(raw: str | None) -> list[dict[str, Any]]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def parse_json_string_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def dump_json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"))
