from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ToolResult(BaseModel):
    ok: bool
    data: dict | list | str | None = None
    error: str | None = None
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    retryable: bool = False


class ToolSpec(BaseModel):
    name: str
    description: str
    risk: str
    args_schema: dict[str, Any]


def normalize_ticket(raw: dict[str, Any], source: str) -> dict[str, Any]:
    def _int(value: Any) -> int | None:
        if value is None or value == "":
            return None
        return int(value)

    def _bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        return str(value).lower() in {"1", "true", "yes"}

    return {
        "id": str(raw.get("id") or raw.get("data-id") or ""),
        "title": raw.get("title") or "",
        "body": raw.get("body") or "",
        "customer": raw.get("customer") or "",
        "status": raw.get("status") or "",
        "priority": raw.get("priority") or "",
        "created_at": raw.get("created_at") or raw.get("createdAt") or "",
        "due_at": raw.get("due_at") or raw.get("dueAt") or None,
        "order_id": raw.get("order_id") or raw.get("orderId") or None,
        "refund_amount": _int(raw.get("refund_amount") if "refund_amount" in raw else raw.get("refundAmount")),
        "days_since_purchase": _int(
            raw.get("days_since_purchase") if "days_since_purchase" in raw else raw.get("daysSincePurchase")
        ),
        "refunded": _bool(raw.get("refunded", False)),
        "refunded_amount": _int(raw.get("refunded_amount") if "refunded_amount" in raw else raw.get("refundedAmount")),
        "source": source,
    }


def empty_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None
