from __future__ import annotations

from typing import Any

from mock_company.db import get_faults, set_faults


def api_is_down(conn) -> bool:
    return get_faults(conn).get("api_down") in {"1", "true", "yes", "on"}


def ui_is_down(conn) -> bool:
    return get_faults(conn).get("ui_down") in {"1", "true", "yes", "on"}


def slow_ms(conn) -> int:
    raw = get_faults(conn).get("slow_ms", "0")
    try:
        return max(0, int(raw))
    except ValueError:
        return 0


def apply_fault_updates(conn, payload: dict[str, Any]) -> dict[str, str]:
    allowed = {"api_down", "ui_down", "slow_ms"}
    updates = {key: value for key, value in payload.items() if key in allowed}
    return set_faults(conn, updates)
